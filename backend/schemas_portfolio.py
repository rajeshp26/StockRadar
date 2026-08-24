# backend/schemas_portfolio.py
"""
Pydantic schemas for Portfolio API

Follows existing schemas.py patterns for request/response validation.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class ImportTransactionsRequest(BaseModel):
    """Request to import transactions from CSV file."""

    brokerage_code: str = Field(
        ...,
        description="Brokerage identifier (wealthsimple, ibkr, questrade)",
        min_length=1,
        max_length=50,
    )
    csv_content: str = Field(
        ...,
        description="Base64-encoded CSV file content",
        min_length=1,
    )
    account_filter: list[str] | None = Field(
        None,
        description="List of account types to import (e.g., ['TFSA', 'RRSP']). None = import all.",
    )

    @field_validator("brokerage_code")
    @classmethod
    def lowercase_brokerage(cls, v: str) -> str:
        return v.lower().strip()


class DeleteAccountRequest(BaseModel):
    """Request to delete portfolio account and all associated data."""

    account_id: int = Field(..., gt=0, description="Account ID to delete")


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class BrokerageInfo(BaseModel):
    """Brokerage information."""

    brokerage_id: int
    brokerage_code: str
    brokerage_name: str
    country_code: str
    is_active: bool


class PortfolioAccountInfo(BaseModel):
    """Portfolio account information."""

    account_id: int
    account_name: str
    account_type: str
    account_external_id: str
    brokerage_name: str
    brokerage_code: str
    currency: str
    is_active: bool
    created_at: datetime
    last_import_at: datetime | None
    holdings_count: int | None = 0
    total_value: float | None = 0
    total_cost: float | None = 0


class HoldingInfo(BaseModel):
    """Individual holding information."""

    holding_id: int
    symbol: str
    company_name: str
    sector: str | None
    industry: str | None
    exchange: str | None = None
    market_group: str | None = None
    quantity: float
    average_cost: float
    total_cost: float
    current_price: float | None
    current_value: float | None
    unrealized_gain_loss: float | None
    unrealized_gain_loss_pct: float | None
    realized_gain_loss: float
    first_purchase_date: date | None
    last_transaction_date: date | None
    account_name: str | None
    account_type: str | None


class AccountBreakdown(BaseModel):
    """Account-level summary for portfolio overview."""

    account_id: int
    account_name: str
    account_type: str
    brokerage_name: str | None
    holdings_count: int
    total_value: float
    total_cost: float
    gain_loss: float
    gain_loss_pct: float
    value_currency: str | None = None


class PortfolioOverviewResponse(BaseModel):
    """Portfolio overview response."""

    success: bool
    net_worth: float
    total_cost_basis: float
    total_gain_loss: float
    total_gain_loss_pct: float
    ytd_dividends: float
    total_holdings_count: int
    accounts_count: int
    top_holdings: list[dict[str, Any]]
    account_breakdown: list[AccountBreakdown]
    value_currency: str | None = None
    error: str | None = None


class ImportTransactionsResponse(BaseModel):
    """Response from import transactions operation."""

    success: bool
    import_batch_id: str | None = None
    status: str | None = None
    total_rows: int | None = 0
    accounts_created: int | None = 0
    accounts_updated: int | None = 0
    transactions_imported: int | None = 0
    holdings_updated: int | None = 0
    dividends_extracted: int | None = 0
    symbols_missing: list[str] | None = []
    account_types: dict[str, int] | None = {}
    warnings: list[str] | None = []
    error: str | None = None
    duplicate_import: bool = False
    previous_import_date: str | None = None
    previous_import_id: int | None = None
    warning: str | None = None


class ImportStatusResponse(BaseModel):
    """Response from import status polling endpoint."""

    success: bool
    import_batch_id: str
    status: str  # pending, processing, completed, failed
    total_rows: int = 0
    rows_parsed: int = 0
    rows_inserted: int = 0
    error: str | None = None
    result: dict[str, Any] | None = None


class ListBrokeragesResponse(BaseModel):
    """Response listing supported brokerages."""

    brokerages: list[BrokerageInfo]


class ListAccountsResponse(BaseModel):
    """Response listing user's portfolio accounts."""

    accounts: list[PortfolioAccountInfo]


