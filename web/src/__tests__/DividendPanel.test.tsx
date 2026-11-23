import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// Required for Recharts ResponsiveContainer
beforeAll(() => {
    globalThis.ResizeObserver = class {
        observe() { }
        unobserve() { }
        disconnect() { }
    } as any;
});

// Mock shared-ui components
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
        ScoreRing: ({ score, category, size }: any) =>
            React.createElement("div", { "data-testid": "score-ring", "data-score": score, "data-category": category, "data-size": size },
                `${score} ${category}`,
            ),
        fmtCurrency: (n?: number | null) => n != null ? `$${n.toFixed(2)}` : "—",
        fmtPct: (n?: number | null) => n != null ? `${(n * 100).toFixed(1)}%` : "—",
    };
});

const mockUseDividendAnalysis = vi.fn();
vi.mock("@/features/analysis/hooks/useDividendAnalysis", () => ({
    useDividendAnalysis: (...args: any[]) => mockUseDividendAnalysis(...args),
}));

import { DividendPanel } from "@/features/analysis/components/dividend-panel";

function makeDividendData(overrides: Record<string, any> = {}) {
    return {
        symbol: "AAPL",
        pays_dividend: true,
        overview: {
            annual_dividend: 1.08,
            per_period_amount: 0.27,
            dividend_yield: 0.0531,
            payout_ratio_adj_eps: 0.48,
            payout_ratio_gaap: 0.45,
            payout_ratio_fcf: 0.29,
            gaap_negative_eps: false,
            frequency: "quarterly",
            frequency_multiplier: 4,
            ex_dividend_date: "2026-02-11",
            payment_date: null,
            last_increase_date: "2024-11-05",
            status: "growing",
            sparkline: [
                { date: "2026-02-11", amount: 0.27 },
                { date: "2025-11-05", amount: 0.27 },
            ],
            current_price: 20.35,
        },
        safety: {
            composite_score: 65,
            composite_category: "Caution",
            metrics: [
                { name: "Div Payout (Adj EPS)", benchmark: "<60%", value: 0.48, formatted: "48%", rating: "safe" },
                { name: "Div Payout (GAAP)", benchmark: "—", value: 0.45, formatted: "45%", rating: "info" },
                { name: "Cash Div Payout", benchmark: "<80%", value: 0.19, formatted: "19%", rating: "safe" },
                { name: "FCF Payout Ratio", benchmark: "<80%", value: 0.29, formatted: "29%", rating: "safe" },
                { name: "Div Coverage (FCF)", benchmark: "≥2×", value: 3.4, formatted: "3.4×", rating: "safe" },
                { name: "Net Debt / EBITDA", benchmark: "<3×", value: 4.6, formatted: "4.6×", rating: "risk" },
                { name: "Interest Coverage", benchmark: "≥3×", value: 3.3, formatted: "3.3×", rating: "safe" },
                { name: "Earnings Stability", benchmark: "5-year trend analysis", value: null, formatted: "Earnings fluctuate", rating: "caution", info_note: "Volatile" },
            ],
            earnings_stability: "volatile",
            dividend_policy: {
                growth_trend: "growing",
                cut_history: "Major cut (2023)",
                has_cut: true,
                cut_year: 2023 as number | null,
                retention_rate: null,
            },
            strengths: [
                "Dividend well-covered by adjusted earnings",
                "Free cash flow generation supports the distribution",
                "Strong interest coverage provides debt service buffer",
            ],
            key_risks: [
                "Prior dividend cut impairs reliability track record",
                "Leverage at 4.6× Net Debt/EBITDA constrains growth",
            ],
        },
        growth: {
            growth_score: 4,
            growth_category: "Poor",
            cagr_1y: 0.0,
            cagr_3y: -0.201,
            cagr_5y: -0.08,
            cagr_10y: null,
            consecutive_increases: 0,
            annual_totals: { "2020": 0.02, "2021": 0.03, "2022": 0.05, "2023": 0.03, "2024": 1.08, "2025": 1.08, "2026": 1.08 },
            recent_changes: [
                { date: "2026-02-11", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
                { date: "2025-11-05", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
                { date: "2025-08-08", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
                { date: "2025-05-09", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
                { date: "2025-02-07", amount: 0.27, change_pct: 0.0, label: "Flat", direction: "flat" },
                { date: "2024-11-05", amount: 0.27, change_pct: 8.0, label: "+800.0%", direction: "increase" },
            ],
        },
        yield_analysis: {
            current_yield: 0.0531,
            avg_yield_5y: 0.0243,
            yield_min_5y: 0.0032,
            yield_max_5y: 0.0592,
            yield_percentile_5y: 89,
            yield_vs_sector: null,
            yield_vs_market: null,
            theory_signal: "Yield is currently above its 5-year average, suggesting potential undervaluation relative to historical norms.",
            yield_history: [
                { date: "2024-01-15", yield: 0.021, price: 25.0, ttm_dividend: 1.08 },
                { date: "2024-06-15", yield: 0.035, price: 30.0, ttm_dividend: 1.08 },
            ],
        },
        ...overrides,
    };
}

describe("DividendPanel", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseDividendAnalysis.mockReturnValue({
            data: null,
            loading: false,
            error: null,
            paysDividend: null,
        });
    });

    // ── Loading & Error States ─────────────────────────────────────────────────
    it("IT-01: shows loading shimmer while fetching", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: null, loading: true, error: null, paysDividend: null,
        });
        const { container } = render(<DividendPanel symbol="AAPL" />);
        expect(container.querySelectorAll(".glass-shimmer").length).toBeGreaterThan(0);
    });

    it("IT-02: shows error banner on fetch failure", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: null, loading: false, error: "Failed to load", paysDividend: null,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Failed to load")).toBeInTheDocument();
    });

    it("IT-03: shows no-dividend state when company does not pay", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: { symbol: "AAPL", pays_dividend: false, overview: null, safety: null, growth: null, yield_analysis: null },
            loading: false, error: null, paysDividend: false,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("No Dividend")).toBeInTheDocument();
        expect(screen.getByText(/does not currently pay a dividend/i)).toBeInTheDocument();
    });

    it("IT-04: null data shows fallback gracefully", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: null, loading: false, error: null, paysDividend: null,
        });
        render(<DividendPanel symbol="AAPL" />);
        // Should not crash — verify no error boundary
        expect(screen.queryByText("No Dividend")).not.toBeInTheDocument();
    });

    // ── Top Bar ─────────────────────────────────────────────────────────────────
    it("IT-05: renders dashboard title and description", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Dividend Dashboard")).toBeInTheDocument();
        // "Current distribution metrics" appears in both dashboard description and section subtitle
        expect(screen.getAllByText(/current distribution metrics/i).length).toBeGreaterThanOrEqual(1);
    });

    it("IT-06: renders all 4 status badges", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        // "Growing" appears once in badge, "Growing" also appears in Growth Score mini-list
        expect(screen.getAllByText("Growing").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("Safety: Caution")).toBeInTheDocument();
        expect(screen.getByText(/Major Cut/)).toBeInTheDocument();
        expect(screen.getByText("Quarterly Payer")).toBeInTheDocument();
    });

    it("IT-07: shows correct badge for declining status", () => {
        const data = makeDividendData();
        data.overview.status = "declining";
        data.safety.composite_category = "Poor";
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Declining")).toBeInTheDocument();
        expect(screen.getByText("Safety: Poor")).toBeInTheDocument();
    });

    it("IT-08: renders 5 filter chips", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Overview")).toBeInTheDocument();
        expect(screen.getByText("Safety")).toBeInTheDocument();
        expect(screen.getByText("Growth")).toBeInTheDocument();
        expect(screen.getByText("Yield")).toBeInTheDocument();
        expect(screen.getByText("History")).toBeInTheDocument();
    });

    // ── Hero Section ────────────────────────────────────────────────────────────
    it("IT-09: renders 4 hero metric tiles with values", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Annual Dividend")).toBeInTheDocument();
        expect(screen.getByText("Dividend Yield")).toBeInTheDocument();
        expect(screen.getByText("Payout Ratio")).toBeInTheDocument();
        expect(screen.getByText("Frequency")).toBeInTheDocument();
    });

    it("IT-10: schedule shows correct dates", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        // Both dates appear in schedule AND recent changes timeline
        expect(screen.getAllByText("Nov 5, 2024").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Feb 11, 2026").length).toBeGreaterThanOrEqual(1);
    });

    it("IT-11: schedule shows FCF and GAAP payout", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        // Both percentages appear in schedule AND safety ratio cards
        expect(screen.getAllByText("29%").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("45%").length).toBeGreaterThanOrEqual(1);
    });

    it("IT-12: signal box is rendered", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Investor Signal")).toBeInTheDocument();
    });

    // ── Safety Section ─────────────────────────────────────────────────────────
    it("IT-13: ScoreRing receives correct safety score and category", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        const rings = screen.getAllByTestId("score-ring");
        const safetyRing = rings.find(r => r.getAttribute("data-score") === "65");
        expect(safetyRing).toBeTruthy();
        expect(safetyRing?.getAttribute("data-category")).toBe("Caution");
    });

    it("IT-14: all safety ratio cards render", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Div Payout (Adj EPS)")).toBeInTheDocument();
        expect(screen.getByText("Net Debt / EBITDA")).toBeInTheDocument();
        expect(screen.getByText("Interest Coverage")).toBeInTheDocument();
        expect(screen.getByText("Earnings Stability")).toBeInTheDocument();
    });

    it("IT-15: ratio values display correctly", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        // "48%" appears in both hero payout ratio metric and safety ratio cards
        expect(screen.getAllByText("48%").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText("3.4×")).toBeInTheDocument();
        expect(screen.getByText("4.6×")).toBeInTheDocument();
    });

    // ── Strengths & Risks ───────────────────────────────────────────────────────
    it("IT-16: strengths list renders", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText(/Dividend well-covered by adjusted earnings/)).toBeInTheDocument();
        expect(screen.getByText(/Free cash flow generation supports/)).toBeInTheDocument();
    });

    it("IT-17: risks list renders", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText(/Prior dividend cut impairs/)).toBeInTheDocument();
        expect(screen.getByText(/Leverage at 4.6×/)).toBeInTheDocument();
    });

    // ── Growth ──────────────────────────────────────────────────────────────────
    it("IT-18: ScoreRing receives correct growth score", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        const rings = screen.getAllByTestId("score-ring");
        const growthRing = rings.find(r => r.getAttribute("data-score") === "4");
        expect(growthRing).toBeTruthy();
        expect(growthRing?.getAttribute("data-category")).toBe("Poor");
    });

    it("IT-19: growth momentum stats render", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("1-Year Growth")).toBeInTheDocument();
        expect(screen.getByText("3-Year CAGR")).toBeInTheDocument();
        expect(screen.getByText("5-Year CAGR")).toBeInTheDocument();
        expect(screen.getByText("10-Year CAGR")).toBeInTheDocument();
        expect(screen.getByText("Consecutive Increases")).toBeInTheDocument();
    });

    it("IT-20: recent changes timeline renders entries", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        // "Flat" appears 5 times (one per flat recent change entry)
        expect(screen.getAllByText("Flat").length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText(/\+800\.0%/)).toBeInTheDocument();
    });

    // ── Yield ───────────────────────────────────────────────────────────────────
    it("IT-21: yield metric tiles render", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("Current Yield")).toBeInTheDocument();
        expect(screen.getByText("5-Year Avg Yield")).toBeInTheDocument();
        expect(screen.getByText("5-Year High")).toBeInTheDocument();
        expect(screen.getByText("5-Year Low")).toBeInTheDocument();
    });

    it("IT-22: yield percentile renders", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("89th")).toBeInTheDocument();
    });

    it("IT-23: yield theory signal renders", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText(/potential undervaluation/)).toBeInTheDocument();
    });

    it("IT-24: relative positioning shows coming-soon text", () => {
        mockUseDividendAnalysis.mockReturnValue({
            data: makeDividendData(), loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText(/market comparison data coming soon/)).toBeInTheDocument();
    });

    // ── Edge Cases ──────────────────────────────────────────────────────────────
    it("IT-25: empty strengths shows fallback", () => {
        const data = makeDividendData();
        data.safety.strengths = [];
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("No notable strengths identified")).toBeInTheDocument();
    });

    it("IT-26: empty risks shows fallback", () => {
        const data = makeDividendData();
        data.safety.key_risks = [];
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("No significant risks identified")).toBeInTheDocument();
    });

    it("IT-27: empty recent changes shows fallback", () => {
        const data = makeDividendData();
        data.growth.recent_changes = [];
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("No recent dividend data available.")).toBeInTheDocument();
    });

    it("IT-28: no cut history hides major cut badge", () => {
        const data = makeDividendData();
        data.safety.dividend_policy.has_cut = false;
        data.safety.dividend_policy.cut_year = null;
        data.safety.dividend_policy.cut_history = "No cuts on record";
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.queryByText(/Major Cut/)).not.toBeInTheDocument();
    });

    it("IT-29: negative CAGR values display with minus sign", () => {
        const data = makeDividendData();
        data.growth.cagr_3y = -0.201;
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        expect(screen.getByText("-20.1%")).toBeInTheDocument();
    });

    it("IT-30: consecutive increases > 0 shows count", () => {
        const data = makeDividendData();
        data.growth.consecutive_increases = 5;
        mockUseDividendAnalysis.mockReturnValue({
            data, loading: false, error: null, paysDividend: true,
        });
        render(<DividendPanel symbol="AAPL" />);
        // "5 Years" appears in both growth score mini-list and growth momentum stats
        expect(screen.getAllByText("5 Years").length).toBeGreaterThanOrEqual(1);
    });
});
