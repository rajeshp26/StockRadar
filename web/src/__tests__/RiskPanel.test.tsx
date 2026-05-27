import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

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
    fmtDateTime: (iso?: string) => iso || "—",
  };
});

const mockUseRiskAssessment = vi.fn();
vi.mock("@/features/analysis/hooks/useRiskAssessment", () => ({
  useRiskAssessment: (...args: any[]) => mockUseRiskAssessment(...args),
}));

function makeRiskResponse(overrides: Record<string, any> = {}) {
  return {
    symbol: "AAPL",
    company_id: 1,
    currency: "USD",
    composite: {
      score: 76,
      category: "Moderate",
      maximum_expected_loss_pct: 12.5,
      bear_case: {
        eps_growth_assumption: 0.02,
        exit_pe_ratio: 15,
        future_value: 165.62,
        current_price: 200.0,
        downside_pct: -0.172,
      },
    },
    layers: {
      business_fragility: {
        name: "business_fragility",
        display_name: "Business Fragility",
        score: 8.2,
        category: "low",
        weight: 0.20,
        metrics: [
          { name: "Moat Durability", value: 85, label: "Wide", status: "pass", weight: 5 },
          { name: "Revenue Recurrence", label: "High", status: "pass", weight: 3 },
        ],
        moat_score: 85,
        moat_category: "Wide",
        roic_minus_wacc: 22.0,
        sector: "Technology",
        industry: "Consumer Electronics",
        recurrence_classification: "High",
        pricing_power_assessment: "Strong",
      },
      balance_sheet: {
        name: "balance_sheet",
        display_name: "Balance Sheet",
        score: 9.1,
        category: "low",
        weight: 0.25,
        metrics: [
          { name: "Debt/EBITDA", value: 0.2, label: "0.2x", status: "pass", weight: 4 },
          { name: "Interest Coverage", value: 52, label: "52.0x", status: "pass", weight: 3 },
        ],
        debt_to_ebitda: 0.2,
        interest_coverage: 52,
        current_ratio: 2.5,
        debt_to_equity: 0.5,
        fcf_stability_pct: 1.0,
      },
      valuation_compression: {
        name: "valuation_compression",
        display_name: "Valuation Compression",
        score: 6.5,
        category: "moderate",
        weight: 0.20,
        metrics: [
          { name: "P/E Percentile (5y)", value: 75, label: "75th", status: "caution", weight: 3 },
          { name: "EV/EBITDA Percentile", value: 65, label: "65th", status: "caution", weight: 3 },
        ],
        pe_current: 35,
        pe_percentile: 75,
        pe_5y_min: 20,
        pe_5y_max: 45,
        pe_5y_median: 30,
        peg_ratio: 2.1,
      },
      earnings_stress: {
        name: "earnings_stress",
        display_name: "Earnings Stress",
        score: 7.8,
        category: "low",
        weight: 0.25,
        metrics: [
          { name: "EPS CAGR (5y)", value: 0.15, label: "15%", status: "pass", weight: 3 },
          { name: "Revenue CAGR (5y)", value: 0.12, label: "12%", status: "pass", weight: 3 },
        ],
        eps_cagr_5y: 0.15,
        revenue_cagr_5y: 0.12,
        net_margin_current: 0.25,
        operating_margin_trend: "expanding",
        revenue_eps_alignment: "aligned",
      },
      drawdown_risk: {
        name: "drawdown_risk",
        display_name: "Drawdown Risk",
        score: 7.0,
        category: "moderate",
        weight: 0.10,
        metrics: [
          { name: "Max Drawdown (5y)", value: -0.38, label: "\u221238%", status: "caution", weight: 3 },
          { name: "Beta (5y)", value: 0.94, label: "0.94", status: "pass", weight: 2 },
        ],
        max_drawdown_5y: -0.38,
        beta_5y: 0.94,
        current_drawdown: -0.05,
      },
    },
    scenarios: [
      { scenario: "bull", probability: 0.25, eps_growth: 0.15, exit_pe: 28, future_eps: 20.11, future_value: 563.08, total_return: 1.815, downside: 0 },
      { scenario: "base", probability: 0.50, eps_growth: 0.08, exit_pe: 22, future_eps: 14.69, future_value: 323.18, total_return: 0.616, downside: 0 },
      { scenario: "bear", probability: 0.20, eps_growth: 0.02, exit_pe: 15, future_eps: 11.04, future_value: 165.62, total_return: -0.172, downside: -0.172 },
      { scenario: "severe", probability: 0.05, eps_growth: 0.00, exit_pe: 12, future_eps: 10.00, future_value: 120.00, total_return: -0.400, downside: -0.400 },
    ],
    data_quality: {
      data_sources: "financial_ratios + income_statements + company_summary",
      fallbacks_used: false,
      last_computed_at: "2026-05-26T10:00:00Z",
    },
    ...overrides,
  };
}

