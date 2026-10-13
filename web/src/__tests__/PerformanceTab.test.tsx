import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const mockUsePortfolioPerformance = vi.fn();
const mockUseBenchmarkCompare = vi.fn();
const mockUsePortfolioAccounts = vi.fn();
const mockUseBenchmarks = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    usePortfolioPerformance: (...args: any[]) => mockUsePortfolioPerformance(...args),
    useBenchmarkCompare: (...args: any[]) => mockUseBenchmarkCompare(...args),
    usePortfolioAccounts: (...args: any[]) => mockUsePortfolioAccounts(...args),
    useBenchmarks: (...args: any[]) => mockUseBenchmarks(...args),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

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

vi.mock("lucide-react", () => {
    const React = require("react");
    const mkIcon = () => () => React.createElement("svg", { "data-testid": "icon" });
    return { TrendingUp: mkIcon(), ChevronDown: mkIcon(), Check: mkIcon(), BarChart3: mkIcon() };
});

import { PerformanceTab } from "@/features/portfolio/components/PerformanceTab";

function makePerformanceSnapshot() {
    return {
        success: true,
        period: "1Y",
        snapshots: [
            { date: "2025-06-01", value: 70000, cost_basis: 60000, net_deposits: 0 },
            { date: "2025-12-01", value: 80000, cost_basis: 61200, net_deposits: 1200 },
        ],
        total_return: 20000,
        total_return_pct: 14.29,
        best_day: { date: "2025-10-15", return_pct: 2.34 },
        worst_day: { date: "2025-09-20", return_pct: -1.87 },
    };
}

function makeBenchmarkCompareResponse() {
    return {
        success: true,
        period: "1Y",
        portfolio: [{ date: "2025-06-01", value: 100 }, { date: "2025-12-01", value: 115 }],
        benchmarks: [
            { symbol: "^GSPC", name: "S&P 500", data: [{ date: "2025-06-01", value: 100 }, { date: "2025-12-01", value: 110 }] },
        ],
    };
}

describe("PerformanceTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUsePortfolioPerformance.mockReturnValue({ data: makePerformanceSnapshot(), isLoading: false });
        mockUseBenchmarkCompare.mockReturnValue({ data: makeBenchmarkCompareResponse(), isLoading: false });
        mockUsePortfolioAccounts.mockReturnValue({ data: [], isLoading: false });
        mockUseBenchmarks.mockReturnValue({
            data: [{ symbol: "SPY", name: "S&P 500 ETF", market: "US" }],
            isLoading: false,
        });
    });

    it("renders portfolio performance chart", () => {
        render(<PerformanceTab />);
        expect(screen.getByText("Portfolio Performance")).toBeInTheDocument();
        expect(screen.getAllByTestId("recharts-container").length).toBeGreaterThanOrEqual(1);
    });

    it("renders period selector buttons from child chart component", () => {
        render(<PerformanceTab />);
        const periods = ["1W", "1M", "1Y", "YTD", "All Time"];
        periods.forEach((p) => {
            expect(screen.getByText(p)).toBeInTheDocument();
        });
    });

    it("handles performance loading state", () => {
        mockUsePortfolioPerformance.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<PerformanceTab />);
        const loadingDivs = container.querySelectorAll(".animate-pulse");
        expect(loadingDivs.length).toBeGreaterThanOrEqual(1);
    });

    it("handles performance error state", () => {
        mockUsePortfolioPerformance.mockReturnValue({ data: null, isLoading: false, isError: true });
        render(<PerformanceTab />);
        expect(screen.getByText("Unable to load performance data")).toBeInTheDocument();
    });

    it("renders with account filter prop", () => {
        mockUsePortfolioAccounts.mockReturnValue({ data: [{ account_id: 1, account_name: "TFSA", account_type: "TFSA", brokerage_name: "Wealthsimple", currency: "CAD", is_active: true, created_at: "", last_import_at: null, holdings_count: 0, total_value: 0, total_cost: 0, account_external_id: "123", brokerage_code: "wealthsimple" }], isLoading: false });
        render(<PerformanceTab accountIds={[1]} />);
        expect(screen.getByText("Portfolio Performance")).toBeInTheDocument();
    });
});
