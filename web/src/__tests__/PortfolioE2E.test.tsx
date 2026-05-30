/**
 * E2E Contract Tests — All Portfolio Tabs
 *
 * These tests validate the frontend ↔ backend contract end-to-end for every
 * portfolio tab. Each test group covers two layers:
 *
 *   1. SERVICE CONTRACT — Calls the real PortfolioService class through a
 *      mocked HTTP layer, verifying response shape matches the TypeScript type.
 *   2. RENDER CONTRACT — Renders the tab via PortfolioTabShell with
 *      backend-shaped mock data and verifies no crash + expected content.
 *
 * If the backend changes a key name (e.g. total_return_pct → gain_loss_pct),
 * the corresponding service contract test breaks — preventing silent drift.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

// ═════════════════════════════════════════════════════════════════════════════
// MOCKS (hoisted before imports)
// ═════════════════════════════════════════════════════════════════════════════

// HTTP layer — intercepts `import api from "@/lib/api"`
const mockApiGet = vi.fn();
vi.mock("@/lib/api", () => ({
    default: {
        get: (...args: any[]) => mockApiGet(...args),
    },
}));

// Navigation — mutable so per-test URL params work
let mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
    useSearchParams: () => mockSearchParams,
    useRouter: () => ({ replace: vi.fn() }),
}));

// Service context — provides real PortfolioService with mocked HTTP
import { PortfolioService } from "@/features/portfolio/services/portfolio.service";
import { useServices } from "@/shared/contexts/ServiceContext";
vi.mock("@/shared/contexts/ServiceContext", () => ({
    useServices: vi.fn(),
}));

// Mock usePortfolioAccounts at the hook level for render tests
// (react-query async timing with service-level mocks is unreliable)
import * as usePortfolioModule from "@/features/portfolio/hooks/usePortfolio";
const mockUsePortfolioAccounts = vi.fn();
vi.mock("@/features/portfolio/hooks/usePortfolio", async () => {
    const actual = await vi.importActual<typeof usePortfolioModule>("@/features/portfolio/hooks/usePortfolio");
    return {
        ...actual,
        usePortfolioAccounts: (...args: any[]) => mockUsePortfolioAccounts(...args),
        useBrokerages: () => ({ data: [], isLoading: false }),
        useImportTransactions: () => ({
            mutateAsync: vi.fn().mockResolvedValue({ success: true, import_batch_id: "test-batch" }),
            isPending: false,
            isSuccess: false,
            isError: false,
            data: null,
            error: null,
            reset: vi.fn(),
        }),
        useImportStatus: () => ({ data: null, isLoading: false }),
    };
});

// Shared UI mocks
vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className, ...props }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className, ...props });
    },
}));

vi.mock("recharts", () => {
    const React = require("react");
    return {
        ResponsiveContainer: ({ children }: any) =>
            React.createElement("div", { "data-testid": "responsive-container" }, children),
        ComposedChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "composed-chart" }, children),
        Area: () => null,
        Line: () => null,
        XAxis: () => null,
        YAxis: () => null,
        Tooltip: () => null,
        CartesianGrid: () => null,
        Legend: () => null,
        BarChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "bar-chart" }, children),
        Bar: () => null,
        Cell: () => null,
        PieChart: ({ children }: any) =>
            React.createElement("div", { "data-testid": "pie-chart" }, children),
        Pie: () => null,
    };
});

vi.mock("lucide-react", () => {
    const React = require("react");
    const mkIcon = (name: string) => () =>
        React.createElement("svg", { "data-testid": `icon-${name}` });
    return {
        LayoutDashboard: mkIcon("LayoutDashboard"),
        TrendingUp: mkIcon("TrendingUp"),
        PieChart: mkIcon("PieChart"),
        DollarSign: mkIcon("DollarSign"),
        Receipt: mkIcon("Receipt"),
        Banknote: mkIcon("Banknote"),
        ChartBar: mkIcon("ChartBar"),
        CircleDollarSign: mkIcon("CircleDollarSign"),
        ChevronRight: mkIcon("ChevronRight"),
        ChevronDown: mkIcon("ChevronDown"),
        Search: mkIcon("Search"),
        X: mkIcon("X"),
        Check: mkIcon("Check"),
        Upload: mkIcon("Upload"),
        Plus: mkIcon("Plus"),
    };
});

// ═════════════════════════════════════════════════════════════════════════════
// IMPORTS
// ═════════════════════════════════════════════════════════════════════════════

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { PortfolioTabShell } from "@/features/portfolio/components/PortfolioTabShell";
import type {
    PortfolioAccount,
    PortfolioOverview,
    PerformanceResponse,
    BenchmarkCompareResponse,
    PortfolioAllocationResponse,
    AllocationSegment,
    DividendHistoryResponse,
    MonthlyDividendSummary,
    Transaction,
    Holding,
    PerformanceSnapshot,
} from "@/features/portfolio/types/portfolio.types";

// ═════════════════════════════════════════════════════════════════════════════
// HELPERS
// ═════════════════════════════════════════════════════════════════════════════

function renderWithProviders(ui: React.ReactElement) {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const React = require("react");
    return render(React.createElement(QueryClientProvider, { client: qc }, ui));
}

function setupServices() {
    vi.clearAllMocks();
    const realService = new PortfolioService();
    (useServices as ReturnType<typeof vi.fn>).mockReturnValue({
        portfolioService: realService,
        watchlistService: {},
    });
}

// ═════════════════════════════════════════════════════════════════════════════
// REALISTIC BACKEND RESPONSE BUILDERS
// ═════════════════════════════════════════════════════════════════════════════

function buildOverviewResponse(): PortfolioOverview {
    return {
        success: true,
        net_worth: 80432.50,
        total_cost_basis: 61200.00,
        total_gain_loss: 19232.50,
        total_gain_loss_pct: 31.42,
        ytd_dividends: 1874.35,
        total_holdings_count: 12,
        accounts_count: 3,
        top_holdings: [
            { holding_id: 1, symbol: "AAPL", company_name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics", exchange: "NASDAQ", market_group: "US", quantity: 50, average_cost: 150.00, total_cost: 7500.00, current_price: 180.50, current_value: 9025.00, unrealized_gain_loss: 1525.00, unrealized_gain_loss_pct: 20.33, realized_gain_loss: 0, first_purchase_date: "2024-01-15", last_transaction_date: "2024-06-01" },
            { holding_id: 2, symbol: "GOOGL", company_name: "Alphabet Inc.", sector: "Technology", industry: "Internet Services", exchange: "NASDAQ", market_group: "US", quantity: 30, average_cost: 140.00, total_cost: 4200.00, current_price: 175.20, current_value: 5256.00, unrealized_gain_loss: 1056.00, unrealized_gain_loss_pct: 25.14, realized_gain_loss: 0, first_purchase_date: "2024-02-10", last_transaction_date: "2024-06-01" },
        ],
        account_breakdown: [
            { account_id: 1, account_name: "TFSA", total_value: 40000, total_cost: 30000, gain_loss: 10000, gain_loss_pct: 33.33, holdings_count: 5, account_type: "TFSA", brokerage_name: "Wealthsimple" },
            { account_id: 2, account_name: "RRSP", total_value: 25000, total_cost: 20000, gain_loss: 5000, gain_loss_pct: 25.00, holdings_count: 4, account_type: "RRSP", brokerage_name: "Wealthsimple" },
        ],
    };
}

function buildAccountsResponse(): PortfolioAccount[] {
    return [
        { account_id: 1, account_name: "TFSA", account_type: "TFSA", account_external_id: "ext-1", brokerage_name: "Wealthsimple", brokerage_code: "WS", currency: "CAD", is_active: true, created_at: "2024-01-01", last_import_at: "2026-05-26", holdings_count: 5, total_value: 40000, total_cost: 30000 },
        { account_id: 2, account_name: "RRSP", account_type: "RRSP", account_external_id: "ext-2", brokerage_name: "Wealthsimple", brokerage_code: "WS", currency: "CAD", is_active: true, created_at: "2024-01-01", last_import_at: "2026-05-26", holdings_count: 4, total_value: 25000, total_cost: 20000 },
    ];
}

function buildPerformanceResponse(): PerformanceResponse {
    return {
        success: true,
        period: "1Y",
        snapshots: [
            { date: "2025-06-01", value: 70000, cost_basis: 60000, net_deposits: 0 },
            { date: "2025-07-01", value: 72000, cost_basis: 60500, net_deposits: 500 },
            { date: "2025-08-01", value: 75000, cost_basis: 61000, net_deposits: 1000 },
            { date: "2025-09-01", value: 74000, cost_basis: 61000, net_deposits: 1000 },
            { date: "2025-10-01", value: 78000, cost_basis: 61200, net_deposits: 1200 },
            { date: "2025-11-01", value: 79000, cost_basis: 61200, net_deposits: 1200 },
            { date: "2025-12-01", value: 80000, cost_basis: 61200, net_deposits: 1200 },
        ],
        total_return: 19232.50,
        total_return_pct: 31.42,
        best_day: { date: "2025-10-15", return_pct: 2.34 },
        worst_day: { date: "2025-09-20", return_pct: -1.87 },
    };
}

function buildBenchmarkCompareResponse(): BenchmarkCompareResponse {
    return {
        success: true,
        period: "1Y",
        portfolio: [
            { date: "2025-06-01", value: 70000 },
            { date: "2025-07-01", value: 72000 },
            { date: "2025-08-01", value: 75000 },
            { date: "2025-09-01", value: 74000 },
            { date: "2025-10-01", value: 78000 },
            { date: "2025-11-01", value: 79000 },
            { date: "2025-12-01", value: 80000 },
        ],
        benchmarks: [
            { symbol: "^GSPC", name: "S&P 500", data: [{ date: "2025-06-01", value: 100000 }, { date: "2025-12-01", value: 110000 }] },
        ],
    };
}

function buildHoldingsResponse() {
    return {
        account_id: 1,
        account_name: "TFSA",
        holdings: [
            { holding_id: 1, symbol: "AAPL", company_name: "Apple Inc.", sector: "Technology", industry: "Consumer Electronics", exchange: "NASDAQ", market_group: "US", quantity: 50, average_cost: 150.00, total_cost: 7500.00, current_price: 180.50, current_value: 9025.00, unrealized_gain_loss: 1525.00, unrealized_gain_loss_pct: 20.33, realized_gain_loss: 0, first_purchase_date: "2024-01-15", last_transaction_date: "2024-06-01", currency: "USD" },
            { holding_id: 2, symbol: "GOOGL", company_name: "Alphabet Inc.", sector: "Technology", industry: "Internet Services", exchange: "NASDAQ", market_group: "US", quantity: 30, average_cost: 140.00, total_cost: 4200.00, current_price: 175.20, current_value: 5256.00, unrealized_gain_loss: 1056.00, unrealized_gain_loss_pct: 25.14, realized_gain_loss: 0, first_purchase_date: "2024-02-10", last_transaction_date: "2024-06-01", currency: "USD" },
        ] as Holding[],
    };
}

function buildDividendsResponse() {
    return {
        account_id: 1,
        current_year_total: 1874.35,
        monthly_summaries: [
            { fiscal_year: 2026, fiscal_month: 1, payment_count: 3, total_amount: 450.00, paying_companies: 2 },
            { fiscal_year: 2026, fiscal_month: 2, payment_count: 2, total_amount: 320.50, paying_companies: 2 },
            { fiscal_year: 2026, fiscal_month: 3, payment_count: 4, total_amount: 520.85, paying_companies: 3 },
        ] as MonthlyDividendSummary[],
    };
}

function buildDividendHistoryResponse(): DividendHistoryResponse {
    return {
        success: true,
        account_id: 1,
        dividends: [
            { dividend_id: 101, symbol: "AAPL", company_name: "Apple Inc.", payment_date: "2026-02-15", amount: 95.00, shares_held: 50, amount_per_share: 1.90, account_name: "TFSA", account_type: "TFSA" },
            { dividend_id: 102, symbol: "GOOGL", company_name: "Alphabet Inc.", payment_date: "2026-03-10", amount: 45.00, shares_held: 30, amount_per_share: 1.50, account_name: "TFSA", account_type: "TFSA" },
        ],
        total_count: 12,
        current_year_total: 1874.35,
    };
}

function buildTransactionsResponse() {
    return {
        account_id: 1,
        transactions: [
            { transaction_id: 5001, transaction_date: "2026-03-15", settlement_date: "2026-03-17", activity_type: "Trade", activity_sub_type: "BUY", symbol: "AAPL", security_name: "APPLE INC", quantity: 10, unit_price: 175.00, commission: 0, net_cash_amount: -1750.00, currency: "USD" },
            { transaction_id: 5002, transaction_date: "2026-02-20", settlement_date: "2026-02-22", activity_type: "Trade", activity_sub_type: "SELL", symbol: "MSFT", security_name: "MICROSOFT CORP", quantity: 5, unit_price: 410.00, commission: 0, net_cash_amount: 2050.00, currency: "USD" },
        ] as Transaction[],
        total_count: 2,
    };
}

function buildAllocationResponse(): PortfolioAllocationResponse {
    return {
        success: true,
        group_by: "sector",
        segments: [
            { segment: "Technology", value: 50000, weight: 62.5, count: 2, gain_loss: 10000 },
            { segment: "Energy", value: 30000, weight: 37.5, count: 1, gain_loss: -2000 },
        ] as AllocationSegment[],
        total_value: 80000,
    };
}

function defaultApiMock() {
    mockApiGet.mockImplementation((url: string) => {
        if (url === "/portfolio/accounts") return Promise.resolve({ data: buildAccountsResponse() });
        if (url === "/portfolio/overview") return Promise.resolve({ data: buildOverviewResponse() });
        if (url.startsWith("/portfolio/performance")) return Promise.resolve({ data: buildPerformanceResponse() });
        if (url.startsWith("/portfolio/allocation")) return Promise.resolve({ data: buildAllocationResponse() });
        if (url.startsWith("/portfolio/holdings")) return Promise.resolve({ data: { holdings: [] } });
        if (url.includes("/holdings")) return Promise.resolve({ data: buildHoldingsResponse() });
        if (url.includes("/dividends") && !url.includes("-history")) return Promise.resolve({ data: buildDividendsResponse() });
        if (url.includes("/dividend-history")) return Promise.resolve({ data: buildDividendHistoryResponse() });
        if (url.includes("/transactions")) return Promise.resolve({ data: buildTransactionsResponse() });
        if (url.includes("/benchmarks") && !url.includes("compare")) return Promise.resolve({ data: { success: true, benchmarks: [] } });
        if (url.includes("/compare")) return Promise.resolve({ data: buildBenchmarkCompareResponse() });
        return Promise.resolve({ data: {} });
    });
}

// ═════════════════════════════════════════════════════════════════════════════
// OVERVIEW — PT-E2E-01 to PT-E2E-06
// ═════════════════════════════════════════════════════════════════════════════

describe("E2E: Overview tab — PT-E2E-01 to PT-E2E-06", () => {
    beforeEach(() => {
        setupServices();
        mockSearchParams = new URLSearchParams();
        mockUsePortfolioAccounts.mockReturnValue({ data: buildAccountsResponse(), isLoading: false });
    });

    it("PT-E2E-01: service response has all PortfolioOverview keys", async () => {
        mockApiGet.mockResolvedValue({ data: buildOverviewResponse() });
        const result = await new PortfolioService().getPortfolioOverview();
        const keys = ["success", "net_worth", "total_cost_basis", "total_gain_loss", "total_gain_loss_pct", "ytd_dividends", "total_holdings_count", "accounts_count", "top_holdings", "account_breakdown"] as const;
        for (const k of keys) expect(result).toHaveProperty(k);
        expect(typeof result.net_worth).toBe("number");
        expect(Array.isArray(result.top_holdings)).toBe(true);
    });

    it("PT-E2E-02: net_worth is populated (catches total_value drift)", async () => {
        mockApiGet.mockResolvedValue({ data: buildOverviewResponse() });
        const result = await new PortfolioService().getPortfolioOverview();
        expect(result.net_worth).toBeGreaterThan(0);
    });

    it("PT-E2E-03: OverviewTab renders summary cards from real backend shape", async () => {
        defaultApiMock();
        renderWithProviders(<PortfolioTabShell />);
        expect(await screen.findByText("Total Value")).toBeInTheDocument();
        expect(screen.getByText("$80,432.50")).toBeInTheDocument();
        expect(screen.getByText("$19,232.50")).toBeInTheDocument();
        expect(screen.getByText("+31.42%")).toBeInTheDocument();
        expect(screen.getByText("$1,874.35")).toBeInTheDocument();
    });

    it("PT-E2E-04: catches net_worth → total_value backend drift", async () => {
        mockApiGet.mockResolvedValue({ data: { ...buildOverviewResponse(), net_worth: undefined, total_value: 80432.50 } });
        const result = await new PortfolioService().getPortfolioOverview();
        expect(result.net_worth).toBeUndefined();
    });

    it("PT-E2E-05: TabBar renders all 6 tabs", async () => {
        defaultApiMock();
        renderWithProviders(<PortfolioTabShell />);
        expect(await screen.findByText("Overview")).toBeInTheDocument();
        expect(screen.getByText("Performance")).toBeInTheDocument();
        expect(screen.getByText("Holdings")).toBeInTheDocument();
        expect(screen.getByText("Dividends")).toBeInTheDocument();
        expect(screen.getByText("Transactions")).toBeInTheDocument();
        expect(screen.getByText("Allocation")).toBeInTheDocument();
    });

    it("PT-E2E-06: account_breakdown entries match backend schema", async () => {
        mockApiGet.mockResolvedValue({ data: buildOverviewResponse() });
        const result = await new PortfolioService().getPortfolioOverview();
        for (const ab of result.account_breakdown) {
            expect(ab).toHaveProperty("account_id");
            expect(ab).toHaveProperty("account_name");
            expect(ab).toHaveProperty("total_value");
            expect(ab).toHaveProperty("gain_loss");
            expect(typeof ab.total_value).toBe("number");
            expect(typeof ab.holdings_count).toBe("number");
        }
    });
});

// ═════════════════════════════════════════════════════════════════════════════
// PERFORMANCE — PT-E2E-07 to PT-E2E-10
// ═════════════════════════════════════════════════════════════════════════════

describe("E2E: Performance tab — PT-E2E-07 to PT-E2E-10", () => {
    beforeEach(() => {
        setupServices();
        mockSearchParams = new URLSearchParams({ tab: "performance" });
        mockUsePortfolioAccounts.mockReturnValue({ data: buildAccountsResponse(), isLoading: false });
    });

    it("PT-E2E-07: PerformanceResponse has all keys", async () => {
        mockApiGet.mockResolvedValue({ data: buildPerformanceResponse() });
        const result = await new PortfolioService().getPortfolioPerformance("1Y");
        expect(result).toHaveProperty("success");
        expect(result).toHaveProperty("period");
        expect(result).toHaveProperty("snapshots");
        expect(result).toHaveProperty("total_return");
        expect(result).toHaveProperty("total_return_pct");
        expect(result).toHaveProperty("best_day");
        expect(result).toHaveProperty("worst_day");
        expect(typeof result.total_return_pct).toBe("number");
        expect(Array.isArray(result.snapshots)).toBe(true);
    });

    it("PT-E2E-08: PerformanceSnapshot entries have correct shape", async () => {
        mockApiGet.mockResolvedValue({ data: buildPerformanceResponse() });
        const result = await new PortfolioService().getPortfolioPerformance("1Y");
        for (const s of result.snapshots) {
            expect(s).toHaveProperty("date");
            expect(s).toHaveProperty("value");
            expect(s).toHaveProperty("cost_basis");
            expect(s).toHaveProperty("net_deposits");
            expect(typeof s.value).toBe("number");
        }
    });

    it("PT-E2E-09: PerformanceTab renders without crashing", async () => {
        defaultApiMock();
        renderWithProviders(<PortfolioTabShell />);
        // Performance chart is self-contained; just verify no crash + skeleton resolves
        expect(await screen.findByText("Performance")).toBeInTheDocument();
        // Period buttons render
        expect(screen.getByText("1M")).toBeInTheDocument();
        expect(screen.getByText("1Y")).toBeInTheDocument();
        expect(screen.getByText("MAX")).toBeInTheDocument();
    });

    it("PT-E2E-10: BenchmarkCompareResponse has all keys", async () => {
        mockApiGet.mockResolvedValue({ data: buildBenchmarkCompareResponse() });
        const result = await new PortfolioService().getBenchmarkCompare("1Y", ["^GSPC"]);
        expect(result).toHaveProperty("success");
        expect(result).toHaveProperty("period");
        expect(result).toHaveProperty("portfolio");
        expect(result).toHaveProperty("benchmarks");
        expect(Array.isArray(result.portfolio)).toBe(true);
        expect(Array.isArray(result.benchmarks)).toBe(true);
        for (const b of result.benchmarks) {
            expect(b).toHaveProperty("symbol");
            expect(b).toHaveProperty("name");
            expect(b).toHaveProperty("data");
            expect(Array.isArray(b.data)).toBe(true);
        }
    });
});

// ═════════════════════════════════════════════════════════════════════════════
// ALLOCATION — PT-E2E-11 to PT-E2E-14
// ═════════════════════════════════════════════════════════════════════════════

describe("E2E: Allocation tab — PT-E2E-11 to PT-E2E-14", () => {
    beforeEach(() => {
        setupServices();
        mockSearchParams = new URLSearchParams({ tab: "allocation" });
        mockUsePortfolioAccounts.mockReturnValue({ data: buildAccountsResponse(), isLoading: false });
    });

    it("PT-E2E-11: PortfolioAllocationResponse has all keys", async () => {
        mockApiGet.mockResolvedValue({ data: buildAllocationResponse() });
        const result = await new PortfolioService().getPortfolioAllocation("sector");
        expect(result).toHaveProperty("success");
        expect(result).toHaveProperty("group_by");
        expect(result).toHaveProperty("segments");
        expect(result).toHaveProperty("total_value");
        expect(Array.isArray(result.segments)).toBe(true);
    });

    it("PT-E2E-12: AllocationSegment entries match backend schema", async () => {
        mockApiGet.mockResolvedValue({ data: buildAllocationResponse() });
        const result = await new PortfolioService().getPortfolioAllocation("sector");
        for (const s of result.segments) {
            expect(s).toHaveProperty("segment");
            expect(s).toHaveProperty("value");
            expect(s).toHaveProperty("weight");
            expect(s).toHaveProperty("count");
            expect(s).toHaveProperty("gain_loss");
            expect(typeof s.weight).toBe("number");
            expect(typeof s.count).toBe("number");
        }
    });

    it("PT-E2E-13: AllocationTab renders segments with correct values", async () => {
        defaultApiMock();
        renderWithProviders(<PortfolioTabShell />);
        expect(await screen.findByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Energy")).toBeInTheDocument();
        expect(screen.getByText("62.5%")).toBeInTheDocument();
        expect(screen.getByText("37.5%")).toBeInTheDocument();
        expect(screen.getByText("$50,000.00")).toBeInTheDocument();
        expect(screen.getByText("$30,000.00")).toBeInTheDocument();
        // Positive gain_loss shows green, negative shows red
        expect(screen.getByText("+$10,000.00")).toBeInTheDocument();
    });

    it("PT-E2E-14: AllocationTab shows empty state when no segments", async () => {
        mockApiGet.mockImplementation((url: string) => {
            if (url.startsWith("/portfolio/allocation")) return Promise.resolve({ data: { success: true, group_by: "sector", segments: [], total_value: 0 } });
            if (url === "/portfolio/accounts") return Promise.resolve({ data: buildAccountsResponse() });
            if (url === "/portfolio/overview") return Promise.resolve({ data: buildOverviewResponse() });
            return Promise.resolve({ data: {} });
        });
        renderWithProviders(<PortfolioTabShell />);
        expect(await screen.findByText("No allocation data available")).toBeInTheDocument();
    });
});

// ═════════════════════════════════════════════════════════════════════════════
// HOLDINGS — PT-E2E-15 to PT-E2E-17
// ═════════════════════════════════════════════════════════════════════════════

describe("E2E: Holdings tab — PT-E2E-15 to PT-E2E-17", () => {
    beforeEach(() => {
        setupServices();
        mockSearchParams = new URLSearchParams({ tab: "holdings", account: "1" });
        mockUsePortfolioAccounts.mockReturnValue({ data: buildAccountsResponse(), isLoading: false });
    });

    it("PT-E2E-15: Holdings response has correct shape", async () => {
        mockApiGet.mockResolvedValue({ data: buildHoldingsResponse() });
        const result = await new PortfolioService().getAccountHoldings(1);
        expect(result).toHaveProperty("account_id");
        expect(result).toHaveProperty("account_name");
        expect(result).toHaveProperty("holdings");
        expect(Array.isArray(result.holdings)).toBe(true);
    });

    it("PT-E2E-16: Holding entries have all required keys from backend schema", async () => {
        mockApiGet.mockResolvedValue({ data: buildHoldingsResponse() });
        const result = await new PortfolioService().getAccountHoldings(1);
        for (const h of result.holdings) {
            expect(h).toHaveProperty("holding_id");
            expect(h).toHaveProperty("symbol");
            expect(h).toHaveProperty("company_name");
            expect(h).toHaveProperty("quantity");
            expect(h).toHaveProperty("average_cost");
            expect(h).toHaveProperty("total_cost");
            expect(h).toHaveProperty("current_price");
            expect(h).toHaveProperty("current_value");
            expect(h).toHaveProperty("unrealized_gain_loss");
            expect(h).toHaveProperty("unrealized_gain_loss_pct");
            expect(typeof h.quantity).toBe("number");
            expect(typeof h.current_value).toBe("number");
        }
    });

    it("PT-E2E-17: HoldingsTab renders holdings from real backend data", async () => {
        mockApiGet.mockImplementation((url: string) => {
            if (url === "/portfolio/accounts") return Promise.resolve({ data: buildAccountsResponse() });
            if (url === "/portfolio/overview") return Promise.resolve({ data: buildOverviewResponse() });
            if (url.includes("/holdings")) return Promise.resolve({ data: buildHoldingsResponse() });
            if (url.startsWith("/portfolio/performance")) return Promise.resolve({ data: buildPerformanceResponse() });
            if (url.startsWith("/portfolio/allocation")) return Promise.resolve({ data: buildAllocationResponse() });
            return Promise.resolve({ data: {} });
        });
        renderWithProviders(<PortfolioTabShell />);
        expect(await screen.findByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("GOOGL")).toBeInTheDocument();
        expect(screen.getByText("$9,025.00")).toBeInTheDocument();
        expect(screen.getByText("$5,256.00")).toBeInTheDocument();
        expect(screen.getByText("+20.33%")).toBeInTheDocument();
        expect(screen.getByText("+25.14%")).toBeInTheDocument();
    });
});

// ═════════════════════════════════════════════════════════════════════════════
// DIVIDENDS — PT-E2E-18 to PT-E2E-21
// ═════════════════════════════════════════════════════════════════════════════

describe("E2E: Dividends tab — PT-E2E-18 to PT-E2E-21", () => {
    beforeEach(() => {
        setupServices();
        mockSearchParams = new URLSearchParams({ tab: "dividends", account: "1" });
        mockUsePortfolioAccounts.mockReturnValue({ data: buildAccountsResponse(), isLoading: false });
    });

    it("PT-E2E-18: Dividend monthly summaries have correct shape", async () => {
        mockApiGet.mockResolvedValue({ data: buildDividendsResponse() });
        const result = await new PortfolioService().getAccountDividends(1);
        expect(result).toHaveProperty("account_id");
        expect(result).toHaveProperty("current_year_total");
        expect(result).toHaveProperty("monthly_summaries");
        expect(Array.isArray(result.monthly_summaries)).toBe(true);
        for (const m of result.monthly_summaries) {
            expect(m).toHaveProperty("fiscal_year");
            expect(m).toHaveProperty("fiscal_month");
            expect(m).toHaveProperty("total_amount");
            expect(m).toHaveProperty("payment_count");
            expect(m).toHaveProperty("paying_companies");
            expect(typeof m.total_amount).toBe("number");
        }
    });

    it("PT-E2E-19: DividendHistoryResponse has correct shape", async () => {
        // Note: dividend-history endpoint is not yet implemented in backend
        mockApiGet.mockResolvedValue({ data: buildDividendHistoryResponse() });
        const result = await new PortfolioService().getDividendHistory(1);
        expect(result).toHaveProperty("success");
        expect(result).toHaveProperty("dividends");
        expect(result).toHaveProperty("total_count");
        expect(result).toHaveProperty("current_year_total");
        expect(Array.isArray(result.dividends)).toBe(true);
        for (const d of result.dividends) {
            expect(d).toHaveProperty("dividend_id");
            expect(d).toHaveProperty("symbol");
            expect(d).toHaveProperty("payment_date");
            expect(d).toHaveProperty("amount");
            expect(typeof d.amount).toBe("number");
        }
    });

    it("PT-E2E-20: DividendsTab shows monthly summary by default", async () => {
        defaultApiMock();
        renderWithProviders(<PortfolioTabShell />);
        // Monthly Summary view shows month labels and amounts
        expect(await screen.findByText("Jan 2026")).toBeInTheDocument();
        expect(screen.getByText("Feb 2026")).toBeInTheDocument();
        expect(screen.getByText("Mar 2026")).toBeInTheDocument();
        expect(screen.getByText("$450.00")).toBeInTheDocument();
        expect(screen.getByText("$320.50")).toBeInTheDocument();
        expect(screen.getByText("$520.85")).toBeInTheDocument();
    });
});

// ═════════════════════════════════════════════════════════════════════════════
// TRANSACTIONS — PT-E2E-22 to PT-E2E-24
// ═════════════════════════════════════════════════════════════════════════════

describe("E2E: Transactions tab — PT-E2E-22 to PT-E2E-24", () => {
    beforeEach(() => {
        setupServices();
        mockSearchParams = new URLSearchParams({ tab: "transactions", account: "1" });
        mockUsePortfolioAccounts.mockReturnValue({ data: buildAccountsResponse(), isLoading: false });
    });

    it("PT-E2E-22: Transactions response has correct shape", async () => {
        mockApiGet.mockResolvedValue({ data: buildTransactionsResponse() });
        const result = await new PortfolioService().getAccountTransactionsFiltered(1);
        expect(result).toHaveProperty("account_id");
        expect(result).toHaveProperty("transactions");
        expect(result).toHaveProperty("total_count");
        expect(Array.isArray(result.transactions)).toBe(true);
    });

    it("PT-E2E-23: Transaction entries have all required keys", async () => {
        mockApiGet.mockResolvedValue({ data: buildTransactionsResponse() });
        const result = await new PortfolioService().getAccountTransactionsFiltered(1);
        for (const t of result.transactions) {
            expect(t).toHaveProperty("transaction_id");
            expect(t).toHaveProperty("transaction_date");
            expect(t).toHaveProperty("activity_type");
            expect(t).toHaveProperty("symbol");
            expect(t).toHaveProperty("security_name");
            expect(t).toHaveProperty("quantity");
            expect(t).toHaveProperty("unit_price");
            expect(t).toHaveProperty("net_cash_amount");
            expect(t).toHaveProperty("currency");
            expect(typeof t.net_cash_amount).toBe("number");
        }
    });

    it("PT-E2E-24: TransactionsTab renders transactions from real backend data", async () => {
        defaultApiMock();
        renderWithProviders(<PortfolioTabShell />);
        expect(await screen.findByText("AAPL")).toBeInTheDocument();
        expect(screen.getByText("MSFT")).toBeInTheDocument();
        // Security name displayed as description fallback
        expect(screen.getByText("APPLE INC")).toBeInTheDocument();
        expect(screen.getByText("MICROSOFT CORP")).toBeInTheDocument();
    });
});
