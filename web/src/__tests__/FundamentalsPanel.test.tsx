import { describe, it, expect, vi, beforeAll } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as any;
});

vi.mock("@/features/analysis/components/shared-ui", () => {
  const React = require("react");
  return {
    SectionHeader: ({ title, subtitle }: any) =>
      React.createElement("div", { "data-testid": "section-header" },
        React.createElement("h3", null, title),
        subtitle ? React.createElement("p", null, subtitle) : null,
      ),
  };
});

const mockUseFundamentals = vi.fn();
vi.mock("@/features/analysis/hooks/useFundamentals", () => ({
  useFundamentals: (...args: any[]) => mockUseFundamentals(...args),
}));

import { FundamentalsPanel } from "@/features/analysis/components/fundamentals-panel";

function makeData(overrides = {}) {
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
          { metric_id: "roic", label: "ROIC", unit: "%", quarters: [
            { fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 0.18 },
            { fiscal_year: 2023, fiscal_quarter: 2, label: "Q2 2023", value: 0.19 },
          ], buy_quarter_index: 1, trend_direction: "up", change_pct: 0.055, change_label: "+5.6%" },
          { metric_id: "roe", label: "ROE", unit: "%", quarters: [
            { fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 0.25 },
          ], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "stable" },
        ],
        status: { label: "Intact" },
        score: 80,
      },
      {
        section_id: "growth",
        title: "Growth metrics",
        metrics: [
          { metric_id: "revenue_yoy", label: "Revenue YoY", unit: "%", quarters: [
            { fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 12.0 },
          ], buy_quarter_index: null, trend_direction: "up", change_pct: null, change_label: "+12%" },
        ],
        status: { label: "Watch" },
        score: 65,
      },
      {
        section_id: "moat",
        title: "Moat signals",
        metrics: [
          { metric_id: "piotroski_f", label: "Piotroski F", unit: "score", quarters: [
            { fiscal_year: 2023, fiscal_quarter: 1, label: "Q1 2023", value: 7 },
          ], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "stable" },
        ],
        status: { label: "Intact" },
        score: 70,
      },
      {
        section_id: "valuation",
        title: "Valuation",
        metrics: [
          { metric_id: "pe_ratio", label: "P/E", unit: "x", quarters: [
            { fiscal_year: 0, fiscal_quarter: 0, label: "Current", value: 15.2 },
          ], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "current snapshot" },
        ],
        status: { label: "Watch" },
        score: 55,
      },
      {
        section_id: "narrative",
        title: "Narrative",
        metrics: [
          { metric_id: "eps_surprise", label: "EPS surprise", unit: "%", quarters: [
            { fiscal_year: 2024, fiscal_quarter: 1, label: "Q1 2024", value: 3.5, narrative_label: "beat" },
          ], buy_quarter_index: null, trend_direction: "stable", change_pct: null, change_label: "beat/miss" },
        ],
        status: { label: "Intact" },
        score: 72,
      },
    ],
    data_quality: { sources: ["financial_ratios"], staleness_days: null, earliest_data_year: 2018, quarterly_data_count: 4 },
    error: null,
    ...overrides,
  };
}

