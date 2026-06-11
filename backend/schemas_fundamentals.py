from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional, Literal

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
    narrative_label: Optional[str] = None
    status: Optional[Literal["normal", "not_applicable", "insufficient_data"]] = None
    components: Optional[List[MetricComponent]] = None
    ttm_eps: Optional[float] = None
    quarter_end_price: Optional[float] = None


class MetricQuarterSeries(BaseModel):
    metric_id: str
    label: str
    unit: str
    quarters: List[QuarterDataPoint]
    buy_quarter_index: Optional[int] = None
    trend_direction: Literal["up", "down", "stable"]
    change_pct: Optional[float] = None
    change_label: str = "stable"


class SectionStatus(BaseModel):
    label: Literal["Intact", "Watch", "Concern"]


class MetricSection(BaseModel):
    section_id: str
    title: str
    metrics: List[MetricQuarterSeries]
    status: SectionStatus
    score: Optional[float] = None


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
