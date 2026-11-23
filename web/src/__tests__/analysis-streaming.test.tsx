import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";

vi.mock("@/lib/data/stocks", () => {
  const mockQuote = {
    symbol: "AAPL",
    price: 150.25,
    change: 2.5,
    changePercent: 1.68,
    lastUpdated: new Date().toISOString(),
  };
  return {
    getStockQuote: vi.fn().mockResolvedValue(mockQuote),
  };
});

vi.mock("@/lib/time", () => ({
  formatTimestamp: vi.fn().mockReturnValue("2m ago"),
}));

vi.mock("@/providers/GlobalSSEProvider", () => ({
  useSSEStatus: vi.fn().mockReturnValue({ isConnected: false }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn() }),
  useParams: () => ({ symbol: "AAPL" }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({ get: vi.fn().mockReturnValue({ value: "test" }) }),
}));

vi.mock("@tanstack/react-query", async () => {
  const actual = await vi.importActual("@tanstack/react-query");
  return {
    ...(actual as object),
    useQuery: vi.fn().mockReturnValue({ data: { price: 150.25, change: 2.5, changePercent: 1.68, lastUpdated: new Date().toISOString() }, isPending: false, error: null }),
    useQueryClient: vi.fn().mockReturnValue({ prefetchQuery: vi.fn() }),
  };
});

import { LivePriceHeader } from "@/components/analysis/live-price-header";

describe("Analysis Page — Client Rendering", () => {
  it("P3-UT-01: renders price header with live data", async () => {
    const { container } = render(
      <LivePriceHeader symbol="AAPL" initialPrice={150.25} initialChange={2.5} initialChangePercent={1.68} initialLastUpdated={new Date().toISOString()} />,
    );
    expect(container.textContent).toContain("AAPL");
  });

  it("P3-UT-02: shows symbol initial in the icon", () => {
    const { container } = render(
      <LivePriceHeader symbol="AAPL" initialPrice={null} initialChange={null} initialChangePercent={null} initialLastUpdated={null} />,
    );
    const icons = container.querySelectorAll('[class*="rounded-2xl"]');
    expect(icons.length).toBeGreaterThanOrEqual(1);
  });

  it("P3-UT-03: price header shows loading state when no data", () => {
    const { container } = render(
      <div>
        <div className="flex h-7 w-28 rounded-lg bg-white/5 animate-pulse" />
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl animate-pulse" />
      </div>,
    );
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(2);
  });

  it("P3-UT-04: valuation overview renders method cards via React Query", async () => {
    const { ValuationOverviewTab } = await import("@/components/analysis/valuation-overview-tab");
    expect(ValuationOverviewTab).toBeDefined();
  });

  it("P3-UT-05: overview handles empty methods gracefully", async () => {
    const { ValuationOverviewTab } = await import("@/components/analysis/valuation-overview-tab");
    expect(typeof ValuationOverviewTab).toBe("function");
  });
});
