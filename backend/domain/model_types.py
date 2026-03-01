
"""
Pydantic models for financial data (Defeat Beta + YFinance).
Aligned 1:1 with Supabase schema.
Compatible with Pydantic v2.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


# ============================================================================
# INCOME STATEMENT MODELS
# ============================================================================

class IncomeStatementRow(BaseModel):
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date

    # Core
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
    currency: Optional[str] = "USD"

    # NEW — fields present in Supabase
    non_operating_income_expense: Optional[Decimal] = None          # NEW
    pretax_income: Optional[Decimal] = None                         # NEW
    equity_in_earnings: Optional[Decimal] = None                    # NEW
    minority_interest: Optional[Decimal] = None                     # NEW
    income_from_continuing_operations: Optional[Decimal] = None     # NEW
    discontinued_operations: Optional[Decimal] = None               # NEW
    net_income_to_common: Optional[Decimal] = None                  # NEW
    preferred_dividends: Optional[Decimal] = None                   # NEW
    ebit: Optional[Decimal] = None                                  # NEW
    last_validated_at: Optional[datetime] = None                    # NEW

    # Canonical per-share metrics (stored in Supabase income_statements)
    eps_basic: Optional[Decimal] = None
    eps_diluted: Optional[Decimal] = None
    shares_outstanding_basic: Optional[int] = None
    shares_outstanding_diluted: Optional[int] = None

    # Metadata
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class IncomeStatementRows(BaseModel):
    rows: list[IncomeStatementRow] = Field(default_factory=list)
    def __len__(self): return len(self.rows)



# ============================================================================
# BALANCE SHEET MODELS
# ============================================================================

class BalanceSheetRow(BaseModel):
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date

    # Core
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

    # NEW — required by Supabase
    long_term_investments: Optional[Decimal] = None             # NEW
    other_non_current_assets: Optional[Decimal] = None          # NEW
    other_current_liabilities: Optional[Decimal] = None         # NEW
    minority_interest: Optional[Decimal] = None                 # NEW
    total_liabilities_and_equity: Optional[Decimal] = None      # NEW
    last_validated_at: Optional[datetime] = None                # NEW

    # Metadata
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class BalanceSheetRows(BaseModel):
    rows: list[BalanceSheetRow] = Field(default_factory=list)
    def __len__(self): return len(self.rows)



# ============================================================================
# CASH FLOW STATEMENT MODELS
# ============================================================================

class CashFlowRow(BaseModel):
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date

    # Core
    cash_from_operating_activities: Optional[Decimal] = None
    net_income: Optional[Decimal] = None
    depreciation_amortization: Optional[Decimal] = None
    capital_expenditures: Optional[Decimal] = None
    cash_from_investing_activities: Optional[Decimal] = None
    cash_from_financing_activities: Optional[Decimal] = None
    dividends_paid: Optional[Decimal] = None
    currency: Optional[str] = "USD"

    # NEW — required by Supabase
    change_in_working_capital: Optional[Decimal] = None        # NEW
    deferred_taxes: Optional[Decimal] = None                   # NEW
    stock_based_compensation: Optional[Decimal] = None         # NEW
    acquisitions: Optional[Decimal] = None                     # NEW
    asset_sales: Optional[Decimal] = None                      # NEW
    investment_purchases: Optional[Decimal] = None             # NEW
    debt_issued: Optional[Decimal] = None                      # NEW
    debt_repayment: Optional[Decimal] = None                   # NEW
    share_repurchases: Optional[Decimal] = None                # NEW
    share_issuance: Optional[Decimal] = None                   # NEW
    last_validated_at: Optional[datetime] = None               # NEW

    # Metadata
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class CashFlowRows(BaseModel):
    rows: list[CashFlowRow] = Field(default_factory=list)
    def __len__(self): return len(self.rows)



# ============================================================================
# EARNINGS MODELS
# ============================================================================

class EarningsRow(BaseModel):
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: Optional[int] = Field(None, ge=1, le=4)
    period_end_date: date
    announcement_date: Optional[date] = None

    # Core EPS
    eps_reported_basic: Optional[Decimal] = None
    eps_reported_diluted: Optional[Decimal] = None
    eps_estimate: Optional[Decimal] = None
    eps_surprise_amount: Optional[Decimal] = None
    eps_surprise_percent: Optional[Decimal] = None

    # Revenue
    revenue_reported: Optional[Decimal] = None
    revenue_estimate: Optional[Decimal] = None

    # NEW — required by Supabase
    revenue_surprise_amount: Optional[Decimal] = None        # NEW
    revenue_surprise_percent: Optional[Decimal] = None       # NEW
    shares_outstanding_basic: Optional[int] = None           # NEW
    shares_outstanding_diluted: Optional[int] = None         # NEW
    last_validated_at: Optional[datetime] = None             # NEW

    currency: Optional[str] = "USD"
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class EarningsRows(BaseModel):
    rows: list[EarningsRow] = Field(default_factory=list)
    def __len__(self): return len(self.rows)



# ============================================================================
# DIVIDEND MODELS
# ============================================================================

class DividendRow(BaseModel):
    company_id: int
    ex_dividend_date: date
    payment_date: Optional[date] = None
    dividend_amount: Optional[Decimal] = None
    dividend_type: str = "regular"
    currency: Optional[str] = "USD"

    # NEW — required by Supabase
    record_date: Optional[date] = None            # NEW
    frequency: Optional[str] = None               # NEW
    last_validated_at: Optional[datetime] = None  # NEW

    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DividendRows(BaseModel):
    rows: list[DividendRow] = Field(default_factory=list)
    def __len__(self): return len(self.rows)



# ============================================================================
# COMPLETE FINANCIALS RESPONSE
# ============================================================================

class CompleteFundamentals(BaseModel):
    company_id: int
    symbol: str

    income_statements: IncomeStatementRows
    balance_sheets: BalanceSheetRows
    cash_flows: CashFlowRows
    earnings: EarningsRows
    dividends: DividendRows

    next_earnings_date: Optional[date] = None

    fetched_at: datetime = Field(default_factory=datetime.utcnow)
    data_source: str = "defeat_beta"  # Overall batch source

    @property
    def total_rows_fetched(self) -> int:
        return (
            len(self.income_statements)
            + len(self.balance_sheets)
            + len(self.cash_flows)
            + len(self.earnings)
            + len(self.dividends)
        )



# ============================================================================
# COMPANY REFRESH METADATA
# ============================================================================

class CompanyRefreshInfo(BaseModel):
    company_id: int
    ticker_symbol: str

    first_financial_data_loaded_at: Optional[datetime] = None
    last_financial_refresh_at: Optional[datetime] = None
    last_refreshed_fiscal_year: Optional[int] = None
    last_refreshed_fiscal_quarter: Optional[int] = None
    data_completeness_status: str = "INITIAL"
    next_earnings_date: Optional[date] = None



# ============================================================================
# FILTERING RESULT
# ============================================================================

class FilteringResult(BaseModel):
    total_rows_fetched: int
    total_rows_to_store: int
    rows_deduplicated: int = 0

    @property
    def deduplication_percentage(self) -> float:
        if self.total_rows_fetched == 0:
            return 0.0
        return (self.rows_deduplicated / self.total_rows_fetched) * 100
