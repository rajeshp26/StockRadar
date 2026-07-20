"""
Backfill historical snapshots — on-demand gap filling.

This is a SEPARATE process from the daily job. The daily job only builds
today's snapshot. This script fills historical gaps when needed:
- After initial setup (cold-start)
- After data corrections (e.g., price backfill)
- On-demand when the user requests a specific date range

Usage:
  cd backend
  python scripts/backfill_snapshots.py                    # fill all gaps
  python scripts/backfill_snapshots.py --account 9        # fill gaps for one account
  python scripts/backfill_snapshots.py --dry-run          # show what would be filled
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from config import settings
from shared.time_utils import now_utc
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from application.jobs.portfolio_snapshot_job import _fill_snapshot_gaps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_backend / "logs" / "backfill_snapshots.log", mode="a"),
    ],
)
logger = logging.getLogger("backfill_snapshots")


async def backfill_account(
    account_id: int,
    today: date,
    portfolio_repo: PortfolioRepository,
    financial_repo: SupabaseFinancialRepository,
    snapshots_repo: PortfolioSnapshotsRepository,
    spike_threshold: float,
    dry_run: bool,
) -> int:
    """Fill missing snapshots for a single account. Returns count of snapshots written."""
    account_currency_result = supabase.table("portfolio_accounts").select("currency").eq("account_id", account_id).limit(1).execute()
    account_currency = account_currency_result.data[0]["currency"] if account_currency_result.data else "CAD"

    holdings = supabase.table("portfolio_holdings").select("company_id, exchange_override").eq("account_id", account_id).execute()
    all_company_ids = [h["company_id"] for h in holdings.data if h.get("company_id")]
    exchange_overrides = {h["company_id"]: h.get("exchange_override") for h in holdings.data if h.get("exchange_override")}

    if not all_company_ids:
        logger.info(f"Account {account_id}: no holdings, skipping")
        return 0

    last_date = snapshots_repo.get_last_snapshot_date(account_id)
    if last_date is None:
        from infrastructure.repositories.event_store import EventStore
        event_store = EventStore()
        earliest = event_store.get_earliest_event_date(account_id)
        if not earliest:
            logger.info(f"Account {account_id}: no events, skipping")
            return 0
        start_date = date.fromisoformat(earliest)
    else:
        start_date = last_date + timedelta(days=1)

    if start_date > today:
        logger.info(f"Account {account_id}: no gaps to fill")
        return 0

    missing = snapshots_repo.get_missing_dates(account_id, start_date, today)
    if not missing:
        logger.info(f"Account {account_id}: no gaps to fill")
        return 0

    logger.info(f"Account {account_id}: {len(missing)} gap dates ({missing[0]} to {missing[-1]})")

    if dry_run:
        logger.info(f"Account {account_id}: DRY RUN — would fill {len(missing)} dates")
        return 0

    prices_by_company = await financial_repo.get_latest_prices(all_company_ids, today)
    price_history = portfolio_repo.get_all_prices_historical(all_company_ids, today)

    count = await _fill_snapshot_gaps(
        account_id=account_id,
        today=today,
        account_currency=account_currency,
        prices_by_company=prices_by_company,
        price_history=price_history,
        exchange_overrides=exchange_overrides,
        snapshots_repo=snapshots_repo,
        job_id_prefix=f"backfill_{today.isoformat()}",
        spike_threshold=spike_threshold,
        financial_repo=financial_repo,
        all_company_ids=all_company_ids,
    )

    logger.info(f"Account {account_id}: filled {count} snapshots")
    return count


async def main(account_id: int = None, dry_run: bool = False):
    today = now_utc().date()
    portfolio_repo = PortfolioRepository()
    financial_repo = SupabaseFinancialRepository()
    snapshots_repo = PortfolioSnapshotsRepository()
    spike_threshold = getattr(settings, "SNAPSHOT_SPIKE_THRESHOLD", 0.20)

    if account_id:
        accounts = [{"account_id": account_id}]
    else:
        accounts = portfolio_repo.get_user_accounts_all()

    if not accounts:
        logger.info("No accounts found")
        return

    logger.info(f"Backfilling snapshots for {len(accounts)} accounts (dry_run={dry_run})")

    total_written = 0
    for acc in accounts:
        aid = acc["account_id"]
        count = await backfill_account(
            account_id=aid,
            today=today,
            portfolio_repo=portfolio_repo,
            financial_repo=financial_repo,
            snapshots_repo=snapshots_repo,
            spike_threshold=spike_threshold,
            dry_run=dry_run,
        )
        total_written += count

    logger.info(f"Backfill complete: {total_written} snapshots written across {len(accounts)} accounts")


def cli():
    parser = argparse.ArgumentParser(description="Backfill historical snapshots.")
    parser.add_argument("--account", type=int, help="Account ID to backfill (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be filled")
    args = parser.parse_args()

    asyncio.run(main(account_id=args.account, dry_run=args.dry_run))


if __name__ == "__main__":
    cli()
