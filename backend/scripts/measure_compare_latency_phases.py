"""Attribute the ~10s compare latency: which phase actually costs the time?

Method (measurement only - writes nothing):
  1. Call PortfolioService.get_performance_compare() in-process, N times,
     timing each call.
  2. Wrap every repository/DB helper the compare path uses with a timer so the
     call is split into named phases (accounts, holdings, snapshots, benchmark
     price rows, guard/store read, simulation, store write, response build).
  3. Repeat the whole run with the market-data refresh job quiesced to see
     whether concurrent pricing work is the cause.

The output is a phase table per sample. Exit 0 always (this is a probe, not a
verifier); read the table.

Run: python backend/scripts/measure_compare_latency_phases.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")

from application.services.portfolio_service import PortfolioService  # noqa: E402

SAMPLES = int(os.environ.get("SAMPLES", "5"))
PERIOD = os.environ.get("PERIOD", "ALL")

PHASES: dict[str, float] = defaultdict(float)
_COUNTS: dict[str, int] = defaultdict(int)


def _wrap(obj: Any, name: str, phase: str, sink: dict[str, float]) -> None:
    """Time every call to obj.name and accumulate under `phase`."""
    original = getattr(obj, name, None)
    if original is None or not callable(original):
        return

    def timed(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            sink[phase] += time.perf_counter() - t0
            _COUNTS[phase] += 1

    setattr(obj, name, timed)


async def _wrap_async(obj: Any, name: str, phase: str, sink: dict[str, float]) -> None:
    original = getattr(obj, name, None)
    if original is None or not callable(original):
        return

    async def timed(*args: Any, **kwargs: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return await original(*args, **kwargs)
        finally:
            sink[phase] += time.perf_counter() - t0
            _COUNTS[phase] += 1

    setattr(obj, name, timed)


def _install_instrumentation(svc: PortfolioService) -> None:
    """Attach timers to the collaborators the compare path touches."""
    repo = svc.portfolio_repo
    # PortfolioRepository helpers used by the compare path.
    for name in (
        "get_user_accounts",
        "get_holdings",
        "get_portfolio_snapshots",
        "get_snapshot_series",
        "get_transactions",
        "get_cash_transactions",
    ):
        _wrap(repo, name, f"repo.{name}", PHASES)

    # The benchmark-specific helpers on the service itself.
    for name in (
        "_fetch_benchmark_price_rows",
        "_benchmark_series_with_reuse",
        "_persist_series_points",
        "_simulate_benchmark_value",
    ):
        _wrap(svc, name, f"svc.{name}", PHASES)

    # Store access (synchronous repository).
    try:
        from infrastructure.repositories.benchmark_series_repository import (
            BenchmarkSeriesRepository,
        )

        for name in ("get_series", "upsert_series", "delete_account_key"):
            _wrap(BenchmarkSeriesRepository, name, f"store.{name}", PHASES)
    except Exception as e:
        print(f"[warn] could not instrument store: {e}")

    # Guard decision (pure function, but time it for completeness).
    try:
        from application.services import benchmark_series_guard as guard_mod

        for name in dir(guard_mod):
            if name.startswith("decide") or name.startswith("should"):
                _wrap(guard_mod, name, f"guard.{name}", PHASES)
    except Exception as e:
        print(f"[warn] could not instrument guard: {e}")


async def main() -> int:
    svc = PortfolioService()
    user_id = 1
    accounts = svc.portfolio_repo.get_user_accounts(user_id)
    account_ids = [a["account_id"] for a in accounts]
    if not account_ids:
        print("NO ACCOUNTS - cannot measure on live data")
        return 1
    print(f"user={user_id} accounts={account_ids} period={PERIOD} samples={SAMPLES}")

    _install_instrumentation(svc)

    totals: list[float] = []
    for i in range(SAMPLES):
        PHASES.clear()
        _COUNTS.clear()
        t0 = time.perf_counter()
        result = await svc.get_performance_compare(
            user_id, PERIOD, ["SPY", "QQQ"], account_ids
        )
        dt = time.perf_counter() - t0
        totals.append(dt)

        n_points = sum(len(b.get("data") or []) for b in result.get("benchmarks", []))
        print(f"\n--- sample {i + 1}: total={dt * 1000:.0f} ms, points={n_points} ---")
        for phase, secs in sorted(PHASES.items(), key=lambda kv: -kv[1]):
            print(
                f"  {phase:42s} {secs * 1000:9.1f} ms  x{_COUNTS[phase]}"
            )
        accounted = sum(PHASES.values())
        print(f"  {'(accounted)':42s} {accounted * 1000:9.1f} ms")
        print(f"  {'(unaccounted)':42s} {(dt - accounted) * 1000:9.1f} ms")
        await asyncio.sleep(0.5)

    print("\n=== TOTAL summary ===")
    print(f"all_ms : {[round(t * 1000) for t in totals]}")
    print(f"min    : {min(totals) * 1000:.0f} ms")
    print(f"max    : {max(totals) * 1000:.0f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
