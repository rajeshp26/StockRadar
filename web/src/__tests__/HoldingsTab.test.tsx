import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

const mockUseAccountHoldings = vi.fn();
const mockUseAllHoldings = vi.fn();
const mockUsePortfolioAllocation = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    useAccountHoldings: (...args: any[]) => mockUseAccountHoldings(...args),
    useAllHoldings: (...args: any[]) => mockUseAllHoldings(...args),
    usePortfolioAllocation: (...args: any[]) => mockUsePortfolioAllocation(...args),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

vi.mock("recharts", () => ({
    ResponsiveContainer: ({ children }: any) =>
        React.createElement("div", { "data-testid": "responsive-container" }, children),
    PieChart: ({ children }: any) =>
        React.createElement("div", { "data-testid": "pie-chart" }, children),
    Pie: () => null,
    Cell: () => null,
    Tooltip: () => null,
}));

import { HoldingsTab } from "@/features/portfolio/components/HoldingsTab";

function makeHolding(overrides = {}) {
    return {
        holding_id: 1,
        symbol: "AAPL",
        company_name: "Apple Inc.",
        quantity: 50,
        average_cost: 150,
        total_cost: 7500,
        current_price: 180.5,
        current_value: 9025,
        unrealized_gain_loss: 1525,
        unrealized_gain_loss_pct: 20.33,
        realized_gain_loss: 0,
        currency: "USD",
        sector: "Technology",
        industry: "Consumer Electronics",
        exchange: "NASDAQ",
        market_group: "US",
        first_purchase_date: "2024-01-15",
        last_transaction_date: "2024-06-01",
        ...overrides,
    };
}

describe("HoldingsTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAccountHoldings.mockReturnValue({ data: null, isLoading: false });
        mockUseAllHoldings.mockReturnValue({ data: [], isLoading: false });
        mockUsePortfolioAllocation.mockReturnValue({ data: null, isLoading: false });
    });

    it("shows empty state when no accountIds means all accounts but none exist", () => {
        mockUseAllHoldings.mockReturnValue({ data: [], isLoading: false });
        render(<HoldingsTab />);
        expect(screen.getByText("No holdings found")).toBeInTheDocument();
    });

    it("shows loading skeletons while fetching", () => {
        mockUseAccountHoldings.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<HoldingsTab accountIds={[1]} />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no holdings exist for specific account", () => {
        mockUseAccountHoldings.mockReturnValue({ data: { account_id: 1, account_name: "TFSA", holdings: [] }, isLoading: false });
        render(<HoldingsTab accountIds={[1]} />);
        expect(screen.getByText("No holdings found")).toBeInTheDocument();
    });

    it("renders holding rows with symbol, value, and gain/loss", () => {
        mockUseAccountHoldings.mockReturnValue({
            data: {
                account_id: 1,
                account_name: "TFSA",
                holdings: [makeHolding(), makeHolding({ holding_id: 2, symbol: "GOOGL", current_value: 5256, unrealized_gain_loss_pct: 25.14 })],
            },
            isLoading: false,
        });
        render(<HoldingsTab accountIds={[1]} />);
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
        expect(screen.getByText("$9,025.00")).toBeInTheDocument();
        expect(screen.getByText("$5,256.00")).toBeInTheDocument();
        expect(screen.getByText("+20.33%")).toBeInTheDocument();
        expect(screen.getByText("+25.14%")).toBeInTheDocument();
    });

    it("shows negative gain/loss in red", () => {
        mockUseAccountHoldings.mockReturnValue({
            data: {
                account_id: 1,
                account_name: "TFSA",
                holdings: [makeHolding({ unrealized_gain_loss_pct: -5.5 })],
            },
            isLoading: false,
        });
        render(<HoldingsTab accountIds={[1]} />);
        const lossText = screen.getByText("-5.50%");
        expect(lossText.className).toContain("text-red-400");
    });

    it("displays share quantity and currency", () => {
        mockUseAccountHoldings.mockReturnValue({
            data: {
                account_id: 1,
                account_name: "TFSA",
                holdings: [makeHolding()],
            },
            isLoading: false,
        });
        render(<HoldingsTab accountIds={[1]} />);
        expect(screen.getByText("50 shares", { exact: false })).toBeInTheDocument();
        expect(screen.getByText("USD", { exact: false })).toBeInTheDocument();
    });

    it("handles holdings as array directly (not wrapped in object)", () => {
        mockUseAccountHoldings.mockReturnValue({
            data: [makeHolding()],
            isLoading: false,
        });
        render(<HoldingsTab accountIds={[1]} />);
        expect(screen.getByText("AAPL")).toBeInTheDocument();
    });

    it("shows holdings for all accounts when no accountIds provided", () => {
        mockUseAllHoldings.mockReturnValue({ data: [makeHolding(), makeHolding({ holding_id: 2, symbol: "GOOGL", account_id: 2 })], isLoading: false });
        render(<HoldingsTab />);
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
    });
});
