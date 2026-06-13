from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Literal, Union

from pydantic import BaseModel, Field


class MetricComponent(BaseModel):
    label: str
    value: Optional[float] = None
    highlight: Optional[Literal["positive", "negative", "driver"]] = None


class QuarterDataPoint(BaseModel):
    fiscal_year: int
    fiscal_quarter: int
    label: str
    value: Optional[float] = None
    raw_value: Optional[float] = None
    """Absolute value of the underlying metric (e.g. revenue in $B for revenue_yoy).
       Populated for growth metrics so the frontend can toggle between YoY% and absolute views."""
    narrative_label: Optional[str] = None
    status: Optional[Literal["normal", "not_applicable", "insufficient_data"]] = None
    components: Optional[List[MetricComponent]] = None
    ttm_eps: Optional[float] = None
    quarter_end_price: Optional[float] = None


class GaugeConfig(BaseModel):
    display_mode: Literal["gauge", "compact_gauge", "slider", "disabled"]
    benchmark: Literal["historical", "sector", "none"]
    benchmark_value: Optional[float] = None
    band_low: Optional[float] = None
    band_high: Optional[float] = None
    current_value: Optional[float] = None
    current_quarter_raw: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: Optional[float] = None
    positive_count: int = 0
    total_quarters: int = 0
    na_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    # ── Design 4: Sparkline / Percentile / Delta ──
    sparkline_values: Optional[List[Optional[float]]] = None
    """Last 8-12 quarters of this metric's values for mini sparkline chart.
       None entries indicate missing quarters (break the line)."""
    percentile: Optional[int] = None
    """Percentile rank of current value within all-time history (0-100)."""
    historical_avg: Optional[float] = None
    """Mean of all available historical values for this metric."""
    vs_avg_delta: Optional[float] = None
    """current_value - historical_avg. Positive = above avg (more expensive)."""
    recent_quarter_label: Optional[str] = None
    """Label of the quarter used for 'current' value.
       e.g. 'Q3 2025' when the most recent quarter had negative earnings."""


class MetricQuarterSeries(BaseModel):
    metric_id: str
    label: str
    unit: str
    quarters: List[QuarterDataPoint]
    buy_quarter_index: Optional[int] = None
    trend_direction: Literal["up", "down", "stable"]
    change_pct: Optional[float] = None
    change_label: str = "stable"
    gauge_config: Optional[GaugeConfig] = None


class SectionStatus(BaseModel):
    label: Literal["Intact", "Watch", "Concern"]


class IntrinsicValuation(BaseModel):
    method: str
    intrinsic_value: float


class MetricSection(BaseModel):
    section_id: str
    title: str
    metrics: List[MetricQuarterSeries]
    status: SectionStatus
    score: Optional[float] = None
    intrinsic_valuations: Optional[List[IntrinsicValuation]] = None
    current_price: Optional[float] = None


class DataQuality(BaseModel):
    sources: List[str] = Field(default_factory=lambda: ["financial_ratios", "income_statements", "cash_flow_statements", "earnings"])
    staleness_days: Optional[int] = None
    earliest_data_year: Optional[int] = None
    quarterly_data_count: Optional[int] = None


class FundamentalsResponse(BaseModel):
    success: bool = True
    symbol: str
    company_name: Optional[str] = None
    currency: str = "USD"
    has_portfolio_position: bool = False
    purchase_date: Optional[date] = None
    purchase_period: Optional[str] = None
    quarters: List[str] = Field(default_factory=list)
    buy_quarter_index: Optional[int] = None
    composite_score: Optional[float] = None
    sections: List[MetricSection] = Field(default_factory=list)
    data_quality: Optional[DataQuality] = None
    error: Optional[str] = None
