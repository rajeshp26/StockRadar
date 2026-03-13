# application/services/owner_earnings_service.py
from __future__ import annotations
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


# ── Helpers (local; isolation principle — do not import from other service files) ─

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _pct_or_frac_to_frac(x: float) -> float:
    return x / 100.0 if x > 1.0 else x


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        return f if f == f else None  # NaN check
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
    """
    Owner Earnings = Net Income + D&A − (Maintenance Capex) [± WC change]

    capex_raw: sign as stored in cash_flow_statements.
      - Negative (e.g. -1000) → cash outflow → add it (it's already negative).
      - Positive (absolute)   → subtract it.
    maintenance_capex_ratio: 0.0–1.0 fraction of total capex treated as maintenance.
    """
    if net_income is None:
        return None
    da_val = da if da is not None else 0.0
    capex_adj = 0.0
    if capex_raw is not None:
        maint = abs(capex_raw) * maintenance_capex_ratio
        capex_adj = -maint  # always a negative adjustment (reduces OE)

    oe = net_income + da_val + capex_adj

    if include_wc and wc_change is not None:
        # Positive WC change = more working capital tied up = cash consumed = reduces OE
        oe -= wc_change

    return oe


# ── Service ───────────────────────────────────────────────────────────────────

class OwnerEarningsService:
    """
    Owner Earnings (Buffett Method) valuation service.

    Architecture:
    - Mirrors DcfService exactly: cached-or-recompute guard, _compute_and_persist,
      sensitivity grid, AI summary, analytics stream insert, valuation_runs persist.
    - Terminal value: perpetuity growth only (consistent with Buffett's long-term focus).
    - Price policy: currentPrice + upsideDownsidePct computed at read-time only.
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo = repo
        self.guard = guard

    async def compute_owner_earnings_if_stale(
        self,
        symbol: str,
        user_id: Optional[int],
        overrides: Optional[OwnerEarningsRequestOverrides] = None,
        force: bool = False,
    ) -> OwnerEarningsResponse:
        overrides = overrides or OwnerEarningsRequestOverrides()
        method = "owner_earnings"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"
        sector = ctx.get("sector")

        decision = await self.guard.cached_or_recompute(
            company_id=company_id, method=method, force=force
        )

        if decision.should_recompute:
            logger.info(
                "[VALUATION][OE] recompute: company=%s symbol=%s reason=%s dep_ts=%s last_ts=%s",
                company_id, symbol, decision.reason,
                decision.latest_dependency_at, decision.last_valuation_at,
            )
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides
            )

        # ── Cached path ───────────────────────────────────────────────────────

        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info("[VALUATION][OE] cached path missing; recomputing for %s", symbol)
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides
            )

        valuation_payload = snap.get("valuation") or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload = snap.get("dataQuality") or {}
        last_computed = (
            (dq_payload.get("freshnessDays") or {}).get("lastComputedAt")
            or snap.get("lastComputedAt")
        )

        # Read-time price only
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps = _safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps and intrinsic_ps > 0:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        valuation_payload["currentPrice"] = current_price
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

    async def _compute_and_persist(
        self,
        symbol: str,
        company_id: int,
        currency: str,
        sector: Optional[str],
        user_id: Optional[int],
        overrides: OwnerEarningsRequestOverrides,
    ) -> OwnerEarningsResponse:

        defaults = await self.repo.get_method_params(company_id, method="owner_earnings")
        flags: List[DiagnosticFlag] = []
        input_decisions: Dict[str, Any] = {"oe": {}}
        fallbacks_used = False

        current_price = await self.repo.get_current_market_price(company_id)

        # ── Forecast years ────────────────────────────────────────────────────

        n_default = int(defaults.get("forecast_years_default", 5))
        if overrides.forecastYears is not None:
            n = int(overrides.forecastYears)
            input_decisions["oe"]["forecastYears"] = {"source": "override.forecastYears", "value": n}
        else:
            n = n_default
            input_decisions["oe"]["forecastYears"] = {"source": "defaults.forecast_years_default", "value": n}
            fallbacks_used = True
        n = int(_clamp(float(n), 1, 20))

        # ── Maintenance capex ratio ───────────────────────────────────────────

        mc_ratio: float
        if overrides.maintenanceCapexRatio is not None:
            mc_ratio = float(overrides.maintenanceCapexRatio)
            input_decisions["oe"]["maintenanceCapexRatio"] = {"source": "override", "value": mc_ratio}
        else:
            mc_ratio = float(defaults.get("maintenance_capex_ratio", 1.0))
            input_decisions["oe"]["maintenanceCapexRatio"] = {"source": "defaults", "value": mc_ratio}
            fallbacks_used = True

        # ── Include working capital change ────────────────────────────────────

        include_wc: bool
        if overrides.includeWorkingCapitalChange is not None:
            include_wc = bool(overrides.includeWorkingCapitalChange)
        else:
            include_wc = bool(defaults.get("include_working_capital_change", True))

        # ── Resolve base OE ───────────────────────────────────────────────────

        base_oe_data = await self._resolve_base_oe(company_id, mc_ratio, include_wc)
        base_oe = _safe_float(base_oe_data.get("value"))
        base_oe_fy = base_oe_data.get("evidence", {}).get("asOfFiscalYear")
        input_decisions["oe"]["baseOe"] = base_oe_data.get("evidence")

        net_income_used = base_oe_data.get("evidence", {}).get("netIncome")
        da_used = base_oe_data.get("evidence", {}).get("da")
        capex_used = base_oe_data.get("evidence", {}).get("capex")
        wc_change_used = base_oe_data.get("evidence", {}).get("wcChange")

        if base_oe is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-BASE",
                severity="critical",
                message="Could not resolve base Owner Earnings (Net Income unavailable).",
                evidence=base_oe_data.get("evidence"),
                recommendation="Ensure income_statements.net_income and cash_flow_statements are populated.",
            ))
        elif base_oe <= 0:
            flags.append(DiagnosticFlag(
                code="OE-NEG-BASE",
                severity="medium",
                message=f"Base Owner Earnings is {base_oe:,.0f} (non-positive). Growth projections carry higher risk.",
                evidence={"baseOe": base_oe},
                recommendation="Apply conservative growth and a wide discount rate to compensate.",
            ))

        # ── OE growth rate ────────────────────────────────────────────────────

        g_oe: Optional[float]
        if overrides.oeGrowthRate is not None:
            g_oe_raw = float(overrides.oeGrowthRate)
            g_oe_source = "override.oeGrowthRate"
        else:
            g_oe_raw = _safe_float(defaults.get("oe_growth_rate"))
            g_oe_source = "defaults.oe_growth_rate"
            if g_oe_raw is not None:
                fallbacks_used = True

        if base_oe is None or g_oe_raw is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-GROWTH",
                severity="critical",
                message="Cannot build OE forecast: base OE or growth rate is missing.",
                evidence={"baseOe": base_oe, "oeGrowthRate": g_oe_raw},
                recommendation="Provide oeGrowthRate override or set oe_growth_rate in method defaults.",
            ))
            return await self._build_empty_response(
                symbol, company_id, currency, sector, n, flags, input_decisions, current_price, user_id=user_id,
            )

        g_oe_frac = _pct_or_frac_to_frac(float(g_oe_raw))
        g_oe_floor = float(defaults.get("oe_growth_floor", 0.00))
        g_oe_cap = float(defaults.get("oe_growth_cap", 0.15))
        g_oe_clamped = _clamp(g_oe_frac, g_oe_floor, g_oe_cap)
        input_decisions["oe"]["oeGrowthRate"] = {
            "source": g_oe_source, "valueRaw": g_oe_raw,
            "valueFrac": g_oe_frac, "valueFinal": g_oe_clamped,
            "floor": g_oe_floor, "cap": g_oe_cap,
            "clamped": g_oe_frac != g_oe_clamped,
        }
        if g_oe_frac != g_oe_clamped:
            flags.append(DiagnosticFlag(
                code="OE-GROWTH-CLAMP", severity="info",
                message="OE growth rate was clamped to safety bounds.",
                evidence=input_decisions["oe"]["oeGrowthRate"],
            ))
        g_oe = g_oe_clamped

        # ── Forecast OE series ────────────────────────────────────────────────

        forecast_oe = [float(base_oe) * ((1.0 + g_oe) ** t) for t in range(1, n + 1)]

        # ── Discount rate ─────────────────────────────────────────────────────

        if overrides.discountRate is not None:
            r_raw = float(overrides.discountRate)
            r_source = "override.discountRate"
        else:
            r_raw = _safe_float(defaults.get("discount_rate_default"))
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
            r_frac = _pct_or_frac_to_frac(float(r_raw))
            r_floor = float(defaults.get("discount_rate_floor", 0.07))
            r_cap = float(defaults.get("discount_rate_cap", 0.15))
            r = _clamp(r_frac, r_floor, r_cap)
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

        # ── Discount OE stream ────────────────────────────────────────────────

        pv_oe: List[float] = []
        discount_factors: List[float] = []
        total_pv_oe = 0.0

        if r > 0:
            for t, cf in enumerate(forecast_oe, start=1):
                df = 1.0 / ((1.0 + r) ** t)
                pv = cf * df
                discount_factors.append(float(df))
                pv_oe.append(float(pv))
                total_pv_oe += float(pv)
        else:
            pv_oe = [0.0] * n
            discount_factors = [0.0] * n
            flags.append(DiagnosticFlag(
                code="OE-NO-DISCOUNT", severity="high",
                message="Discount rate is 0 or unavailable; cannot compute present values.",
            ))

        # ── Terminal value (perpetuity growth) ────────────────────────────────

        tv: Optional[float] = None
        pv_tv: Optional[float] = None
        oe_n_plus_1: Optional[float] = None
        terminal_g_used: Optional[float] = None

        if r > 0:
            if overrides.terminalGrowthRate is not None:
                tg_raw = float(overrides.terminalGrowthRate)
                tg_source = "override.terminalGrowthRate"
            else:
                tg_raw = _safe_float(defaults.get("terminal_growth_default"))
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
                tg = _pct_or_frac_to_frac(float(tg_raw))
                terminal_g_used = tg
                if tg >= r:
                    flags.append(DiagnosticFlag(
                        code="OE-G-GE-R", severity="critical",
                        message="Terminal growth rate (g) must be less than discount rate (r) for perpetuity formula.",
                        evidence={"g": tg, "r": r, "source": tg_source},
                        recommendation="Lower g or raise r.",
                    ))
                else:
                    oe_n = float(forecast_oe[-1])
                    oe_n_plus_1 = oe_n * (1.0 + tg)
                    tv = oe_n_plus_1 / (r - tg)
                    pv_tv = tv / ((1.0 + r) ** n)
                input_decisions["oe"]["terminal"] = {
                    "method": "perpetuity_growth", "source": tg_source,
                    "gRaw": tg_raw, "gFinal": tg, "r": r,
                    "oeN": float(forecast_oe[-1]) if forecast_oe else None,
                    "oeNPlus1": float(oe_n_plus_1) if oe_n_plus_1 is not None else None,
                    "valid": (tg < r if tg_raw is not None else False),
                }

        # ── Enterprise → Equity → Per-share bridge ───────────────────────────

        enterprise_value: Optional[float] = None
        if pv_tv is not None:
            enterprise_value = float(total_pv_oe) + float(pv_tv)
        else:
            enterprise_value = float(total_pv_oe) if total_pv_oe else None

        # Net debt
        net_debt = overrides.netDebt
        net_debt_source = "override.netDebt" if net_debt is not None else None
        if net_debt is None:
            bs = await self.repo.get_balance_sheet_latest(company_id)
            debt = _safe_float(bs.get("total_debt")) if bs else None
            cash = _safe_float(bs.get("cash_and_cash_equivalents")) if bs else None
            if debt is not None and cash is not None:
                net_debt = float(debt) - float(cash)
                net_debt_source = "balance_sheets.total_debt - cash_and_cash_equivalents"
                fallbacks_used = True
        input_decisions["oe"]["netDebt"] = {"source": net_debt_source, "value": net_debt}

        equity_value: Optional[float] = None
        if enterprise_value is not None and net_debt is not None:
            equity_value = float(enterprise_value) - float(net_debt)

        # Shares
        shares = overrides.sharesOutstanding
        shares_source = "override.sharesOutstanding" if shares is not None else None
        if shares is None:
            rows = await self.repo.get_shares_history(company_id)
            if rows:
                last = rows[-1]
                sh = _safe_float(last.get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares = float(sh)
                    shares_source = "income_statements.shares_outstanding_diluted(latest)"
                    fallbacks_used = True
        if shares is None:
            summary = await self.repo.get_company_summary_latest(company_id)
            if summary:
                sh = _safe_float(summary.get("shares_outstanding"))
                if sh and sh > 0:
                    shares = float(sh)
                    shares_source = "company_summary.shares_outstanding"
                    fallbacks_used = True
        input_decisions["oe"]["sharesOutstanding"] = {"source": shares_source, "value": shares}

        intrinsic_ps: Optional[float] = None
        if equity_value is not None and shares is not None and float(shares) > 0:
            intrinsic_ps = float(equity_value) / float(shares)

        upside: Optional[float] = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps and intrinsic_ps > 0:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        # ── Sensitivity grid (discount_rate × terminal_growth_rate) ──────────

        sensitivity_grid: Optional[OeSensitivityGrid] = None
        if (
            r > 0 and terminal_g_used is not None and tg_raw is not None
            and intrinsic_ps is not None and equity_value is not None
            and shares is not None and float(shares) > 0
        ):
            cfg_r = defaults.get("sensitivity_discount_rates")
            cfg_g = defaults.get("sensitivity_terminal_growth_rates")

            def _to_float_list(x: Any) -> Optional[List[float]]:
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
                    pv_sum = sum(float(cf) / ((1.0 + r_s) ** t)
                                 for t, cf in enumerate(forecast_oe, start=1))
                    oe_np1 = float(forecast_oe[-1]) * (1.0 + g_s)
                    tv_s = oe_np1 / (r_s - g_s)
                    pv_tv_s = tv_s / ((1.0 + r_s) ** n)
                    ev_s = pv_sum + pv_tv_s
                    eq_s = ev_s - float(net_debt) if net_debt is not None else None
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

        # ── Suitability scorecard ─────────────────────────────────────────────

        oe_score, oe_category, oe_flags, oe_evidence = await evaluate_owner_earnings_suitability(
            repo=self.repo, company_id=company_id, sector=sector,
        )
        flags.extend(oe_flags)

        # ── AI suitability summary ────────────────────────────────────────────

        suitability_summary = await generate_suitability_summary(
            symbol=symbol,
            method="owner_earnings",
            score=int(oe_score),
            category=oe_category,
            flags=[f.dict() for f in flags],
            evidence=oe_evidence,
            valuation_inputs={
                "currency": currency,
                "baseOe": float(base_oe) if base_oe is not None else None,
                "forecastYears": int(n),
                "discountRateUsed": float(r) if r else None,
                "oeGrowthRateUsed": float(g_oe) if g_oe is not None else None,
                "terminalGrowthRateUsed": float(terminal_g_used) if terminal_g_used is not None else None,
                "enterpriseValue": float(enterprise_value) if enterprise_value is not None else None,
                "intrinsicValuePerShare": float(intrinsic_ps) if intrinsic_ps is not None else None,
                "currentPrice": current_price,
                "upsideDownsidePct": upside,
            },
            input_decisions=input_decisions,
        )

        if intrinsic_ps is None:
            flags.append(DiagnosticFlag(
                code="OE-NO-PER-SHARE", severity="high",
                message="OE computed but intrinsic value per share unavailable (missing shares or equity bridge).",
                evidence={"enterpriseValue": enterprise_value, "equityValue": equity_value, "shares": shares},
                recommendation="Provide sharesOutstanding and netDebt overrides, or ensure financial tables are populated.",
            ))

        # ── Build valuation object ────────────────────────────────────────────

        valuation = OwnerEarningsValuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            forecastYears=int(n),
            discountRateUsed=float(r) if r else 0.0,
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
            currentPrice=current_price,
            upsideDownsidePct=upside,
            sensitivityScenarios=sensitivity_grid,
        )

        # Persist early-abort run so the frontend shows an error state
        # instead of a perpetual loading spinner.
        now_iso = datetime.utcnow().isoformat() + "Z"
        try:
            await self.repo.insert_valuation_run(
                company_id=company_id,
                method="owner_earnings",
                run={
                    "run_by_user_id": user_id,
                    "input_snapshot": input_decisions,
                    "assumption_snapshot": {},
                    "output_snapshot": {
                        "valuation": valuation.dict(),
                        "applicability": {
                            "score": int(oe_score),
                            "category": oe_category,
                            "flags": [f.dict() for f in all_flags],
                            "suitabilitySummary": suitability_summary,
                        },
                        "dataQuality": {
                            "freshnessDays": {"lastComputedAt": now_iso},
                            "fallbacksUsed": True,
                            "inputDecisions": input_decisions,
                        },
                        "earlyAbort": True,
                        "lastComputedAt": now_iso,
                    },
                    "data_version_tag": None,
                    "notes": "early_abort",
                },
            )
        except Exception as e:
            logger.warning("[OE][%s] Failed to persist early-abort valuation run: %s", symbol, e)

        # ── Audit run (append-only) ───────────────────────────────────────────

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
            company_id=company_id,
            method="owner_earnings",
            run={
                "run_by_user_id": user_id,
                "input_snapshot": {"overrides": overrides.dict()},
                "assumption_snapshot": defaults,
                "output_snapshot": output_snapshot,
                "data_version_tag": None,
                "notes": overrides.notes,
            },
        )

        return OwnerEarningsResponse(
            valuation=valuation,
            applicability=Applicability(
                score=oe_score,
                category=oe_category,
                flags=flags,
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
        self,
        symbol: str,
        company_id: int,
        currency: str,
        sector: Optional[str],
        n: int,
        flags: list,
        input_decisions: dict,
        current_price,
        user_id: Optional[int] = None,
    ) -> "OwnerEarningsResponse":
        """
        Early-abort response when required inputs are irresolvably missing.
        FIX: Now async — runs suitability scorecard + AI summary so the
        frontend AI panel renders even for uncomputable stocks.
        """
        # Run suitability scorecard (provides score/category/flags for AI)
        try:
            oe_score, oe_category, oe_flags, oe_evidence = await evaluate_owner_earnings_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
            )
        except Exception:
            oe_score, oe_category, oe_flags, oe_evidence = 0, "Poor", [], {}

        all_flags = flags + oe_flags

        # Generate AI summary
        suitability_summary = None
        try:
            suitability_summary = await generate_suitability_summary(
                symbol=symbol,
                method="owner_earnings",
                score=int(oe_score),
                category=oe_category,
                flags=[f.dict() for f in all_flags],
                evidence=oe_evidence,
                valuation_inputs={
                    "currency": currency,
                    "baseOe": None,
                    "forecastYears": int(n),
                    "currentPrice": current_price,
                    "note": "Early abort — required OE inputs unavailable.",
                },
                input_decisions=input_decisions,
            )
        except Exception:
            pass  # AI summary is non-critical; never break the response

        valuation = OwnerEarningsValuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            forecastYears=n,
            discountRateUsed=0.0,
            forecastOe=[0.0] * n,
            pvOe=[0.0] * n,
            totalPvOe=0.0,
            currentPrice=current_price,
        )
        return OwnerEarningsResponse(
            valuation=valuation,
            applicability=Applicability(
                score=int(oe_score),
                category=oe_category,
                flags=all_flags,
                suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={}, fallbacksUsed=True, inputDecisions=input_decisions,
            ),
        )

    async def _resolve_base_oe(
        self,
        company_id: int,
        maintenance_capex_ratio: float,
        include_wc: bool,
    ) -> Dict[str, Any]:
        """
        Resolve base Owner Earnings deterministically from financial statements.
        OE = Net Income + D&A − (Maintenance Capex) [± Working Capital Change]

        Returns { "value": Optional[float], "evidence": {...} }
        """
        # Use the OE-specific cash flow fetch that includes D&A and WC change
        cf: Optional[Dict[str, Any]] = None
        if hasattr(self.repo, "get_cash_flow_oe_inputs"):
            try:
                cf = await self.repo.get_cash_flow_oe_inputs(company_id)
            except Exception:
                cf = None

        is_row: Optional[Dict[str, Any]] = None
        try:
            is_row = await self.repo.get_income_statement_latest(company_id)
        except Exception:
            pass

        net_income = _safe_float(is_row.get("net_income_to_common") or is_row.get("net_income")) if is_row else None
        da = _safe_float(cf.get("depreciation_amortization")) if cf else None
        capex_raw = _safe_float(cf.get("capital_expenditures")) if cf else None
        wc_change = _safe_float(cf.get("change_in_working_capital")) if cf else None
        fiscal_year = (cf or {}).get("fiscal_year") or (is_row or {}).get("fiscal_year")

        value = _compute_oe(net_income, da, capex_raw, wc_change, maintenance_capex_ratio, include_wc)

        return {
            "value": value,
            "evidence": {
                "source": "income_statements + cash_flow_statements (latest annual)",
                "netIncome": net_income,
                "da": da,
                "capex": capex_raw,
                "wcChange": wc_change if include_wc else None,
                "maintenanceCapexRatio": maintenance_capex_ratio,
                "includeWcChange": include_wc,
                "computedOe": value,
                "asOfFiscalYear": fiscal_year,
            },
        }