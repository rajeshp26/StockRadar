"""
Backfill script: compute quarterly Piotroski F-Score + Altman Z-Score for all
companies that have quarterly income_statement / balance_sheet / cash_flow data.

Usage:
    python -m scripts.backfill_quarterly_health_scores

Runs compute_and_upsert_quarterly_health_scores() for every company in the
database that has at least one fiscal year with quarterly data.

Safe to re-run (idempotent — version-gated upsert skips unchanged rows).
"""

from __future__ import annotations

import asyncio
import logging

from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_quarterly_health_scores,
)
from database import supabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info("Fetching all company IDs…")
    resp = supabase.table("companies").select("company_id").execute()
    companies = resp.data or []
    logger.info("Found %d companies", len(companies))

    total_changed = 0
    total_upserted = 0
    for i, c in enumerate(companies):
        cid = c["company_id"]
        result = await compute_and_upsert_quarterly_health_scores(cid)
        changed = result.get("rows_changed", 0)
        upserted = result.get("upserted", False)
        if upserted:
            total_changed += changed
            total_upserted += 1
        if (i + 1) % 10 == 0:
            logger.info("Progress: %d/%d companies processed", i + 1, len(companies))

    logger.info(
        "Backfill complete. %d/%d companies had new rows written (%d total rows changed).",
        total_upserted, len(companies), total_changed,
    )


if __name__ == "__main__":
    asyncio.run(main())
