// web/src/features/portfolio/types/portfolio.types.ts

export interface Brokerage {
  brokerage_id: number;
  brokerage_code: string;
  brokerage_name: string;
  country_code: string;
  is_active: boolean;
}

export interface PortfolioAccount {
  account_id: number;
  account_name: string;
  account_type: string;
  account_external_id: string;
  brokerage_name: string;
  brokerage_code: string;
  currency: string;
  is_active: boolean;
  created_at: string;
  last_import_at: string | null;
  holdings_count: number;
  total_value: number;
  total_cost: number;
}

export interface Holding {
  holding_id: number;
  account_id?: number;
  symbol: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  exchange: string | null;
  market_group: string | null;
  quantity: number;
  average_cost: number;
  total_cost: number;
  current_price: number | null;
  current_value: number | null;
  unrealized_gain_loss: number | null;
  unrealized_gain_loss_pct: number | null;
  realized_gain_loss: number;
  first_purchase_date: string | null;
  last_transaction_date: string | null;
  currency?: string;
  account_name?: string;
  account_type?: string;
}

export interface AccountBreakdown {
  account_id: number;
  account_name: string;
  account_type: string;
  brokerage_name: string | null;
  holdings_count: number;
  total_value: number;
  total_cost: number;
  gain_loss: number;
  gain_loss_pct: number;
  cash_balance?: number;
  value_currency?: string;
}

export interface PortfolioOverview {
  success: boolean;
  net_worth: number;
  total_value: number;
  cash_balance: number;
  total_dividends: number;
  total_cost_basis: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  ytd_dividends: number;
  total_holdings_count: number;
  accounts_count: number;
  top_holdings: Holding[];
  account_breakdown: AccountBreakdown[];
  value_currency?: string;
  error?: string;
}

export interface Transaction {
  transaction_id: number;
  transaction_date: string;
  settlement_date: string | null;
  activity_type: string;
  activity_sub_type: string | null;
  symbol: string | null;
  security_name: string | null;
  quantity: number | null;
  unit_price: number | null;
  commission: number;
  net_cash_amount: number;
  currency: string;
}

export interface MonthlyDividendSummary {
  fiscal_year: number;
  fiscal_month: number;
  payment_count: number;
  total_amount: number;
  paying_companies: number;
}

export interface ImportResult {
  success: boolean;
  import_batch_id?: string;
  status?: string;
  total_rows?: number;
  accounts_created?: number;
  accounts_updated?: number;
  transactions_imported?: number;
  holdings_updated?: number;
  dividends_extracted?: number;
  symbols_missing?: string[];
  account_types?: Record<string, number>;
  warnings?: string[];
  error?: string;
  duplicate_import?: boolean;
  previous_import_date?: string;
  previous_import_id?: number;
  warning?: string;
}

export interface ImportStatusResponse {
  success: boolean;
  import_batch_id: string;
  status: string;
  total_rows: number;
  rows_parsed: number;
  rows_inserted: number;
  error?: string | null;
  result?: Record<string, unknown> | null;
}

export interface AddManualTransactionRequest {
  account_id: number;
  transaction_date: string;
  activity_type: string;
  symbol?: string | null;
  quantity?: number | null;
  unit_price?: number | null;
  commission?: number;
  notes?: string | null;
}

export interface AddManualTransactionResponse {
  success: boolean;
  transaction_id?: number;
  transaction?: Record<string, unknown>;
  error?: string;
}

// Request types
export interface ImportTransactionsRequest {
  brokerage_code: string;
  csv_content: string; // Base64-encoded CSV
  account_filter?: string[];
}

export const ACCOUNT_TYPE_LABELS: Record<string, string> = {
  TFSA: "TFSA (Tax-Free Savings Account)",
  RRSP: "RRSP (Registered Retirement Savings Plan)",
  "Non-registered": "Non-Registered",
  FHSA: "FHSA (First Home Savings Account)",
  "401k": "401(k)",
  IRA: "IRA (Individual Retirement Account)",
  "Roth IRA": "Roth IRA",
};

