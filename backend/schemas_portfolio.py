# backend/schemas_portfolio.py
"""
Pydantic schemas for Portfolio API

Follows existing schemas.py patterns for request/response validation.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import date, datetime
from decimal import Decimal


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
    account_filter: Optional[List[str]] = Field(
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
    last_import_at: Optional[datetime]
    holdings_count: Optional[int] = 0
    total_value: Optional[float] = 0
    total_cost: Optional[float] = 0


class HoldingInfo(BaseModel):
    """Individual holding information."""
    
    holding_id: int
    symbol: str
    company_name: str
    sector: Optional[str]
    industry: Optional[str]
    exchange: Optional[str] = None
    market_group: Optional[str] = None
    quantity: float
    average_cost: float
    total_cost: float
    current_price: Optional[float]
    current_value: Optional[float]
    unrealized_gain_loss: Optional[float]
    unrealized_gain_loss_pct: Optional[float]
    realized_gain_loss: float
    first_purchase_date: Optional[date]
    last_transaction_date: Optional[date]
    account_name: Optional[str]
    account_type: Optional[str]


class AccountBreakdown(BaseModel):
    """Account-level summary for portfolio overview."""
    
    account_id: int
    account_name: str
    account_type: str
    brokerage_name: Optional[str]
    holdings_count: int
    total_value: float
    total_cost: float
    gain_loss: float
    gain_loss_pct: float


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
    top_holdings: List[Dict[str, Any]]
    account_breakdown: List[AccountBreakdown]
    error: Optional[str] = None


class ImportTransactionsResponse(BaseModel):
    """Response from import transactions operation."""
    
    success: bool
    import_batch_id: Optional[str] = None
    status: Optional[str] = None
    total_rows: Optional[int] = 0
    accounts_created: Optional[int] = 0
    accounts_updated: Optional[int] = 0
    transactions_imported: Optional[int] = 0
    holdings_updated: Optional[int] = 0
    dividends_extracted: Optional[int] = 0
    symbols_missing: Optional[List[str]] = []
    account_types: Optional[Dict[str, int]] = {}
    warnings: Optional[List[str]] = []
    error: Optional[str] = None
    duplicate_import: bool = False
    previous_import_date: Optional[str] = None
    previous_import_id: Optional[int] = None
    warning: Optional[str] = None


class ImportStatusResponse(BaseModel):
    """Response from import status polling endpoint."""

    success: bool
    import_batch_id: str
    status: str  # pending, processing, completed, failed
    total_rows: int = 0
    rows_parsed: int = 0
    rows_inserted: int = 0
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class ListBrokeragesResponse(BaseModel):
    """Response listing supported brokerages."""
    
    brokerages: List[BrokerageInfo]


class ListAccountsResponse(BaseModel):
    """Response listing user's portfolio accounts."""
    
    accounts: List[PortfolioAccountInfo]


class AccountHoldingsResponse(BaseModel):
    """Response with holdings for a specific account."""
    
    account_id: int
    account_name: str
    holdings: List[HoldingInfo]


class TransactionInfo(BaseModel):
    """Transaction detail."""
    
    transaction_id: int
    transaction_date: date
    settlement_date: Optional[date]
    activity_type: str
    activity_sub_type: Optional[str]
    symbol: Optional[str]
    security_name: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    commission: float
    net_cash_amount: float
    currency: str


class AccountTransactionsResponse(BaseModel):
    """Response with transactions for an account."""
    
    account_id: Optional[int] = None
    transactions: List[TransactionInfo]
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
    
    account_id: Optional[int] = None
    current_year_total: float
    monthly_summaries: List[MonthlyDividendsSummary]

