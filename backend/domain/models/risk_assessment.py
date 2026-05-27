from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import date


RiskCategory = Literal[
    "Very Low Downside",
    "Moderate",
    "Elevated",
    "High Risk",
]

RiskSeverity = Literal["low", "moderate", "elevated", "high", "severe"]

LayerName = Literal[
    "business_fragility",
    "balance_sheet",
    "valuation_compression",
    "earnings_stress",
    "drawdown_risk",
]


class RiskMetric(BaseModel):
    name: str
    value: Optional[float] = None
    label: str
    status: Literal["pass", "caution", "fail", "na"]
    weight: float = 1.0
    evidence: Optional[Dict[str, Any]] = None
    threshold_description: Optional[str] = None


class RiskLayer(BaseModel):
    name: LayerName
    display_name: str
    score: float
    category: RiskSeverity
    metrics: List[RiskMetric]
    weight: float


class BusinessFragility(RiskLayer):
    moat_score: Optional[float] = None
    moat_category: Optional[str] = None
    roic_minus_wacc: Optional[float] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    recurrence_classification: Optional[str] = None
    pricing_power_assessment: Optional[str] = None


class BalanceSheetRisk(RiskLayer):
    debt_to_ebitda: Optional[float] = None
    net_debt_to_ebitda: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    debt_to_equity: Optional[float] = None
    fcf_conversion: Optional[float] = None
    fcf_stability_pct: Optional[float] = None


class ValuationCompressionRisk(RiskLayer):
    pe_current: Optional[float] = None
    pe_percentile: Optional[float] = None
    pe_5y_min: Optional[float] = None
    pe_5y_max: Optional[float] = None
    pe_5y_median: Optional[float] = None
    ev_ebitda_current: Optional[float] = None
    ev_ebitda_percentile: Optional[float] = None
    peg_ratio: Optional[float] = None


class EarningsStressRisk(RiskLayer):
    eps_cagr_3y: Optional[float] = None
    eps_cagr_5y: Optional[float] = None
    revenue_cagr_3y: Optional[float] = None
    revenue_cagr_5y: Optional[float] = None
    net_margin_current: Optional[float] = None
    operating_margin_trend: Optional[Literal["expanding", "stable", "contracting"]] = None
    revenue_eps_alignment: Optional[Literal["aligned", "diverging", "volatile"]] = None
    eps_volatility: Optional[float] = None


class CrisisDrawdown(BaseModel):
    crisis_name: str
    start_date: date
    end_date: date
    max_drawdown: float
    start_value: float
    end_value: float


class DrawdownRisk(RiskLayer):
    max_drawdown_1y: Optional[float] = None
    max_drawdown_3y: Optional[float] = None
    max_drawdown_5y: Optional[float] = None
    beta_5y: Optional[float] = None
    current_drawdown: Optional[float] = None
    crisis_drawdowns: Optional[List[CrisisDrawdown]] = None
    recovery_time_days: Optional[int] = None


class ScenarioInput(BaseModel):
    name: str
    eps_growth: float
    exit_pe: float
    probability: float


class ScenarioResult(BaseModel):
    scenario: str
    probability: float
    eps_growth: float
    exit_pe: float
    future_eps: float
    future_value: float
    total_return: float
    downside: float


class BearCase(BaseModel):
    eps_growth_assumption: float
    exit_pe_ratio: float
    future_value: float
    current_price: float
    downside_pct: float


class CompositeScore(BaseModel):
    score: float
    category: RiskCategory
    maximum_expected_loss_pct: float
    bear_case: BearCase


class RiskAiNarrative(BaseModel):
    narrative: str
    model: str = "openrouter/default"
    generated_at: str = ""
    generation_time_ms: Optional[int] = None


class RiskDataQuality(BaseModel):
    data_sources: str = "database"
    fiscal_year_end: Optional[int] = None
    days_since_update: Optional[int] = None
    fallbacks_used: bool = False
    last_computed_at: str = ""


class RiskAssessmentResponse(BaseModel):
    symbol: str
    company_id: int
    currency: str
    composite: CompositeScore
    layers: Dict[LayerName, RiskLayer]
    scenarios: Optional[List[ScenarioResult]] = None
    ai_narrative: Optional[RiskAiNarrative] = None
    data_quality: RiskDataQuality
