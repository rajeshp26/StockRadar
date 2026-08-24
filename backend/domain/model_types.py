
"""
Pydantic models for financial data (Defeat Beta + YFinance).
Aligned 1:1 with Supabase schema.
Compatible with Pydantic v2.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ============================================================================
# INCOME STATEMENT MODELS
# ============================================================================

class IncomeStatementRow(BaseModel):
    company_id: int
    fiscal_year: int = Field(..., ge=1900, le=2100)
    fiscal_quarter: int | None = Field(None, ge=1, le=4)
    period_end_date: date

    # Core
    revenue: Decimal | None = None
    cost_of_goods_sold: Decimal | None = None
    gross_profit: Decimal | None = None
    operating_expenses: Decimal | None = None
    rd_expenses: Decimal | None = None
    sga_expenses: Decimal | None = None
    operating_income: Decimal | None = None
    interest_expense: Decimal | None = None
    tax_expense: Decimal | None = None
    net_income: Decimal | None = None
    ebitda: Decimal | None = None
    currency: str | None = "USD"

    # NEW — fields present in Supabase
    non_operating_income_expense: Decimal | None = None          # NEW
    pretax_income: Decimal | None = None                         # NEW
    equity_in_earnings: Decimal | None = None                    # NEW
    minority_interest: Decimal | None = None                     # NEW
    income_from_continuing_operations: Decimal | None = None     # NEW
    discontinued_operations: Decimal | None = None               # NEW
    net_income_to_common: Decimal | None = None                  # NEW
    preferred_dividends: Decimal | None = None                   # NEW
    ebit: Decimal | None = None                                  # NEW
    last_validated_at: datetime | None = None                    # NEW

    # Canonical per-share metrics (stored in Supabase income_statements)
    eps_basic: Decimal | None = None
    eps_diluted: Decimal | None = None
    shares_outstanding_basic: int | None = None
    shares_outstanding_diluted: int | None = None
    # Phase 3 — Tier 1 new columns
    interest_income: Decimal | None = None
    effective_tax_rate: Decimal | None = None
    # Phase 5 — Tier 2 new columns
    total_unusual_items: Decimal | None = None
    special_charges: Decimal | None = None

    # Metadata
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: str | None = None
    field_sources: dict[str, list[str]] | None = None
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
    fiscal_quarter: int | None = Field(None, ge=1, le=4)
    period_end_date: date

    # Core
    total_assets: Decimal | None = None
    current_assets: Decimal | None = None
    cash_and_cash_equivalents: Decimal | None = None
    accounts_receivable: Decimal | None = None
    inventory: Decimal | None = None
    property_plant_equipment_net: Decimal | None = None
    intangible_assets: Decimal | None = None
    goodwill: Decimal | None = None

    total_liabilities: Decimal | None = None
    current_liabilities: Decimal | None = None
    accounts_payable: Decimal | None = None
    short_term_debt: Decimal | None = None
    long_term_debt: Decimal | None = None
    total_debt: Decimal | None = None

    shareholders_equity: Decimal | None = None
    retained_earnings: Decimal | None = None
    common_stock: Decimal | None = None
    currency: str | None = "USD"

    # NEW — required by Supabase
    long_term_investments: Decimal | None = None             # NEW
    other_non_current_assets: Decimal | None = None          # NEW
    other_current_liabilities: Decimal | None = None         # NEW
    minority_interest: Decimal | None = None                 # NEW
    total_liabilities_and_equity: Decimal | None = None      # NEW
    last_validated_at: datetime | None = None                # NEW
    # Phase 3 — Tier 1 new columns
    shares_outstanding: int | None = None
    invested_capital: Decimal | None = None
    # Phase 5 — Tier 2 new columns
    capital_lease_obligations: Decimal | None = None
    total_non_current_liabilities: Decimal | None = None
    total_non_current_assets: Decimal | None = None
    tangible_book_value: Decimal | None = None
    deferred_revenue_current: Decimal | None = None
    deferred_revenue_non_current: Decimal | None = None
    other_current_assets: Decimal | None = None
    # Metadata
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: str | None = None
    field_sources: dict[str, list[str]] | None = None
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
    fiscal_quarter: int | None = Field(None, ge=1, le=4)
    period_end_date: date

    # Core
    cash_from_operating_activities: Decimal | None = None
    net_income: Decimal | None = None
    depreciation_amortization: Decimal | None = None
    capital_expenditures: Decimal | None = None
    cash_from_investing_activities: Decimal | None = None
    cash_from_financing_activities: Decimal | None = None
    dividends_paid: Decimal | None = None
    currency: str | None = "USD"

    # NEW — required by Supabase
    change_in_working_capital: Decimal | None = None        # NEW
    deferred_taxes: Decimal | None = None                   # NEW
    stock_based_compensation: Decimal | None = None         # NEW
    acquisitions: Decimal | None = None                     # NEW
    asset_sales: Decimal | None = None                      # NEW
    investment_purchases: Decimal | None = None             # NEW
    debt_issued: Decimal | None = None                      # NEW
    debt_repayment: Decimal | None = None                   # NEW
    share_repurchases: Decimal | None = None                # NEW
    share_issuance: Decimal | None = None                   # NEW
    last_validated_at: datetime | None = None               # NEW
    # Phase 5 — Tier 2 new columns
    net_change_in_cash: Decimal | None = None
    effect_of_fx_on_cash: Decimal | None = None
    beginning_cash: Decimal | None = None
    ending_cash: Decimal | None = None
    short_term_debt_net_change: Decimal | None = None
    asset_impairment_charge: Decimal | None = None
    free_cash_flow: Decimal | None = None
    # Metadata
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: str | None = None
    field_sources: dict[str, list[str]] | None = None
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
    fiscal_quarter: int | None = Field(None, ge=1, le=4)
    period_end_date: date
    announcement_date: date | None = None

    # Core EPS
    eps_reported_basic: Decimal | None = None
    eps_reported_diluted: Decimal | None = None
    eps_estimate: Decimal | None = None
    eps_surprise_amount: Decimal | None = None
    eps_surprise_percent: Decimal | None = None

    # Revenue
    revenue_reported: Decimal | None = None
    revenue_estimate: Decimal | None = None

    # NEW — required by Supabase
    revenue_surprise_amount: Decimal | None = None        # NEW
    revenue_surprise_percent: Decimal | None = None       # NEW
    shares_outstanding_basic: int | None = None           # NEW
    shares_outstanding_diluted: int | None = None         # NEW
    last_validated_at: datetime | None = None             # NEW

    currency: str | None = "USD"
    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: str | None = None
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
    payment_date: date | None = None
    dividend_amount: Decimal | None = None
    dividend_type: str = "regular"
    currency: str | None = "USD"

    # NEW — required by Supabase
    record_date: date | None = None            # NEW
    frequency: str | None = None               # NEW
    last_validated_at: datetime | None = None  # NEW

    data_source: str = "defeat_beta"
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DividendRows(BaseModel):
    rows: list[DividendRow] = Field(default_factory=list)
    def __len__(self): return len(self.rows)


class UpcomingDividendEvent(BaseModel):
    """Forward-looking ex-dividend date from a provider or prediction.
    
    Stored in upcoming_dividend_events table — separate from historical
    dividend_history to prevent metrics pollution.
    """
    company_id: int
    data_source: str
    ex_dividend_date: date
    trust_score: float = Field(default=0.0, ge=0.0, le=1.0)
    status: str = "predicted"  # 'predicted' | 'provider_reported'
    source_observed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None




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

    next_earnings_date: date | None = None

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
    exchange: str | None = None

    first_financial_data_loaded_at: datetime | None = None
    last_financial_refresh_at: datetime | None = None
    last_refreshed_fiscal_year: int | None = None
    last_refreshed_fiscal_quarter: int | None = None
    data_completeness_status: str = "INITIAL"
    next_earnings_date: date | None = None
    last_price_refresh_at: datetime | None = None



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
