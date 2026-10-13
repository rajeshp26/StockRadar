import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { format } from "date-fns";
import React from "react";

// ═════════════════════════════════════════════════════════════════════════
// Capturing recharts mock — records every XAxis props object so tests can
// assert on the wired `ticks` / `tickFormatter` per chart and per period.
// ═════════════════════════════════════════════════════════════════════════
const xAxisCaptures: { dataKey?: string; ticks?: string[]; tickFormatter?: (v: string) => string; minTickGap?: number }[] = [];
const yAxisCaptures: { tickFormatter?: (v: number) => string }[] = [];

vi.mock("recharts", () => {
    const React = require("react");
    return {
        ResponsiveContainer: ({ children }: any) => React.createElement("div", { "data-testid": "recharts-container" }, children),
        ComposedChart: ({ children }: any) => React.createElement("div", { "data-testid": "composed-chart" }, children),
        AreaChart: ({ children }: any) => React.createElement("div", { "data-testid": "area-chart" }, children),
        LineChart: ({ children }: any) => React.createElement("div", { "data-testid": "line-chart" }, children),
        BarChart: ({ children }: any) => React.createElement("div", { "data-testid": "bar-chart" }, children),
        Area: () => null,
        Line: () => null,
        Bar: () => null,
        XAxis: (props: any) => {
            xAxisCaptures.push({
                dataKey: props.dataKey,
                ticks: props.ticks,
                tickFormatter: props.tickFormatter,
                minTickGap: props.minTickGap,
            });
            return null;
        },
        YAxis: (props: any) => {
            yAxisCaptures.push({ tickFormatter: props.tickFormatter });
            return null;
        },
        Tooltip: () => null,
        CartesianGrid: () => null,
        Legend: () => null,
    };
});

// ── Portfolio-level hooks (used by PortfolioPerformanceChart) ──────────────
const mockUsePortfolioPerformance = vi.fn();
const mockUseBenchmarks = vi.fn();
const mockUseBenchmarkCompare = vi.fn();

// ── Holding-level hooks (used by StockPerformancePanel) ────────────────────
const mockUseHoldingPerformance = vi.fn();
const mockUseHoldingDividends = vi.fn();
const mockUseHoldingBenchmarkCompare = vi.fn();
const mockUseHoldingTransactions = vi.fn();
const mockUseHoldingAccounts = vi.fn();

vi.mock("@/features/portfolio/hooks/usePortfolio", () => ({
    usePortfolioPerformance: (...args: any[]) => mockUsePortfolioPerformance(...args),
    useBenchmarks: (...args: any[]) => mockUseBenchmarks(...args),
    useBenchmarkCompare: (...args: any[]) => mockUseBenchmarkCompare(...args),
    useHoldingPerformance: (...args: any[]) => mockUseHoldingPerformance(...args),
    useHoldingDividends: (...args: any[]) => mockUseHoldingDividends(...args),
    useHoldingBenchmarkCompare: (...args: any[]) => mockUseHoldingBenchmarkCompare(...args),
    useHoldingTransactions: (...args: any[]) => mockUseHoldingTransactions(...args),
    useHoldingAccounts: (...args: any[]) => mockUseHoldingAccounts(...args),
    usePortfolioAccounts: () => ({ data: [], isLoading: false }),
}));

const mockUseLivePrice = vi.fn();

vi.mock("@/features/analysis/hooks/useLivePrice", () => ({
    useLivePrice: (...args: any[]) => mockUseLivePrice(...args),
}));

// ── Stock-vs-index hooks ────────────────────────────────────────────────────
const mockUseStockVsIndex = vi.fn();
const mockUseAnalysisBenchmarks = vi.fn();

vi.mock("@/features/analysis/hooks/useStockVsIndex", () => ({
    useStockVsIndex: (...args: any[]) => mockUseStockVsIndex(...args),
    useAnalysisBenchmarks: (...args: any[]) => mockUseAnalysisBenchmarks(...args),
}));