class AccountHoldingsResponse(BaseModel):
    """Response with holdings for a specific account."""

    account_id: int
    account_name: str
    holdings: list[HoldingInfo]


class TransactionInfo(BaseModel):
    """Transaction detail."""

    transaction_id: int
    transaction_date: date
    settlement_date: date | None
    activity_type: str
    activity_sub_type: str | None
    symbol: str | None
    security_name: str | None
    quantity: float | None
    unit_price: float | None
    commission: float
    net_cash_amount: float
    currency: str


class AccountTransactionsResponse(BaseModel):
    """Response with transactions for an account."""

    account_id: int | None = None
    transactions: list[TransactionInfo]
    total_count: int


class DividendInfo(BaseModel):
    """Dividend payment information."""

    dividend_id: int
    symbol: str
    payment_date: date
    amount: float
    fiscal_year: int
    fiscal_month: int


class MonthlyDividendsSummary(BaseModel):
    """Monthly dividend summary."""

    fiscal_year: int
    fiscal_month: int
    payment_count: int
    total_amount: float
    paying_companies: int


class AccountDividendsResponse(BaseModel):
    """Response with dividend data for an account."""

    account_id: int | None = None
    current_year_total: float
    monthly_summaries: list[MonthlyDividendsSummary]

class ManualTransactionRequest(BaseModel):
    """Request to manually add a transaction."""

    account_id: int = Field(..., gt=0)
    transaction_date: date
    activity_type: str = Field(
        ...,
        description="Transaction type: BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAWAL"
    )
    symbol: str | None = Field(None, max_length=20)
    quantity: Decimal | None = Field(None, gt=0)
    unit_price: Decimal | None = Field(None, gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = Field(None, max_length=500)

    @field_validator("activity_type")
    @classmethod
    def validate_activity_type(cls, v: str) -> str:
        allowed = ["BUY", "SELL", "DIVIDEND", "DEPOSIT", "WITHDRAWAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Activity type must be one of: {', '.join(allowed)}")
        return v.upper()


class ManualTransactionResponse(BaseModel):
    """Response from manual transaction creation."""
    success: bool
    transaction_id: int | None = None
    transaction: dict[str, Any] | None = None
    error: str | None = None
    company_created: bool = False
    company_name: str | None = None


# ============================================================================
# PERFORMANCE & BENCHMARK SCHEMAS
# ============================================================================

class PerformanceSnapshot(BaseModel):
    """Single portfolio value snapshot at a point in time."""

    date: str
    value: float
    cost_basis: float
    net_deposits: float = 0.0
    cash_balance: float | None = None
    holdings: list[dict[str, Any]] | None = None


class PerformanceResponse(BaseModel):
    """Portfolio performance time series."""

    success: bool
    period: str
    snapshots: list[PerformanceSnapshot]
    total_return: float
    total_return_pct: float
    twr_pct: float = 0.0
    mwr_pct: float = 0.0
    cagr_pct: float = 0.0
    best_day: dict[str, Any] | None = None
    worst_day: dict[str, Any] | None = None
    error: str | None = None
    data_source: str | None = None
    data_quality_flag: str | None = None
    return_methodology: str | None = None
    spike_detected: bool = False
    locf_count: int | None = None


class PerformanceBatchResponse(BaseModel):
    """Batch portfolio performance response with multiple periods."""

    success: bool
    results: dict[str, PerformanceResponse | None]


class BenchmarkInfo(BaseModel):
    """Benchmark index metadata."""

    role: str
    symbol: str
    name: str
    market: str
    description: str | None = None


class BenchmarkListResponse(BaseModel):
    """List of available benchmarks."""

    success: bool
    benchmarks: list[BenchmarkInfo]
    error: str | None = None


class BenchmarkSeries(BaseModel):
    """Single benchmark performance series."""

    symbol: str
    name: str
    data: list[dict[str, Any]]


class BenchmarkCompareResponse(BaseModel):
    """Portfolio vs benchmark comparison."""

    success: bool
    period: str
    portfolio: list[dict[str, Any]]
    benchmarks: list[BenchmarkSeries]
    error: str | None = None


# ============================================================================
# ALLOCATION SCHEMAS
# ============================================================================

class AllocationSegment(BaseModel):
    """Single allocation breakdown segment."""

    segment: str
    value: float
    weight: float
    count: int
    gain_loss: float = 0


class SectorAllocationSegment(BaseModel):
    """A sector segment within a security type group."""

    segment: str
    value: float
    weight: float
    count: int
    gain_loss: float = 0


class TypeAllocationSegment(BaseModel):
    """A security type group (e.g. Stocks, ETFs) with nested sector segments."""

    type: str
    type_label: str
    value: float
    weight: float
    count: int
    gain_loss: float = 0
    sectors: list[SectorAllocationSegment]


class AccountHoldingBreakdown(BaseModel):
    """Per-account breakdown within an aggregated holding."""

    account_id: int
    account_name: str | None = None
    account_type: str | None = None
    quantity: float = 0
    total_cost: float = 0
    current_value: float = 0


class AggregatedHolding(BaseModel):
    """A holding aggregated across all accounts (one row per symbol)."""

    company_id: int
    symbol: str
    company_name: str
    sector: str | None = None
    industry: str | None = None
    exchange: str | None = None
    market_group: str | None = None
    security_type: str | None = None
    currency: str | None = None
    total_quantity: float = 0
    average_cost: float = 0
    total_cost: float = 0
    current_price: float | None = None
    current_value: float = 0
    unrealized_gain_loss: float = 0
    unrealized_gain_loss_pct: float = 0
    accounts_count: int = 0
    account_breakdown: list[AccountHoldingBreakdown] = []


class PortfolioAllocationResponse(BaseModel):
    """Portfolio allocation breakdown response."""

    success: bool
    group_by: str
    segments: list[AllocationSegment] = []
    types: list[TypeAllocationSegment] = []
    total_value: float = 0
    error: str | None = None


# ============================================================================
# EXTENDED DIVIDEND SCHEMAS
# ============================================================================

class DividendDetail(BaseModel):
    """Full dividend detail for history table."""

    dividend_id: int
    symbol: str
    company_name: str | None = None
    payment_date: date
    amount: float
    shares_held: float | None = None
    amount_per_share: float | None = None
    account_name: str | None = None
    account_type: str | None = None


class DividendHistoryResponse(BaseModel):
    """Full dividend history response."""

    success: bool
    account_id: int | None = None
    dividends: list[DividendDetail]
    total_count: int
    current_year_total: float = 0
    error: str | None = None


# ============================================================================
# DIVIDEND DASHBOARD SCHEMAS
# ============================================================================

class UpcomingExDate(BaseModel):
    """Upcoming ex-dividend date for a held position."""

    symbol: str
    company_name: str
    ex_dividend_date: str
    amount_per_share: float = 0.0
    estimated_income: float = 0.0
    dividend_type: str = "regular"
    confidence: str = "low"
    trust_score: float | None = None
    trust_label: str | None = None
    data_source: str | None = None


class MetricWithCoverage(BaseModel):
    """Metric value with coverage percentage."""

    value: float | None = None
    coverage_pct: float = 0.0


class PortfolioDividendSummary(BaseModel):
    """Portfolio-level dividend summary response."""

    trailing_12m_income: float = 0.0
    forward_annual_estimate: float = 0.0
    ytd_dividends: float = 0.0
    forward_yield_on_cost: float | None = None
    avg_monthly_trailing: float = 0.0
    avg_monthly_forward: float = 0.0
    portfolio_growth_5yr: MetricWithCoverage = MetricWithCoverage()
    portfolio_safety: MetricWithCoverage = MetricWithCoverage()
    goal_progress: dict[str, Any] | None = None
    currency: str | None = None
    currencies_mixed: bool = False
    last_updated: datetime | None = None


class PortfolioDividendHolding(BaseModel):
    """Per-holding dividend data."""

    account_id: int
    symbol: str
    company_name: str
    sector: str | None = None
    quantity: float = 0.0
    market_value: float = 0.0
    total_cost: float = 0.0
    forward_income: float = 0.0
    trailing_12m_income: float = 0.0
    current_yield: float | None = None
    forward_yield_on_cost: float | None = None
    payout_ratio: float | None = None
    increase_streak: int | None = None
    safety_score: float | None = None
    next_event: UpcomingExDate | None = None


class DividendHistoryPoint(BaseModel):
    """Single dividend history entry."""

    date: str
    amount: float


class RecentPayment(BaseModel):
    """Recent dividend payment entry."""

    payment_date: str
    amount: float
    shares_held: float | None = None


class IncomeSummary(BaseModel):
    """Income summary for a single holding."""

    trailing_12m: float = 0.0
    forward: float = 0.0
    ytd: float = 0.0
    yield_on_cost: float | None = None


class QualityMetrics(BaseModel):
    """Quality metrics for a single holding."""

    safety_score: float | None = None
    payout_ratio: float | None = None
    growth_5yr: float | None = None
    increase_streak: int | None = None


class PortfolioDividendHoldingDetail(BaseModel):
    """Detailed dividend data for a single holding."""

    symbol: str
    company_name: str
    sector: str | None = None
    income: IncomeSummary = IncomeSummary()
    quality_metrics: QualityMetrics | None = None
    dividend_history: list[DividendHistoryPoint] = []
    recent_payments: list[RecentPayment] = []


# ============================================================================
# RISK METRICS SCHEMAS
# ============================================================================

from enum import Enum


class RiskMetricError(str, Enum):
    INSUFFICIENT_DATA = "insufficient_data"
    SINGLE_HOLDING = "single_holding"
    NO_HOLDINGS = "no_holdings"
    DATA_INTEGRITY = "data_integrity"
    COMPUTATION_FAILED = "computation_failed"
    ACCOUNT_NOT_FOUND = "account_not_found"
    BENCHMARK_NOT_FOUND = "benchmark_not_found"


class RiskMetricsResponse(BaseModel):
    success: bool
    period: str
    variance: float = 0.0
    std_deviation: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    value_at_risk_95: float = 0.0
    value_at_risk_99: float = 0.0
    conditional_var_95: float = 0.0
    downside_deviation: float = 0.0
    total_return_pct: float = 0.0
    tracking_error: float | None = None
    information_ratio: float | None = None
    beta: float | None = None
    alpha: float | None = None
    error: str | None = None
    error_code: str | None = None

    @field_validator("sharpe_ratio")
    @classmethod
    def warn_sharpe_range(cls, v: float) -> float:
        if v != 0.0 and (v < -3.0 or v > 5.0):
            import logging
            logging.getLogger(__name__).warning(f"sharpe_ratio={v} outside sane range [-3, 5]")
        return v

    @field_validator("max_drawdown_pct")
    @classmethod
    def clamp_drawdown(cls, v: float) -> float:
        if v > 0.0:
            return 0.0
        if v < -1.0:
            return -1.0
        return v

    @field_validator("value_at_risk_95")
    @classmethod
    def warn_positive_var(cls, v: float) -> float:
        if v > 0.0:
            import logging
            logging.getLogger(__name__).warning(f"value_at_risk_95={v} is positive (unusual)")
        return v


class DrawdownPoint(BaseModel):
    date: str
    value: float
    drawdown_pct: float


class DrawdownResponse(BaseModel):
    success: bool
    period: str
    drawdowns: list[DrawdownPoint]
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_start: str | None = None
    max_drawdown_end: str | None = None
    max_drawdown_recovery: str | None = None
    avg_drawdown: float = 0.0
    error: str | None = None
    error_code: str | None = None


class CovarianceResponse(BaseModel):
    success: bool
    period: str
    holdings: list[str]
    covariance_matrix: list[list[float]]
    correlation_matrix: list[list[float]]
    error: str | None = None
    error_code: str | None = None


class EfficientFrontierPoint(BaseModel):
    volatility: float
    expected_return: float
    weights: dict[str, float]
    sharpe_ratio: float | None = None


class EfficientFrontierResponse(BaseModel):
    success: bool
    frontier: list[EfficientFrontierPoint]
    max_sharpe: EfficientFrontierPoint | None = None
    min_variance: EfficientFrontierPoint | None = None
    cml: list[dict[str, float]] | None = None
    error: str | None = None
    error_code: str | None = None


class RollingSharpeResponse(BaseModel):
    success: bool
    period: str
    window: int
    series: list[dict[str, Any]]
    error: str | None = None
    error_code: str | None = None


class RiskContributionItem(BaseModel):
    symbol: str
    weight: float
    marginal_risk: float
    component_risk: float
    risk_pct: float


class RiskContributionResponse(BaseModel):
    success: bool
    contributions: list[RiskContributionItem]
    total_risk: float = 0.0
    error: str | None = None
    error_code: str | None = None


class FactorExposureResponse(BaseModel):
    success: bool
    exposures: dict[str, float]
    r_squared: float = 0.0
    error: str | None = None
    error_code: str | None = None


# ============================================================================
# HOLDING PERFORMANCE SCHEMAS
# ============================================================================

class HoldingExistsResponse(BaseModel):
    symbol: str
    held: bool


class HoldingPerformanceSnapshot(BaseModel):
    date: str
    position_value: float
    cost_basis: float
    cumulative_invested: float
    shares_held: float = 0
    avg_cost_per_share: float = 0


class MonthlyReturnSummary(BaseModel):
    month: str
    return_pct: float
    label: str


class DrawdownInfo(BaseModel):
    dd_pct: float
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int | None = None
    is_ongoing: bool = False


class DaysAboveCostBasis(BaseModel):
    days_above: int
    total_days: int
    pct_above: float


class HoldingPerformanceResponse(BaseModel):
    success: bool = True
    symbol: str
    period: str
    snapshots: list[HoldingPerformanceSnapshot] = []
    total_return: float = 0
    total_return_pct: float = 0
    total_dividends: float = 0
    total_dividends_pct: float = 0
    combined_return: float = 0
    best_month: MonthlyReturnSummary | None = None
    worst_month: MonthlyReturnSummary | None = None
    max_drawdown: DrawdownInfo | None = None
    longest_drawdown: DrawdownInfo | None = None
    volatility_30d: float = 0
    days_above_cost_basis: DaysAboveCostBasis | None = None
    error: str | None = None


class HoldingDividendSummary(BaseModel):
    fiscal_year: int
    fiscal_quarter: int
    label: str
    total_amount: float
    payments_count: int
    amount_per_share: float


class HoldingTransactionInfo(BaseModel):
    transaction_id: int
    transaction_date: str
    activity_sub_type: str
    quantity: float
    unit_price: float
    commission: float
    net_cash_amount: float
    account_name: str
    account_type: str


class HoldingAccountBreakdown(BaseModel):
    account_id: int
    account_name: str
    account_type: str
    shares_held: float = 0
    total_cost: float = 0
    current_value: float = 0
    unrealized_gain_loss: float = 0
    unrealized_gain_loss_pct: float = 0
    dividends_received: float = 0


class DashboardAccount(BaseModel):
    """Account entry in the portfolio dashboard bundle."""
    account_id: int
    account_name: str
    account_type: str
    brokerage_name: str | None = None
    currency: str
    holdings_count: int
    total_value: float
    total_cost: float
    gain_loss: float
    gain_loss_pct: float
    value_currency: str | None = None


class DashboardOverview(BaseModel):
    """Overview section of the portfolio dashboard."""
    total_value: float
    total_cost_basis: float
    total_gain_loss: float
    total_gain_loss_pct: float
    ytd_dividends: float
    holdings_count: int
    accounts_count: int
    value_currency: str | None = None


class DashboardHolding(BaseModel):
    """Holding entry in the portfolio dashboard bundle."""
    company_id: int | None = None
    symbol: str
    company_name: str | None = None
    quantity: float
    current_price: float
    current_value: float
    total_cost: float
    unrealized_gain_loss: float
    unrealized_gain_loss_pct: float
    value_currency: str | None = None


class PortfolioDashboardResponse(BaseModel):
    """Portfolio dashboard bundle — single-enrichment response."""
    accounts: list[DashboardAccount]
    overview: DashboardOverview
    holdings: list[DashboardHolding]
