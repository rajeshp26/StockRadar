"use client";
// web/src/features/analysis/components/canslim-panel.tsx
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { RefreshCw, AlertTriangle } from "lucide-react";
import { useCANSlim } from "../hooks/useCANSlim";
import { SectionHeader } from "./shared-ui";
import type { LetterScore, CANSlimMarketCondition } from "../types/analysis.types";

function Shimmer({ className }: { className?: string }) {
    return <div className={cn("rounded-xl bg-white/5 glass-shimmer", className)} />;
}

// ── Signal color helpers ────────────────────────────────────────────────────────

function signalColors(signal: string) {
    const map: Record<string, { bar: string; text: string; bg: string; border: string }> = {
        bullish: { bar: "bg-emerald-500", text: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/20" },
        bearish: { bar: "bg-rose-500", text: "text-rose-400", bg: "bg-rose-500/10", border: "border-rose-500/20" },
        neutral: { bar: "bg-white/30", text: "text-white/40", bg: "bg-white/5", border: "border-white/10" },
        unavailable: { bar: "bg-white/15", text: "text-white/25", bg: "bg-white/3", border: "border-white/8" },
    };
    return map[signal] ?? map.neutral;
}

// ── Per-letter row ──────────────────────────────────────────────────────────────

function LetterRow({ ls }: { ls: LetterScore }) {
    const [expanded, setExpanded] = useState(false);
    const colors = signalColors(ls.signal);
    const weight = Math.round(ls.weight * 100);

    return (
        <div className="border-b border-white/5 last:border-0">
            <button
                onClick={() => setExpanded((s) => !s)}
                className="w-full flex items-center gap-4 py-3.5 px-4 hover:bg-white/3 transition-colors text-left"
            >
                {/* Letter badge */}
                <div
                    className={cn(
                        "flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl",
                        "text-sm font-black border",
                        ls.available ? colors.bg + " " + colors.border : "bg-white/3 border-white/8",
                    )}
                >
                    <span className={ls.available ? colors.text : "text-white/20"}>
                        {ls.letter}
                    </span>
                </div>

                {/* Name + headline */}
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                        <span className="text-xs font-black text-white/70">{ls.name}</span>
                        <span className="text-[10px] text-white/25">({weight}%)</span>
                    </div>
                    <p className="text-[11px] text-white/40 leading-relaxed truncate">
                        {ls.headline}
                    </p>
                </div>

                {/* Score bar */}
                <div className="flex items-center gap-3 flex-shrink-0">
                    {ls.available ? (
                        <>
                            <div className="w-20 h-1.5 rounded-full bg-white/8 overflow-hidden">
                                <div
                                    className={cn("h-1.5 rounded-full transition-all duration-700", colors.bar)}
                                    style={{ width: `${ls.score}%` }}
                                />
                            </div>
                            <span className="text-sm font-black text-white/70 tabular-nums w-8 text-right">
                                {ls.score}
                            </span>
                        </>
                    ) : (
                        <span className="text-[10px] text-white/25 font-bold uppercase tracking-widest">
                            N/A
                        </span>
                    )}
                </div>

                {/* Expand indicator */}
                <span className="text-white/20 text-xs flex-shrink-0">
                    {expanded ? "▲" : "▼"}
                </span>
            </button>

            {/* Expanded detail */}
            {expanded && (
                <div className="px-4 pb-4 animate-fade-up">
                    <div className="rounded-xl bg-white/3 border border-white/8 p-4">
                        <p className="text-xs text-white/60 leading-relaxed mb-3">{ls.headline}</p>
                        {ls.available && Object.keys(ls.evidence.metrics).length > 0 && (
                            <div className="grid grid-cols-2 gap-2">
                                {Object.entries(ls.evidence.metrics)
                                    .filter(([, v]) => v != null)
                                    .map(([k, v]) => (
                                        <div key={k} className="flex justify-between gap-2">
                                            <span className="text-[10px] text-white/30 capitalize">
                                                {k.replace(/_/g, " ")}
                                            </span>
                                            <span className="text-[10px] font-bold text-white/60 tabular-nums text-right">
                                                {typeof v === "boolean"
                                                    ? v ? "Yes" : "No"
                                                    : Array.isArray(v)
                                                        ? `${v.length} items`
                                                        : String(v)}
                                            </span>
                                        </div>
                                    ))}
                            </div>
                        )}
                        {ls.flags.length > 0 && (
                            <div className="mt-3 pt-3 border-t border-white/5">
                                {ls.flags.map((f, i) => (
                                    <p key={i} className="text-[11px] text-amber-400/60 leading-relaxed">
                                        {f}
                                    </p>
                                ))}
                            </div>
                        )}
                        <div className="mt-2">
                            <span className="text-[10px] text-white/20 capitalize">
                                Source: {ls.evidence.data_source.replace(/_/g, " ")}
                            </span>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// ── Market condition card ──────────────────────────────────────────────────────

function MarketConditionCard({ mc }: { mc: CANSlimMarketCondition }) {
    const conditionColors: Record<string, { border: string; bg: string; text: string }> = {
        confirmed_uptrend: { border: "border-emerald-500/25", bg: "bg-emerald-500/8", text: "text-emerald-400" },
        uptrend_pressure: { border: "border-amber-500/25", bg: "bg-amber-500/8", text: "text-amber-400" },
        distribution: { border: "border-rose-500/25", bg: "bg-rose-500/8", text: "text-rose-400" },
        downtrend: { border: "border-rose-500/30", bg: "bg-rose-500/10", text: "text-rose-400" },
        unknown: { border: "border-white/10", bg: "bg-white/5", text: "text-white/40" },
    };
    const cfg = conditionColors[mc.condition] ?? conditionColors.unknown;

    return (
        <div className={cn("rounded-xl border px-4 py-3", cfg.border, cfg.bg)}>
            <div className="flex items-center justify-between mb-2">
                <span className={cn("text-[10px] font-black uppercase tracking-widest", cfg.text)}>
                    {mc.condition.replace(/_/g, " ")}
                </span>
                <div className="flex items-center gap-4 text-[11px] text-white/30 tabular-nums">
                    {mc.spy_price != null && (
                        <span>Price: ${mc.spy_price.toFixed(2)}</span>
                    )}
                    {mc.spy_sma50 != null && (
                        <span>50d: ${mc.spy_sma50.toFixed(2)}</span>
                    )}
                    {mc.spy_sma200 != null && (
                        <span>200d: ${mc.spy_sma200.toFixed(2)}</span>
                    )}
                </div>
            </div>
            <p className="text-xs text-white/50 leading-relaxed">{mc.description}</p>
        </div>
    );
}

// ── Composite score display ────────────────────────────────────────────────────

function CompositeScore({
    score,
    category,
}: {
    score: number;
    category: string;
}) {
    const cfg = {
        Strong: { bar: "bg-emerald-500", text: "text-emerald-400", label: "Strong" },
        Moderate: { bar: "bg-amber-500", text: "text-amber-400", label: "Moderate" },
        Weak: { bar: "bg-rose-500", text: "text-rose-400", label: "Weak" },
    }[category] ?? { bar: "bg-white/30", text: "text-white/50", label: category };

    return (
        <div className="glass-stat">
            <p className="glass-overline">Composite score</p>
            <div className={cn("text-4xl font-black tracking-tighter mt-1", cfg.text)}>
                {score}
                <span className="text-lg text-white/20 font-medium"> / 100</span>
            </div>
            <div className="mt-3 h-2 rounded-full bg-white/8 overflow-hidden">
                <div
                    className={cn("h-2 rounded-full transition-all duration-700", cfg.bar)}
                    style={{ width: `${score}%` }}
                />
            </div>
            <span
                className={cn(
                    "mt-2 inline-block px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border",
                    cfg.text,
                    "bg-white/5 border-white/10",
                )}
            >
                {cfg.label}
            </span>
        </div>
    );
}

// ── Main panel ──────────────────────────────────────────────────────────────────

export function CANSlimPanel({ symbol }: { symbol: string }) {
    const { data, loading, error, notComputed, recompute } = useCANSlim(symbol);
    const [recomputing, setRecomputing] = useState(false);

    const handleRecompute = useCallback(async () => {
        setRecomputing(true);
        try { await recompute(); } finally { setRecomputing(false); }
    }, [recompute]);

    // Not computed state
    if (!loading && notComputed) {
        return (
            <div className="glass-panel p-12 flex flex-col items-center text-center space-y-6 animate-fade-up">
                <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-white/5 border border-white/10">
                    <span className="text-xl font-black text-white/20">CS</span>
                </div>
                <div>
                    <h3 className="text-xl font-black text-white tracking-tight">Not yet computed</h3>
                    <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">
                        Run CANSlim analysis to score all seven O'Neil criteria for this company.
                    </p>
                </div>
                <button
                    onClick={handleRecompute}
                    disabled={recomputing}
                    className={cn(
                        "glass-btn inline-flex items-center gap-2 px-6 py-3 rounded-xl",
                        "text-[10px] font-black uppercase tracking-widest",
                        recomputing && "opacity-50 cursor-not-allowed",
                    )}
                >
                    <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
                    {recomputing ? "Computing…" : "Run Analysis"}
                </button>
            </div>
        );
    }

    const letters = data?.letters;
    const letterOrder = ["C", "A", "N", "S", "L", "I", "M"] as const;

    return (
        <div className="space-y-6 animate-fade-up">
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
                    <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                    <p className="text-sm text-white/60">{error}</p>
                </div>
            )}

            {/* ── Summary card ── */}
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
                    title="CANSlim (William O'Neil)"
                    subtitle="Seven-letter framework — C and A carry the most weight (40% combined)"
                    action={
                        <button
                            onClick={handleRecompute}
                            disabled={loading || recomputing}
                            className={cn(
                                "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                                "text-[10px] font-black uppercase tracking-widest",
                                (loading || recomputing) && "opacity-50 cursor-not-allowed",
                            )}
                        >
                            <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
                            {recomputing ? "Recomputing…" : "Recompute"}
                        </button>
                    }
                />

                {loading ? (
                    <div className="space-y-4">
                        <Shimmer className="h-24 w-48" />
                        <Shimmer className="h-4 w-full" />
                    </div>
                ) : data ? (
                    <div className="flex flex-col md:flex-row gap-6 items-start">
                        <CompositeScore
                            score={data.composite_score}
                            category={data.composite_category}
                        />
                        <div className="flex-1 space-y-3">
                            {/* Market condition */}
                            <MarketConditionCard mc={data.market_condition} />
                            {/* Confidence note */}
                            {data.data_quality.confidence_note && (
                                <div className="rounded-xl bg-white/3 border border-white/8 px-4 py-3">
                                    <p className="text-xs text-white/45 leading-relaxed">
                                        {data.data_quality.confidence_note}
                                    </p>
                                </div>
                            )}
                        </div>
                    </div>
                ) : null}

                {/* Global flags */}
                {!loading && data?.flags && data.flags.length > 0 && (
                    <div className="mt-6 space-y-2">
                        {data.flags.map((f, i) => (
                            <div
                                key={i}
                                className={cn(
                                    "rounded-xl border px-4 py-3",
                                    f.severity === "high" || f.severity === "critical"
                                        ? "bg-rose-500/8 border-rose-500/20"
                                        : "bg-amber-500/8 border-amber-500/20",
                                )}
                            >
                                <p className="text-[10px] font-black uppercase tracking-widest text-white/30 mb-1">
                                    {f.code}
                                </p>
                                <p className="text-xs text-white/55 leading-relaxed">{f.message}</p>
                                {f.recommendation && (
                                    <p className="mt-1 text-xs text-amber-400/60 leading-relaxed">
                                        {f.recommendation}
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* ── Letter scorecard ── */}
            <div className="glass-panel p-8">
                <SectionHeader
                    title="Letter scorecard"
                    subtitle="Click any letter to expand evidence — L and M use live benchmark data"
                />
                {loading ? (
                    <div className="space-y-3">
                        {letterOrder.map((l) => (
                            <Shimmer key={l} className="h-14" />
                        ))}
                    </div>
                ) : letters ? (
                    <div className="rounded-2xl border border-white/8 overflow-hidden">
                        {letterOrder.map((letter) => (
                            <LetterRow key={letter} ls={letters[letter]} />
                        ))}
                    </div>
                ) : null}
            </div>

            {/* ── Data quality footer ── */}
            {data?.data_quality && !loading && (
                <div className="glass-panel p-6">
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-white/30">
                        <span>
                            Letters scored:{" "}
                            <span className="text-white/50 font-bold">
                                {data.data_quality.letters_fully_scored}/7
                            </span>
                        </span>
                        <span>
                            Benchmark:{" "}
                            <span className="text-white/50 font-bold">
                                {data.data_quality.benchmark_symbol}
                            </span>
                        </span>
                        <span>
                            Confidence:{" "}
                            <span className="text-white/50 font-bold">
                                {(data.data_quality.confidence_adjustment * 100).toFixed(0)}%
                            </span>
                        </span>
                        {data.data_quality.letters_unavailable.length > 0 && (
                            <span className="text-amber-400/60">
                                Unavailable: {data.data_quality.letters_unavailable.join(", ")}
                            </span>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}