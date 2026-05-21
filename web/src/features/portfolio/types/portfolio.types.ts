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
}

export interface PortfolioOverview {
    success: boolean;
    net_worth: number;
    total_cost_basis: number;
    total_gain_loss: number;
    total_gain_loss_pct: number;
    ytd_dividends: number;
    total_holdings_count: number;
    accounts_count: number;
    top_holdings: Holding[];
    account_breakdown: AccountBreakdown[];
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
    'TFSA': 'TFSA (Tax-Free Savings Account)',
    'RRSP': 'RRSP (Registered Retirement Savings Plan)',
    'Non-registered': 'Non-Registered',
    'FHSA': 'FHSA (First Home Savings Account)',
    '401k': '401(k)',
    'IRA': 'IRA (Individual Retirement Account)',
    'Roth IRA': 'Roth IRA',
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
}

export interface BenchmarkInfo {
    role: string;
    symbol: string;
    name: string;
    market: string;
    description?: string;
}

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

export type TimePeriod = '1D' | '1W' | '1M' | '3M' | '1Y' | 'YTD' | 'ALL';

export const PERIOD_OPTIONS: { label: string; value: TimePeriod }[] = [
    { label: '1D', value: '1D' },
    { label: '1W', value: '1W' },
    { label: '1M', value: '1M' },
    { label: '3M', value: '3M' },
    { label: '1Y', value: '1Y' },
    { label: 'YTD', value: 'YTD' },
    { label: 'ALL', value: 'ALL' },
];

export const ACCOUNT_TYPE_COLORS: Record<string, string> = {
    'TFSA': 'emerald',
    'RRSP': 'indigo',
    'Non-registered': 'amber',
    'FHSA': 'violet',
    '401k': 'blue',
    'IRA': 'rose',
    'Roth IRA': 'pink',
};