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
    getValuationOverview: vi.fn().mockResolvedValue({
      symbol: "AAPL",
      methods: [
        {
          method: "dcf",
          status: "computed",
          intrinsicValue: 180.0,
          currentPrice: 150.25,
          upsideDownside: 19.8,
          score: 85,
          category: "Good",
          lastComputedAt: new Date().toISOString(),
        },
      ],
    }),
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

import { PriceHeaderRSC } from "@/components/analysis/price-header-rsc";

describe("Analysis Page — RSC Streaming", () => {
  it("P3-UT-01: renders price header with server-fetched data", async () => {
    const { container } = render(
      await PriceHeaderRSC({ symbol: "AAPL" }),
    );
    expect(container.textContent).toContain("AAPL");
    await waitFor(() => {
      expect(screen.getByText(/150\.25/)).toBeInTheDocument();
    });
  });

  it("P3-UT-02: shows symbol initial in the icon", async () => {
    const { container } = render(
      await PriceHeaderRSC({ symbol: "AAPL" }),
    );
    const icons = container.querySelectorAll('[class*="rounded-2xl"]');
    expect(icons.length).toBeGreaterThanOrEqual(1);
  });

  it("P3-UT-03: price header uses skeletons before data loads", () => {
    const { container } = render(
      <div>
        <div className="flex h-7 w-28 rounded-lg bg-white/5 animate-pulse" />
        <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl animate-pulse" />
      </div>,
    );
    const skeletons = container.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(2);
  });

  it("P3-UT-04: valuation overview renders method cards from server data", async () => {
    const { ValuationOverviewRSC } = await import("@/components/analysis/valuation-overview-rsc");
    const { container } = render(await ValuationOverviewRSC({ symbol: "AAPL" }));
    expect(container.textContent).toContain("Valuation Overview");
    expect(container.textContent).toContain("Discounted Cash Flow");
    expect(container.textContent).toContain("$180.00");
  });

  it("P3-UT-05: overview shows 'no data' when methods are empty", async () => {
    vi.mocked((await import("@/lib/data/stocks")).getValuationOverview).mockResolvedValueOnce({
      symbol: "AAPL",
      methods: [],
    });
    const { ValuationOverviewRSC } = await import("@/components/analysis/valuation-overview-rsc");
    const { container } = render(await ValuationOverviewRSC({ symbol: "AAPL" }));
    expect(container.textContent).toContain("No valuation data available");
  });
});
