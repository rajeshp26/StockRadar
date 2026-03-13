# application/services/residual_income_service.py
from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from application.services.ai_service import generate_suitability_summary
from application.services.residual_income_suitability import evaluate_residual_income_suitability
from application.services.recompute_guard import RecomputeGuard
from domain.models.valuation_residual_income import (
    ResidualIncomeRequestOverrides,
    ResidualIncomeResponse,
    ResidualIncomeValuation,
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


# ── Service ───────────────────────────────────────────────────────────────────

class ResidualIncomeService:
    """
    Residual Income (Economic Profit / Ohlson Model) valuation service.

    Formula: Intrinsic/Share = BV₀/share + PV(RI stream) + PV(terminal RI)
    Where:   RI_t/share = EPS_t − k_e × BV_t/share   (simplified: projected at growth rate g)

    Architecture mirrors DdmService:
    - Cost of equity resolved via CAPM (rf + β × ERP), same _resolve_required_return pattern.
    - No equity bridge (model is equity-native; BV already denominated per share).
    - Early exit if shareholders' equity ≤ 0 (book value anchor is broken).
    - AI summary called AFTER intrinsic value and upside are fully resolved.
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo = repo
        self.guard = guard

    async def compute_residual_income_if_stale(
        self,
        symbol: str,
        user_id: Optional[int],
        overrides: Optional[ResidualIncomeRequestOverrides] = None,
        force: bool = False,
    ) -> ResidualIncomeResponse:
        overrides = overrides or ResidualIncomeRequestOverrides()
        method = "residual_income"

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
                "[VALUATION][RI] recompute: company=%s symbol=%s reason=%s dep_ts=%s last_ts=%s",
                company_id, symbol, decision.reason,
                decision.latest_dependency_at, decision.last_valuation_at,
            )
            return await self._compute_and_persist(
                symbol, company_id, currency, sector, user_id, overrides
            )

        # ── Cached path ───────────────────────────────────────────────────────

        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info("[VALUATION][RI] cached path missing; recomputing for %s", symbol)
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

        # Read-time price
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic_ps = _safe_float(valuation_payload.get("intrinsicValuePerShare"))
        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps is not None:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        valuation_payload["currentPrice"] = current_price
        valuation_payload["upsideDownsidePct"] = upside

        if not applicability_payload:
            applicability_payload = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "RI-NO-AUDIT", "severity": "info",
                    "message": "No prior RI valuation run found; suitability scorecard not available on cached path.",
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return ResidualIncomeResponse(
            valuation=ResidualIncomeValuation(**valuation_payload),
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
        overrides: ResidualIncomeRequestOverrides,
    ) -> ResidualIncomeResponse:

        defaults = await self.repo.get_method_params(company_id, method="residual_income")
        flags: List[DiagnosticFlag] = []
        input_decisions: Dict[str, Any] = {"ri": {}}
        fallbacks_used = False

        current_price = await self.repo.get_current_market_price(company_id)

        # ── Fetch base financial inputs ───────────────────────────────────────

        is_row = await self.repo.get_income_statement_latest(company_id)
        bs_row = await self.repo.get_balance_sheet_latest(company_id)

        # Book value per share and EPS require shares
        shares_history = await self.repo.get_shares_history(company_id)

        shares: Optional[float] = None

        if shares_history:
            # Use most recent year from income_statements
            shares = float(shares_history[-1]["shares_outstanding_diluted"])
            logger.debug("[RI][%s] shares from income_statements: %s", symbol, shares)
        else:
            # Fallback: company_summary.shares_outstanding (from defeatbeta/yfinance snapshot)
            logger.warning(
                "[RI][%s] shares_outstanding_diluted null in all income_statement rows, "
                "falling back to company_summary",
                symbol,
            )
            try:
                summary = await self.repo.get_company_summary_latest(company_id)
                if summary:
                    raw = summary.get("shares_outstanding") or summary.get("implied_shares_outstanding")
                    if raw:
                        shares = float(raw)
                        logger.info("[RI][%s] shares from company_summary: %s", symbol, shares)
            except Exception as e:
                logger.error("[RI][%s] company_summary fallback failed: %s", symbol, e)

        if shares is None or shares <= 0:
            logger.warning("[RI][%s] No shares available from any source, returning empty", symbol)
            n_default = int(defaults.get("forecast_years_default", 5))
            k_e_default = float(defaults.get("k_default", 0.10))
            ri_score, ri_category, ri_flags, ri_evidence = await evaluate_residual_income_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
                cost_of_equity=k_e_default,
            )
            abort_flags = flags + ri_flags
            abort_flags.append(DiagnosticFlag(
                code="RI-NO-SHARES", severity="critical",
                message="Shares outstanding unavailable from income_statements and company_summary.",
                recommendation="Trigger a financial data refresh for this company.",
            ))
            suitability_summary = None
            try:
                suitability_summary = await generate_suitability_summary(
                    symbol=symbol, method="residual_income",
                    score=int(ri_score), category=ri_category,
                    flags=[f.dict() for f in abort_flags], evidence=ri_evidence,
                    valuation_inputs={"currency": currency, "note": "Early abort — shares unavailable."},
                    input_decisions=input_decisions,
                )
            except Exception:
                pass
            now_iso = datetime.utcnow().isoformat() + "Z"
            abort_valuation = ResidualIncomeValuation(
                symbol=symbol.upper(), companyId=company_id, currency=currency,
                forecastYears=n_default, costOfEquityUsed=k_e_default,
                currentPrice=current_price,
            )
            try:
                await self.repo.insert_valuation_run(
                    company_id=company_id,
                    method="residual_income",
                    run={
                        "run_by_user_id": user_id,
                        "input_snapshot": input_decisions,
                        "assumption_snapshot": defaults,
                        "output_snapshot": {
                            "valuation": abort_valuation.dict(),
                            "applicability": {
                                "score": int(ri_score), "category": ri_category,
                                "flags": [f.dict() for f in abort_flags],
                                "suitabilitySummary": suitability_summary,
                            },
                            "dataQuality": {
                                "freshnessDays": {"lastComputedAt": now_iso},
                                "fallbacksUsed": True,
                                "inputDecisions": input_decisions,
                            },
                            "earlyAbort": True, "lastComputedAt": now_iso,
                        },
                        "data_version_tag": None,
                        "notes": "early_abort:shares_not_available",
                    },
                )
            except Exception as e:
                logger.warning("[RI][%s] Failed to persist early-abort run: %s", symbol, e)
            return ResidualIncomeResponse(
                valuation=abort_valuation,
                applicability=Applicability(
                    score=int(ri_score), category=ri_category, flags=abort_flags,
                    suitabilitySummary=suitability_summary,
                ),
                dataQuality=DataQuality(
                    freshnessDays={"lastComputedAt": now_iso},
                    fallbacksUsed=True, inputDecisions=input_decisions,
                ),
            )

        equity = _safe_float(bs_row.get("shareholders_equity")) if bs_row else None
        net_income = _safe_float(
            (is_row or {}).get("net_income_to_common") or (is_row or {}).get("net_income")
        )
        bv_fy = (bs_row or {}).get("fiscal_year")

        # ── Early exit: negative or missing equity ────────────────────────────

        if equity is None or (equity is not None and equity <= 0):
            flags.append(DiagnosticFlag(
                code="RI-NEG-EQUITY", severity="critical",
                message=f"Shareholders' equity is {'missing' if equity is None else f'{equity:,.0f} (non-positive)'}. "
                        "RI model requires positive book equity as the valuation anchor.",
                evidence={"equity": equity},
                recommendation="Avoid RI model for companies with negative or zero book equity. "
                               "Use DCF or Owner Earnings instead.",
            ))
            # Still run suitability to provide scorecard, then return
            k_e_default = float(defaults.get("k_default", 0.10))
            ri_score, ri_category, ri_flags, ri_evidence = await evaluate_residual_income_suitability(
                repo=self.repo, company_id=company_id, sector=sector,
                cost_of_equity=k_e_default,
            )
            flags.extend(ri_flags)
            suitability_summary = await generate_suitability_summary(
                symbol=symbol, method="residual_income",
                score=int(ri_score), category=ri_category,
                flags=[f.dict() for f in flags], evidence=ri_evidence,
                valuation_inputs={"currency": currency, "equity": equity},
                input_decisions={"ri": input_decisions},
            )
            return ResidualIncomeResponse(
                valuation=ResidualIncomeValuation(
                    symbol=symbol.upper(), companyId=company_id, currency=currency,
                    forecastYears=int(defaults.get("forecast_years_default", 5)),
                    costOfEquityUsed=k_e_default,
                    currentPrice=current_price,
                ),
                applicability=Applicability(
                    score=int(ri_score), category=ri_category, flags=flags,
                    suitabilitySummary=suitability_summary,
                ),
                dataQuality=DataQuality(
                    freshnessDays={}, fallbacksUsed=True,
                    inputDecisions={"ri": input_decisions},
                ),
            )

        # ── Forecast years ────────────────────────────────────────────────────

        n_default = int(defaults.get("forecast_years_default", 5))
        if overrides.forecastYears is not None:
            n = int(_clamp(float(overrides.forecastYears), 1, 20))
            input_decisions["ri"]["forecastYears"] = {"source": "override.forecastYears", "value": n}
        else:
            n = n_default
            input_decisions["ri"]["forecastYears"] = {"source": "defaults.forecast_years_default", "value": n}
            fallbacks_used = True

        # ── Cost of equity (CAPM; mirrors DDM _resolve_required_return) ───────

        k_e, k_evidence = await self._resolve_cost_of_equity(company_id, overrides, defaults)
        input_decisions["ri"]["costOfEquity"] = k_evidence
        if k_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="RI-K-CLAMP", severity="info",
                message="Cost of equity (k_e) was clamped to safety bounds.",
                evidence=k_evidence,
            ))

        # ── Base values ───────────────────────────────────────────────────────

        bv_per_share: Optional[float] = None
        if equity is not None and shares is not None and float(shares) > 0:
            bv_per_share = float(equity) / float(shares)

        eps0: Optional[float] = None
        if net_income is not None and shares is not None and float(shares) > 0:
            eps0 = float(net_income) / float(shares)

        roe0: Optional[float] = None
        if net_income is not None and equity is not None and float(equity) > 0:
            roe0 = float(net_income) / float(equity)

        # RI₀/share = EPS₀ − k_e × BV₀/share
        ri0_per_share: Optional[float] = None
        if eps0 is not None and bv_per_share is not None:
            ri0_per_share = eps0 - k_e * bv_per_share
        elif roe0 is not None and bv_per_share is not None:
            ri0_per_share = bv_per_share * (roe0 - k_e)

        input_decisions["ri"]["baseValues"] = {
            "equity": float(equity), "shares": shares,
            "netIncome": float(net_income) if net_income is not None else None,
            "bvPerShare": bv_per_share, "eps0": eps0, "roe0": roe0,
            "ri0PerShare": ri0_per_share, "costOfEquity": k_e,
        }

        if ri0_per_share is None:
            flags.append(DiagnosticFlag(
                code="RI-NO-BASE", severity="critical",
                message="Cannot compute base RI per share (missing EPS or book value per share).",
                evidence=input_decisions["ri"]["baseValues"],
                recommendation="Ensure income_statements and balance_sheets are populated.",
            ))

        # ── RI growth rate ────────────────────────────────────────────────────

        g_ri, g_evidence = await self._resolve_ri_growth(company_id, overrides, defaults, k_e)
        input_decisions["ri"]["riGrowthRate"] = g_evidence
        if g_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="RI-GROWTH-CLAMP", severity="info",
                message="RI growth rate was clamped to safety bounds.",
                evidence=g_evidence,
            ))

        # ── Terminal growth rate ──────────────────────────────────────────────

        tg_used: Optional[float] = None
        if overrides.terminalGrowthRate is not None:
            tg_raw = float(overrides.terminalGrowthRate)
            tg_source = "override.terminalGrowthRate"
        else:
            tg_raw = _safe_float(defaults.get("terminal_growth_default"))
            tg_source = "defaults.terminal_growth_default"
            if tg_raw is not None:
                fallbacks_used = True

        if tg_raw is not None:
            tg_used = _pct_or_frac_to_frac(float(tg_raw))

        input_decisions["ri"]["terminalGrowthRate"] = {"source": tg_source, "value": tg_used}

        # ── Forecast RI per share ─────────────────────────────────────────────

        forecast_ri: List[float] = []
        if ri0_per_share is not None:
            forecast_ri = [float(ri0_per_share) * ((1.0 + g_ri) ** t) for t in range(1, n + 1)]
        else:
            forecast_ri = [0.0] * n

        # ── Discount RI stream at k_e ─────────────────────────────────────────

        pv_ri: List[float] = []
        discount_factors: List[float] = []
        total_pv_ri = 0.0

        if k_e > 0:
            for t, ri_t in enumerate(forecast_ri, start=1):
                df = 1.0 / ((1.0 + k_e) ** t)
                pv = ri_t * df
                discount_factors.append(float(df))
                pv_ri.append(float(pv))
                total_pv_ri += float(pv)
        else:
            pv_ri = [0.0] * n
            discount_factors = [0.0] * n

        # ── Terminal RI value ─────────────────────────────────────────────────

        terminal_ri_ps: Optional[float] = None
        tv_ri: Optional[float] = None
        pv_tv_ri: Optional[float] = None

        if k_e > 0 and tg_used is not None:
            if tg_used >= k_e:
                flags.append(DiagnosticFlag(
                    code="RI-G-GE-K", severity="critical",
                    message="Terminal growth rate (g) must be less than cost of equity (k_e) for perpetuity formula.",
                    evidence={"g": tg_used, "ke": k_e},
                    recommendation="Lower terminal growth rate or raise cost of equity.",
                ))
            elif forecast_ri and float(forecast_ri[-1]) > 0:
                terminal_ri_ps = float(forecast_ri[-1]) * (1.0 + tg_used)
                tv_ri = terminal_ri_ps / (k_e - tg_used)
                pv_tv_ri = tv_ri / ((1.0 + k_e) ** n)
            else:
                # RI fades to zero (or negative) — terminal value is 0 (conservative)
                flags.append(DiagnosticFlag(
                    code="RI-TV-ZERO", severity="info",
                    message="Terminal RI set to zero because RI_{n} ≤ 0 (company not earning excess returns at end of forecast).",
                    evidence={"riN": float(forecast_ri[-1]) if forecast_ri else None},
                    recommendation="This is a conservative but valid choice. Positive terminal RI requires RI_{n} > 0.",
                ))

        # ── Intrinsic value per share ─────────────────────────────────────────

        intrinsic_ps: Optional[float] = None
        if bv_per_share is not None:
            intrinsic_ps = float(bv_per_share) + float(total_pv_ri) + (float(pv_tv_ri) if pv_tv_ri is not None else 0.0)

        # ── Upside (computed after intrinsic is final — mirrors DDM pattern) ──

        upside: Optional[float] = None
        if current_price is not None and float(current_price) > 0 and intrinsic_ps is not None:
            upside = (intrinsic_ps - float(current_price)) / float(current_price)

        # ── Suitability scorecard ─────────────────────────────────────────────

        ri_score, ri_category, ri_flags, ri_evidence = await evaluate_residual_income_suitability(
            repo=self.repo, company_id=company_id, sector=sector,
            cost_of_equity=float(k_e),
        )
        flags.extend(ri_flags)

        # ── AI summary (called AFTER intrinsic and upside are finalised) ──────

        suitability_summary = await generate_suitability_summary(
            symbol=symbol,
            method="residual_income",
            score=int(ri_score),
            category=ri_category,
            flags=[f.dict() for f in flags],
            evidence=ri_evidence,
            valuation_inputs={
                "currency": currency,
                "eps0": eps0,
                "bvPerShare": bv_per_share,
                "roe0": roe0,
                "ri0PerShare": ri0_per_share,
                "costOfEquity": float(k_e),
                "riGrowthRate": float(g_ri),
                "intrinsicValuePerShare": float(intrinsic_ps) if intrinsic_ps is not None else None,
                "currentPrice": current_price,
                "upsideDownsidePct": upside,
            },
            input_decisions={"ri": input_decisions},
        )

        # ── Build valuation object ────────────────────────────────────────────

        valuation = ResidualIncomeValuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            forecastYears=int(n),
            costOfEquityUsed=float(k_e),
            betaUsed=k_evidence.get("beta"),
            rfUsed=k_evidence.get("rf"),
            erpUsed=k_evidence.get("erp"),
            riGrowthRateUsed=float(g_ri),
            terminalGrowthRateUsed=tg_used,
            eps0=eps0,
            bvPerShare=bv_per_share,
            roe0=roe0,
            ri0PerShare=ri0_per_share,
            bvFiscalYear=int(bv_fy) if isinstance(bv_fy, int) else None,
            forecastRiPerShare=[float(x) for x in forecast_ri],
            pvRiPerShare=[float(x) for x in pv_ri],
            discountFactors=[float(x) for x in discount_factors],
            totalPvRiPerShare=float(total_pv_ri),
            terminalRiPerShare=float(terminal_ri_ps) if terminal_ri_ps is not None else None,
            terminalValueRi=float(tv_ri) if tv_ri is not None else None,
            pvTerminalRiPerShare=float(pv_tv_ri) if pv_tv_ri is not None else None,
            intrinsicValuePerShare=float(intrinsic_ps) if intrinsic_ps is not None else None,
            currentPrice=current_price,
            upsideDownsidePct=upside,
        )

        # ── Audit run ─────────────────────────────────────────────────────────

        now_iso = datetime.utcnow().isoformat() + "Z"
        output_snapshot = {
            "valuation": valuation.dict(),
            "applicability": {
                "score": ri_score, "category": ri_category,
                "flags": [f.dict() for f in flags],
                "suitabilitySummary": suitability_summary,
            },
            "dataQuality": {
                "freshnessDays": {"lastComputedAt": now_iso},
                "fallbacksUsed": bool(fallbacks_used),
                "inputDecisions": {"ri": input_decisions},
            },
            "suitabilityEvidence": ri_evidence,
            "lastComputedAt": now_iso,
        }
        await self.repo.insert_valuation_run(
            company_id=company_id,
            method="residual_income",
            run={
                "run_by_user_id": user_id,
                "input_snapshot": {"overrides": overrides.dict()},
                "assumption_snapshot": defaults,
                "output_snapshot": output_snapshot,
                "data_version_tag": None,
                "notes": overrides.notes,
            },
        )

        return ResidualIncomeResponse(
            valuation=valuation,
            applicability=Applicability(
                score=ri_score, category=ri_category, flags=flags,
                suitabilitySummary=suitability_summary,
            ),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": now_iso},
                fallbacksUsed=bool(fallbacks_used),
                inputDecisions={"ri": input_decisions},
            ),
        )

    # ── Cost of equity resolution (mirrors DDM _resolve_required_return) ──────

    async def _resolve_cost_of_equity(
        self,
        company_id: int,
        overrides: ResidualIncomeRequestOverrides,
        defaults: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        k_floor = float(defaults.get("k_floor", 0.07))
        k_cap = float(defaults.get("k_cap", 0.14))
        k_default = float(defaults.get("k_default", 0.10))
        rf_default = float(defaults.get("rf_default", 0.045))
        erp_default = float(defaults.get("erp_default", 0.055))

        if overrides.requiredReturn is not None:
            k_raw = _pct_or_frac_to_frac(float(overrides.requiredReturn))
            k_final = _clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "override.requiredReturn",
                "kRaw": k_raw, "kFinal": k_final,
                "kFloor": k_floor, "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        beta = overrides.beta
        if beta is None:
            beta = await self.repo.get_beta_latest(company_id)

        rf = _pct_or_frac_to_frac(float(overrides.riskFreeRate)) if overrides.riskFreeRate is not None else rf_default
        erp = _pct_or_frac_to_frac(float(overrides.equityRiskPremium)) if overrides.equityRiskPremium is not None else erp_default

        if beta is None:
            k_raw = k_default
            k_final = _clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "default.k_default (beta missing)",
                "beta": None, "rf": rf, "erp": erp,
                "kRaw": k_raw, "kFinal": k_final,
                "kFloor": k_floor, "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        k_raw = rf + float(beta) * erp
        k_final = _clamp(k_raw, k_floor, k_cap)
        return k_final, {
            "source": "capm",
            "beta": float(beta), "rf": rf, "erp": erp,
            "kRaw": k_raw, "kFinal": k_final,
            "kFloor": k_floor, "kCap": k_cap,
            "clamped": k_raw != k_final,
        }

    # ── RI growth rate resolution ─────────────────────────────────────────────

    async def _resolve_ri_growth(
        self,
        company_id: int,
        overrides: ResidualIncomeRequestOverrides,
        defaults: Dict[str, Any],
        k_e: float,
    ) -> Tuple[float, Dict[str, Any]]:
        """
        Resolve RI growth rate. Priority:
        1. Override.riGrowthRate
        2. EPS CAGR from history (proxy for RI growth)
        3. Defaults

        The growth rate is clamped so g < k_e (perpetuity stability requirement).
        """
        g_floor = float(defaults.get("g_floor", -0.05))
        g_cap = float(defaults.get("g_cap", 0.15))
        g_default = float(defaults.get("g_default", 0.04))
        gap_to_k = float(defaults.get("g_gap_to_k", 0.01))

        if overrides.riGrowthRate is not None:
            g_raw = _pct_or_frac_to_frac(float(overrides.riGrowthRate))
            g_stable = min(g_raw, max(g_floor, k_e - gap_to_k))
            g_final = _clamp(g_stable, g_floor, g_cap)
            return g_final, {
                "source": "override.riGrowthRate",
                "gRaw": g_raw, "gStable": g_stable, "gFinal": g_final,
                "gFloor": g_floor, "gCap": g_cap, "gapToK": gap_to_k, "ke": k_e,
                "clamped": g_final != g_raw,
            }

        # EPS CAGR from history as proxy
        g_hist: Optional[float] = None
        try:
            eps_rows = await self.repo.get_eps_yearly_series(company_id)
            eps_pairs = sorted(
                [(r["fiscal_year"], float(r["eps"])) for r in eps_rows
                 if r.get("fiscal_year") and r.get("eps") is not None],
                key=lambda t: t[0],
            )[-6:]
            if len(eps_pairs) >= 2:
                y0, v0 = eps_pairs[0]
                yN, vN = eps_pairs[-1]
                span = yN - y0
                if span > 0 and v0 > 0 and vN > 0:
                    g_hist = (vN / v0) ** (1.0 / span) - 1.0
        except Exception:
            g_hist = None

        if g_hist is not None:
            g_raw = float(g_hist)
            source = "eps_cagr_approx"
        else:
            g_raw = g_default
            source = "default.g_default"

        g_stable = min(g_raw, max(g_floor, k_e - gap_to_k))
        g_final = _clamp(g_stable, g_floor, g_cap)
        return g_final, {
            "source": source,
            "gHistEps": g_hist,
            "gRaw": g_raw, "gStable": g_stable, "gFinal": g_final,
            "gFloor": g_floor, "gCap": g_cap, "gapToK": gap_to_k, "ke": k_e,
            "clamped": g_final != g_raw,
        }