# application/services/valuation_service.py
from __future__ import annotations

import math
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from domain.models.valuation_rule1 import (
    Rule1RequestOverrides,
    Rule1Valuation,
    Rule1Response,
    DiagnosticFlag,
    Applicability,
    DataQuality,
)
from infrastructure.repositories.valuation_repository import ValuationRepository
from application.services.recompute_guard import RecomputeGuard
from database import supabase  # for best-effort hydration of diagnostics on cached path

logger = logging.getLogger(__name__)

# Sector heuristics for diagnostics
SECTOR_FIN = {"Financial Services", "Banks", "Insurance", "Diversified Financials"}
SECTOR_CYCL = {"Energy", "Materials"}

# Weights for suitability score
SEVERITY_WEIGHT = {"critical": 40, "high": 25, "medium": 12, "low": 6, "info": 2}


def _as_date(d: Any) -> Optional[date]:
    """
    Normalize Supabase DATE payloads (which may be ISO strings) into datetime.date.
    Returns None on failure.
    """
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


class ValuationService:
    """
    Computes intrinsic value models (Rule #1 for now) and emits diagnostics.
    Provides a cached-vs-recompute entry point using RecomputeGuard.
    """

    def __init__(self, repo: ValuationRepository, guard: RecomputeGuard):
        self.repo = repo
        self.guard = guard

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------
    async def compute_rule1_if_stale(
        self,
        symbol: str,
        user_id: Optional[int],
        overrides: Optional[Rule1RequestOverrides] = None,
        force: bool = False,
    ) -> Rule1Response:
        """
        Cached-vs-Recompute entry point for:
          C) Manual API requests
          A) Slow-path ingestion (with force=True)
          B) Scheduler hooks (force=False)

        Behavior:
          - If 'force': recompute
          - Else: compare last valuation TS vs latest dependency TS; if deps newer -> recompute
          - Else: return cached IVA (and hydrate diagnostics from last run if available)
        """
        overrides = overrides or Rule1RequestOverrides()

        # Resolve company context
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = ctx["company_id"]
        currency = ctx.get("currency") or "USD"

        # Decide
        decision = await self.guard.cached_or_recompute(company_id=company_id, force=force)

        # If we should recompute, do it
        if decision.should_recompute:
            logger.info(
                "[VALUATION][R1] recompute: company=%s symbol=%s reason=%s dep_ts=%s last_ts=%s",
                company_id, symbol, decision.reason, decision.latest_dependency_at, decision.last_valuation_at
            )
            return await self.compute_rule1_with_diagnostics(symbol, user_id, overrides)

        # Else: return cached IVA (hydrate from last valuation run if possible)
        logger.info(
            "[VALUATION][R1] cached: company=%s symbol=%s dep_ts=%s last_ts=%s",
            company_id, symbol, decision.latest_dependency_at, decision.last_valuation_at
        )
        cached = await self.repo.get_cached_intrinsic_value(company_id)
        if not cached:
            # No IVA persisted yet—fallback to compute now
            logger.info("[VALUATION][R1] cached path missing IVA; recomputing for %s", symbol)
            return await self.compute_rule1_with_diagnostics(symbol, user_id, overrides)

        # Try to hydrate diagnostics from last valuation_runs output_snapshot (optional best effort)
        diagnostics_resp = await self._hydrate_diagnostics_from_last_run(company_id)

        valuation = Rule1Valuation(
            symbol=symbol.upper(),
            companyId=company_id,
            currency=currency,
            eps0=float(cached.get("current_eps") or 0.0),
            growth=float(cached.get("growth_rate") or 0.0),
            futurePE=float(cached.get("future_pe") or 0.0),
            futureEPS=0.0,   # future EPS not stored in IVA; only recompute path fills it
            futurePrice=float(cached.get("future_price") or 0.0),
            discountRate=diagnostics_resp.get("assumptions", {}).get("discountRate", 0.15),
            horizonYears=diagnostics_resp.get("assumptions", {}).get("horizonYears", 10),
            mos=diagnostics_resp.get("assumptions", {}).get("mos", 0.50),
            stickerPrice=float(cached.get("sticker_price") or 0.0),
            mosPrice=float(cached.get("mos_price") or 0.0),
        )

        # Applicability/DataQuality
        last_computed = cached.get("last_updated")
        applicability = diagnostics_resp.get("applicability") or {
            "score": 100,
            "category": "Good",
            "flags": []
        }
        data_quality = diagnostics_resp.get("dataQuality") or {
            "freshnessDays": {},
            "fallbacksUsed": False,
            "inputDecisions": {}
        }

        # Ensure Pydantic models
        resp = Rule1Response(
            valuation=valuation,
            applicability=Applicability(**applicability),
            dataQuality=DataQuality(**{
                **data_quality,
                "freshnessDays": data_quality.get("freshnessDays", {}),
            }),
        )

        # Attach lastComputedAt into dataQuality.freshnessDays (UI reference)
        if last_computed:
            if isinstance(resp.dataQuality.freshnessDays, dict):
                resp.dataQuality.freshnessDays["lastComputedAt"] = last_computed

        return resp

    async def compute_rule1_with_diagnostics(
        self,
        symbol: str,
        user_id: Optional[int],
        overrides: Optional[Rule1RequestOverrides] = None,
    ) -> Rule1Response:
        """
        Compute Phil Town's Rule #1 (sticker + MOS) with suitability diagnostics,
        persist IVA + valuation_runs, and return FE-ready response.
        """
        overrides = overrides or Rule1RequestOverrides()

        # ------------------------------------------------------------------
        # Context & Parameters
        # ------------------------------------------------------------------
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found in companies.")
        company_id = ctx["company_id"]
        currency = ctx.get("currency") or "USD"
        sector = ctx.get("sector")
        industry = ctx.get("industry")

        params = await self.repo.get_method_params(company_id)
        discount_rate = float(overrides.discountRate if overrides.discountRate is not None else params.get("discount_rate", 0.15))
        horizon_years = int(overrides.horizonYears if overrides.horizonYears is not None else params.get("horizon_years", 10))
        mos = float(overrides.marginOfSafety if overrides.marginOfSafety is not None else params.get("margin_of_safety", 0.50))

        # ------------------------------------------------------------------
        # Resolve EPS0 (prefer trailing EPS; fallback TTM)
        # ------------------------------------------------------------------
        flags: List[DiagnosticFlag] = []
        dq_freshness: Dict[str, Optional[int]] = {}
        input_decisions: Dict[str, Any] = {}
        fallbacks_used = False

        trailing = await self.repo.get_trailing_eps(company_id)
        eps0: Optional[float] = None
        eps_snapshot_date: Optional[date] = None

        prefer_trailing = bool(params.get("prefer_trailing_eps", True))
        if trailing and trailing.get("trailing_eps") is not None and prefer_trailing:
            eps0 = float(trailing["trailing_eps"])
            eps_snapshot_date = _as_date(trailing.get("snapshot_date"))
            if eps_snapshot_date:
                dq_freshness["trailingEPS"] = (date.today() - eps_snapshot_date).days
            else:
                dq_freshness["trailingEPS"] = None
        else:
            eps0 = await self.repo.compute_ttm_eps_fallback(company_id)
            fallbacks_used = True
            dq_freshness["trailingEPS"] = None

        if eps0 is None:
            flags.append(DiagnosticFlag(
                code="R1-NOEPS", severity="high",
                message="EPS not available; valuation relies on fallbacks or may be low confidence."
            ))
        elif eps0 <= 0.05:
            flags.append(DiagnosticFlag(
                code="R1-NEGEPS", severity="critical",
                message="Negative or near-zero EPS—Rule #1 is less suitable."
            ))

        input_decisions["eps0"] = {
            "value": eps0,
            "source": "company_summary.trailing_eps" if eps_snapshot_date else "ttm_fallback",
            "snapshotDate": eps_snapshot_date.isoformat() if eps_snapshot_date else None,
        }

        # ------------------------------------------------------------------
        # Resolve Growth (g) with fallbacks & clamping
        # ------------------------------------------------------------------
        growth: Optional[float] = None
        growth_source: str = ""
        prefer_forecast = bool(params.get("prefer_forecast_growth", True))

        if overrides.forceGrowth is not None:
            growth = float(overrides.forceGrowth)
            growth_source = "override"
        else:
            # Forecast growth
            if prefer_forecast:
                growth_row = await self.repo.get_eps_forecast_growth(company_id)
                if growth_row and growth_row.get("estimate_eps_growth") is not None:
                    growth = float(growth_row["estimate_eps_growth"])
                    growth_source = "earnings_forecast.estimate_eps_growth"
                    rep_date = _as_date(growth_row.get("report_date"))
                    dq_freshness["epsForecast"] = (date.today() - rep_date).days if rep_date else None

            # EPS CAGR fallback
            if growth is None:
                eps_hist = await self.repo.get_eps_history(company_id)
                g_eps = self._cagr_from_series(eps_hist, key="eps")
                if g_eps is not None:
                    growth = g_eps
                    growth_source = "eps_cagr_approx"

            # Revenue CAGR fallback
            if growth is None:
                rev_hist = await self.repo.get_revenue_history(company_id)
                g_rev = self._cagr_from_series(rev_hist, key="revenue")
                if g_rev is not None:
                    growth = g_rev
                    growth_source = "revenue_cagr_approx"
                    fallbacks_used = True

            # Industry median growth
            if growth is None:
                im = await self.repo.get_industry_multiples(sector, industry) if (sector and industry) else None
                if im and im.get("median_eps_growth") is not None:
                    growth = float(im["median_eps_growth"])
                    growth_source = "industry.median_eps_growth"
                    fallbacks_used = True

            # Conservative default
            if growth is None:
                growth = 0.10
                growth_source = "conservative_default"
                fallbacks_used = True

        # Clamp growth
        g_min = float(params.get("growth_clamp_min", 0.02))
        g_max = float(params.get("growth_clamp_max", 0.25))
        growth_raw = growth
        growth = self._clamp(growth or 0.0, g_min, g_max)

        if growth_raw is not None and growth_raw > growth:
            flags.append(DiagnosticFlag(
                code="R1-GCLAMP-HIGH", severity="low",
                message=f"Growth input {growth_raw:.2%} clamped to {g_max:.2%} for conservatism."
            ))
        if growth_raw is not None and growth_raw < growth:
            flags.append(DiagnosticFlag(
                code="R1-GCLAMP-LOW", severity="low",
                message=f"Growth input {growth_raw:.2%} raised to {g_min:.2%} minimum."
            ))

        input_decisions["growth"] = {
            "valueRaw": growth_raw,
            "valueClamped": growth,
            "source": growth_source,
        }

        # ------------------------------------------------------------------
        # Future PE (guardrails)
        # ------------------------------------------------------------------
        if overrides.forceFuturePE is not None:
            future_pe = float(overrides.forceFuturePE)
            pe_source = "override"
        else:
            pe_floor = float(params.get("pe_floor", 8))
            pe_cap = float(params.get("pe_cap", 50))
            two_x_growth_rule = min(2 * (growth * 100), pe_cap)  # 2 × growth% with cap
            rule_pe = max(pe_floor, two_x_growth_rule)
            pe_source = "2xGrowthRule"

            im = await self.repo.get_industry_multiples(sector, industry) if (sector and industry) else None
            if params.get("use_industry_pe_if_lower", True) and im and im.get("median_pe") is not None:
                industry_pe = float(im["median_pe"])
                if industry_pe < rule_pe:
                    future_pe = industry_pe
                    pe_source = "industry_median_pe"
                    flags.append(DiagnosticFlag(
                        code="R1-PERULE", severity="info",
                        message="Used industry median PE for conservatism.",
                        evidence={"industryMedianPE": industry_pe, "twoXGrowthRulePE": rule_pe},
                    ))
                else:
                    future_pe = rule_pe
            else:
                future_pe = rule_pe

        input_decisions["futurePE"] = {"selected": future_pe, "rule": pe_source}

        # ------------------------------------------------------------------
        # Compute Rule #1 values
        # ------------------------------------------------------------------
        eps0_safe = float(eps0 or 0.0)
        future_eps = eps0_safe * ((1 + growth) ** horizon_years) if eps0_safe > 0 else 0.0
        future_price = future_eps * future_pe
        denominator = (1 + discount_rate) ** horizon_years
        sticker_price = future_price / denominator if denominator > 0 else 0.0
        mos_price = sticker_price * (1 - mos)

        # ------------------------------------------------------------------
        # Diagnostics & Suitability
        # ------------------------------------------------------------------
        # Sector flags
        if sector in SECTOR_FIN:
            flags.append(DiagnosticFlag(
                code="R1-SECTOR-FIN", severity="high",
                message="Financial sector—Rule #1 may be less suitable.",
                recommendation="Consider Residual Income or dividend-based models."
            ))
        if sector in SECTOR_CYCL:
            flags.append(DiagnosticFlag(
                code="R1-SECTOR-CYCL", severity="medium",
                message="Cyclical sector—earnings swing with commodity cycles.",
                recommendation="Use conservative growth and a wider MOS."
            ))

        # EPS volatility (from earnings history)
        eps_hist = await self.repo.get_eps_history(company_id)
        vol = self._eps_volatility(eps_hist, key="eps")
        if vol and vol["stdev"] > float(params.get("volatility_stdev_threshold", 0.30)):
            flags.append(DiagnosticFlag(
                code="R1-VOL", severity="medium",
                message="Earnings volatile—wide uncertainty.",
                evidence=vol,
                recommendation="Consider scenario ranges or DCF."
            ))

        # Dilution / Buybacks (shares CAGR over range)
        shares_hist = await self.repo.get_shares_history(company_id)
        scagr = self._shares_cagr(shares_hist)
        if scagr is not None:
            if scagr > float(params.get("dilution_cagr_high", 0.10)):
                flags.append(DiagnosticFlag(
                    code="R1-DILUTION", severity="medium",
                    message="Significant dilution—EPS growth may be distorted.",
                    evidence={"sharesCAGR": scagr},
                ))
            elif scagr < float(params.get("buyback_cagr_low", -0.05)):
                flags.append(DiagnosticFlag(
                    code="R1-BUYBACKS", severity="low",
                    message="Heavy buybacks—EPS may be inflated vs fundamentals.",
                    evidence={"sharesCAGR": scagr},
                ))

        # Splits after EPS snapshot (may indicate EPS not adjusted)
        if eps_snapshot_date:
            split_cnt = await self.repo.get_recent_split_count_after(company_id, eps_snapshot_date)
            if split_cnt > 0:
                flags.append(DiagnosticFlag(
                    code="R1-SPLIT", severity="medium",
                    message="Recent split after EPS snapshot—EPS may be unadjusted.",
                    evidence={
                        "splitCount": split_cnt,
                        "epsSnapshotDate": eps_snapshot_date.isoformat()
                    },
                ))

        # Freshness warnings
        stale_eps_days = int(params.get("stale_days_eps", 30))
        stale_fc_days = int(params.get("stale_days_forecast", 90))
        if dq_freshness.get("trailingEPS") and dq_freshness["trailingEPS"] > stale_eps_days:
            flags.append(DiagnosticFlag(
                code="R1-STALE", severity="medium",
                message=f"EPS snapshot is {dq_freshness['trailingEPS']} days old."
            ))
        if dq_freshness.get("epsForecast") and dq_freshness["epsForecast"] > stale_fc_days:
            flags.append(DiagnosticFlag(
                code="R1-STALE", severity="low",
                message=f"EPS forecast is {dq_freshness['epsForecast']} days old."
            ))

        # Earnings proximity note (UI info only)
        next_earn = await self.repo.get_next_earnings_date(company_id)
        warn_days = int(params.get("warn_earnings_within_days", 14))
        if next_earn:
            try:
                # repo already normalizes to date; this is a defensive guard
                next_earn_d = _as_date(next_earn)
                if next_earn_d:
                    delta = (next_earn_d - date.today()).days
                    if 0 <= delta <= warn_days:
                        flags.append(DiagnosticFlag(
                            code="R1-EVENT", severity="info",
                            message=f"Earnings in {delta} days; valuation may change materially.",
                            evidence={"nextEarningsDate": next_earn_d.isoformat()},
                        ))
            except Exception:
                pass

        # Score & category
        score = self._score(flags)
        category = self._category(score)

        # ------------------------------------------------------------------
        # Persist IVA + valuation_runs
        # ------------------------------------------------------------------
        await self.repo.upsert_intrinsic_value_analysis(
            company_id,
            {
                "growth_rate": growth,
                "current_eps": eps0_safe,
                "future_pe": future_pe,
                "future_price": future_price,
                "sticker_price": sticker_price,
                "mos_price": mos_price,
            },
        )

        output_snapshot = {
            "valuation": {
                "symbol": symbol.upper(),
                "companyId": company_id,
                "currency": currency,
                "eps0": eps0_safe,
                "growth": growth,
                "futurePE": future_pe,
                "futureEPS": future_eps,
                "futurePrice": future_price,
                "discountRate": discount_rate,
                "horizonYears": horizon_years,
                "mos": mos,
                "stickerPrice": sticker_price,
                "mosPrice": mos_price,
            },
            "applicability": {
                "score": score,
                "category": category,
                "flags": [f.dict() for f in flags],
            },
            "dataQuality": {
                "freshnessDays": dq_freshness,
                "fallbacksUsed": fallbacks_used,
                "inputDecisions": {
                    **input_decisions,
                    "assumptions": {
                        "discountRate": discount_rate,
                        "horizonYears": horizon_years,
                        "mos": mos,
                    },
                },
                "lastComputedAt": datetime.utcnow().isoformat() + "Z",
            },
        }

        await self.repo.insert_valuation_run(
            company_id,
            {
                "run_by_user_id": user_id,
                "input_snapshot": {"overrides": overrides.dict()},
                "assumption_snapshot": params,
                "output_snapshot": output_snapshot,
                "data_version_tag": None,
                "notes": None,
            },
        )

        # ------------------------------------------------------------------
        # Response
        # ------------------------------------------------------------------
        return Rule1Response(
            valuation=Rule1Valuation(**output_snapshot["valuation"]),
            applicability=Applicability(**output_snapshot["applicability"]),
            dataQuality=DataQuality(**{
                "freshnessDays": output_snapshot["dataQuality"]["freshnessDays"],
                "fallbacksUsed": output_snapshot["dataQuality"]["fallbacksUsed"],
                "inputDecisions": output_snapshot["dataQuality"]["inputDecisions"],
            }),
        )

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------
    @staticmethod
    def _clamp(val: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, val))

    @staticmethod
    def _score(flags: List[DiagnosticFlag]) -> int:
        deduct = sum(SEVERITY_WEIGHT.get(f.severity, 0) for f in flags)
        return max(0, 100 - deduct)

    @staticmethod
    def _category(score: int) -> str:
        if score >= 75:
            return "Good"
        if score >= 50:
            return "Caution"
        return "Poor"

    @staticmethod
    def _cagr(v0: float, vN: float, years: int) -> Optional[float]:
        if v0 is None or vN is None or years is None or years <= 0 or v0 <= 0:
            return None
        try:
            return (vN / v0) ** (1.0 / years) - 1.0
        except Exception:
            return None

    def _cagr_from_series(self, rows: List[Dict[str, Any]], key: str) -> Optional[float]:
        """
        rows: list of dicts with keys [fiscal_year, <key>]
        """
        vals = [r.get(key) for r in rows if r.get(key) is not None]
        years = [r.get("fiscal_year") for r in rows if r.get(key) is not None]
        if len(vals) < 2:
            return None
        v0, vN = float(vals[0]), float(vals[-1])
        n = (years[-1] - years[0]) if years and (years[-1] is not None and years[0] is not None) else len(vals) - 1
        if n < 3:
            return None
        return self._cagr(v0, vN, n)

    @staticmethod
    def _eps_volatility(rows: List[Dict[str, Any]], key: str) -> Optional[Dict[str, float]]:
        """
        Compute YoY EPS growth stdev for volatility diagnostic.
        rows: [{'fiscal_year': int, 'eps': float}, ...] ordered ascending.
        """
        vals = [float(r.get(key)) for r in rows if r.get(key) is not None]
        if len(vals) < 3:
            return None
        growths: List[float] = []
        for i in range(1, len(vals)):
            prev, cur = vals[i - 1], vals[i]
            if prev and prev != 0:
                growths.append((cur - prev) / prev)
        if len(growths) < 2:
            return None
        avg = sum(growths) / len(growths)
        var = sum((g - avg) ** 2 for g in growths) / (len(growths) - 1)
        stdev = math.sqrt(var)
        return {"avg": avg, "stdev": stdev, "n": float(len(growths))}

    def _shares_cagr(self, rows: List[Dict[str, Any]]) -> Optional[float]:
        """
        CAGR of diluted shares using fiscal year endpoints.
        """
        vals = [r.get("shares_outstanding_diluted") for r in rows if r.get("shares_outstanding_diluted")]
        years = [r.get("fiscal_year") for r in rows if r.get("shares_outstanding_diluted")]
        if len(vals) < 2:
            return None
        s0, sN = float(vals[0]), float(vals[-1])
        n = max(0, (years[-1] - years[0])) if (years and years[0] is not None and years[-1] is not None) else len(vals) - 1
        if n < 3:
            return None
        return self._cagr(s0, sN, n)

    async def _hydrate_diagnostics_from_last_run(self, company_id: int) -> Dict[str, Any]:
        """
        Best-effort: fetch last valuation_runs.output_snapshot for method='rule1'
        to hydrate applicability, dataQuality, and assumptions on cached returns.

        Returns {} if not found or on failure.
        """
        try:
            resp = (
                supabase.table("valuation_runs")
                .select("output_snapshot")
                .eq("company_id", company_id)
                .eq("method", "rule1")
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = resp.data[0] if resp and getattr(resp, "data", None) else None
            if not row:
                return {}
            snapshot = row.get("output_snapshot") or {}
            # Pull out only what we need
            app = snapshot.get("applicability") or {}
            dq = snapshot.get("dataQuality") or {}
            assumptions = dq.get("inputDecisions", {}).get("assumptions", {})
            return {
                "applicability": app,
                "dataQuality": dq,
                "assumptions": assumptions,
            }
        except Exception:
            # If supabase is not imported here, you can move this logic into the repository later.
            return {}