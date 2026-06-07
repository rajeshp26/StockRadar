import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseHoldingPerformance = vi.fn();
const mockUseHoldingDividends = vi.fn();
const mockUseBenchmarks = vi.fn();
const mockUseHoldingBenchmarkCompare = vi.fn();
const mockUseHoldingTransactions = vi.fn();
const mockUseHoldingAccounts = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    useHoldingPerformance: (...args: any[]) => mockUseHoldingPerformance(...args),
    useHoldingDividends: (...args: any[]) => mockUseHoldingDividends(...args),
    useBenchmarks: (...args: any[]) => mockUseBenchmarks(...args),
    useHoldingBenchmarkCompare: (...args: any[]) => mockUseHoldingBenchmarkCompare(...args),
    useHoldingTransactions: (...args: any[]) => mockUseHoldingTransactions(...args),
    useHoldingAccounts: (...args: any[]) => mockUseHoldingAccounts(...args),
    usePortfolioAccounts: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

const mockUseLivePrice = vi.fn();

vi.mock("@/features/analysis/hooks/useLivePrice", () => ({
    useLivePrice: (...args: any[]) => mockUseLivePrice(...args),
}));

vi.mock("lucide-react", () => {
    const React = require("react");
    const mkIcon = () => () => React.createElement("svg", { "data-testid": "icon" });
    return { TrendingUp: mkIcon(), TrendingDown: mkIcon(), DollarSign: mkIcon(), Wallet: mkIcon(), ChevronDown: mkIcon(), Check: mkIcon(), PiggyBank: mkIcon(), Receipt: mkIcon(), Calendar: mkIcon(), Activity: mkIcon(), ArrowUpRight: mkIcon(), CalendarDays: mkIcon(), BarChart3: mkIcon(), DollarSign: mkIcon(), PiggyBank: mkIcon() };
});

vi.mock("recharts", () => {
    const React = require("react");
    return {
        ResponsiveContainer: ({ children }: any) => React.createElement("div", { "data-testid": "recharts-container" }, children),
        ComposedChart: ({ children }: any) => React.createElement("div", { "data-testid": "composed-chart" }, children),
        BarChart: ({ children }: any) => React.createElement("div", { "data-testid": "bar-chart" }, children),
        Bar: () => null,
        Area: () => null,
        Line: () => null,
        XAxis: () => null,
        YAxis: () => null,
        Tooltip: () => null,
        CartesianGrid: () => null,
        Legend: () => null,
    };
});

import { StockPerformancePanel } from "@/features/analysis/components/stock-performance-panel";

function makePerformanceData(overrides = {}) {
    return {
        success: true,
        symbol: "AAPL",
        period: "1Y",
        snapshots: [
            { date: "2024-01-15", position_value: 1800, cost_basis: 1800, cumulative_invested: 1800 },
            { date: "2024-07-15", position_value: 2000, cost_basis: 1800, cumulative_invested: 1800 },
            { date: "2024-12-31", position_value: 2200, cost_basis: 1800, cumulative_invested: 1800, avg_cost_per_share: 180 },
        ],
        total_return: 400,
        total_return_pct: 22.22,
        total_dividends: 87.00,
        total_dividends_pct: 4.83,
        combined_return: 487.00,
        best_month: { month: "2024-07", return_pct: 11.11, label: "Jul 2024" },
        worst_month: { month: "2024-01", return_pct: 5.56, label: "Jan 2024" },
        max_drawdown: { dd_pct: -10.5, start_date: "2024-03-01", end_date: "2024-06-15", duration_days: 106, is_ongoing: false },
        longest_drawdown: { dd_pct: -8.2, start_date: "2024-02-01", end_date: "2024-05-01", duration_days: 90, is_ongoing: false },
        volatility_30d: 25.5,
        days_above_cost_basis: { days_above: 200, total_days: 300, pct_above: 66.7 },
        ...overrides,
    };
}

