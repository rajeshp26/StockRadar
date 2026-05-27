from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from datetime import date


class MoatDiagnosticFlag(BaseModel):
    code: str
    severity: str
    message: str
    recommendation: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


class MoatInputs(BaseModel):
    nopat: Optional[float] = None
    invested_capital: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    roic_5y_avg: Optional[float] = None
    roic_volatility: Optional[float] = None
    asset_turnover: Optional[float] = None
    fiscal_years_used: int = 0
    as_of_date: Optional[str] = None


class MoatValuation(BaseModel):
    roic: Optional[float] = None
    wacc: Optional[float] = None
    roic_minus_wacc: Optional[float] = None
    gross_margin_pct: Optional[float] = None
    operating_margin_pct: Optional[float] = None
    net_margin_pct: Optional[float] = None
    roic_5y_avg: Optional[float] = None
    roic_5y_std: Optional[float] = None
    roic_stability_score: Optional[float] = None
    asset_turnover: Optional[float] = None
    capital_efficiency_score: Optional[float] = None
    moat_score: Optional[float] = None
    moat_category: str = "Unknown"
    moat_summary: Optional[str] = None


class MoatIndustryContext(BaseModel):
    sector: Optional[str] = None
    industry: Optional[str] = None
    avg_roic: Optional[float] = None
    roic_vs_industry: Optional[str] = None
    avg_margin: Optional[float] = None
    sample_size: Optional[int] = None
    context_note: str = (
        "Industry ROIC and margin averages are directional. "
        "Moat durability is assessed relative to sector peers."
    )


class MoatApplicability(BaseModel):
    score: int = 0
    category: str = "Not Applicable"
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    flags: List[MoatDiagnosticFlag] = []
    suitability_summary: Optional[str] = None


class MoatDataQuality(BaseModel):
    data_sources: str = "database"
    fiscal_year_end: Optional[int] = None
    quarters_used: int = 0
    days_since_update: Optional[int] = None
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
    snippet: Optional[str] = None
    relevance_score: float = 1.0
    filing_date: Optional[date] = None


class MoatEvidenceResponse(BaseModel):
    symbol: str
    company_id: int
    text_analysis_available: bool = False
    filing_type: Optional[str] = None
    filing_date: Optional[date] = None
    total_keyword_matches: int = 0
    evidence_by_group: Dict[str, List[MoatKeywordEvidence]] = {}
    groups_found: List[str] = []


class MoatAiNarrative(BaseModel):
    narrative: str
    summary: Optional[str] = None
    model: str = "openrouter/default"
    generated_at: str = ""
    generation_time_ms: Optional[int] = None


class MoatAiResponse(BaseModel):
    symbol: str
    company_id: int
    narrative: MoatAiNarrative
    available: bool = True
