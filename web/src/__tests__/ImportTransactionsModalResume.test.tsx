import { beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const state = vi.hoisted(() => ({
    importResult: null as any,
    status: { status: "completed", rows_inserted: 0, total_rows: 2 } as any,
    mutateAsync: vi.fn(),
    toast: vi.fn(),
}));

vi.mock("@/shared/contexts/ServiceContext", () => ({
    useServices: () => ({
        portfolioService: {
            api: { get: vi.fn(), post: vi.fn() },
            fileToBase64: vi.fn().mockResolvedValue("base64content"),
            getBrokerages: vi.fn().mockResolvedValue([]),
            getImportStatus: vi.fn(),
            importTransactions: vi.fn(),
        },
        watchlistService: {},
    }),
}));

vi.mock("@/hooks/use-toast", () => ({ useToast: () => ({ toast: state.toast }) }));

vi.mock("@tanstack/react-query", () => ({
    useMutation: vi.fn(),
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
    useQuery: () => ({ data: [], isLoading: false }),
}));

vi.mock("@/lib/query-keys", () => ({
    QK: {
        portfolioOverview: () => ["portfolio", "overview"],
        portfolioAccounts: () => ["portfolio", "accounts"],
        portfolioHoldings: () => ["portfolio", "holdings"],
        portfolioBrokerages: () => ["portfolio", "brokerages"],
    },
}));

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    useImportTransactions: () => ({
        mutateAsync: state.mutateAsync,
        mutate: vi.fn(),
        isPending: false,
        isSuccess: state.importResult !== null,
        isError: false,
        data: state.importResult,
        error: null,
        reset: vi.fn(),
    }),
    useBrokerages: () => ({ data: [], isLoading: false }),
    useImportStatus: () => ({ data: state.status, isLoading: false }),
}));

vi.mock("@/components/ui/button", () => ({
    Button: ({ children, onClick, disabled, type }: any) => {
        const React = require("react");
        return React.createElement("button", { onClick, disabled, type }, children);
    },
}));

vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ children, open }: any) => {
        const React = require("react");
        return open ? React.createElement("div", { "data-testid": "dialog" }, children) : null;
    },
    DialogContent: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", null, children);
    },
    DialogHeader: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", null, children);
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
    Label: ({ children, htmlFor }: any) => {
        const React = require("react");
        return React.createElement("label", { htmlFor }, children);
    },
}));

vi.mock("@/components/ui/select", () => ({
    Select: ({ children, onValueChange }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "select", onClick: () => onValueChange?.("wealthsimple") }, children);
    },
    SelectTrigger: ({ children, id, disabled }: any) => {
        const React = require("react");
        return React.createElement("button", { id, disabled }, children);
    },
    SelectValue: ({ placeholder }: any) => {
        const React = require("react");
        return React.createElement("span", null, placeholder);
    },
    SelectContent: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", null, children);
    },
    SelectItem: ({ children, value }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-value": value }, children);
    },
}));

vi.mock("@/components/ui/checkbox", () => ({
    Checkbox: ({ id, checked, onCheckedChange }: any) => {
        const React = require("react");
        return React.createElement("input", {
            type: "checkbox", id, checked,
            onChange: () => onCheckedChange?.(!checked),
        });
    },
}));

