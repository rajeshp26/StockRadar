"""
Recompute Guard for Valuations (Rule #1 + DDM + DCF)

Single decision point to determine whether a valuation should be recomputed
based on data freshness.

Design rule:
- RecomputeGuard is the ONLY freshness gate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class RecomputeDecision:
    should_recompute: bool
    last_valuation_at: Optional[datetime]
    latest_dependency_at: Optional[datetime]
    reason: str  # "no_prior_valuation" | "no_dependencies" | "dependencies_newer" | "up_to_date" | "forced"


class RecomputeGuard:
    """
    Central decision helper used by:
      - schedulers
      - API endpoints (cached vs recompute)

    Repository contract:
      - get_last_valuation_ts(company_id, method) -> Optional[datetime]
      - get_latest_dependency_ts(company_id, method) -> Optional[datetime]
    """

    def __init__(self, valuation_repo: "ValuationRepository"):
        self.repo = valuation_repo

    async def should_recompute(self, company_id: int, method: str = "rule1") -> RecomputeDecision:
        last_val_ts = await self.repo.get_last_valuation_ts(company_id, method=method)
        latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id, method=method)

        if last_val_ts is None:
            logger.debug("[RECOMPUTE][%s][%s] No prior valuation -> recompute", company_id, method)
            return RecomputeDecision(True, None, latest_dep_ts, "no_prior_valuation")

        if latest_dep_ts is None:
            logger.debug("[RECOMPUTE][%s][%s] No dependency timestamps -> recompute", company_id, method)
            return RecomputeDecision(True, last_val_ts, None, "no_dependencies")

        if latest_dep_ts > last_val_ts:
            logger.debug("[RECOMPUTE][%s][%s] Dependencies newer -> recompute", company_id, method)
            return RecomputeDecision(True, last_val_ts, latest_dep_ts, "dependencies_newer")

        logger.debug("[RECOMPUTE][%s][%s] Up to date -> cached", company_id, method)
        return RecomputeDecision(False, last_val_ts, latest_dep_ts, "up_to_date")

    async def cached_or_recompute(self, company_id: int, force: bool = False, method: str = "rule1") -> RecomputeDecision:
        if force:
            last_val_ts = await self.repo.get_last_valuation_ts(company_id, method=method)
            latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id, method=method)
            logger.debug("[RECOMPUTE][%s][%s] Forced recompute requested", company_id, method)
            return RecomputeDecision(True, last_val_ts, latest_dep_ts, "forced")

        return await self.should_recompute(company_id=company_id, method=method)

    async def should_recompute_rule1(self, company_id: int) -> RecomputeDecision:
        return await self.should_recompute(company_id=company_id, method="rule1")