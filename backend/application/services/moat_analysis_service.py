from __future__ import annotations
import logging
import math
from datetime import timedelta
from shared.time_utils import now_utc, now_iso, parse_db_timestamp
from typing import Any, Dict, List, Optional

from domain.models.analysis_moat import (
    MoatDiagnosticFlag,
    MoatInputs,
    MoatValuation,
    MoatIndustryContext,
    MoatApplicability,
    MoatDataQuality,
    MoatResponse,
    MoatKeywordEvidence,
    MoatEvidenceResponse,
    MoatAiNarrative,
    MoatAiResponse,
)
from infrastructure.repositories.moat_repository import MoatRepository
from application.services.moat_wacc_service import MoatWaccService
from application.services.edgar_filing_service import EdgarFilingService
from application.services.moat_keyword_analyzer import MoatKeywordAnalyzer
from shared.finance_math import safe_float

logger = logging.getLogger(__name__)

_CACHE_MAX_AGE_HOURS = 24
_TEXT_CACHE_MAX_AGE_DAYS = 365

_SECTOR_MOAT_ADJUSTMENTS: Dict[str, float] = {
    "Technology": 0.0,
    "Healthcare": 0.0,
    "Consumer Cyclical": -0.02,
    "Consumer Defensive": 0.03,
    "Communication Services": 0.0,
    "Energy": -0.05,
    "Basic Materials": -0.03,
    "Industrials": -0.02,
    "Financial Services": -0.05,
    "Financials": -0.05,
    "Utilities": -0.08,
    "Real Estate": -0.05,
}


