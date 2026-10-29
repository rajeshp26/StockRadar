"use client";
import React, { useMemo } from "react";
import { cn } from "@/lib/utils";
import {
    TrendingDown, AlertTriangle, TrendingUp, CheckCircle2, Info,
} from "lucide-react";
import {
    BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    LineChart, Line,
} from "recharts";
import { useDividendAnalysis } from "../hooks/useDividendAnalysis";
import {
    ScoreRing, SectionHeader, Metric,
    fmtCurrency, fmtPct,
} from "./shared-ui";
import type {
    DividendAnalysis, DividendRating, DividendDataResolution, DividendResolutionLevel,
} from "../types/analysis.types";

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

function RatingTag({ rating, text }: { rating: DividendRating; text?: string }) {
    const styles: Record<DividendRating, string> = {
        safe: "bg-emerald-500/12 border-emerald-500/25 text-emerald-400",
        moderate: "bg-amber-500/12 border-amber-500/25 text-amber-400",
        borderline: "bg-orange-500/10 border-orange-500/25 text-orange-400",
        risk: "bg-rose-500/12 border-rose-500/25 text-rose-400",
        info: "bg-indigo-500/12 border-indigo-500/25 text-indigo-400",
    };
    const labels: Record<DividendRating, string> = {
        safe: "Safe", moderate: "Moderate", borderline: "Borderline",
        risk: "Risk", info: "Info",
    };
    return (
        <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-[10px] font-black uppercase tracking-widest border", styles[rating])}>
            {text ?? labels[rating]}
        </span>
    );
}

function MetricSkeleton() {
    return (
        <div className="glass-stat space-y-3">
            <div className="h-2 w-16 rounded-full bg-white/10 glass-shimmer" />
            <div className="h-8 w-24 rounded-lg bg-white/10 glass-shimmer" />
        </div>
    );
}

/** Yield range bar — adapted from the existing component */
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
            <div className="flex justify-between text-[10px]">
                <span className="text-white/30">Low: {fmtYield(min)}</span>
                <span className="font-black text-indigo-300">Now: {fmtYield(current)}</span>
                <span className="text-white/30">High: {fmtYield(max)}</span>
            </div>
            {percentile != null && (
                <div className="space-y-2">
                    <p className="glass-overline text-[9px]">5-Year yield percentile</p>
                    <div className="flex items-baseline gap-2">
                        <span className="text-2xl font-black text-white">{percentile}th</span>
                        <span className="text-xs text-white/40">percentile</span>
                    </div>
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
                        <span>100th</span>
                    </div>
                </div>
            )}
        </div>
    );
}

