import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

const mockUseDividendSummary = vi.fn();
const mockUseDividendUpcoming = vi.fn();
const mockUseDividendHoldings = vi.fn();
const mockUseAllDividends = vi.fn();
const mockUseDividendHoldingDetail = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    useDividendSummary: (...args: any[]) => mockUseDividendSummary(...args),
    useDividendUpcoming: (...args: any[]) => mockUseDividendUpcoming(...args),
    useDividendHoldings: (...args: any[]) => mockUseDividendHoldings(...args),
    useAllDividends: (...args: any[]) => mockUseAllDividends(...args),
    useDividendHoldingDetail: (...args: any[]) => mockUseDividendHoldingDetail(...args),
}));

import { DividendsTab } from "@/features/portfolio/components/DividendsTab";

const mockSummary = {
    trailing_12m_income: 5000,
    forward_annual_estimate: 5200,
    ytd_dividends: 1874.35,
    forward_yield_on_cost: 4.52,
    avg_monthly_trailing: 416.67,
    avg_monthly_forward: 433.33,
    portfolio_growth_5yr: { value: 8.5, coverage_pct: 80 },
    portfolio_safety: { value: 72.3, coverage_pct: 85 },
    goal_progress: null,
    currency: 'USD',
    currencies_mixed: false,
    last_updated: '2026-06-18T00:00:00Z',
};

const mockMonthlySummaries = {
    account_id: 1,
    current_year_total: 1874.35,
    monthly_summaries: [
        { fiscal_year: 2026, fiscal_month: 1, payment_count: 3, total_amount: 450, paying_companies: 2 },
        { fiscal_year: 2026, fiscal_month: 2, payment_count: 2, total_amount: 320.5, paying_companies: 2 },
    ],
};

const mockUpcoming = [
    { symbol: 'AAPL', company_name: 'Apple Inc.', ex_dividend_date: '2026-07-15', amount_per_share: 1.90, estimated_income: 95, dividend_type: 'regular', confidence: 'high' },
];

const mockHoldings = [
    { account_id: 1, symbol: 'AAPL', company_name: 'Apple Inc.', sector: 'Technology', quantity: 50, market_value: 9025, total_cost: 7500, forward_income: 380, trailing_12m_income: 360, current_yield: 4.21, forward_yield_on_cost: 5.07, payout_ratio: 45, increase_streak: 10, safety_score: 75, next_event: null },
];

describe("DividendsTab", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseDividendSummary.mockReturnValue({ data: mockSummary, isLoading: false, error: null });
        mockUseDividendUpcoming.mockReturnValue({ data: mockUpcoming, isLoading: false, error: null });
        mockUseDividendHoldings.mockReturnValue({ data: mockHoldings, isLoading: false, error: null });
        mockUseAllDividends.mockReturnValue({ data: mockMonthlySummaries, isLoading: false });
        mockUseDividendHoldingDetail.mockReturnValue({ data: undefined, isLoading: false, error: null });
    });

    it("renders page header", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Dividend Dashboard")).toBeInTheDocument();
    });

    it("renders summary metrics", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Dividend Summary")).toBeInTheDocument();
        expect(screen.getAllByText("Trailing 12M").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("Forward Est. Annual")).toBeInTheDocument();
    });

    it("renders trend chart section", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Monthly Dividend Income")).toBeInTheDocument();
    });

    it("renders sector chart section", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Income by Sector")).toBeInTheDocument();
    });

    it("renders upcoming ex-dates section", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Upcoming Ex-Dates")).toBeInTheDocument();
        expect(screen.getAllByText("AAPL").length).toBeGreaterThanOrEqual(1);
    });

    it("renders holdings section", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getAllByText("Holdings").length).toBeGreaterThanOrEqual(1);
    });

    it("renders all filter chips", () => {
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Summary")).toBeInTheDocument();
        expect(screen.getByText("Trend")).toBeInTheDocument();
        expect(screen.getByText("Upcoming")).toBeInTheDocument();
        expect(screen.getAllByText("Holdings").length).toBeGreaterThanOrEqual(1);
    });

    it("shows loading state", () => {
        mockUseDividendSummary.mockReturnValue({ data: undefined, isLoading: true, error: null });
        mockUseAllDividends.mockReturnValue({ data: null, isLoading: true });
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Dividend Summary")).toBeInTheDocument();
    });

    it("shows error state in summary", () => {
        mockUseDividendSummary.mockReturnValue({ data: undefined, isLoading: false, error: new Error('fail') });
        render(<DividendsTab accountIds={[1]} />);
        expect(screen.getByText("Failed to load dividend summary")).toBeInTheDocument();
    });
});
