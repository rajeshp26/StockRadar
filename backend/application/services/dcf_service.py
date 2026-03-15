# application/services/dcf_service.py
"""
DCF Service — Three-Gate Caching (Phase 2c)

Gate 1 — Timestamp:   Are dependency tables newer than the last valuation run?
Gate 2 — Fingerprint: Have source data VALUES actually changed?
Gate 3 — Materiality: Are resolved inputs (base_fcf, wacc, terminal_g) material?

Bypass rules (always recompute):
  force=True              → explicit caller request
  no_prior_valuation      → nothing to compare
  any override non-null   → explicit user inputs, always honour them

Terminal value methods: perpetuity_growth | exit_multiple
Price policy: intrinsic is cached; currentPrice + upside computed at read-time only.
"""
from __future__ import annotations
 
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
 
from application.services.ai_service import generate_suitability_summary
from application.services.dcf_suitability import evaluate_dcf_suitability
from application.services.recompute_guard import RecomputeGuard
from domain.models.valuation_dcf import (
    DcfRequestOverrides,
    DcfResponse,
    DcfSensitivityGrid,
    DcfValuation,
    TerminalMethod,
)
from domain.models.valuation_rule1 import Applicability, DataQuality, DiagnosticFlag
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import (
    build_fingerprint,
    clamp,
    compute_fcf,
    pct_or_frac_to_frac,
    safe_float,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _assert_length_invariant(name, arr, expected_len, flags):
    if len(arr) != expected_len:
        flags.append(DiagnosticFlag(
            code="DCF-LENGTH-MISMATCH", severity="critical",
            message=f"{name} length ({len(arr)}) does not match forecastYears ({expected_len}).",
            evidence={"field": name, "length": len(arr), "forecastYears": expected_len},
            recommendation="This indicates an internal computation error. Re-run or inspect recent changes.",
        ))
        return False
    return True

# ── Service ────────────────────────────────────────────────────────────────────

class DcfService:
    """Discounted Cash Flow valuation service with three-gate caching."""

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo  = repo
        self.guard = guard

    # ── Public entry point ─────────────────────────────────────────────────────

    async def compute_dcf_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[DcfRequestOverrides] = None,
        force:     bool = False,
    ) -> DcfResponse:
        overrides  = overrides or DcfRequestOverrides()
        method     = "dcf"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
        sector     = ctx.get("sector")

        # ── Force: bypass all gates ────────────────────────────────────────
        if force:
            dep_values  = await self.repo.get_dcf_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            logger.info("[VALUATION][DCF] forced recompute: %s", symbol)
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
            "[VALUATION][DCF] Gate 1 fired: %s reason=%s dep_ts=%s last_ts=%s",
            symbol, gate1.reason, gate1.latest_dependency_at, gate1.last_valuation_at,
        )

        # ── No prior valuation ─────────────────────────────────────────────
        if gate1.reason == "no_prior_valuation":
            dep_values  = await self.repo.get_dcf_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Override present: bypass Gates 2 & 3 ──────────────────────────
        if self._has_overrides(overrides):
            dep_values  = await self.repo.get_dcf_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            logger.info("[VALUATION][DCF] Override present → bypass Gates 2&3: %s", symbol)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides,
                dependency_fingerprint=fingerprint,
            )

        # ── Gate 2: Fingerprint ────────────────────────────────────────────
        dep_values  = await self.repo.get_dcf_dependency_values(company_id)
        fingerprint = build_fingerprint(dep_values)

        gate2 = await self.guard.check_fingerprint(company_id, method, fingerprint)
        if not gate2.should_recompute:
            logger.info("[VALUATION][DCF] Gate 2 → cached (fingerprint_match): %s", symbol)
            return await self._serve_cached(
                symbol, company_id, currency, sector, user_id, method, overrides
            )

        logger.info(
            "[VALUATION][DCF] Gate 2 fired: %s reason=%s", symbol, gate2.reason
        )

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
                    "[VALUATION][DCF] Gate 3 → cached (immaterial): %s reason=%s",
                    symbol, gate3_reason,
                )
                await self.guard.record_immaterial_change(company_id, method, fingerprint)
                return await self._serve_cached(
                    symbol, company_id, currency, sector, user_id, method, overrides
                )
            logger.info(
                "[VALUATION][DCF] Gate 3 → recompute (material): %s reason=%s",
                symbol, gate3_reason,
            )
        else:
            logger.debug("[VALUATION][DCF] Gate 3 skipped: no stored resolved yet: %s", symbol)

        return await self._compute_and_persist(
            symbol, company_id, currency, sector, user_id, overrides,
            dependency_fingerprint=fingerprint,
        )

    async def get_cached(self, symbol: str) -> Optional[DcfResponse]:
        """
        Pure cache read — no gate logic, no recompute, no DB writes.
        Returns None if no prior valuation exists.
        Used by GET /valuations/{symbol}/dcf for instant tab loads.
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            return None
        company_id = int(ctx["company_id"])
 
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method="dcf")
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
        intrinsic_ps  = safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside        = None
        if (current_price is not None and float(current_price) > 0
                and intrinsic_ps is not None and intrinsic_ps > 0):
            upside = (float(intrinsic_ps) - float(current_price)) / float(current_price)
        valuation_payload["currentPrice"]      = current_price
        valuation_payload["upsideDownsidePct"] = upside
 
        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{"code": "DCF-NO-AUDIT", "severity": "info",
                           "message": "No prior DCF valuation run found; run Recompute once."}],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed
 
        return DcfResponse(
            valuation=DcfValuation(**valuation_payload),
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
        overrides:  DcfRequestOverrides,
    ) -> DcfResponse:
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info("[VALUATION][DCF] Cached path: snapshot missing, recomputing: %s", symbol)
            dep_values  = await self.repo.get_dcf_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
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
        intrinsic_ps  = safe_float(valuation_payload.get("intrinsicValuePerShare"))
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
                    "code": "DCF-NO-AUDIT", "severity": "info",
                    "message": "No prior DCF valuation run found; suitability scorecard not available on cached path.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return DcfResponse(
            valuation=DcfValuation(**valuation_payload),
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**dq_payload),
        )

    # ── Gate helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _has_overrides(overrides: DcfRequestOverrides) -> bool:
        return any([
            overrides.forecastFcf            is not None,
            overrides.forecastYears          is not None,
            overrides.fcfGrowthRate          is not None,
            # revenueGrowthRate intentionally omitted:
            # Pydantic model_validator maps it to fcfGrowthRate before this runs.
            overrides.wacc                   is not None,
            overrides.terminalMethod         is not None,
            overrides.terminalGrowthRate     is not None,
            overrides.exitMultiple           is not None,
            overrides.terminalMetric         is not None,   # ← ADDED
            overrides.ebitdaMarginAssumption is not None,   # ← ADDED (affects terminal EBITDA derivation)
            overrides.terminalEbitda         is not None,
            overrides.netDebt                is not None,
            overrides.sharesOutstanding      is not None,
            # fcfMarginAssumption intentionally omitted:
            # stored in analytics stream only, not used in intrinsic computation.
        ])

    async def resolve_current_inputs(
        self,
        company_id: int,
        overrides:  DcfRequestOverrides,
        defaults:   Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Lightweight input resolution for Gate 3.
        Resolves base_fcf, wacc, terminal_g without computing intrinsic value.
        Returns dict with same keys stored in input_snapshot["resolved"].
        """
        # ── Base FCF ──────────────────────────────────────────────────────
        base_fcf: Optional[float] = None
        base_fcf_source = "cash_flow_statements"
        if overrides.forecastFcf is not None:
            base_fcf        = safe_float(overrides.forecastFcf[0]) if overrides.forecastFcf else None
            base_fcf_source = "override.forecastFcf[0]"
        elif overrides.fcfGrowthRate is None:
            cf_data    = await self._resolve_base_fcf(company_id)
            base_fcf   = safe_float(cf_data.get("value"))

        # ── WACC ──────────────────────────────────────────────────────────
        wacc: Optional[float] = None
        wacc_source = "unknown"
        if overrides.wacc is not None:
            wacc_raw   = float(overrides.wacc)
            wacc_source = "override.wacc"
        else:
            wacc_raw   = safe_float(defaults.get("wacc_default"))
            wacc_source = "defaults.wacc_default"
        if wacc_raw is not None:
            wacc = clamp(
                pct_or_frac_to_frac(float(wacc_raw)),
                float(defaults.get("wacc_floor", 0.06)),
                float(defaults.get("wacc_cap",   0.18)),
            )

        # ── Terminal growth ────────────────────────────────────────────────
        terminal_g: Optional[float] = None
        terminal_g_source = "unknown"
        terminal_method   = (
            overrides.terminalMethod
            or defaults.get("terminal_method_default")
            or "perpetuity_growth"
        )
        if terminal_method == "perpetuity_growth":
            if overrides.terminalGrowthRate is not None:
                tg_raw         = float(overrides.terminalGrowthRate)
                terminal_g_source = "override.terminalGrowthRate"
            else:
                tg_raw         = safe_float(defaults.get("terminal_growth_default"))
                terminal_g_source = "defaults.terminal_growth_default"
            if tg_raw is not None:
                terminal_g = pct_or_frac_to_frac(float(tg_raw))
        else:
            terminal_g_source = "exit_multiple"

        # ── Net debt ──────────────────────────────────────────────────────
        net_debt: Optional[float] = None
        if overrides.netDebt is not None:
            net_debt = float(overrides.netDebt)
        else:
            bs   = await self.repo.get_balance_sheet_latest(company_id)
            debt = safe_float(bs.get("total_debt"))   if bs else None
            cash = safe_float(bs.get("cash_and_cash_equivalents")) if bs else None
            if debt is not None and cash is not None:
                net_debt = float(debt) - float(cash)

        # ── Shares ────────────────────────────────────────────────────────
        shares: Optional[float] = None
        if overrides.sharesOutstanding is not None:
            shares = float(overrides.sharesOutstanding)
        else:
            rows = await self.repo.get_shares_history(company_id)
            if rows:
                sh = safe_float(rows[-1].get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares = sh
            if shares is None:
                summary = await self.repo.get_company_summary_latest(company_id)
                if summary:
                    sh = safe_float(summary.get("shares_outstanding"))
                    if sh and sh > 0:
                        shares = sh

        n = int(overrides.forecastYears) if overrides.forecastYears is not None else int(defaults.get("forecast_years_default", 5))

        return {
            "base_fcf":         round(base_fcf, 2)    if base_fcf    is not None else None,
            "base_fcf_source":  base_fcf_source,
            "wacc_final":       round(wacc, 4)         if wacc        is not None else None,
            "wacc_source":      wacc_source,
            "terminal_g_final": round(terminal_g, 4)   if terminal_g  is not None else None,
            "terminal_g_source": terminal_g_source,
            "terminal_method":  terminal_method,
            "forecast_years":   n,
            "net_debt":         round(net_debt, 0)     if net_debt    is not None else None,
            "shares":           round(shares, 0)        if shares      is not None else None,
        }

    # ── Full computation + persistence ─────────────────────────────────────────

    async def _compute_and_persist(
        self,
        symbol:                 str,
        company_id:             int,
        currency:               str,
        sector:                 Optional[str],
        user_id:                Optional[int],
        overrides:              DcfRequestOverrides,
        dependency_fingerprint: Optional[str] = None,
    ) -> DcfResponse:
        defaults = await self.repo.get_method_params(company_id, method="dcf")

        flags:          List[DiagnosticFlag] = []
        input_decisions: Dict[str, Any]     = {"dcf": {}}
        fallbacks_used                       = False

        current_price = await self.repo.get_current_market_price(company_id)

        # ── Forecast years ─────────────────────────────────────────────────
        n_default = int(defaults.get("forecast_years_default", 5))
        if overrides.forecastYears is not None:
            n = int(overrides.forecastYears)
            input_decisions["dcf"]["forecastYears"] = {"source": "override.forecastYears", "value": n}
        else:
            n = n_default
            input_decisions["dcf"]["forecastYears"] = {"source": "defaults.forecast_years_default", "value": n}
            fallbacks_used = True
        n = int(clamp(float(n), 1, 20))

        series:          Optional[List[float]] = overrides.forecastFcf
        base_fcf_value:  Optional[float]       = None
        base_fcf_fy:     Optional[int]         = None

        if series is not None:
            if len(series) != n:
                n = len(series)
                input_decisions["dcf"]["forecastYears"] = {"source": "override.forecastFcf.length", "value": n}
            input_decisions["dcf"]["forecastFcf"] = {"source": "override.forecastFcf", "years": n}
        else:
            base_cf        = await self._resolve_base_fcf(company_id)
            base_fcf_value = safe_float(base_cf.get("value"))
            base_fcf_fy    = base_cf.get("evidence", {}).get("asOfFiscalYear")
            input_decisions["dcf"]["baseFcf"] = base_cf.get("evidence")

            fcf_growth = None
            if defaults.get("fcf_growth_rate") is not None and overrides.fcfGrowthRate is None:
                fcf_growth = float(defaults.get("fcf_growth_rate"))
                input_decisions["dcf"]["fcfGrowthRate"] = {"source": "defaults.fcf_growth_rate", "valueRaw": fcf_growth}
                fallbacks_used = True
            elif overrides.fcfGrowthRate is not None:
                fcf_growth = float(overrides.fcfGrowthRate)
                input_decisions["dcf"]["fcfGrowthRate"] = {"source": "override.fcfGrowthRate", "valueRaw": fcf_growth}

            if base_fcf_value is None or fcf_growth is None:
                flags.append(DiagnosticFlag(
                    code="DCF-NO-FORECAST", severity="critical",
                    message="No explicit FCF forecast provided and insufficient assumptions to derive a forecast.",
                    evidence={"hasForecastFcf": False, "baseFcf": base_fcf_value, "fcfGrowthRate": fcf_growth},
                    recommendation="Provide forecastFcf[] or configure explicit defaults/overrides for DCF forecasting inputs.",
                ))
                terminal_method = (
                    overrides.terminalMethod or defaults.get("terminal_method_default") or "perpetuity_growth"
                )
                valuation = DcfValuation(
                    symbol=symbol.upper(), companyId=company_id, currency=currency,
                    terminalMethod=terminal_method, forecastYears=n,
                    forecastFcf=[0.0] * n, pvFcf=[0.0] * n, totalPvFcf=0.0,
                    discountFactors=[0.0] * n, waccUsed=0.0,
                    baseFcf=base_fcf_value,
                    baseFcfFiscalYear=int(base_fcf_fy) if isinstance(base_fcf_fy, int) else None,
                    currentPrice=current_price, upsideDownsidePct=None,
                )
                return DcfResponse(
                    valuation=valuation,
                    applicability=Applicability(score=0, category="Poor", flags=flags),
                    dataQuality=DataQuality(
                        freshnessDays={}, fallbacksUsed=True, inputDecisions=input_decisions,
                    ),
                )

            g_fcf = clamp(
                pct_or_frac_to_frac(float(fcf_growth)),
                float(defaults.get("fcf_growth_floor", 0.00)),
                float(defaults.get("fcf_growth_cap",   0.20)),
            )
            input_decisions["dcf"]["fcfGrowthRate"] = {
                **(input_decisions["dcf"].get("fcfGrowthRate") or {}),
                "valueFinal": g_fcf,
            }
            if pct_or_frac_to_frac(float(fcf_growth)) != g_fcf:
                flags.append(DiagnosticFlag(
                    code="DCF-GROWTH-CLAMP", severity="info",
                    message="FCF growth rate was clamped to safety bounds.",
                    evidence=input_decisions["dcf"]["fcfGrowthRate"],
                ))
            series = [float(base_fcf_value) * ((1.0 + g_fcf) ** t) for t in range(1, n + 1)]
            input_decisions["dcf"]["forecastFcf"] = {"source": "derived_from_baseFcf_and_growth", "years": n}
            fallbacks_used = True

        assert series is not None
        forecast_fcf   = [float(x) for x in series]
        terminal_method: TerminalMethod = (
            overrides.terminalMethod or defaults.get("terminal_method_default") or "perpetuity_growth"
        )

        # ── WACC ──────────────────────────────────────────────────────────
        if overrides.wacc is not None:
            wacc_raw    = float(overrides.wacc)
            wacc_source = "override.wacc"
        else:
            wacc_raw    = safe_float(defaults.get("wacc_default"))
            wacc_source = "defaults.wacc_default"
            fallbacks_used = True

        if wacc_raw is None:
            flags.append(DiagnosticFlag(
                code="DCF-NO-WACC", severity="critical",
                message="Discount rate (WACC) is missing.",
                recommendation="Provide wacc override or configure dcf method defaults for wacc.",
            ))
            wacc = 0.0
        else:
            wacc_floor = float(defaults.get("wacc_floor", 0.06))
            wacc_cap   = float(defaults.get("wacc_cap",   0.18))
            wacc       = clamp(pct_or_frac_to_frac(float(wacc_raw)), wacc_floor, wacc_cap)
            input_decisions["dcf"]["wacc"] = {
                "source": wacc_source, "valueRaw": float(wacc_raw),
                "valueFinal": float(wacc), "waccFloor": wacc_floor, "waccCap": wacc_cap,
                "clamped": pct_or_frac_to_frac(float(wacc_raw)) != float(wacc),
            }
            if input_decisions["dcf"]["wacc"]["clamped"]:
                flags.append(DiagnosticFlag(
                    code="DCF-WACC-CLAMP", severity="info",
                    message="WACC was clamped to safety bounds.",
                    evidence=input_decisions["dcf"]["wacc"],
                ))

        # ── Discount forecast cash flows ───────────────────────────────────
        pv_fcf:           List[float] = []
        discount_factors: List[float] = []
        total_pv                      = 0.0

        if wacc > 0:
            for t, cf in enumerate(forecast_fcf, start=1):
                df = 1.0 / ((1.0 + wacc) ** t)
                pv = cf * df
                discount_factors.append(float(df))
                pv_fcf.append(float(pv))
                total_pv += float(pv)
        else:
            pv_fcf           = [0.0] * n
            discount_factors = [0.0] * n
            flags.append(DiagnosticFlag(
                code="DCF-NO-DISCOUNT", severity="high",
                message="DCF cannot compute present values because WACC is not available/valid.",
            ))

        # ── Invariants ────────────────────────────────────────────────────
        ok = True
        ok &= _assert_length_invariant("forecastFcf",     forecast_fcf,     n, flags)
        ok &= _assert_length_invariant("pvFcf",           pv_fcf,           n, flags)
        ok &= _assert_length_invariant("discountFactors", discount_factors,  n, flags)

        if not ok:
            valuation = DcfValuation(
                symbol=symbol.upper(), companyId=company_id, currency=currency,
                terminalMethod=terminal_method, forecastYears=n,
                forecastFcf=forecast_fcf, pvFcf=pv_fcf, totalPvFcf=float(total_pv),
                discountFactors=discount_factors, waccUsed=float(wacc) if wacc else 0.0,
            )
            return DcfResponse(
                valuation=valuation,
                applicability=Applicability(score=0, category="Poor", flags=flags),
                dataQuality=DataQuality(freshnessDays={}, fallbacksUsed=True, inputDecisions=input_decisions),
            )

        # ── Terminal value ─────────────────────────────────────────────────
        tv = None; pv_tv = None
        terminal_g_used: Optional[float] = None
        cf_n_plus_1:     Optional[float] = None
        g_source_for_resolved             = "unknown"

        if wacc > 0:
            if terminal_method == "perpetuity_growth":
                if overrides.terminalGrowthRate is not None:
                    g_raw    = float(overrides.terminalGrowthRate)
                    g_source = "override.terminalGrowthRate"
                else:
                    g_raw    = safe_float(defaults.get("terminal_growth_default"))
                    g_source = "defaults.terminal_growth_default"
                    if g_raw is not None:
                        fallbacks_used = True

                g_source_for_resolved = g_source or "unknown"

                if g_raw is None:
                    flags.append(DiagnosticFlag(
                        code="DCF-NO-TERM-G", severity="critical",
                        message="Terminal growth rate (g) is missing for perpetuity growth terminal value.",
                        recommendation="Provide terminalGrowthRate override or set terminal_growth_default in method defaults.",
                    ))
                else:
                    g = pct_or_frac_to_frac(float(g_raw))
                    terminal_g_used = g
                    if g >= wacc:
                        flags.append(DiagnosticFlag(
                            code="DCF-GE-WACC", severity="critical",
                            message="Terminal growth rate (g) must be less than WACC.",
                            evidence={"g": g, "wacc": wacc, "source": g_source},
                            recommendation="Lower g or raise WACC.",
                        ))
                    else:
                        cf_n       = float(forecast_fcf[-1])
                        cf_n_plus_1 = cf_n * (1.0 + g)
                        tv         = cf_n_plus_1 / (wacc - g)
                        pv_tv      = tv / ((1.0 + wacc) ** n)

                    input_decisions["dcf"]["terminal"] = {
                        "method": "perpetuity_growth", "source": g_source,
                        "gRaw": float(g_raw), "gFinal": float(g), "wacc": float(wacc),
                        "cfNPlus1": float(cf_n_plus_1) if cf_n_plus_1 else None,
                        "valid": (g < wacc),
                    }

            elif terminal_method == "exit_multiple":
                g_source_for_resolved = "exit_multiple"
                mult = float(overrides.exitMultiple) if overrides.exitMultiple is not None else (
                    safe_float(defaults.get("exit_multiple_default")) or 0.0
                )
                mult_source  = "override.exitMultiple" if overrides.exitMultiple is not None else "defaults.exit_multiple_default"
                metric       = overrides.terminalMetric or defaults.get("terminal_metric_default") or "ebitda"
                ebitda_terminal = overrides.terminalEbitda

                if mult <= 0:
                    flags.append(DiagnosticFlag(code="DCF-NO-EXIT-MULT", severity="critical",
                        message="Exit multiple missing/invalid.", evidence={"exitMultiple": mult}))
                elif ebitda_terminal is None:
                    flags.append(DiagnosticFlag(code="DCF-NO-TERM-EBITDA", severity="critical",
                        message="Terminal EBITDA required for Exit Multiple terminal value.",
                        evidence={"terminalMetric": metric, "exitMultiple": mult}))
                else:
                    tv    = float(ebitda_terminal) * float(mult)
                    pv_tv = tv / ((1.0 + wacc) ** n)

                input_decisions["dcf"]["terminal"] = {
                    "method": "exit_multiple", "exitMultiple": float(mult) if mult else None,
                    "exitMultipleSource": mult_source, "terminalMetric": metric,
                    "terminalEbitda": float(ebitda_terminal) if ebitda_terminal is not None else None,
                }

        # ── Enterprise → Equity → Per-share bridge ─────────────────────────
        enterprise_value: Optional[float] = None
        if tv is not None and pv_tv is not None:
            enterprise_value = float(total_pv) + float(pv_tv)
        else:
            enterprise_value = float(total_pv) if total_pv else None

        net_debt: Optional[float] = None
        net_debt_source = None
        if overrides.netDebt is not None:
            net_debt        = float(overrides.netDebt)
            net_debt_source = "override.netDebt"
        else:
            bs   = await self.repo.get_balance_sheet_latest(company_id)
            debt = safe_float(bs.get("total_debt"))               if bs else None
            cash = safe_float(bs.get("cash_and_cash_equivalents")) if bs else None
            if debt is not None and cash is not None:
                net_debt        = float(debt) - float(cash)
                net_debt_source = "balance_sheets.total_debt - cash_and_cash_equivalents"
                fallbacks_used  = True
        input_decisions["dcf"]["netDebt"] = {"source": net_debt_source, "value": net_debt}

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
                sh = safe_float(rows[-1].get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares        = float(sh)
                    shares_source = "income_statements.shares_outstanding_diluted(latest)"
                    fallbacks_used = True
        if shares is None:
            summary = await self.repo.get_company_summary_latest(company_id)
            if summary:
                sh = safe_float(summary.get("shares_outstanding"))
                if sh and sh > 0:
                    shares        = float(sh)
                    shares_source = "company_summary.shares_outstanding"
                    fallbacks_used = True
        input_decisions["dcf"]["sharesOutstanding"] = {"source": shares_source, "value": shares}

        intrinsic_ps: Optional[float] = None
        if equity_value is not None and shares is not None and float(shares) > 0:
            intrinsic_ps = float(equity_value) / float(shares)

        upside: Optional[float] = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps and intrinsic_ps > 0:
            upside = (float(intrinsic_ps) - float(current_price)) / float(current_price)

        # ── Sensitivity grid ───────────────────────────────────────────────
        sensitivity_grid: Optional[DcfSensitivityGrid] = None
        if (terminal_method == "perpetuity_growth" and wacc and float(wacc) > 0
                and terminal_g_used is not None and intrinsic_ps is not None
                and equity_value is not None and shares and float(shares) > 0):
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
            r_used  = float(wacc)
            g_used  = float(terminal_g_used)

            if r_list is None:
                derived = True
                r_list = [max(0.01, r_used - 0.01), r_used, min(0.30, r_used + 0.01)]
            if g_list is None:
                derived = True
                g_list = [max(0.00, g_used - 0.01), g_used, max(0.00, g_used + 0.01)]

            matrix: List[List[Optional[float]]] = []
            for r_s in r_list:
                row: List[Optional[float]] = []
                for g_s in g_list:
                    if g_s >= r_s:
                        row.append(None)
                        continue
                    pv_sum = sum(float(cf) / ((1.0 + r_s) ** t) for t, cf in enumerate(forecast_fcf, start=1))
                    cf_np1 = float(forecast_fcf[-1]) * (1.0 + g_s)
                    tv_s   = cf_np1 / (r_s - g_s)
                    pv_tv_s = tv_s / ((1.0 + r_s) ** n)
                    ev_s   = pv_sum + pv_tv_s
                    eq_s   = ev_s - float(net_debt) if net_debt is not None else None
                    row.append(float(eq_s) / float(shares) if eq_s is not None else None)
                matrix.append(row)

            sensitivity_grid = DcfSensitivityGrid(
                discountRates=[float(x) for x in r_list],
                terminalGrowthRates=[float(x) for x in g_list],
                intrinsicValuePerShareMatrix=matrix,
                currency=currency,
            )
            input_decisions["dcf"]["sensitivity"] = {
                "enabled": True,
                "source": "defaults" if not derived else "derived_around_used_r_g",
            }
            if derived:
                fallbacks_used = True

        # ── Suitability scorecard ──────────────────────────────────────────
        dcf_score, dcf_category, dcf_flags, dcf_evidence = await evaluate_dcf_suitability(
            repo=self.repo, company_id=company_id, sector=sector,
        )
        flags.extend(dcf_flags)

        suitability_summary = await generate_suitability_summary(
            symbol=symbol, method="dcf",
            score=int(dcf_score), category=dcf_category,
            flags=[f.dict() for f in flags], evidence=dcf_evidence,
            valuation_inputs={
                "currency":               currency,
                "baseFcf":                float(base_fcf_value) if base_fcf_value is not None else None,
                "forecastYears":          int(n),
                "waccUsed":               float(wacc) if wacc else None,
                "terminalMethod":         terminal_method,
                "terminalGrowthRateUsed": float(terminal_g_used) if terminal_g_used is not None else None,
                "intrinsicValuePerShare": float(intrinsic_ps) if intrinsic_ps is not None else None,
                "currentPrice":           current_price,
                "upsideDownsidePct":      upside,
            },
            input_decisions=input_decisions,
        )

        if intrinsic_ps is None:
            flags.append(DiagnosticFlag(
                code="DCF-NO-PER-SHARE", severity="high",
                message="Intrinsic value per share unavailable (missing shares and/or equity bridge).",
                evidence={"enterpriseValue": enterprise_value, "equityValue": equity_value, "sharesOutstanding": shares},
                recommendation="Provide sharesOutstanding and netDebt, or ensure financial tables are populated.",
            ))

        valuation = DcfValuation(
            symbol=symbol.upper(), companyId=company_id, currency=currency,
            terminalMethod=terminal_method, forecastYears=int(n),
            forecastFcf=[float(x) for x in forecast_fcf],
            pvFcf=[float(x) for x in pv_fcf],
            totalPvFcf=float(total_pv),
            discountFactors=[float(x) for x in discount_factors],
            waccUsed=float(wacc) if wacc is not None else 0.0,
            terminalValue=(float(tv) if tv is not None else None),
            pvTerminalValue=(float(pv_tv) if pv_tv is not None else None),
            terminalGrowthRateUsed=(float(terminal_g_used) if terminal_g_used is not None else None),
            cashFlowNPlus1=(float(cf_n_plus_1) if cf_n_plus_1 is not None else None),
            enterpriseValue=(float(enterprise_value) if enterprise_value is not None else None),
            netDebtUsed=(float(net_debt) if net_debt is not None else None),
            equityValue=(float(equity_value) if equity_value is not None else None),
            sharesOutstanding=(float(shares) if shares is not None else None),
            intrinsicValuePerShare=(float(intrinsic_ps) if intrinsic_ps is not None else None),
            baseFcf=(float(base_fcf_value) if base_fcf_value is not None else None),
            baseFcfFiscalYear=(int(base_fcf_fy) if isinstance(base_fcf_fy, int) else None),
            currentPrice=current_price,
            upsideDownsidePct=upside,
            sensitivityScenarios=sensitivity_grid,
        )

        # ── Persist: dcf_valuations (analytics stream) ─────────────────────
        try:
            await self.repo.insert_dcf_valuation(payload={
                "company_id":                  company_id,
                "analysis_date":               date.today().isoformat(),
                "forecast_years":              int(n),
                "revenue_growth_rate":         None,
                "terminal_growth_rate":        float(terminal_g_used) if terminal_g_used is not None else None,
                "wacc_used":                   float(wacc) if wacc is not None else None,
                "fcf_margin_assumption":       pct_or_frac_to_frac(float(overrides.fcfMarginAssumption)) if overrides.fcfMarginAssumption is not None else None,
                "total_pv_fcf":                float(total_pv),
                "terminal_value":              float(tv) if tv is not None else None,
                "pv_terminal_value":           float(pv_tv) if pv_tv is not None else None,
                "enterprise_value_dcf":        float(enterprise_value) if enterprise_value is not None else None,
                "less_net_debt":               float(net_debt) if net_debt is not None else None,
                "equity_value":                float(equity_value) if equity_value is not None else None,
                "shares_outstanding":          int(shares) if shares is not None else None,
                "intrinsic_value_per_share":   float(intrinsic_ps) if intrinsic_ps is not None else None,
                "current_stock_price":         current_price,
                "upside_downside_pct":         upside,
                "analyst_name":                overrides.analystName,
                "sensitivity_scenarios":       sensitivity_grid.dict() if sensitivity_grid is not None else None,
                "notes":                       overrides.notes,
            })
        except Exception:
            pass

        # ── Build resolved inputs for Gate 3 storage ───────────────────────
        # Captures the actual computed values so future Gate 3 comparisons
        # can determine whether a source data change is economically material.
        resolved_inputs: Dict[str, Any] = {
            "base_fcf":          round(float(base_fcf_value), 2) if base_fcf_value is not None else None,
            "base_fcf_source":   "cash_flow_statements",
            "wacc_final":        round(float(wacc), 4) if wacc else None,
            "wacc_source":       wacc_source,
            "terminal_g_final":  round(float(terminal_g_used), 4) if terminal_g_used is not None else None,
            "terminal_g_source": g_source_for_resolved,
            "terminal_method":   terminal_method,
            "forecast_years":    int(n),
            "net_debt":          round(float(net_debt), 0) if net_debt is not None else None,
            "shares":            round(float(shares), 0)   if shares    is not None else None,
            "resolved_at":       datetime.utcnow().isoformat() + "Z",
        }

        # ── Persist: valuation_runs (audited record) ───────────────────────
        now_iso = datetime.utcnow().isoformat() + "Z"
        output_snapshot = {
            "valuation": valuation.dict(),
            "applicability": {
                "score": dcf_score, "category": dcf_category,
                "flags": [f.dict() for f in flags],
                "suitabilitySummary": suitability_summary,
            },
            "dataQuality": {
                "freshnessDays": {"lastComputedAt": now_iso},
                "fallbacksUsed": bool(fallbacks_used),
                "inputDecisions": input_decisions,
            },
            "sensitivity": sensitivity_grid.dict() if sensitivity_grid is not None else None,
            "suitabilityEvidence": dcf_evidence,
            "lastComputedAt": now_iso,
        }
        await self.repo.insert_valuation_run(
            company_id=company_id, method="dcf",
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

        return DcfResponse(
            valuation=valuation,
            applicability=Applicability(
                score=dcf_score, category=dcf_category,
                flags=flags, suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": now_iso},
                fallbacksUsed=bool(fallbacks_used),
                inputDecisions=input_decisions,
            ),
        )

    async def _resolve_base_fcf(self, company_id: int) -> Dict[str, Any]:
        cf    = await self.repo.get_cash_flow_latest(company_id)
        ocf   = safe_float(cf.get("cash_from_operating_activities")) if cf else None
        capex = safe_float(cf.get("capital_expenditures"))           if cf else None
        value = compute_fcf(ocf, capex)
        return {
            "value": value,
            "evidence": {
                "source": "cash_flow_statements(latest annual)",
                "cashFromOperatingActivities": ocf,
                "capitalExpenditures": capex,
                "computedFcf": value,
                "asOfFiscalYear": cf.get("fiscal_year") if cf else None,
            },
        }