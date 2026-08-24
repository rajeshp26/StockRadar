from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel

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
    value: float | None = None
    label: str
    status: Literal["pass", "caution", "fail", "na"]
    weight: float = 1.0
    evidence: dict[str, Any] | None = None
    threshold_description: str | None = None


class RiskLayer(BaseModel):
    name: LayerName
    display_name: str
    score: float
    category: RiskSeverity
    metrics: list[RiskMetric]
    weight: float


class BusinessFragility(RiskLayer):
    moat_score: float | None = None
    moat_category: str | None = None
    roic_minus_wacc: float | None = None
    sector: str | None = None
    industry: str | None = None
    recurrence_classification: str | None = None
    pricing_power_assessment: str | None = None


class BalanceSheetRisk(RiskLayer):
    debt_to_ebitda: float | None = None
    net_debt_to_ebitda: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None
    quick_ratio: float | None = None
    debt_to_equity: float | None = None
    fcf_conversion: float | None = None
    fcf_stability_pct: float | None = None


class ValuationCompressionRisk(RiskLayer):
    pe_current: float | None = None
    pe_percentile: float | None = None
    pe_5y_min: float | None = None
    pe_5y_max: float | None = None
    pe_5y_median: float | None = None
    ev_ebitda_current: float | None = None
    ev_ebitda_percentile: float | None = None
    peg_ratio: float | None = None


class EarningsStressRisk(RiskLayer):
    eps_cagr_3y: float | None = None
    eps_cagr_5y: float | None = None
    revenue_cagr_3y: float | None = None
    revenue_cagr_5y: float | None = None
    net_margin_current: float | None = None
    operating_margin_trend: Literal["expanding", "stable", "contracting"] | None = None
    revenue_eps_alignment: Literal["aligned", "diverging", "volatile"] | None = None
    eps_volatility: float | None = None


class CrisisDrawdown(BaseModel):
    crisis_name: str
    start_date: date
    end_date: date
    max_drawdown: float
    start_value: float
    end_value: float


class DrawdownRisk(RiskLayer):
    max_drawdown_1y: float | None = None
    max_drawdown_3y: float | None = None
    max_drawdown_5y: float | None = None
    beta_5y: float | None = None
    current_drawdown: float | None = None
    crisis_drawdowns: list[CrisisDrawdown] | None = None
    recovery_time_days: int | None = None


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
    maximum_expected_loss_pct: float | None = None
    bear_case: BearCase


class RiskAiNarrative(BaseModel):
    narrative: str
    model: str = "openrouter/default"
    generated_at: str = ""
    generation_time_ms: int | None = None


class RiskDataQuality(BaseModel):
    data_sources: str = "database"
    fiscal_year_end: int | None = None
    days_since_update: int | None = None
    fallbacks_used: bool = False
    last_computed_at: str = ""


class RiskAssessmentResponse(BaseModel):
    symbol: str
    company_id: int
    currency: str
    composite: CompositeScore
    layers: dict[LayerName, RiskLayer]
    scenarios: list[ScenarioResult] | None = None
    ai_narrative: RiskAiNarrative | None = None
    data_quality: RiskDataQuality
