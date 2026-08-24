# backend/application/services/magic_formula_service.py
"""
Magic Formula (Greenblatt) Analysis Service.

Cached in valuation_runs (method='magic_formula') with a 24-hour staleness window.
No user overrides — the formula has no tunable parameters.

Earnings Yield = TTM EBIT / Enterprise Value
Return on Capital = TTM EBIT / (NWC + NFA)

NWC = (current_assets - cash) - (current_liabilities - short_term_debt)
NFA = property_plant_equipment_net  [goodwill and intangibles excluded]

Sector exclusions (Greenblatt's own guidance):
  financials, utilities, REITs — capital structures break the formula.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from application.services.ai_service import generate_suitability_summary
from domain.models.analysis_magic_formula import (
    DiagnosticFlag,
    MagicFormulaApplicability,
    MagicFormulaDataQuality,
    MagicFormulaIndustryContext,
    MagicFormulaInputs,
    MagicFormulaResponse,
    MagicFormulaValuation,
)
from infrastructure.repositories.analysis_repository import AnalysisRepository
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import safe_float
from shared.time_utils import now_iso, now_utc, parse_db_timestamp

logger = logging.getLogger(__name__)

_CACHE_MAX_AGE_HOURS = 24

_EXCLUDED_SECTORS = {
    "Financial Services",
    "Financials",
    "Utilities",
    "Real Estate",
}
_EXCLUDED_SECTOR_KEYWORDS = ["bank", "insur", "reit", "utility", "utilities"]


class MagicFormulaService:
    def __init__(
        self,
        valuation_repo: ValuationRepository,
        analysis_repo: AnalysisRepository,
    ) -> None:
        self._repo = valuation_repo
        self._arepo = analysis_repo

    # ── Public entry ──────────────────────────────────────────────────────────

    async def get_magic_formula(
        self, symbol: str, force: bool = False
    ) -> MagicFormulaResponse:
        ctx = await self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"
        sector = ctx.get("sector") or ""
        industry = ctx.get("industry") or ""

        if not force:
            cached = await self._serve_cached(company_id, symbol, currency)
            if cached:
                return cached

        return await self._compute_and_cache(
            symbol, company_id, currency, sector, industry
        )

    # ── Cache read ────────────────────────────────────────────────────────────

    async def _serve_cached(
        self, company_id: int, symbol: str, currency: str
    ) -> MagicFormulaResponse | None:
        snap = await self._repo.get_last_output_snapshot(company_id, "magic_formula")
        if not snap:
            return None
        last_computed = snap.get("lastComputedAt")
        if last_computed:
            try:
                ts = parse_db_timestamp(last_computed)
                age = now_utc() - ts
                if age > timedelta(hours=_CACHE_MAX_AGE_HOURS):
                    return None
            except Exception:
                return None
        return self._hydrate_response(snap)

    @staticmethod
    def _hydrate_response(snap: dict[str, Any]) -> MagicFormulaResponse | None:
        try:
            return MagicFormulaResponse(**snap["response"])
        except Exception as e:
            logger.warning("Magic Formula cache hydration failed: %s", e)
            return None

    # ── Full computation ──────────────────────────────────────────────────────

    async def _compute_and_cache(
        self,
        symbol: str,
        company_id: int,
        currency: str,
        sector: str,
        industry: str,
    ) -> MagicFormulaResponse:
        now_str = now_iso()

        # ── Parallel data fetch ────────────────────────────────────────────────
        (
            ttm_ebit_result,
            ev,
            bs_inputs,
            ratios,
            industry_mults,
            current_price,
        ) = await asyncio.gather(
            self._arepo.get_ttm_ebit(company_id),
            self._arepo.get_enterprise_value_latest(company_id),
            self._arepo.get_balance_sheet_mf_inputs(company_id),
            self._repo.get_derived_metrics_latest(company_id),
            self._arepo.get_industry_multiples_full(sector, industry),
            self._repo.get_current_market_price(company_id),
        )

        # ttm_ebit_result is a float (or None)
        ttm_ebit = safe_float(ttm_ebit_result)

        # ── Determine TTM source metadata ──────────────────────────────────────
        # We can't easily know how many quarters were used without a separate
        # query; the AnalysisRepository.get_ttm_ebit() logs this.
        # We expose a conservative label here.
        ttm_source = "ttm_quarterly"
        ttm_quarters = 4  # best-case assumption; actual may be less

        # ── Balance sheet inputs ───────────────────────────────────────────────
        bs = bs_inputs or {}
        current_assets = safe_float(bs.get("current_assets"))
        cash = safe_float(bs.get("cash_and_cash_equivalents"))
        current_liabilities = safe_float(bs.get("current_liabilities"))
        short_term_debt = safe_float(bs.get("short_term_debt")) or 0.0
        ppe_net = safe_float(bs.get("property_plant_equipment_net"))
        goodwill = safe_float(bs.get("goodwill"))
        intangibles = safe_float(bs.get("intangible_assets"))
        bs_fy = bs.get("fiscal_year")

        # ── Greenblatt NWC and NFA ────────────────────────────────────────────
        nwc: float | None = None
        nfa: float | None = None
        invested_capital_mf: float | None = None

        if (
            current_assets is not None
            and cash is not None
            and current_liabilities is not None
        ):
            excess_cash_excluded = cash
            operating_ca = current_assets - excess_cash_excluded
            operating_cl = current_liabilities - short_term_debt
            nwc = operating_ca - operating_cl

        if ppe_net is not None:
            nfa = ppe_net   # goodwill/intangibles already separate columns

        if nwc is not None and nfa is not None:
            invested_capital_mf = nwc + nfa

        # ── Earnings Yield and ROC ────────────────────────────────────────────
        earnings_yield: float | None = None
        roc: float | None = None

        if ttm_ebit is not None and ev and ev > 0:
            earnings_yield = ttm_ebit / ev

        if ttm_ebit is not None and invested_capital_mf and invested_capital_mf > 0:
            roc = ttm_ebit / invested_capital_mf

        # ROIC cross-check from financial_ratios
        roic_from_ratios = safe_float((ratios or {}).get("roic"))
        roic_delta_note: str | None = None
        if roc is not None and roic_from_ratios is not None:
            delta = abs(roc - roic_from_ratios)
            if delta > 0.05:
                roic_delta_note = (
                    f"Greenblatt ROC ({roc:.1%}) differs from stored ROIC "
                    f"({roic_from_ratios:.1%}) by {delta:.1%}. "
                    "ROIC uses NOPAT/invested_capital; Greenblatt uses EBIT/(NWC+NFA)."
                )

        # ── Sector applicability ──────────────────────────────────────────────
        flags, excluded, exclusion_reason = self._assess_applicability(
            sector, industry, ttm_ebit, earnings_yield, roc, ev
        )

        score = self._compute_applicability_score(
            excluded, earnings_yield, roc, ttm_ebit, ev
        )
        category = (
            "Not Applicable" if excluded
            else "Applicable" if score >= 60
            else "Caution"
        )

        suitability_summary = await generate_suitability_summary(
            symbol=symbol,
            method="magic_formula",
            score=score,
            category=category,
            flags=[f.dict() for f in flags],
            evidence={
                "earnings_yield": earnings_yield,
                "return_on_capital": roc,
                "enterprise_value": ev,
                "ttm_ebit": ttm_ebit,
                "sector": sector,
                "industry": industry,
            },
            valuation_inputs={
                "currency": currency,
                "earnings_yield_pct": round(earnings_yield * 100, 2) if earnings_yield else None,
                "roc_pct": round(roc * 100, 2) if roc else None,
            },
            input_decisions={},
        )

        # ── Industry context ──────────────────────────────────────────────────
        im = industry_mults or {}
        avg_ev_ebitda = safe_float(im.get("avg_ev_ebitda"))
        implied_ey = (1.0 / avg_ev_ebitda) if (avg_ev_ebitda and avg_ev_ebitda > 0) else None

        ey_vs_industry: str | None = None
        ey_premium: float | None = None
        if earnings_yield is not None and implied_ey is not None:
            delta_pct = (earnings_yield - implied_ey) * 100
            ey_premium = round(delta_pct, 2)
            if delta_pct > 1:
                ey_vs_industry = "above"
            elif delta_pct < -1:
                ey_vs_industry = "below"
            else:
                ey_vs_industry = "inline"

        # ── Data quality ──────────────────────────────────────────────────────
        snapshot_date = im.get("calculation_date")

        dq = MagicFormulaDataQuality(
            ttm_coverage="full_4q" if ttm_quarters == 4 else f"partial_{ttm_quarters}q",
            ev_source="company_summary" if ev else "unavailable",
            bs_fiscal_year=bs_fy,
            days_since_bs_update=None,   # would require an extra query; omit for now
            days_since_ev_snapshot=None,
            fallbacks_used=(ttm_ebit is None or ev is None),
            last_computed_at=now_str,
        )

        # ── Assemble response ─────────────────────────────────────────────────
        response = MagicFormulaResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            currency=currency,
            inputs=MagicFormulaInputs(
                ttm_ebit=round(ttm_ebit, 2) if ttm_ebit is not None else None,
                ttm_ebit_source=ttm_source,
                ttm_quarters_used=ttm_quarters,
                enterprise_value=round(ev, 2) if ev else None,
                current_assets=round(current_assets, 2) if current_assets is not None else None,
                cash_and_equivalents=round(cash, 2) if cash is not None else None,
                current_liabilities=round(current_liabilities, 2) if current_liabilities is not None else None,
                short_term_debt=round(short_term_debt, 2),
                ppe_net=round(ppe_net, 2) if ppe_net is not None else None,
                goodwill_excluded=round(goodwill, 2) if goodwill is not None else None,
                intangibles_excluded=round(intangibles, 2) if intangibles is not None else None,
                fiscal_year_bs=bs_fy,
            ),
            valuation=MagicFormulaValuation(
                earnings_yield=round(earnings_yield, 6) if earnings_yield is not None else None,
                return_on_capital=round(roc, 6) if roc is not None else None,
                net_working_capital=round(nwc, 2) if nwc is not None else None,
                net_fixed_assets=round(nfa, 2) if nfa is not None else None,
                invested_capital_mf=round(invested_capital_mf, 2) if invested_capital_mf is not None else None,
                roic_from_ratios=round(roic_from_ratios, 6) if roic_from_ratios is not None else None,
                roic_delta_note=roic_delta_note,
                earnings_yield_pct=round(earnings_yield * 100, 4) if earnings_yield is not None else None,
                return_on_capital_pct=round(roc * 100, 4) if roc is not None else None,
            ),
            industry_context=MagicFormulaIndustryContext(
                sector=sector or None,
                industry=industry or None,
                avg_ev_ebitda=round(avg_ev_ebitda, 2) if avg_ev_ebitda else None,
                implied_industry_earnings_yield=round(implied_ey, 4) if implied_ey else None,
                earnings_yield_vs_industry=ey_vs_industry,
                earnings_yield_premium_pct=ey_premium,
                avg_eps_growth=safe_float(im.get("avg_eps_growth")),
                sample_size=im.get("sample_size"),
                calculation_date=str(snapshot_date) if snapshot_date else None,
            ),
            applicability=MagicFormulaApplicability(
                score=score,
                category=category,
                excluded=excluded,
                exclusion_reason=exclusion_reason,
                flags=flags,
                suitability_summary=suitability_summary,
            ),
            data_quality=dq,
        )

        # ── Persist to valuation_runs ─────────────────────────────────────────
        await self._repo.insert_valuation_run(
            company_id=company_id,
            method="magic_formula",
            run={
                "run_by_user_id": None,
                "input_snapshot": {
                    "ttm_ebit": ttm_ebit,
                    "enterprise_value": ev,
                    "nwc": nwc,
                    "nfa": nfa,
                },
                "assumption_snapshot": {},
                "output_snapshot": {
                    "response": response.dict(),
                    "lastComputedAt": now_str,
                },
                "data_version_tag": None,
                "notes": None,
            },
        )

        return response

    # ── Applicability scoring ─────────────────────────────────────────────────

    @staticmethod
    def _assess_applicability(
        sector: str,
        industry: str,
        ttm_ebit: float | None,
        earnings_yield: float | None,
        roc: float | None,
        ev: float | None,
    ) -> tuple:
        flags: list[DiagnosticFlag] = []
        excluded = False
        exclusion_reason: str | None = None

        sector_lower = (sector or "").lower()
        industry_lower = (industry or "").lower()

        if sector in _EXCLUDED_SECTORS or any(
            kw in sector_lower or kw in industry_lower
            for kw in _EXCLUDED_SECTOR_KEYWORDS
        ):
            excluded = True
            exclusion_reason = (
                f"Greenblatt explicitly excludes {sector} companies — "
                "capital structures make Earnings Yield and ROC non-comparable."
            )
            flags.append(DiagnosticFlag(
                code="MF-SECTOR-EXCLUDED",
                severity="critical",
                message=exclusion_reason,
                recommendation="Use sector-specific valuation methods (e.g. P/B for financials).",
            ))

        if ttm_ebit is not None and ttm_ebit <= 0:
            flags.append(DiagnosticFlag(
                code="MF-NEGATIVE-EBIT",
                severity="high",
                message=f"TTM EBIT is negative ({ttm_ebit:,.0f}) — Earnings Yield is not meaningful.",
                recommendation="Formula only applicable to profitable companies.",
            ))

        if ev is None:
            flags.append(DiagnosticFlag(
                code="MF-NO-EV",
                severity="high",
                message="Enterprise value not available — cannot compute Earnings Yield.",
            ))

        if roc is not None and roc > 2.0:
            flags.append(DiagnosticFlag(
                code="MF-ROC-EXTREME",
                severity="medium",
                message=f"ROC of {roc:.0%} is unusually high — verify NWC and NFA inputs.",
                recommendation="Asset-light businesses can show extreme ROC; review balance sheet inputs.",
            ))

        return flags, excluded, exclusion_reason

    @staticmethod
    def _compute_applicability_score(
        excluded: bool,
        earnings_yield: float | None,
        roc: float | None,
        ttm_ebit: float | None,
        ev: float | None,
    ) -> int:
        if excluded:
            return 0
        score = 0
        if ttm_ebit is not None and ttm_ebit > 0:
            score += 30
        if ev is not None and ev > 0:
            score += 25
        if earnings_yield is not None and earnings_yield > 0:
            score += 25
        if roc is not None and roc > 0:
            score += 20
        return min(100, score)
