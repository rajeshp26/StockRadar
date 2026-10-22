"""Is recording the full curve from a windowed request affordable?

Layer 2's read model must hold inception->today (the merge is stateful), but a
user request asks for one period. If recording the full curve requires a SECOND
snapshot read over ALL, that read is added to every windowed request.

This measures the two reads side by side so the cost is a number, not a guess:
  - the period read (what the request already does)
  - the ALL read (what recording would additionally need)

Measurement only. Run: python backend/scripts/measure_record_overhead.py
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
from infrastructure.repositories.portfolio_snapshots_repository import (  # noqa: E402
    PortfolioSnapshotsRepository,
)


async def main() -> int:
    svc = PortfolioService()
    account_ids = sorted(a["account_id"] for a in svc.portfolio_repo.get_user_accounts(1))
    repo = PortfolioSnapshotsRepository()
    print(f"accounts = {account_ids}\n")
    print(f"{'period':6s} {'rows':>7s} {'read_ms':>9s}")
    print("-" * 26)

    for period in ["1W", "1M", "YTD", "1Y", "5Y", "ALL"]:
        start, end = svc._period_to_date_range(period, account_ids)
        t0 = time.perf_counter()
        rows = repo.get_portfolio_snapshots_series(account_ids, start, end)
        ms = (time.perf_counter() - t0) * 1000
        print(f"{period:6s} {len(rows):7d} {ms:9.0f}")

    print(
        "\nIf recording needs the ALL read on top of a period read, add the ALL\n"
        "read cost to every windowed request. Compare against the current total\n"
        "request cost (~130-200 ms) before deciding."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