class ManualTransactionRequest(BaseModel):
    """Request to manually add a transaction."""
    
    account_id: int = Field(..., gt=0)
    transaction_date: date
    activity_type: str = Field(
        ..., 
        description="Transaction type: BUY, SELL, DIVIDEND, DEPOSIT, WITHDRAWAL"
    )
    symbol: Optional[str] = Field(None, max_length=20)
    quantity: Optional[Decimal] = Field(None, gt=0)
    unit_price: Optional[Decimal] = Field(None, gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    notes: Optional[str] = Field(None, max_length=500)
    
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
    transaction_id: Optional[int] = None
    transaction: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    company_created: bool = False
    company_name: Optional[str] = None


# ============================================================================
# PERFORMANCE & BENCHMARK SCHEMAS
# ============================================================================

class PerformanceSnapshot(BaseModel):
    """Single portfolio value snapshot at a point in time."""

    date: str
    value: float
    cost_basis: float
    net_deposits: float = 0.0


class PerformanceResponse(BaseModel):
    """Portfolio performance time series."""

    success: bool
    period: str
    snapshots: List[PerformanceSnapshot]
    total_return: float
    total_return_pct: float
    best_day: Optional[Dict[str, Any]] = None
    worst_day: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BenchmarkInfo(BaseModel):
    """Benchmark index metadata."""

    role: str
    symbol: str
    name: str
    market: str
    description: Optional[str] = None


class BenchmarkListResponse(BaseModel):
    """List of available benchmarks."""

    success: bool
    benchmarks: List[BenchmarkInfo]
    error: Optional[str] = None


class BenchmarkSeries(BaseModel):
    """Single benchmark performance series."""

    symbol: str
    name: str
    data: List[Dict[str, Any]]


class BenchmarkCompareResponse(BaseModel):
    """Portfolio vs benchmark comparison."""

    success: bool
    period: str
    portfolio: List[Dict[str, Any]]
    benchmarks: List[BenchmarkSeries]
    error: Optional[str] = None


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
    sectors: List[SectorAllocationSegment]


class AccountHoldingBreakdown(BaseModel):
    """Per-account breakdown within an aggregated holding."""

    account_id: int
    account_name: Optional[str] = None
    account_type: Optional[str] = None
    quantity: float = 0
    total_cost: float = 0
    current_value: float = 0


class AggregatedHolding(BaseModel):
    """A holding aggregated across all accounts (one row per symbol)."""

    company_id: int
    symbol: str
    company_name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    exchange: Optional[str] = None
    market_group: Optional[str] = None
    security_type: Optional[str] = None
    currency: Optional[str] = None
    total_quantity: float = 0
    average_cost: float = 0
    total_cost: float = 0
    current_price: Optional[float] = None
    current_value: float = 0
    unrealized_gain_loss: float = 0
    unrealized_gain_loss_pct: float = 0
    accounts_count: int = 0
    account_breakdown: List[AccountHoldingBreakdown] = []


class PortfolioAllocationResponse(BaseModel):
    """Portfolio allocation breakdown response."""

    success: bool
    group_by: str
    segments: List[AllocationSegment] = []
    types: List[TypeAllocationSegment] = []
    total_value: float = 0
    error: Optional[str] = None


# ============================================================================
# EXTENDED DIVIDEND SCHEMAS
# ============================================================================

class DividendDetail(BaseModel):
    """Full dividend detail for history table."""

    dividend_id: int
    symbol: str
    company_name: Optional[str] = None
    payment_date: date
    amount: float
    shares_held: Optional[float] = None
    amount_per_share: Optional[float] = None
    account_name: Optional[str] = None
    account_type: Optional[str] = None


class DividendHistoryResponse(BaseModel):
    """Full dividend history response."""

    success: bool
    account_id: Optional[int] = None
    dividends: List[DividendDetail]
    total_count: int
    current_year_total: float = 0
    error: Optional[str] = None


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
    tracking_error: Optional[float] = None
    information_ratio: Optional[float] = None
    beta: Optional[float] = None
    alpha: Optional[float] = None
    error: Optional[str] = None
    error_code: Optional[str] = None

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
    drawdowns: List[DrawdownPoint]
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_start: Optional[str] = None
    max_drawdown_end: Optional[str] = None
    max_drawdown_recovery: Optional[str] = None
    avg_drawdown: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None


class CovarianceResponse(BaseModel):
    success: bool
    period: str
    holdings: List[str]
    covariance_matrix: List[List[float]]
    correlation_matrix: List[List[float]]
    error: Optional[str] = None
    error_code: Optional[str] = None


class EfficientFrontierPoint(BaseModel):
    volatility: float
    expected_return: float
    weights: Dict[str, float]
    sharpe_ratio: Optional[float] = None


class EfficientFrontierResponse(BaseModel):
    success: bool
    frontier: List[EfficientFrontierPoint]
    max_sharpe: Optional[EfficientFrontierPoint] = None
    min_variance: Optional[EfficientFrontierPoint] = None
    cml: Optional[List[Dict[str, float]]] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


class RollingSharpeResponse(BaseModel):
    success: bool
    period: str
    window: int
    series: List[Dict[str, Any]]
    error: Optional[str] = None
    error_code: Optional[str] = None


class RiskContributionItem(BaseModel):
    symbol: str
    weight: float
    marginal_risk: float
    component_risk: float
    risk_pct: float


class RiskContributionResponse(BaseModel):
    success: bool
    contributions: List[RiskContributionItem]
    total_risk: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None


class FactorExposureResponse(BaseModel):
    success: bool
    exposures: Dict[str, float]
    r_squared: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None


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


class HoldingPerformanceResponse(BaseModel):
    success: bool = True
    symbol: str
    period: str
    snapshots: List[HoldingPerformanceSnapshot] = []
    total_return: float = 0
    total_return_pct: float = 0
    total_dividends: float = 0
    total_dividends_pct: float = 0
    error: Optional[str] = None


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