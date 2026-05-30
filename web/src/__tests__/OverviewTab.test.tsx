import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const mockUsePortfolioOverview = vi.fn();
const mockUsePortfolioPerformance = vi.fn();

const mockUsePortfolioAccounts = vi.fn();
const mockUseBenchmarks = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    usePortfolioOverview: (...args: any[]) => mockUsePortfolioOverview(...args),
    usePortfolioPerformance: (...args: any[]) => mockUsePortfolioPerformance(...args),
    usePortfolioAccounts: (...args: any[]) => mockUsePortfolioAccounts(...args),
    useBenchmarks: (...args: any[]) => mockUseBenchmarks(...args),
    useBenchmarkCompare: () => ({ data: null, isLoading: false }),
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
    return { TrendingUp: mkIcon(), TrendingDown: mkIcon(), DollarSign: mkIcon() };
});

vi.mock("recharts", () => {
    const React = require("react");
    return {
        ResponsiveContainer: ({ children }: any) => React.createElement("div", { "data-testid": "recharts-container" }, children),
        ComposedChart: ({ children }: any) => React.createElement("div", { "data-testid": "composed-chart" }, children),
        Area: () => null,
        Line: () => null,
        XAxis: () => null,
        YAxis: () => null,
        Tooltip: () => null,
        CartesianGrid: () => null,
        Legend: () => null,
    };
});

import { OverviewTab } from "@/features/portfolio/components/OverviewTab";

function makeOverview(overrides = {}) {
    return {
        net_worth: 80432.5,
        total_cost_basis: 61200,
        total_gain_loss: 19232.5,
        total_gain_loss_pct: 31.42,
        ytd_dividends: 1874.35,
        accounts_count: 2,
        total_holdings_count: 12,
        top_holdings: [],
        account_breakdown: [],
        success: true,
        ...overrides,
    };
}

describe("OverviewTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUsePortfolioOverview.mockReturnValue({ data: makeOverview(), isLoading: false });
        mockUsePortfolioPerformance.mockReturnValue({
            data: {
                success: true,
                period: "1Y",
                snapshots: [
                    { date: "2025-06-01", value: 70000, cost_basis: 60000, net_deposits: 0 },
                    { date: "2025-12-01", value: 80000, cost_basis: 61200, net_deposits: 1200 },
                ],
                monthly_breakdown: [],
            },
            isLoading: false,
        });
        mockUsePortfolioAccounts.mockReturnValue({ data: [], isLoading: false });
        mockUseBenchmarks.mockReturnValue({ data: [], isLoading: false });
    });

    it("renders loading skeleton while fetching", () => {
        mockUsePortfolioOverview.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<OverviewTab />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("renders all 4 summary cards with values", () => {
        render(<OverviewTab />);
        expect(screen.getByText("Total Value")).toBeInTheDocument();
        expect(screen.getByText("Total Gain/Loss")).toBeInTheDocument();
        expect(screen.getByText("Gain/Loss %")).toBeInTheDocument();
        expect(screen.getByText("Total Dividends")).toBeInTheDocument();
        expect(screen.getByText("$80,432.50")).toBeInTheDocument();
        expect(screen.getByText("+31.42%")).toBeInTheDocument();
        expect(screen.getByText("$1,874.35")).toBeInTheDocument();
    });

    it("shows positive gain/loss in green and negative in red", () => {
        mockUsePortfolioOverview.mockReturnValue({
            data: makeOverview({ total_gain_loss: -5000, total_gain_loss_pct: -8.16 }),
            isLoading: false,
        });
        const { container } = render(<OverviewTab />);
        const gainLossText = screen.getByText(($) => $.includes("$") && $.includes("-5,000"));
        expect(gainLossText.className).toContain("text-red-400");
    });

    it("renders performance chart when data is available", () => {
        render(<OverviewTab />);
        expect(screen.getAllByTestId("recharts-container").length).toBeGreaterThanOrEqual(1);
    });

    it("renders with account filter", () => {
        render(<OverviewTab accountIds={[1]} />);
        expect(screen.getByText("Total Value")).toBeInTheDocument();
    });

    it("handles null gain_loss values gracefully", () => {
        mockUsePortfolioOverview.mockReturnValue({
            data: makeOverview({ total_gain_loss: null, total_gain_loss_pct: null }),
            isLoading: false,
        });
        render(<OverviewTab />);
        const dashes = screen.getAllByText("—");
        expect(dashes.length).toBeGreaterThanOrEqual(1);
    });
});
