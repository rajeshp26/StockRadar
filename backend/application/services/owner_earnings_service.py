# application/services/owner_earnings_service.py
"""
Owner Earnings Service — Three-Gate Caching (Phase 2d)

BUG FIX included: the original _compute_and_persist had a premature early-abort
insert_valuation_run block that referenced undefined `all_flags` and `oe_score`.
That dead-code block is removed; _build_empty_response handles early aborts correctly.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from application.services.ai_service import generate_suitability_summary
from application.services.owner_earnings_suitability import evaluate_owner_earnings_suitability
from application.services.recompute_guard import RecomputeGuard
from domain.models.valuation_owner_earnings import (
    OeSensitivityGrid,
    OwnerEarningsRequestOverrides,
    OwnerEarningsResponse,
    OwnerEarningsValuation,
)
from domain.models.valuation_rule1 import Applicability, DataQuality, DiagnosticFlag
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _pct_or_frac_to_frac(x: float) -> float:
    return x / 100.0 if x > 1.0 else x


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        return f if f == f else None
    except Exception:
        return None


def _compute_oe(
    net_income: Optional[float],
    da: Optional[float],
    capex_raw: Optional[float],
    wc_change: Optional[float],
    maintenance_capex_ratio: float,
    include_wc: bool,
) -> Optional[float]:
    if net_income is None:
        return None
    da_val = da if da is not None else 0.0
    capex_adj = 0.0
    if capex_raw is not None:
        maint     = abs(capex_raw) * maintenance_capex_ratio
        capex_adj = -maint
    oe = net_income + da_val + capex_adj
    if include_wc and wc_change is not None:
        oe -= wc_change
    return oe


def _build_fingerprint(dep_values: Dict[str, Any]) -> str:
    raw = json.dumps(dep_values, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]


# ── Service ────────────────────────────────────────────────────────────────────

class OwnerEarningsService:
    """Owner Earnings (Buffett Method) valuation service with three-gate caching."""

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo  = repo
        self.guard = guard

    # ── Public entry point ─────────────────────────────────────────────────────

    async def compute_owner_earnings_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[OwnerEarningsRequestOverrides] = None,
        force:     bool = False,
    ) -> OwnerEarningsResponse:
        overrides  = overrides or OwnerEarningsRequestOverrides()
        method     = "owner_earnings"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
        sector     = ctx.get("sector")

        # ── Force: bypass all gates ────────────────────────────────────────
        if force:
            dep_values  = await self.repo.get_oe_dependency_values(company_id)
            fingerprint = _build_fingerprint(dep_values)
            logger.info("[VALUATION][OE] forced recompute: %s", symbol)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 1: Timestamp ──────────────────────────────────────────────
        gate1 = await self.guard.should_recompute(company_id, method=method)

        if not gate1.should_recompute:
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info(
            "[VALUATION][OE] Gate 1 fired: %s reason=%s dep_ts=%s last_ts=%s",
            symbol, gate1.reason, gate1.latest_dependency_at, gate1.last_valuation_at,
        )

        # ── No prior valuation ─────────────────────────────────────────────
        if gate1.reason == "no_prior_valuation":
            dep_values  = await self.repo.get_oe_dependency_values(company_id)
            fingerprint = _build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Override present: bypass Gates 2 & 3 ──────────────────────────
        if self._has_overrides(overrides):
            dep_values  = await self.repo.get_oe_dependency_values(company_id)
            fingerprint = _build_fingerprint(dep_values)
            logger.info("[VALUATION][OE] Override present → bypass Gates 2&3: %s", symbol)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 2: Fingerprint ────────────────────────────────────────────
        dep_values  = await self.repo.get_oe_dependency_values(company_id)
        fingerprint = _build_fingerprint(dep_values)

        gate2 = await self.guard.check_fingerprint(company_id, method, fingerprint)
        if not gate2.should_recompute:
            logger.info("[VALUATION][OE] Gate 2 → cached (fingerprint_match): %s", symbol)
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info("[VALUATION][OE] Gate 2 fired: %s reason=%s", symbol, gate2.reason)

        # ── Gate 3: Materiality ────────────────────────────────────────────
        last_input_snap = await self.repo.get_last_input_snapshot(company_id, method)
        stored_resolved = (last_input_snap or {}).get("resolved")

        if stored_resolved:
            defaults         = await self.repo.get_method_params(company_id, method=method)
            current_resolved = await self.resolve_current_inputs(company_id, overrides, defaults)
            is_material, gate3_reason, gate3_details = self.guard.is_material_change(
                current_resolved, stored_resolved, method
            )
            if not is_material:
                logger.info(
                    "[VALUATION][OE] Gate 3 → cached (immaterial): %s reason=%s",
                    symbol, gate3_reason,
                )
                await self.guard.record_immaterial_change(company_id, method, fingerprint)
                return await self._serve_cached(
                    symbol, company_id, currency, sector, user_id, method, overrides
                )
            logger.info(
                "[VALUATION][OE] Gate 3 → recompute (material): %s reason=%s",
                symbol, gate3_reason,
            )
        else:
            logger.debug("[VALUATION][OE] Gate 3 skipped: no stored resolved yet: %s", symbol)

        return await self._compute_and_persist(
            symbol, company_id, currency, sector, user_id, overrides,
            dependency_fingerprint=fingerprint,
        )

    async def get_cached(self, symbol: str) -> Optional[OwnerEarningsResponse]:
        """
        Pure cache read — no gate logic, no recompute, no DB writes.
        Returns None if no prior Owner Earnings valuation exists.
        Used by GET /valuations/{symbol}/owner_earnings for instant tab loads.
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            return None
        company_id = int(ctx["company_id"])
 
        snap = await self.repo.get_last_output_snapshot(
            company_id=company_id, method="owner_earnings"
        )
        if not snap:
            return None
 
        valuation_payload     = snap.get("valuation")     or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload            = snap.get("dataQuality")   or {}
        last_computed = (
            (dq_payload.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
        )
 
        # Refresh currentPrice and upside at read time
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps  = _safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside        = None
        if (current_price is not None and float(current_price) > 0
                and intrinsic_ps is not None and intrinsic_ps > 0):
            upside = (float(intrinsic_ps) - float(current_price)) / float(current_price)
        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside
 
        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "OE-NO-AUDIT", "severity": "info",
                    "message": "No prior OE valuation run found; run Recompute once.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed
 
        return OwnerEarningsResponse(
            valuation=OwnerEarningsValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )
 
    # ── Cached path ────────────────────────────────────────────────────────────

    async def _serve_cached(
        self,
        symbol:     str,
        company_id: int,
        currency:   str,
        sector:     Optional[str],
        user_id:    Optional[int],
        method:     str,
        overrides:  OwnerEarningsRequestOverrides,
    ) -> OwnerEarningsResponse:
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info("[VALUATION][OE] Cached path: snapshot missing, recomputing: %s", symbol)
            dep_values  = await self.repo.get_oe_dependency_values(company_id)
            fingerprint = _build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        valuation_payload     = snap.get("valuation")     or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload            = snap.get("dataQuality")   or {}
        last_computed = (
            (dq_payload.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
        )

        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps  = _safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside        = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps and intrinsic_ps > 0:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside

        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "OE-NO-AUDIT", "severity": "info",
                    "message": "No prior OE valuation run found; suitability scorecard not available on cached path.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return OwnerEarningsResponse(
            valuation=OwnerEarningsValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )

    # ── Gate helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _has_overrides(overrides: OwnerEarningsRequestOverrides) -> bool:
        return any([
            overrides.forecastYears            is not None,
            overrides.oeGrowthRate             is not None,
            overrides.discountRate             is not None,
            overrides.terminalGrowthRate       is not None,
            overrides.maintenanceCapexRatio    is not None,
            overrides.includeWorkingCapitalChange is not None,
            overrides.netDebt                  is not None,
            overrides.sharesOutstanding        is not None,
        ])

    async def resolve_current_inputs(
        self,
        company_id: int,
        overrides:  OwnerEarningsRequestOverrides,
        defaults:   Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Lightweight input resolution for Gate 3.
        Resolves base_oe, g_oe, discount_rate, terminal_g without computing intrinsic.
        """
        mc_ratio   = float(overrides.maintenanceCapexRatio) if overrides.maintenanceCapexRatio is not None else float(defaults.get("maintenance_capex_ratio", 1.0))
        include_wc = bool(overrides.includeWorkingCapitalChange) if overrides.includeWorkingCapitalChange is not None else bool(defaults.get("include_working_capital_change", True))

        # ── Base OE ───────────────────────────────────────────────────────
        base_oe_data = await self._resolve_base_oe(company_id, mc_ratio, include_wc)
        base_oe      = _safe_float(base_oe_data.get("value"))

        # ── OE growth rate ────────────────────────────────────────────────
        g_oe_source = "override.oeGrowthRate"
        if overrides.oeGrowthRate is not None:
            g_oe_raw = float(overrides.oeGrowthRate)
        else:
            g_oe_raw    = _safe_float(defaults.get("oe_growth_rate"))
            g_oe_source = "defaults.oe_growth_rate"

        g_oe: Optional[float] = None
        if g_oe_raw is not None:
            g_oe = _clamp(
                _pct_or_frac_to_frac(float(g_oe_raw)),
                float(defaults.get("oe_growth_floor", 0.00)),
                float(defaults.get("oe_growth_cap",   0.15)),
            )

        # ── Discount rate ─────────────────────────────────────────────────
        r_source = "override.discountRate"
        if overrides.discountRate is not None:
            r_raw = float(overrides.discountRate)
        else:
            r_raw    = _safe_float(defaults.get("discount_rate_default"))
            r_source = "defaults.discount_rate_default"

        r: Optional[float] = None
        if r_raw is not None:
            r = _clamp(
                _pct_or_frac_to_frac(float(r_raw)),
                float(defaults.get("discount_rate_floor", 0.07)),
                float(defaults.get("discount_rate_cap",   0.15)),
            )

        # ── Terminal growth ────────────────────────────────────────────────
        tg: Optional[float] = None
        if overrides.terminalGrowthRate is not None:
            tg = _pct_or_frac_to_frac(float(overrides.terminalGrowthRate))
        else:
            tg_raw = _safe_float(defaults.get("terminal_growth_default"))
            if tg_raw is not None:
                tg = _pct_or_frac_to_frac(float(tg_raw))

        # ── Net debt ──────────────────────────────────────────────────────
        net_debt: Optional[float] = None
        if overrides.netDebt is not None:
            net_debt = float(overrides.netDebt)
        else:
            bs   = await self.repo.get_balance_sheet_latest(company_id)
            debt = _safe_float(bs.get("total_debt"))               if bs else None
            cash = _safe_float(bs.get("cash_and_cash_equivalents")) if bs else None
            if debt is not None and cash is not None:
                net_debt = float(debt) - float(cash)

        # ── Shares ────────────────────────────────────────────────────────
        shares: Optional[float] = None
        if overrides.sharesOutstanding is not None:
            shares = float(overrides.sharesOutstanding)
        else:
            rows = await self.repo.get_shares_history(company_id)
            if rows:
                sh = _safe_float(rows[-1].get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares = sh
            if shares is None:
                summary = await self.repo.get_company_summary_latest(company_id)
                if summary:
                    sh = _safe_float(summary.get("shares_outstanding"))
                    if sh and sh > 0:
                        shares = sh

        n = int(overrides.forecastYears) if overrides.forecastYears is not None else int(defaults.get("forecast_years_default", 5))

        return {
            "base_oe":            round(base_oe, 2)  if base_oe is not None else None,
            "g_oe_final":         round(g_oe, 4)     if g_oe    is not None else None,
            "g_oe_source":        g_oe_source,
            "discount_rate_final": round(r, 4)        if r       is not None else None,
            "discount_rate_source": r_source,
            "terminal_g_final":   round(tg, 4)        if tg      is not None else None,
            "forecast_years":     n,
            "net_debt":           round(net_debt, 0)  if net_debt is not None else None,
            "shares":             round(shares, 0)    if shares   is not None else None,
        }

    # ── Full computation + persistence ─────────────────────────────────────────

    async def _compute_and_persist(
        self,
        symbol:                 str,
        company_id:             int,
        currency:               str,
        sector:                 Optional[str],
        user_id:                Optional[int],
        overrides:              OwnerEarningsRequestOverrides,
        dependency_fingerprint: Optional[str] = None,
    ) -> OwnerEarningsResponse:

        defaults = await self.repo.get_method_params(company_id, method="owner_earnings")
        flags:           List[DiagnosticFlag] = []
        input_decisions: Dict[str, Any]       = {"oe": {}}
        fallbacks_used                         = False

        current_price = await self.repo.get_current_market_price(company_id)

        # ── Forecast years ─────────────────────────────────────────────────
        n_default = int(defaults.get("forecast_years_default", 5))
        if overrides.forecastYears is not None:
            n = int(overrides.forecastYears)
            input_decisions["oe"]["forecastYears"] = {"source": "override.forecastYears", "value": n}
        else:
            n = n_default
            input_decisions["oe"]["forecastYears"] = {"source": "defaults.forecast_years_default", "value": n}
            fallbacks_used = True
        n = int(_clamp(float(n), 1, 20))

        # ── Maintenance capex ratio ────────────────────────────────────────
        if overrides.maintenanceCapexRatio is not None:
            mc_ratio = float(overrides.maintenanceCapexRatio)
            input_decisions["oe"]["maintenanceCapexRatio"] = {"source": "override", "value": mc_ratio}
        else:
            mc_ratio = float(defaults.get("maintenance_capex_ratio", 1.0))
            input_decisions["oe"]["maintenanceCapexRatio"] = {"source": "defaults", "value": mc_ratio}
            fallbacks_used = True

        include_wc = (
            bool(overrides.includeWorkingCapitalChange)
            if overrides.includeWorkingCapitalChange is not None
            else bool(defaults.get("include_working_capital_change", True))
        )

        # ── Base OE ────────────────────────────────────────────────────────
        base_oe_data = await self._resolve_base_oe(company_id, mc_ratio, include_wc)
        base_oe      = _safe_float(base_oe_data.get("value"))
        base_oe_fy   = base_oe_data.get("evidence", {}).get("asOfFiscalYear")
        input_decisions["oe"]["baseOe"] = base_oe_data.get("evidence")

        net_income_used = base_oe_data.get("evidence", {}).get("netIncome")
        da_used         = base_oe_data.get("evidence", {}).get("da")
        capex_used      = base_oe_data.get("evidence", {}).get("capex")
        wc_change_used  = base_oe_data.get("evidence", {}).get("wcChange")

        if base_oe is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-BASE", severity="critical",
                message="Could not resolve base Owner Earnings (Net Income unavailable).",
                evidence=base_oe_data.get("evidence"),
                recommendation="Ensure income_statements.net_income and cash_flow_statements are populated.",
            ))
        elif base_oe <= 0:
            flags.append(DiagnosticFlag(
                code="OE-NEG-BASE", severity="medium",
                message=f"Base Owner Earnings is {base_oe:,.0f} (non-positive).",
                evidence={"baseOe": base_oe},
                recommendation="Apply conservative growth and a wide discount rate.",
            ))

        # ── OE growth rate ─────────────────────────────────────────────────
        g_oe_source: str
        if overrides.oeGrowthRate is not None:
            g_oe_raw    = float(overrides.oeGrowthRate)
            g_oe_source = "override.oeGrowthRate"
        else:
            g_oe_raw    = _safe_float(defaults.get("oe_growth_rate"))
            g_oe_source = "defaults.oe_growth_rate"
            if g_oe_raw is not None:
                fallbacks_used = True

        if base_oe is None or g_oe_raw is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-GROWTH", severity="critical",
                message="Cannot build OE forecast: base OE or growth rate is missing.",
                evidence={"baseOe": base_oe, "oeGrowthRate": g_oe_raw},
                recommendation="Provide oeGrowthRate override or set oe_growth_rate in method defaults.",
            ))
            return await self._build_empty_response(
                symbol, company_id, currency, sector, n, flags, input_decisions,
                current_price, user_id=user_id,
            )

        g_oe_frac    = _pct_or_frac_to_frac(float(g_oe_raw))
        g_oe_floor   = float(defaults.get("oe_growth_floor", 0.00))
        g_oe_cap     = float(defaults.get("oe_growth_cap",   0.15))
        g_oe_clamped = _clamp(g_oe_frac, g_oe_floor, g_oe_cap)
        input_decisions["oe"]["oeGrowthRate"] = {
            "source": g_oe_source, "valueRaw": g_oe_raw,
            "valueFrac": g_oe_frac, "valueFinal": g_oe_clamped,
            "floor": g_oe_floor, "cap": g_oe_cap, "clamped": g_oe_frac != g_oe_clamped,
        }
        if g_oe_frac != g_oe_clamped:
            flags.append(DiagnosticFlag(
                code="OE-GROWTH-CLAMP", severity="info",
                message="OE growth rate was clamped to safety bounds.",
                evidence=input_decisions["oe"]["oeGrowthRate"],
            ))
        g_oe = g_oe_clamped

        forecast_oe = [float(base_oe) * ((1.0 + g_oe) ** t) for t in range(1, n + 1)]

        # ── Discount rate ──────────────────────────────────────────────────
        r_source: str
        if overrides.discountRate is not None:
            r_raw    = float(overrides.discountRate)
            r_source = "override.discountRate"
        else:
            r_raw    = _safe_float(defaults.get("discount_rate_default"))
            r_source = "defaults.discount_rate_default"
            if r_raw is not None:
                fallbacks_used = True

        if r_raw is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-RATE", severity="critical",
                message="Discount rate is missing.",
                recommendation="Provide discountRate override or set discount_rate_default in method defaults.",
            ))
            r = 0.0
        else:
            r_frac  = _pct_or_frac_to_frac(float(r_raw))
            r_floor = float(defaults.get("discount_rate_floor", 0.07))
            r_cap   = float(defaults.get("discount_rate_cap",   0.15))
            r       = _clamp(r_frac, r_floor, r_cap)
            input_decisions["oe"]["discountRate"] = {
                "source": r_source, "valueRaw": r_raw,
                "valueFrac": r_frac, "valueFinal": r,
                "floor": r_floor, "cap": r_cap, "clamped": r_frac != r,
            }
            if r_frac != r:
                flags.append(DiagnosticFlag(
                    code="OE-RATE-CLAMP", severity="info",
                    message="Discount rate was clamped to safety bounds.",
                    evidence=input_decisions["oe"]["discountRate"],
                ))

        # ── Discount OE stream ─────────────────────────────────────────────
        pv_oe:            List[float] = []
        discount_factors: List[float] = []
        total_pv_oe                   = 0.0

        if r > 0:
            for t, cf in enumerate(forecast_oe, start=1):
                df = 1.0 / ((1.0 + r) ** t)
                pv = cf * df
                discount_factors.append(float(df))
                pv_oe.append(float(pv))
                total_pv_oe += float(pv)
        else:
            pv_oe            = [0.0] * n
            discount_factors = [0.0] * n
            flags.append(DiagnosticFlag(
                code="OE-NO-DISCOUNT", severity="high",
                message="Discount rate is 0 or unavailable; cannot compute present values.",
            ))

        # ── Terminal value (perpetuity growth) ─────────────────────────────
        tv: Optional[float] = None; pv_tv: Optional[float] = None
        oe_n_plus_1:   Optional[float] = None
        terminal_g_used: Optional[float] = None
        tg                               = None
        tg_raw                           = None

        if r > 0:
            if overrides.terminalGrowthRate is not None:
                tg_raw    = float(overrides.terminalGrowthRate)
                tg_source = "override.terminalGrowthRate"
            else:
                tg_raw    = _safe_float(defaults.get("terminal_growth_default"))
                tg_source = "defaults.terminal_growth_default"
                if tg_raw is not None:
                    fallbacks_used = True

            if tg_raw is None:
                flags.append(DiagnosticFlag(
                    code="OE-NO-TERM-G", severity="critical",
                    message="Terminal growth rate (g) is missing.",
                    recommendation="Provide terminalGrowthRate override or set terminal_growth_default in method defaults.",
                ))
            else:
                tg             = _pct_or_frac_to_frac(float(tg_raw))
                terminal_g_used = tg
                if tg >= r:
                    flags.append(DiagnosticFlag(
                        code="OE-G-GE-R", severity="critical",
                        message="Terminal growth rate (g) must be less than discount rate (r).",
                        evidence={"g": tg, "r": r, "source": tg_source},
                        recommendation="Lower g or raise r.",
                    ))
                else:
                    oe_n        = float(forecast_oe[-1])
                    oe_n_plus_1 = oe_n * (1.0 + tg)
                    tv          = oe_n_plus_1 / (r - tg)
                    pv_tv       = tv / ((1.0 + r) ** n)
                input_decisions["oe"]["terminal"] = {
                    "method": "perpetuity_growth", "source": tg_source,
                    "gRaw": tg_raw, "gFinal": tg, "r": r,
                    "oeNPlus1": float(oe_n_plus_1) if oe_n_plus_1 is not None else None,
                    "valid": (tg < r if tg_raw is not None else False),
                }

        # ── Enterprise → Equity → Per-share bridge ─────────────────────────
        enterprise_value: Optional[float] = None
        if pv_tv is not None:
            enterprise_value = float(total_pv_oe) + float(pv_tv)
        else:
            enterprise_value = float(total_pv_oe) if total_pv_oe else None

        net_debt: Optional[float] = None
        net_debt_source = None
        if overrides.netDebt is not None:
            net_debt        = float(overrides.netDebt)
            net_debt_source = "override.netDebt"
        else:
            bs   = await self.repo.get_balance_sheet_latest(company_id)
            debt = _safe_float(bs.get("total_debt"))               if bs else None
            cash = _safe_float(bs.get("cash_and_cash_equivalents")) if bs else None
            if debt is not None and cash is not None:
                net_debt        = float(debt) - float(cash)
                net_debt_source = "balance_sheets.total_debt - cash_and_cash_equivalents"
                fallbacks_used  = True
        input_decisions["oe"]["netDebt"] = {"source": net_debt_source, "value": net_debt}

        equity_value: Optional[float] = None
        if enterprise_value is not None and net_debt is not None:
            equity_value = float(enterprise_value) - float(net_debt)

        shares: Optional[float] = None
        shares_source = None
        if overrides.sharesOutstanding is not None:
            shares        = float(overrides.sharesOutstanding)
            shares_source = "override.sharesOutstanding"
        else:
            rows = await self.repo.get_shares_history(company_id)
            if rows:
                sh = _safe_float(rows[-1].get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares        = float(sh)
                    shares_source = "income_statements.shares_outstanding_diluted(latest)"
                    fallbacks_used = True
        if shares is None:
            summary = await self.repo.get_company_summary_latest(company_id)
            if summary:
                sh = _safe_float(summary.get("shares_outstanding"))
                if sh and sh > 0:
                    shares        = float(sh)
                    shares_source = "company_summary.shares_outstanding"
                    fallbacks_used = True
        input_decisions["oe"]["sharesOutstanding"] = {"source": shares_source, "value": shares}

        intrinsic_ps: Optional[float] = None
        if equity_value is not None and shares is not None and float(shares) > 0:
            intrinsic_ps = float(equity_value) / float(shares)

        upside: Optional[float] = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps and intrinsic_ps > 0:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        # ── Sensitivity grid ───────────────────────────────────────────────
        sensitivity_grid: Optional[OeSensitivityGrid] = None
        if (r > 0 and terminal_g_used is not None and tg_raw is not None
                and intrinsic_ps is not None and equity_value is not None
                and shares is not None and float(shares) > 0):
            cfg_r = defaults.get("sensitivity_discount_rates")
            cfg_g = defaults.get("sensitivity_terminal_growth_rates")

            def _to_float_list(x):
                if not isinstance(x, list) or not x:
                    return None
                try:
                    return [float(v) for v in x]
                except Exception:
                    return None

            r_list = _to_float_list(cfg_r)
            g_list = _to_float_list(cfg_g)
            derived = False
            if r_list is None:
                derived = True
                r_list = [max(0.01, r - 0.01), r, min(0.30, r + 0.01)]
            if g_list is None:
                derived = True
                g_list = [max(0.00, terminal_g_used - 0.01), terminal_g_used,
                          min(terminal_g_used + 0.01, r - 0.001)]

            matrix: List[List[Optional[float]]] = []
            for r_s in r_list:
                row: List[Optional[float]] = []
                for g_s in g_list:
                    if g_s >= r_s:
                        row.append(None)
                        continue
                    pv_sum  = sum(float(cf) / ((1.0 + r_s) ** t) for t, cf in enumerate(forecast_oe, start=1))
                    oe_np1  = float(forecast_oe[-1]) * (1.0 + g_s)
                    tv_s    = oe_np1 / (r_s - g_s)
                    pv_tv_s = tv_s / ((1.0 + r_s) ** n)
                    ev_s    = pv_sum + pv_tv_s
                    eq_s    = ev_s - float(net_debt) if net_debt is not None else None
                    row.append(float(eq_s) / float(shares) if eq_s is not None else None)
                matrix.append(row)

            sensitivity_grid = OeSensitivityGrid(
                discountRates=[float(x) for x in r_list],
                terminalGrowthRates=[float(x) for x in g_list],
                intrinsicValuePerShareMatrix=matrix,
                currency=currency,
            )
            input_decisions["oe"]["sensitivity"] = {
                "enabled": True,
                "source": "defaults" if not derived else "derived_around_used_r_g",
            }
            if derived:
                fallbacks_used = True

        # ── Suitability + AI summary ───────────────────────────────────────
        oe_score, oe_category, oe_flags, oe_evidence = await evaluate_owner_earnings_suitability(
            repo=self.repo, company_id=company_id, sector=sector,
        )
        flags.extend(oe_flags)

        suitability_summary = await generate_suitability_summary(
            symbol=symbol, method="owner_earnings",
            score=int(oe_score), category=oe_category,
            flags=[f.dict() for f in flags], evidence=oe_evidence,
            valuation_inputs={
                "currency": currency,
                "baseOe": float(base_oe) if base_oe is not None else None,
                "forecastYears": int(n),
                "discountRateUsed": float(r) if r else None,
                "oeGrowthRateUsed": float(g_oe) if g_oe is not None else None,
                "terminalGrowthRateUsed": float(terminal_g_used) if terminal_g_used is not None else None,
                "intrinsicValuePerShare": float(intrinsic_ps) if intrinsic_ps is not None else None,
                "currentPrice": current_price, "upsideDownsidePct": upside,
            },
            input_decisions=input_decisions,
        )

        if intrinsic_ps is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-PER-SHARE", severity="high",
                message="OE computed but intrinsic value per share unavailable.",
                evidence={"enterpriseValue": enterprise_value, "equityValue": equity_value, "shares": shares},
                recommendation="Provide sharesOutstanding and netDebt overrides.",
            ))

        valuation = OwnerEarningsValuation(
            symbol=symbol.upper(), companyId=company_id, currency=currency,
            forecastYears=int(n), discountRateUsed=float(r) if r else 0.0,
            oeGrowthRateUsed=float(g_oe) if g_oe is not None else None,
            terminalGrowthRateUsed=float(terminal_g_used) if terminal_g_used is not None else None,
            maintenanceCapexRatioUsed=float(mc_ratio),
            baseOe=float(base_oe) if base_oe is not None else None,
            baseOeFiscalYear=int(base_oe_fy) if isinstance(base_oe_fy, int) else None,
            netIncomeUsed=float(net_income_used) if net_income_used is not None else None,
            daUsed=float(da_used) if da_used is not None else None,
            capexUsed=float(capex_used) if capex_used is not None else None,
            wcChangeUsed=float(wc_change_used) if wc_change_used is not None else None,
            forecastOe=[float(x) for x in forecast_oe],
            pvOe=[float(x) for x in pv_oe],
            discountFactors=[float(x) for x in discount_factors],
            totalPvOe=float(total_pv_oe),
            terminalValue=float(tv) if tv is not None else None,
            pvTerminalValue=float(pv_tv) if pv_tv is not None else None,
            oeNPlus1=float(oe_n_plus_1) if oe_n_plus_1 is not None else None,
            enterpriseValue=float(enterprise_value) if enterprise_value is not None else None,
            netDebtUsed=float(net_debt) if net_debt is not None else None,
            equityValue=float(equity_value) if equity_value is not None else None,
            sharesOutstanding=float(shares) if shares is not None else None,
            intrinsicValuePerShare=float(intrinsic_ps) if intrinsic_ps is not None else None,
            currentPrice=current_price, upsideDownsidePct=upside,
            sensitivityScenarios=sensitivity_grid,
        )

        # ── Build resolved inputs for Gate 3 ───────────────────────────────
        resolved_inputs: Dict[str, Any] = {
            "base_oe":             round(float(base_oe), 2)   if base_oe is not None else None,
            "g_oe_final":          round(float(g_oe), 4)      if g_oe    is not None else None,
            "g_oe_source":         g_oe_source,
            "discount_rate_final": round(float(r), 4)         if r       else None,
            "discount_rate_source": r_source,
            "terminal_g_final":    round(float(terminal_g_used), 4) if terminal_g_used is not None else None,
            "forecast_years":      int(n),
            "net_debt":            round(float(net_debt), 0)  if net_debt is not None else None,
            "shares":              round(float(shares), 0)    if shares   is not None else None,
            "resolved_at":         datetime.utcnow().isoformat() + "Z",
        }

        # ── Audit run ──────────────────────────────────────────────────────
        now_iso = datetime.utcnow().isoformat() + "Z"
        output_snapshot = {
            "valuation": valuation.dict(),
            "applicability": {
                "score": oe_score, "category": oe_category,
                "flags": [f.dict() for f in flags],
                "suitabilitySummary": suitability_summary,
            },
            "dataQuality": {
                "freshnessDays": {"lastComputedAt": now_iso},
                "fallbacksUsed": bool(fallbacks_used),
                "inputDecisions": input_decisions,
            },
            "sensitivity": sensitivity_grid.dict() if sensitivity_grid is not None else None,
            "suitabilityEvidence": oe_evidence,
            "lastComputedAt": now_iso,
        }
        await self.repo.insert_valuation_run(
            company_id=company_id, method="owner_earnings",
            run={
                "run_by_user_id":    user_id,
                "input_snapshot":    {
                    "overrides":              overrides.dict(),
                    "dependency_fingerprint": dependency_fingerprint,
                    "resolved":               resolved_inputs,
                },
                "assumption_snapshot": defaults,
                "output_snapshot":   output_snapshot,
                "data_version_tag":  None,
                "notes":             overrides.notes,
            },
        )

        return OwnerEarningsResponse(
            valuation=valuation,
            applicability=Applicability(
                score=oe_score, category=oe_category, flags=flags,
                suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": now_iso},
                fallbacksUsed=bool(fallbacks_used),
                inputDecisions=input_decisions,
            ),
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _build_empty_response(
        self, symbol, company_id, currency, sector, n, flags, input_decisions,
        current_price, user_id=None,
    ) -> OwnerEarningsResponse:
        try:
            oe_score, oe_category, oe_flags, oe_evidence = await evaluate_owner_earnings_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
            )
        except Exception:
            oe_score, oe_category, oe_flags, oe_evidence = 0, "Poor", [], {}

        all_flags = flags + oe_flags
        suitability_summary = None
        try:
            suitability_summary = await generate_suitability_summary(
                symbol=symbol, method="owner_earnings",
                score=int(oe_score), category=oe_category,
                flags=[f.dict() for f in all_flags], evidence=oe_evidence,
                valuation_inputs={
                    "currency": currency, "baseOe": None,
                    "forecastYears": int(n), "currentPrice": current_price,
                    "note": "Early abort — required OE inputs unavailable.",
                },
                input_decisions=input_decisions,
            )
        except Exception:
            pass

        valuation = OwnerEarningsValuation(
            symbol=symbol.upper(), companyId=company_id, currency=currency,
            forecastYears=n, discountRateUsed=0.0,
            forecastOe=[0.0] * n, pvOe=[0.0] * n, totalPvOe=0.0,
            currentPrice=current_price,
        )
        return OwnerEarningsResponse(
            valuation=valuation,
            applicability=Applicability(
                score=int(oe_score), category=oe_category,
                flags=all_flags, suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={}, fallbacksUsed=True, inputDecisions=input_decisions,
            ),
        )

    async def _resolve_base_oe(self, company_id, maintenance_capex_ratio, include_wc):
        cf: Optional[Dict[str, Any]] = None
        if hasattr(self.repo, "get_cash_flow_oe_inputs"):
            try:
                cf = await self.repo.get_cash_flow_oe_inputs(company_id)
            except Exception:
                cf = None

        is_row = None
        try:
            is_row = await self.repo.get_income_statement_latest(company_id)
        except Exception:
            pass

        net_income = _safe_float(
            (is_row or {}).get("net_income_to_common") or (is_row or {}).get("net_income")
        )
        da         = _safe_float(cf.get("depreciation_amortization")) if cf else None
        capex_raw  = _safe_float(cf.get("capital_expenditures"))      if cf else None
        wc_change  = _safe_float(cf.get("change_in_working_capital")) if cf else None
        fiscal_year = (cf or {}).get("fiscal_year") or (is_row or {}).get("fiscal_year")

        value = _compute_oe(net_income, da, capex_raw, wc_change, maintenance_capex_ratio, include_wc)
        return {
            "value": value,
            "evidence": {
                "source": "income_statements + cash_flow_statements (latest annual)",
                "netIncome": net_income, "da": da, "capex": capex_raw,
                "wcChange": wc_change if include_wc else None,
                "maintenanceCapexRatio": maintenance_capex_ratio,
                "includeWcChange": include_wc,
                "computedOe": value,
                "asOfFiscalYear": fiscal_year,
            },
        }