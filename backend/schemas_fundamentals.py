from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class MetricComponent(BaseModel):
    label: str
    value: float | None = None
    highlight: Literal["positive", "negative", "driver"] | None = None


class QuarterDataPoint(BaseModel):
    fiscal_year: int
    fiscal_quarter: int
    label: str
    value: float | None = None
    raw_value: float | None = None
    """Absolute value of the underlying metric (e.g. revenue in $B for revenue_yoy).
       Populated for growth metrics so the frontend can toggle between YoY% and absolute views."""
    narrative_label: str | None = None
    status: Literal["normal", "not_applicable", "insufficient_data"] | None = None
    components: list[MetricComponent] | None = None
    ttm_eps: float | None = None
    quarter_end_price: float | None = None


class GaugeConfig(BaseModel):
    display_mode: Literal["gauge", "compact_gauge", "slider", "disabled"]
    benchmark: Literal["historical", "sector", "none"]
    benchmark_value: float | None = None
    band_low: float | None = None
    band_high: float | None = None
    current_value: float | None = None
    current_quarter_raw: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    avg_value: float | None = None
    positive_count: int = 0
    total_quarters: int = 0
    na_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    # ── Design 4: Sparkline / Percentile / Delta ──
    sparkline_values: list[float | None] | None = None
    """Last 8-12 quarters of this metric's values for mini sparkline chart.
       None entries indicate missing quarters (break the line)."""
    percentile: int | None = None
    """Percentile rank of current value within all-time history (0-100)."""
    historical_avg: float | None = None
    """Mean of all available historical values for this metric."""
    vs_avg_delta: float | None = None
    """current_value - historical_avg. Positive = above avg (more expensive)."""
    recent_quarter_label: str | None = None
    """Label of the quarter used for 'current' value.
       e.g. 'Q3 2025' when the most recent quarter had negative earnings."""
    # ── Sector benchmark fields (populated when sector stats available) ──
    sector_p05: float | None = None
    """5th percentile of this metric within the company's sector."""
    sector_p50: float | None = None
    """50th percentile (median) of this metric within the company's sector."""
    sector_p95: float | None = None
    """95th percentile of this metric within the company's sector."""
    sector_sample_size: int = 0
    """Number of companies in the sector used to compute the percentiles."""


class MetricQuarterSeries(BaseModel):
    metric_id: str
    label: str
    unit: str
    quarters: list[QuarterDataPoint]
    buy_quarter_index: int | None = None
    trend_direction: Literal["up", "down", "stable"]
    change_pct: float | None = None
    change_label: str = "stable"
    gauge_config: GaugeConfig | None = None


class SectionStatus(BaseModel):
    label: Literal["Intact", "Watch", "Concern"]


class IntrinsicValuation(BaseModel):
    method: str
    intrinsic_value: float


class MetricSection(BaseModel):
    section_id: str
    title: str
    metrics: list[MetricQuarterSeries]
    status: SectionStatus
    score: float | None = None
    intrinsic_valuations: list[IntrinsicValuation] | None = None
    current_price: float | None = None


class DataQuality(BaseModel):
    sources: list[str] = Field(default_factory=lambda: ["financial_ratios", "income_statements", "cash_flow_statements", "earnings"])
    staleness_days: int | None = None
    earliest_data_year: int | None = None
    quarterly_data_count: int | None = None


class FundamentalsResponse(BaseModel):
    success: bool = True
    symbol: str
    company_name: str | None = None
    currency: str = "USD"
    has_portfolio_position: bool = False
    purchase_date: date | None = None
    purchase_period: str | None = None
    quarters: list[str] = Field(default_factory=list)
    buy_quarter_index: int | None = None
    composite_score: float | None = None
    sections: list[MetricSection] = Field(default_factory=list)
    data_quality: DataQuality | None = None
    error: str | None = None