vi.mock("@/components/ui/skeleton", () => ({
    Skeleton: ({ className }: any) => {
        const React = require("react");
        return React.createElement("div", { "data-testid": "skeleton", className });
    },
}));

vi.mock("lucide-react", () => {
    const React = require("react");
    const mkIcon = () => () => React.createElement("svg", { "data-testid": "icon" });
    return {
        TrendingUp: mkIcon(),
        TrendingDown: mkIcon(),
        DollarSign: mkIcon(),
        Wallet: mkIcon(),
        Receipt: mkIcon(),
        PiggyBank: mkIcon(),
        Calendar: mkIcon(),
        Activity: mkIcon(),
        ArrowUpRight: mkIcon(),
        CalendarDays: mkIcon(),
        BarChart3: mkIcon(),
        AlertTriangle: mkIcon(),
        Check: mkIcon(),
        ChevronDown: mkIcon(),
    };
});

import { PortfolioPerformanceChart } from "@/features/portfolio/components/PortfolioPerformanceChart";
import { BenchmarkComparisonChart } from "@/features/portfolio/components/BenchmarkComparisonChart";
import { DrawdownChart } from "@/features/portfolio/components/DrawdownChart";
import { StockPerformancePanel } from "@/features/analysis/components/stock-performance-panel";
import { StockVsIndexPanel } from "@/features/analysis/components/stock-vs-index-panel";

// ═════════════════════════════════════════════════════════════════════════
// Fixtures
// ═════════════════════════════════════════════════════════════════════════

function makePortfolioPerformance(period: string) {
    const snapshots: { date: string; value: number; cost_basis: number; net_deposits: number }[] = [];
    let value = 100000;
    if (period === "1D") {
        for (const hour of [9, 11, 13, 15]) {
            snapshots.push({ date: `2026-09-14T${String(hour).padStart(2, "0")}:00:00`, value, cost_basis: 98000, net_deposits: 0 });
            value += 400;
        }
    } else if (period === "1W") {
        for (let day = 8; day <= 14; day++) {
            snapshots.push({ date: `2026-09-${String(day).padStart(2, "0")}`, value, cost_basis: 98000, net_deposits: 0 });
            value += 400;
        }
    } else if (period === "1M") {
        // 6 points across a single month -> day-granular 'MMM d'
        for (let day = 5; day <= 30; day += 5) {
            snapshots.push({ date: `2026-09-${String(day).padStart(2, "0")}`, value, cost_basis: 98000, net_deposits: 0 });
            value += 400;
        }
    } else if (period === "YTD") {
        for (let m = 1; m <= 8; m++) {
            snapshots.push({ date: `2026-${String(m).padStart(2, "0")}-01`, value, cost_basis: 98000, net_deposits: 0 });
            value += 400;
        }
    } else if (period === "ALL") {
        // 10-year span → year ticks (`yyyy`); spans ≤ 8 years now get quarters
        for (let m = 0; m < 121; m++) {
            const d = new Date(2018, 6 + m, 1);
            snapshots.push({ date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`, value, cost_basis: 98000, net_deposits: 0 });
            value += 400;
        }
    } else {
        // 1Y (default): 12 monthly points 2025-09-01 .. 2026-08-01
        for (let m = 0; m < 12; m++) {
            const d = new Date(2025, 8 + m, 1);
            snapshots.push({ date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`, value, cost_basis: 98000, net_deposits: 0 });
            value += 400;
        }
    }
    return { success: true, period, snapshots, total_return: 5000, total_return_pct: 5.0 };
}

