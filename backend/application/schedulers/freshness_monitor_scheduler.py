"""
Freshness Monitor Scheduler (v3 planner)
=========================================

Daily planner that snapshots data-freshness coverage for the financial and
super-investor domains and alerts when coverage is degrading.

Coverage model
--------------
Domain coverage = distinct stored periods within the expected window divided
by expected periods.

  financial    : quarter interval from the earliest domain candidate
                 (first_financial_data_loaded_at) through the last completed
                 quarter; candidate predicate matches
                 get_stale_financial_companies step 1 exactly (status
                 INITIAL/PARTIAL/COMPLETE/CURRENT, first_financial_data_loaded_at
                 set, stock or unspecified security type)

  investors    : last SUPER_INVESTORS_INITIAL_QUARTERS quarters ending at the
                 last completed quarter

Snapshot persistence
--------------------
One row per domain per as_of date (freshness_snapshot, UNIQUE(domain, as_of));
repeat runs for the same date upsert in place so the table never grows per run.

Alerting
--------
Coverage below FRESHNESS_ALERT_THRESHOLD_PCT (config, default 95.0) logs an
ERROR-level FRESHNESS ALERT line a watcher can page on.

Design: docs/DATA_FRESHNESS_RECONCILIATION.md
"""

import logging
from collections import defaultdict
from datetime import date
from typing import Any

from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
from application.schedulers.quarter_utils import (
    as_date,
    quarter_end,
    quarter_ends_between,
    quarter_start,
    shift_quarters,
)
from config import settings
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from shared.time_utils import now_iso, now_utc

logger = logging.getLogger(__name__)

SNAPSHOT_JOB_TYPE = "freshness_snapshot"
SNAPSHOT_DEDUPE_TEMPLATE = "freshness_snapshot:{as_of}"
SNAPSHOT_RESOURCE_TYPE = "system"
SNAPSHOT_PRIORITY = 20
SNAPSHOT_MAX_ATTEMPTS = 3
SNAPSHOT_INTERVAL_HOURS = 24

FINANCIAL_DOMAIN = "financial_statements"
INVESTORS_DOMAIN = "institutional_holdings"

# Bound the per-domain missing-entity list in FRESHNESS ALERT logs.
ALERT_MISSING_LIMIT = 10


