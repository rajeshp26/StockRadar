"use client";
// web/src/features/analysis/components/murphy-panel.tsx
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { RefreshCw, AlertTriangle, Sparkles } from "lucide-react";
import { useMurphyAnalysis } from "../hooks/useMurphyAnalysis";
import {
    Metric,
    SectionHeader,
} from "./shared-ui";
import type { TrendAnalysis, MurphySynthesis, PriceLevel } from "../types/analysis.types";

// ── Skeleton ───────────────────────────────────────────────────────────────────

function Shimmer({ className }: { className?: string }) {
    return <div className={cn("rounded-xl bg-white/5 glass-shimmer", className)} />;
}

function MetricSkeleton() {
    return (
        <div className="glass-stat space-y-3">
            <Shimmer className="h-2 w-16" />
            <Shimmer className="h-8 w-24" />
        </div>
    );
}

// ── Signal badge ────────────────────────────────────────────────────────────────

function SignalBadge({ signal }: { signal: string }) {
    const config: Record<string, string> = {
        strong_buy: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
        buy: "bg-teal-500/15 border-teal-500/30 text-teal-400",
        neutral: "bg-white/8 border-white/15 text-white/50",
        sell: "bg-amber-500/15 border-amber-500/30 text-amber-400",
        strong_sell: "bg-rose-500/15 border-rose-500/30 text-rose-400",
        // trend
        uptrend: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
        downtrend: "bg-rose-500/15 border-rose-500/30 text-rose-400",
        sideways: "bg-white/8 border-white/15 text-white/50",
        // volume
        accumulation: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
        distribution: "bg-rose-500/15 border-rose-500/30 text-rose-400",
        // slope / position
        rising: "bg-emerald-500/12 border-emerald-500/25 text-emerald-400",
        falling: "bg-rose-500/12 border-rose-500/25 text-rose-400",
        flat: "bg-white/8 border-white/12 text-white/40",
        above: "bg-emerald-500/12 border-emerald-500/25 text-emerald-400",
        below: "bg-rose-500/12 border-rose-500/25 text-rose-400",
    };
    const cls = config[signal] ?? "bg-white/8 border-white/12 text-white/50";
    const label = signal.replace(/_/g, " ");
    return (
        <span
            className={cn(
                "px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border",
                cls,
            )}
        >
            {label}
        </span>
    );
}

// ── Detail row ─────────────────────────────────────────────────────────────────

function DetailRow({
    label,
    value,
    badge,
}: {
    label: string;
    value: string;
    badge?: string;
}) {
    return (
        <div className="flex items-center justify-between py-2.5 border-b border-white/5 last:border-0 gap-3">
            <span className="text-[11px] font-black uppercase tracking-widest text-white/30 flex-shrink-0">
                {label}
            </span>
            <div className="flex items-center gap-2">
                {badge && <SignalBadge signal={badge} />}
                <span className="text-sm font-bold text-white/70 tabular-nums text-right">
                    {value}
                </span>
            </div>
        </div>
    );
}

// ── Synthesis signal display ────────────────────────────────────────────────────

function SynthesisSignal({ synthesis }: { synthesis: MurphySynthesis }) {
    const signalConfig: Record<
        string,
        { label: string; bar: string; text: string }
    > = {
        strong_buy: { label: "Strong Buy", bar: "bg-emerald-500", text: "text-emerald-400" },
        buy: { label: "Buy", bar: "bg-teal-500", text: "text-teal-400" },
        neutral: { label: "Neutral", bar: "bg-white/30", text: "text-white/50" },
        sell: { label: "Sell", bar: "bg-amber-500", text: "text-amber-400" },
        strong_sell: { label: "Strong Sell", bar: "bg-rose-500", text: "text-rose-400" },
    };
    const cfg = signalConfig[synthesis.overall_signal] ?? signalConfig.neutral;
    const pct = synthesis.signal_strength;

    return (
        <div className="space-y-4">
            <div className="flex items-center gap-4">
                <div className="flex-1">
                    <div className="flex items-center justify-between mb-2">
                        <span className={cn("text-xl font-black tracking-tight", cfg.text)}>
                            {cfg.label}
                        </span>
                        <span className="text-white/30 text-sm font-bold tabular-nums">
                            {pct}<span className="text-white/20">/100</span>
                        </span>
                    </div>
                    <div className="h-2 rounded-full bg-white/8 overflow-hidden">
                        <div
                            className={cn("h-2 rounded-full transition-all duration-700", cfg.bar)}
                            style={{ width: `${pct}%` }}
                        />
                    </div>
                </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-black uppercase tracking-widest text-white/25">
                    Dominant factor
                </span>
                <SignalBadge signal={synthesis.dominant_factor} />
                <span className="text-[11px] text-white/35">
                    Risk: {synthesis.risk_level}
                </span>
            </div>
        </div>
    );
}

