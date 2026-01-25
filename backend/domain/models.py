"""
Pydantic models for Defeat Beta financial data.
These models represent the data contracts between providers and services.
Compatible with Pydantic v2.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, field_validator


# ============================================================================
# INCOME STATEMENT MODELS
# ============================================================================

class IncomeStatementRow(BaseModel):
    """Single row of income statement data (quarterly or annual)."""
    
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date
    
    revenue: Optional[Decimal] = None
    cost_of_goods_sold: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    operating_expenses: Optional[Decimal] = None
    rd_expenses: Optional[Decimal] = None
    sga_expenses: Optional[Decimal] = None
    operating_income: Optional[Decimal] = None
    interest_expense: Optional[Decimal] = None
    tax_expense: Optional[Decimal] = None
    net_income: Optional[Decimal] = None
    ebitda: Optional[Decimal] = None
    ebit: Optional[Decimal] = None
    
    currency: Optional[str] = "USD"
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IncomeStatementRows(BaseModel):
    """Collection of income statement rows."""
    rows: list[IncomeStatementRow] = Field(default_factory=list)
    
    def __len__(self):
        return len(self.rows)


# ============================================================================
# BALANCE SHEET MODELS
# ============================================================================

class BalanceSheetRow(BaseModel):
    """Single row of balance sheet data."""
    
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date
    
    total_assets: Optional[Decimal] = None
    current_assets: Optional[Decimal] = None
    cash_and_cash_equivalents: Optional[Decimal] = None
    accounts_receivable: Optional[Decimal] = None
    inventory: Optional[Decimal] = None
    property_plant_equipment_net: Optional[Decimal] = None
    intangible_assets: Optional[Decimal] = None
    goodwill: Optional[Decimal] = None
    
    total_liabilities: Optional[Decimal] = None
    current_liabilities: Optional[Decimal] = None
    accounts_payable: Optional[Decimal] = None
    short_term_debt: Optional[Decimal] = None
    long_term_debt: Optional[Decimal] = None
    total_debt: Optional[Decimal] = None
    
    shareholders_equity: Optional[Decimal] = None
    retained_earnings: Optional[Decimal] = None
    common_stock: Optional[Decimal] = None
    
    currency: Optional[str] = "USD"
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BalanceSheetRows(BaseModel):
    """Collection of balance sheet rows."""
    rows: list[BalanceSheetRow] = Field(default_factory=list)
    
    def __len__(self):
        return len(self.rows)


# ============================================================================
# CASH FLOW STATEMENT MODELS
# ============================================================================

class CashFlowRow(BaseModel):
    """Single row of cash flow statement data."""
    
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date
    
    cash_from_operating_activities: Optional[Decimal] = None
    net_income: Optional[Decimal] = None
    depreciation_amortization: Optional[Decimal] = None
    capital_expenditures: Optional[Decimal] = None
    cash_from_investing_activities: Optional[Decimal] = None
    cash_from_financing_activities: Optional[Decimal] = None
    dividends_paid: Optional[Decimal] = None
    
    currency: Optional[str] = "USD"
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CashFlowRows(BaseModel):
    """Collection of cash flow rows."""
    rows: list[CashFlowRow] = Field(default_factory=list)
    
    def __len__(self):
        return len(self.rows)


# ============================================================================
# EARNINGS MODELS
# ============================================================================

class EarningsRow(BaseModel):
    """Single row of earnings data with surprise metrics."""
    
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date
    announcement_date: Optional[date] = None
    
    eps_reported_basic: Optional[Decimal] = None
    eps_reported_diluted: Optional[Decimal] = None
    eps_estimate: Optional[Decimal] = None
    eps_surprise_amount: Optional[Decimal] = None
    eps_surprise_percent: Optional[Decimal] = None
    
    revenue_reported: Optional[Decimal] = None
    revenue_estimate: Optional[Decimal] = None
    
    currency: Optional[str] = "USD"
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EarningsRows(BaseModel):
    """Collection of earnings rows."""
    rows: list[EarningsRow] = Field(default_factory=list)
    
    def __len__(self):
        return len(self.rows)


# ============================================================================
# DIVIDEND MODELS
# ============================================================================

class DividendRow(BaseModel):
    """Single dividend payment record."""
    
    company_id: int
    ex_dividend_date: date
    payment_date: Optional[date] = None
    dividend_amount: Optional[Decimal] = None
    dividend_type: str = "regular"
    currency: Optional[str] = "USD"
    
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DividendRows(BaseModel):
    """Collection of dividend records."""
    rows: list[DividendRow] = Field(default_factory=list)
    
    def __len__(self):
        return len(self.rows)


# ============================================================================
# COMPLETE FINANCIALS RESPONSE MODEL
# ============================================================================

class CompleteFundamentals(BaseModel):
    """Complete set of all financial data from defeat-beta for a company."""
    
    company_id: int
    symbol: str
    
    income_statements: IncomeStatementRows
    balance_sheets: BalanceSheetRows
    cash_flows: CashFlowRows
    earnings: EarningsRows
    dividends: DividendRows
    
    next_earnings_date: Optional[date] = None
    
    # Metadata
    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    data_source: str = "defeat_beta"
    
    @property
    def total_rows_fetched(self) -> int:
        """Calculate total rows across all financial statements."""
        return sum([
            len(self.income_statements),
            len(self.balance_sheets),
            len(self.cash_flows),
            len(self.earnings),
            len(self.dividends),
        ])


# ============================================================================
# COMPANY REFRESH METADATA MODEL
# ============================================================================

class CompanyRefreshInfo(BaseModel):
    """Metadata about when a company's financials were last refreshed."""
    
    company_id: int
    ticker_symbol: str
    
    first_financial_data_loaded_at: Optional[datetime] = None
    last_financial_refresh_at: Optional[datetime] = None
    last_refreshed_fiscal_year: Optional[int] = None
    last_refreshed_fiscal_quarter: Optional[int] = None
    data_completeness_status: str = "INITIAL"  # INITIAL, PARTIAL, COMPLETE, CURRENT
    next_earnings_date: Optional[date] = None


# ============================================================================
# FILTER RESULT MODEL
# ============================================================================

class FilteringResult(BaseModel):
    """Result of filtering old vs new data."""
    
    total_rows_fetched: int
    total_rows_to_store: int
    rows_deduplicated: int = 0
    
    @property
    def deduplication_percentage(self) -> float:
        """Calculate percentage of rows deduplicated."""
        if self.total_rows_fetched == 0:
            return 0.0
        return (self.rows_deduplicated / self.total_rows_fetched) * 100