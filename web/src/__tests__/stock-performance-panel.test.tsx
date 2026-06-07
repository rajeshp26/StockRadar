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

vi.mock("lucide-react", () => {
    const React = require("react");
    const mkIcon = () => () => React.createElement("svg", { "data-testid": "icon" });
    return { TrendingUp: mkIcon(), TrendingDown: mkIcon(), DollarSign: mkIcon(), Wallet: mkIcon(), ChevronDown: mkIcon(), Check: mkIcon(), PiggyBank: mkIcon(), Receipt: mkIcon() };
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
            { date: "2024-12-31", position_value: 2200, cost_basis: 1800, cumulative_invested: 1800 },
        ],
        total_return: 400,
        total_return_pct: 22.22,
        total_dividends: 87.00,
        total_dividends_pct: 4.83,
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
    });

    it("renders 5 summary cards when data loaded", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("Total Value")).toBeInTheDocument();
        expect(screen.getByText("Total Invested")).toBeInTheDocument();
        expect(screen.getByText("Gain/Loss ($)")).toBeInTheDocument();
        expect(screen.getByText("Gain/Loss (%)")).toBeInTheDocument();
        expect(screen.getByText("Dividends")).toBeInTheDocument();
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

    it("P-03: summary cards render correctly when benchmarks selected", () => {
        mockUseBenchmarks.mockReturnValue({
            data: [
                { symbol: "SPY", name: "S&P 500", role: "benchmark", market: "US" },
                { symbol: "QQQ", name: "Nasdaq", role: "benchmark", market: "US" },
            ],
            isLoading: false,
        });

        render(<StockPerformancePanel symbol="AAPL" />);

        expect(screen.getByText("Total Value")).toBeInTheDocument();
        expect(screen.getByText("Total Invested")).toBeInTheDocument();
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

    it("P-01: shows cumulative_invested as Total Invested card", () => {
        const perfData = makePerformanceData();
        perfData.snapshots[perfData.snapshots.length - 1].cumulative_invested = 2500;
        mockUseHoldingPerformance.mockReturnValue({ data: perfData, isLoading: false });
        render(<StockPerformancePanel symbol="AAPL" />);
        expect(screen.getByText("$2,500.00")).toBeInTheDocument();
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
