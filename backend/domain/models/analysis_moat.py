from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel


class MoatDiagnosticFlag(BaseModel):
    code: str
    severity: str
    message: str
    recommendation: str | None = None
    evidence: dict[str, Any] | None = None


class MoatInputs(BaseModel):
    nopat: float | None = None
    invested_capital: float | None = None
    gross_margin: float | None = None
    operating_margin: float | None = None
    net_margin: float | None = None
    roic_5y_avg: float | None = None
    roic_volatility: float | None = None
    asset_turnover: float | None = None
    fiscal_years_used: int = 0
    as_of_date: str | None = None


class MoatValuation(BaseModel):
    roic: float | None = None
    wacc: float | None = None
    roic_minus_wacc: float | None = None
    gross_margin_pct: float | None = None
    operating_margin_pct: float | None = None
    net_margin_pct: float | None = None
    roic_5y_avg: float | None = None
    roic_5y_std: float | None = None
    roic_stability_score: float | None = None
    asset_turnover: float | None = None
    capital_efficiency_score: float | None = None
    moat_score: float | None = None
    moat_category: str = "Unknown"
    moat_summary: str | None = None


class MoatIndustryContext(BaseModel):
    sector: str | None = None
    industry: str | None = None
    avg_roic: float | None = None
    roic_vs_industry: str | None = None
    avg_margin: float | None = None
    sample_size: int | None = None
    context_note: str = (
        "Industry ROIC and margin averages are directional. "
        "Moat durability is assessed relative to sector peers."
    )


class MoatApplicability(BaseModel):
    score: int = 0
    category: str = "Not Applicable"
    excluded: bool = False
    exclusion_reason: str | None = None
    flags: list[MoatDiagnosticFlag] = []
    suitability_summary: str | None = None


class MoatDataQuality(BaseModel):
    data_sources: str = "database"
    fiscal_year_end: int | None = None
    quarters_used: int = 0
    days_since_update: int | None = None
    fallbacks_used: bool = False
    last_computed_at: str = ""


class MoatResponse(BaseModel):
    symbol: str
    company_id: int
    currency: str
    inputs: MoatInputs
    valuation: MoatValuation
    industry_context: MoatIndustryContext
    applicability: MoatApplicability
    data_quality: MoatDataQuality


class MoatKeywordEvidence(BaseModel):
    keyword: str
    keyword_group: str
    section: str
    snippet: str | None = None
    relevance_score: float = 1.0
    filing_date: date | None = None


class MoatEvidenceResponse(BaseModel):
    symbol: str
    company_id: int
    text_analysis_available: bool = False
    filing_type: str | None = None
    filing_date: date | None = None
    total_keyword_matches: int = 0
    evidence_by_group: dict[str, list[MoatKeywordEvidence]] = {}
    groups_found: list[str] = []


class MoatAiNarrative(BaseModel):
    narrative: str
    summary: str | None = None
    model: str = "openrouter/default"
    generated_at: str = ""
    generation_time_ms: int | None = None


class MoatAiResponse(BaseModel):
    symbol: str
    company_id: int
    narrative: MoatAiNarrative
    available: bool = True
