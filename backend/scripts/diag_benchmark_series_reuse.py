"""Answer: on a normal request, does the compare endpoint REUSE the stored
series or recompute it cold every time?

This is the question timing alone cannot answer. The probe instruments
`_simulate_benchmark_value` and counts invocations per pass, and reports how
many date-points each pass actually computes. That distinguishes:

  * cold-on-first-call   -> 2 series simulated once, then 0 (reuse works)
  * never-reused         -> 2 series simulated on EVERY pass (reuse broken)

Run: python backend/scripts/diag_benchmark_series_reuse.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from application.services.portfolio_service import PortfolioService  # noqa: E402


async def main() -> int:
    svc = PortfolioService()
    user_id = 1
    accounts = svc.portfolio_repo.get_user_accounts(user_id)
    account_ids = [a["account_id"] for a in accounts]
    if not account_ids:
        print("NO ACCOUNTS - cannot probe on live data")
        return 1
    print(f"user={user_id} accounts={account_ids}")

    calls: list[tuple[str, int]] = []
    original = svc._simulate_benchmark_value

    def counting_sim(*args, **kwargs):
        dates = tuple(kwargs.get("snapshot_dates") or [])
        calls.append((str(kwargs.get("benchmark_company_id")), len(dates)))
        return original(*args, **kwargs)

    svc._simulate_benchmark_value = counting_sim  # type: ignore[method-assign]

    async def pass_(tag: str, period: str) -> None:
        calls.clear()
        t0 = time.perf_counter()
        res = await svc.get_performance_compare(user_id, period, ["SPY", "QQQ"], account_ids)
        ms = int((time.perf_counter() - t0) * 1000)
        n_series = len(calls)
        n_points = sum(n for _, n in calls)
        shapes = [(b["symbol"], len(b["data"])) for b in res["benchmarks"]]
        print(
            f"  {tag:26} period={period:3} {ms:6} ms  "
            f"simulated={n_series} series/{n_points} points  out={shapes}"
        )

    print()
    print("=" * 78)
    print("REUSE BEHAVIOUR (simulator invocation counts)")
    print("=" * 78)
    await pass_("1st ever (cold)", "ALL")
    await pass_("2nd (warm, same period)", "ALL")
    await pass_("3rd (warm, same period)", "ALL")
    await pass_("different period", "1Y")
    await pass_("back to ALL (warm)", "ALL")
    print()
    print("Reading: simulated=0 on a warm pass means the store was reused.")
    print("        simulated=2 on EVERY pass means reuse never happens.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
