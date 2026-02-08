# application/services/recompute_guard.py
"""
Recompute Guard for Valuations (Rule #1)

This module provides a single decision point to determine whether a Rule #1
valuation should be recomputed based on data freshness.

It compares:
- last valuation timestamp (intrinsic_value_analysis.last_updated OR latest valuation_runs)
vs
- latest dependency timestamp across all inputs that can affect Rule #1:
  * company_summary.snapshot_date            (trailing EPS)
  * earnings_forecast.report_date            (EPS growth estimate)
  * earnings.updated_at                      (EPS history for CAGR)
  * income_statements.updated_at             (revenue/EPS for fallbacks)
  * statistics.updated_at                    (diluted shares drift)
  * splits.report_date                       (EPS scaling, structural)
  * industry_multiples.calculation_date      (future PE guardrails & growth proxy)
  * valuation_method_defaults.updated_at     (global assumptions)
  * company_valuation_overrides.updated_at   (company-specific assumptions)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


@dataclass
class RecomputeDecision:
    should_recompute: bool
    last_valuation_at: Optional[datetime]
    latest_dependency_at: Optional[datetime]
    reason: str  # "no_prior_valuation" | "no_dependencies" | "dependencies_newer" | "up_to_date"


class RecomputeGuard:
    """
    Central decision helper used by:
      - WatchlistService slow-path ingestion hook
      - EarningsRefreshScheduler and MarketDataRefreshScheduler hooks
      - /valuations/{symbol}/rule1 API (cached vs recompute)
    """

    def __init__(self, valuation_repo: "ValuationRepository"):
        """
        Args:
            valuation_repo: Repository exposing:
              - get_last_valuation_ts(company_id) -> Optional[datetime]
              - get_latest_dependency_ts(company_id) -> Optional[datetime]
        """
        self.repo = valuation_repo

    async def should_recompute_rule1(self, company_id: int) -> RecomputeDecision:
        """
        Returns a RecomputeDecision with a conservative, deterministic policy:
          - If NO prior valuation exists      -> recompute
          - If NO dependencies timestamps     -> recompute (first computation scenario)
          - If latest dependency > last value -> recompute
          - Else                              -> cached is up to date

        Notes:
            * This guard does NOT lock. Callers can choose to apply short-lived
              distributed locks (e.g., scheduler_locks) if they need strict serialization.
        """
        last_val_ts = await self.repo.get_last_valuation_ts(company_id)
        latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id)

        # Case 1: Never computed before
        if last_val_ts is None:
            logger.debug("[RECOMPUTE][%s] No prior valuation -> recompute", company_id)
            return RecomputeDecision(
                should_recompute=True,
                last_valuation_at=None,
                latest_dependency_at=latest_dep_ts,
                reason="no_prior_valuation",
            )

        # Case 2: No dependency information available (first-time compute path)
        if latest_dep_ts is None:
            logger.debug("[RECOMPUTE][%s] No dependency timestamps -> recompute", company_id)
            return RecomputeDecision(
                should_recompute=True,
                last_valuation_at=last_val_ts,
                latest_dependency_at=None,
                reason="no_dependencies",
            )

        # Case 3: Dependencies newer than last valuation
        if latest_dep_ts > last_val_ts:
            logger.debug(
                "[RECOMPUTE][%s] Dependencies newer (dep=%s > last=%s) -> recompute",
                company_id, latest_dep_ts, last_val_ts
            )
            return RecomputeDecision(
                should_recompute=True,
                last_valuation_at=last_val_ts,
                latest_dependency_at=latest_dep_ts,
                reason="dependencies_newer",
            )

        # Case 4: Up to date
        logger.debug(
            "[RECOMPUTE][%s] Up to date (dep=%s <= last=%s) -> use cached",
            company_id, latest_dep_ts, last_val_ts
        )
        return RecomputeDecision(
            should_recompute=False,
            last_valuation_at=last_val_ts,
            latest_dependency_at=latest_dep_ts,
            reason="up_to_date",
        )

    # Convenience wrapper used by API/schedulers to decide cached vs recompute behavior
    async def cached_or_recompute(
        self,
        company_id: int,
        force: bool = False,
    ) -> RecomputeDecision:
        """
        If 'force' is True, always recompute (callers use this after slow-path ingestion).
        Otherwise, apply standard freshness logic.
        """
        if force:
            last_val_ts = await self.repo.get_last_valuation_ts(company_id)
            latest_dep_ts = await self.repo.get_latest_dependency_ts(company_id)
            logger.debug("[RECOMPUTE][%s] Forced recompute requested by caller", company_id)
            return RecomputeDecision(
                should_recompute=True,
                last_valuation_at=last_val_ts,
                latest_dependency_at=latest_dep_ts,
                reason="forced",
            )

        return await self.should_recompute_rule1(company_id)