import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Mock next/navigation ───────────────────────────────────────────────
const mockUseSearchParams = vi.fn();
const mockUseRouter = vi.fn();
const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
    useSearchParams: (...args: any[]) => mockUseSearchParams(...args),
    useRouter: (...args: any[]) => mockUseRouter(...args),
}));

// ── Mock ServiceContext ─────────────────────────────────────────────────
vi.mock("@/shared/contexts/ServiceContext", () => ({
    useServices: () => ({
        portfolioService: {
            api: {
                get: vi.fn().mockResolvedValue({ data: { exists: true, company_name: "Test Corp" } }),
                post: vi.fn().mockResolvedValue({ data: { success: true } }),
            },
            fileToBase64: vi.fn().mockResolvedValue("base64content"),
            getBrokerages: vi.fn().mockResolvedValue([]),
            getImportStatus: vi.fn().mockResolvedValue({ status: "completed", rows_inserted: 10 }),
            importTransactions: vi.fn().mockResolvedValue({ success: true, import_batch_id: "test-batch" }),
        },
        watchlistService: {},
    }),
}));

vi.mock("@/hooks/use-toast", () => ({
    useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("@tanstack/react-query", async () => {
    const actual = await vi.importActual("@tanstack/react-query");
    return {
        ...actual,
        useMutation: () => ({
            mutateAsync: vi.fn().mockResolvedValue({ success: true, import_batch_id: "test-batch" }),
            mutate: vi.fn(),
            isPending: false,
            isSuccess: false,
            isError: false,
            data: null,
            error: null,
            reset: vi.fn(),
        }),
        useQueryClient: () => ({
            invalidateQueries: vi.fn(),
        }),
    };
});

vi.mock("@/lib/query-keys", () => ({
    QK: {
        portfolioOverview: () => ["portfolio", "overview"],
        portfolioAccounts: () => ["portfolio", "accounts"],
        portfolioHoldings: () => ["portfolio", "holdings"],
        portfolioAccountHoldings: (id: number) => ["portfolio", "account", id, "holdings"],
        portfolioBrokerages: () => ["portfolio", "brokerages"],
        portfolioPerformance: () => ["portfolio", "performance"],
        portfolioBenchmarkCompare: () => ["portfolio", "benchmark-compare"],
        portfolioBenchmarks: () => ["portfolio", "benchmarks"],
        portfolioAllocation: () => ["portfolio", "allocation"],
        portfolioAccountDividends: (id: number) => ["portfolio", "account", id, "dividends"],
        portfolioDividendHistory: (id: number) => ["portfolio", "account", id, "dividend-history"],
        portfolioAccountTransactionsFiltered: (id: number, filter: string) => ["portfolio", "account", id, "transactions", filter],
    },
}));

// ── Mock hooks ─────────────────────────────────────────────────────────
const mockUsePortfolioDashboard = vi.fn();
const mockUsePortfolioAccounts = vi.fn();
const mockUsePortfolioOverview = vi.fn();
const mockUsePortfolioPerformance = vi.fn();
const mockUseBenchmarkCompare = vi.fn();
const mockUseBenchmarks = vi.fn();
const mockUseAccountHoldings = vi.fn();
const mockUseAccountDividends = vi.fn();
const mockUseDividendHistory = vi.fn();
const mockUseAccountTransactionsFiltered = vi.fn();
const mockUsePortfolioAllocation = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    usePortfolioAccounts: (...args: any[]) => mockUsePortfolioAccounts(...args),
    usePortfolioOverview: (...args: any[]) => mockUsePortfolioOverview(...args),
    usePortfolioPerformance: (...args: any[]) => mockUsePortfolioPerformance(...args),
    usePortfolioDashboard: (...args: any[]) => mockUsePortfolioDashboard(...args),
    useBenchmarkCompare: (...args: any[]) => mockUseBenchmarkCompare(...args),
    useBenchmarks: (...args: any[]) => mockUseBenchmarks(...args),
    useAccountHoldings: (...args: any[]) => mockUseAccountHoldings(...args),
    useAccountDividends: (...args: any[]) => mockUseAccountDividends(...args),
    useDividendHistory: (...args: any[]) => mockUseDividendHistory(...args),
    useAccountTransactionsFiltered: (...args: any[]) => mockUseAccountTransactionsFiltered(...args),
    usePortfolioAllocation: (...args: any[]) => mockUsePortfolioAllocation(...args),
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
    useAllHoldings: () => ({ data: [], isLoading: false }),
    useAllDividends: () => ({ data: null, isLoading: false }),
    useAllTransactions: () => ({ data: { transactions: [], total_count: 0 }, isLoading: false }),
    useRiskMetrics: () => ({ data: null, isLoading: false }),
    useDrawdown: () => ({ data: null, isLoading: false }),
    useCovariance: () => ({ data: null, isLoading: false }),
    useEfficientFrontier: () => ({ data: null, isLoading: false }),
    useRollingSharpe: () => ({ data: null, isLoading: false }),
    useRiskContribution: () => ({ data: null, isLoading: false }),
    useMarketExposure: () => ({ data: null, isLoading: false }),
    usePortfolioPerformance: (...args: any[]) => mockUsePortfolioPerformance(...args),
    useHoldingExists: () => ({ data: { held: false }, isLoading: false }),
    useHoldingPerformance: () => ({ data: null, isLoading: false }),
    useHoldingDividends: () => ({ data: [], isLoading: false }),
    useAggregatedHoldings: () => ({ data: [], isLoading: false }),
    useDividendSummary: () => ({ data: null, isLoading: false }),
    useDividendUpcoming: () => ({ data: [], isLoading: false }),
    useDividendHoldings: () => ({ data: [], isLoading: false }),
}));