// ── Support / resistance levels ─────────────────────────────────────────────────

function LevelRow({ level }: { level: PriceLevel }) {
    const isSupport = level.level_type === "support";
    const dist = level.distance_pct;
    const distText = `${dist > 0 ? "+" : ""}${dist.toFixed(1)}%`;
    const strengthColor =
        level.strength === "strong"
            ? isSupport ? "text-emerald-400" : "text-rose-400"
            : level.strength === "moderate"
                ? "text-amber-400/70"
                : "text-white/30";

    return (
        <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0 gap-2">
            <div className="flex items-center gap-2">
                <span
                    className={cn(
                        "w-1.5 h-1.5 rounded-full flex-shrink-0",
                        isSupport ? "bg-emerald-500" : "bg-rose-500",
                    )}
                />
                <span className="text-[10px] font-black uppercase tracking-widest text-white/30">
                    {level.level_type}
                </span>
                <span className={cn("text-[10px] font-black uppercase tracking-widest", strengthColor)}>
                    {level.strength}
                </span>
            </div>
            <div className="flex items-center gap-3">
                <span className="text-xs text-white/35 tabular-nums">{distText}</span>
                <span className="text-sm font-bold text-white/80 tabular-nums">
                    ${level.price.toFixed(2)}
                </span>
            </div>
        </div>
    );
}

// ── Main panel ──────────────────────────────────────────────────────────────────

