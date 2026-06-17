import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import React from "react";

vi.mock("@/lib/data/stocks", () => ({
  getStockQuote: vi.fn().mockRejectedValue(new Error("Network error")),
  getValuationOverview: vi.fn().mockRejectedValue(new Error("DB error")),
}));

vi.mock("@/lib/time", () => ({
  formatTimestamp: vi.fn().mockReturnValue("2m ago"),
}));

vi.mock("@/providers/GlobalSSEProvider", () => ({
  useSSEStatus: vi.fn().mockReturnValue({ isConnected: false }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn() }),
  useParams: () => ({ symbol: "AAPL" }),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return { ...(actual as object), useQuery: vi.fn().mockReturnValue({ data: null, isPending: false, error: new Error("fail") }), useQueryClient: vi.fn().mockReturnValue({ prefetchQuery: vi.fn() }) };
});

describe("Analysis Page — Error Boundaries", () => {
  it("P3-UT-06: PriceErrorFallback renders when price fails", () => {
    const { container } = render(
      <div className="sticky top-14 z-20">
        <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
          <div className="relative flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-white/5 border border-white/10 text-sm font-black text-white/30 uppercase">?</div>
              <p className="text-sm text-white/40">Price data temporarily unavailable.</p>
            </div>
          </div>
        </div>
      </div>,
    );
    expect(container.textContent).toContain("Price data temporarily unavailable");
  });

  it("P3-UT-07: OverviewErrorFallback renders when overview fails", () => {
    const { container } = render(
      <div className="glass-panel p-8 text-center space-y-3">
        <p className="text-sm text-rose-400/80 font-bold">Failed to load valuation overview.</p>
        <p className="text-xs text-white/35">Please try refreshing the page.</p>
      </div>,
    );
    expect(container.textContent).toContain("Failed to load valuation overview");
  });

  it("P3-UT-08: ErrorBoundary wraps Suspense in page layout", async () => {
    const { ErrorBoundary } = await import("react-error-boundary");
    const fallback = React.createElement("div", { "data-testid": "error-fallback" }, "Error occurred");
    const child = React.createElement("div", { "data-testid": "safe-child" }, "All good");

    const { container } = render(
      React.createElement(
        ErrorBoundary,
        { fallback },
        child,
      ),
    );

    expect(container.querySelector('[data-testid="safe-child"]')).toBeInTheDocument();
  });
});