// Performance & Benchmark types
export interface PerformanceSnapshot {
  date: string;
  value: number;
  cost_basis: number;
  net_deposits: number;
}

export interface PerformanceResponse {
  success: boolean;
  period: string;
  snapshots: PerformanceSnapshot[];
  total_return: number;
  total_return_pct: number;
  best_day: { date: string; return_pct: number } | null;
  worst_day: { date: string; return_pct: number } | null;
  error?: string;
  data_source?: string;
  data_quality_flag?: string;
  spike_detected?: boolean;
  locf_count?: number;
}

export type { BenchmarkInfo } from "@/lib/types";

export interface BenchmarkSeries {
  symbol: string;
  name: string;
  data: { date: string; value: number }[];
}

export interface BenchmarkCompareResponse {
  success: boolean;
  period: string;
  portfolio: { date: string; value: number }[];
  benchmarks: BenchmarkSeries[];
  error?: string;
}

export type TimePeriod = "1D" | "1W" | "1M" | "3M" | "1Y" | "YTD" | "ALL";

export const PERIOD_OPTIONS: { label: string; value: TimePeriod }[] = [
  { label: "1W", value: "1W" },
  { label: "1M", value: "1M" },
  { label: "1Y", value: "1Y" },
  { label: "YTD", value: "YTD" },
  { label: "All Time", value: "ALL" },
];

export const ACCOUNT_TYPE_COLORS: Record<string, string> = {
  TFSA: "emerald",
  RRSP: "indigo",
  "Non-registered": "amber",
  FHSA: "violet",
  "401k": "blue",
  IRA: "rose",
  "Roth IRA": "pink",
};

// ============================================================================
// DIVIDEND DASHBOARD TYPES
// ============================================================================

export interface MetricWithCoverage {
  value: number | null;
  coverage_pct: number;
}

export interface UpcomingExDate {
  symbol: string;
  company_name: string;
  ex_dividend_date: string;
  amount_per_share: number;
  estimated_income: number;
  dividend_type: string;
  confidence: "high" | "medium" | "low";
  trust_score?: number;
  trust_label?: "Likely" | "Estimate" | "Predicted";
  data_source?: string;
  event_type?: string;
}

export interface PortfolioDividendSummary {
  trailing_12m_income: number;
  forward_annual_estimate: number;
  ytd_dividends: number;
  forward_yield_on_cost: number | null;
  avg_monthly_trailing: number;
  avg_monthly_forward: number;
  portfolio_growth_5yr: MetricWithCoverage;
  portfolio_safety: MetricWithCoverage;
  goal_progress: { monthly_income: number; monthly_goal: number | null; pct: number } | null;
  currency: string | null;
  currencies_mixed: boolean;
  last_updated: string;
}

export interface PortfolioDividendHolding {
  account_id: number;
  symbol: string;
  company_name: string;
  sector: string | null;
  quantity: number;
  market_value: number;
  total_cost: number;
  forward_income: number;
  trailing_12m_income: number;
  current_yield: number | null;
  forward_yield_on_cost: number | null;
  payout_ratio: number | null;
  increase_streak: number | null;
  safety_score: number | null;
  next_event: UpcomingExDate | null;
}

export interface PortfolioDividendHoldingDetail {
  symbol: string;
  company_name: string;
  sector: string | null;
  income: {
    trailing_12m: number;
    forward: number;
    ytd: number;
    yield_on_cost: number | null;
    market_value: number;
    cost_basis: number;
  };
  quality_metrics: {
    safety_score: number | null;
    payout_ratio: number | null;
    growth_5yr: number | null;
    increase_streak: number | null;
    current_yield: number | null;
  } | null;
  dividend_history: Array<{
    date: string;
    amount: number;
  }>;
  annual_dividends_per_share: Array<{
    year: number;
    amount: number;
  }>;
  cash_received_by_year: Array<{
    year: number;
    amount: number;
  }>;
  recent_payments: Array<{
    payment_date: string;
    amount: number;
    shares_held: number | null;
  }>;
}

// ============================================================================
// AGGREGATED HOLDING TYPES
// ============================================================================