/** Arrow indicator for change direction */
function ChangeDirection({ change_pct, direction }: { change_pct: number; direction: string }) {
    if (direction === "flat") return <span className="text-white/40 font-bold">Flat</span>;
    const isUp = direction === "increase";
    const label = `${isUp ? "+" : ""}${(change_pct * 100).toFixed(1)}%`;
    return (
        <span className={cn("font-bold flex items-center gap-0.5", isUp ? "text-emerald-400" : "text-rose-400")}>
            {isUp ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
            {label}
        </span>
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// Chart components (memoized)
// ─────────────────────────────────────────────────────────────────────────────

const DividendBarChart = React.memo(function DividendBarChart({ data }: { data: { year: string; amount: number }[] }) {
    if (!data.length) {
        return <p className="text-sm text-white/30 italic pt-8 text-center">No dividend history data</p>;
    }
    return (
        <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="year" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} tickFormatter={(v: number) => `$${v.toFixed(2)}`} />
                <Tooltip
                    contentStyle={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                    formatter={(value: number) => [`$${value.toFixed(2)}`, "Annual Dividend"]}
                />
                <Bar dataKey="amount" radius={[8, 8, 0, 0]} fill="#818cf8" />
            </BarChart>
        </ResponsiveContainer>
    );
});

const GrowthLineChart = React.memo(function GrowthLineChart({ data }: { data: { year: string; amount: number }[] }) {
    if (!data.length) {
        return <p className="text-sm text-white/30 italic pt-8 text-center">No dividend history data</p>;
    }
    return (
        <ResponsiveContainer width="100%" height={250}>
            <LineChart data={data}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis dataKey="year" stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} />
                <YAxis stroke="rgba(255,255,255,0.3)" tick={{ fontSize: 10 }} tickFormatter={(v: number) => `$${v.toFixed(2)}`} />
                <Tooltip
                    contentStyle={{ backgroundColor: "#111827", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }}
                    formatter={(value: number) => [`$${value.toFixed(2)}`, "Annual Dividend"]}
                />
                <Line type="monotone" dataKey="amount" stroke="#22c55e" strokeWidth={3} dot={{ r: 4, fill: "#22c55e" }} />
            </LineChart>
        </ResponsiveContainer>
    );
});

// ─────────────────────────────────────────────────────────────────────────────
// No-dividend state
// ─────────────────────────────────────────────────────────────────────────────
function DataResolutionNotice({ resolution }: { resolution?: DividendDataResolution }) {
    if (!resolution || !resolution.sources?.length) return null;
    const eff = resolution.effective;
    if (eff === 'daily') return null;

    const labels: Record<DividendResolutionLevel, string> = {
        daily: 'Daily',
        weekly: 'Weekly',
        monthly: 'Monthly',
        quarterly: 'Quarterly',
        unknown: 'Unknown',
    };

    const primary = resolution.sources[0];
    const name = primary?.brokerage_name || primary?.brokerage_code || 'your broker';

    return (
        <div className="flex items-start gap-3 p-4 rounded-2xl bg-amber-500/8 border border-amber-500/25">
            <AlertTriangle className="h-4 w-4 text-amber-400 flex-shrink-0 mt-0.5" />
            <div className="space-y-1">
                <p className="text-sm text-white/80">
                    <span className="font-semibold text-white">Dividend data resolution: {labels[eff]}</span> — available from {name}.
                </p>
                <p className="text-xs text-white/50 leading-relaxed">
                    {eff === 'monthly'
                        ? 'Dividend data from Wealthsimple is provided at monthly/statement level in the exported CSV. Per-day cash flow breakdown is not available from this feed, so values shown are aggregated to the available resolution.'
                        : eff === 'weekly'
                        ? 'Dividend data is provided at weekly resolution from your connected brokerage. Some intraday/per-day timing details may be aggregated.'
                        : eff === 'quarterly'
                        ? 'Dividend data is provided at quarterly resolution from your connected brokerage. Timing details may be limited.'
                        : 'Dividend data resolution is limited from your connected brokerage. Some timing/details may be aggregated.'}
                    {primary?.note ? ` ${primary.note}` : ''}
                </p>
                {resolution.sources.length > 1 && (
                    <p className="text-[11px] text-white/40">
                        Sources: {resolution.sources.map(s => s.brokerage_name || s.brokerage_code).join(', ')}
                    </p>
                )}
            </div>
        </div>
    );
}

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
    const { data, loading, error, paysDividend } = useDividendAnalysis(symbol);

    // ── Derived data ──────────────────────────────────────────────────────────

    const chartData = useMemo(() => {
        const totals = data?.growth?.annual_totals;
        if (!totals || !Object.keys(totals).length) return [];
        return Object.entries(totals)
            .map(([year, amount]) => ({ year, amount }))
            .sort((a, b) => a.year.localeCompare(b.year));
    }, [data?.growth?.annual_totals]);

    const annualDividend = data?.overview?.annual_dividend;
    const perPeriod = data?.overview?.per_period_amount;
    const dividendYield = data?.overview?.dividend_yield;
    const payoutRatio = data?.overview?.payout_ratio_adj_eps;
    const frequency = data?.overview?.frequency;
    const freqMult = data?.overview?.frequency_multiplier;

    const lastIncrease = data?.overview?.last_increase_date;
    const exDivDate = data?.overview?.ex_dividend_date;
    const fcfPayout = data?.overview?.payout_ratio_fcf;
    const gaapPayout = data?.overview?.payout_ratio_gaap;
    const status = data?.overview?.status;

    const safetyScore = data?.safety?.composite_score;
    const safetyCategory = data?.safety?.composite_category;
    const safetyMetrics = data?.safety?.metrics ?? [];

    const growthScore = data?.growth?.growth_score;
    const growthCategory = data?.growth?.growth_category;
    const cagr1y = data?.growth?.cagr_1y;
    const cagr3y = data?.growth?.cagr_3y;
    const cagr5y = data?.growth?.cagr_5y;
    const cagr10y = data?.growth?.cagr_10y;
    const consecutiveInc = data?.growth?.consecutive_increases;

    const yieldCurr = data?.yield_analysis?.current_yield;
    const yieldAvg5y = data?.yield_analysis?.avg_yield_5y;
    const yieldMax5y = data?.yield_analysis?.yield_max_5y;
    const yieldMin5y = data?.yield_analysis?.yield_min_5y;
    const yieldPctl = data?.yield_analysis?.yield_percentile_5y;
    const theorySignal = data?.yield_analysis?.theory_signal;

    const policy = data?.safety?.dividend_policy;
    const strengths = data?.safety?.strengths ?? [];
    const keyRisks = data?.safety?.key_risks ?? [];
    const recentChanges = data?.growth?.recent_changes ?? [];

    // ── Render ────────────────────────────────────────────────────────────────

    return (
        <div className="space-y-6 animate-fade-up">
            {/* Error banner */}
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
                    <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                    <p className="text-sm text-white/60">{error}</p>
                </div>
            )}

            {data?.data_resolution && (
                <DataResolutionNotice resolution={data.data_resolution} />
            )}

            {paysDividend === false && !loading ? (
                <NoDividendState />
            ) : (
                <>
                    {/* ── Top Bar ─────────────────────────────────────────────── */}
                    <div className="flex justify-between items-start gap-5 flex-wrap">
                        <div>
                            <h1 className="text-2xl font-black text-white tracking-tight">Dividend Dashboard</h1>
                            <p className="text-sm text-white/35 mt-1">
                                Current distribution metrics, dividend safety, growth profile, yield analysis, and recent payout activity.
                            </p>
                            <div className="flex gap-2 flex-wrap mt-3">
                                {loading ? (
                                    <>
                                        <div className="h-6 w-20 rounded-full bg-white/8 glass-shimmer" />
                                        <div className="h-6 w-28 rounded-full bg-white/8 glass-shimmer" />
                                        <div className="h-6 w-32 rounded-full bg-white/8 glass-shimmer" />
                                        <div className="h-6 w-24 rounded-full bg-white/8 glass-shimmer" />
                                    </>
                                ) : data ? (
                                    <>
                                        <span className={cn(
                                            "glass-badge",
                                            status === "growing" ? "glass-badge-buy" :
                                            status === "stable" ? "glass-badge-hold" :
                                            "glass-badge-sell",
                                        )}>
                                            {status === "growing" && <TrendingUp className="h-2.5 w-2.5 mr-1" />}
                                            {status === "declining" && <TrendingDown className="h-2.5 w-2.5 mr-1" />}
                                            {status === "stable" && <CheckCircle2 className="h-2.5 w-2.5 mr-1" />}
                                            {status === "growing" ? "Growing" : status === "stable" ? "Stable" : "Declining"}
                                        </span>
                                        <span className={cn(
                                            "glass-badge",
                                            safetyCategory === "Good" ? "glass-badge-buy" :
                                            safetyCategory === "Caution" ? "glass-badge-hold" :
                                            "glass-badge-sell",
                                        )}>
                                            Safety: {safetyCategory}
                                        </span>
                                        {policy?.has_cut && (
                                            <span className="glass-badge glass-badge-sell">
                                                Major Cut {policy.cut_year ? `(${policy.cut_year})` : ""}
                                            </span>
                                        )}
                                        <span className="glass-badge-dark">
                                            {fmtFrequency(frequency || "quarterly")} Payer
                                        </span>
                                        {data?.data_resolution?.effective && data.data_resolution.effective !== 'daily' && (
                                            <span className="glass-badge" title="Dividend data granularity from your connected brokerage">
                                                <Info className="h-2.5 w-2.5 mr-1" />
                                                Data: {data.data_resolution.effective === 'monthly' ? 'Monthly' : data.data_resolution.effective === 'weekly' ? 'Weekly' : data.data_resolution.effective === 'quarterly' ? 'Quarterly' : 'Limited'}
                                            </span>
                                        )}
                                    </>
                                ) : null}
                            </div>
                        </div>
                        <div className="flex gap-2 flex-wrap">
                            {["Overview", "Safety", "Growth", "Yield", "History"].map((chip) => (
                                <span key={chip} className="glass-chip">{chip}</span>
                            ))}
                        </div>
                    </div>

                    {/* ── 12-Column Grid ─────────────────────────────────────── */}
                    <div className="grid grid-cols-12 gap-4">

                        {/* ── Hero Section (span-12) ─────────────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-12">
                            <AccentLine />
                            <div className="grid md:grid-cols-[2fr_1fr] gap-6">
                                {/* Left: Metrics */}
                                <div>
                                    <SectionHeader
                                        title="Dividend Overview"
                                        subtitle="Current distribution metrics and schedule"
                                    />
                                    {loading ? (
                                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                                            {Array.from({ length: 4 }).map((_, i) => <MetricSkeleton key={i} />)}
                                        </div>
                                    ) : data ? (
                                        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                                            <Metric
                                                label="Annual Dividend"
                                                value={annualDividend != null ? `$${annualDividend.toFixed(2)}` : "—"}
                                                hint={`$${(perPeriod ?? 0).toFixed(4)} / ${fmtFrequency(frequency || "").toLowerCase()} payment`}
                                                accent="indigo"
                                            />
                                            <Metric
                                                label="Dividend Yield"
                                                value={fmtYield(dividendYield)}
                                                hint="At current market price"
                                                accent="emerald"
                                            />
                                            <Metric
                                                label="Payout Ratio"
                                                value={payoutRatio != null ? fmtPctRaw(payoutRatio, 0) : "—"}
                                                hint="Adjusted EPS basis"
                                                accent={
                                                    (payoutRatio ?? 0) < 0.60 ? "emerald" :
                                                    (payoutRatio ?? 0) < 0.80 ? "amber" : "rose"
                                                }
                                            />
                                            <Metric
                                                label="Frequency"
                                                value={fmtFrequency(frequency || "")}
                                                hint={`${freqMult ?? "?"}× per year`}
                                            />
                                        </div>
                                    ) : null}
                                </div>

                                {/* Right: Schedule + Signal */}
                                <div className="flex flex-col gap-4">
                                    {/* Schedule */}
                                    <div className="bg-white/4 border border-white/8 rounded-2xl p-4">
                                        <p className="glass-overline mb-3">Dividend Schedule</p>
                                        <div className="space-y-3">
                                            {[
                                                { label: "Last Increase", value: fmtDate(lastIncrease) },
                                                { label: "Ex-Dividend Date", value: fmtDate(exDivDate) },
                                                { label: "FCF Payout", value: fcfPayout != null ? fmtPctRaw(fcfPayout, 0) : "—" },
                                                { label: "GAAP Payout", value: gaapPayout != null ? fmtPctRaw(gaapPayout, 0) : "—" },
                                            ].map(({ label, value }) => (
                                                <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/6 last:border-0">
                                                    <span className="text-xs text-white/50">{label}</span>
                                                    <span className="text-sm font-bold text-white">{value}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* Signal box */}
                                    {!loading && data && (
                                        <div className="rounded-2xl border border-teal-500/20 bg-teal-500/8 px-4 py-3">
                                            <p className="text-[9px] font-black uppercase tracking-widest text-teal-400/80 mb-2">
                                                Investor Signal
                                            </p>
                                            <p className="text-xs leading-relaxed text-white/70">
                                                Yield is elevated at <strong className="text-white">${((dividendYield ?? 0) * 100).toFixed(2)}%</strong>,
                                                while cash flow coverage remains healthy.
                                                However, leverage and prior cut history suggest investors should prioritize
                                                safety monitoring over pure yield.
                                            </p>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* ── Dividend History Chart (span-8) ─────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-8 lg:col-span-8 max-lg:col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Dividend History"
                                subtitle="Annual dividend trend over time"
                            />
                            {loading ? (
                                <div className="h-[250px] rounded-xl bg-white/5 glass-shimmer" />
                            ) : (
                                <DividendBarChart data={chartData} />
                            )}
                        </div>

                        {/* ── Growth Score (span-4) ──────────────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-4 max-lg:col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Dividend Growth"
                                subtitle="Historical momentum and consistency"
                            />
                            {loading ? (
                                <div className="flex flex-col items-center gap-4">
                                    <div className="h-[110px] w-[110px] rounded-full bg-white/5 glass-shimmer" />
                                    <div className="h-4 w-32 rounded-full bg-white/8 glass-shimmer" />
                                    {Array.from({ length: 3 }).map((_, i) => (
                                        <div key={i} className="h-3 w-full rounded-full bg-white/5 glass-shimmer" />
                                    ))}
                                </div>
                            ) : data ? (
                                <>
                                    <div className="flex items-center gap-4 mb-5">
                                        <ScoreRing
                                            score={growthScore}
                                            category={growthCategory}
                                            size={110}
                                        />
                                        <div>
                                            <h3 className={cn(
                                                "text-lg font-black",
                                                growthCategory === "Good" ? "text-emerald-400" :
                                                growthCategory === "Caution" ? "text-amber-400" :
                                                "text-rose-400",
                                            )}>
                                                {growthCategory === "Good" ? "Strong Growth Track" :
                                                 growthCategory === "Caution" ? "Inconsistent Growth" :
                                                 "Poor Suitability"}
                                            </h3>
                                            <p className="text-xs text-white/40 mt-0.5">
                                                {growthCategory === "Good" ? "Consistent growth history" :
                                                 growthCategory === "Caution" ? "Mixed growth signals" :
                                                 "Weak growth profile"}
                                            </p>
                                        </div>
                                    </div>
                                    <div className="space-y-3">
                                        {[
                                            { label: "Growth Trend", value: policy?.growth_trend === "growing" ? "Growing" : policy?.growth_trend === "flat" ? "Flat" : policy?.growth_trend === "declining" ? "Declining" : "—", color: "text-white" },
                                            { label: "Cut History", value: policy?.has_cut ? (policy.cut_year ? `Major cut (${policy.cut_year})` : "Major cut") : "No cuts on record", color: policy?.has_cut ? "text-rose-400" : "text-emerald-400" },
                                            { label: "Consecutive Years of Increases", value: consecutiveInc === 0 ? "None" : `${consecutiveInc} Year${consecutiveInc !== 1 ? "s" : ""}`, color: consecutiveInc && consecutiveInc >= 5 ? "text-emerald-400" : "text-white" },
                                            { label: "Retention Rate", value: policy?.retention_rate != null ? fmtPctRaw(policy.retention_rate, 0) : "—", color: "text-white/50" },
                                        ].map(({ label, value, color }) => (
                                            <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/6 last:border-0">
                                                <span className="text-xs text-white/50">{label}</span>
                                                <span className={cn("text-sm font-bold text-right", color)}>{value}</span>
                                            </div>
                                        ))}
                                    </div>
                                </>
                            ) : null}
                        </div>

                        {/* ── Dividend Safety (span-8) ───────────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-8 max-lg:col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Dividend Safety"
                                subtitle="Coverage ratios, leverage, and sustainability scorecard"
                            />
                            {loading ? (
                                <div className="flex gap-6">
                                    <div className="h-[110px] w-[110px] rounded-full bg-white/5 glass-shimmer flex-shrink-0" />
                                    <div className="flex-1 grid grid-cols-2 gap-3">
                                        {Array.from({ length: 8 }).map((_, i) => (
                                            <div key={i} className="h-20 rounded-xl bg-white/5 glass-shimmer" />
                                        ))}
                                    </div>
                                </div>
                            ) : data ? (
                                <>
                                    <div className="flex flex-col lg:flex-row gap-6">
                                        <div className="flex-shrink-0 flex flex-col items-center gap-2">
                                            <ScoreRing
                                                score={safetyScore}
                                                category={safetyCategory}
                                                size={110}
                                            />
                                            <p className={cn(
                                                "text-[10px] font-black uppercase tracking-widest text-center max-w-[120px]",
                                                safetyCategory === "Good" ? "text-emerald-400" :
                                                safetyCategory === "Caution" ? "text-amber-400" :
                                                "text-rose-400",
                                            )}>
                                                {safetyCategory === "Good" ? "Well-Covered" :
                                                 safetyCategory === "Caution" ? "Monitor Ratios" :
                                                 "At Risk"}
                                            </p>
                                        </div>
                                        <div className="flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3">
                                            {safetyMetrics.map((m) => (
                                                <div key={m.name} className="bg-white/4 border border-white/8 rounded-xl p-3">
                                                    <div className="flex items-start justify-between gap-2 mb-2">
                                                        <div>
                                                            <p className="text-xs font-bold text-white/80">{m.name}</p>
                                                            <p className="text-[9px] text-white/30 mt-0.5">Benchmark: {m.benchmark}</p>
                                                        </div>
                                                        <RatingTag rating={m.rating} text={m.info_note ?? undefined} />
                                                    </div>
                                                    <p className="text-xl font-black text-white tabular-nums">{m.formatted}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                    <div className="mt-4 text-xs text-white/40">
                                        Dividend policy: <strong className="text-white/80">{policy?.growth_trend === "growing" ? "Growing" : policy?.growth_trend === "flat" ? "Flat" : policy?.growth_trend === "declining" ? "Declining" : "—"}</strong>
                                        {policy?.has_cut && <> · Cut history: <strong className="text-rose-400">Major cut {policy.cut_year ? `(${policy.cut_year})` : ""}</strong></>}
                                    </div>
                                </>
                            ) : null}
                        </div>

                        {/* ── Strengths & Risks (span-4) ─────────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-4 max-lg:col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Strengths & Risks"
                                subtitle="Plain-language scorecard"
                            />
                            {loading ? (
                                <div className="space-y-4">
                                    {Array.from({ length: 5 }).map((_, i) => (
                                        <div key={i} className="h-4 rounded-full bg-white/5 glass-shimmer" />
                                    ))}
                                </div>
                            ) : data ? (
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/6 p-4">
                                        <div className="flex items-center gap-2 mb-3">
                                            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                                            <span className="text-[10px] font-black uppercase tracking-widest text-emerald-400">
                                                Strengths
                                            </span>
                                        </div>
                                        <ul className="space-y-2">
                                            {strengths.map((s, i) => (
                                                <li key={i} className="flex items-start gap-2 text-[11px] text-white/65 leading-relaxed">
                                                    <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 flex-shrink-0 mt-1.5" />
                                                    {s}
                                                </li>
                                            ))}
                                            {strengths.length === 0 && (
                                                <li className="text-[11px] text-white/30 italic">No notable strengths identified</li>
                                            )}
                                        </ul>
                                    </div>
                                    <div className="rounded-xl border border-rose-500/20 bg-rose-500/6 p-4">
                                        <div className="flex items-center gap-2 mb-3">
                                            <AlertTriangle className="h-3.5 w-3.5 text-rose-400" />
                                            <span className="text-[10px] font-black uppercase tracking-widest text-rose-400">
                                                Key Risks
                                            </span>
                                        </div>
                                        <ul className="space-y-2">
                                            {keyRisks.map((r, i) => (
                                                <li key={i} className="flex items-start gap-2 text-[11px] text-white/65 leading-relaxed">
                                                    <div className="h-1.5 w-1.5 rounded-full bg-rose-400 flex-shrink-0 mt-1.5" />
                                                    {r}
                                                </li>
                                            ))}
                                            {keyRisks.length === 0 && (
                                                <li className="text-[11px] text-white/30 italic">No significant risks identified</li>
                                            )}
                                        </ul>
                                    </div>
                                </div>
                            ) : null}
                        </div>

                        {/* ── Growth Momentum (span-12) ──────────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Growth Momentum"
                                subtitle="Historical growth rates and consistency"
                            />
                            {loading ? (
                                <div className="space-y-4">
                                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
                                        {Array.from({ length: 5 }).map((_, i) => <MetricSkeleton key={i} />)}
                                    </div>
                                    <div className="h-[250px] rounded-xl bg-white/5 glass-shimmer" />
                                </div>
                            ) : data ? (
                                <>
                                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
                                        {[
                                            { label: "1-Year Growth", v: cagr1y },
                                            { label: "3-Year CAGR", v: cagr3y },
                                            { label: "5-Year CAGR", v: cagr5y },
                                            { label: "10-Year CAGR", v: cagr10y },
                                            { label: "Consecutive Increases", v: consecutiveInc as number | null, isCount: true },
                                        ].map(({ label, v, isCount }) => {
                                            const isNeg = !isCount && v != null && v < 0;
                                            const isZero = !isCount && v === 0;
                                            const display = isCount
                                                ? (v === 0 ? "None" : `${v} Year${v !== 1 ? "s" : ""}`)
                                                : fmtCagr(v as number | null | undefined);
                                            return (
                                                <div key={label} className="bg-white/4 border border-white/8 rounded-xl p-4">
                                                    <p className="glass-overline text-[9px]">{label}</p>
                                                    <p className={cn(
                                                        "text-2xl font-black mt-1.5",
                                                        isNeg ? "text-rose-400" :
                                                        isZero ? "text-white/50" :
                                                        "text-white",
                                                    )}>
                                                        {display}
                                                    </p>
                                                </div>
                                            );
                                        })}
                                    </div>
                                    <GrowthLineChart data={chartData} />
                                </>
                            ) : null}
                        </div>

                        {/* ── Recent Dividend Changes (span-6) ──────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-6 max-lg:col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Recent Dividend Changes"
                                subtitle="Per-payment movement history"
                            />
                            {loading ? (
                                <div className="space-y-3">
                                    {Array.from({ length: 6 }).map((_, i) => (
                                        <div key={i} className="h-12 rounded-xl bg-white/5 glass-shimmer" />
                                    ))}
                                </div>
                            ) : !recentChanges.length ? (
                                <p className="text-sm text-white/30 italic">No recent dividend data available.</p>
                            ) : (
                                <div className="space-y-1">
                                    {recentChanges.map((c, i) => (
                                        <div key={`${c.date}-${i}`} className="flex items-center justify-between py-3 px-1 border-b border-white/6 last:border-0">
                                            <div className="flex items-center gap-4">
                                                <span className="text-xs text-white/50 font-semibold w-[100px]">{fmtDate(c.date)}</span>
                                                <div>
                                                    <p className="text-sm font-bold text-white/90">Dividend payment</p>
                                                    <p className="text-[11px] text-white/30">${c.amount.toFixed(4)}</p>
                                                </div>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-sm font-black text-white">${c.amount.toFixed(4)}</p>
                                                <ChangeDirection change_pct={c.change_pct} direction={c.direction} />
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>

                        {/* ── Yield Analysis (span-6) ────────────────────────── */}
                        <div className="glass-panel p-8 relative overflow-hidden col-span-6 max-lg:col-span-12">
                            <AccentLine />
                            <SectionHeader
                                title="Yield Analysis"
                                subtitle="Current, historical, and relative yield positioning"
                            />
                            {loading ? (
                                <>
                                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                                        {Array.from({ length: 4 }).map((_, i) => <MetricSkeleton key={i} />)}
                                    </div>
                                    <div className="h-40 rounded-xl bg-white/5 glass-shimmer" />
                                </>
                            ) : data ? (
                                <>
                                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                                        <Metric label="Current Yield" value={fmtYield(yieldCurr)} hint="At current market price" accent="emerald" />
                                        <Metric label="5-Year Avg Yield" value={fmtYield(yieldAvg5y)} hint="Historical mean yield" accent="indigo" />
                                        <Metric label="5-Year High" value={fmtYield(yieldMax5y)} hint="Peak historical yield" accent="amber" />
                                        <Metric label="5-Year Low" value={fmtYield(yieldMin5y)} hint="Trough historical yield" />
                                    </div>

                                    {/* Range bar */}
                                    <div className="bg-white/4 border border-white/8 rounded-xl p-5">
                                        <p className="glass-overline mb-4">5-Year Historical Yield Range</p>
                                        <YieldRangeBar
                                            current={yieldCurr}
                                            min={yieldMin5y}
                                            max={yieldMax5y}
                                            percentile={yieldPctl}
                                        />

                                        {/* Theory signal */}
                                        {theorySignal && (
                                            <div className="mt-4 rounded-xl border border-indigo-500/15 bg-indigo-500/5 p-4">
                                                <p className="text-[11px] leading-relaxed text-white/60 italic border-l-2 border-indigo-500/50 pl-3">
                                                    {theorySignal}
                                                </p>
                                            </div>
                                        )}

                                        {/* Relative positioning */}
                                        <div className="mt-4 space-y-2">
                                            <p className="glass-overline text-[9px]">Relative Positioning</p>
                                            {[
                                                { label: "vs Sector avg", v: data?.yield_analysis?.yield_vs_sector },
                                                { label: "vs Market avg", v: data?.yield_analysis?.yield_vs_market },
                                            ].map(({ label, v }) => (
                                                <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/5 last:border-0">
                                                    <span className="text-xs text-white/50">{label}</span>
                                                    <span className="text-sm font-black text-white/30">
                                                        {v != null ? `${v.toFixed(1)}×` : "—"}
                                                    </span>
                                                </div>
                                            ))}
                                            {!data?.yield_analysis?.yield_vs_sector && !data?.yield_analysis?.yield_vs_market && (
                                                <p className="text-[10px] text-white/20 italic">
                                                    Sector &amp; market comparison data coming soon
                                                </p>
                                            )}
                                        </div>
                                    </div>
                                </>
                            ) : null}
                        </div>

                    </div>
                </>
            )}
        </div>
    );
}
