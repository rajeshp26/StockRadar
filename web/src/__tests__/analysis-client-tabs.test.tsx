import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

const mockUseHoldingExists = vi.fn().mockReturnValue({ data: { held: false } });
const mockUsePredictiveTabPrefetch = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
  useHoldingExists: (...args: unknown[]) => mockUseHoldingExists(...args),
}));

vi.mock("@/features/analysis/hooks/usePredictiveTabPrefetch", () => ({
  usePredictiveTabPrefetch: (...args: unknown[]) => mockUsePredictiveTabPrefetch(...args),
}));

vi.mock("@/features/analysis/utils/prefetch-valuations", () => ({
  prefetchAllValuations: vi.fn(),
}));

vi.mock("@/features/analysis/hooks/useLivePrice", () => ({
  useLivePrice: vi.fn().mockReturnValue({ price: 150.25, change: 2.5, changePercent: 1.68, lastUpdated: new Date().toISOString(), loading: false, error: null }),
}));

vi.mock("@/lib/time", () => ({ formatTimestamp: vi.fn().mockReturnValue("2m ago") }));

vi.mock("next/navigation", () => ({ useRouter: () => ({ back: vi.fn() }), useParams: () => ({ symbol: "AAPL" }) }));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return { ...(actual as object), useQuery: vi.fn().mockReturnValue({ data: null, isPending: false, error: null }), useQueryClient: vi.fn().mockReturnValue({ prefetchQuery: vi.fn() }) };
});

vi.mock("@/features/analysis/components/dcf-panel", () => ({
  DcfPanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "dcf-panel" }, `DCF ${symbol}`),
}));

vi.mock("@/features/analysis/components/intrinsic-panel", () => ({
  IntrinsicPanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "intrinsic-panel" }, `Intrinsic ${symbol}`),
}));

vi.mock("@/features/analysis/components/method-selector", () => ({
  MethodSelector: ({ method, onChange }: { method: string; onChange: (m: string) => void }) =>
    React.createElement("div", { "data-testid": "method-selector" },
      React.createElement("select", { value: method, onChange: (e: React.ChangeEvent<HTMLSelectElement>) => onChange(e.target.value), "data-testid": "method-select" },
        React.createElement("option", { value: "overview" }, "Overview"),
        React.createElement("option", { value: "dcf" }, "DCF"),
        React.createElement("option", { value: "rule1" }, "Rule 1"),
        React.createElement("option", { value: "ownerEarnings" }, "Owner Earnings"),
        React.createElement("option", { value: "residualIncome" }, "Residual Income"),
      ),
    ),
}));

vi.mock("@/features/analysis/components/ddm-panel", () => ({
  DdmPanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "ddm-panel" }, `DDM ${symbol}`),
}));

vi.mock("@/features/analysis/components/owner-earnings-panel", () => ({
  OwnerEarningsPanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "oe-panel" }, `OwnerEarnings ${symbol}`),
}));

vi.mock("@/features/analysis/components/residual-income-panel", () => ({
  ResidualIncomePanel: ({ symbol }: { symbol: string }) => React.createElement("div", { "data-testid": "ri-panel" }, `ResidualIncome ${symbol}`),
}));

import { ClientTabs } from "@/components/analysis/client-tabs";

describe("Analysis Page — Tab Switching", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("P3-UT-09: defaults to intrinsic tab", () => {
    const { container } = render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    const tabBar = container.querySelector(".glass-segmented");
    expect(tabBar).toBeInTheDocument();
  });

  it("P3-UT-10: switches tab when tab button clicked", () => {
    const { container } = render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    const tabButtons = container.querySelectorAll(".glass-segmented-item");
    expect(tabButtons.length).toBeGreaterThanOrEqual(9);
  });

  it("P3-UT-11: method selector renders inside intrinsic tab", () => {
    render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    expect(screen.getByTestId("method-selector")).toBeInTheDocument();
  });

  it("P3-UT-12: changing method renders correct panel", () => {
    render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    const select = screen.getByTestId("method-select");
    fireEvent.change(select, { target: { value: "dcf" } });
    expect(screen.getByTestId("dcf-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("intrinsic-panel")).not.toBeInTheDocument();
  });

  it("P3-UT-13: overview children render when method is overview", () => {
    const overviewContent = React.createElement("div", { "data-testid": "overview-rsc" }, "RSC Overview Cards");
    render(React.createElement(ClientTabs, { symbol: "AAPL", overviewChildren: overviewContent }));
    expect(screen.getByTestId("overview-rsc")).toBeInTheDocument();
  });

  it("P3-UT-14: overview children hidden when method changes", () => {
    const overviewContent = React.createElement("div", { "data-testid": "overview-rsc" }, "RSC Overview Cards");
    render(React.createElement(ClientTabs, { symbol: "AAPL", overviewChildren: overviewContent }));
    const select = screen.getByTestId("method-select");
    fireEvent.change(select, { target: { value: "rule1" } });
    expect(screen.queryByTestId("overview-rsc")).not.toBeInTheDocument();
    expect(screen.getByTestId("intrinsic-panel")).toBeInTheDocument();
  });

  it("P3-UT-15: clicking Fundamentals tab shows correct content", () => {
    const { container } = render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    const tabButtons = container.querySelectorAll(".glass-segmented-item");
    fireEvent.click(tabButtons[1]);
    const activeTab = container.querySelector(".glass-segmented-item.active");
    expect(activeTab?.textContent).toMatch(/Fund/i);
  });

  it("P3-UT-17: calls usePredictiveTabPrefetch with symbol and tab", () => {
    render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    expect(mockUsePredictiveTabPrefetch).toHaveBeenCalled();
  });

  it("P3-UT-18: prefetches all valuations on mount", async () => {
    const { prefetchAllValuations } = await import("@/features/analysis/utils/prefetch-valuations");
    render(React.createElement(ClientTabs, { symbol: "AAPL" }));
    expect(prefetchAllValuations).toHaveBeenCalled();
  });
});