vi.mock("@/components/ui/alert", () => ({
    Alert: ({ children }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "alert" }, children);
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

vi.mock("lucide-react", () => {
    const React = require("react");
    const icon = () => React.createElement("svg");
    return {
        Upload: icon, AlertCircle: icon, CheckCircle2: icon, Loader2: icon, AlertTriangle: icon,
    };
});

vi.mock("@/lib/utils", () => ({ cn: (...parts: any[]) => parts.filter(Boolean).join(" ") }));

import { ImportTransactionsModal } from "@/features/portfolio/components/ImportTransactionsModal";

describe("ImportTransactionsModal resume behaviour", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        state.importResult = null;
        state.status = { status: "completed", rows_inserted: 0, total_rows: 2 };
        state.mutateAsync.mockImplementation(async () => {
            state.importResult = {
                success: true,
                import_batch_id: "dup-batch",
                duplicate_import: true,
                warning: "This CSV has already been imported; only new rows will be added.",
            };
            return state.importResult;
        });
    });

    it("allows a previously imported CSV to be uploaded again to resume", async () => {
        render(<ImportTransactionsModal open={true} onOpenChange={vi.fn()} />);

        fireEvent.click(screen.getByTestId("select"));
        const input = document.getElementById("csv-file") as HTMLInputElement;
        fireEvent.change(input, {
            target: { files: [new File(["date\n2026-01-01"], "activities.csv", { type: "text/csv" })] },
        });

        fireEvent.click(screen.getByText("Import"));
        await waitFor(() => expect(screen.getByText("Duplicate Import Detected")).toBeInTheDocument());
        expect(screen.getByText(/only new rows will be added/)).toBeInTheDocument();

        const importButton = screen.getByText("Import").closest("button");
        expect(importButton).not.toBeDisabled();
    });

    it("shows the backend error when the queue request is rejected", async () => {
        state.importResult = {
            success: false,
            error: "Unsupported brokerage: WS_TRADE",
        };
        state.status = null;

        render(<ImportTransactionsModal open={true} onOpenChange={vi.fn()} />);

        expect(screen.getByText("Import Failed")).toBeInTheDocument();
        expect(screen.getByText(/Reason: Unsupported brokerage: WS_TRADE/)).toBeInTheDocument();
        expect(screen.queryByText("An error occurred during import")).not.toBeInTheDocument();
    });

    it("reports an exact re-upload as already up to date, not as zero imported", () => {
        state.status = {
            status: "completed",
            total_rows: 2488,
            rows_parsed: 2463,
            rows_inserted: 0,
            result: {
                new_entries: 0,
                already_imported: 2463,
                skipped_rows: 25,
                accounts_created: 0,
                accounts_updated: 4,
                symbols_created: 0,
            },
        };

        render(<ImportTransactionsModal open={true} onOpenChange={vi.fn()} />);

        expect(screen.getByText("Nothing New to Import")).toBeInTheDocument();
        expect(screen.getByText(/2,463 rows already imported/)).toBeInTheDocument();
        expect(screen.getByText(/25 rows skipped/)).toBeInTheDocument();
        expect(screen.getByText(/already up to date/)).toBeInTheDocument();
        expect(screen.queryByText("0 transactions imported")).not.toBeInTheDocument();
        expect(state.toast).toHaveBeenCalledWith(expect.objectContaining({
            title: "Already Up to Date",
        }));
    });

    it("summarises new, duplicate and skipped rows on a successful import", () => {
        state.status = {
            status: "completed",
            total_rows: 100,
            rows_parsed: 95,
            rows_inserted: 3,
            result: {
                new_entries: 3,
                already_imported: 92,
                skipped_rows: 5,
                accounts_created: 1,
                accounts_updated: 4,
                symbols_created: 2,
            },
        };

        render(<ImportTransactionsModal open={true} onOpenChange={vi.fn()} />);

        expect(screen.getByText("Import Successful")).toBeInTheDocument();
        expect(screen.getByText("3 new transactions added")).toBeInTheDocument();
        expect(screen.getByText("92 rows already imported — skipped")).toBeInTheDocument();
        expect(screen.getByText(/5 rows skipped/)).toBeInTheDocument();
        expect(screen.getByText(/1 new account created/)).toBeInTheDocument();
        expect(screen.getByText(/2 new companies created/)).toBeInTheDocument();
        expect(state.toast).toHaveBeenCalledWith(expect.objectContaining({
            title: "Import Successful",
            description: "3 new transactions added · 92 rows already imported · 5 rows skipped",
        }));
    });
});