// ── Mock shared components ─────────────────────────────────────────────
vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", {
            "data-testid": "skeleton",
            className,
        });
    },
}));

vi.mock("@/components/ui/button", () => ({
    Button: ({ children, onClick, className, variant, disabled }: any) => {
        const React = require("react");
        return React.createElement("button", {
            onClick,
            className,
            disabled,
            "data-variant": variant,
        }, children);
    },
}));

vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ children, open }: any) => {
        const React = require("react");
        return open ? React.createElement("div", { "data-testid": "dialog" }, children) : null;
    },
    DialogContent: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "dialog-content" }, children);
    },
    DialogHeader: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "dialog-header" }, children);
    },
    DialogTitle: ({ children }: any) => {
        const React = require("react");
        return React.createElement("h2", null, children);
    },
    DialogDescription: ({ children }: any) => {
        const React = require("react");
        return React.createElement("p", null, children);
    },
}));

vi.mock("@/components/ui/label", () => ({
    Label: ({ children, htmlFor, className }: any) => {
        const React = require("react");
        return React.createElement("label", { htmlFor, className }, children);
    },
}));

let selectOnValueChange: ((value: string) => void) | null = null;

vi.mock("@/components/ui/select", () => {
    const React = require("react");
    return {
        Select: ({ children, value, onValueChange }: any) => {
            selectOnValueChange = onValueChange ?? null;
            return React.createElement("div", { "data-testid": "select" }, children);
        },
        SelectTrigger: ({ children, id, className, disabled }: any) => {
            return React.createElement("button", { id, className, disabled, "data-testid": "select-trigger" }, children);
        },
        SelectValue: ({ placeholder }: any) => {
            return React.createElement("span", null, placeholder);
        },
        SelectContent: ({ children }: any) => {
            return React.createElement("div", null, children);
        },
        SelectItem: ({ children, value }: any) => {
            return React.createElement(
                "button",
                { value, onClick: () => selectOnValueChange?.(value) },
                children
            );
        },
    };
});

vi.mock("@/components/ui/checkbox", () => ({
    Checkbox: ({ id, checked, onCheckedChange, className }: any) => {
        const React = require("react");
        return React.createElement("input", {
            type: "checkbox",
            id,
            checked,
            onChange: () => onCheckedChange?.(!checked),
            className,
            "data-testid": "checkbox",
        });
    },
}));

vi.mock("@/components/ui/alert", () => ({
    Alert: ({ children, className }: any) => {
        const React = require("react");
        return React.createElement("div", { className, "data-testid": "alert" }, children);
    },
    AlertTitle: ({ children }: any) => {
        const React = require("react");
        return React.createElement("h4", null, children);
    },
    AlertDescription: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", null, children);
    },
}));

