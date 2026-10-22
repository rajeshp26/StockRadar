"""Per-period cost AFTER Layer 1: is Layer 2 (denormalised series) still needed?

Times every period the user can select, warm, through the live service.
If each period is already fast, the narrow-table layer is buying little.
If a specific period is still slow, this names it.

Measurement only. Exit 0 always.
Run: python backend/scripts/measure_period_costs.py
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_BACKEND_ROOT / ".env")

from application.services.portfolio_service import PortfolioService  # noqa: E402

PERIODS = ["1W", "1M", "YTD", "1Y", "5Y", "ALL"]
REPEATS = 2


async def main() -> int:
    svc = PortfolioService()
    user_id = 1
    accounts = svc.portfolio_repo.get_user_accounts(user_id)
    account_ids = [a["account_id"] for a in accounts]
    if not account_ids:
        print("NO ACCOUNTS")
        return 1
    print(f"accounts={account_ids}  repeats={REPEATS}\n")
    print(f"{'period':6s} {'pass1_ms':>10s} {'pass2_ms':>10s} {'points':>7s}")
    print("-" * 38)

    for period in PERIODS:
        times: list[float] = []
        points = 0
        for _ in range(REPEATS):
            t0 = time.perf_counter()
            res = await svc.get_performance_compare(
                user_id, period, ["SPY", "QQQ"], account_ids
            )
            times.append((time.perf_counter() - t0) * 1000)
            points = sum(len(b.get("data") or []) for b in res.get("benchmarks", []))
        print(f"{period:6s} {times[0]:10.0f} {times[1]:10.0f} {points:7d}")

    print("\n(compare endpoint: portfolio series + benchmark series together)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
