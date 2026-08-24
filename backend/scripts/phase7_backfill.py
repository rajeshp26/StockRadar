"""
StockerPro — Phase 7 backfill script
Run once after all Phase 1–6 changes are deployed to production.

What this does:
  1. Resets all companies to data_completeness_status = 'INITIAL'
  2. Triggers a full defeatbeta re-fetch for every company (force_full_history=True)
  3. Logs per-company success / failure to a local log file for review

Usage:
  cd backend
  python scripts/backfill_all_companies.py [--dry-run] [--company-id 123]

Flags:
  --dry-run        Print what would happen; make no DB or provider calls
  --company-id N   Only process a single company (spot-check mode)
  --concurrency N  Max simultaneous fetches (default: 3; keep low to avoid
                   rate-limiting on defeatbeta)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

# ── ensure backend/ is on sys.path when run from repo root ──────────────────
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_derived_financial_metrics,
)
from application.services.recompute_guard import RecomputeGuard
from application.services.valuation_service import ValuationService
from database import supabase
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from infrastructure.repositories.valuation_repository import ValuationRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider

# ── logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_backend / "logs" / "backfill.log", mode="a"),
    ],
)
logger = logging.getLogger("backfill")


# ── helpers ──────────────────────────────────────────────────────────────────
async def reset_company_status(repo: SupabaseFinancialRepository, company_id: int) -> None:
    """
    Reset a company so the provider treats the next fetch as a first-ever load.
    Clears fiscal year / quarter watermarks so force_full_history is effective
    even if the company was previously marked COMPLETE or CURRENT.
    """
    supabase.table("companies").update({
        "data_completeness_status": "INITIAL",
        "last_refreshed_fiscal_year": None,
        "last_refreshed_fiscal_quarter": None,
        "last_financial_refresh_at": None,
        "first_financial_data_loaded_at": None,
    }).eq("company_id", company_id).execute()


async def backfill_company(
    repo: SupabaseFinancialRepository,
    provider: DefeatBetaProvider,
    valuation_service: ValuationService,
    company: dict,
    dry_run: bool,
) -> dict:
    company_id = company["company_id"]
    symbol = company["ticker_symbol"]
    result = {"company_id": company_id, "symbol": symbol, "status": "pending"}

    try:
        if dry_run:
            logger.info("[DRY RUN] would reset + re-fetch %s (id=%s)", symbol, company_id)
            result["status"] = "dry_run"
            return result

        # 1. Reset watermarks so the scheduler won't skip periods
        await reset_company_status(repo, company_id)
        logger.info("Reset %s (id=%s) → INITIAL", symbol, company_id)

        # 2. Full re-fetch — bypasses incremental filter, limit to 2021+
        fin = await provider.get_all_financials_optimized(
            symbol=symbol,
            company_id=company_id,
            force_full_history=True,
            min_fiscal_year=2021,
        )

        # 3. Persist
        counts = await repo.upsert_all_financials(fin)

        # 4. Update watermarks
        if fin.income_statements.rows:
            annual = [r for r in fin.income_statements.rows if r.fiscal_quarter is None]
            if annual:
                latest = max(annual, key=lambda r: r.fiscal_year)
                await repo.update_company_refresh_metadata(
                    company_id=company_id,
                    last_fiscal_year=latest.fiscal_year,
                    last_fiscal_quarter=None,
                    is_first_load=True,
                    next_earnings_date=fin.next_earnings_date,
                )

        total_rows = sum(counts.values())
        logger.info(
            "✅ %s (id=%s): %d total rows upserted %s",
            symbol, company_id, total_rows, counts,
        )

        # 5. Trigger valuation
        logger.info("Triggering RI valuation for %s (id=%s)", symbol, company_id)
        await valuation_service.compute_residual_income_if_stale(
            symbol=symbol, user_id=None, force=True
        )
        logger.info("✅ RI valuation complete for %s (id=%s)", symbol, company_id)

        # 6. Compute derived financial metrics
        try:
            ratios = await compute_and_upsert_derived_financial_metrics(company_id=company_id)
            logger.info(
                "[DERIVED] %s: %d rows changed", symbol, ratios.get("rows_changed", 0),
            )
        except Exception as de:
            logger.error("[DERIVED] %s: %s", symbol, de)

        result["status"] = "ok"
        result["rows"] = counts

    except Exception as e:
        logger.error("❌ %s (id=%s): %s", symbol, company_id, e, exc_info=True)
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
    from providers.edgar_provider import EdgarToolsProvider
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    sd = StockdexMacrotrendsProvider()
    ed = EdgarToolsProvider()
    provider = DefeatBetaProvider(yfinance_provider=yf, stockdex_provider=sd, edgar_provider=ed)

    # Instantiate valuation services
    valuation_repo = ValuationRepository()
    recompute_guard = RecomputeGuard(valuation_repo)
    valuation_service = ValuationService(repo=valuation_repo, guard=recompute_guard)

    # Fetch target companies
    query = supabase.table("companies").select("company_id, ticker_symbol, security_type")
    query = query.eq("security_type", "stock")
    if company_ids:
        if len(company_ids) == 1:
            query = query.eq("company_id", company_ids[0])
        else:
            query = query.in_("company_id", company_ids)
    resp = query.execute()

    companies = resp.data or []
    if company_ids and len(companies) < len(company_ids):
        skipped = set(company_ids) - {c["company_id"] for c in companies}
        logger.warning("Non-stock companies filtered out (ids=%s)", sorted(skipped))
    if not companies:
        logger.warning("No companies found — nothing to backfill.")
        return

    logger.info(
        "Starting backfill: %d companies | concurrency=%d | dry_run=%s",
        len(companies), concurrency, dry_run,
    )

    sem = asyncio.Semaphore(concurrency)
    started_at = datetime.utcnow()

    async def bounded(company: dict) -> dict:
        async with sem:
            return await backfill_company(repo, provider, valuation_service, company, dry_run)

    results = await asyncio.gather(*[bounded(c) for c in companies])

    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    elapsed = (datetime.utcnow() - started_at).total_seconds()

    logger.info(
        "Backfill complete: %d ok, %d errors, %.1fs elapsed",
        ok, err, elapsed,
    )

    if err:
        failed = [r["symbol"] for r in results if r["status"] == "error"]
        logger.warning("Failed symbols: %s", failed)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="StockerPro full-history backfill")
    parser.add_argument("--dry-run", action="store_true", help="Print plan, make no changes")
    parser.add_argument("--company-id", type=int, nargs="*", default=None, help="Company ID(s) to process (omit for all)")
    parser.add_argument("--concurrency", type=int, default=3, help="Max parallel fetches")
    args = parser.parse_args()

    asyncio.run(run_backfill(
        company_ids=args.company_id,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    ))


if __name__ == "__main__":
    main()
