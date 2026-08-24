# backend/application/services/valuation_service.py
from __future__ import annotations

import logging
from typing import Any

from application.services.dcf_service import DcfService
from application.services.ddm_service import DdmService
from application.services.owner_earnings_service import OwnerEarningsService
from application.services.recompute_guard import RecomputeGuard
from application.services.residual_income_service import ResidualIncomeService
from application.services.rule1_service import Rule1Service
from domain.models.valuation_dcf import DcfRequestOverrides, DcfResponse
from domain.models.valuation_ddm import DdmRequestOverrides, DdmResponse
from domain.models.valuation_owner_earnings import (
    OwnerEarningsRequestOverrides,
    OwnerEarningsResponse,
)
from domain.models.valuation_residual_income import (
    ResidualIncomeRequestOverrides,
    ResidualIncomeResponse,
)
from domain.models.valuation_rule1 import (
    Rule1RequestOverrides,
    Rule1Response,
)
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import safe_float
from shared.time_utils import now_utc, parse_db_timestamp

logger = logging.getLogger(__name__)

_METHODS = ["rule1", "dcf", "ddm_gordon", "owner_earnings", "residual_income"]
_METHOD_IV_FIELD = {
    "rule1": "stickerPrice",
    "dcf": "intrinsicValuePerShare",
    "ddm_gordon": "intrinsicValue",
    "owner_earnings": "intrinsicValuePerShare",
    "residual_income": "intrinsicValuePerShare",
}


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
        user_id:   int | None,
        overrides: Rule1RequestOverrides | None = None,
        force:     bool = False,
    ) -> Rule1Response:
        return await self.rule1.compute_rule1_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    async def get_rule1_cached(self, symbol: str) -> Rule1Response | None:
        """Return last Rule #1 result instantly. None if never computed."""
        return await self.rule1.get_cached(symbol)

    async def compute_rule1_with_diagnostics(
        self,
        symbol:                 str,
        user_id:                int | None,
        overrides:              Rule1RequestOverrides | None = None,
        dependency_fingerprint: str | None = None,
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
        user_id:   int | None,
        variant:   str,
        overrides: DdmRequestOverrides | None = None,
        force:     bool = False,
    ) -> DdmResponse:
        return await self.ddm.compute_ddm_if_stale(
            symbol=symbol, user_id=user_id, variant=variant,
            overrides=overrides, force=force,
        )

    async def get_ddm_cached(
        self, symbol: str, variant: str = "gordon"
    ) -> DdmResponse | None:
        """Return last DDM result instantly. None if never computed."""
        return await self.ddm.get_cached(symbol, variant=variant)

    # ── DCF ───────────────────────────────────────────────────────────────────

    async def compute_dcf_if_stale(
        self,
        symbol:    str,
        user_id:   int | None,
        overrides: DcfRequestOverrides | None = None,
        force:     bool = False,
    ) -> DcfResponse:
        return await self.dcf.compute_dcf_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    async def get_dcf_cached(self, symbol: str) -> DcfResponse | None:
        """Return last DCF result instantly. None if never computed."""
        return await self.dcf.get_cached(symbol)

    # ── Owner Earnings ────────────────────────────────────────────────────────

    async def compute_owner_earnings_if_stale(
        self,
        symbol:    str,
        user_id:   int | None,
        overrides: OwnerEarningsRequestOverrides | None = None,
        force:     bool = False,
    ) -> OwnerEarningsResponse:
        return await self.owner_earnings.compute_owner_earnings_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    async def get_owner_earnings_cached(
        self, symbol: str
    ) -> OwnerEarningsResponse | None:
        """Return last Owner Earnings result instantly. None if never computed."""
        return await self.owner_earnings.get_cached(symbol)

    # ── Residual Income ───────────────────────────────────────────────────────

    async def compute_residual_income_if_stale(
        self,
        symbol:    str,
        user_id:   int | None,
        overrides: ResidualIncomeRequestOverrides | None = None,
        force:     bool = False,
    ) -> ResidualIncomeResponse:
        return await self.residual_income.compute_residual_income_if_stale(
            symbol=symbol, user_id=user_id, overrides=overrides, force=force
        )

    async def get_residual_income_cached(
        self, symbol: str
    ) -> ResidualIncomeResponse | None:
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

    # ── Phase 2: canonical read-model summary (§6.1-B/C/E) ────────────────────

    async def get_valuation_summary(self, symbol: str) -> dict:
        """
        Cross-method valuation summary straight from the read model
        (v_valuation_latest_runs). One query; no compute, no LLM, no quote fetch.

        Contract (§6.1-E): status ∈ {available, stale, not_computed,
        not_applicable, failed_without_previous_result} + reasonCode +
        computedAt + inputAsOf + modelVersion + refresh + nullable numerics.
        A broken snapshot for one method never fails the whole response — that
        method becomes failed_without_previous_result.
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"
        sector = ctx.get("sector")

        rows = await self.repo.get_valuation_summary_rows(company_id)
        by_method = {r.get("method"): r for r in rows}

        methods = {}
        for method in _METHODS:
            try:
                methods[method] = self._build_method_summary(
                    method, by_method.get(method), currency
                )
            except Exception as exc:
                logger.warning("valuation summary section failed for %s: %s", method, exc)
                methods[method] = {
                    "method": method,
                    "status": "failed_without_previous_result",
                    "reasonCode": "SECTION_BUILD_ERROR",
                    "intrinsicValue": None,
                    "referencePrice": None,
                    "referencePriceAsOf": None,
                    "upsideDownside": None,
                    "computedAt": None,
                    "inputAsOf": None,
                    "modelVersion": None,
                    "freshnessDays": None,
                    "score": None,
                    "category": None,
                    "currency": currency,
                    "refresh": None,
                }

        return {
            "symbol": symbol.upper(),
            "currency": currency,
            "sector": sector,
            "generatedAt": now_utc().isoformat(),
            "methods": methods,
            "recommendation": self._recommendation_status(methods),
        }

    def _build_method_summary(
        self, method: str, row: dict[str, Any] | None, currency: str
    ) -> dict[str, Any]:
        base = {
            "method": method,
            "intrinsicValue": None,
            "referencePrice": None,
            "referencePriceAsOf": None,
            "upsideDownside": None,
            "computedAt": None,
            "inputAsOf": None,
            "modelVersion": None,
            "freshnessDays": None,
            "score": None,
            "category": None,
            "currency": currency,
            "refresh": None,
        }
        if not row:
            base["status"] = "not_computed"
            base["reasonCode"] = None
            return base

        snap = row.get("output_snapshot") or {}
        if not isinstance(snap, dict):
            base["status"] = "failed_without_previous_result"
            base["reasonCode"] = "MISSING_SNAPSHOT"
            return base

        val = snap.get("valuation") or {}
        app = snap.get("applicability") or {}
        dq = snap.get("dataQuality") or {}
        iv_field = _METHOD_IV_FIELD.get(method, "intrinsicValuePerShare")
        iv = safe_float(val.get(iv_field))

        computed_at = (
            (dq.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
            or row.get("run_at")
        )
        input_as_of = self._extract_input_as_of(row.get("input_snapshot"))
        base["computedAt"] = computed_at
        base["inputAsOf"] = input_as_of
        base["modelVersion"] = row.get("data_version_tag")
        base["freshnessDays"] = self._freshness_days(computed_at)

        score, category, hard_fail = self._extract_applicability(app)
        base["score"] = score
        base["category"] = category

        if iv is None or iv <= 0:
            if method == "rule1" and safe_float(val.get("eps0")) is not None and safe_float(val.get("eps0")) <= 0:
                base["status"] = "not_applicable"
                base["reasonCode"] = "NEGATIVE_EPS"
            elif hard_fail:
                base["status"] = "not_applicable"
                base["reasonCode"] = "NOT_MEANINGFUL"
            else:
                base["status"] = "not_applicable"
                base["reasonCode"] = "NO_MEANINGFUL_VALUE"
            return base

        base["status"] = "available"
        base["reasonCode"] = None
        base["intrinsicValue"] = iv

        ref = safe_float(val.get("currentPrice"))
        if ref is not None and ref > 0:
            base["referencePrice"] = ref
            base["referencePriceAsOf"] = computed_at
            base["upsideDownside"] = (iv - ref) / ref
        return base

    @staticmethod
    def _extract_input_as_of(input_snapshot: Any) -> Any | None:
        if not isinstance(input_snapshot, dict):
            return None
        resolved = input_snapshot.get("resolved")
        if isinstance(resolved, dict):
            return resolved.get("resolved_at")
        return None

    @staticmethod
    def _freshness_days(computed_at: Any) -> int | None:
        if not computed_at:
            return None
        try:
            dt = parse_db_timestamp(str(computed_at))
            days = (now_utc() - dt).days
            return max(days, 0)
        except Exception:
            return None

    @staticmethod
    def _extract_applicability(app: dict[str, Any]) -> tuple:
        score, category, hard_fail = None, None, False
        for flag in app.get("flags") or []:
            evidence = flag.get("evidence") or {}
            if not isinstance(evidence, dict):
                continue
            if evidence.get("score0to100") is not None:
                score = evidence.get("score0to100")
            if evidence.get("category"):
                category = evidence.get("category")
            if evidence.get("hardFail") is True:
                hard_fail = True
        return score, category, hard_fail

    @staticmethod
    def _recommendation_status(methods: dict[str, Any]) -> dict[str, Any]:
        from config import settings
        configured = bool(settings.OPEN_ROUTER_KEY)
        base = {
            "status": "pending" if configured else "disabled",
            "reasonCode": None if configured else "PROVIDER_NOT_CONFIGURED",
            "text": None,
            "generatedAt": None,
            "sourceSnapshotVersion": None,
            "provider": None,
            "model": None,
        }
        if not configured:
            base["text"] = ValuationService._deterministic_recommendation(methods)
            base["provider"] = "deterministic"
        return base

    @staticmethod
    def _deterministic_recommendation(methods: dict[str, Any]) -> str:
        available = [
            m for m in methods.values()
            if m.get("status") == "available" and m.get("upsideDownside") is not None
        ]
        if not available:
            return "No computed valuations available yet."

        upsides = [m["upsideDownside"] for m in available]
        avg = sum(upsides) / len(upsides)
        if avg > 0.02:
            stance = "Undervalued"
        elif avg < -0.02:
            stance = "Overvalued"
        else:
            stance = "Fairly valued"
        return (
            f"{stance} — {len(available)} of {len(methods)} methods computed "
            f"(average upside {avg:+.1%})."
        )