function makeHoldingPerformance() {
    const snapshots: { date: string; position_value: number; cost_basis: number; cumulative_invested: number }[] = [];
    let v = 1800;
    for (let m = 0; m < 12; m++) {
        const d = new Date(2025, 8 + m, 1);
        snapshots.push({
            date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`,
            position_value: v,
            cost_basis: 1800,
            cumulative_invested: 1800,
        });
        v += 40;
    }
    return {
        success: true,
        symbol: "AAPL",
        period: "1Y",
        snapshots,
        total_return: 400,
        total_return_pct: 22.22,
        total_dividends: 87.0,
        total_dividends_pct: 4.83,
        combined_return: 487.0,
        best_month: { month: "2025-10", return_pct: 11.11, label: "Oct 2025" },
        worst_month: { month: "2025-09", return_pct: 5.0, label: "Sep 2025" },
        max_drawdown: { dd_pct: -10.5, start_date: "2025-11-01", end_date: "2025-12-15", duration_days: 44, is_ongoing: false },
        longest_drawdown: { dd_pct: -8.2, start_date: "2025-10-01", end_date: "2025-11-01", duration_days: 31, is_ongoing: false },
        volatility_30d: 25.5,
        days_above_cost_basis: { days_above: 200, total_days: 300, pct_above: 66.7 },
    };
}

function makeBenchmarkCompare() {
    const points: { date: string; value: number }[] = [];
    let v = 100;
    for (let m = 0; m < 12; m++) {
        const d = new Date(2025, 8 + m, 1);
        points.push({ date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`, value: v });
        v += 3;
    }
    return {
        success: true,
        period: "1Y",
        portfolio: points,
        benchmarks: [{ symbol: "^GSPC", name: "S&P 500", data: points.map((p) => ({ date: p.date, value: p.value * 0.9 })) }],
    };
}

