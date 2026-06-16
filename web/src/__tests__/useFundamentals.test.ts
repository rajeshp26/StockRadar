import { describe, it, expect, vi } from "vitest";
import { renderHook } from "@testing-library/react";

const mockFetchFundamentals = vi.fn();

vi.mock("@/features/analysis/services/analysis.service", () => ({
  fetchFundamentals: (...args: any[]) => mockFetchFundamentals(...args),
}));

const mockUseQuery = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQuery: (...args: any[]) => mockUseQuery(...args),
  useQueryClient: () => ({ setQueryData: vi.fn(), getQueryData: vi.fn() }),
}));

import { useFundamentals } from "@/features/analysis/hooks/useFundamentals";

function makeResponse(overrides = {}) {
  return {
    success: true,
    symbol: "AAPL",
    company_name: "Apple Inc.",
    currency: "USD",
    composite_score: 72,
    has_portfolio_position: true,
    purchase_date: "2020-06-15",
    purchase_period: "2020-06",
    quarters: ["Q1 2023", "Q2 2023", "Q3 2023", "Q4 2023"],
    buy_quarter_index: 1,
    sections: [
      {
        section_id: "quality",
        title: "Quality metrics",
        metrics: [
          { metric_id: "roic", label: "ROIC", unit: "%", quarters: [{ fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 0.18 }], buy_quarter_index: null, trend_direction: "up", change_pct: null, change_label: "stable" },
          { metric_id: "roe", label: "ROE", unit: "%", quarters: [{ fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 0.25 }], buy_quarter_index: null, trend_direction: "up", change_pct: null, change_label: "stable" },
        ],
        status: { label: "Intact" },
        score: 80,
      },
      {
        section_id: "growth",
        title: "Growth metrics",
        metrics: [
          { metric_id: "revenue_yoy", label: "Revenue YoY", unit: "%", quarters: [{ fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 12.0 }], buy_quarter_index: null, trend_direction: "up", change_pct: null, change_label: "stable" },
        ],
        status: { label: "Watch" },
        score: 65,
      },
      {
        section_id: "financial_health",
        title: "Financial Health",
        metrics: [
          { metric_id: "piotroski_f", label: "Piotroski F", unit: "score", quarters: [{ fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 7 }], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "stable" },
        ],
        status: { label: "Intact" },
        score: 70,
      },
      {
        section_id: "valuation",
        title: "Valuation",
        metrics: [
          { metric_id: "pe_ratio", label: "P/E", unit: "x", quarters: [{ fiscal_year: 0, fiscal_quarter: 0, label: "Current", value: 15.2 }], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "current snapshot" },
        ],
        status: { label: "Watch" },
        score: 55,
      },
      {
        section_id: "narrative",
        title: "Narrative",
        metrics: [
          { metric_id: "eps_surprise", label: "EPS surprise", unit: "%", quarters: [{ fiscal_year: 2024, fiscal_quarter: 1, label: "Q1 2024", value: 3.5, narrative_label: "beat" }], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "beat/miss" },
        ],
        status: { label: "Intact" },
        score: 72,
      },
    ],
    data_quality: { sources: ["financial_ratios", "income_statements"], staleness_days: null, earliest_data_year: 2018, quarterly_data_count: 4 },
    error: null,
    ...overrides,
  };
}

describe("useFundamentals", () => {
  it("returns loading state on initial fetch", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: true, error: null });
    const { result } = renderHook(() => useFundamentals("AAPL"));
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it("returns parsed data on success", () => {
    const payload = makeResponse();
    mockUseQuery.mockReturnValue({ data: payload, isPending: false, error: null });
    const { result } = renderHook(() => useFundamentals("AAPL"));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeTruthy();
    expect(result.current.data!.composite_score).toBe(72);
    expect(result.current.data!.has_portfolio_position).toBe(true);
    expect(result.current.data!.sections[0].score).toBe(80);
    expect(result.current.data!.sections[3].metrics[0].quarters[0].value).toBe(15.2);
    expect(result.current.data!.sections[4].metrics[0].quarters[0].narrative_label).toBe("beat");
    expect(result.current.data!.quarters.length).toBe(4);
    expect(result.current.data!.buy_quarter_index).toBe(1);
  });

  it("returns error state on failure", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: false, error: new Error("Network error") });
    const { result } = renderHook(() => useFundamentals("AAPL"));
    expect(result.current.loading).toBe(false);
    expect(result.current.data).toBeNull();
    expect(result.current.error).toBe("Network error");
  });

  it("handles API-level error in response", () => {
    mockUseQuery.mockReturnValue({
      data: makeResponse({ success: false, error: "Company not found" }),
      isPending: false,
      error: null,
    });
    const { result } = renderHook(() => useFundamentals("AAPL"));
    expect(result.current.error).toBe("Company not found");
  });

  it("handles empty symbol (disabled query)", () => {
    mockUseQuery.mockReturnValue({ data: undefined, isPending: false, error: null });
    const { result } = renderHook(() => useFundamentals(""));
    expect(result.current.data).toBeNull();
    expect(result.current.loading).toBe(false);
  });
});
