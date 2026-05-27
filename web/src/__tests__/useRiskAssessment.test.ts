import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

const mockFetchRiskCached = vi.fn();
const mockFetchRiskAssessment = vi.fn();
const mockFetchRiskAiNarrative = vi.fn();

vi.mock("@/features/analysis/services/analysis.service", () => ({
  fetchRiskCached: (...args: any[]) => mockFetchRiskCached(...args),
  fetchRiskAssessment: (...args: any[]) => mockFetchRiskAssessment(...args),
  fetchRiskAiNarrative: (...args: any[]) => mockFetchRiskAiNarrative(...args),
}));

const mockQueryKey = vi.fn();
vi.mock("@/lib/query-keys", () => ({
  QK: {
    riskAssessment: (symbol: string) => mockQueryKey(symbol),
  },
}));

const mockUseQuery = vi.fn();
const mockSetQueryData = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: any[]) => mockUseQuery(...args),
  useQueryClient: () => ({
    setQueryData: mockSetQueryData,
    getQueryData: vi.fn(),
  }),
}));

import { useRiskAssessment, riskQueryFn } from "@/features/analysis/hooks/useRiskAssessment";

function makeRiskPayload(overrides = {}) {
  return {
    symbol: "AAPL",
    company_id: 1,
    currency: "USD",
    composite: { score: 76, category: "Moderate" as const, maximum_expected_loss_pct: 12.5, bear_case: { eps_growth_assumption: 0.02, exit_pe_ratio: 15, future_value: 165.62, current_price: 200, downside_pct: -0.172 } },
    layers: {},
    data_quality: { data_sources: "db", fallbacks_used: false, last_computed_at: "" },
    ...overrides,
  };
}

describe("useRiskAssessment — UT-FH1 to UT-FH5", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQueryKey.mockReturnValue(["analysis", "risk-assessment", "AAPL"]);
  });

  it("UT-FH1: returns loading state on initial fetch", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: true, error: null });
    const { result } = renderHook(() => useRiskAssessment("AAPL"));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.notComputed).toBe(false);
  });

  it("UT-FH2: returns notComputed on 404", () => {
    mockUseQuery.mockReturnValue({
      data: { notComputed: true },
      isPending: false,
      error: null,
    });
    const { result } = renderHook(() => useRiskAssessment("AAPL"));
    expect(result.current.notComputed).toBe(true);
    expect(result.current.data).toBeNull();
  });

  it("UT-FH3: returns parsed data on success", () => {
    const payload = makeRiskPayload();
    mockUseQuery.mockReturnValue({
      data: { ...payload, notComputed: false },
      isPending: false,
      error: null,
    });
    const { result } = renderHook(() => useRiskAssessment("AAPL"));
    expect(result.current.notComputed).toBe(false);
    expect(result.current.data).toBeTruthy();
    expect(result.current.data?.composite.score).toBe(76);
  });

  it("UT-FH4: recompute() updates cache", async () => {
    const freshPayload = makeRiskPayload({ composite: { score: 85, category: "Very Low Downside", maximum_expected_loss_pct: 5, bear_case: { eps_growth_assumption: 0.03, exit_pe_ratio: 18, future_value: 200, current_price: 200, downside_pct: -0.05 } } });
    mockFetchRiskAssessment.mockResolvedValue(freshPayload);
    mockUseQuery.mockReturnValue({
      data: { ...makeRiskPayload(), notComputed: false },
      isPending: false,
      error: null,
    });

    const { result } = renderHook(() => useRiskAssessment("AAPL"));
    await result.current.recompute();

    expect(mockFetchRiskAssessment).toHaveBeenCalledWith("AAPL", { force: true });
    expect(mockSetQueryData).toHaveBeenCalledWith(
      ["analysis", "risk-assessment", "AAPL"],
      { ...freshPayload, notComputed: false },
    );
  });

  it("UT-FH5: generateAi() patches AI narrative into cache", async () => {
    mockFetchRiskAiNarrative.mockResolvedValue({ narrative: "AI summary text", model: "openrouter/default" });
    const existingData = { ...makeRiskPayload(), ai_narrative: null, notComputed: false };
    mockUseQuery.mockReturnValue({
      data: existingData,
      isPending: false,
      error: null,
    });

    const { result } = renderHook(() => useRiskAssessment("AAPL"));
    await result.current.generateAi();

    expect(mockFetchRiskAiNarrative).toHaveBeenCalledWith("AAPL");
    expect(mockSetQueryData).toHaveBeenCalledWith(
      ["analysis", "risk-assessment", "AAPL"],
      expect.any(Function),
    );
  });
});
