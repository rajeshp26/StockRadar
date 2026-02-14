# application/services/ddm_service.py
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from application.services.recompute_guard import RecomputeGuard
from application.services.ddm_suitability import evaluate_ddm_suitability
from domain.models.valuation_ddm import DdmRequestOverrides, DdmResponse, DdmValuation
from domain.models.valuation_rule1 import Applicability, DataQuality, DiagnosticFlag
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _pct_or_frac_to_frac(x: float) -> float:
    # If user stores 5 for 5%, convert to 0.05. If already 0.05, keep.
    return x / 100.0 if x > 1.0 else x


class DdmService:
    """
    Dividend Discount Model valuation service with cached-vs-recompute.

    Variants:
      - ddm_gordon
      - ddm_two_stage

    Price policy:
      - Intrinsic valuation is cached and audited.
      - Current price & upside are computed at read-time only.
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo = repo
        self.guard = guard

    async def compute_ddm_if_stale(
        self,
        symbol: str,
        user_id: Optional[int],
        variant: str,  # "gordon" | "two_stage"
        overrides: Optional[DdmRequestOverrides] = None,
        force: bool = False,
    ) -> DdmResponse:
        overrides = overrides or DdmRequestOverrides()
        method = "ddm_gordon" if variant == "gordon" else "ddm_two_stage"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"
        sector = ctx.get("sector")

        decision = await self.guard.cached_or_recompute(company_id=company_id, method=method, force=force)

        if decision.should_recompute:
            logger.info(
                "[VALUATION][DDM][%s] recompute: company=%s symbol=%s reason=%s dep_ts=%s last_ts=%s",
                method,
                company_id,
                symbol,
                decision.reason,
                decision.latest_dependency_at,
                decision.last_valuation_at,
            )
            return await self._compute_and_persist(symbol, company_id, currency, sector, user_id, method, overrides)

        # Cached path: read last audited run for this method
        snap = await self.repo.get_last_output_snapshot(company_id=company_id, method=method)
        if not snap:
            logger.info("[VALUATION][DDM][%s] cached path missing audited run; recomputing for %s", method, symbol)
            return await self._compute_and_persist(symbol, company_id, currency, sector, user_id, method, overrides)

        valuation_payload = snap.get("valuation") or {}
        applicability_payload = snap.get("applicability") or {}
        dq_payload = snap.get("dataQuality") or {}
        last_computed = (dq_payload.get("freshnessDays") or {}).get("lastComputedAt") or snap.get("lastComputedAt")

        # Read-time price only
        current_price = await self.repo.get_current_market_price(company_id)
        intrinsic = float(valuation_payload.get("intrinsicValue") or 0.0)

        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic > 0:
            upside = (intrinsic - float(current_price)) / float(current_price)

        # Update valuation fields without altering intrinsic assumptions
        valuation_payload["currentPrice"] = current_price
        valuation_payload["upsideDownsidePct"] = upside

        # If no audited applicability exists (defensive), do NOT fabricate
        if not applicability_payload:
            applicability_payload = {
                "score": 0,
                "category": "Caution",
                "flags": [
                    {
                        "code": "DDM-NO-AUDIT",
                        "severity": "info",
                        "message": "No prior DDM valuation run found; suitability scorecard not available on cached path.",
                        "recommendation": "Run Recompute once to generate an audited scorecard.",
                    }
                ],
            }

        if not dq_payload:
            dq_payload = {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}

        if isinstance(dq_payload.get("freshnessDays"), dict) and last_computed:
            dq_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return DdmResponse(
            valuation=DdmValuation(**valuation_payload),
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
        method: str,  # "ddm_gordon" | "ddm_two_stage"
        overrides: DdmRequestOverrides,
    ) -> DdmResponse:
        # Defaults (method-specific)
        defaults = await self.repo.get_method_params(company_id, method=method)

        # Resolve D0 (annual dividend per share)
        d0 = overrides.currentDps
        d0_source = "override.currentDps" if d0 is not None else None

        if d0 is None:
            d0 = await self.repo.get_dividend_ttm_dps(company_id)
            d0_source = "dividend_history_ttm"

        # Read-time price (captured for run snapshot, but not a recompute dependency)
        current_price = await self.repo.get_current_market_price(company_id)

        input_decisions: Dict[str, Any] = {"d0Source": d0_source}
        flags: list[DiagnosticFlag] = []
        fallbacks_used = False

        if d0 is None or float(d0) <= 0:
            flags.append(DiagnosticFlag(
                code="DDM-NO-DIV",
                severity="critical",
                message="No dividend data available (D0 missing). DDM is not applicable.",
                recommendation="Use non-dividend valuation methods (Rule #1 / DCF / Owner Earnings).",
            ))
            valuation = DdmValuation(
                symbol=symbol.upper(),
                companyId=company_id,
                currency=currency,
                method="gordon" if method == "ddm_gordon" else "two_stage",
                currentDps=0.0,
                nextYearDps=0.0,
                dividendGrowthRate=0.0,
                requiredReturn=0.0,
                intrinsicValue=0.0,
                currentPrice=current_price,
                upsideDownsidePct=None,
            )
            return DdmResponse(
                valuation=valuation,
                applicability=Applicability(score=0, category="Poor", flags=flags),
                dataQuality=DataQuality(
                    freshnessDays={},
                    fallbacksUsed=True,
                    inputDecisions={"ddm": input_decisions},
                ),
            )

        d0 = float(d0)

        # Resolve k (required return)
        k, k_evidence = await self._resolve_required_return(company_id, overrides, defaults)
        input_decisions["requiredReturn"] = k_evidence

        # Resolve g
        g, g_evidence = await self._resolve_dividend_growth(company_id, overrides, defaults, k)
        input_decisions["dividendGrowthRate"] = g_evidence

        # D1
        d1 = d0 * (1.0 + g)

        # Suitability scorecard (authoritative)
        ddm_score, ddm_category, ddm_flags, ddm_evidence = await evaluate_ddm_suitability(
            repo=self.repo,
            company_id=company_id,
            sector=sector,
        )
        flags.extend(ddm_flags)

        # Add explicit guardrail evidence flags
        if k_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="DDM-K-CLAMP",
                severity="info",
                message="Required return (k) was clamped to safety bounds.",
                evidence=k_evidence,
            ))
        if g_evidence.get("clamped"):
            flags.append(DiagnosticFlag(
                code="DDM-G-CLAMP",
                severity="info",
                message="Dividend growth (g) was clamped to safety bounds.",
                evidence=g_evidence,
            ))

        intrinsic = 0.0
        pv_stage1 = None
        pv_terminal = None

        if method == "ddm_gordon":
            if g >= k:
                flags.append(DiagnosticFlag(
                    code="DDM-GE-K",
                    severity="critical",
                    message="Dividend growth rate (g) must be less than required return (k) for Gordon model.",
                    evidence={"g": g, "k": k},
                    recommendation="Use Two-Stage DDM or lower g / raise k.",
                ))
                intrinsic = 0.0
            else:
                intrinsic = d1 / (k - g)

        else:
            # Two-stage
            n = int(overrides.highGrowthYears if overrides.highGrowthYears is not None else defaults.get("twostageyearsdefault", 5))
            g1_default = float(defaults.get("g1_cap", 0.12))
            g2_default = float(defaults.get("g2default", 0.03))
            gap = float(defaults.get("ggaptok", 0.01))

            g1 = float(overrides.highGrowthRate) if overrides.highGrowthRate is not None else min(g, g1_default)
            g1 = _clamp(g1, 0.0, g1_default)

            g2 = float(overrides.stableGrowthRate) if overrides.stableGrowthRate is not None else g2_default
            g2 = _pct_or_frac_to_frac(g2)
            if g2 >= k:
                g2 = max(0.0, k - gap)
                flags.append(DiagnosticFlag(
                    code="DDM-G2-ADJUST",
                    severity="medium",
                    message="Stable growth rate (g2) adjusted to ensure g2 < k.",
                    evidence={"g2Adjusted": g2, "k": k, "gap": gap},
                ))

            pv1 = 0.0
            for t in range(1, n + 1):
                dt = d0 * ((1.0 + g1) ** t)
                pv1 += dt / ((1.0 + k) ** t)

            dn = d0 * ((1.0 + g1) ** n)
            dn1 = dn * (1.0 + g2)
            tv_n = dn1 / (k - g2) if k > g2 else 0.0
            pv_tv = tv_n / ((1.0 + k) ** n)

            pv_stage1 = pv1
            pv_terminal = pv_tv
            intrinsic = pv1 + pv_tv

            # for response, show stable growth as dividendGrowthRate
            g = g2

        upside = None
        if current_price is not None and float(current_price) > 0 and intrinsic > 0:
            upside = (intrinsic - float(current_price)) / float(current_price)

        valuation = DdmValuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            method="gordon" if method == "ddm_gordon" else "two_stage",
            currentDps=d0,
            nextYearDps=float(d1),
            dividendGrowthRate=float(g),
            requiredReturn=float(k),
            intrinsicValue=float(intrinsic),
            highGrowthYears=(None if method == "ddm_gordon" else n),
            highGrowthRate=(None if method == "ddm_gordon" else float(g1)),
            stableGrowthRate=(None if method == "ddm_gordon" else float(g2)),
            pvStage1=pv_stage1,
            pvTerminal=pv_terminal,
            currentPrice=current_price,
            upsideDownsidePct=upside,
        )

        # Persist to ddm_valuations (latest snapshot stream; not used for cached read)
        await self.repo.insert_ddm_valuation(
            payload={
                "company_id": company_id,
                "analysis_date": date.today().isoformat(),
                "current_dps": d0,
                "next_year_dps": float(d1),
                "dividend_growth_rate": float(g),
                "required_return": float(k),
                "intrinsic_value_gordon": float(intrinsic) if method == "ddm_gordon" else None,
                "high_growth_years": valuation.highGrowthYears,
                "high_growth_rate": valuation.highGrowthRate,
                "stable_growth_rate": valuation.stableGrowthRate,
                "intrinsic_value_multistage": float(intrinsic) if method != "ddm_gordon" else None,
                "current_stock_price": current_price,
                "upside_downside_pct": upside,
                "analyst_name": overrides.analystName,
                "notes": overrides.notes,
            }
        )

        # Persist audited valuation_runs record (append-only)
        now_iso = datetime.utcnow().isoformat() + "Z"
        output_snapshot = {
            "valuation": valuation.dict(),
            "applicability": {
                "score": ddm_score,
                "category": ddm_category,
                "flags": [f.dict() for f in flags],
            },
            "dataQuality": {
                "freshnessDays": {"lastComputedAt": now_iso},
                "fallbacksUsed": fallbacks_used,
                "inputDecisions": {"ddm": input_decisions},
            },
            "suitabilityEvidence": ddm_evidence,
            "lastComputedAt": now_iso,
        }

        await self.repo.insert_valuation_run(
            company_id=company_id,
            method=method,
            run={
                "run_by_user_id": user_id,
                "input_snapshot": {"overrides": overrides.dict()},
                "assumption_snapshot": defaults,
                "output_snapshot": output_snapshot,
                "data_version_tag": None,
                "notes": overrides.notes,
            },
        )

        return DdmResponse(
            valuation=valuation,
            applicability=Applicability(score=ddm_score, category=ddm_category, flags=flags),
            dataQuality=DataQuality(
                freshnessDays={"lastComputedAt": now_iso},
                fallbacksUsed=fallbacks_used,
                inputDecisions={"ddm": input_decisions},
            ),
        )

    async def _resolve_required_return(
        self,
        company_id: int,
        overrides: DdmRequestOverrides,
        defaults: Dict[str, Any],
    ) -> Tuple[float, Dict[str, Any]]:
        k_floor = float(defaults.get("kfloor", 0.07))
        k_cap = float(defaults.get("kcap", 0.14))
        k_default = float(defaults.get("kdefault", 0.10))
        rf_default = float(defaults.get("rfdefault", 0.045))
        erp_default = float(defaults.get("erpdefault", 0.055))

        if overrides.requiredReturn is not None:
            k_raw = float(overrides.requiredReturn)
            k_final = _clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "override.requiredReturn",
                "kRaw": k_raw,
                "kFinal": k_final,
                "kFloor": k_floor,
                "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        beta = overrides.beta
        if beta is None:
            beta = await self.repo.get_beta_latest(company_id)

        rf = float(overrides.riskFreeRate) if overrides.riskFreeRate is not None else rf_default
        erp = float(overrides.equityRiskPremium) if overrides.equityRiskPremium is not None else erp_default

        if beta is None:
            k_raw = k_default
            k_final = _clamp(k_raw, k_floor, k_cap)
            return k_final, {
                "source": "default.kdefault (beta missing)",
                "beta": None,
                "rf": rf,
                "erp": erp,
                "kRaw": k_raw,
                "kFinal": k_final,
                "kFloor": k_floor,
                "kCap": k_cap,
                "clamped": k_raw != k_final,
            }

        k_raw = rf + float(beta) * erp
        k_final = _clamp(k_raw, k_floor, k_cap)

        return k_final, {
            "source": "capm-ish",
            "beta": float(beta),
            "rf": rf,
            "erp": erp,
            "kRaw": k_raw,
            "kFinal": k_final,
            "kFloor": k_floor,
            "kCap": k_cap,
            "clamped": k_raw != k_final,
        }

    async def _resolve_dividend_growth(
        self,
        company_id: int,
        overrides: DdmRequestOverrides,
        defaults: Dict[str, Any],
        k: float,
    ) -> Tuple[float, Dict[str, Any]]:
        g_floor = float(defaults.get("gfloor", 0.02))
        g_cap = float(defaults.get("gcap", 0.10))
        gap_to_k = float(defaults.get("ggaptok", 0.01))
        g_default = float(defaults.get("g2default", 0.04))

        if overrides.dividendGrowthRate is not None:
            g_raw = _pct_or_frac_to_frac(float(overrides.dividendGrowthRate))
            g_stable = min(g_raw, max(0.0, k - gap_to_k))
            g_final = _clamp(g_stable, g_floor, g_cap)
            return g_final, {
                "source": "override.dividendGrowthRate",
                "gRaw": g_raw,
                "gAfterStability": g_stable,
                "gFinal": g_final,
                "gFloor": g_floor,
                "gCap": g_cap,
                "gapToK": gap_to_k,
                "k": k,
                "clamped": (g_final != g_raw) or (g_raw != g_stable),
            }

        g_hist = await self.repo.get_dividend_cagr(company_id, years=10)
        g_sgr = await self.repo.get_sustainable_dividend_growth(company_id)

        candidates = [g for g in [g_hist, g_sgr] if g is not None]
        if not candidates:
            g_raw = g_default
            source = "default.g2default (missing hist & sgr)"
        else:
            g_raw = float(min(candidates))
            source = "min(g_hist, g_sgr)" if (g_hist is not None and g_sgr is not None) else ("g_hist" if g_hist is not None else "g_sgr")

        g_stable = min(g_raw, max(0.0, k - gap_to_k))
        g_final = _clamp(g_stable, g_floor, g_cap)

        return g_final, {
            "source": source,
            "gHist": g_hist,
            "gSgr": g_sgr,
            "gRaw": g_raw,
            "gAfterStability": g_stable,
            "gFinal": g_final,
            "gFloor": g_floor,
            "gCap": g_cap,
            "gapToK": gap_to_k,
            "k": k,
            "clamped": (g_final != g_raw) or (g_raw != g_stable),
        }