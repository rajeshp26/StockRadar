"""
StockerPro — Company Summary Backfill Script

Populates the company_summary table for active companies (in portfolio/watchlist)
that currently have no data. Uses DefeatBeta primary with YFinance fallback.

Usage:
  cd backend
  python scripts/backfill_company_summary.py [--dry-run] [--company-id 123]

Flags:
  --dry-run        Print what would happen; make no DB or provider calls
  --company-id N   Only process a single company (spot-check mode)
  --concurrency N  Max simultaneous fetches (default: 5)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_backend / "logs" / "company_summary_backfill.log", mode="a"),
    ],
)
logger = logging.getLogger("company_summary_backfill")


async def process_company(
    repo: SupabaseFinancialRepository,
    provider: DefeatBetaProvider,
    company: dict,
    dry_run: bool,
) -> dict:
    company_id = company["company_id"]
    symbol = company["ticker_symbol"]
    result = {"company_id": company_id, "symbol": symbol, "status": "pending"}

    try:
        if dry_run:
            logger.info("[DRY RUN] would fetch company_summary for %s (id=%s)", symbol, company_id)
            result["status"] = "dry_run"
            return result

        summary = await provider.get_company_summary_optimized(symbol, company_id)
        if summary:
            await repo.upsert_company_summary(summary)
            filled = sum(
                1 for k in ("trailing_pe", "enterprise_to_ebitda", "market_cap", "enterprise_value")
                if summary.get(k) is not None
            )
            logger.info("OK %s (id=%s): %d/4 core fields populated", symbol, company_id, filled)
            result["status"] = "ok"
            result["fields_populated"] = filled
        else:
            logger.warning("NO_DATA %s (id=%s): no data returned", symbol, company_id)
            result["status"] = "no_data"

    except Exception as e:
        logger.error("FAIL %s (id=%s): %s", symbol, company_id, e, exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)

    return result


async def run_backfill(
    company_ids: list[int] | None,
    dry_run: bool,
    concurrency: int,
) -> None:
    repo = SupabaseFinancialRepository(supabase)
    yf = YFinanceProvider()
    provider = DefeatBetaProvider(yfinance_provider=yf)

    all_companies = await repo.get_active_companies_for_market_data()
    companies = [c for c in all_companies if c.get("security_type") == "stock"]
    skipped = len(all_companies) - len(companies)
    if skipped:
        logger.info("Skipped %d non-stock companies (ETF/index)", skipped)
    if company_ids:
        companies = [c for c in companies if c["company_id"] in company_ids]
        if not companies:
            logger.warning("No matching active stock companies found for IDs: %s", company_ids)
            return

    logger.info(
        "Starting company_summary backfill: %d companies | concurrency=%d | dry_run=%s",
        len(companies), concurrency, dry_run,
    )

    sem = asyncio.Semaphore(concurrency)
    started_at = datetime.utcnow()

    async def bounded(company: dict) -> dict:
        async with sem:
            return await process_company(repo, provider, company, dry_run)

    results = await asyncio.gather(*[bounded(c) for c in companies])

    ok = sum(1 for r in results if r["status"] == "ok")
    no_data = sum(1 for r in results if r["status"] == "no_data")
    err = sum(1 for r in results if r["status"] == "error")
    elapsed = (datetime.utcnow() - started_at).total_seconds()

    logger.info(
        "Backfill complete: %d ok, %d no_data, %d errors, %.1fs elapsed",
        ok, no_data, err, elapsed,
    )

    if err:
        failed = [r["symbol"] for r in results if r["status"] == "error"]
        logger.warning("Failed symbols: %s", failed)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="StockerPro company_summary backfill")
    parser.add_argument("--dry-run", action="store_true", help="Print plan, make no changes")
    parser.add_argument("--company-id", type=int, nargs="*", default=None, help="Company ID(s) to process (omit for all active)")
    parser.add_argument("--concurrency", type=int, default=5, help="Max parallel fetches")
    args = parser.parse_args()

    asyncio.run(run_backfill(
        company_ids=args.company_id,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()
