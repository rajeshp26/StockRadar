"""Attribute the ~10s compare latency at the DB boundary.

Previous measurement: 99.7% of the call was OUTSIDE every service/repository
method instrumented at the Python level. That means the time is inside a DB
round-trip or a blocking call. This probes the lowest common denominator: the
Supabase/PostgREST client itself.

Method (measurement only - writes nothing):
  Wrap the supabase client's query builder so every .execute() is timed and
  labelled with its table + filters. Then run the compare call once and print
  a per-call table sorted by cost.

Run: python backend/scripts/measure_compare_db_calls.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")

# Import the shared client the services use.
from database import supabase  # noqa: E402

CALLS: list[tuple[str, float]] = []
COUNTS: dict[str, int] = defaultdict(int)
TOTALS: dict[str, float] = defaultdict(float)


class _TimedExecute:
    """Proxy that times .execute() on a PostgREST query builder."""

    def __init__(self, inner: Any, label: str):
        self._inner = inner
        self.__label = label

    def execute(self) -> Any:
        t0 = time.perf_counter()
        try:
            return self._inner.execute()
        finally:
            dt = time.perf_counter() - t0
            CALLS.append((self.__label, dt))
            TOTALS[self.__label] += dt
            COUNTS[self.__label] += 1

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if callable(attr):
            def chained(*args: Any, **kwargs: Any) -> Any:
                result = attr(*args, **kwargs)
                # The builder returns itself for chainable calls.
                if hasattr(result, "execute"):
                    return _TimedExecute(result, self.__label)
                return result

            return chained
        return attr


_TABLE_HOLDER: dict[int, str] = {}


def _install() -> None:
    """Wrap supabase.table(name) so each builder carries its table label."""
    original_table = supabase.table

    def table(name: str) -> Any:
        builder = original_table(name)
        return _TimedExecute(builder, f"table:{name}")

    supabase.table = table  # type: ignore[method-assign]
    print("[probe] instrumented supabase.table()")


async def main() -> int:
    _install()

    from application.services.portfolio_service import PortfolioService

    svc = PortfolioService()
    user_id = 1
    accounts = svc.portfolio_repo.get_user_accounts(user_id)
    account_ids = [a["account_id"] for a in accounts]
    if not account_ids:
        print("NO ACCOUNTS")
        return 1

    CALLS.clear()
    TOTALS.clear()
    COUNTS.clear()

    t0 = time.perf_counter()
    result = await svc.get_performance_compare(user_id, "ALL", ["SPY", "QQQ"], account_ids)
    total = time.perf_counter() - t0

    db_total = sum(TOTALS.values())
    print(f"\n=== compare total = {total * 1000:.0f} ms ===")
    print(f"=== DB time      = {db_total * 1000:.0f} ms across {len(CALLS)} calls ===")
    print(f"=== non-DB time  = {(total - db_total) * 1000:.0f} ms ===")
    print(f"points           = {sum(len(b.get('data') or []) for b in result.get('benchmarks', []))}")

    print("\n--- per-table totals (all calls) ---")
    for label, secs in sorted(TOTALS.items(), key=lambda kv: -kv[1]):
        print(f"  {label:38s} {secs * 1000:9.1f} ms  x{COUNTS[label]}")

    print("\n--- 10 slowest individual calls ---")
    for label, secs in sorted(CALLS, key=lambda c: -c[1])[:10]:
        print(f"  {label:38s} {secs * 1000:9.1f} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
