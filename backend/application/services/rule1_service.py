# application/services/rule1_service.py
"""
Rule #1 Valuation Service (Phil Town method).

Extracted from ValuationService to match the DDM / DCF / OE / RI pattern.
ValuationService keeps thin wrappers for backward compatibility.

Three-gate caching:
  Gate 1 — Timestamp:   Are dependency tables newer than the last valuation run?
  Gate 2 — Fingerprint: Have source data VALUES actually changed?
  Gate 3 — Not applicable: Rule1 scorecard metrics are categorical (EPS CAGR
            pass/fail). No numeric significance thresholds are defined.
            Fingerprint mismatch (Gate 2) always triggers recompute.

Bypass rules:
  force=True                → skip all gates
  no_prior_valuation        → skip Gate 2 (nothing to compare)
  any override field set    → skip Gate 2 (explicit user inputs)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
 
from shared.finance_math import (
    build_fingerprint,
    clamp,
    safe_float,
)

from application.services.ai_service import generate_suitability_summary
from application.services.recompute_guard import RecomputeGuard
from application.services.rule1_suitability import evaluate_rule1_suitability
from domain.models.valuation_rule1 import (
    Applicability,
    DataQuality,
    DiagnosticFlag,
    Rule1RequestOverrides,
    Rule1Response,
    Rule1Valuation,
)
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

SECTOR_CYCL = {"Energy", "Materials"}


# ── Module-level helpers ───────────────────────────────────────────────────────

def _as_date(d: Any) -> Optional[date]:
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, str):
        try:
            return date.fromisoformat(d)
        except Exception:
            return None
    return None

# ── Service ────────────────────────────────────────────────────────────────────

class Rule1Service:
    """Phil Town Rule #1 valuation service with three-gate caching."""

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo  = repo
        self.guard = guard

    # ── Public entry point ─────────────────────────────────────────────────────

    async def compute_rule1_if_stale(
        self,
        symbol:    str,
        user_id:   Optional[int],
        overrides: Optional[Rule1RequestOverrides] = None,
        force:     bool = False,
    ) -> Rule1Response:
        overrides = overrides or Rule1RequestOverrides()
        method    = "rule1"

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"

        # ── Force: bypass all gates ────────────────────────────────────────
        if force:
            dep_values  = await self.repo.get_rule1_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            logger.info("[VALUATION][R1] forced recompute: %s", symbol)
            return await self.compute_rule1_with_diagnostics(
                symbol, user_id, overrides, dependency_fingerprint=fingerprint
            )

        # ── Gate 1: Timestamp ──────────────────────────────────────────────
        decision = await self.guard.cached_or_recompute(
            company_id=company_id, method=method, force=False
        )

        if not decision.should_recompute:
            logger.info(
                "[VALUATION][R1] Gate 1 → cached: company=%s symbol=%s dep_ts=%s last_ts=%s",
                company_id, symbol,
                decision.latest_dependency_at, decision.last_valuation_at,
            )
            return await self._serve_rule1_cached(company_id, symbol, currency)

        logger.info(
            "[VALUATION][R1] Gate 1 fired: company=%s symbol=%s reason=%s dep_ts=%s last_ts=%s",
            company_id, symbol, decision.reason,
            decision.latest_dependency_at, decision.last_valuation_at,
        )

        # ── No prior valuation: skip Gate 2 ───────────────────────────────
        if decision.reason == "no_prior_valuation":
            dep_values  = await self.repo.get_rule1_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            return await self.compute_rule1_with_diagnostics(
                symbol, user_id, overrides, dependency_fingerprint=fingerprint
            )

        # ── Override present: bypass Gate 2 ───────────────────────────────
        if self._has_rule1_overrides(overrides):
            dep_values  = await self.repo.get_rule1_dependency_values(company_id)
            fingerprint = build_fingerprint(dep_values)
            logger.info("[VALUATION][R1] Override present → bypass Gate 2: %s", symbol)
            return await self.compute_rule1_with_diagnostics(
                symbol, user_id, overrides, dependency_fingerprint=fingerprint
            )

        # ── Gate 2: Fingerprint ────────────────────────────────────────────
        dep_values  = await self.repo.get_rule1_dependency_values(company_id)
        fingerprint = build_fingerprint(dep_values)

        gate2 = await self.guard.check_fingerprint(company_id, method, fingerprint)
        if not gate2.should_recompute:
            logger.info(
                "[VALUATION][R1] Gate 2 → cached (fingerprint_match): %s", symbol
            )
            return await self._serve_rule1_cached(company_id, symbol, currency)

        logger.info(
            "[VALUATION][R1] Gate 2 fired: %s reason=%s", symbol, gate2.reason
        )

        # ── Gate 3: not applicable for Rule1 ──────────────────────────────
        # guard.is_material_change() returns "no_gate3_for_method" for rule1
        # → always treated as material → proceed to full recompute.
        return await self.compute_rule1_with_diagnostics(
            symbol, user_id, overrides, dependency_fingerprint=fingerprint
        )

    # ── Full computation ───────────────────────────────────────────────────────

    async def compute_rule1_with_diagnostics(
        self,
        symbol:                 str,
        user_id:                Optional[int],
        overrides:              Optional[Rule1RequestOverrides] = None,
        dependency_fingerprint: Optional[str] = None,
    ) -> Rule1Response:
        overrides = overrides or Rule1RequestOverrides()

        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")

        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
        sector     = ctx.get("sector")
        industry   = ctx.get("industry")

        params = await self.repo.get_method_params(company_id, method="rule1")

        discount_rate = float(
            overrides.discountRate if overrides.discountRate is not None
            else params.get("discount_rate", 0.15)
        )
        horizon_years = int(
            overrides.horizonYears if overrides.horizonYears is not None
            else params.get("horizon_years", 10)
        )
        mos = float(
            overrides.marginOfSafety if overrides.marginOfSafety is not None
            else params.get("margin_of_safety", 0.50)
        )

        extra_flags:     List[DiagnosticFlag] = []
        dq_freshness:    Dict[str, Any]       = {}
        input_decisions: Dict[str, Any]       = {}
        fallbacks_used                         = False

        # ── EPS ───────────────────────────────────────────────────────────
        trailing           = await self.repo.get_trailing_eps(company_id)
        eps0:              Optional[float] = None
        eps_snapshot_date: Optional[date]  = None

        prefer_trailing = bool(params.get("prefer_trailing_eps", True))
        if trailing and trailing.get("trailing_eps") is not None and prefer_trailing:
            eps0              = float(trailing["trailing_eps"])
            eps_snapshot_date = _as_date(trailing.get("snapshot_date"))
            dq_freshness["trailingEPS"] = (
                (date.today() - eps_snapshot_date).days if eps_snapshot_date else None
            )
        else:
            eps0           = await self.repo.compute_ttm_eps_fallback(company_id)
            fallbacks_used = True
            dq_freshness["trailingEPS"] = None

        if eps0 is None:
            extra_flags.append(DiagnosticFlag(
                code="R1-NOEPS", severity="high",
                message="EPS not available; valuation may be low confidence.",
            ))
        elif eps0 <= 0.05:
            extra_flags.append(DiagnosticFlag(
                code="R1-NEGEPS", severity="critical",
                message="Negative or near-zero EPS—Rule #1 valuation is not meaningful.",
            ))

        input_decisions["eps0"] = {
            "value":        eps0,
            "source":       "company_summary.trailing_eps" if eps_snapshot_date else "ttm_fallback",
            "snapshotDate": eps_snapshot_date.isoformat() if eps_snapshot_date else None,
        }

        # ── Growth rate ────────────────────────────────────────────────────
        growth:        Optional[float] = None
        growth_source: str             = ""
        prefer_forecast = bool(params.get("prefer_forecast_growth", True))

        if overrides.forceGrowth is not None:
            growth        = float(overrides.forceGrowth)
            growth_source = "override"
        else:
            if prefer_forecast:
                growth_row = await self.repo.get_eps_forecast_growth(company_id)
                if growth_row and growth_row.get("estimate_eps_growth") is not None:
                    growth        = float(growth_row["estimate_eps_growth"])
                    growth_source = "earnings_forecast.estimate_eps_growth"
                    rep_date      = _as_date(growth_row.get("report_date"))
                    dq_freshness["epsForecast"] = (
                        (date.today() - rep_date).days if rep_date else None
                    )

            if growth is None:
                eps_hist = await self.repo.get_eps_history(company_id)
                g_eps    = self._cagr_from_series(eps_hist, key="eps")
                if g_eps is not None:
                    growth        = g_eps
                    growth_source = "eps_cagr_approx"

            if growth is None:
                rev_hist = await self.repo.get_revenue_history(company_id)
                g_rev    = self._cagr_from_series(rev_hist, key="revenue")
                if g_rev is not None:
                    growth         = g_rev
                    growth_source  = "revenue_cagr_approx"
                    fallbacks_used = True

            if growth is None and sector and industry:
                im = await self.repo.get_industry_multiples(sector, industry)
                if im and im.get("median_eps_growth") is not None:
                    growth         = float(im["median_eps_growth"])
                    growth_source  = "industry.median_eps_growth"
                    fallbacks_used = True

            if growth is None:
                growth         = 0.10
                growth_source  = "conservative_default"
                fallbacks_used = True

        g_min      = float(params.get("growth_clamp_min", 0.02))
        g_max      = float(params.get("growth_clamp_max", 0.25))
        growth_raw = growth
        growth = clamp(float(growth or 0.0), g_min, g_max)

        if growth_raw is not None and growth_raw > growth:
            extra_flags.append(DiagnosticFlag(
                code="R1-GCLAMP-HIGH", severity="low",
                message=f"Growth input {growth_raw:.2%} clamped to {g_max:.2%} for conservatism.",
            ))
        if growth_raw is not None and growth_raw < growth:
            extra_flags.append(DiagnosticFlag(
                code="R1-GCLAMP-LOW", severity="low",
                message=f"Growth input {growth_raw:.2%} raised to {g_min:.2%} minimum.",
            ))

        input_decisions["growth"] = {
            "valueRaw": growth_raw, "valueClamped": growth, "source": growth_source
        }

        # ── Future PE ──────────────────────────────────────────────────────
        pe_source: str
        if overrides.forceFuturePE is not None:
            future_pe = float(overrides.forceFuturePE)
            pe_source = "override"
        else:
            pe_floor          = float(params.get("pe_floor", 8))
            pe_cap            = float(params.get("pe_cap",   50))
            two_x_growth_rule = min(2 * (growth * 100.0), pe_cap)
            rule_pe           = max(pe_floor, two_x_growth_rule)
            pe_source         = "2xGrowthRule"

            if sector and industry and bool(params.get("use_industry_pe_if_lower", True)):
                im = await self.repo.get_industry_multiples(sector, industry)
                if im and im.get("median_pe") is not None:
                    industry_pe = float(im["median_pe"])
                    if industry_pe < rule_pe:
                        future_pe = industry_pe
                        pe_source = "industry_median_pe"
                        extra_flags.append(DiagnosticFlag(
                            code="R1-PERULE", severity="info",
                            message="Used industry median PE for conservatism.",
                            evidence={
                                "industryMedianPE":   industry_pe,
                                "twoXGrowthRulePE":   rule_pe,
                            },
                        ))
                    else:
                        future_pe = rule_pe
                else:
                    future_pe = rule_pe
            else:
                future_pe = rule_pe

        input_decisions["futurePE"] = {"selected": future_pe, "rule": pe_source}

        # ── Intrinsic value math ───────────────────────────────────────────
        eps0_safe   = float(eps0 or 0.0)
        future_eps  = eps0_safe * ((1.0 + growth) ** horizon_years) if eps0_safe > 0 else 0.0
        future_price = future_eps * float(future_pe)
        denominator  = (1.0 + discount_rate) ** horizon_years
        sticker_price = future_price / denominator if denominator > 0 else 0.0
        mos_price     = sticker_price * (1.0 - mos)

        # ── Sector and split flags ─────────────────────────────────────────
        if sector in SECTOR_CYCL:
            extra_flags.append(DiagnosticFlag(
                code="R1-SECTOR-CYCL", severity="medium",
                message="Cyclical sector—earnings can swing materially across cycles.",
                recommendation=(
                    "Use conservative growth and a wider MOS; "
                    "review drawdown metric carefully."
                ),
            ))

        if eps_snapshot_date:
            split_cnt = await self.repo.get_recent_split_count_after(
                company_id, eps_snapshot_date
            )
            if split_cnt > 0:
                extra_flags.append(DiagnosticFlag(
                    code="R1-SPLIT", severity="medium",
                    message="Recent split after EPS snapshot—EPS may be unadjusted.",
                    evidence={
                        "splitCount":       split_cnt,
                        "epsSnapshotDate":  eps_snapshot_date.isoformat(),
                    },
                ))

        # ── Suitability scorecard ──────────────────────────────────────────
        metric_score, metric_category, metric_flags, suitability_evidence = (
            await evaluate_rule1_suitability(
                repo=self.repo,
                company_id=company_id,
                sector=sector,
            )
        )

        all_flags: List[DiagnosticFlag] = list(metric_flags) + list(extra_flags)

        # ── AI summary ────────────────────────────────────────────────────
        suitability_summary = await generate_suitability_summary(
            symbol=symbol,
            method="rule1",
            score=int(metric_score),
            category=metric_category,
            flags=[f.dict() for f in all_flags],
            evidence=suitability_evidence,
            valuation_inputs={
                "currency":     currency,
                "eps0":         eps0_safe,
                "growth":       growth,
                "futurePE":     float(future_pe),
                "futureEPS":    float(future_eps),
                "futurePrice":  float(future_price),
                "stickerPrice": float(sticker_price),
                "mosPrice":     float(mos_price),
                "discountRate": float(discount_rate),
                "horizonYears": int(horizon_years),
                "mos":          float(mos),
            },
            input_decisions={
                **input_decisions,
                "assumptions": {
                    "discountRate": float(discount_rate),
                    "horizonYears": int(horizon_years),
                    "mos":          float(mos),
                },
            },
        )

        # ── Persist: intrinsic_value_analysis (Rule1-specific table) ──────
        await self.repo.upsert_intrinsic_value_analysis(
            company_id,
            {
                "growth_rate":  growth,
                "current_eps":  eps0_safe,
                "future_pe":    future_pe,
                "future_price": future_price,
                "sticker_price": sticker_price,
                "mos_price":    mos_price,
            },
        )

        now_iso = datetime.utcnow().isoformat() + "Z"
        dq_freshness["lastComputedAt"] = now_iso

        # ── Build resolved inputs for audit trail ──────────────────────────
        # Rule1 has no Gate 3 numeric thresholds today, but storing resolved
        # inputs here makes future Gate 3 adoption trivial and gives a clear
        # per-run audit record of what was actually computed.
        resolved_inputs: Dict[str, Any] = {
            "eps0":          eps0_safe,
            "growth":        float(growth),
            "growth_source": growth_source,
            "future_pe":     float(future_pe),
            "pe_source":     pe_source,
            "sticker_price": float(sticker_price),
            "mos_price":     float(mos_price),
            "discount_rate": float(discount_rate),
            "horizon_years": int(horizon_years),
            "mos":           float(mos),
            "resolved_at":   datetime.utcnow().isoformat() + "Z",
        }

        output_snapshot: Dict[str, Any] = {
            "valuation": {
                "symbol":       symbol.upper(),
                "companyId":    company_id,
                "currency":     currency,
                "eps0":         eps0_safe,
                "growth":       growth,
                "futurePE":     float(future_pe),
                "futureEPS":    float(future_eps),
                "futurePrice":  float(future_price),
                "discountRate": float(discount_rate),
                "horizonYears": int(horizon_years),
                "mos":          float(mos),
                "stickerPrice": float(sticker_price),
                "mosPrice":     float(mos_price),
            },
            "applicability": {
                "score":              int(metric_score),
                "category":           metric_category,
                "flags":              [f.dict() for f in all_flags],
                "suitabilitySummary": suitability_summary,
            },
            "dataQuality": {
                "freshnessDays": dq_freshness,
                "fallbacksUsed": bool(fallbacks_used),
                "inputDecisions": {
                    **input_decisions,
                    "assumptions": {
                        "discountRate": float(discount_rate),
                        "horizonYears": int(horizon_years),
                        "mos":          float(mos),
                    },
                },
            },
            "suitabilityEvidence": suitability_evidence,
            "lastComputedAt":      now_iso,
        }

        # ── Persist: valuation_runs (audited record) ───────────────────────
        await self.repo.insert_valuation_run(
            company_id=company_id,
            method="rule1",
            run={
                "run_by_user_id":    user_id,
                "input_snapshot":    {
                    "overrides":              overrides.dict(),
                    "dependency_fingerprint": dependency_fingerprint,
                    "resolved":               resolved_inputs,
                },
                "assumption_snapshot": params,
                "output_snapshot":   output_snapshot,
                "data_version_tag":  None,
                "notes":             None,
            },
        )

        return Rule1Response(
            valuation=Rule1Valuation(**output_snapshot["valuation"]),
            applicability=Applicability(**output_snapshot["applicability"]),
            dataQuality=DataQuality(**output_snapshot["dataQuality"]),
        )

    async def get_cached(self, symbol: str) -> Optional[Rule1Response]:
        """
        Pure cache read — no gate logic, no recompute, no DB writes.
        Returns None if no prior valuation exists.
        Used by GET /valuations/{symbol}/rule1 for instant tab loads.
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            return None
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"
 
        cached = await self.repo.get_cached_intrinsic_value(company_id)
        if not cached:
            return None
 
        diagnostics_resp = await self.repo.get_last_method_diagnostics(
            company_id, method="rule1"
        )
 
        valuation = Rule1Valuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            eps0=float(cached.get("current_eps") or 0.0),
            growth=float(cached.get("growth_rate") or 0.0),
            futurePE=float(cached.get("future_pe") or 0.0),
            futureEPS=0.0,
            futurePrice=float(cached.get("future_price") or 0.0),
            discountRate=float(
                diagnostics_resp.get("assumptions", {}).get("discountRate", 0.15)
            ),
            horizonYears=int(
                diagnostics_resp.get("assumptions", {}).get("horizonYears", 10)
            ),
            mos=float(diagnostics_resp.get("assumptions", {}).get("mos", 0.50)),
            stickerPrice=float(cached.get("sticker_price") or 0.0),
            mosPrice=float(cached.get("mos_price") or 0.0),
        )
 
        last_computed = cached.get("last_updated")
 
        if not diagnostics_resp.get("applicability"):
            applicability_payload: Dict[str, Any] = {
                "score": 0, "category": "Caution",
                "flags": [{
                    "code": "R1-NO-AUDIT", "severity": "info",
                    "message": "Cached result; run Recompute for full scorecard.",
                }],
            }
            data_quality_payload: Dict[str, Any] = {
                "freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {},
            }
        else:
            applicability_payload = (
                diagnostics_resp.get("applicability")
                or {"score": 0, "category": "Caution", "flags": []}
            )
            data_quality_payload = (
                diagnostics_resp.get("dataQuality")
                or {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
            )
 
        if isinstance(data_quality_payload.get("freshnessDays"), dict) and last_computed:
            data_quality_payload["freshnessDays"]["lastComputedAt"] = last_computed
 
        return Rule1Response(
            valuation=valuation,
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**data_quality_payload),
        )

    # ── Cached path ────────────────────────────────────────────────────────────

    async def _serve_rule1_cached(
        self,
        company_id: int,
        symbol:     str,
        currency:   str,
    ) -> Rule1Response:
        """
        Hydrate and return the last persisted Rule1 output.
        Falls back to full recompute if no cached snapshot exists.
        """
        cached = await self.repo.get_cached_intrinsic_value(company_id)
        if not cached:
            logger.info(
                "[VALUATION][R1] cached path missing IVA; recomputing for %s", symbol
            )
            return await self.compute_rule1_with_diagnostics(symbol, None, None)

        diagnostics_resp = await self.repo.get_last_method_diagnostics(
            company_id, method="rule1"
        )

        valuation = Rule1Valuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            eps0=float(cached.get("current_eps") or 0.0),
            growth=float(cached.get("growth_rate") or 0.0),
            futurePE=float(cached.get("future_pe") or 0.0),
            futureEPS=0.0,
            futurePrice=float(cached.get("future_price") or 0.0),
            discountRate=float(
                diagnostics_resp.get("assumptions", {}).get("discountRate", 0.15)
            ),
            horizonYears=int(
                diagnostics_resp.get("assumptions", {}).get("horizonYears", 10)
            ),
            mos=float(diagnostics_resp.get("assumptions", {}).get("mos", 0.50)),
            stickerPrice=float(cached.get("sticker_price") or 0.0),
            mosPrice=float(cached.get("mos_price") or 0.0),
        )

        last_computed = cached.get("last_updated")

        if not diagnostics_resp.get("applicability"):
            applicability_payload: Dict[str, Any] = {
                "score":    0,
                "category": "Caution",
                "flags": [{
                    "code":           "R1-NO-AUDIT",
                    "severity":       "info",
                    "message":        (
                        "No prior valuation run found; suitability scorecard "
                        "not available on cached path."
                    ),
                    "recommendation": "Run Recompute once to generate an audited scorecard.",
                }],
            }
            data_quality_payload: Dict[str, Any] = {
                "freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {},
            }
        else:
            applicability_payload = (
                diagnostics_resp.get("applicability")
                or {"score": 0, "category": "Caution", "flags": []}
            )
            data_quality_payload = (
                diagnostics_resp.get("dataQuality")
                or {"freshnessDays": {}, "fallbacksUsed": False, "inputDecisions": {}}
            )

        if isinstance(data_quality_payload.get("freshnessDays"), dict) and last_computed:
            data_quality_payload["freshnessDays"]["lastComputedAt"] = last_computed

        return Rule1Response(
            valuation=valuation,
            applicability=Applicability(**applicability_payload),
            dataQuality=DataQuality(**data_quality_payload),
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _has_rule1_overrides(overrides: Rule1RequestOverrides) -> bool:
        return any([
            overrides.forceGrowth    is not None,
            overrides.forceFuturePE  is not None,
            overrides.discountRate   is not None,
            overrides.horizonYears   is not None,
            overrides.marginOfSafety is not None,
        ])

    @staticmethod
    def _cagr(v0: float, vN: float, years: int) -> Optional[float]:
        if years <= 0 or v0 <= 0 or vN <= 0:
            return None
        try:
            return (vN / v0) ** (1.0 / years) - 1.0
        except Exception:
            return None

    def _cagr_from_series(
        self, rows: List[Dict[str, Any]], key: str
    ) -> Optional[float]:
        vals:  List[float] = []
        years: List[int]   = []
        for r in rows:
            v = r.get(key)
            y = r.get("fiscal_year")
            if v is None or y is None:
                continue
            try:
                vals.append(float(v))
                years.append(int(y))
            except Exception:
                continue

        if len(vals) < 2 or len(years) < 2:
            return None

        v0, vN   = vals[0], vals[-1]
        n_years  = years[-1] - years[0]
        if n_years < 3:
            return None

        return self._cagr(v0, vN, n_years)