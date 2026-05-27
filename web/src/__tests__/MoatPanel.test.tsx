import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

// ── Mock shared-ui components ──────────────────────────────────────────────
// NOTE: vi.mock factories run before JSX transform, so we use React.createElement.
vi.mock("@/features/analysis/components/shared-ui", () => {
  const React = require("react");
  return {
    Metric: ({ label, value, hint, accent }: any) =>
      React.createElement("div", { "data-testid": `metric-${label}`, "data-accent": accent },
        React.createElement("span", null, label),
        React.createElement("span", null, value),
        hint ? React.createElement("span", { "data-testid": "hint" }, hint) : null,
      ),
    SectionHeader: ({ title, subtitle, action }: any) =>
      React.createElement("div", { "data-testid": "section-header" },
        React.createElement("h3", null, title),
        subtitle ? React.createElement("p", null, subtitle) : null,
        action ? React.createElement("div", { "data-testid": "section-action" }, action) : null,
      ),
    SuitabilitySidebar: ({ loading, score, category, showDiagnostics, onToggleDiagnostics }: any) =>
      React.createElement("div", { "data-testid": "suitability-sidebar", "data-loading": loading, "data-score": score, "data-category": category },
        !loading
          ? React.createElement("button", { "data-testid": "toggle-diagnostics", onClick: onToggleDiagnostics },
              showDiagnostics ? "Hide Details" : "Diagnostics",
            )
          : null,
      ),
    DiagnosticsList: ({ items }: any) =>
      React.createElement("div", { "data-testid": "diagnostics-list" },
        `diagnostics: ${items ? items.length : 0}`,
      ),
  };
});

// ── Mock moat service ──────────────────────────────────────────────────────
const mockFetchMoatEvidence = vi.fn();
const mockFetchMoatAiNarrative = vi.fn();
const mockGenerateMoatAiNarrative = vi.fn();

vi.mock("@/features/analysis/services/moat.service", () => ({
  fetchMoatEvidence: (...args: any[]) => mockFetchMoatEvidence(...args),
  fetchMoatAiNarrative: (...args: any[]) => mockFetchMoatAiNarrative(...args),
  generateMoatAiNarrative: (...args: any[]) => mockGenerateMoatAiNarrative(...args),
}));

// ── Mock useMoatAnalysis hook ──────────────────────────────────────────────
const mockUseMoatAnalysis = vi.fn();
vi.mock("@/features/analysis/hooks/useMoatAnalysis", () => ({
  useMoatAnalysis: (...args: any[]) => mockUseMoatAnalysis(...args),
}));

// ── Factory helpers ────────────────────────────────────────────────────────
function makeFullData(overrides = {}) {
  return {
    symbol: "AAPL",
    company_id: 1,
    currency: "USD",
    inputs: {
      nopat: 25000,
      invested_capital: 140000,
      gross_margin: 0.43,
      operating_margin: 0.30,
      net_margin: 0.25,
      roic_5y_avg: 0.30,
      roic_volatility: 0.02,
      asset_turnover: 0.88,
      fiscal_years_used: 5,
      as_of_date: "2026-05-25",
    },
    valuation: {
      roic: 0.32,
      wacc: 0.10,
      roic_minus_wacc: 22.0,
      gross_margin_pct: 43.0,
      operating_margin_pct: 30.0,
      net_margin_pct: 25.0,
      roic_5y_avg: 0.30,
      roic_5y_std: 0.02,
      roic_stability_score: 90.0,
      asset_turnover: 0.88,
      capital_efficiency_score: 85.0,
      moat_score: 85.0,
      moat_category: "Wide",
      moat_summary: null,
    },
    industry_context: {
      sector: "Technology",
      industry: "Software",
      avg_roic: 15.0,
      roic_vs_industry: "above",
      avg_margin: null,
      sample_size: 100,
      context_note: "",
    },
    applicability: {
      score: 85,
      category: "Applicable",
      excluded: false,
      exclusion_reason: null,
      flags: [
        { code: "MOAT-ROIC-EXTREME", severity: "info", message: "High ROIC", recommendation: null },
      ],
      suitability_summary: null,
    },
    data_quality: {
      data_sources: "company_summary + financial_ratios",
      fiscal_year_end: 2024,
      quarters_used: 0,
      days_since_update: null,
      fallbacks_used: false,
      last_computed_at: "2026-05-25T00:00:00Z",
    },
    ...overrides,
  };
}