class FreshnessMonitorScheduler:
    """Daily snapshot of per-domain freshness coverage with threshold alerting."""

    def __init__(self, financial_repo: SupabaseFinancialRepository | None = None):
        self.financial_repo = financial_repo or SupabaseFinancialRepository()

    async def plan(self, today: date | None = None) -> list[dict[str, Any]]:
        """Emit a single snapshot job for the given (default: today) as_of date."""
        target = today or now_utc().date()
        return [
            {
                "job_type": SNAPSHOT_JOB_TYPE,
                "dedupe_key": SNAPSHOT_DEDUPE_TEMPLATE.format(as_of=target.isoformat()),
                "resource_type": SNAPSHOT_RESOURCE_TYPE,
                "resource_id": target.isoformat(),
                "payload": {
                    "as_of": target.isoformat(),
                    "reasons": ["routine"],
                },
                "priority": SNAPSHOT_PRIORITY,
                "max_attempts": SNAPSHOT_MAX_ATTEMPTS,
                "not_before": now_iso(),
            }
        ]

    async def snapshot(self, today: date | None = None) -> dict[str, Any]:
        """Measure both domains and persist snapshot rows for the as_of date."""
        target = today or now_utc().date()
        watermark = EarningsRefreshScheduler._last_completed_quarter_start(target)
        # Expected period per domain (design doc DATA_FRESHNESS_RECONCILIATION.md
        # §2.2): financial = the date-driven watermark (last completed quarter
        # start); investors = prior quarter end (last fully reported 13F quarter).
        expected_periods = {
            FINANCIAL_DOMAIN: watermark,
            INVESTORS_DOMAIN: quarter_end(watermark),
        }

        states: dict[str, dict[str, int | float | list]] = {}
        try:
            states[FINANCIAL_DOMAIN] = await self._measure_financials(watermark)
        except Exception:
            logger.exception("Freshness monitor: financial domain measure failed")
            states[FINANCIAL_DOMAIN] = {"covered": 0, "total": 0, "coverage": 0.0, "missing": []}
        try:
            states[INVESTORS_DOMAIN] = await self._measure_investors(watermark)
        except Exception:
            logger.exception("Freshness monitor: investor domain measure failed")
            states[INVESTORS_DOMAIN] = {"covered": 0, "total": 0, "coverage": 0.0, "missing": []}

        for domain in (FINANCIAL_DOMAIN, INVESTORS_DOMAIN):
            await self._append(domain, target, expected_periods[domain], states[domain])

        alert_threshold = getattr(settings, "FRESHNESS_ALERT_THRESHOLD_PCT", 95.0)
        for domain in (FINANCIAL_DOMAIN, INVESTORS_DOMAIN):
            state = states[domain]
            if state["coverage"] < alert_threshold:
                missing_ids = [str(m) for m in state.get("missing", [])][:ALERT_MISSING_LIMIT]
                missing_repr = ", ".join(missing_ids) if missing_ids else "none"
                logger.error(
                    "FRESHNESS ALERT: %s coverage %.1f%% below threshold %.1f%% "
                    "(covered %d/%d, expected_period %s, missing %s)",
                    domain,
                    state["coverage"],
                    alert_threshold,
                    state["covered"],
                    state["total"],
                    expected_periods[domain].isoformat(),
                    missing_repr,
                )
        return {"as_of": target.isoformat(), "domains": states}

    async def _measure_financials(
        self, watermark: date
    ) -> dict[str, int | float | list]:
        candidates = await self.financial_repo.get_financial_candidates()
        if not candidates:
            return {"covered": 0, "total": 0, "coverage": 100.0, "missing": []}

        loads: list[date] = []
        for c in candidates:
            ld = as_date(c.get("first_financial_data_loaded_at"))
            if ld is not None:
                loads.append(ld)
        if not loads:
            return {"covered": 0, "total": 0, "coverage": 100.0, "missing": []}

        window_start = quarter_start(min(loads))
        expected = quarter_ends_between(window_start, watermark)
        latest = quarter_end(watermark)

        rows = await self.financial_repo.get_financial_periods_in_range(
            window_start, watermark
        )
        present: set[date] = set()
        present_by_company: dict[int, set[date]] = defaultdict(set)
        for row in rows:
            pid = as_date(row.get("period_end_date"))
            cid = row.get("company_id")
            if pid is not None:
                present.add(pid)
                if cid is not None:
                    present_by_company[int(cid)].add(pid)
        state = self._coverage(len(present & expected), len(expected))
        # Bounded alert detail: entities without a row for the latest expected
        # period-end (income statements through the last completed quarter).
        state["missing"] = [
            int(c["company_id"])
            for c in candidates
            if c.get("company_id") is not None
            and latest not in present_by_company.get(int(c["company_id"]), set())
        ]
        return state

    async def _measure_investors(
        self, watermark: date
    ) -> dict[str, int | float | list]:
        tracked = await self.financial_repo.get_tracked_investors()
        if not tracked:
            return {"covered": 0, "total": 0, "coverage": 100.0, "missing": []}

        initial_quarters = getattr(settings, "SUPER_INVESTORS_INITIAL_QUARTERS", 20)
        window_start = shift_quarters(watermark, -(initial_quarters - 1))
        expected = quarter_ends_between(window_start, watermark)
        latest = quarter_end(watermark)

        rows = await self.financial_repo.get_investor_periods_in_range(
            window_start, watermark
        )
        present: set[date] = set()
        present_by_investor: dict[int, set[date]] = defaultdict(set)
        for row in rows:
            qe = as_date(row.get("quarter_end_date"))
            iid = row.get("investor_id")
            if qe is not None:
                present.add(qe)
                if iid is not None:
                    present_by_investor[int(iid)].add(qe)
        state = self._coverage(len(present & expected), len(expected))
        # Bounded alert detail: tracked investors without a holding row for the
        # prior quarter end (latest fully reported 13F quarter).
        state["missing"] = [
            int(i["investor_id"])
            for i in tracked
            if i.get("investor_id") is not None
            and latest not in present_by_investor.get(int(i["investor_id"]), set())
        ]
        return state

    @staticmethod
    def _coverage(covered: int, total: int) -> dict[str, int | float]:
        """Coverage over a window; an empty window counts as fully fresh."""
        if total <= 0:
            return {"covered": covered, "total": total, "coverage": 100.0}
        return {
            "covered": covered,
            "total": total,
            "coverage": round(100.0 * covered / total, 3),
        }

    async def _append(
        self,
        domain: str,
        as_of: date,
        expected_period: date,
        state: dict[str, int | float | list],
    ) -> None:
        row = {
            "domain": domain,
            "total": state["total"],
            "covered": state["covered"],
            "pct": state["coverage"],
            "as_of": as_of.isoformat(),
            "expected_period": expected_period.isoformat(),
        }
        await self.financial_repo.append_freshness_snapshot(row)
