import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

const mockUseAccountDividends = vi.fn();
const mockUseDividendHistory = vi.fn();
const mockUseAllDividends = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    useAccountDividends: (...args: any[]) => mockUseAccountDividends(...args),
    useDividendHistory: (...args: any[]) => mockUseDividendHistory(...args),
    useAllDividends: (...args: any[]) => mockUseAllDividends(...args),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

import { DividendsTab } from "@/features/portfolio/components/DividendsTab";

function makeMonthlySummaries() {
    return {
        account_id: 1,
        current_year_total: 1874.35,
        monthly_summaries: [
            { fiscal_year: 2026, fiscal_month: 1, payment_count: 3, total_amount: 450.0, paying_companies: 2 },
            { fiscal_year: 2026, fiscal_month: 2, payment_count: 2, total_amount: 320.5, paying_companies: 2 },
        ],
    };
}

function makeDetailData() {
    return {
        success: true,
        account_id: 1,
        dividends: [
            { dividend_id: 101, symbol: "AAPL", company_name: "Apple Inc.", payment_date: "2026-02-15", amount: 95.0, shares_held: 50, amount_per_share: 1.9 },
            { dividend_id: 102, symbol: "GOOGL", company_name: "Alphabet Inc.", payment_date: "2026-03-10", amount: 45.0, shares_held: 30, amount_per_share: 1.5 },
        ],
        total_count: 2,
        current_year_total: 140.0,
    };
}

describe("DividendsTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAccountDividends.mockReturnValue({ data: makeMonthlySummaries(), isLoading: false });
        mockUseDividendHistory.mockReturnValue({ data: makeDetailData(), isLoading: false });
        mockUseAllDividends.mockReturnValue({ data: makeMonthlySummaries(), isLoading: false });
    });

    it("renders monthly summary view by default for a specific account", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Jan 2026")).toBeInTheDocument();
        expect(screen.getByText("Feb 2026")).toBeInTheDocument();
        expect(screen.getByText("$450.00")).toBeInTheDocument();
        expect(screen.getByText("$320.50")).toBeInTheDocument();
    });

    it("renders monthly summary view for all accounts", () => {
        render(<DividendsTab />);
        expect(screen.getByText("Jan 2026")).toBeInTheDocument();
        expect(screen.getByText("Feb 2026")).toBeInTheDocument();
    });

    it("switches to detailed history view", () => {
        render(<DividendsTab accountIds={[1]} />);
        fireEvent.click(screen.getByText("Detailed History"));
        expect(screen.getByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
        expect(screen.getByText("Apple Inc.")).toBeInTheDocument();
        expect(screen.getByText("Alphabet Inc.")).toBeInTheDocument();
    });

    it("switches back to monthly summary view", () => {
        render(<DividendsTab accountIds={[1]} />);
        fireEvent.click(screen.getByText("Detailed History"));
        fireEvent.click(screen.getByText("Monthly Summary"));
        expect(screen.getByText("Jan 2026")).toBeInTheDocument();
    });

    it("shows loading state", () => {
        mockUseAccountDividends.mockReturnValue({ data: null, isLoading: true });
        mockUseAllDividends.mockReturnValue({ data: null, isLoading: true });
        const { container } = render(<DividendsTab accountIds={[1]} />);
        expect(container.querySelectorAll("[data-testid='skeleton']").length).toBeGreaterThanOrEqual(1);
    });

    it("shows empty state when no monthly summaries", () => {
        mockUseAccountDividends.mockReturnValue({ data: { account_id: 1, current_year_total: 0, monthly_summaries: [] }, isLoading: false });
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("No dividend data available")).toBeInTheDocument();
    });

    it("shows amount per share in detailed view", () => {
        render(<DividendsTab accountIds={[1]} />);
        fireEvent.click(screen.getByText("Detailed History"));
        expect(screen.getByText("$1.9000/share")).toBeInTheDocument();
        expect(screen.getByText("$1.5000/share")).toBeInTheDocument();
    });

    it("has Monthly Summary button active by default", () => {
        render(<DividendsTab accountIds={[1]} />);
        const summaryBtn = screen.getByText("Monthly Summary");
        expect(summaryBtn.className).toContain("bg-blue-600");
    });
});