vi.mock("@/components/ui/input", () => ({
    Input: ({ id, type, value, onChange, className, placeholder, max, maxLength, step }: any) => {
        const React = require("react");
        return React.createElement("input", { id, type, value, onChange, className, placeholder, max, maxLength, step, "data-testid": "input" });
    },
}));

vi.mock("@/components/ui/textarea", () => ({
    Textarea: ({ id, value, onChange, className, placeholder, maxLength }: any) => {
        const React = require("react");
        return React.createElement("textarea", { id, value, onChange, className, placeholder, maxLength, "data-testid": "textarea" });
    },
}));

// ── Components under test ──────────────────────────────────────────────
import { TabBar } from "@/features/portfolio/components/TabBar";
import { AccountNavDropdown } from "@/features/portfolio/components/AccountNavDropdown";
import { PortfolioTabShell } from "@/features/portfolio/components/PortfolioTabShell";

// ── Factory helpers ────────────────────────────────────────────────────
function makeMockAccounts() {
    return [
        { account_id: 1, account_name: "TFSA", account_type: "TFSA", brokerage_name: "Test", total_value: 50000, is_active: true },
        { account_id: 2, account_name: "RRSP", account_type: "RRSP", brokerage_name: "Test", total_value: 30000, is_active: true },
    ];
}

function makeMockSearchParams(params: Record<string, string> = {}) {
    return new URLSearchParams(params);
}

// ═══════════════════════════════════════════════════════════════════════
// TAB NAVIGATION TESTS
// ═══════════════════════════════════════════════════════════════════════

describe("TabBar — FT-TAB-01 to FT-TAB-04", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("FT-TAB-01: renders all 4 tab buttons", () => {
        render(<TabBar activeTab="overview" onTabChange={vi.fn()} />);
        expect(screen.getByText("Overview")).toBeInTheDocument();
        expect(screen.getByText("Dividends")).toBeInTheDocument();
        expect(screen.getByText("Transaction")).toBeInTheDocument();
        expect(screen.getByText("Risk")).toBeInTheDocument();
    });

    it("FT-TAB-02: active tab has blue highlight class", () => {
        const { container } = render(<TabBar activeTab="overview" onTabChange={vi.fn()} />);
        const activeBtn = container.querySelector("button.text-blue-400");
        expect(activeBtn).toBeTruthy();
        expect(activeBtn?.textContent).toMatch(/Overview/);
    });

    it("FT-TAB-03: clicking tab calls onTabChange with correct id", () => {
        const onTabChange = vi.fn();
        render(<TabBar activeTab="overview" onTabChange={onTabChange} />);
        fireEvent.click(screen.getByText("Risk"));
        expect(onTabChange).toHaveBeenCalledWith("risk");
    });

    it("FT-TAB-04: hides Transaction tab when showTransactions=false", () => {
        render(<TabBar activeTab="overview" onTabChange={vi.fn()} showTransactions={false} />);
        expect(screen.queryByText("Transaction")).not.toBeInTheDocument();
    });
});

// ═══════════════════════════════════════════════════════════════════════
// ACCOUNT CHIP STRIP TESTS
// ═══════════════════════════════════════════════════════════════════════

describe("AccountNavDropdown — FT-DROPDOWN-01 to FT-DROPDOWN-03", () => {
    const accounts = makeMockAccounts();

    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("FT-DROPDOWN-01: renders All Accounts plus one item per account", () => {
        render(
            <AccountNavDropdown
                accounts={accounts}
                selectedAccountId={null}
                onSelect={vi.fn()}
            />
        );
        const allAccounts = screen.getAllByText("All Accounts");
        expect(allAccounts.length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("TFSA (TFSA)")).toBeInTheDocument();
        expect(screen.getByText("RRSP (RRSP)")).toBeInTheDocument();
    });

    it("FT-DROPDOWN-02: selecting account calls onSelect with account_id", () => {
        const onSelect = vi.fn();
        render(
            <AccountNavDropdown
                accounts={accounts}
                selectedAccountId={null}
                onSelect={onSelect}
            />
        );
        fireEvent.click(screen.getByText("TFSA (TFSA)"));
        expect(onSelect).toHaveBeenCalledWith(1);
    });

    it("FT-DROPDOWN-03: selecting All Accounts calls onSelect with null", () => {
        const onSelect = vi.fn();
        render(
            <AccountNavDropdown
                accounts={accounts}
                selectedAccountId={1}
                onSelect={onSelect}
            />
        );
        fireEvent.click(screen.getByText("All Accounts"));
        expect(onSelect).toHaveBeenCalledWith(null);
    });
});