class MoatAnalysisService:
    def __init__(
        self,
        repo: MoatRepository,
        wacc_service: MoatWaccService,
        edgar_service: Optional[EdgarFilingService] = None,
        keyword_analyzer: Optional[MoatKeywordAnalyzer] = None,
    ) -> None:
        self._repo = repo
        self._wacc_service = wacc_service
        self._edgar_service = edgar_service or EdgarFilingService()
        self._keyword_analyzer = keyword_analyzer or MoatKeywordAnalyzer()

    async def get_moat_analysis(
        self, symbol: str, force: bool = False
    ) -> MoatResponse:
        ctx = self._repo.get_company_context(symbol)
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

    async def _serve_cached(
        self, company_id: int, symbol: str, currency: str
    ) -> Optional[MoatResponse]:
        row = await self._repo.get_moat_analysis(company_id)
        if not row:
            return None
        computed_at = row.get("computed_at")
        if computed_at:
            try:
                ts = computed_at
                if isinstance(ts, str):
                    ts = parse_db_timestamp(ts)
                age = now_utc() - ts
                if age > timedelta(hours=_CACHE_MAX_AGE_HOURS):
                    return None
            except Exception:
                return None
        return self._hydrate_response(row, symbol, currency)

    @staticmethod
    def _hydrate_response(
        row: Dict[str, Any], symbol: str, currency: str
    ) -> Optional[MoatResponse]:
        try:
            return MoatResponse(
                symbol=symbol.upper(),
                company_id=row["company_id"],
                currency=currency,
                inputs=MoatInputs(
                    nopat=safe_float(row.get("nopat")),
                    invested_capital=safe_float(row.get("invested_capital")),
                    gross_margin=safe_float(row.get("gross_margin")),
                    operating_margin=safe_float(row.get("operating_margin")),
                    net_margin=safe_float(row.get("net_margin")),
                    roic_5y_avg=safe_float(row.get("roic_5y_avg")),
                    roic_volatility=safe_float(row.get("roic_5y_std")),
                    asset_turnover=safe_float(row.get("asset_turnover")),
                    fiscal_years_used=row.get("fiscal_years_used", 0),
                ),
                valuation=MoatValuation(
                    roic=safe_float(row.get("roic")),
                    wacc=safe_float(row.get("wacc")),
                    roic_minus_wacc=safe_float(row.get("roic_minus_wacc")),
                    gross_margin_pct=safe_float(row.get("gross_margin_pct")),
                    operating_margin_pct=safe_float(row.get("operating_margin_pct")),
                    net_margin_pct=safe_float(row.get("net_margin_pct")),
                    roic_5y_avg=safe_float(row.get("roic_5y_avg")),
                    roic_5y_std=safe_float(row.get("roic_5y_std")),
                    roic_stability_score=safe_float(row.get("roic_stability_score")),
                    asset_turnover=safe_float(row.get("asset_turnover")),
                    capital_efficiency_score=safe_float(
                        row.get("capital_efficiency_score")
                    ),
                    moat_score=safe_float(row.get("moat_score")),
                    moat_category=row.get("moat_category", "Unknown"),
                ),
                industry_context=MoatIndustryContext(
                    sector=row.get("sector"),
                ),
                applicability=MoatApplicability(
                    score=int(safe_float(row.get("moat_score")) or 0),
                    category=row.get("moat_category", "Unknown"),
                ),
                data_quality=MoatDataQuality(
                    data_sources=row.get("data_sources", "database"),
                    fiscal_year_end=row.get("fiscal_year_end"),
                    quarters_used=row.get("quarters_used", 0),
                    fallbacks_used=row.get("fallbacks_used", False),
                    last_computed_at=str(row.get("computed_at", "")),
                ),
            )
        except Exception as e:
            logger.warning("Moat cache hydration failed: %s", e)
            return None

    async def _compute_and_cache(
        self,
        symbol: str,
        company_id: int,
        currency: str,
        sector: str,
        industry: str,
    ) -> MoatResponse:
        now_iso_str = now_iso()
        now_date = now_utc().date()

        ratios = await self._repo.get_financial_ratios_history(company_id, years=6)
        income_statements = await self._repo.get_income_statements_annual(
            company_id, years=6
        )
        bs = await self._repo.get_balance_sheet_latest(company_id)
        cf = await self._repo.get_cash_flow_latest(company_id)
        cs = await self._repo.get_company_summary_latest(company_id)
        industry_data = await self._repo.get_industry_multiples(sector, industry)

        # ── Stage 1: Quant Metrics ───────────────────────────────────────
        wacc = await self._wacc_service.compute_wacc(company_id)

        valid_ratios = [r for r in ratios if r.get("roic") is not None]
        roic_values = [safe_float(r["roic"]) for r in valid_ratios if safe_float(r["roic"]) is not None]
        latest_roic = roic_values[-1] if roic_values else None
        roic_5y_avg = sum(roic_values) / len(roic_values) if roic_values else None
        roic_5y_std = (
            self._compute_std(roic_values) if len(roic_values) > 1 else None
        )

        roic_stability_score = self._compute_stability_score(
            roic_5y_std, roic_values
        )

        gross_margin_vals = [
            safe_float(r.get("gross_margin"))
            for r in valid_ratios
            if safe_float(r.get("gross_margin")) is not None
        ]
        operating_margin_vals = [
            safe_float(r.get("operating_margin"))
            for r in valid_ratios
            if safe_float(r.get("operating_margin")) is not None
        ]
        net_margin_vals = [
            safe_float(r.get("net_margin"))
            for r in valid_ratios
            if safe_float(r.get("net_margin")) is not None
        ]

        latest_gross_margin = gross_margin_vals[-1] if gross_margin_vals else None
        latest_operating_margin = (
            operating_margin_vals[-1] if operating_margin_vals else None
        )
        latest_net_margin = net_margin_vals[-1] if net_margin_vals else None

        asset_turnover = safe_float(valid_ratios[-1].get("asset_turnover")) if valid_ratios and valid_ratios[-1].get("asset_turnover") is not None else None

        capital_efficiency_score = self._compute_capital_efficiency_score(
            asset_turnover, latest_roic, wacc
        )

        # NOPAT and Invested Capital
        nopat = None
        invested_capital = None
        if income_statements and bs:
            latest_is = income_statements[-1] if income_statements else None
            ebit = safe_float(latest_is.get("ebit")) if latest_is else None
            tax = safe_float(latest_is.get("income_tax_expense")) if latest_is else None
            ni = safe_float(latest_is.get("net_income")) if latest_is else None
            pretax = safe_float(latest_is.get("net_income")) if latest_is else None

            if ebit is not None and tax is not None and ebit != 0:
                tax_rate = tax / ebit
                nopat = ebit * (1 - tax_rate)
            elif ebit is not None:
                nopat = ebit * 0.79

            total_assets = safe_float(bs.get("total_assets"))
            cash = safe_float(bs.get("cash_and_cash_equivalents"))
            total_debt = safe_float(bs.get("total_debt"))
            if total_assets is not None:
                invested_capital = total_assets - (cash or 0) - (total_debt or 0)

        # ── Stage 1 composite score ──────────────────────────────────────
        stage1_score = self.compute_stage1_score(
            latest_roic=latest_roic,
            wacc=wacc,
            roic_5y_avg=roic_5y_avg,
            roic_stability_score=roic_stability_score,
            capital_efficiency_score=capital_efficiency_score,
            latest_gross_margin=latest_gross_margin,
            latest_net_margin=latest_net_margin,
        )

        # ── Sector adjustment ────────────────────────────────────────────
        sector_adjustment = _SECTOR_MOAT_ADJUSTMENTS.get(sector, 0.0)
        adjusted_score = max(0, min(100, stage1_score * (1.0 + sector_adjustment)))

        # ── Moat category ────────────────────────────────────────────────
        moat_category = self._categorize_score(adjusted_score)

        roic_minus_wacc = (
            round((latest_roic - wacc) * 100, 2)
            if latest_roic is not None and wacc is not None
            else None
        )

        # ── Flags ────────────────────────────────────────────────────────
        flags = self._generate_flags(
            latest_roic, wacc, roic_5y_std, asset_turnover, sector
        )

        # ── Assemble response ────────────────────────────────────────────
        fiscal_years_used = len(valid_ratios)

        response = MoatResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            currency=currency,
            inputs=MoatInputs(
                nopat=round(nopat, 2) if nopat is not None else None,
                invested_capital=round(invested_capital, 2)
                if invested_capital is not None
                else None,
                gross_margin=latest_gross_margin,
                operating_margin=latest_operating_margin,
                net_margin=latest_net_margin,
                roic_5y_avg=roic_5y_avg,
                roic_volatility=roic_5y_std,
                asset_turnover=asset_turnover,
                fiscal_years_used=fiscal_years_used,
                as_of_date=str(now_date),
            ),
            valuation=MoatValuation(
                roic=round(latest_roic, 6) if latest_roic is not None else None,
                wacc=round(wacc, 6) if wacc is not None else None,
                roic_minus_wacc=roic_minus_wacc,
                gross_margin_pct=(
                    round(latest_gross_margin * 100, 2)
                    if latest_gross_margin is not None
                    else None
                ),
                operating_margin_pct=(
                    round(latest_operating_margin * 100, 2)
                    if latest_operating_margin is not None
                    else None
                ),
                net_margin_pct=(
                    round(latest_net_margin * 100, 2)
                    if latest_net_margin is not None
                    else None
                ),
                roic_5y_avg=round(roic_5y_avg, 6) if roic_5y_avg is not None else None,
                roic_5y_std=round(roic_5y_std, 6) if roic_5y_std is not None else None,
                roic_stability_score=roic_stability_score,
                asset_turnover=round(asset_turnover, 4) if asset_turnover is not None else None,
                capital_efficiency_score=capital_efficiency_score,
                moat_score=round(adjusted_score, 1),
                moat_category=moat_category,
            ),
            industry_context=MoatIndustryContext(
                sector=sector or None,
                industry=industry or None,
                avg_roic=(
                    safe_float(industry_data.get("avg_roic"))
                    if industry_data
                    else None
                ),
                sample_size=industry_data.get("sample_size") if industry_data else None,
            ),
            applicability=MoatApplicability(
                score=int(round(adjusted_score)),
                category=(
                    "Not Applicable"
                    if adjusted_score == 0
                    else "Applicable" if adjusted_score >= 30 else "Caution"
                ),
                excluded=False,
                flags=flags,
            ),
            data_quality=MoatDataQuality(
                data_sources=(
                    "company_summary + financial_ratios + income_statements + balance_sheets"
                ),
                fiscal_year_end=(
                    int(bs.get("fiscal_year")) if bs and bs.get("fiscal_year") else None
                ),
                quarters_used=0,
                fallbacks_used=(
                    latest_roic is None or wacc is None
                ),
                last_computed_at=now_iso_str,
            ),
        )

        # ── Persist ──────────────────────────────────────────────────────
        db_record = {
            "company_id": company_id,
            "symbol": symbol.upper(),
            "roic": latest_roic,
            "wacc": wacc,
            "roic_minus_wacc": roic_minus_wacc,
            "gross_margin_pct": response.valuation.gross_margin_pct,
            "operating_margin_pct": response.valuation.operating_margin_pct,
            "net_margin_pct": response.valuation.net_margin_pct,
            "roic_5y_avg": roic_5y_avg,
            "roic_5y_std": roic_5y_std,
            "roic_stability_score": roic_stability_score,
            "asset_turnover": asset_turnover,
            "capital_efficiency_score": capital_efficiency_score,
            "moat_score": round(adjusted_score, 1),
            "moat_category": moat_category,
            "text_analysis_available": False,
            "keyword_matches_count": 0,
            "sector": sector,
            "sector_adjustment": sector_adjustment,
            "ai_narrative_available": False,
            "fiscal_years_used": fiscal_years_used,
            "data_sources": "financial_ratios + income_statements + balance_sheets + company_summary",
            "quarters_used": 0,
            "fallbacks_used": latest_roic is None or wacc is None,
        }
        await self._repo.upsert_moat_analysis(company_id, db_record)

        return response

    def compute_stage1_score(
        self,
        latest_roic: Optional[float],
        wacc: Optional[float],
        roic_5y_avg: Optional[float],
        roic_stability_score: Optional[float],
        capital_efficiency_score: Optional[float],
        latest_gross_margin: Optional[float] = None,
        latest_net_margin: Optional[float] = None,
    ) -> float:
        score = 0.0
        max_score = 0.0

        # ROIC vs WACC spread (0-35)
        max_score += 35
        if latest_roic is not None and wacc is not None:
            spread = latest_roic - wacc
            if spread > 0.10:
                score += 35
            elif spread > 0.05:
                score += 28
            elif spread > 0.02:
                score += 20
            elif spread > 0.0:
                score += 12
            else:
                score += max(0, 12 + (spread / 0.02) * 12)

        # ROIC 5y avg (0-20)
        max_score += 20
        if roic_5y_avg is not None:
            if roic_5y_avg > 0.20:
                score += 20
            elif roic_5y_avg > 0.15:
                score += 16
            elif roic_5y_avg > 0.10:
                score += 12
            elif roic_5y_avg > 0.05:
                score += 6
            elif roic_5y_avg > 0:
                score += 3

        # Margin durability (0-20)
        max_score += 20
        margin_score = 0
        if latest_gross_margin is not None:
            if latest_gross_margin > 0.60:
                margin_score += 8
            elif latest_gross_margin > 0.40:
                margin_score += 6
            elif latest_gross_margin > 0.20:
                margin_score += 3
        if latest_net_margin is not None:
            if latest_net_margin > 0.20:
                margin_score += 12
            elif latest_net_margin > 0.15:
                margin_score += 9
            elif latest_net_margin > 0.10:
                margin_score += 6
            elif latest_net_margin > 0.05:
                margin_score += 3
        score += margin_score

        # ROIC stability (0-15)
        max_score += 15
        if roic_stability_score is not None:
            score += (roic_stability_score / 100.0) * 15

        # Capital efficiency (0-10)
        max_score += 10
        if capital_efficiency_score is not None:
            score += (capital_efficiency_score / 100.0) * 10

        return (score / max_score * 100) if max_score > 0 else 0.0

    @staticmethod
    def _compute_std(values: List[float]) -> float:
        n = len(values)
        if n < 2:
            return 0.0
        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        return math.sqrt(variance)

    @staticmethod
    def _compute_stability_score(
        std: Optional[float], values: List[float]
    ) -> Optional[float]:
        if std is None or not values:
            return None
        mean = sum(values) / len(values)
        if mean == 0:
            return 50.0
        cv = std / abs(mean)
        if cv < 0.1:
            return 95.0
        if cv < 0.2:
            return 85.0
        if cv < 0.3:
            return 70.0
        if cv < 0.5:
            return 50.0
        if cv < 0.75:
            return 30.0
        return 15.0

    @staticmethod
    def _compute_capital_efficiency_score(
        asset_turnover: Optional[float],
        roic: Optional[float],
        wacc: Optional[float],
    ) -> Optional[float]:
        score = 0.0
        if asset_turnover is not None:
            if asset_turnover > 1.0:
                score += 40
            elif asset_turnover > 0.5:
                score += 25
            elif asset_turnover > 0.2:
                score += 10
            else:
                score += 5

        if roic is not None and wacc is not None:
            if roic > wacc * 2:
                score += 60
            elif roic > wacc:
                score += 40
            elif roic > wacc * 0.5:
                score += 20
            else:
                score += 5

        return score if (asset_turnover is not None or (roic is not None and wacc is not None)) else None

    @staticmethod
    def _categorize_score(score: float) -> str:
        if score >= 70:
            return "Wide"
        if score >= 40:
            return "Narrow"
        if score >= 10:
            return "None"
        return "Unknown"

    @staticmethod
    def _generate_flags(
        latest_roic: Optional[float],
        wacc: Optional[float],
        roic_5y_std: Optional[float],
        asset_turnover: Optional[float],
        sector: str,
    ) -> List[MoatDiagnosticFlag]:
        flags: List[MoatDiagnosticFlag] = []

        if latest_roic is not None and wacc is not None:
            if latest_roic < wacc:
                flags.append(
                    MoatDiagnosticFlag(
                        code="MOAT-ROIC-BELOW-WACC",
                        severity="high",
                        message=f"ROIC ({latest_roic:.1%}) is below WACC ({wacc:.1%}) — company is destroying value.",
                        recommendation="Focus on margin improvement or asset efficiency to close the gap.",
                    )
                )
            if latest_roic > wacc * 3:
                flags.append(
                    MoatDiagnosticFlag(
                        code="MOAT-ROIC-EXTREME",
                        severity="info",
                        message=f"ROIC ({latest_roic:.1%}) is very high relative to WACC ({wacc:.1%}). Verify sustainability.",
                    )
                )

        if roic_5y_std is not None and roic_5y_std > 0.10:
            flags.append(
                MoatDiagnosticFlag(
                    code="MOAT-ROIC-HIGH-VOLATILITY",
                    severity="medium",
                    message=f"ROIC standard deviation of {roic_5y_std:.1%} indicates unstable returns.",
                    recommendation="Investigate earnings quality and competitive position durability.",
                )
            )

        if asset_turnover is not None and asset_turnover < 0.2:
            flags.append(
                MoatDiagnosticFlag(
                    code="MOAT-LOW-ASSET-TURNOVER",
                    severity="low",
                    message=f"Asset turnover of {asset_turnover:.2f} is very low — capital-intensive business model.",
                )
            )

        sector_lower = sector.lower()
        if any(kw in sector_lower for kw in ["bank", "insur", "reit", "utility", "financial"]):
            flags.append(
                MoatDiagnosticFlag(
                    code="MOAT-SECTOR-REGULATED",
                    severity="info",
                    message=f"{sector} companies operate in regulated environments. "
                    "Moat assessment adjusted for sector-specific capital structures.",
                    recommendation="Focus on regulatory barriers and brand as primary moat sources.",
                )
            )

        return flags

    # ── Evidence ────────────────────────────────────────────────────────────

    async def get_moat_evidence(self, symbol: str) -> MoatEvidenceResponse:
        ctx = self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])

        rows = await self._repo.get_moat_keyword_evidence(company_id)

        evidence_by_group: Dict[str, List[MoatKeywordEvidence]] = {}
        for r in rows:
            group = r.get("keyword_group", "other")
            evidence_by_group.setdefault(group, []).append(
                MoatKeywordEvidence(
                    keyword=r.get("keyword", ""),
                    keyword_group=group,
                    section=r.get("section", ""),
                    snippet=r.get("snippet"),
                    relevance_score=float(r.get("relevance_score", 1.0)),
                    filing_date=r.get("filing_date"),
                )
            )

        return MoatEvidenceResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            text_analysis_available=len(rows) > 0,
            total_keyword_matches=len(rows),
            evidence_by_group=evidence_by_group,
            groups_found=list(evidence_by_group.keys()),
        )

    async def run_text_analysis(
        self, symbol: str
    ) -> MoatEvidenceResponse:
        ctx = self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])

        raw_text = await self._edgar_service.fetch_tenk_text(symbol)
        if not raw_text:
            return MoatEvidenceResponse(
                symbol=symbol.upper(),
                company_id=company_id,
                text_analysis_available=False,
            )

        filing_date = await self._edgar_service.get_latest_filing_date(symbol)

        analysis = self._keyword_analyzer.analyze(raw_text)

        await self._repo.delete_moat_keyword_evidence(company_id)

        evidence_rows = []
        for ev in analysis.get("evidence", []):
            evidence_rows.append(
                {
                    "company_id": company_id,
                    "symbol": symbol.upper(),
                    "filing_type": "10-K",
                    "filing_date": str(filing_date) if filing_date else None,
                    "section": ev.get("section", "unknown"),
                    "keyword": ev["keyword"],
                    "keyword_group": ev["keyword_group"],
                    "snippet": ev["snippet"],
                    "relevance_score": ev["relevance_score"],
                }
            )
        if evidence_rows:
            await self._repo.insert_moat_keyword_evidence(evidence_rows)

        await self._repo.upsert_moat_analysis(
            company_id,
            {
                "company_id": company_id,
                "symbol": symbol.upper(),
                "text_analysis_available": True,
                "keyword_matches_count": analysis.get("total_matches", 0),
            },
        )

        return await self.get_moat_evidence(symbol)

    # ── AI Narrative ────────────────────────────────────────────────────────

    async def get_moat_ai_narrative(self, symbol: str) -> MoatAiResponse:
        ctx = self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])

        cached = await self._repo.get_moat_ai_narrative(company_id)
        if cached:
            return MoatAiResponse(
                symbol=symbol.upper(),
                company_id=company_id,
                narrative=MoatAiNarrative(
                    narrative=cached.get("narrative", ""),
                    summary=cached.get("summary"),
                    model=cached.get("model", "openrouter/default"),
                    generated_at=str(cached.get("generated_at", "")),
                    generation_time_ms=cached.get("generation_time_ms"),
                ),
                available=True,
            )

        return MoatAiResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            narrative=MoatAiNarrative(
                narrative="AI analysis not yet generated. Call POST endpoint to generate.",
            ),
            available=False,
        )

    async def generate_moat_ai_narrative(
        self, symbol: str
    ) -> MoatAiResponse:
        ctx = self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])

        moat_data = await self._repo.get_moat_analysis(company_id)
        evidence = await self._repo.get_moat_keyword_evidence(company_id)

        quant_summary = self._build_quant_summary(moat_data)
        evidence_summary = (
            f"Found {len(evidence)} keyword matches across "
            f"{len(set(e.get('keyword_group', '') for e in evidence))} moat categories."
            if evidence
            else "No text evidence available."
        )

        prompt = self._build_ai_prompt(symbol, quant_summary, evidence_summary)
        narrative = await self._call_ai(prompt)
        start_ms = 0
        end_ms = 0

        if narrative:
            import time
            start_ms = int(time.time() * 1000)
            narrative_text = narrative
            end_ms = int(time.time() * 1000)

            await self._repo.upsert_moat_ai_narrative(
                company_id,
                {
                    "company_id": company_id,
                    "symbol": symbol.upper(),
                    "model": "openrouter/default",
                    "narrative": narrative_text,
                    "quant_snapshot": {
                        "moat_score": moat_data.get("moat_score") if moat_data else None,
                        "moat_category": moat_data.get("moat_category") if moat_data else None,
                    },
                    "evidence_count": len(evidence),
                    "generation_time_ms": end_ms - start_ms,
                },
            )

            return MoatAiResponse(
                symbol=symbol.upper(),
                company_id=company_id,
                narrative=MoatAiNarrative(
                    narrative=narrative_text,
                    model="openrouter/default",
                    generated_at=now_iso(),
                    generation_time_ms=end_ms - start_ms,
                ),
                available=True,
            )

        return MoatAiResponse(
            symbol=symbol.upper(),
            company_id=company_id,
            narrative=MoatAiNarrative(
                narrative="AI narrative generation failed. Please try again later.",
            ),
            available=False,
        )

    @staticmethod
    def _build_quant_summary(moat_data: Optional[Dict[str, Any]]) -> str:
        if not moat_data:
            return "No quantitative data available."
        return (
            f"Moat Score: {moat_data.get('moat_score', 'N/A')}/100 "
            f"(Category: {moat_data.get('moat_category', 'N/A')}). "
            f"ROIC: {moat_data.get('roic', 'N/A')}, "
            f"WACC: {moat_data.get('wacc', 'N/A')}, "
            f"ROIC 5yr Avg: {moat_data.get('roic_5y_avg', 'N/A')}, "
            f"Gross Margin: {moat_data.get('gross_margin_pct', 'N/A')}%, "
            f"Net Margin: {moat_data.get('net_margin_pct', 'N/A')}%."
        )

    @staticmethod
    def _build_ai_prompt(
        symbol: str, quant_summary: str, evidence_summary: str
    ) -> str:
        return (
            f"Analyze the economic moat for {symbol}. "
            f"Quantitative data: {quant_summary} "
            f"Text evidence: {evidence_summary} "
            "Provide a concise assessment of the company's competitive advantage "
            "durability, identifying specific moat sources (intangibles, switching costs, "
            "network effects, cost advantages, scale efficiencies). "
            "Keep the response to 2-3 paragraphs. Be specific and reference the data provided."
        )

    async def _call_ai(self, prompt: str) -> Optional[str]:
        try:
            from config import settings
            key = settings.OPEN_ROUTER_KEY or ""
            if not key:
                logger.info("OPEN_ROUTER_KEY not set — AI narrative disabled")
                return None

            import httpx
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "openai/gpt-4o-mini",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are a financial analyst specializing in competitive advantage and economic moat analysis. Provide concise, specific assessments.",
                            },
                            {"role": "user", "content": prompt},
                        ],
                        "max_tokens": 500,
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return data["choices"][0]["message"]["content"]
                logger.error(
                    "OpenRouter API error: %s %s", resp.status_code, resp.text
                )
                return None
        except ImportError:
            logger.warning("httpx not installed; AI narrative disabled")
            return None
        except Exception as e:
            logger.error("AI narrative call failed: %s", e)
            return None