export interface AccountHoldingBreakdown {
  account_id: number;
  account_name?: string | null;
  account_type?: string | null;
  quantity: number;
  total_cost: number;
  current_value: number;
}

export interface AggregatedHolding {
  company_id: number;
  symbol: string;
  company_name: string;
  sector: string | null;
  industry: string | null;
  exchange: string | null;
  market_group: string | null;
  security_type: string;
  currency: string | null;
  total_quantity: number;
  average_cost: number;
  total_cost: number;
  current_price: number | null;
  current_value: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  accounts_count: number;
  account_breakdown: AccountHoldingBreakdown[];
}

// ============================================================================
// ALLOCATION TYPES
// ============================================================================

export interface AllocationSegment {
  segment: string;
  value: number;
  weight: number;
  count: number;
  gain_loss: number;
}

export interface SectorAllocationSegment {
  segment: string;
  value: number;
  weight: number;
  count: number;
  gain_loss: number;
}

export interface TypeAllocationSegment {
  type: string;
  type_label: string;
  value: number;
  weight: number;
  count: number;
  gain_loss: number;
  sectors: SectorAllocationSegment[];
}

export interface PortfolioAllocationResponse {
  success: boolean;
  group_by: string;
  segments: AllocationSegment[];
  types: TypeAllocationSegment[];
  total_value: number;
  error?: string;
}

// ============================================================================
// EXTENDED DIVIDEND TYPES
// ============================================================================

export interface DividendDetail {
  dividend_id: number;
  symbol: string;
  company_name?: string;
  payment_date: string;
  amount: number;
  shares_held?: number;
  amount_per_share?: number;
  account_name?: string;
  account_type?: string;
}

export interface DividendHistoryResponse {
  success: boolean;
  account_id?: number;
  dividends: DividendDetail[];
  total_count: number;
  current_year_total: number;
  error?: string;
}

// ============================================================================
// TRANSACTION FILTER TYPES
// ============================================================================

export interface TransactionFilter {
  from_date?: string;
  to_date?: string;
  activity_type?: string;
  search?: string;
}

// ============================================================================
// RISK METRICS TYPES
// ============================================================================

export interface RiskMetricsResponse {
  success: boolean;
  period: string;
  variance: number;
  std_deviation: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  max_drawdown_pct: number;
  value_at_risk_95: number;
  value_at_risk_99: number;
  conditional_var_95: number;
  downside_deviation: number;
  total_return_pct: number;
  tracking_error: number | null;
  information_ratio: number | null;
  beta: number | null;
  alpha: number | null;
  error?: string | null;
  error_code?: string | null;
}

export interface DrawdownPoint {
  date: string;
  value: number;
  drawdown_pct: number;
}

export interface DrawdownResponse {
  success: boolean;
  period: string;
  drawdowns: DrawdownPoint[];
  max_drawdown: number;
  max_drawdown_pct: number;
  max_drawdown_start: string | null;
  max_drawdown_end: string | null;
  max_drawdown_recovery: string | null;
  avg_drawdown: number;
  error?: string | null;
  error_code?: string | null;
}

export interface CovarianceResponse {
  success: boolean;
  period: string;
  holdings: string[];
  covariance_matrix: number[][];
  correlation_matrix: number[][];
  error?: string | null;
  error_code?: string | null;
}

export interface EfficientFrontierPoint {
  volatility: number;
  expected_return: number;
  weights: Record<string, number>;
  sharpe_ratio?: number | null;
}

export interface EfficientFrontierResponse {
  success: boolean;
  frontier: EfficientFrontierPoint[];
  max_sharpe: EfficientFrontierPoint | null;
  min_variance: EfficientFrontierPoint | null;
  cml?: Record<string, number>[] | null;
  error?: string | null;
  error_code?: string | null;
}

export interface RollingSharpeResponse {
  success: boolean;
  period: string;
  window: number;
  series: Record<string, unknown>[];
  error?: string | null;
  error_code?: string | null;
}

export interface RiskContributionItem {
  symbol: string;
  weight: number;
  marginal_risk: number;
  component_risk: number;
  risk_pct: number;
}

