# backend/application/services/valuation_service.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from application.services.ai_service import generate_overview_summary
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

    async def get_rule1_cached(self, symbol: str) -> Optional[Rule1Response]:
        """Return last Rule #1 result instantly. None if never computed."""
        return await self.rule1.get_cached(symbol)

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

    async def get_ddm_cached(
        self, symbol: str, variant: str = "gordon"
    ) -> Optional[DdmResponse]:
        """Return last DDM result instantly. None if never computed."""
        return await self.ddm.get_cached(symbol, variant=variant)

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

    async def get_dcf_cached(self, symbol: str) -> Optional[DcfResponse]:
        """Return last DCF result instantly. None if never computed."""
        return await self.dcf.get_cached(symbol)

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

    async def get_owner_earnings_cached(
        self, symbol: str
    ) -> Optional[OwnerEarningsResponse]:
        """Return last Owner Earnings result instantly. None if never computed."""
        return await self.owner_earnings.get_cached(symbol)

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

    async def get_residual_income_cached(
        self, symbol: str
    ) -> Optional[ResidualIncomeResponse]:
        """Return last Residual Income result instantly. None if never computed."""
        return await self.residual_income.get_cached(symbol)

    async def get_valuation_overview(self, symbol: str) -> dict:
        """
        Reads the last cached snapshot for all 5 valuation methods and
        generates a cross-method AI recommendation.
 
        Each method entry contains:
          - status:        "computed" | "not_computed"
          - intrinsicValue: the primary per-share value (None if not computed)
          - upsideDownside: fraction vs current price (None if not computed)
          - score:         suitability score 0-100 (None if not computed)
          - category:      "Good" | "Caution" | "Poor" (None if not computed)
          - lastComputedAt: ISO timestamp (None if not computed)
 
        The AI recommendation is generated from whichever methods have data.
        If no methods have been computed yet, recommendation is None.
        """
        import asyncio
 
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
        sector     = ctx.get("sector")
 
        # ── Read all 5 snapshots in parallel ──────────────────────────────────
        snaps = await self.repo.get_last_output_snapshots(
            company_id, ["rule1", "dcf", "ddm_gordon", "owner_earnings", "residual_income"]
        )
        rule1_snap = snaps.get("rule1")
        dcf_snap = snaps.get("dcf")
        ddm_gordon_snap = snaps.get("ddm_gordon")
        oe_snap = snaps.get("owner_earnings")
        ri_snap = snaps.get("residual_income")
 
        current_price = await self.repo.get_current_market_price(company_id)
 
        def _extract(snap, iv_field: str) -> dict:
            if not snap:
                return {"status": "not_computed"}
            val = snap.get("valuation") or {}
            app = snap.get("applicability") or {}
            dq  = snap.get("dataQuality") or {}
            iv  = val.get(iv_field)
            iv_f = float(iv) if iv is not None else None
            upside = None
            if (iv_f and iv_f > 0
                    and current_price is not None and float(current_price) > 0):
                upside = (iv_f - float(current_price)) / float(current_price)
            last_computed = (
                (dq.get("freshnessDays") or {}).get("lastComputedAt")
                or snap.get("lastComputedAt")
            )
            return {
                "status":         "computed",
                "intrinsicValue": iv_f,
                "upsideDownside": upside,
                "score":          app.get("score"),
                "category":       app.get("category"),
                "lastComputedAt": last_computed,
                "currency":       currency,
            }
 
        methods = {
            "rule1":          _extract(rule1_snap,      "stickerPrice"),
            "dcf":            _extract(dcf_snap,        "intrinsicValuePerShare"),
            "ddm_gordon":     _extract(ddm_gordon_snap, "intrinsicValue"),
            "owner_earnings": _extract(oe_snap,         "intrinsicValuePerShare"),
            "residual_income": _extract(ri_snap,        "intrinsicValuePerShare"),
        }
 
        # ── AI cross-method recommendation ─────────────────────────────────────
        # Only generate if at least one method has been computed.
        computed_methods = {k: v for k, v in methods.items() if v["status"] == "computed"}
        recommendation = None
        if computed_methods:
            try:
                from application.services.ai_service import generate_overview_summary
                recommendation = await generate_overview_summary(
                    symbol=symbol,
                    sector=sector,
                    currency=currency,
                    current_price=current_price,
                    methods=computed_methods,
                )
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning(
                    "generate_overview_summary failed for %s: %s", symbol, exc
                )
 
        return {
            "symbol":          symbol.upper(),
            "currentPrice":    current_price,
            "currency":        currency,
            "methods":         methods,
            "recommendation":  recommendation,
        }
 