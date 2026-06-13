"""
Backfill: Compute valuation multiples (EV/EBITDA, P/FCF, market_cap, enterprise_value)
for all historical quarters for all active companies.

Runs compute_and_upsert_quarterly_valuation_metrics for every company that
has quarterly income_statements. Since the function now pre-computes all
valuation multiples (trailing P/E, EV/EBITDA, P/FCF, market_cap, enterprise_value),
this single backfill populates all of them.

Usage:
    cd backend && python scripts/backfill_valuation_multiples.py
"""
import asyncio
import logging
import sys
import time
from datetime import datetime

sys.path.insert(0, ".")
from database import supabase
from config import settings
from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_quarterly_valuation_metrics,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main():
    logger.info("=" * 60)
    logger.info("VALUATION MULTIPLES BACKFILL (EV/EBITDA, P/FCF, market_cap, enterprise_value)")
    logger.info("=" * 60)

    # Find all companies that have quarterly income statement data
    resp = (
        supabase.table("income_statements")
        .select("company_id")
        .not_.is_("fiscal_quarter", "null")
        .execute()
    )
    rows = resp.data or []
    company_ids = sorted(set(
        int(r["company_id"]) for r in rows if r.get("company_id")
    ))
    logger.info("Found %d companies with quarterly income data", len(company_ids))

    # Check which already have ev_ebitda populated
    already_resp = (
        supabase.table("financial_ratios")
        .select("company_id")
        .not_.is_("ev_ebitda", "null")
        .execute()
    )
    already_done = set(
        int(r["company_id"]) for r in (already_resp.data or [])
    )
    pending = [cid for cid in company_ids if cid not in already_done]
    logger.info(
        "Already have ev_ebitda: %d, Pending: %d",
        len(already_done), len(pending),
    )

    if not pending:
        logger.info("Nothing to backfill — all companies already have valuation multiples")
        return

    start = time.time()
    ok = 0
    fail = 0
    total_rows = 0

    for i, cid in enumerate(pending):
        try:
            result = await compute_and_upsert_quarterly_valuation_metrics(cid)
            written = result.get("rows_changed", 0)
            count = result.get("count", 0)
            if count > 0:
                ok += 1
                total_rows += written if written else count
                logger.info(
                    "[%d/%d] company_id=%s → %d rows (changed=%d)",
                    i + 1, len(pending), cid, count, written,
                )
            else:
                logger.info(
                    "[%d/%d] company_id=%s → skipped (no data)",
                    i + 1, len(pending), cid,
                )
        except Exception as e:
            fail += 1
            logger.error("[%d/%d] company_id=%s failed: %s", i + 1, len(pending), cid, e)

    elapsed = time.time() - start
    logger.info("=" * 60)
    logger.info("COMPLETE: %d ok, %d failed, %d total rows, %.1fs", ok, fail, total_rows, elapsed)


if __name__ == "__main__":
    asyncio.run(main())