describe("StockPerformancePanel", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseHoldingPerformance.mockReturnValue({ data: makePerformanceData(), isLoading: false });
        mockUseHoldingDividends.mockReturnValue({ data: [], isLoading: false });
        mockUseBenchmarks.mockReturnValue({ data: [], isLoading: false });
        mockUseHoldingBenchmarkCompare.mockReturnValue({ data: null, isLoading: false });
        mockUseHoldingTransactions.mockReturnValue({ data: [], isLoading: false });
        mockUseHoldingAccounts.mockReturnValue({ data: [], isLoading: false });
        mockUseLivePrice.mockReturnValue({ price: 220, change: 0, changePercent: 0, loading: false, error: null, lastUpdated: null, currency: null });
    });

    it("renders PerformanceSummaryCard with Gain/Loss headline", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Gain / Loss")).toBeInTheDocument();
        expect(screen.getByText("Current Value")).toBeInTheDocument();
    });

    it("renders combined return with $ and %", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/\$487\.00/)).toBeInTheDocument();
        const pctElements = screen.getAllByText(/22\.22/);
        expect(pctElements.length).toBeGreaterThanOrEqual(1);
    });

    it("renders attribution row: Price Change + Dividends", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Price Change")).toBeInTheDocument();
        expect(screen.getByText("Dividends")).toBeInTheDocument();
    });

    it("renders avg cost context line with live price", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/Avg Cost/)).toBeInTheDocument();
        expect(screen.getByText(/Last Price/)).toBeInTheDocument();
    });

    it("renders risk quadrants", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Best Month")).toBeInTheDocument();
        expect(screen.getByText("Worst Month")).toBeInTheDocument();
        expect(screen.getByText("Max Drawdown")).toBeInTheDocument();
        expect(screen.getByText(/Volatility/)).toBeInTheDocument();
    });

    it("renders extended metrics", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Days Above Cost Basis")).toBeInTheDocument();
        expect(screen.getByText("Longest Drawdown")).toBeInTheDocument();
    });

    it("shows best and worst month labels", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Jul 2024")).toBeInTheDocument();
        expect(screen.getByText("Jan 2024")).toBeInTheDocument();
    });

    it("shows drawdown duration in days", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("106d")).toBeInTheDocument();
    });

    it("shows loading skeleton while fetching", () => {
        mockUseHoldingPerformance.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<StockPerformancePanel symbol="AAPL" />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("shows error state on fetch failure", () => {
        mockUseHoldingPerformance.mockReturnValue({ data: null, isError: true, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Unable to load performance data")).toBeInTheDocument();
    });

    it("renders ComposedChart when snapshots exist", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getAllByTestId("recharts-container").length).toBeGreaterThanOrEqual(1);
    });

    it("renders BarChart when dividends exist", () => {
        mockUseHoldingDividends.mockReturnValue({
            data: [
                { fiscal_year: 2024, fiscal_quarter: 1, label: "Q1 2024", total_amount: 22.50, payments_count: 1, amount_per_share: 2.25 },
            ],
            isLoading: false,
        });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getAllByTestId("recharts-container").length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no data", () => {
        mockUseHoldingPerformance.mockReturnValue({ data: null, isLoading: false, isError: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("No performance data yet")).toBeInTheDocument();
    });

    // ═════════════════════════════════════════════════════════════════════
    // REGRESSION TESTS — Benchmark Compare (P-03)
    // ═════════════════════════════════════════════════════════════════════
    // P-03 replaces portfolio-level useBenchmarkCompare with holding-level
    // useHoldingBenchmarkCompare for single-stock benchmark comparison.
    // ═════════════════════════════════════════════════════════════════════

    it("P-03: calls useHoldingBenchmarkCompare when benchmarks are selected", () => {
        mockUseBenchmarks.mockReturnValue({
            data: [{ symbol: "SPY", name: "S&P 500", role: "benchmark", market: "US" }],
            isLoading: false,
        });
        mockUseHoldingBenchmarkCompare.mockReturnValue({
            data: {
                success: true,
                period: "1Y",
                portfolio: [],
                benchmarks: [{
                    symbol: "SPY",
                    name: "S&P 500",
                    data: [
                        { date: "2024-01-15", value: 100 },
                        { date: "2024-12-31", value: 120 },
                    ],
                }],
            },
            isLoading: false,
        });

        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("+ Compare")).toBeInTheDocument();
    });

    it("P-03: performance summary card renders with benchmarks selected", () => {
        mockUseBenchmarks.mockReturnValue({
            data: [
                { symbol: "SPY", name: "S&P 500", role: "benchmark", market: "US" },
                { symbol: "QQQ", name: "Nasdaq", role: "benchmark", market: "US" },
            ],
            isLoading: false,
        });

        render(<StockPerformancePanel symbol="AAPL" />);

        expect(screen.getByText("Gain / Loss")).toBeInTheDocument();
        expect(screen.getByText("Current Value")).toBeInTheDocument();
    });

    // ═════════════════════════════════════════════════════════════════════
    // P-04: Transaction History Table
    // ═════════════════════════════════════════════════════════════════════

    it("P-04: renders transaction history table when transactions exist", () => {
        mockUseHoldingTransactions.mockReturnValue({
            data: [
                { transaction_id: 1, transaction_date: "2024-01-15", activity_sub_type: "BUY", quantity: 10, unit_price: 150, commission: 0, net_cash_amount: -1500, account_name: "Main TFSA", account_type: "TFSA" },
                { transaction_id: 2, transaction_date: "2024-06-01", activity_sub_type: "BUY", quantity: 5, unit_price: 180, commission: 0, net_cash_amount: -900, account_name: "RRSP", account_type: "RRSP" },
            ],
            isLoading: false,
        });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Transaction History")).toBeInTheDocument();
        expect(screen.getByText("Main TFSA")).toBeInTheDocument();
        expect(screen.getByText("RRSP")).toBeInTheDocument();
    });

    it("P-04: shows empty state when no transactions", () => {
        mockUseHoldingTransactions.mockReturnValue({ data: [], isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("No transaction history available")).toBeInTheDocument();
    });

    // ═════════════════════════════════════════════════════════════════════
    // P-05: Account Breakdown
    // ═════════════════════════════════════════════════════════════════════

    it("P-05: renders account breakdown table when accounts exist", () => {
        mockUseHoldingAccounts.mockReturnValue({
            data: [
                { account_id: 1, account_name: "Main TFSA", account_type: "TFSA", shares_held: 10, total_cost: 1500, current_value: 1800, unrealized_gain_loss: 300, unrealized_gain_loss_pct: 20, dividends_received: 45 },
                { account_id: 2, account_name: "RRSP Account", account_type: "RRSP", shares_held: 5, total_cost: 900, current_value: 900, unrealized_gain_loss: 0, unrealized_gain_loss_pct: 0, dividends_received: 20 },
            ],
            isLoading: false,
        });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Holdings by Account")).toBeInTheDocument();
        expect(screen.getByText("Main TFSA")).toBeInTheDocument();
        expect(screen.getByText("RRSP Account")).toBeInTheDocument();
    });

    it("P-05: shows empty state when no account breakdown", () => {
        mockUseHoldingAccounts.mockReturnValue({ data: [], isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("No account breakdown available")).toBeInTheDocument();
    });

    // ═════════════════════════════════════════════════════════════════════
    // P-01: Total Invested Summary Card
    // ═════════════════════════════════════════════════════════════════════

    it("P-01: shows accurate combined_return in headline", () => {
        const perfData = makePerformanceData({ combined_return: 1234.56, total_return_pct: 15.5 });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/\$1,234\.56/)).toBeInTheDocument();
        const pctElements = screen.getAllByText(/15\.50/);
        expect(pctElements.length).toBeGreaterThanOrEqual(1);
    });

    // ═════════════════════════════════════════════════════════════════════
    // P-06: Pre-Purchase Period Indicator
    // ═════════════════════════════════════════════════════════════════════

    // ═════════════════════════════════════════════════════════════════════
    // Performance Summary Card — Edge Cases
    // ═════════════════════════════════════════════════════════════════════

    it("shows — for best/worst month when showMonthlyMetrics false (ALL period)", () => {
        const perfData = makePerformanceData({ period: "ALL", best_month: null, worst_month: null });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        const dashes = screen.getAllByText("—");
        expect(dashes.length).toBeGreaterThanOrEqual(2);
    });

    it("shows — for best/worst month when showMonthlyMetrics false (5Y period)", () => {
        const perfData = makePerformanceData({ period: "5Y", best_month: null, worst_month: null });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        const dashes = screen.getAllByText("—");
        expect(dashes.length).toBeGreaterThanOrEqual(2);
    });

    it("shows negative combined return in red", () => {
        const perfData = makePerformanceData({ combined_return: -250, total_return: -300, total_return_pct: -15 });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/\$250\.00/)).toBeInTheDocument();
    });

    it("hides avg cost line when no snapshot or live price missing", () => {
        mockUseLivePrice.mockReturnValue({ price: null, change: null, changePercent: null, loading: false, error: null, lastUpdated: null, currency: null });
        const perfData = makePerformanceData({
            snapshots: [
                { date: "2024-01-15", position_value: 1800, cost_basis: 1800, cumulative_invested: 1800 },
                { date: "2024-12-31", position_value: 2200, cost_basis: 1800, cumulative_invested: 1800 },
            ],
        });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.queryByText(/Avg Cost/)).not.toBeInTheDocument();
        expect(screen.queryByText(/Last Price/)).not.toBeInTheDocument();
    });

    it("shows ongoing indicator for longest drawdown", () => {
        const perfData = makePerformanceData({
            longest_drawdown: { dd_pct: -5.0, start_date: "2024-01-01", duration_days: 30, is_ongoing: true },
        });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/Ongoing/)).toBeInTheDocument();
    });

    it("renders volatility as percentage when positive", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("25.50%")).toBeInTheDocument();
    });

    it("shows — for volatility when zero", () => {
        const perfData = makePerformanceData({ volatility_30d: 0 });
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("—")).toBeInTheDocument();
    });

    it("shows days above cost basis stats", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/200 \/ 300 days/)).toBeInTheDocument();
        expect(screen.getByText(/66.7%/)).toBeInTheDocument();
    });

    // ═════════════════════════════════════════════════════════════════════
    // P-06: Pre-Purchase Period Indicator
    // ═════════════════════════════════════════════════════════════════════

    it("P-06: shows pre-purchase indicator when chart data precedes first purchase", () => {
        const perfData = makePerformanceData();
        perfData.snapshots = [
            { date: "2023-01-01", position_value: 0, cost_basis: 0, cumulative_invested: 0 },
            { date: "2024-01-15", position_value: 1800, cost_basis: 1800, cumulative_invested: 1800 },
        ];
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText(/No position held before/)).toBeInTheDocument();
    });
});