// ═══════════════════════════════════════════════════════════════════════
// PORTFOLIO TAB SHELL INTEGRATION TESTS
// ═══════════════════════════════════════════════════════════════════════

describe("PortfolioTabShell — FT-SHELL-01 to FT-SHELL-04", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseSearchParams.mockReturnValue(makeMockSearchParams());
        mockUseRouter.mockReturnValue({ replace: mockReplace });
        mockUsePortfolioDashboard.mockReturnValue({
            data: { accounts: makeMockAccounts() },
            isLoading: false,
        });
        mockUsePortfolioAccounts.mockReturnValue({
            data: makeMockAccounts(),
            isLoading: false,
        });
        mockUsePortfolioOverview.mockReturnValue({
            data: {
                success: true,
                net_worth: 80000,
                total_cost_basis: 60000,
                total_gain_loss: 20000,
                total_gain_loss_pct: 33.33,
                ytd_dividends: 1500,
                total_holdings_count: 5,
                accounts_count: 2,
                top_holdings: [],
                account_breakdown: [
                    { account_id: 1, account_name: "TFSA", total_value: 50000, total_cost: 40000, gain_loss: 10000, gain_loss_pct: 25, holdings_count: 3 },
                    { account_id: 2, account_name: "RRSP", total_value: 30000, total_cost: 20000, gain_loss: 10000, gain_loss_pct: 50, holdings_count: 2 },
                ],
            },
            isLoading: false,
        });
        mockUsePortfolioPerformance.mockReturnValue({
            data: { success: true, period: "1Y", monthly_breakdown: [], snapshots: [] },
            isLoading: false,
        });
        mockUseBenchmarkCompare.mockReturnValue({
            data: null,
            isLoading: false,
        });
        mockUseBenchmarks.mockReturnValue({
            data: [],
            isLoading: false,
        });
        mockUseAccountHoldings.mockReturnValue({ data: [], isLoading: false });
        mockUseAccountDividends.mockReturnValue({ data: { monthly_summaries: [] }, isLoading: false });
        mockUseDividendHistory.mockReturnValue({ data: { dividends: [] }, isLoading: false });
        mockUseAccountTransactionsFiltered.mockReturnValue({ data: { transactions: [] }, isLoading: false });
        mockUsePortfolioAllocation.mockReturnValue({ data: { segments: [] }, isLoading: false });
    });

    it("FT-SHELL-01: renders account chips and tab bar on load", () => {
        render(<PortfolioTabShell />);
        const chips = screen.getAllByText("All Accounts");
        expect(chips.length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("Overview")).toBeInTheDocument();
    });

    it("FT-SHELL-02: renders Risk tab content", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "risk" }));
        render(<PortfolioTabShell />);
        expect(screen.getByText("Portfolio Risk Analytics")).toBeInTheDocument();
    });

    it("FT-SHELL-03: shows loading skeleton while accounts load", () => {
        mockUsePortfolioDashboard.mockReturnValue({
            data: null,
            isLoading: true,
        });
        const { container } = render(<PortfolioTabShell />);
        const skeletons = container.querySelectorAll("[data-testid='skeleton']");
        expect(skeletons.length).toBeGreaterThanOrEqual(1);
    });

    it("FT-SHELL-04: renders overview allocation content", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "overview" }));
        mockUsePortfolioAllocation.mockReturnValue({
            data: {
                success: true,
                group_by: "sector",
                segments: [
                    { segment: "Technology", value: 50000, weight: 62.5, count: 2, gain_loss: 10000 },
                    { segment: "Energy", value: 30000, weight: 37.5, count: 1, gain_loss: -2000 },
                ],
                types: [
                    {
                        type: "stock",
                        type_label: "Stocks",
                        value: 80000,
                        weight: 100.0,
                        count: 3,
                        gain_loss: 8000,
                        sectors: [
                            { segment: "Technology", value: 50000, weight: 62.5, count: 2, gain_loss: 10000 },
                            { segment: "Energy", value: 30000, weight: 37.5, count: 1, gain_loss: -2000 },
                        ],
                    },
                ],
                total_value: 80000,
            },
            isLoading: false,
        });
        render(<PortfolioTabShell />);
        expect(screen.getByText("Stocks")).toBeInTheDocument();
        expect(screen.getByText("Technology")).toBeInTheDocument();
        expect(screen.getByText("Energy")).toBeInTheDocument();
    });

    it("FT-SHELL-05: renders Risk tab when tab=risk", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "risk" }));
        mockUsePortfolioDashboard.mockReturnValue({
            data: { accounts: [] },
            isLoading: false,
        });
        render(<PortfolioTabShell />);
        expect(screen.getByText("Portfolio Risk Analytics")).toBeInTheDocument();
    });

    it("FT-SHELL-06: renders Dividends tab placeholder when no account selected", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "dividends" }));
        mockUsePortfolioDashboard.mockReturnValue({
            data: { accounts: [] },
            isLoading: false,
        });
        render(<PortfolioTabShell />);
        expect(screen.getByText("Dividend Dashboard")).toBeInTheDocument();
    });

    it("FT-SHELL-07: renders Transactions tab placeholder when no account selected", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "transactions" }));
        mockUsePortfolioDashboard.mockReturnValue({
            data: { accounts: [] },
            isLoading: false,
        });
        render(<PortfolioTabShell />);
        expect(screen.getByText("No transactions found matching filters")).toBeInTheDocument();
    });

    it("FT-SHELL-08: overview shows empty allocation state when no segments", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "overview" }));
        mockUsePortfolioAllocation.mockReturnValue({
            data: { success: true, group_by: "sector", segments: [], total_value: 0 },
            isLoading: false,
        });
        render(<PortfolioTabShell />);
        expect(screen.getByText(/No allocation data available/)).toBeInTheDocument();
    });

    it("FT-SHELL-09: clicking a tab in shell updates URL", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({}));
        render(<PortfolioTabShell />);
        fireEvent.click(screen.getByText("Risk"));
        expect(mockReplace).toHaveBeenCalledWith("?tab=risk", { scroll: false });
    });

    it("FT-SHELL-10: selecting account in shell updates URL", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({}));
        render(<PortfolioTabShell />);
        fireEvent.click(screen.getByText("TFSA (TFSA)"));
        expect(mockReplace).toHaveBeenCalledWith("?account=1", { scroll: false });
    });

    it("FT-SHELL-11: overview tab shows summary cards with correct values", () => {
        mockUseSearchParams.mockReturnValue(makeMockSearchParams({ tab: "overview" }));
        render(<PortfolioTabShell />);
        expect(screen.getByText("Total Value")).toBeInTheDocument();
        expect(screen.getByText("Total Gain/Loss")).toBeInTheDocument();
        expect(screen.getByText("Total Dividends")).toBeInTheDocument();
        expect(screen.getByText("$80,000.00")).toBeInTheDocument();
    });

    // ═══════════════════════════════════════════════════════════════════════
    // IMPORT / MANUAL BUTTON TESTS (restored features)
    // ═══════════════════════════════════════════════════════════════════════

    it("FT-SHELL-12: renders Import CSV button in shell header", () => {
        render(<PortfolioTabShell />);
        expect(screen.getByText("Import CSV")).toBeInTheDocument();
    });

    it("FT-SHELL-13: renders Add Trade button in shell header", () => {
        render(<PortfolioTabShell />);
        expect(screen.getByText("Add Trade")).toBeInTheDocument();
    });

    it("FT-SHELL-14: clicking Import CSV button opens import modal", () => {
        render(<PortfolioTabShell />);
        fireEvent.click(screen.getByText("Import CSV"));
        expect(screen.getByText("Import Transactions")).toBeInTheDocument();
    });

    it("FT-SHELL-15: clicking Add Trade button opens manual trade form", () => {
        render(<PortfolioTabShell />);
        fireEvent.click(screen.getByText("Add Trade"));
        expect(screen.getAllByText("Add Transaction")).toHaveLength(2);
    });
});