function makeDrawdown() {
    const drawdowns: { date: string; value: number; drawdown_pct: number }[] = [];
    let v = 100000;
    for (let m = 0; m < 12; m++) {
        const d = new Date(2025, 8 + m, 1);
        drawdowns.push({
            date: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`,
            value: v,
            drawdown_pct: -m * 1.5,
        });
        v -= 300;
    }
    return {
        success: true,
        period: "1Y",
        drawdowns,
        max_drawdown: 16500,
        max_drawdown_pct: -16.5,
        max_drawdown_start: "2025-12-01",
        max_drawdown_end: "2026-03-01",
        max_drawdown_recovery: null,
        avg_drawdown: -8.2,
    };
}

function makeStockVsIndex() {
    const dates: string[] = [];
    const count = 37; // 3-year monthly span 2023-07-01 .. 2026-07-01
    for (let m = 0; m < count; m++) {
        const d = new Date(2023, 6 + m, 1);
        dates.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`);
    }
    const priceSeries = (start: number) => dates.map((_, i) => start + i * 2.5);
    const rsSeries = dates.map((_, i) => 100 + i * 0.8);
    return {
        symbol: "AAPL",
        primary_index: "^GSPC",
        benchmarks: [{ symbol: "SPY", name: "S&P 500" }],
        period_years: 3,
        quantitative: { beta: 1.1, alpha: 0.02, stock_sharpe: 0.9, index_sharpe: 0.8, growth_score: 2, revenue_cagr: 8.0, eps_cagr: 10.0, fcf_cagr: 7.0, peg_ratio: 1.2, score: 70 },
        visual: { rs_trend: 0.05, outperform_rate: 0.6, stock_max_drawdown: -0.2, index_max_drawdown: -0.25, dd_ratio: 0.8, score: 65 },
        combined_score: 0.72,
        recommendation: "outperform",
        charts: {
            dates,
            normalized_prices: { AAPL: priceSeries(100), SPY: priceSeries(100) },
            relative_strength: { SPY: rsSeries },
            rolling_12m_returns: { SPY: dates.map(() => 0.1) },
            drawdowns: { SPY: dates.map(() => -0.1) },
        },
    };
}

// ═════════════════════════════════════════════════════════════════════════
// Helpers
// ═════════════════════════════════════════════════════════════════════════

function dateAxesSince(from: number) {
    return xAxisCaptures.slice(from).filter((c) => Array.isArray(c.ticks));
}

describe("chart x-axis wiring (getDateAxis → XAxis ticks/tickFormatter)", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        xAxisCaptures.length = 0;
        yAxisCaptures.length = 0;

        mockUsePortfolioPerformance.mockImplementation((period: string) => ({
            data: makePortfolioPerformance(period),
            isLoading: false,
            isError: false,
            isFetching: false,
        }));
        mockUseBenchmarks.mockReturnValue({ data: [], isLoading: false });
        mockUseBenchmarkCompare.mockReturnValue({ data: undefined, isLoading: false, isError: false });

        mockUseHoldingPerformance.mockReturnValue({ data: makeHoldingPerformance(), isLoading: false });
        mockUseHoldingDividends.mockReturnValue({ data: [], isLoading: false });
        mockUseHoldingBenchmarkCompare.mockReturnValue({ data: null, isLoading: false });
        mockUseHoldingTransactions.mockReturnValue({ data: [], isLoading: false });
        mockUseHoldingAccounts.mockReturnValue({ data: [], isLoading: false });
        mockUseLivePrice.mockReturnValue({ price: 220, change: 0, changePercent: 0, loading: false, error: null, lastUpdated: null, currency: null });

        mockUseStockVsIndex.mockReturnValue({ loading: false, data: makeStockVsIndex() });
        mockUseAnalysisBenchmarks.mockReturnValue({ data: [], isLoading: false });
    });

    it("PortfolioPerformanceChart: default 1Y passes monthly MMM'yy ticks ⊆ data dates", () => {
        render(<PortfolioPerformanceChart />);
        const axes = dateAxesSince(0);
        expect(axes.length).toBe(1);
        const axis = axes[0];
        const dataDates = new Set(makePortfolioPerformance("1Y").snapshots.map((s) => s.date));
        expect(axis.ticks!.length).toBeGreaterThan(0);
        expect(axis.ticks!.every((t) => dataDates.has(t))).toBe(true);
        expect(axis.tickFormatter!("2025-09-01")).toBe(format(new Date(2025, 8, 1), "MMM''yy"));
        expect(axis.minTickGap).toBeUndefined();
    });

    it("PortfolioPerformanceChart: switching period re-derives axis format (1M MMM d, 1W EEE, ALL yyyy)", () => {
        render(<PortfolioPerformanceChart />);

        fireEvent.click(screen.getByText("1M"));
        let axes = dateAxesSince(0).slice(-1);
        expect(axes[0].tickFormatter!("2026-09-15")).toBe(format(new Date(2026, 8, 15), "MMM d"));

        fireEvent.click(screen.getByText("1W"));
        axes = dateAxesSince(0).slice(-1);
        expect(axes[0].tickFormatter!("2026-09-08")).toBe(format(new Date(2026, 8, 8), "EEE"));

        fireEvent.click(screen.getByText("All Time"));
        axes = dateAxesSince(0).slice(-1);
        const allDates = new Set(makePortfolioPerformance("ALL").snapshots.map((s) => s.date));
        expect(axes[0].ticks!.length).toBeGreaterThan(0);
        expect(axes[0].ticks!.every((t) => allDates.has(t))).toBe(true);
        expect(axes[0].tickFormatter!("2018-07-01")).toBe(format(new Date(2018, 6, 1), "yyyy"));
    });

    it("PortfolioPerformanceChart: bar variant keeps XAxis ticks wired to data dates", () => {
        render(<PortfolioPerformanceChart />);

        fireEvent.click(screen.getByRole("button", { name: "Bar" }));
        const axes = dateAxesSince(0);
        expect(axes.length).toBeGreaterThan(0);
        const axis = axes[axes.length - 1];
        const dataDates = new Set(makePortfolioPerformance("1Y").snapshots.map((s) => s.date));
        expect(axis.ticks!.length).toBeGreaterThan(0);
        expect(axis.ticks!.every((t) => dataDates.has(t))).toBe(true);
        expect(axis.tickFormatter!("2025-09-01")).toBe(format(new Date(2025, 8, 1), "MMM''yy"));
    });

    it("BenchmarkComparisonChart: passes 1Y MMM'yy ticks ⊆ merged data dates", () => {
        render(<BenchmarkComparisonChart data={makeBenchmarkCompare() as any} />);
        const axes = dateAxesSince(0);
        expect(axes.length).toBe(1);
        const axis = axes[0];
        const merged = new Set(["2025-09-01"]);
        for (const pt of makeBenchmarkCompare().portfolio) merged.add(pt.date);
        expect(axis.ticks!.length).toBeGreaterThan(0);
        expect(axis.ticks!.every((t) => merged.has(t))).toBe(true);
        expect(axis.tickFormatter!("2025-09-01")).toBe(format(new Date(2025, 8, 1), "MMM''yy"));
        expect(axis.minTickGap).toBeUndefined();
    });

    it("DrawdownChart: passes 1Y MMM'yy ticks ⊆ drawdown dates", () => {
        render(<DrawdownChart data={makeDrawdown() as any} isLoading={false} isError={false} />);
        const axes = dateAxesSince(0);
        expect(axes.length).toBe(1);
        const axis = axes[0];
        const ddDates = new Set(makeDrawdown().drawdowns.map((d) => d.date));
        expect(axis.ticks!.length).toBeGreaterThan(0);
        expect(axis.ticks!.every((t) => ddDates.has(t))).toBe(true);
        expect(axis.tickFormatter!("2025-09-01")).toBe(format(new Date(2025, 8, 1), "MMM''yy"));
        expect(axis.minTickGap).toBeUndefined();
    });

    it("StockPerformancePanel: main chart passes 1Y MMM'yy ticks ⊆ snapshot dates", () => {
        render(<StockPerformancePanel symbol="AAPL" />);
        const axes = dateAxesSince(0);
        expect(axes.length).toBe(1); // dividend bar chart is categorical → no ticks
        const axis = axes[0];
        const snapDates = new Set(makeHoldingPerformance().snapshots.map((s) => s.date));
        expect(axis.ticks!.length).toBeGreaterThan(0);
        expect(axis.ticks!.every((t) => snapDates.has(t))).toBe(true);
        expect(axis.tickFormatter!("2025-09-01")).toBe(format(new Date(2025, 8, 1), "MMM''yy"));
        expect(axis.minTickGap).toBeUndefined();
    });

    it("StockVsIndexPanel: both charts pass ALL Qn'yy ticks ⊆ data dates", () => {
        render(<StockVsIndexPanel symbol="AAPL" />);
        const axes = dateAxesSince(0);
        expect(axes.length).toBe(2); // normalized prices + relative strength
        const dataDates = new Set(makeStockVsIndex().charts.dates);
        for (const axis of axes) {
            expect(axis.ticks!.length).toBeGreaterThan(0);
            expect(axis.ticks!.every((t) => dataDates.has(t))).toBe(true);
            expect(axis.tickFormatter!("2023-07-01")).toBe(format(new Date(2023, 6, 1), "QQQ''yy"));
            expect(axis.minTickGap).toBeUndefined();
        }
    });

    it("PortfolioPerformanceChart: Y axis uses scale-aware compact formatter (k/M tiers)", () => {
        render(<PortfolioPerformanceChart />);
        const yAxis = yAxisCaptures[yAxisCaptures.length - 1];
        expect(yAxis.tickFormatter).toBeDefined();
        expect(yAxis.tickFormatter!(500)).toBe("500");
        expect(yAxis.tickFormatter!(20_000)).toBe("20k");
        expect(yAxis.tickFormatter!(197_667)).toBe("197.7k");
        expect(yAxis.tickFormatter!(1_500_000)).toBe("1.5M");
    });
});