function makeEvidenceData(overrides = {}) {
  return {
    symbol: "AAPL",
    company_id: 1,
    text_analysis_available: true,
    filing_type: "10-K",
    filing_date: "2025-09-15",
    total_keyword_matches: 5,
    groups_found: ["intangible_assets", "switching_costs"],
    evidence_by_group: {
      intangible_assets: [
        { keyword: "patent", keyword_group: "intangible_assets", section: "item_1_business", snippet: "holds patents", relevance_score: 0.9, filing_date: "2025-09-15" },
        { keyword: "brand", keyword_group: "intangible_assets", section: "item_1_business", snippet: "brand recognition", relevance_score: 0.7, filing_date: "2025-09-15" },
      ],
      switching_costs: [
        { keyword: "switching costs", keyword_group: "switching_costs", section: "item_1_business", snippet: "creates switching costs", relevance_score: 1.0, filing_date: "2025-09-15" },
      ],
    },
    ...overrides,
  };
}

function makeAiNarrativeData(overrides = {}) {
  return {
    symbol: "AAPL",
    company_id: 1,
    narrative: {
      narrative: "Apple has a wide economic moat based on brand power and ecosystem lock-in.",
      summary: null,
      model: "openrouter/default",
      generated_at: "2026-05-25T00:00:00Z",
      generation_time_ms: 1500,
    },
    available: true,
    ...overrides,
  };
}

// ── Component under test ───────────────────────────────────────────────────
import { MoatPanel } from "@/features/analysis/components/moat-panel";

