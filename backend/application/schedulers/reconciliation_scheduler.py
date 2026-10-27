"""
Reconciliation Scheduler (v3 planner)
======================================

Weekly gap-detection planner that re-enqueues refresh jobs for companies and
super-investors whose stored history is missing periods versus the expected
window.

Financial pass
--------------
For each financial-data candidate (same predicate as get_stale_financial_companies:
loaded, status INITIAL/PARTIAL/COMPLETE/CURRENT, stock or unspecified security
type), expected quarter-ends run from the quarter containing
first_financial_data_loaded_at through the last completed quarter. Any missing
period enqueues a company_refresh:{company_id}:financials job - the same dedupe
key the routine earnings planner uses, so the job merges (scopes/reasons/priority)
rather than duplicating work.

Investor pass
-------------
For each tracked super-investor, expected quarter-ends run over the last
SUPER_INVESTORS_INITIAL_QUARTERS quarters ending at the last completed quarter.
A holdings history shorter than that window enqueues investor_refresh:{cik}.

Design: docs/DATA_FRESHNESS_RECONCILIATION.md
"""

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
from config import settings
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from shared.time_utils import now_iso, now_utc

logger = logging.getLogger(__name__)

FINANCIAL_JOB_TYPE = "company_refresh"
FINANCIAL_DEDUPE_TEMPLATE = "company_refresh:{company_id}:financials"
FINANCIAL_SCOPES = ["financials"]
FINANCIAL_REASON = "reconciliation"
FINANCIAL_PRIORITY = 20
FINANCIAL_MAX_ATTEMPTS = 3

INVESTOR_JOB_TYPE = "investor_refresh"
INVESTOR_DEDUPE_TEMPLATE = "investor_refresh:{cik}"
INVESTOR_PRIORITY = 20
INVESTOR_MAX_ATTEMPTS = 3


from application.schedulers.quarter_utils import (
    as_date,
    quarter_end,
    quarter_ends_between,
    quarter_start,
    shift_quarters,
)

# Thin aliases so this module keeps its historical underscore helper names.
_quarter_start = quarter_start
_quarter_end = quarter_end
_quarter_ends_between = quarter_ends_between
_shift_quarters = shift_quarters
_as_date = as_date



class ReconciliationScheduler:
    """Weekly planner that detects and repairs missing financial/holdings history."""

    def __init__(self, financial_repo: SupabaseFinancialRepository | None = None):
        self.financial_repo = financial_repo or SupabaseFinancialRepository()

    async def plan(self, today: date | None = None) -> list[dict[str, Any]]:
        """Run both reconciliation passes; a failure in one never blocks the other."""
        target = today or now_utc().date()
        watermark = EarningsRefreshScheduler._last_completed_quarter_start(target)

        jobs: list[dict[str, Any]] = []
        try:
            jobs.extend(await self._reconcile_financials(watermark))
        except Exception:
            logger.exception("Reconciliation (financials pass) failed; continuing")
        try:
            jobs.extend(await self._reconcile_investors(watermark))
        except Exception:
            logger.exception("Reconciliation (investors pass) failed; continuing")
        return jobs

    async def _reconcile_financials(self, watermark: date) -> list[dict[str, Any]]:
        candidates = await self.financial_repo.get_financial_candidates()
        if not candidates:
            return []

        loads: list[date] = []
        for c in candidates:
            ld = _as_date(c.get("first_financial_data_loaded_at"), None)
            if ld is not None:
                loads.append(ld)
        if not loads:
            return []
        min_start = _quarter_start(min(loads))

        period_rows = await self.financial_repo.get_financial_periods_in_range(
            min_start, watermark
        )
        present_by_company: dict[Any, set[date]] = defaultdict(set)
        for row in period_rows:
            cid = row.get("company_id")
            pid = _as_date(row.get("period_end_date"), None)
            if cid is not None and pid is not None:
                present_by_company[cid].add(pid)

        jobs: list[dict[str, Any]] = []
        for candidate in candidates:
            cid = candidate.get("company_id")
            first_load = _as_date(candidate.get("first_financial_data_loaded_at"), None)
            if cid is None or first_load is None:
                continue
            ticker = candidate.get("ticker_symbol")
            if not ticker or not str(ticker).strip():
                logger.warning("Reconciliation: skipping company_id=%s - missing ticker_symbol", cid)
                continue
            expected = _quarter_ends_between(
                _quarter_start(first_load), watermark
            )
            missing_periods = expected - present_by_company.get(cid, set())
            if missing_periods:
                jobs.append({
                    "job_type": FINANCIAL_JOB_TYPE,
                    "dedupe_key": FINANCIAL_DEDUPE_TEMPLATE.format(company_id=cid),
                    "resource_type": "company",
                    "resource_id": str(cid),
                    "payload": {
                        "company_id": int(cid) if isinstance(cid, str) and cid.isdigit() else cid,
                        "ticker_symbol": str(ticker).strip().upper(),
                        "scopes": FINANCIAL_SCOPES,
                        "reasons": [FINANCIAL_REASON],
                    },
                    "priority": FINANCIAL_PRIORITY,
                    "max_attempts": FINANCIAL_MAX_ATTEMPTS,
                    "not_before": now_iso(),
                })
        if jobs:
            logger.warning(
                "Reconciliation: %d/%d companies with missing financial periods",
                len(jobs), len(candidates),
            )
        return jobs

    async def _reconcile_investors(self, watermark: date) -> list[dict[str, Any]]:
        tracked = await self.financial_repo.get_tracked_investors()
        if not tracked:
            return []

        initial_quarters = getattr(settings, "SUPER_INVESTORS_INITIAL_QUARTERS", 20)
        window_start = _shift_quarters(watermark, -(initial_quarters - 1))
        expected = _quarter_ends_between(window_start, watermark)

        period_rows = await self.financial_repo.get_investor_periods_in_range(
            window_start, watermark
        )
        present_by_investor: dict[int, set[date]] = defaultdict(set)
        for row in period_rows:
            iid = row.get("investor_id")
            qe = _as_date(row.get("quarter_end_date"), None)
            if iid is not None and qe is not None:
                present_by_investor[int(iid)].add(qe)

        jobs: list[dict[str, Any]] = []
        for investor in tracked:
            iid = investor.get("investor_id")
            cik = investor.get("cik")
            if iid is None or not cik:
                continue
            present = present_by_investor.get(int(iid), set())
            if len(present & expected) < len(expected):
                jobs.append({
                    "job_type": INVESTOR_JOB_TYPE,
                    "dedupe_key": INVESTOR_DEDUPE_TEMPLATE.format(cik=cik),
                    "resource_type": "investor",
                    "resource_id": str(cik),
                    "payload": {
                        "cik": cik,
                        "name": investor.get("investor_name"),
                        "firm": investor.get("firm_name"),
                        "tag": investor.get("investor_tag"),
                        "reasons": [FINANCIAL_REASON],
                    },
                    "priority": INVESTOR_PRIORITY,
                    "max_attempts": INVESTOR_MAX_ATTEMPTS,
                    "not_before": now_iso(),
                })
        if jobs:
            logger.warning(
                "Reconciliation: %d/%d investors with holdings history shorter than expected",
                len(jobs), len(tracked),
            )
        return jobs
