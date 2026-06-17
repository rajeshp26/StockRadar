import { describe, it, expect, vi } from "vitest";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

vi.mock("next/headers", () => ({
  cookies: vi.fn().mockResolvedValue({
    get: vi.fn().mockReturnValue({ value: "test-session" }),
  }),
}));

describe("Analysis Page — Cache Layer", () => {
  it("P3-UT-19: getStockQuote calls correct backend URL", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ symbol: "AAPL", price: 150.25 }),
    });

    const { getStockQuote } = await import("@/lib/data/stocks");
    await getStockQuote("AAPL");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/stocks/AAPL/quote"),
      expect.any(Object),
    );
  });

  it("P3-UT-20: getValuationOverview calls correct backend URL", async () => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ symbol: "AAPL", methods: [] }),
    });

    const { getValuationOverview } = await import("@/lib/data/stocks");
    await getValuationOverview("AAPL");

    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("/valuations/AAPL/overview"),
      expect.any(Object),
    );
  });

  it("P3-UT-21: getIndividualValuation returns 404 result as notComputed", async () => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({}),
    });

    const { getIndividualValuation } = await import("@/lib/data/stocks");
    const result = await getIndividualValuation("AAPL", "dcf");
    expect(result).toEqual({ notComputed: true });
  });

  it("P3-UT-22: getIndividualValuation returns null on server error", async () => {
    mockFetch.mockReset();
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    });

    const { getIndividualValuation } = await import("@/lib/data/stocks");
    const result = await getIndividualValuation("AAPL", "dcf");
    expect(result).toBeNull();
  });

  it("P3-UT-23: getStockQuote returns null on fetch failure", async () => {
    mockFetch.mockReset();
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    const { getStockQuote } = await import("@/lib/data/stocks");
    const result = await getStockQuote("AAPL");
    expect(result).toBeNull();
  });
});