export function MurphyPanel({ symbol }: { symbol: string }) {
    const { data, loading, error, refresh } = useMurphyAnalysis(symbol);
    const [refreshing, setRefreshing] = useState(false);

    const handleRefresh = useCallback(async () => {
        setRefreshing(true);
        try { await refresh(); } finally { setRefreshing(false); }
    }, [refresh]);

    const t = data?.trend;
    const m = data?.momentum;
    const v = data?.volume;
    const sr = data?.support_resistance;
    const osc = data?.oscillators;
    const syn = data?.synthesis;
    const dq = data?.data_quality;

    const fmt = (n: number | null | undefined, decimals = 2) =>
        n != null ? `$${n.toFixed(decimals)}` : "—";
    const fmtPct = (n: number | null | undefined) =>
        n != null ? `${n > 0 ? "+" : ""}${n.toFixed(1)}%` : "—";

    return (
        <div className="space-y-6 animate-fade-up">
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
                    <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                    <p className="text-sm text-white/60">{error}</p>
                </div>
            )}

            {/* ── Synthesis card ── */}
            <div className="glass-panel p-8 relative overflow-hidden">
                <div
                    className="pointer-events-none absolute inset-x-0 top-0 h-px"
                    style={{
                        background:
                            "linear-gradient(90deg, transparent, rgba(99,102,241,0.5) 40%, rgba(139,92,246,0.3) 70%, transparent)",
                    }}
                    aria-hidden="true"
                />
                <SectionHeader
                    title="Murphy Technical Analysis"
                    subtitle="Hierarchical signal: trend overrules oscillators"
                    action={
                        <button
                            onClick={handleRefresh}
                            disabled={loading || refreshing}
                            className={cn(
                                "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                                "text-[10px] font-black uppercase tracking-widest",
                                (loading || refreshing) && "opacity-50 cursor-not-allowed",
                            )}
                        >
                            <RefreshCw className={cn("h-3 w-3", refreshing && "animate-spin")} />
                            {refreshing ? "Refreshing…" : "Refresh"}
                        </button>
                    }
                />

                {loading ? (
                    <div className="space-y-4">
                        <Shimmer className="h-10 w-64" />
                        <Shimmer className="h-2 w-full" />
                        <Shimmer className="h-2 w-3/4" />
                    </div>
                ) : syn ? (
                    <SynthesisSignal synthesis={syn} />
                ) : null}

                {/* Key observations */}
                {syn?.key_observations && syn.key_observations.length > 0 && (
                    <div className="mt-6 space-y-2">
                        <p className="text-[10px] font-black uppercase tracking-widest text-white/25">
                            Key observations
                        </p>
                        {syn.key_observations.map((obs, i) => (
                            <div key={i} className="flex items-start gap-2.5">
                                <span className="mt-1.5 h-1 w-1 rounded-full bg-indigo-400/50 flex-shrink-0" />
                                <p className="text-sm text-white/60 leading-relaxed">{obs}</p>
                            </div>
                        ))}
                    </div>
                )}

                {/* Conflicts */}
                {syn?.conflicts && syn.conflicts.length > 0 && (
                    <div className="mt-4 space-y-2">
                        <p className="text-[10px] font-black uppercase tracking-widest text-amber-400/60">
                            Conflicts
                        </p>
                        {syn.conflicts.map((c, i) => (
                            <div key={i} className="flex items-start gap-2.5">
                                <span className="mt-1.5 h-1 w-1 rounded-full bg-amber-400/50 flex-shrink-0" />
                                <p className="text-sm text-amber-400/70 leading-relaxed">{c}</p>
                            </div>
                        ))}
                    </div>
                )}

                {/* Caution note */}
                {syn?.caution_note && (
                    <div className="mt-4 rounded-xl bg-amber-500/8 border border-amber-500/20 px-4 py-3">
                        <div className="flex items-center gap-2 mb-1">
                            <AlertTriangle className="h-3 w-3 text-amber-400" />
                            <span className="text-[9px] font-black uppercase tracking-widest text-amber-400/70">
                                Data quality note
                            </span>
                        </div>
                        <p className="text-xs text-white/50 leading-relaxed">{syn.caution_note}</p>
                    </div>
                )}
            </div>

            {/* ── Trend + Volume row ── */}
            <div className="grid lg:grid-cols-2 gap-6">
                {/* Trend */}
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="Trend (layer 1)"
                        subtitle="200/50 SMA — primary signal in Murphy hierarchy"
                    />
                    {loading ? (
                        <div className="space-y-3">
                            {[...Array(5)].map((_, i) => <Shimmer key={i} className="h-8" />)}
                        </div>
                    ) : t ? (
                        <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                            <DetailRow
                                label="Primary trend"
                                value={t.primary_trend}
                                badge={t.primary_trend}
                            />
                            <DetailRow
                                label="Intermediate trend"
                                value={t.intermediate_trend}
                                badge={t.intermediate_trend}
                            />
                            <DetailRow
                                label="Trend strength"
                                value={t.trend_strength}
                            />
                            <DetailRow
                                label="Price vs 200 SMA"
                                value={t.sma200 ? fmt(t.sma200) : "N/A"}
                                badge={t.price_vs_sma200}
                            />
                            <DetailRow
                                label="Price vs 50 SMA"
                                value={t.sma50 ? fmt(t.sma50) : "N/A"}
                                badge={t.price_vs_sma50}
                            />
                            <DetailRow
                                label="50 SMA vs 200 SMA"
                                value=""
                                badge={t.sma50_vs_sma200}
                            />
                            <DetailRow
                                label="200 SMA slope"
                                value=""
                                badge={t.sma200_slope}
                            />
                            {(t.golden_cross || t.death_cross) && (
                                <DetailRow
                                    label={t.golden_cross ? "Golden cross" : "Death cross"}
                                    value={t.cross_bars_ago != null ? `${t.cross_bars_ago} bars ago` : "Recent"}
                                    badge={t.golden_cross ? "rising" : "falling"}
                                />
                            )}
                            <DetailRow
                                label="Dist. from 200 SMA"
                                value={fmtPct(t.distance_from_sma200_pct)}
                            />
                        </div>
                    ) : null}
                </div>

                {/* Volume */}
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="Volume / OBV (layer 2)"
                        subtitle="Confirms or diverges from price"
                    />
                    {loading ? (
                        <div className="space-y-3">
                            {[...Array(4)].map((_, i) => <Shimmer key={i} className="h-8" />)}
                        </div>
                    ) : v ? (
                        <div className="space-y-4">
                            <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                                <DetailRow
                                    label="Volume signal"
                                    value=""
                                    badge={v.volume_signal}
                                />
                                <DetailRow
                                    label="OBV trend"
                                    value=""
                                    badge={v.obv_trend}
                                />
                                <DetailRow
                                    label="OBV confirms price"
                                    value={v.obv_confirms_price ? "Yes" : "No"}
                                />
                                {v.vol_ratio != null && (
                                    <DetailRow
                                        label="Volume ratio (10/50)"
                                        value={`${v.vol_ratio.toFixed(2)}×`}
                                        badge={
                                            v.vol_ratio > 1.1
                                                ? "above"
                                                : v.vol_ratio < 0.9
                                                    ? "below"
                                                    : "flat"
                                        }
                                    />
                                )}
                            </div>
                            <div className="rounded-xl bg-white/3 border border-white/8 px-4 py-3">
                                <p className="text-xs text-white/50 leading-relaxed">
                                    {v.volume_signal_note}
                                </p>
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>

            {/* ── Momentum row ── */}
            <div className="grid lg:grid-cols-2 gap-6">
                {/* MACD */}
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="MACD (layer 3)"
                        subtitle="Zero-line crossover > signal-line crossover"
                    />
                    {loading ? (
                        <div className="space-y-3">
                            {[...Array(5)].map((_, i) => <Shimmer key={i} className="h-8" />)}
                        </div>
                    ) : m?.macd ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-3 gap-3">
                                <Metric
                                    label="MACD line"
                                    value={m.macd.macd_line?.toFixed(4) ?? "—"}
                                    accent={
                                        m.macd.macd_line != null && m.macd.macd_line > 0
                                            ? "emerald"
                                            : "rose"
                                    }
                                />
                                <Metric
                                    label="Signal line"
                                    value={m.macd.signal_line?.toFixed(4) ?? "—"}
                                />
                                <Metric
                                    label="Histogram"
                                    value={m.macd.histogram?.toFixed(4) ?? "—"}
                                    accent={
                                        m.macd.histogram != null && m.macd.histogram > 0
                                            ? "emerald"
                                            : "rose"
                                    }
                                />
                            </div>
                            <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                                <DetailRow
                                    label="Zero-line position"
                                    value=""
                                    badge={m.macd.zero_line_position}
                                />
                                <DetailRow
                                    label="Zero-line cross"
                                    value={m.macd.zero_cross === "none" ? "None" : m.macd.zero_cross.replace(/_/g, " ")}
                                    badge={m.macd.zero_cross !== "none" ? m.macd.zero_cross.startsWith("bullish") ? "rising" : "falling" : undefined}
                                />
                                <DetailRow
                                    label="Signal-line cross"
                                    value={m.macd.signal_cross === "none" ? "None" : m.macd.signal_cross.replace(/_/g, " ")}
                                />
                                <DetailRow
                                    label="Histogram direction"
                                    value={m.macd.histogram_direction.replace(/_/g, " ")}
                                />
                            </div>
                            {m.macd.divergence !== "none" && m.macd.divergence !== "insufficient_data" && (
                                <div className={cn(
                                    "rounded-xl border px-4 py-3",
                                    m.macd.divergence === "bullish"
                                        ? "bg-emerald-500/8 border-emerald-500/20"
                                        : "bg-rose-500/8 border-rose-500/20",
                                )}>
                                    <p className="text-xs leading-relaxed text-white/60">
                                        {m.macd.divergence_note}
                                    </p>
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>

                {/* RSI */}
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="RSI (layer 3)"
                        subtitle="Divergences matter more than level alone"
                    />
                    {loading ? (
                        <div className="space-y-3">
                            {[...Array(3)].map((_, i) => <Shimmer key={i} className="h-8" />)}
                        </div>
                    ) : m?.rsi ? (
                        <div className="space-y-4">
                            <div className="flex items-start gap-6">
                                <div className="glass-stat flex-shrink-0">
                                    <p className="glass-overline">RSI (14)</p>
                                    <div
                                        className={cn(
                                            "text-3xl font-black tracking-tighter",
                                            m.rsi.zone === "overbought"
                                                ? "text-rose-400"
                                                : m.rsi.zone === "oversold"
                                                    ? "text-emerald-400"
                                                    : "text-white",
                                        )}
                                    >
                                        {m.rsi.value?.toFixed(1) ?? "—"}
                                    </div>
                                    <p className="text-[10px] text-white/30 mt-1 font-bold uppercase tracking-widest">
                                        {m.rsi.zone.replace(/_/g, " ")}
                                    </p>
                                </div>
                                <div className="flex-1 rounded-xl bg-white/3 border border-white/8 px-4 py-3">
                                    <p className="text-xs text-white/50 leading-relaxed">
                                        {m.rsi.trend_context}
                                    </p>
                                </div>
                            </div>
                            {m.rsi.divergence !== "none" && m.rsi.divergence !== "insufficient_data" && (
                                <div className={cn(
                                    "rounded-xl border px-4 py-3",
                                    m.rsi.divergence === "bullish"
                                        ? "bg-emerald-500/8 border-emerald-500/20"
                                        : "bg-rose-500/8 border-rose-500/20",
                                )}>
                                    <div className="flex items-center gap-2 mb-1">
                                        <Sparkles className="h-3 w-3 text-indigo-400/70" />
                                        <span className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70">
                                            {m.rsi.divergence} divergence
                                        </span>
                                    </div>
                                    <p className="text-xs text-white/60 leading-relaxed">
                                        {m.rsi.divergence_note}
                                    </p>
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>
            </div>

            {/* ── Support/Resistance + Oscillators row ── */}
            <div className="grid lg:grid-cols-2 gap-6">
                {/* Support/Resistance */}
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="Support & resistance (layer 4)"
                        subtitle="Pivot highs and lows from last 52 weeks"
                    />
                    {loading ? (
                        <div className="space-y-3">
                            {[...Array(4)].map((_, i) => <Shimmer key={i} className="h-8" />)}
                        </div>
                    ) : sr ? (
                        <div className="space-y-4">
                            <div className="grid grid-cols-2 gap-3">
                                <Metric
                                    label="52-week high"
                                    value={fmt(sr.high_52w)}
                                />
                                <Metric
                                    label="52-week low"
                                    value={fmt(sr.low_52w)}
                                />
                                <Metric
                                    label="From 52w high"
                                    value={fmtPct(sr.pct_from_52w_high)}
                                    accent={
                                        sr.pct_from_52w_high != null && sr.pct_from_52w_high >= -5
                                            ? "emerald"
                                            : undefined
                                    }
                                />
                                <Metric
                                    label="From 52w low"
                                    value={fmtPct(sr.pct_from_52w_low)}
                                />
                            </div>
                            {sr.levels.length > 0 && (
                                <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                                    {sr.levels.slice(0, 6).map((level, i) => (
                                        <LevelRow key={i} level={level} />
                                    ))}
                                </div>
                            )}
                        </div>
                    ) : null}
                </div>

                {/* Oscillators */}
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="Oscillators (layer 5)"
                        subtitle="Weakest signal — only meaningful when trend is neutral"
                    />
                    {loading ? (
                        <div className="space-y-3">
                            {[...Array(4)].map((_, i) => <Shimmer key={i} className="h-8" />)}
                        </div>
                    ) : osc ? (
                        <div className="space-y-4">
                            {/* Bollinger */}
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-white/25 mb-3">
                                    Bollinger bands (20, 2σ)
                                </p>
                                <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                                    <DetailRow
                                        label="Price position"
                                        value={osc.bollinger.price_position.replace(/_/g, " ")}
                                    />
                                    <DetailRow
                                        label="Bandwidth pct."
                                        value={osc.bollinger.bandwidth_percentile != null ? `${osc.bollinger.bandwidth_percentile}th pct.` : "—"}
                                    />
                                    {osc.bollinger.squeeze && (
                                        <DetailRow
                                            label="Squeeze"
                                            value="Active — compression"
                                            badge="flat"
                                        />
                                    )}
                                    <DetailRow label="Upper" value={fmt(osc.bollinger.upper)} />
                                    <DetailRow label="Middle (SMA20)" value={fmt(osc.bollinger.middle)} />
                                    <DetailRow label="Lower" value={fmt(osc.bollinger.lower)} />
                                </div>
                            </div>
                            {/* Stochastic */}
                            <div>
                                <p className="text-[10px] font-black uppercase tracking-widest text-white/25 mb-3">
                                    Stochastic (14, 3, 3)
                                </p>
                                <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                                    <DetailRow
                                        label="%K"
                                        value={osc.stochastic.k_line?.toFixed(1) ?? "—"}
                                    />
                                    <DetailRow
                                        label="%D"
                                        value={osc.stochastic.d_line?.toFixed(1) ?? "—"}
                                    />
                                    <DetailRow
                                        label="Zone"
                                        value=""
                                        badge={osc.stochastic.zone}
                                    />
                                    {osc.stochastic.signal !== "none" && (
                                        <DetailRow
                                            label="Signal"
                                            value={osc.stochastic.signal.replace(/_/g, " ")}
                                            badge={osc.stochastic.signal.startsWith("bullish") ? "rising" : "falling"}
                                        />
                                    )}
                                </div>
                            </div>
                        </div>
                    ) : null}
                </div>
            </div>

            {/* ── Data quality footer ── */}
            {dq && (
                <div className="glass-panel p-6">
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-white/30">
                        <span>
                            Source: <span className="text-white/50 font-bold">{dq.data_source}</span>
                        </span>
                        <span>
                            Bars: <span className="text-white/50 font-bold">{dq.bars_available}</span>
                        </span>
                        <span>
                            As of: <span className="text-white/50 font-bold">{dq.newest_bar_date ?? "—"}</span>
                        </span>
                        {!dq.sufficient_for_full_analysis && (
                            <span className="text-amber-400/60">
                                Degraded: {dq.degraded_indicators.join(", ")}
                            </span>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}