export interface RiskContributionResponse {
  success: boolean;
  contributions: RiskContributionItem[];
  total_risk: number;
  error?: string | null;
  error_code?: string | null;
}

export interface FactorExposureResponse {
  success: boolean;
  exposures: Record<string, number>;
  r_squared: number;
  error?: string | null;
  error_code?: string | null;
}

// ============================================================================
// HOLDING PERFORMANCE TYPES (single-stock)
// ============================================================================

export interface HoldingExistsResponse {
  symbol: string;
  held: boolean;
}

export interface HoldingPerformanceSnapshot {
  date: string;
  position_value: number;
  cost_basis: number;
  cumulative_invested: number;
  shares_held?: number;
  avg_cost_per_share?: number;
}

export interface MonthlyReturnSummary {
  month: string;
  return_pct: number;
  label: string;
}

export interface DrawdownInfo {
  dd_pct: number;
  start_date?: string;
  end_date?: string;
  duration_days?: number;
  is_ongoing: boolean;
}

export interface DaysAboveCostBasis {
  days_above: number;
  total_days: number;
  pct_above: number;
}

export interface HoldingPerformanceResponse {
  success: boolean;
  symbol: string;
  period: string;
  snapshots: HoldingPerformanceSnapshot[];
  total_return: number;
  total_return_pct: number;
  total_dividends: number;
  total_dividends_pct: number;
  combined_return: number;
  best_month?: MonthlyReturnSummary | null;
  worst_month?: MonthlyReturnSummary | null;
  max_drawdown?: DrawdownInfo | null;
  longest_drawdown?: DrawdownInfo | null;
  volatility_30d: number;
  days_above_cost_basis?: DaysAboveCostBasis | null;
  error?: string;
}

export interface HoldingDividendSummary {
  fiscal_year: number;
  fiscal_quarter: number;
  label: string;
  total_amount: number;
  payments_count: number;
  amount_per_share: number;
}

// ============================================================================
// HOLDING TRANSACTION + ACCOUNT BREAKDOWN TYPES
// ============================================================================

export interface HoldingTransaction {
  transaction_id: number;
  transaction_date: string;
  activity_sub_type: string;
  quantity: number;
  unit_price: number;
  commission: number;
  net_cash_amount: number;
  account_name: string;
  account_type: string;
}

export interface HoldingAccountBreakdown {
  account_id: number;
  account_name: string;
  account_type: string;
  shares_held: number;
  total_cost: number;
  current_value: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  dividends_received: number;
}

// ============================================================================
// PORTFOLIO DASHBOARD TYPES (bundle endpoint)
// ============================================================================

export interface DashboardAccount {
  account_id: number;
  account_name: string;
  account_type: string;
  brokerage_name: string | null;
  currency: string;
  holdings_count: number;
  total_value: number;
  total_cost: number;
  gain_loss: number;
  gain_loss_pct: number;
  value_currency?: string;
}

export interface DashboardOverview {
  total_value: number;
  total_cost_basis: number;
  total_gain_loss: number;
  total_gain_loss_pct: number;
  ytd_dividends: number;
  holdings_count: number;
  accounts_count: number;
  value_currency?: string;
}

export interface DashboardHolding {
  company_id?: number;
  symbol: string;
  company_name: string;
  quantity: number;
  current_price: number;
  current_value: number;
  total_cost: number;
  unrealized_gain_loss: number;
  unrealized_gain_loss_pct: number;
  value_currency?: string;
}

export interface PortfolioDashboardResponse {
  accounts: DashboardAccount[];
  overview: DashboardOverview;
  holdings: DashboardHolding[];
}

// ============================================================================
// TAB NAVIGATION TYPES
// ============================================================================

export const TAB_DEFINITIONS = [
  { id: "overview", label: "Overview", icon: "LayoutDashboard" },
  { id: "dividends", label: "Dividends", icon: "DollarSign" },
  { id: "transactions", label: "Transaction", icon: "Receipt" },
  { id: "risk", label: "Risk", icon: "Shield" },
] as const;

export type TabId = (typeof TAB_DEFINITIONS)[number]["id"];
