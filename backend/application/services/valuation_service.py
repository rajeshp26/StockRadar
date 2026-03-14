# backend/application/services/valuation_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from application.services.ddm_service import DdmService
from application.services.dcf_service import DcfService
from application.services.owner_earnings_service import OwnerEarningsService
from application.services.residual_income_service import ResidualIncomeService
from application.services.rule1_service import Rule1Service
from application.services.recompute_guard import RecomputeGuard

from domain.models.valuation_rule1 import (
    Rule1RequestOverrides,
    Rule1Response,
)
from domain.models.valuation_ddm import DdmRequestOverrides, DdmResponse
from domain.models.valuation_dcf import DcfRequestOverrides, DcfResponse
from domain.models.valuation_owner_earnings import (
    OwnerEarningsRequestOverrides,
    OwnerEarningsResponse,
)
from domain.models.valuation_residual_income import (
    ResidualIncomeRequestOverrides,
    ResidualIncomeResponse,
)
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class ValuationService:
    """
    Thin orchestration layer — one public method per valuation model.

    DESIGN RULES:
    - ValuationService MUST NOT contain computation logic.
      All logic lives in the dedicated service class for each method.
    - ValuationService MUST NOT query Supabase directly.
      Repository owns all DB access.
    - Each public method is a one-line delegate. This keeps the API surface
      stable while allowing each method's service to evolve independently.

    Method → Service mapping:
      Rule #1     → Rule1Service          (rule1_service.py)
      DDM         → DdmService            (ddm_service.py)
      DCF         → DcfService            (dcf_service.py)
      Owner Earn. → OwnerEarningsService  (owner_earnings_service.py)
      Residual In.→ ResidualIncomeService (residual_income_service.py)
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo            = repo
        self.guard           = guard
        self.rule1           = Rule1Service(repo=repo, guard=guard)
        self.ddm             = DdmService(repo=repo, guard=guard)
        self.dcf             = DcfService(repo=repo, guard=guard)
        self.owner_earnings  = OwnerEarningsService(repo=repo, guard=guard)
        self.residual_income = ResidualIncomeService(repo=repo, guard=guard)

    # ── Rule #1 ───────────────────────────────────────────────────────────────

    async def compute_rule1_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[Rule1RequestOverrides] = None,
        force:     bool = False,
    ) -> Rule1Response:
        return await self.rule1.compute_rule1_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    async def compute_rule1_with_diagnostics(
        self,
        symbol:                 str,
        user_id:                Optional[int],
        overrides:              Optional[Rule1RequestOverrides] = None,
        dependency_fingerprint: Optional[str] = None,
    ) -> Rule1Response:
        """
        Thin wrapper kept for backward compatibility.
        Called directly by tests/backend/test_rule1_service.py which
        instantiates ValuationService. New code should instantiate
        Rule1Service directly and call compute_rule1_with_diagnostics on it.
        """
        return await self.rule1.compute_rule1_with_diagnostics(
            symbol=symbol,
            user_id=user_id,
            overrides=overrides,
            dependency_fingerprint=dependency_fingerprint,
        )

    # ── DDM ───────────────────────────────────────────────────────────────────

    async def compute_ddm_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        variant:   str,
        overrides: Optional[DdmRequestOverrides] = None,
        force:     bool = False,
    ) -> DdmResponse:
        return await self.ddm.compute_ddm_if_stale(
            symbol=symbol, user_id=user_id, variant=variant,
            overrides=overrides, force=force,
        )

    # ── DCF ───────────────────────────────────────────────────────────────────

    async def compute_dcf_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[DcfRequestOverrides] = None,
        force:     bool = False,
    ) -> DcfResponse:
        return await self.dcf.compute_dcf_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    # ── Owner Earnings ────────────────────────────────────────────────────────

    async def compute_owner_earnings_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[OwnerEarningsRequestOverrides] = None,
        force:     bool = False,
    ) -> OwnerEarningsResponse:
        return await self.owner_earnings.compute_owner_earnings_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    # ── Residual Income ───────────────────────────────────────────────────────

    async def compute_residual_income_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[ResidualIncomeRequestOverrides] = None,
        force:     bool = False,
    ) -> ResidualIncomeResponse:
        return await self.residual_income.compute_residual_income_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )