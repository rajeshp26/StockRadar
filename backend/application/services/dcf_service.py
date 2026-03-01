from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from shared.finance_math import compute_fcf   # shared sign-aware formula
from application.services.recompute_guard import RecomputeGuard
from domain.models.valuation_dcf import DcfRequestOverrides, DcfResponse, DcfValuation, TerminalMethod, DcfSensitivityGrid
from domain.models.valuation_rule1 import Applicability, DataQuality, DiagnosticFlag
from infrastructure.repositories.valuation_repository import ValuationRepository
from application.services.dcf_suitability import evaluate_dcf_suitability

logger = logging.getLogger(__name__)

def _assert_length_invariant(
    name: str,
    arr: list,
    expected_len: int,
    flags: list,
):
    if len(arr) != expected_len:
        flags.append(DiagnosticFlag(
            code="DCF-LENGTH-MISMATCH",
            severity="critical",
            message=f"{name} length ({len(arr)}) does not match forecastYears ({expected_len}).",
            evidence={"field": name, "length": len(arr), "forecastYears": expected_len},
            recommendation="This indicates an internal computation error. Re-run valuation or inspect recent changes.",
        ))
        return False
    return True
    
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _pct_or_frac_to_frac(x: float) -> float:
    # If user stores 5 for 5%, convert to 0.05. If already 0.05, keep.
    return x / 100.0 if x > 1.0 else x


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if f != f:  # NaN
            return None
        return f
    except Exception:
        return None