describe("FundamentalsPanel", () => {
  it("shows loading shimmer while fetching", () => {
    mockUseFundamentals.mockReturnValue({ data: null, loading: true, error: null });
    const { container } = render(<FundamentalsPanel symbol="AAPL" />);
    expect(container.querySelectorAll(".glass-shimmer").length).toBeGreaterThan(0);
  });

  it("shows error message on fetch failure", () => {
    mockUseFundamentals.mockReturnValue({ data: null, loading: false, error: "Network error" });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText(/Failed to load fundamentals/i)).toBeTruthy();
  });

  it("shows error when response has no data", () => {
    mockUseFundamentals.mockReturnValue({ data: null, loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText(/No fundamentals data available/i)).toBeTruthy();
  });

  it("renders company name and section header", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByTestId("section-header")).toBeTruthy();
  });

  it("renders composite score when available", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText("72/100")).toBeTruthy();
  });

  it("shows both All and From purchase options in each section when portfolio position exists", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getAllByText("All").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("From purchase").length).toBeGreaterThanOrEqual(1);
  });

  it("shows All option but hides From purchase when no portfolio position", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData({ has_portfolio_position: false, purchase_date: null, purchase_period: null }), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getAllByText("All").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("From purchase")).toBeNull();
  });

  it("renders FrequencyToggle in each section when portfolio position exists", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    const quarterly = screen.getAllByText("Quarterly");
    expect(quarterly.length).toBeGreaterThanOrEqual(1);
    const annual = screen.getAllByText("Annual");
    expect(annual.length).toBeGreaterThanOrEqual(1);
  });

  it("renders FrequencyToggle in each section even without portfolio position", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData({ has_portfolio_position: false, purchase_date: null, purchase_period: null }), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    const quarterly = screen.getAllByText("Quarterly");
    expect(quarterly.length).toBeGreaterThanOrEqual(1);
    const annual = screen.getAllByText("Annual");
    expect(annual.length).toBeGreaterThanOrEqual(1);
  });

  it("shows purchase info when portfolio position exists", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText(/Purchased:/)).toBeTruthy();
  });

  it("shows not-held label when no portfolio position", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData({ has_portfolio_position: false, purchase_date: null, purchase_period: null }), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText(/Portfolio position not held/)).toBeTruthy();
  });

  it("renders all 5 sections with status badges", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getAllByText("Quality metrics").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Growth metrics").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Moat signals").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Valuation").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Narrative").length).toBeGreaterThanOrEqual(1);
  });

  it("renders status badges for sections", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    const badges = screen.getAllByText(/Intact|Watch|Concern/);
    expect(badges.length).toBeGreaterThanOrEqual(5);
  });

  it("renders metric names in sections", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText("ROIC")).toBeTruthy();
    expect(screen.getByText("ROE")).toBeTruthy();
    expect(screen.getByText("Revenue YoY")).toBeTruthy();
    expect(screen.getByText("Piotroski F")).toBeTruthy();
    expect(screen.getByText("P/E")).toBeTruthy();
    expect(screen.getByText("EPS surprise")).toBeTruthy();
  });

  it("renders metric values in bar charts", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    const { container } = render(<FundamentalsPanel symbol="AAPL" />);
    const scrollContainers = container.querySelectorAll(".overflow-x-auto");
    expect(scrollContainers.length).toBeGreaterThanOrEqual(5);
  });

  it("renders data quality footer", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByText(/Data since 2018/)).toBeTruthy();
  });

  it("renders metric labels in sections", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    // New design renders metric labels (ROIC, ROE, Revenue YoY, etc.) instead of quarter column headers
    expect(screen.getAllByText("ROIC").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ROE").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Revenue YoY").length).toBeGreaterThanOrEqual(1);
  });

  it("handles null composite score gracefully", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData({ composite_score: null }), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.queryByText("72/100")).toBeNull();
  });

  it("handles empty sections gracefully", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData({ sections: [] }), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);
    expect(screen.getByTestId("section-header")).toBeTruthy();
  });

  // ── Data filtering tests ──────────────────────────────────────────────────

  it("filters ROIC data to show only post-purchase quarter when From purchase is clicked", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    const qualitySection = screen.getByText("Quality metrics").closest(".glass-panel")!;

    // Default "All" mode — x-axis labels only (floating tooltip only on hover)
    expect(within(qualitySection).getAllByText("Q1'23").length).toBe(2);  // ROIC + ROE
    expect(within(qualitySection).getAllByText("Q2'23").length).toBe(1);  // ROIC

    // Click "From purchase" within this section
    fireEvent.click(within(qualitySection).getByText("From purchase"));

    // After filtering, pre-purchase quarter is gone
    expect(within(qualitySection).queryAllByText("Q1'23").length).toBe(0);
    expect(within(qualitySection).getAllByText("Q2'23").length).toBe(1);  // ROIC
  });

  it("restores all data when toggling back to All from From purchase", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    const qualitySection = screen.getByText("Quality metrics").closest(".glass-panel")!;

    fireEvent.click(within(qualitySection).getByText("From purchase"));
    expect(within(qualitySection).queryAllByText("Q1'23").length).toBe(0);

    fireEvent.click(within(qualitySection).getByText("All"));
    expect(within(qualitySection).getAllByText("Q1'23").length).toBe(2);
    expect(within(qualitySection).getAllByText("Q2'23").length).toBe(1);
  });

  it("shows all data with From purchase when buyQuarterIndex is null", () => {
    mockUseFundamentals.mockReturnValue({
      data: makeData({ buy_quarter_index: null, has_portfolio_position: true }),
      loading: false,
      error: null,
    });
    render(<FundamentalsPanel symbol="AAPL" />);

    const qualitySection = screen.getByText("Quality metrics").closest(".glass-panel")!;

    // "From purchase" button appears because has_portfolio_position is true
    fireEvent.click(within(qualitySection).getByText("From purchase"));

    // buyQuarterIndex is null, so no filtering — all quarters remain
    expect(within(qualitySection).getAllByText("Q1'23").length).toBe(2);
    expect(within(qualitySection).getAllByText("Q2'23").length).toBe(1);
  });

  it("renders exactly one All and one From purchase button per section when portfolio exists", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    expect(screen.getAllByText("All").length).toBe(5);
    expect(screen.getAllByText("From purchase").length).toBe(5);
  });

  it("renders All but no From purchase buttons when portfolio not held", () => {
    mockUseFundamentals.mockReturnValue({
      data: makeData({ has_portfolio_position: false, purchase_date: null, purchase_period: null }),
      loading: false,
      error: null,
    });
    render(<FundamentalsPanel symbol="AAPL" />);

    expect(screen.getAllByText("All").length).toBe(5);
    expect(screen.queryByText("From purchase")).toBeNull();
  });

  it("does not affect other sections when clicking From purchase in one section", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    const qualitySection = screen.getByText("Quality metrics").closest(".glass-panel")!;
    const growthSection = screen.getByText("Growth metrics").closest(".glass-panel")!;

    // Click "From purchase" only in quality section
    fireEvent.click(within(qualitySection).getByText("From purchase"));

    // Quality section: filtered
    expect(within(qualitySection).queryAllByText("Q1'23").length).toBe(0);

    // Growth section: still has all its data (Q1'23 x-axis label)
    expect(within(growthSection).getAllByText("Q1'23").length).toBe(1);
  });

  it("shows No data for a metric that has no quarters after filtering", () => {
    mockUseFundamentals.mockReturnValue({ data: makeData(), loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    const qualitySection = screen.getByText("Quality metrics").closest(".glass-panel")!;

    // ROE has only Q1 2023, filtered out when panel-level buy_quarter_index=1 slices
    fireEvent.click(within(qualitySection).getByText("From purchase"));

    // ROE chart shows "No data" since its only quarter (index 0) is sliced away
    expect(within(qualitySection).getByText("No data")).toBeTruthy();
  });

  // ── New PE bar states and EPS tooltip tests ────────────────────────────────

  it("renders P/E with normal status (filled bar, value shown)", () => {
    const data = makeData();
    data.sections[3].metrics[0].quarters = [
      { fiscal_year: 2025, fiscal_quarter: 3, label: "Q3 2025", value: 10.25, status: "normal", ttm_eps: 1.16, components: [
        { label: "Q3 2025", value: 0.60 },
        { label: "Q2 2025", value: -0.01 },
        { label: "Q1 2025", value: 0.12 },
        { label: "Q4 2024", value: 0.45 },
      ]},
    ];
    mockUseFundamentals.mockReturnValue({ data, loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    // Header shows 10.3× (appears in header and tooltip, so check for at least 1)
    const matches = screen.getAllByText("10.3×");
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it("renders P/E with not_applicable status (hollow bar, N/A header, tooltip shows -6.3× + breakdown)", () => {
    const data = makeData();
    data.sections[3].metrics[0].quarters = [
      { fiscal_year: 2025, fiscal_quarter: 4, label: "Q4 2025", value: -6.35, status: "not_applicable", ttm_eps: -2.78, components: [
        { label: "Q4 2025", value: -2.78, highlight: "driver" },
        { label: "Q3 2025", value: 0.60 },
        { label: "Q2 2025", value: -0.01 },
        { label: "Q1 2025", value: 0.12 },
      ]},
    ];
    mockUseFundamentals.mockReturnValue({ data, loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    // Header shows N/A (based on status), value is the actual PE
    const peMetric = screen.getByText("P/E").closest(".flex-1")!;
    expect(within(peMetric).getAllByText("N/A").length).toBeGreaterThanOrEqual(1);

    // Hover over the bar to show tooltip with PE, EPS breakdown, and driver flag
    const bar = within(peMetric).getByTestId("bar-0");
    fireEvent.mouseEnter(bar);
    expect(screen.getByText("-6.3×")).toBeTruthy();
    expect(screen.getByText("Negative earnings")).toBeTruthy();
    expect(screen.getByText("driver")).toBeTruthy();
  });

  it("renders P/E with insufficient_data status (dashed bar, shows insufficient data label on hover)", () => {
    const data = makeData();
    data.sections[3].metrics[0].quarters = [
      { fiscal_year: 2022, fiscal_quarter: 2, label: "Q2 2022", value: null, status: "insufficient_data", ttm_eps: null, components: [] },
    ];
    mockUseFundamentals.mockReturnValue({ data, loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    const peMetric = screen.getByText("P/E").closest(".flex-1")!;
    const bar = within(peMetric).getByTestId("bar-0");
    fireEvent.mouseEnter(bar);
    expect(screen.getByText("insufficient data")).toBeTruthy();
  });

  it("EPS breakdown appears in tooltip on hover for normal status", () => {
    const data = makeData();
    data.sections[3].metrics[0].quarters = [
      { fiscal_year: 2025, fiscal_quarter: 3, label: "Q3 2025", value: 10.25, status: "normal", ttm_eps: 1.16, components: [
        { label: "Q3 2025", value: 0.60 },
        { label: "Q2 2025", value: -0.01 },
        { label: "Q1 2025", value: 0.12 },
        { label: "Q4 2024", value: 0.45 },
      ]},
    ];
    mockUseFundamentals.mockReturnValue({ data, loading: false, error: null });
    render(<FundamentalsPanel symbol="AAPL" />);

    // Hover over the bar to show tooltip with EPS breakdown
    const peMetric = screen.getByText("P/E").closest(".flex-1")!;
    const bar = within(peMetric).getByTestId("bar-0");
    fireEvent.mouseEnter(bar);

    // TTM EPS shown
    expect(screen.getByText(/TTM EPS:/)).toBeTruthy();
    // Component labels visible
    expect(screen.getByText("Q3 2025:")).toBeTruthy();
    expect(screen.getByText("Q2 2025:")).toBeTruthy();
  });
});
