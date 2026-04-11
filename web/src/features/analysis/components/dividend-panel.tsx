// web/src/features/analysis/components/dividend-panel.tsx
"use client";
import { useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import {
    TrendingDown, AlertTriangle, CheckCircle2,
    TrendingUp, Sparkles, Calendar, Percent,
    BarChart2, ArrowUpRight, ArrowDownRight, Minus,
} from "lucide-react";
import { useDividendAnalysis } from "../hooks/useDividendAnalysis";
import {
    ScoreRing, SectionHeader, Metric,
    fmtCurrency, fmtPct,
} from "./shared-ui";
import type {
    DividendOverviewData, DividendSafetyData,
    DividendGrowthData, DividendYieldData,
    DividendRating, SuitabilityCategory,
} from "../types/analysis.types";

// ─────────────────────────────────────────────────────────────────────────────
// Sub-tab type & config
// ─────────────────────────────────────────────────────────────────────────────
type DivTab = "overview" | "safety" | "growth" | "yield";

const DIV_TABS: { id: DivTab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "safety", label: "Safety" },
    { id: "growth", label: "Growth" },
    { id: "yield", label: "Yield" },
];

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────
function fmtYield(v: number | null | undefined): string {
    if (v == null) return "—";
    return `${(v * 100).toFixed(2)}%`;
}

function fmtPctRaw(v: number | null | undefined, digits = 1): string {
    if (v == null) return "—";
    return `${(v * 100).toFixed(digits)}%`;
}

function fmtMultiple(v: number | null | undefined, digits = 1): string {
    if (v == null) return "—";
    return `${v.toFixed(digits)}×`;
}

function fmtDate(iso: string | null | undefined): string {
    if (!iso) return "—";
    try {
        return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
            month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
        });
    } catch { return iso; }
}

function fmtFrequency(freq: string): string {
    const map: Record<string, string> = {
        quarterly: "Quarterly", monthly: "Monthly",
        "semi-annual": "Semi-Annual", annual: "Annual",
        semiannual: "Semi-Annual", biannual: "Semi-Annual",
    };
    return map[freq.toLowerCase()] ?? freq;
}

