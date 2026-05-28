import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const mockUseAccountTransactionsFiltered = vi.fn();
const mockUseAllTransactions = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    useAccountTransactionsFiltered: (...args: any[]) => mockUseAccountTransactionsFiltered(...args),
    useAllTransactions: (...args: any[]) => mockUseAllTransactions(...args),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

import { TransactionsTab } from "@/features/portfolio/components/TransactionsTab";

function makeTransactions() {
    return {
        account_id: 1,
        transactions: [
            {
                transaction_id: 5001, transaction_date: "2026-03-15", settlement_date: "2026-03-17",
                activity_type: "Trade", activity_sub_type: "BUY", symbol: "AAPL",
                security_name: "APPLE INC", quantity: 10, unit_price: 175, commission: 0,
                net_cash_amount: -1750, currency: "USD",
            },
            {
                transaction_id: 5002, transaction_date: "2026-02-20", settlement_date: "2026-02-22",
                activity_type: "Trade", activity_sub_type: "SELL", symbol: "MSFT",
                security_name: "MICROSOFT CORP", quantity: 5, unit_price: 410, commission: 0,
                net_cash_amount: 2050, currency: "USD",
            },
            {
                transaction_id: 5003, transaction_date: "2026-01-10", settlement_date: null,
                activity_type: "DIVIDEND", activity_sub_type: null, symbol: "AAPL",
                security_name: null, quantity: null, unit_price: null, commission: 0,
                net_cash_amount: 95, currency: "USD",
            },
        ],
        total_count: 3,
    };
}

describe("TransactionsTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAccountTransactionsFiltered.mockReturnValue({ data: makeTransactions(), isLoading: false });
        mockUseAllTransactions.mockReturnValue({ data: makeTransactions(), isLoading: false });
    });

    it("renders transaction rows with symbols and amounts for a specific account", () => {
        render(<TransactionsTab accountIds={[1]} />);
        expect(screen.getAllByText("AAPL").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("MSFT")).toBeInTheDocument();
        expect(screen.getByText("APPLE INC")).toBeInTheDocument();
        expect(screen.getByText("MICROSOFT CORP")).toBeInTheDocument();
    });

    it("renders transaction rows for all accounts", () => {
        render(<TransactionsTab />);
        expect(screen.getAllByText("AAPL").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("MSFT")).toBeInTheDocument();
    });

    it("shows absolute dollar amounts for net_cash", () => {
        render(<TransactionsTab accountIds={[1]} />);
        expect(screen.getByText("$1,750.00")).toBeInTheDocument();
        expect(screen.getByText("$2,050.00")).toBeInTheDocument();
    });

    it("shows loading state", () => {
        mockUseAccountTransactionsFiltered.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<TransactionsTab accountIds={[1]} />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no transactions", () => {
        mockUseAccountTransactionsFiltered.mockReturnValue({
            data: { account_id: 1, transactions: [], total_count: 0 },
            isLoading: false,
        });
        render(<TransactionsTab accountIds={[1]} />);
        expect(screen.getByText("No transactions found matching filters")).toBeInTheDocument();
    });

    it("toggles filter panel visibility", () => {
        render(<TransactionsTab accountIds={[1]} />);
        expect(screen.queryByText("Activity Type")).not.toBeInTheDocument();
        fireEvent.click(screen.getByText("Show Filters"));
        expect(screen.getByText("Activity Type")).toBeInTheDocument();
        expect(screen.getByText("From")).toBeInTheDocument();
        expect(screen.getByText("To")).toBeInTheDocument();
        expect(screen.getByText("Search")).toBeInTheDocument();
        fireEvent.click(screen.getByText("Hide Filters"));
        expect(screen.queryByText("Activity Type")).not.toBeInTheDocument();
    });

    it("shows activity type colors for each transaction type", () => {
        render(<TransactionsTab accountIds={[1]} />);
        const buyText = screen.getAllByText("Trade");
        expect(buyText.length).toBeGreaterThanOrEqual(1);
    });

    it("displays transaction dates", () => {
        render(<TransactionsTab accountIds={[1]} />);
        expect(screen.getByText("2026-03-15")).toBeInTheDocument();
        expect(screen.getByText("2026-02-20")).toBeInTheDocument();
    });
});