class DcfService:
    """
    Discounted Cash Flow valuation service with cached-vs-recompute.

    Terminal value methods supported:
      - perpetuity_growth
      - exit_multiple (requires explicit terminal EBITDA per "no assumptions")

    Price policy:
      - DCF intrinsic math is audited and persisted.
      - Current price & upside are computed at read-time only.
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo = repo
        self.guard = guard

    async def compute_dcf_if_stale(
        self,
        symbol: str,
        user_id: Optional[int],
        overrides: Optional[DcfRequestOverrides] = None,
        force: bool = False,
    ) -> DcfResponse:
        overrides = overrides or DcfRequestOverrides()
        method = "dcf"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"
        sector = ctx.get("sector")

        decision = await self.guard.cached_or_recompute(company_id=company_id, method=method, force=force)

        if decision.should_recompute:
            logger.info(
                "[VALUATION][DCF] recompute: company=%s symbol=%s reason=%s dep_ts=%s last_ts=%s",
                company_id,
                symbol,
                decision.reason,
                decision.latest_dependency_at,
                decision.last_valuation_at,
            )
            return await self._compute_and_persist(symbol, company_id, currency, sector, user_id, overrides)

        # Cached path: hydrate last audited run for this method
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info("[VALUATION][DCF] cached path missing audited run; recomputing for %s", symbol)
            return await self._compute_and_persist(symbol, company_id, currency, sector, user_id, overrides)

        valuation_payload = snap.get("valuation") or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload = snap.get("dataQuality") or {}
        last_computed = (dq_payload.get("freshnessDays") or {}).get("lastComputedAt") or snap.get("lastComputedAt")

        # Read-time price only
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps = _safe_float(valuation_payload.get("intrinsicValuePerShare"))

        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps is not None and intrinsic_ps > 0:
            upside = (float(intrinsic_ps) - float(current_price)) / float(current_price)

        valuation_payload["currentPrice"] = current_price
        valuation_payload["upsideDownsidePct"] = upside

        # If no audited applicability exists (defensive), do NOT fabricate
        if not applicability_payload:
            applicability_payload = {
                "score": 0,
                "category": "Caution",
                "flags": [
                    {
                        "code": "DCF-NO-AUDIT",
                        "severity": "info",
                        "message": "No prior DCF valuation run found; suitability scorecard not available on cached path.",
                        "recommendation": "Run Recompute once to generate an audited scorecard.",
                    }
                ],
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

    async def _compute_and_persist(
        self,
        symbol: str,
        company_id: int,
        currency: str,
        sector: Optional[str],
        user_id: Optional[int],
        overrides: DcfRequestOverrides,
    ) -> DcfResponse:
        defaults = await self.repo.get_method_params(company_id, method="dcf")

        flags: List[DiagnosticFlag] = []
        input_decisions: Dict[str, Any] = {"dcf": {}}
        fallbacks_used = False

        # Read-time price (captured for run snapshot, but not a recompute dependency)
        current_price = await self.repo.get_current_market_price(company_id)

        # ---------------------------
        # Resolve forecast years / forecast FCF
        # ---------------------------
        n_default = int(defaults.get("forecast_years_default", 5))
        if overrides.forecastYears is not None:
            n = int(overrides.forecastYears)
            input_decisions["dcf"]["forecastYears"] = {"source": "override.forecastYears", "value": n}
        else:
            n = n_default
            input_decisions["dcf"]["forecastYears"] = {"source": "defaults.forecast_years_default", "value": n}
            fallbacks_used = True

        n = int(_clamp(float(n), 1, 20))

        series: Optional[List[float]] = overrides.forecastFcf
        base_fcf_value: Optional[float] = None
        base_fcf_fy: Optional[int] = None

        if series is not None:
            # Enforce horizon consistency (avoid silent truncation/padding)
            if len(series) != n:
                n = len(series)
                input_decisions["dcf"]["forecastYears"] = {"source": "override.forecastFcf.length", "value": n}
            input_decisions["dcf"]["forecastFcf"] = {"source": "override.forecastFcf", "years": n}
        else:
            # Deterministic base FCF from latest annual cash flow:
            base_cf = await self._resolve_base_fcf(company_id)
            input_decisions["dcf"]["baseFcf"] = base_cf.get("evidence")

            base_fcf_value = _safe_float(base_cf.get("value"))
            base_fcf_fy = base_cf.get("evidence", {}).get("asOfFiscalYear")

            # IMPORTANT: We do not invent a forecast.
            # We only derive a forecast if an explicit FCF growth assumption is provided.
            #   - overrides.fcfGrowthRate OR defaults.fcf_growth_rate
            fcf_growth = None

            if defaults.get("fcf_growth_rate") is not None and overrides.fcfGrowthRate is None:
                # Use explicit DCF default growth rate if configured
                fcf_growth = float(defaults.get("fcf_growth_rate"))
                input_decisions["dcf"]["fcfGrowthRate"] = {"source": "defaults.fcf_growth_rate", "valueRaw": fcf_growth}
                fallbacks_used = True
            elif overrides.fcfGrowthRate is not None:
                # Clear semantics: fcfGrowthRate grows base FCF
                fcf_growth = float(overrides.fcfGrowthRate)
                input_decisions["dcf"]["fcfGrowthRate"] = {"source": "override.fcfGrowthRate", "valueRaw": fcf_growth}

            if base_fcf_value is None or fcf_growth is None:
                flags.append(DiagnosticFlag(
                    code="DCF-NO-FORECAST",
                    severity="critical",
                    message="No explicit FCF forecast provided and insufficient assumptions to derive a forecast.",
                    evidence={"hasForecastFcf": False, "baseFcf": base_fcf_value, "fcfGrowthRate": fcf_growth},
                    recommendation="Provide forecastFcf[] or configure explicit defaults/overrides for DCF forecasting inputs.",
                ))

                valuation = DcfValuation(
                    symbol=symbol.upper(),
                    companyId=company_id,
                    currency=currency,
                    terminalMethod=(overrides.terminalMethod or defaults.get("terminal_method_default") or "perpetuity_growth"),
                    forecastYears=n,
                    forecastFcf=[0.0 for _ in range(n)],
                    pvFcf=[0.0 for _ in range(n)],
                    totalPvFcf=0.0,
                    discountFactors=[0.0 for _ in range(n)],
                    waccUsed=0.0,
                    terminalValue=None,
                    pvTerminalValue=None,
                    terminalGrowthRateUsed=None,
                    cashFlowNPlus1=None,
                    enterpriseValue=None,
                    netDebtUsed=None,
                    equityValue=None,
                    sharesOutstanding=None,
                    intrinsicValuePerShare=None,
                    baseFcf=base_fcf_value,
                    baseFcfFiscalYear=base_fcf_fy if isinstance(base_fcf_fy, int) else None,
                    currentPrice=current_price,
                    upsideDownsidePct=None,
                    sensitivityScenarios=None,
                )
                return DcfResponse(
                    valuation=valuation,
                    applicability=Applicability(score=0, category="Poor", flags=flags),
                    dataQuality=DataQuality(
                        freshnessDays={},
                        fallbacksUsed=True,
                        inputDecisions=input_decisions,
                    ),
                )

            g_fcf = _pct_or_frac_to_frac(float(fcf_growth))
            g_fcf = _clamp(
                g_fcf,
                float(defaults.get("fcf_growth_floor", 0.00)),
                float(defaults.get("fcf_growth_cap", 0.20)),
            )
            input_decisions["dcf"]["fcfGrowthRate"] = {
                **(input_decisions["dcf"].get("fcfGrowthRate") or {}),
                "valueFinal": g_fcf,
            }
            if float(_pct_or_frac_to_frac(float(fcf_growth))) != float(g_fcf):
                flags.append(DiagnosticFlag(
                    code="DCF-GROWTH-CLAMP",
                    severity="info",
                    message="FCF growth rate was clamped to safety bounds.",
                    evidence=input_decisions["dcf"]["fcfGrowthRate"],
                ))

            series = [float(base_fcf_value) * ((1.0 + g_fcf) ** t) for t in range(1, n + 1)]
            input_decisions["dcf"]["forecastFcf"] = {"source": "derived_from_baseFcf_and_growth", "years": n}
            fallbacks_used = True

        assert series is not None
        forecast_fcf = [float(x) for x in series]

        # ---------------------------
        # Resolve terminal method early (needed for invariant-failure return path)
        # ---------------------------
        terminal_method: TerminalMethod = (
            overrides.terminalMethod
            or defaults.get("terminal_method_default")
            or "perpetuity_growth"
        )

        # ---------------------------
        # Resolve WACC
        # ---------------------------
        if overrides.wacc is not None:
            wacc_raw = float(overrides.wacc)
            wacc_source = "override.wacc"
        else:
            wacc_raw = _safe_float(defaults.get("wacc_default"))
            wacc_source = "defaults.wacc_default"
            fallbacks_used = True

        if wacc_raw is None:
            flags.append(DiagnosticFlag(
                code="DCF-NO-WACC",
                severity="critical",
                message="Discount rate (WACC) is missing.",
                recommendation="Provide wacc override or configure dcf method defaults/overrides for wacc.",
            ))
            wacc = 0.0
        else:
            wacc = _pct_or_frac_to_frac(float(wacc_raw))
            wacc_floor = float(defaults.get("wacc_floor", 0.06))
            wacc_cap = float(defaults.get("wacc_cap", 0.18))
            wacc_final = _clamp(wacc, wacc_floor, wacc_cap)

            input_decisions["dcf"]["wacc"] = {
                "source": wacc_source,
                "valueRaw": float(wacc_raw),
                "valueFinal": float(wacc_final),
                "waccFloor": wacc_floor,
                "waccCap": wacc_cap,
                "clamped": float(wacc) != float(wacc_final),
            }
            if float(wacc) != float(wacc_final):
                flags.append(DiagnosticFlag(
                    code="DCF-WACC-CLAMP",
                    severity="info",
                    message="WACC was clamped to safety bounds.",
                    evidence=input_decisions["dcf"]["wacc"],
                ))
            wacc = float(wacc_final)

        # ---------------------------
        # Discount forecast cash flows (and compute discount factors for transparency)
        # ---------------------------
        pv_fcf: List[float] = []
        discount_factors: List[float] = []
        total_pv = 0.0

        if wacc > 0:
            for t, cf in enumerate(forecast_fcf, start=1):
                df = 1.0 / ((1.0 + wacc) ** t)
                pv = cf * df
                discount_factors.append(float(df))
                pv_fcf.append(float(pv))
                total_pv += float(pv)
        else:
            pv_fcf = [0.0 for _ in range(n)]
            discount_factors = [0.0 for _ in range(n)]
            total_pv = 0.0
            flags.append(DiagnosticFlag(
                code="DCF-NO-DISCOUNT",
                severity="high",
                message="DCF cannot compute present values because WACC is not available/valid.",
            ))

        # ---------------------------
        # Invariants (Priority 6)
        # ---------------------------
        ok = True
        ok &= _assert_length_invariant("forecastFcf", forecast_fcf, n, flags)
        ok &= _assert_length_invariant("pvFcf", pv_fcf, n, flags)
        if discount_factors:
            ok &= _assert_length_invariant("discountFactors", discount_factors, n, flags)

        if not ok:
            # Abort valuation construction but return diagnostics + data quality
            valuation = DcfValuation(
                symbol=symbol.upper(),
                companyId=company_id,
                currency=currency,
                terminalMethod=terminal_method,
                forecastYears=n,
                forecastFcf=forecast_fcf,
                pvFcf=pv_fcf,
                totalPvFcf=float(total_pv),
                discountFactors=discount_factors,
                waccUsed=float(wacc) if wacc else 0.0,
            )

            return DcfResponse(
                valuation=valuation,
                applicability=Applicability(
                    score=0,
                    category="Poor",
                    flags=flags,
                ),
                dataQuality=DataQuality(
                    freshnessDays={},
                    fallbacksUsed=True,
                    inputDecisions=input_decisions,
                ),
            )

        # ---------------------------
        # Terminal value (two methods)
        # ---------------------------


        tv = None
        pv_tv = None
        terminal_g_used: Optional[float] = None
        cf_n_plus_1: Optional[float] = None

        if wacc > 0:
            if terminal_method == "perpetuity_growth":
                if overrides.terminalGrowthRate is not None:
                    g_raw = float(overrides.terminalGrowthRate)
                    g_source = "override.terminalGrowthRate"
                else:
                    g_raw = _safe_float(defaults.get("terminal_growth_default"))
                    g_source = "defaults.terminal_growth_default"
                    if g_raw is not None:
                        fallbacks_used = True

                if g_raw is None:
                    flags.append(DiagnosticFlag(
                        code="DCF-NO-TERM-G",
                        severity="critical",
                        message="Terminal growth rate (g) is missing for perpetuity growth terminal value.",
                        recommendation="Provide terminalGrowthRate override or set terminal_growth_default in method defaults.",
                    ))
                else:
                    g = _pct_or_frac_to_frac(float(g_raw))
                    terminal_g_used = g

                    if g >= wacc:
                        flags.append(DiagnosticFlag(
                            code="DCF-GE-WACC",
                            severity="critical",
                            message="Terminal growth rate (g) must be less than WACC for perpetuity terminal value.",
                            evidence={"g": g, "wacc": wacc, "source": g_source},
                            recommendation="Lower g or raise WACC; consider Exit Multiple method if appropriate.",
                        ))
                    else:
                        cf_n = float(forecast_fcf[-1])
                        cf_n_plus_1 = cf_n * (1.0 + g)
                        tv = cf_n_plus_1 / (wacc - g)
                        pv_tv = tv / ((1.0 + wacc) ** n)

                    input_decisions["dcf"]["terminal"] = {
                        "method": "perpetuity_growth",
                        "source": g_source,
                        "gRaw": float(g_raw),
                        "gFinal": float(g),
                        "wacc": float(wacc),
                        "cfN": float(forecast_fcf[-1]) if forecast_fcf else None,
                        "cfNPlus1": float(cf_n_plus_1) if cf_n_plus_1 is not None else None,
                        "valid": (g < wacc),
                    }

            elif terminal_method == "exit_multiple":
                # Option A: deterministic only (no assumptions): require terminal EBITDA input
                if overrides.exitMultiple is not None:
                    mult = float(overrides.exitMultiple)
                    mult_source = "override.exitMultiple"
                else:
                    mult = _safe_float(defaults.get("exit_multiple_default")) or 0.0
                    mult_source = "defaults.exit_multiple_default"
                    if mult:
                        fallbacks_used = True

                metric = overrides.terminalMetric or defaults.get("terminal_metric_default") or "ebitda"
                ebitda_terminal = overrides.terminalEbitda

                if mult <= 0:
                    flags.append(DiagnosticFlag(
                        code="DCF-NO-EXIT-MULT",
                        severity="critical",
                        message="Exit multiple is missing/invalid for Exit Multiple terminal value.",
                        evidence={"exitMultiple": mult, "source": mult_source},
                        recommendation="Provide exitMultiple override or set exit_multiple_default in method defaults.",
                    ))
                elif ebitda_terminal is None:
                    flags.append(DiagnosticFlag(
                        code="DCF-NO-TERM-EBITDA",
                        severity="critical",
                        message="Terminal EBITDA is required to compute Exit Multiple terminal value (no assumptions).",
                        evidence={"terminalMetric": metric, "exitMultiple": mult, "terminalEbitda": None},
                        recommendation="Provide terminalEbitda (absolute) in overrides (or implement a deterministic derivation path later).",
                    ))
                else:
                    tv = float(ebitda_terminal) * float(mult)
                    pv_tv = tv / ((1.0 + wacc) ** n)

                input_decisions["dcf"]["terminal"] = {
                    "method": "exit_multiple",
                    "exitMultiple": float(mult) if mult else None,
                    "exitMultipleSource": mult_source,
                    "terminalMetric": metric,
                    "terminalEbitda": float(ebitda_terminal) if ebitda_terminal is not None else None,
                    "hasTerminalEbitda": ebitda_terminal is not None,
                }
                fallbacks_used = fallbacks_used or (mult_source.startswith("defaults"))

            else:
                flags.append(DiagnosticFlag(
                    code="DCF-TERM-METHOD",
                    severity="critical",
                    message="Invalid terminal value method.",
                    evidence={"terminalMethod": terminal_method},
                ))

        # ---------------------------
        # Enterprise -> Equity -> Per-share bridge
        # ---------------------------
        enterprise_value = None
        if tv is not None and pv_tv is not None:
            enterprise_value = float(total_pv) + float(pv_tv)
        else:
            # still show PV of explicit forecast even without TV
            enterprise_value = float(total_pv) if total_pv is not None else None

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

        input_decisions["dcf"]["netDebt"] = {"source": net_debt_source, "value": net_debt}

        equity_value = None
        if enterprise_value is not None and net_debt is not None:
            equity_value = float(enterprise_value) - float(net_debt)

        # Shares outstanding
        shares = overrides.sharesOutstanding
        shares_source = "override.sharesOutstanding" if shares is not None else None
        if shares is None:
            rows = await self.repo.get_shares_history(company_id)
            if rows:
                last = rows[-1]
                sh = _safe_float(last.get("shares_outstanding_diluted"))
                if sh is not None and sh > 0:
                    shares = float(sh)
                    shares_source = "statistics.shares_outstanding_diluted(latest)"
                    fallbacks_used = True

        input_decisions["dcf"]["sharesOutstanding"] = {"source": shares_source, "value": shares}

        intrinsic_ps = None
        if equity_value is not None and shares is not None and float(shares) > 0:
            intrinsic_ps = float(equity_value) / float(shares)

        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps is not None and intrinsic_ps > 0:
            upside = (float(intrinsic_ps) - float(current_price)) / float(current_price)

        # ---------------------------
        # Sensitivity Grid (Priority 5)
        # - Only for perpetuity_growth (r x g grid)
        # - Stored in valuation_runs.output_snapshot.sensitivity
        # - Returned to FE as valuation.sensitivityScenarios
        # ---------------------------
        sensitivity_grid: Optional[DcfSensitivityGrid] = None
        if (
            terminal_method == "perpetuity_growth"
            and wacc is not None
            and float(wacc) > 0
            and terminal_g_used is not None
            and intrinsic_ps is not None
            and equity_value is not None
            and shares is not None
            and float(shares) > 0
        ):
            # Preferred configuration from method defaults (fractions):
            cfg_r = defaults.get("sensitivity_discount_rates")
            cfg_g = defaults.get("sensitivity_terminal_growth_rates")

            def _to_float_list(x: Any) -> Optional[List[float]]:
                if not isinstance(x, list) or not x:
                    return None
                out: List[float] = []
                for v in x:
                    try:
                        out.append(float(v))
                    except Exception:
                        return None
                return out

            r_list = _to_float_list(cfg_r)
            g_list = _to_float_list(cfg_g)

            r_used = float(wacc)
            g_used = float(terminal_g_used)

            # If not configured, derive a local 3x3 grid around used r/g (deterministic, logged).
            derived = False
            if r_list is None:
                derived = True
                r_list = [max(0.01, r_used - 0.01), r_used, min(0.30, r_used + 0.01)]
            if g_list is None:
                derived = True
                # Ensure g stays below r for validity; cells with g>=r will be null.
                g_list = [max(0.00, g_used - 0.01), g_used, max(0.00, g_used + 0.01)]

            # Compute matrix [r][g]
            matrix: List[List[Optional[float]]] = []
            for r_sens in r_list:
                row: List[Optional[float]] = []
                for g_sens in g_list:
                    # Invalid terminal formula when g >= r
                    if g_sens >= r_sens:
                        row.append(None)
                        continue
                    # PV of forecast FCF using r_sens
                    pv_sum = 0.0
                    for t, cf in enumerate(forecast_fcf, start=1):
                        pv_sum += float(cf) / ((1.0 + float(r_sens)) ** t)

                    # Terminal value using CF(n+1) / (r - g)
                    cf_n = float(forecast_fcf[-1])
                    cf_np1 = cf_n * (1.0 + float(g_sens))
                    tv_sens = cf_np1 / (float(r_sens) - float(g_sens))
                    pv_tv_sens = tv_sens / ((1.0 + float(r_sens)) ** int(n))

                    ev_sens = pv_sum + pv_tv_sens
                    eq_sens = ev_sens - float(net_debt) if net_debt is not None else None
                    if eq_sens is None:
                        row.append(None)
                        continue
                    row.append(float(eq_sens) / float(shares))
                matrix.append(row)

            sensitivity_grid = DcfSensitivityGrid(
                discountRates=[float(x) for x in r_list],
                terminalGrowthRates=[float(x) for x in g_list],
                intrinsicValuePerShareMatrix=matrix,
                currency=currency,
            )

            input_decisions["dcf"]["sensitivity"] = {
                "enabled": True,
                "source": "defaults" if (not derived) else "derived_around_used_r_g",
                "discountRates": [float(x) for x in r_list],
                "terminalGrowthRates": [float(x) for x in g_list],
                "baseWaccUsed": r_used,
                "baseTerminalGrowthUsed": g_used,
            }
            if derived:
                fallbacks_used = True
        else:
            input_decisions["dcf"]["sensitivity"] = {
                "enabled": False,
                "reason": "Requires perpetuity_growth + valid r/g + computable per-share value",
            }

        # ---------------------------
        # Suitability scorecard (authoritative)
        # ---------------------------
        dcf_score, dcf_category, dcf_flags, dcf_evidence = await evaluate_dcf_suitability(
            repo=self.repo,
            company_id=company_id,
            sector=sector,
        )
        flags.extend(dcf_flags)

        if intrinsic_ps is None:
            flags.append(DiagnosticFlag(
                code="DCF-NO-PER-SHARE",
                severity="high",
                message="DCF computed but intrinsic value per share is not available (missing shares and/or equity bridge inputs).",
                evidence={"enterpriseValue": enterprise_value, "equityValue": equity_value, "sharesOutstanding": shares},
                recommendation="Provide sharesOutstanding and netDebt (or ensure financial tables contain the required fields).",
            ))

        valuation = DcfValuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            terminalMethod=terminal_method,
            forecastYears=int(n),
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

        # Optional persistence to dcf_valuations (analytics stream; not used for cached read)
        try:
            await self.repo.insert_dcf_valuation(
                payload={
                    "company_id": company_id,
                    "analysis_date": date.today().isoformat(),
                    "forecast_years": int(n),
                    "revenue_growth_rate": None,
                    "terminal_growth_rate": float(terminal_g_used) if terminal_g_used is not None else None,
                    "wacc_used": float(wacc) if wacc is not None else None,
                    "fcf_margin_assumption": _pct_or_frac_to_frac(float(overrides.fcfMarginAssumption)) if overrides.fcfMarginAssumption is not None else None,
                    "total_pv_fcf": float(total_pv),
                    "terminal_value": float(tv) if tv is not None else None,
                    "pv_terminal_value": float(pv_tv) if pv_tv is not None else None,
                    "enterprise_value_dcf": float(enterprise_value) if enterprise_value is not None else None,
                    "less_net_debt": float(net_debt) if net_debt is not None else None,
                    "equity_value": float(equity_value) if equity_value is not None else None,
                    "shares_outstanding": int(shares) if shares is not None else None,
                    "intrinsic_value_per_share": float(intrinsic_ps) if intrinsic_ps is not None else None,
                    "current_stock_price": current_price,
                    "upside_downside_pct": upside,
                    "analyst_name": overrides.analystName,
                    "sensitivity_scenarios": sensitivity_grid.dict() if sensitivity_grid is not None else None,
                    "notes": overrides.notes,
                }
            )
        except Exception:
            pass

        # Persist audited valuation_runs record (append-only)
        now_iso = datetime.utcnow().isoformat() + "Z"
        output_snapshot = {
            "valuation": valuation.dict(),
            "applicability": {
                "score": dcf_score,
                "category": dcf_category,
                "flags": [f.dict() for f in flags],
            },
            "dataQuality": {
                "freshnessDays": {"lastComputedAt": now_iso},
                "fallbacksUsed": bool(fallbacks_used),
                "inputDecisions": input_decisions,
            },
            # As per design: store sensitivity separately under output_snapshot.sensitivity
            "sensitivity": sensitivity_grid.dict() if sensitivity_grid is not None else None,
            "suitabilityEvidence": dcf_evidence,
            "lastComputedAt": now_iso,
        }

        await self.repo.insert_valuation_run(
            company_id=company_id,
            method="dcf",
            run={
                "run_by_user_id": user_id,
                "input_snapshot": {"overrides": overrides.dict()},
                "assumption_snapshot": defaults,
                "output_snapshot": output_snapshot,
                "data_version_tag": None,
                "notes": overrides.notes,
            },
        )

        return DcfResponse(
            valuation=valuation,
            applicability=Applicability(score=dcf_score, category=dcf_category, flags=flags),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": now_iso},
                fallbacksUsed=bool(fallbacks_used),
                inputDecisions=input_decisions,
            ),
        )

    async def _resolve_base_fcf(self, company_id: int) -> Dict[str, Any]:
        """
        Resolve a base FCF value deterministically from latest annual cash flow:
          FCF = cash_from_operating_activities - capital_expenditures

        Returns:
          {"value": Optional[float], "evidence": {...}}
        """
        cf = await self.repo.get_cash_flow_latest(company_id)
        ocf = _safe_float(cf.get("cash_from_operating_activities")) if cf else None
        capex = _safe_float(cf.get("capital_expenditures")) if cf else None

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

    