// web/src/features/super-investors/types/super-investors-page.types.ts
// Types for the standalone /super-investors page.
// Per-ticker types (SuperInvestorHolder etc.) remain in analysis.types.ts.

// ── Shared atoms ─────────────────────────────────────────────────────────────

export type ChangeType = "new" | "increased" | "decreased" | "held" | "sold";
export type ConvictionLevel = "none" | "low" | "moderate" | "high" | "very_high";
export type InvestorStyle =
    | "Long-Term Compounder"
    | "Value"
    | "Growth"
    | "Activist"
    | "Sector";

// ── Overview tab ─────────────────────────────────────────────────────────────

export interface OverviewMover {
    ticker: string;
    company_name: string;
    sector: string;
    investor_count: number;
    investor_tags: string[];
}

export interface OverviewData {
    latest_quarter: string;
    prev_quarter: string | null;
    investors_tracked: number;
    stocks_held: number;
    new_positions: number;
    full_exits: number;
    most_added: OverviewMover[];
    most_exited: OverviewMover[];
}

// ── Top Stocks tab ───────────────────────────────────────────────────────────

export interface TopStock {
    rank: number;
    ticker: string;
    company_name: string;
    sector: string;
    investor_count: number;
    investor_breadth_pct: number;
    total_position_value: number;
    avg_portfolio_weight: number;
    conviction_level: ConvictionLevel;
    investor_tags: string[];
}

export interface TopStocksData {
    quarter: string;
    total_stocks: number;
    stocks: TopStock[];
}

// ── Conviction Overlap tab ───────────────────────────────────────────────────

export interface OverlapInvestor {
    tag: string;
    investor_name: string;
    style: string;
    portfolio_weight: number;
    change_type: ChangeType;
}

export interface OverlapStock {
    ticker: string;
    company_name: string;
    sector: string;
    investor_count: number;
    investors: OverlapInvestor[];
    avg_portfolio_weight: number;
    conviction_level: ConvictionLevel;
}

export interface OverlapData {
    quarter: string;
    stocks: OverlapStock[];
}

// ── Activity Feed tab ────────────────────────────────────────────────────────

export interface ActivityItem {
    quarter_end_date: string;
    investor_tag: string;
    investor_name: string;
    style: string;
    ticker: string;
    company_name: string;
    sector: string;
    change_type: ChangeType;
    shares_held: number | null;
    shares_change: number | null;
    shares_change_pct: number | null;
    position_value: number | null;
    portfolio_weight: number | null;
}

export interface ActivityData {
    quarters_shown: string[];
    activity: ActivityItem[];
}

// ── Investors list tab ───────────────────────────────────────────────────────

export interface InvestorSummary {
    investor_id: number;
    investor_name: string;
    firm_name: string;
    tag: string;
    style: InvestorStyle;
    last_filed_period: string | null;
    portfolio_value: number;
    positions_count: number;
    top_holding_ticker: string;
    top_holding_weight: number;
}

export interface InvestorsListData {
    investors: InvestorSummary[];
}

// ── By Investor tab ──────────────────────────────────────────────────────────

export interface InvestorInfo {
    investor_name: string;
    firm_name: string;
    tag: string;
    style: InvestorStyle;
    last_filed_period: string | null;
}

export interface HoldingHistoryPoint {
    quarter: string;
    shares_held: number;
    portfolio_weight: number;
    change_type: ChangeType;
    shares_change: number | null;
    shares_change_pct: number | null;
}

export interface InvestorHolding {
    rank: number;
    ticker: string;
    company_name: string;
    sector: string;
    shares_held: number;
    position_value: number;
    portfolio_weight: number;
    change_type: ChangeType;
    shares_change: number | null;
    shares_change_pct: number | null;
    history: HoldingHistoryPoint[];
}

export interface SectorWeight {
    sector: string;
    value: number;
    weight: number;
}

export interface InvestorPortfolioData {
    investor: InvestorInfo;
    latest_quarter: string;
    portfolio_value: number;
    positions_count: number;
    sector_breakdown: SectorWeight[];
    holdings: InvestorHolding[];
}

// ── Sectors tab ──────────────────────────────────────────────────────────────

export interface SectorTopStock {
    ticker: string;
    total_value: number;
}

export interface SectorRow {
    sector: string;
    total_value: number;
    avg_weight: number;
    stock_count: number;
    investor_count: number;
    top_stocks: SectorTopStock[];
}

export interface SectorsData {
    quarter: string;
    sectors: SectorRow[];
}