function fmtCagr(v: number | null | undefined): string {
    if (v == null) return "—";
    const pct = (v * 100).toFixed(1);
    return v >= 0 ? `+${pct}%` : `${pct}%`;
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared sub-components
// ─────────────────────────────────────────────────────────────────────────────

function MetricSkeleton() {
    return (
        <div className="glass-stat space-y-3">
            <div className="h-2 w-16 rounded-full bg-white/10 glass-shimmer" />
            <div className="h-8 w-24 rounded-lg bg-white/10 glass-shimmer" />
        </div>
    );
}

function AccentLine() {
    return (
        <div
            className="pointer-events-none absolute inset-x-0 top-0 h-px z-10"
            style={{
                background:
                    "linear-gradient(90deg,transparent,rgba(99,102,241,0.5) 40%,rgba(139,92,246,0.3) 70%,transparent)",
            }}
            aria-hidden="true"
        />
    );
}

function AiNote({ text, loading }: { text?: string | null; loading?: boolean }) {
    if (loading) {
        return (
            <div className="rounded-2xl border border-white/6 bg-white/3 px-5 py-4 space-y-2">
                {[20, 36, 28].map((w, i) => (
                    <div key={i} className={`h-2 w-${w} rounded-full bg-white/8 glass-shimmer`} />
                ))}
            </div>
        );
    }
    if (!text) return null;
    return (
        <div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/5 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
                <Sparkles className="h-3 w-3 text-indigo-400/70" />
                <span className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70">
                    AI Dividend Insight
                </span>
            </div>
            <p className="text-[12px] leading-relaxed text-white/60">{text}</p>
        </div>
    );
}

/** Rating pill — maps backend rating to exact glass-badge CSS classes */
function RatingBadge({ rating, text }: { rating: DividendRating; text?: string }) {
    const styles: Record<DividendRating, string> = {
        safe: "glass-badge-buy",
        moderate: "glass-badge-hold",
        borderline: "bg-orange-500/10 border-orange-500/25 text-orange-400",
        risk: "glass-badge-sell",
        info: "bg-indigo-500/10 border-indigo-500/25 text-indigo-400",
    };
    const labels: Record<DividendRating, string> = {
        safe: "Safe", moderate: "Moderate", borderline: "Borderline",
        risk: "Risk", info: "Info",
    };
    return (
        <span className={cn("glass-badge", styles[rating])}>
            {text ?? labels[rating]}
        </span>
    );
}

/** Status chip shown in overview */
function StatusBadge({ status }: { status: string }) {
    if (status === "stable") return (
        <span className="glass-badge glass-badge-buy flex items-center gap-1">
            <CheckCircle2 className="h-2.5 w-2.5" /> Stable
        </span>
    );
    if (status === "growing") return (
        <span className="glass-badge glass-badge-buy flex items-center gap-1">
            <TrendingUp className="h-2.5 w-2.5" /> Growing
        </span>
    );
    if (status === "declining") return (
        <span className="glass-badge glass-badge-sell flex items-center gap-1">
            <TrendingDown className="h-2.5 w-2.5" /> Declining
        </span>
    );
    return <span className="glass-badge bg-white/5 border-white/10 text-white/30">—</span>;
}

/** Category label coloring */
function categoryColor(cat?: SuitabilityCategory | string): string {
    if (cat === "Good") return "text-emerald-400";
    if (cat === "Caution") return "text-amber-400";
    if (cat === "Poor") return "text-rose-400";
    return "text-white/40";
}

/** Metric row used in the safety table */
function SafetyRow({ m }: { m: { name: string; formatted: string; benchmark: string; rating: DividendRating; info_note?: string | null } }) {
    return (
        <div className="flex items-center justify-between py-2.5 border-b border-white/5 last:border-0">
            <div>
                <p className="text-[11px] font-semibold text-white/75">{m.name}</p>
                <p className="text-[9px] text-white/25 mt-0.5">Benchmark: {m.benchmark}</p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
                <span className="text-sm font-black text-white tabular-nums">
                    {m.info_note ? (
                        <span className="text-[10px] text-white/40 font-medium">{m.formatted}</span>
                    ) : m.formatted}
                </span>
                <RatingBadge rating={m.rating} text={m.info_note ?? undefined} />
            </div>
        </div>
    );
}

/** Dividend sparkline SVG — polyline with y-axis labels and multi-year x-axis */
function DividendSparkline({ data }: { data: { date: string; amount: number }[] }) {
    if (!data.length) return null;

    // Layout constants
    const LW = 42;            // left margin reserved for y-axis labels
    const TW = 256;           // total SVG width
    const CW = TW - LW;      // chart area width
    const CH = 52;            // chart area height
    const XH = 14;            // x-axis label row height below chart
    const TH = CH + XH;      // total SVG height
    const PAD = 6;             // inner padding within chart area

    const amounts = data.map((d) => d.amount);
    const minA = Math.min(...amounts);
    const maxA = Math.max(...amounts);
    const range = maxA - minA || 1;

    const toX = (i: number) =>
        LW + PAD + (i / Math.max(data.length - 1, 1)) * (CW - PAD * 2);
    const toY = (amt: number) =>
        PAD + ((maxA - amt) / range) * (CH - PAD * 2);

    const points = data.map((_, i) => `${toX(i).toFixed(1)},${toY(data[i].amount).toFixed(1)}`);
    const firstX = parseFloat(points[0].split(",")[0]);
    const lastPt = points[points.length - 1];
    const lastX = parseFloat(lastPt.split(",")[0]);
    const fillPath = `M ${firstX},${CH - PAD} L ${points.join(" L ")} L ${lastX},${CH - PAD} Z`;

    const hasCut = data.some((d, i) => i > 0 && d.amount < data[i - 1].amount * 0.9);
    const stroke = hasCut ? "rgba(248,113,113,0.75)" : "rgba(99,102,241,0.75)";
    const fillCol = hasCut ? "rgba(248,113,113,0.08)" : "rgba(99,102,241,0.08)";

    // Y-axis label formatter — adapts decimal places to magnitude
    const fmtAmt = (v: number) =>
        v < 0.1 ? `$${v.toFixed(4)}` : v < 1 ? `$${v.toFixed(3)}` : `$${v.toFixed(2)}`;

    // X-axis: unique years sampled to ≤5 labels so they don't collide
    const uniqueYears = [...new Set(data.map((d) => d.date?.slice(0, 4) ?? ""))].sort();
    const step = Math.max(1, Math.ceil(uniqueYears.length / 5));
    const xLabels = uniqueYears
        .filter((_, i) => i % step === 0 || i === uniqueYears.length - 1)
        .map((yr) => {
            const idx = data.findIndex((d) => d.date?.startsWith(yr));
            return idx >= 0 ? { yr, x: toX(idx) } : null;
        })
        .filter((v): v is { yr: string; x: number } => v !== null);

    const [lx, ly] = lastPt.split(",").map(Number);

    return (
        <svg viewBox={`0 0 ${TW} ${TH}`} className="w-full" aria-hidden="true">
            {/* Y-axis: max and min labels */}
            <text x={LW - 4} y={toY(maxA) + 4} textAnchor="end" fontSize="7.5"
                fill="rgba(255,255,255,0.28)">{fmtAmt(maxA)}</text>
            <text x={LW - 4} y={toY(minA) + 4} textAnchor="end" fontSize="7.5"
                fill="rgba(255,255,255,0.28)">{fmtAmt(minA)}</text>

            {/* Horizontal guide lines */}
            <line x1={LW} y1={toY(maxA)} x2={TW - PAD} y2={toY(maxA)}
                stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="3 3" />
            <line x1={LW} y1={toY(minA)} x2={TW - PAD} y2={toY(minA)}
                stroke="rgba(255,255,255,0.05)" strokeWidth="0.5" strokeDasharray="3 3" />

            {/* Area fill */}
            <path d={fillPath} fill={fillCol} />

            {/* Sparkline */}
            <polyline points={points.join(" ")} fill="none" stroke={stroke}
                strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />

            {/* Terminal dot */}
            <circle cx={lx} cy={ly} r="3" fill={stroke} />

            {/* X-axis year labels */}
            {xLabels.map(({ yr, x }) => (
                <text key={yr} x={x} y={TH - 2} textAnchor="middle" fontSize="7.5"
                    fill="rgba(255,255,255,0.25)">{yr}</text>
            ))}
        </svg>
    );
}

/** Yield range bar */
function YieldRangeBar({
    current, min, max, percentile,
}: {
    current?: number | null;
    min?: number | null;
    max?: number | null;
    percentile?: number | null;
}) {
    if (!min || !max || !current) return null;
    const fillPct = Math.max(0, Math.min(100, ((current - min) / (max - min)) * 100));

    return (
        <div className="space-y-3">
            {/* Range track */}
            <div className="relative h-2 rounded-full bg-white/8">
                <div
                    className="absolute left-0 top-0 h-2 rounded-full"
                    style={{
                        width: `${fillPct}%`,
                        background: "linear-gradient(90deg, rgba(99,102,241,0.5), #818cf8)",
                    }}
                />
                <div
                    className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-4 w-4 rounded-full bg-white border-2 border-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.5)]"
                    style={{ left: `${fillPct}%` }}
                />
            </div>
            {/* Labels */}
            <div className="flex justify-between text-[10px]">
                <span className="text-white/30">Low: {fmtYield(min)}</span>
                <span className="font-black text-indigo-300">Now: {fmtYield(current)}</span>
                <span className="text-white/30">High: {fmtYield(max)}</span>
            </div>
            {/* Percentile bar */}
            {percentile != null && (
                <div className="rounded-xl bg-white/4 border border-white/7 p-3 space-y-2">
                    <p className="glass-overline text-[9px]">5-Year yield percentile</p>
                    <div className="h-1.5 rounded-full bg-white/8 overflow-hidden">
                        <div
                            className="h-full rounded-full"
                            style={{
                                width: `${percentile}%`,
                                background: "linear-gradient(90deg, #34d399, #6366f1)",
                            }}
                        />
                    </div>
                    <div className="flex justify-between text-[9px] text-white/25">
                        <span>0th</span>
                        <span className="text-indigo-300 font-black">{percentile}th percentile</span>
                        <span>100th</span>
                    </div>
                </div>
            )}
        </div>
    );
}