describe("MoatPanel — FT-01 to FT-15", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseMoatAnalysis.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      notComputed: false,
      recompute: vi.fn(),
    });
    mockFetchMoatEvidence.mockResolvedValue(makeEvidenceData());
    mockFetchMoatAiNarrative.mockResolvedValue(makeAiNarrativeData());
    mockGenerateMoatAiNarrative.mockResolvedValue(makeAiNarrativeData());
  });

  // ── FT-01: Loading state ──────────────────────────────────────────
  it("FT-01: renders skeleton/metrics loading state", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: null, loading: true, error: null, notComputed: false, recompute: vi.fn(),
    });
    const { container } = render(<MoatPanel symbol="AAPL" />);
    const shimmers = container.querySelectorAll(".glass-shimmer");
    expect(shimmers.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Economic Moat Analysis")).toBeInTheDocument();
  });

  // ── FT-02: Not computed state ─────────────────────────────────────
  it("FT-02: shows not-computed state with Run Analysis button", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: null, loading: false, error: null, notComputed: true, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("Not yet computed")).toBeInTheDocument();
    expect(screen.getByText("Run Analysis")).toBeInTheDocument();
  });

  // ── FT-03: Panel renders with full data ───────────────────────────
  it("FT-03: renders with full moat data", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("Economic Moat Analysis")).toBeInTheDocument();
    const moatScores = screen.getAllByText("85/100");
    expect(moatScores.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Wide Moat")).toBeInTheDocument();
  });

  // ── FT-04: Error state ────────────────────────────────────────────
  it("FT-04: shows error banner when error is present", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: null, loading: false, error: "Failed to load data", notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("Failed to load data")).toBeInTheDocument();
  });

  // ── FT-05: Core metrics display correctly ─────────────────────────
  it("FT-05: displays core metric values", () => {
    const data = makeFullData();
    mockUseMoatAnalysis.mockReturnValue({
      data, loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("ROIC")).toBeInTheDocument();
    expect(screen.getByText("WACC")).toBeInTheDocument();
    expect(screen.getByText("Moat Category")).toBeInTheDocument();
  });

  // ── FT-06: Inputs section ─────────────────────────────────────────
  it("FT-06: renders Inputs section with raw data", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("Inputs")).toBeInTheDocument();
    expect(screen.getByText("NOPAT")).toBeInTheDocument();
    expect(screen.getByText("Invested capital")).toBeInTheDocument();
  });

  // ── FT-07: Data quality footer ────────────────────────────────────
  it("FT-07: renders data quality footer", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText(/Data source/)).toBeInTheDocument();
    expect(screen.getByText(/company_summary \+ financial_ratios/)).toBeInTheDocument();
  });

  // ── FT-08: No evidence loaded state ───────────────────────────────
  it("FT-08: shows initial evidence placeholder when no evidence loaded", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByRole("button", { name: /View Evidence/ })).toBeInTheDocument();
  });

  // ── FT-09: Evidence loaded state ──────────────────────────────────
  it("FT-09: shows evidence when loaded via button click", async () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    const btn = screen.getByRole("button", { name: /View Evidence/ });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(screen.getByText(/keyword matches found/)).toBeInTheDocument();
    });
  });

  // ── FT-10: Evidence loading state ─────────────────────────────────
  it("FT-10: shows loading shimmer when evidence is loading", () => {
    mockFetchMoatEvidence.mockImplementation(() => new Promise(() => {}));
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    fireEvent.click(screen.getByRole("button", { name: /View Evidence/ }));
    expect(screen.getByText(/EDGAR 10-K Evidence/)).toBeInTheDocument();
  });

  // ── FT-11: AI narrative — generate state ──────────────────────────
  it("FT-11: shows Generate AI button", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("Generate AI")).toBeInTheDocument();
  });

  // ── FT-12: AI narrative — loaded state ────────────────────────────
  it("FT-12: displays AI narrative when loaded via button click", async () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Generate AI"));
    await waitFor(() => {
      expect(screen.getByText(/wide economic moat/)).toBeInTheDocument();
    });
  });

  // ── FT-13: AI narrative — error state ─────────────────────────────
  it("FT-13: shows error when AI narrative fetch fails", async () => {
    mockGenerateMoatAiNarrative.mockRejectedValue(new Error("AI service unavailable"));
    mockFetchMoatAiNarrative.mockResolvedValue({
      available: false, symbol: "AAPL", company_id: 1,
      narrative: { narrative: "", summary: null, model: "", generated_at: "", generation_time_ms: null },
    });
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Generate AI"));
    await waitFor(() => {
      expect(screen.getByText("AI service unavailable")).toBeInTheDocument();
    });
  });

  // ── FT-14: Diagnostics toggle ─────────────────────────────────────
  it("FT-14: toggles diagnostics panel visibility", () => {
    mockUseMoatAnalysis.mockReturnValue({
      data: makeFullData(), loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    const toggleBtn = screen.getByTestId("toggle-diagnostics");
    fireEvent.click(toggleBtn);
    expect(screen.getByTestId("diagnostics-list")).toBeInTheDocument();
  });

  // ── FT-15: Sector exclusion banner ────────────────────────────────
  it("FT-15: shows exclusion banner when sector is excluded", () => {
    const data = makeFullData({
      applicability: {
        ...makeFullData().applicability,
        excluded: true,
        exclusion_reason: "Financial sector not suitable for moat analysis.",
      },
    });
    mockUseMoatAnalysis.mockReturnValue({
      data, loading: false, error: null, notComputed: false, recompute: vi.fn(),
    });
    render(<MoatPanel symbol="AAPL" />);
    expect(screen.getByText("Sector excluded")).toBeInTheDocument();
    expect(screen.getByText(/Financial sector not suitable/)).toBeInTheDocument();
  });
});