import { RiskPanel } from "@/features/analysis/components/risk-panel";

describe("RiskPanel — UT-F1 to UT-F15", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseRiskAssessment.mockReturnValue({
      data: null,
      loading: false,
      error: null,
      notComputed: false,
      recompute: vi.fn(),
      generateAi: vi.fn(),
    });
  });

  it("UT-F1: renders loading skeleton state", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: null, loading: true, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    const { container } = render(<RiskPanel symbol="AAPL" />);
    const shimmers = container.querySelectorAll(".glass-shimmer");
    expect(shimmers.length).toBeGreaterThanOrEqual(1);
  });

  it("UT-F2: shows not-computed state with Run Analysis button", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: null, loading: false, error: null, notComputed: true, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("Not yet computed")).toBeInTheDocument();
    expect(screen.getByText("Run Analysis")).toBeInTheDocument();
  });

  it("UT-F3: shows error banner with retry", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: null, loading: false, error: "Failed to load", notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("Failed to load")).toBeInTheDocument();
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });

  it("UT-F4: renders hero section with composite score and MEL", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("Risk Assessment")).toBeInTheDocument();
    expect(screen.getByText("12.5%")).toBeInTheDocument();
    expect(screen.getByText("Moderate")).toBeInTheDocument();
  });

  it("UT-F5: renders all 5 layer cards", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("Business Fragility")).toBeInTheDocument();
    expect(screen.getByText("Balance Sheet")).toBeInTheDocument();
    expect(screen.getByText("Valuation Compression")).toBeInTheDocument();
    expect(screen.getByText("Earnings Stress")).toBeInTheDocument();
    expect(screen.getByText("Drawdown Risk")).toBeInTheDocument();
  });

  it("UT-F6: Business Fragility card shows moat badge on expand", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Business Fragility"));
    expect(screen.getAllByText("Wide").length).toBeGreaterThanOrEqual(1);
  });

  it("UT-F7: Balance Sheet card shows Debt/EBITDA on expand", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Balance Sheet"));
    expect(screen.getByText("0.2x")).toBeInTheDocument();
  });

  it("UT-F8: Valuation card shows P/E percentile on expand", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Valuation Compression"));
    expect(screen.getAllByText("75th").length).toBeGreaterThanOrEqual(1);
  });

  it("UT-F9: Earnings Stress card shows CAGRs on expand", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Earnings Stress"));
    expect(screen.getByText("15%")).toBeInTheDocument();
  });

  it("UT-F10: Drawdown card shows max drawdown on expand", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    fireEvent.click(screen.getByText("Drawdown Risk"));
    expect(screen.getByText("\u221238%")).toBeInTheDocument();
  });

  it("UT-F11: Scenario cards rendered", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("bull")).toBeInTheDocument();
    expect(screen.getByText("base")).toBeInTheDocument();
    expect(screen.getByText("bear")).toBeInTheDocument();
    expect(screen.getByText("severe")).toBeInTheDocument();
  });

  it("UT-F12: AI Narrative section shows Generate AI Summary button", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("Generate AI Summary")).toBeInTheDocument();
  });

  it("UT-F13: AI Narrative section shows Regenerate when narrative exists", () => {
    const data = makeRiskResponse({
      ai_narrative: { narrative: "Test narrative", model: "openrouter/default", generated_at: "2026-05-26T00:00:00Z" },
    });
    mockUseRiskAssessment.mockReturnValue({
      data, loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText("Regenerate")).toBeInTheDocument();
  });

  it("UT-F14: Data quality footer renders", () => {
    mockUseRiskAssessment.mockReturnValue({
      data: makeRiskResponse(), loading: false, error: null, notComputed: false, recompute: vi.fn(), generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    expect(screen.getByText(/financial_ratios/)).toBeInTheDocument();
    expect(screen.getByText("No fallbacks used")).toBeInTheDocument();
  });

  it("UT-F15: Not-computed Run Analysis button calls recompute", async () => {
    const recomputeMock = vi.fn().mockResolvedValue(undefined);
    mockUseRiskAssessment.mockReturnValue({
      data: null, loading: false, error: null, notComputed: true, recompute: recomputeMock, generateAi: vi.fn(),
    });
    render(<RiskPanel symbol="AAPL" />);
    const btn = screen.getByText("Run Analysis");
    fireEvent.click(btn);
    expect(recomputeMock).toHaveBeenCalled();
  });
});