/** History row for recent dividend changes */
function ChangeRow({ c }: {
    c: { date: string; amount: number; change_pct: number; label: string; direction: string };
}) {
    const Icon = c.direction === "increase" ? ArrowUpRight
        : c.direction === "decrease" ? ArrowDownRight
            : Minus;
    const color = c.direction === "increase" ? "text-emerald-400"
        : c.direction === "decrease" ? "text-rose-400"
            : "text-white/30";
    return (
        <div className="flex items-center justify-between px-4 py-3 border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors">
            <div>
                <p className="text-sm font-bold text-white/80">{fmtDate(c.date)}</p>
                <p className="text-[9px] text-white/25 uppercase tracking-wider mt-0.5">Dividend payment</p>
            </div>
            <div className="text-right">
                <p className="text-sm font-black text-white">${c.amount.toFixed(4)}</p>
                <p className={cn("text-[10px] font-bold flex items-center justify-end gap-0.5 mt-0.5", color)}>
                    <Icon className="h-2.5 w-2.5" />{c.label}
                </p>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-tab panels
// ─────────────────────────────────────────────────────────────────────────────

function OverviewPanel({ data, loading }: { data: DividendOverviewData | null; loading: boolean }) {
    return (
        <div className="space-y-6 animate-fade-up">
            {/* KPI cards */}
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader
                    title="Dividend Overview"
                    subtitle="Current distribution metrics and schedule"
                    action={data ? <StatusBadge status={data.status} /> : undefined}
                />

                {loading ? (
                    <div className="grid md:grid-cols-4 gap-4">
                        {Array.from({ length: 4 }).map((_, i) => <MetricSkeleton key={i} />)}
                    </div>
                ) : data ? (
                    <div className="grid md:grid-cols-4 gap-4">
                        <Metric
                            label="Annual Dividend"
                            value={data.annual_dividend != null ? `$${data.annual_dividend.toFixed(2)}` : "—"}
                            hint={`$${(data.per_period_amount ?? 0).toFixed(4)} / ${fmtFrequency(data.frequency).toLowerCase()} payment`}
                            accent="indigo"
                        />
                        <Metric
                            label="Dividend Yield"
                            value={fmtYield(data.dividend_yield)}
                            hint="At current market price"
                            accent="emerald"
                        />
                        <Metric
                            label="Payout Ratio"
                            value={data.payout_ratio_adj_eps != null
                                ? fmtPctRaw(data.payout_ratio_adj_eps, 0)
                                : "—"}
                            hint="Adjusted EPS basis"
                            accent={
                                (data.payout_ratio_adj_eps ?? 0) < 0.60 ? "emerald" :
                                    (data.payout_ratio_adj_eps ?? 0) < 0.80 ? "amber" : "rose"
                            }
                        />
                        <Metric
                            label="Frequency"
                            value={fmtFrequency(data.frequency)}
                            hint={`${data.frequency_multiplier}× per year`}
                        />
                    </div>
                ) : null}

                <div className="glass-divider my-6" />

                {/* Schedule + Sparkline */}
                <div className="grid md:grid-cols-[1.6fr_1fr] gap-6">
                    <div>
                        <p className="glass-overline mb-4">Dividend Schedule</p>
                        <div className="grid grid-cols-2 gap-3">
                            {[
                                { label: "Last Increase", value: fmtDate(data?.last_increase_date) },
                                { label: "Ex-Dividend Date", value: fmtDate(data?.ex_dividend_date) },
                            ].map(({ label, value }) => (
                                <div
                                    key={label}
                                    className="bg-white/4 border border-white/7 rounded-xl p-3"
                                >
                                    <p className="glass-overline text-[9px]">{label}</p>
                                    <p className="text-sm font-black text-white mt-1.5">{value}</p>
                                </div>
                            ))}
                        </div>

                        {/* Secondary payout metrics */}
                        {data && (
                            <div className="grid grid-cols-2 gap-3 mt-3">
                                <div className="bg-white/4 border border-white/7 rounded-xl p-3">
                                    <p className="glass-overline text-[9px]">FCF Payout</p>
                                    <p className="text-sm font-black text-white mt-1.5">
                                        {data.payout_ratio_fcf != null
                                            ? fmtPctRaw(data.payout_ratio_fcf, 0)
                                            : "—"}
                                    </p>
                                </div>
                                <div className="bg-white/4 border border-white/7 rounded-xl p-3">
                                    <p className="glass-overline text-[9px]">GAAP Payout</p>
                                    <p className="text-sm font-black text-white mt-1.5">
                                        {data.gaap_negative_eps
                                            ? <span className="text-[10px] text-white/40 font-medium">Neg EPS</span>
                                            : data.payout_ratio_gaap != null
                                                ? fmtPctRaw(data.payout_ratio_gaap, 0)
                                                : "—"}
                                    </p>
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Sparkline */}
                    <div className="bg-white/4 border border-white/7 rounded-xl p-4">
                        <p className="glass-overline text-[9px] mb-3">Dividend History</p>
                        {data?.sparkline?.length ? (
                            <DividendSparkline data={data.sparkline} />
                        ) : (
                            <p className="text-xs text-white/20 italic">No history data</p>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

function SafetyPanel({ data, loading }: { data: DividendSafetyData | null; loading: boolean }) {
    return (
        <div className="space-y-6 animate-fade-up">
            {/* Score + Metrics */}
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader
                    title="Dividend Safety"
                    subtitle="Coverage ratios, leverage, and sustainability scorecard"
                />

                <div className="flex flex-col lg:flex-row gap-8">
                    {/* Score ring */}
                    <div className="flex-shrink-0 flex justify-center lg:justify-start">
                        {loading ? (
                            <div className="flex flex-col items-center gap-3">
                                <div className="h-[120px] w-[120px] rounded-full bg-white/5 glass-shimmer" />
                                <div className="h-3 w-24 rounded-full bg-white/8 glass-shimmer" />
                            </div>
                        ) : data ? (
                            <div className="flex flex-col items-center gap-3">
                                <ScoreRing
                                    score={data.composite_score}
                                    category={data.composite_category}
                                    size={120}
                                />
                                <p className={cn(
                                    "text-[10px] font-black uppercase tracking-widest text-center max-w-[140px] leading-relaxed",
                                    categoryColor(data.composite_category),
                                )}>
                                    {data.composite_category === "Good" ? "Dividend Well-Covered"
                                        : data.composite_category === "Caution" ? "Monitor Key Ratios"
                                            : "High Sustainability Risk"}
                                </p>
                            </div>
                        ) : null}
                    </div>

                    <div className="hidden lg:block w-px bg-white/8 self-stretch" />
                    <div className="block lg:hidden h-px bg-white/8" />

                    {/* Metrics table — 2-col grid */}
                    <div className="flex-1 min-w-0">
                        {loading ? (
                            <div className="space-y-3">
                                {Array.from({ length: 6 }).map((_, i) => (
                                    <div key={i} className="h-10 rounded-xl bg-white/5 glass-shimmer" />
                                ))}
                            </div>
                        ) : data ? (
                            <div className="grid md:grid-cols-2 gap-x-8">
                                {/* Left column: first 4 metrics */}
                                <div>
                                    {data.metrics.slice(0, 4).map((m) => (
                                        <SafetyRow key={m.name} m={m} />
                                    ))}
                                </div>
                                {/* Right column: remaining metrics */}
                                <div>
                                    {data.metrics.slice(4).map((m) => (
                                        <SafetyRow key={m.name} m={m} />
                                    ))}
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            </div>

            {/* Policy + Strengths + Risks */}
            {(loading || data) && (
                <div className="grid md:grid-cols-2 gap-6">
                    {/* Policy + Earnings Stability */}
                    <div className="space-y-4">
                        <div className="glass-panel p-6">
                            <SectionHeader title="Earnings Stability" />
                            <div className="bg-white/4 border border-white/7 rounded-xl p-3">
                                {loading ? (
                                    <div className="h-3 w-40 rounded-full bg-white/8 glass-shimmer" />
                                ) : (
                                    <>
                                        <p className="text-sm font-bold text-white/75 capitalize">
                                            {data?.earnings_stability === "high" ? "High — consistent earnings base"
                                                : data?.earnings_stability === "moderate" ? "Moderate — some variability"
                                                    : data?.earnings_stability === "volatile" ? "Volatile — earnings fluctuate"
                                                        : "Insufficient data"}
                                        </p>
                                        <p className="glass-overline text-[8px] mt-1">5-year trend analysis</p>
                                    </>
                                )}
                            </div>
                        </div>

                        <div className="glass-panel p-6">
                            <SectionHeader title="Dividend Policy" />
                            {loading ? (
                                <div className="grid grid-cols-2 gap-2">
                                    {Array.from({ length: 4 }).map((_, i) => (
                                        <div key={i} className="h-14 rounded-xl bg-white/5 glass-shimmer" />
                                    ))}
                                </div>
                            ) : data ? (
                                <div className="grid grid-cols-2 gap-2">
                                    {[
                                        { label: "Growth Trend", value: data.dividend_policy.growth_trend === "growing" ? "Growing" : data.dividend_policy.growth_trend === "flat" ? "Flat" : data.dividend_policy.growth_trend === "declining" ? "Declining" : "—", color: data.dividend_policy.growth_trend === "growing" ? "text-emerald-400" : data.dividend_policy.growth_trend === "declining" ? "text-rose-400" : "" },
                                        { label: "Cut History", value: data.dividend_policy.cut_history, color: data.dividend_policy.has_cut ? "text-rose-400" : "text-emerald-400" },
                                        { label: "Retention Rate", value: data.dividend_policy.retention_rate != null ? fmtPctRaw(data.dividend_policy.retention_rate, 0) : "—", color: "" },
                                    ].map(({ label, value, color }) => (
                                        <div key={label} className="bg-white/4 border border-white/7 rounded-xl p-3">
                                            <p className="glass-overline text-[8px]">{label}</p>
                                            <p className={cn("text-[11px] font-bold text-white mt-1 leading-tight", color)}>
                                                {value}
                                            </p>
                                        </div>
                                    ))}
                                </div>
                            ) : null}
                        </div>
                    </div>

                    {/* Strengths + Risks */}
                    <div className="space-y-4">
                        <div className="glass-panel p-6">
                            <div className="flex items-center gap-2 mb-4">
                                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                                <span className="text-[10px] font-black uppercase tracking-widest text-emerald-400">
                                    Strengths
                                </span>
                            </div>
                            {loading ? (
                                <div className="space-y-2">
                                    {Array.from({ length: 3 }).map((_, i) => (
                                        <div key={i} className="h-3 rounded-full bg-white/5 glass-shimmer" />
                                    ))}
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {(data?.strengths ?? []).map((s, i) => (
                                        <div key={i} className="flex items-start gap-2.5 text-[11px] text-white/65 leading-relaxed">
                                            <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0 mt-1.5" />
                                            {s}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        <div className="glass-panel p-6">
                            <div className="flex items-center gap-2 mb-4">
                                <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                                <span className="text-[10px] font-black uppercase tracking-widest text-rose-400">
                                    Key Risks
                                </span>
                            </div>
                            {loading ? (
                                <div className="space-y-2">
                                    {Array.from({ length: 3 }).map((_, i) => (
                                        <div key={i} className="h-3 rounded-full bg-white/5 glass-shimmer" />
                                    ))}
                                </div>
                            ) : (
                                <div className="space-y-2">
                                    {(data?.key_risks ?? []).map((r, i) => (
                                        <div key={i} className="flex items-start gap-2.5 text-[11px] text-white/65 leading-relaxed">
                                            <div className="h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0 mt-1.5" />
                                            {r}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

function GrowthPanel({ data, loading }: { data: DividendGrowthData | null; loading: boolean }) {
    return (
        <div className="space-y-6 animate-fade-up">
            {/* Score + CAGR table */}
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader
                    title="Dividend Growth"
                    subtitle="Historical momentum and consistency of dividend increases"
                />

                <div className="flex flex-col lg:flex-row gap-8">
                    {/* Score ring */}
                    <div className="flex-shrink-0 flex justify-center lg:justify-start">
                        {loading ? (
                            <div className="flex flex-col items-center gap-3">
                                <div className="h-[120px] w-[120px] rounded-full bg-white/5 glass-shimmer" />
                                <div className="h-3 w-24 rounded-full bg-white/8 glass-shimmer" />
                            </div>
                        ) : data ? (
                            <div className="flex flex-col items-center gap-3">
                                <ScoreRing
                                    score={data.growth_score}
                                    category={data.growth_category}
                                    size={120}
                                />
                                <p className={cn(
                                    "text-[10px] font-black uppercase tracking-widest text-center max-w-[140px] leading-relaxed",
                                    categoryColor(data.growth_category),
                                )}>
                                    {data.growth_category === "Good" ? "Strong Growth Track"
                                        : data.growth_category === "Caution" ? "Inconsistent Growth"
                                            : "Weak Growth Profile"}
                                </p>
                            </div>
                        ) : null}
                    </div>

                    <div className="hidden lg:block w-px bg-white/8 self-stretch" />
                    <div className="block lg:hidden h-px bg-white/8" />

                    {/* CAGR grid */}
                    <div className="flex-1 min-w-0">
                        <p className="glass-overline mb-4">Growth Momentum</p>
                        {loading ? (
                            <div className="grid grid-cols-2 gap-3">
                                {Array.from({ length: 5 }).map((_, i) => <MetricSkeleton key={i} />)}
                            </div>
                        ) : data ? (
                            <div className="grid grid-cols-2 gap-0 border border-white/8 rounded-2xl overflow-hidden">
                                {[
                                    { label: "1-Year Growth", v: data.cagr_1y },
                                    { label: "3-Year CAGR", v: data.cagr_3y },
                                    { label: "5-Year CAGR", v: data.cagr_5y },
                                    { label: "10-Year CAGR", v: data.cagr_10y },
                                ].map(({ label, v }, i) => {
                                    const isNeg = v != null && v < 0;
                                    const border = i % 2 === 1 ? "border-l border-white/5" : "";
                                    return (
                                        <div key={label} className={cn("p-4 border-b border-white/5", border)}>
                                            <p className="glass-overline text-[9px]">{label}</p>
                                            <p className={cn(
                                                "text-xl font-black mt-1.5 tracking-tight",
                                                isNeg ? "text-rose-400" : v === 0 ? "text-white/50" : "text-white",
                                            )}>
                                                {fmtCagr(v)}
                                            </p>
                                        </div>
                                    );
                                })}
                                <div className="col-span-2 p-4 border-t border-white/5">
                                    <p className="glass-overline text-[9px]">Consecutive Years of Increases</p>
                                    <p className={cn(
                                        "text-xl font-black mt-1.5",
                                        data.consecutive_increases >= 5 ? "text-emerald-400" :
                                            data.consecutive_increases >= 1 ? "text-white" : "text-rose-400",
                                    )}>
                                        {data.consecutive_increases === 0 ? "None" : `${data.consecutive_increases} Year${data.consecutive_increases !== 1 ? "s" : ""}`}
                                    </p>
                                </div>
                            </div>
                        ) : null}
                    </div>
                </div>
            </div>

            {/* Recent changes — history table */}
            <div className="glass-panel p-8">
                <SectionHeader
                    title="Recent Dividend Changes"
                    subtitle="Per-payment movement history"
                />
                {loading ? (
                    <div className="space-y-2">
                        {Array.from({ length: 4 }).map((_, i) => (
                            <div key={i} className="h-14 rounded-xl bg-white/5 glass-shimmer" />
                        ))}
                    </div>
                ) : !data?.recent_changes?.length ? (
                    <p className="text-sm text-white/30 italic">No recent dividend data available.</p>
                ) : (
                    <div className="rounded-2xl overflow-hidden border border-white/8">
                        {/* Header */}
                        <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/8">
                            <span className="glass-overline">Date</span>
                            <span className="glass-overline">Amount / Change</span>
                        </div>
                        {data.recent_changes.map((c, i) => (
                            <ChangeRow key={`${c.date}-${i}`} c={c} />
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}

function YieldPanel({ data, loading }: { data: DividendYieldData | null; loading: boolean }) {
    return (
        <div className="space-y-6 animate-fade-up">
            {/* Top KPI tiles */}
            <div className="glass-panel p-8 relative overflow-hidden">
                <AccentLine />
                <SectionHeader
                    title="Yield Analysis"
                    subtitle="Current, historical, and relative yield positioning"
                />

                {loading ? (
                    <div className="grid md:grid-cols-4 gap-4">
                        {Array.from({ length: 4 }).map((_, i) => <MetricSkeleton key={i} />)}
                    </div>
                ) : data ? (
                    <div className="grid md:grid-cols-4 gap-4">
                        <Metric
                            label="Current Yield"
                            value={fmtYield(data.current_yield)}
                            hint="At current market price"
                            accent="emerald"
                        />
                        <Metric
                            label="5-Year Avg Yield"
                            value={fmtYield(data.avg_yield_5y)}
                            hint="Historical mean yield"
                            accent="indigo"
                        />
                        <Metric
                            label="5-Year High"
                            value={fmtYield(data.yield_max_5y)}
                            hint="Peak historical yield"
                            accent="amber"
                        />
                        <Metric
                            label="5-Year Low"
                            value={fmtYield(data.yield_min_5y)}
                            hint="Trough historical yield"
                        />
                    </div>
                ) : null}

                <div className="glass-divider my-6" />

                {/* Range + Theory */}
                <div className="grid md:grid-cols-[1.6fr_1fr] gap-6">
                    <div>
                        <p className="glass-overline mb-5">5-Year Historical Yield Range</p>
                        {loading ? (
                            <div className="space-y-3">
                                <div className="h-2 rounded-full bg-white/8 glass-shimmer" />
                                <div className="h-12 rounded-xl bg-white/5 glass-shimmer" />
                            </div>
                        ) : (
                            <YieldRangeBar
                                current={data?.current_yield}
                                min={data?.yield_min_5y}
                                max={data?.yield_max_5y}
                                percentile={data?.yield_percentile_5y}
                            />
                        )}
                    </div>

                    <div className="space-y-4">
                        {/* Yield Theory */}
                        <div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/5 p-5">
                            <p className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70 mb-3">
                                Yield Theory Signal
                            </p>
                            {loading ? (
                                <div className="space-y-2">
                                    <div className="h-2 w-full rounded-full bg-white/5 glass-shimmer" />
                                    <div className="h-2 w-4/5 rounded-full bg-white/5 glass-shimmer" />
                                </div>
                            ) : (
                                <p className="text-[12px] leading-relaxed text-white/60 italic border-l-2 border-indigo-500/50 pl-3">
                                    {data?.theory_signal ?? "Insufficient history to generate a yield signal."}
                                </p>
                            )}
                        </div>

                        {/* Relative vs sector/market — optional */}
                        <div className="glass-card rounded-xl p-4 space-y-3">
                            <p className="glass-overline text-[9px]">Relative Positioning</p>
                            {[
                                { label: "vs Sector avg", v: data?.yield_vs_sector },
                                { label: "vs Market avg", v: data?.yield_vs_market },
                            ].map(({ label, v }) => (
                                <div key={label} className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
                                    <span className="text-[11px] text-white/60">{label}</span>
                                    <span className="text-sm font-black text-white/30">
                                        {v != null ? `${v.toFixed(1)}×` : "—"}
                                    </span>
                                </div>
                            ))}
                            {(!data?.yield_vs_sector && !data?.yield_vs_market) && (
                                <p className="text-[10px] text-white/20 italic">
                                    Sector &amp; market comparison data coming soon
                                </p>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// No-dividend state
// ─────────────────────────────────────────────────────────────────────────────
function NoDividendState() {
    return (
        <div className="glass-panel p-12 flex flex-col items-center text-center space-y-6 animate-fade-up">
            <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-white/5 border border-white/10">
                <TrendingDown className="h-9 w-9 text-white/20" />
            </div>
            <div>
                <h3 className="text-xl font-black text-white tracking-tight">No Dividend</h3>
                <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">
                    This company does not currently pay a dividend. Analysis is unavailable.
                </p>
            </div>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main exported component
// ─────────────────────────────────────────────────────────────────────────────
export function DividendPanel({ symbol }: { symbol: string }) {
    const [activeTab, setActiveTab] = useState<DivTab>("overview");
    const { data, loading, error, paysDividend } = useDividendAnalysis(symbol);

    return (
        <div className="space-y-6 animate-fade-up">
            {/* Error banner */}
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
                    <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                    <p className="text-sm text-white/60">{error}</p>
                </div>
            )}

            {/* Sub-tab bar — same CSS pattern as MethodSelector */}
            <div className="flex items-center gap-2 flex-wrap" role="tablist">
                {DIV_TABS.map(({ id, label }) => (
                    <button
                        key={id}
                        role="tab"
                        aria-selected={activeTab === id}
                        onClick={() => setActiveTab(id)}
                        className={cn(
                            "px-5 py-2 rounded-xl text-[10px] font-black uppercase tracking-[0.2em]",
                            "border transition-all duration-200",
                            activeTab === id
                                ? "bg-indigo-600 border-indigo-400/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)]"
                                : "bg-white/5 border-white/8 text-white/30 hover:text-white/60 hover:bg-white/8",
                        )}
                    >
                        {label}
                    </button>
                ))}
            </div>

            {/* Content */}
            {paysDividend === false && !loading ? (
                <NoDividendState />
            ) : (
                <>
                    {activeTab === "overview" && (
                        <OverviewPanel data={data?.overview ?? null} loading={loading} />
                    )}
                    {activeTab === "safety" && (
                        <SafetyPanel data={data?.safety ?? null} loading={loading} />
                    )}
                    {activeTab === "growth" && (
                        <GrowthPanel data={data?.growth ?? null} loading={loading} />
                    )}
                    {activeTab === "yield" && (
                        <YieldPanel data={data?.yield_analysis ?? null} loading={loading} />
                    )}
                </>
            )}
        </div>
    );
}