"use client";
// web/src/features/analysis/components/magic-formula-panel.tsx
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { RefreshCw, AlertTriangle, Sparkles } from "lucide-react";
import { useMagicFormula } from "../hooks/useMagicFormula";
import {
    Metric,
    SectionHeader,
    SuitabilitySidebar,
    DiagnosticsList,
} from "./shared-ui";

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

function Row({ label, value }: { label: string; value: React.ReactNode }) {
    return (
        <div className="flex items-start justify-between gap-4 py-2.5 border-b border-white/5 last:border-0">
            <span className="text-[11px] font-black uppercase tracking-widest text-white/30">
                {label}
            </span>
            <span className="text-sm font-bold text-white/70 text-right tabular-nums">
                {value}
            </span>
        </div>
    );
}

function ContextBadge({
    direction,
}: {
    direction: "above" | "below" | "inline" | null | undefined;
}) {
    if (!direction) return null;
    const cfg = {
        above: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
        below: "bg-rose-500/15 border-rose-500/30 text-rose-400",
        inline: "bg-white/8 border-white/15 text-white/50",
    };
    return (
        <span
            className={cn(
                "px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border",
                cfg[direction],
            )}
        >
            {direction} industry
        </span>
    );
}

export function MagicFormulaPanel({ symbol }: { symbol: string }) {
    const { data, loading, error, notComputed, recompute } =
        useMagicFormula(symbol);
    const [recomputing, setRecomputing] = useState(false);
    const [showDiagnostics, setShowDiagnostics] = useState(false);

    const handleRecompute = useCallback(async () => {
        setRecomputing(true);
        try { await recompute(); } finally { setRecomputing(false); }
    }, [recompute]);

    const v = data?.valuation;
    const app = data?.applicability;
    const ind = data?.industry_context;
    const inp = data?.inputs;
    const dq = data?.data_quality;

    const fmtPct = (n: number | null | undefined, decimals = 2) =>
        n != null ? `${n.toFixed(decimals)}%` : "—";
    const fmtNum = (n: number | null | undefined, decimals = 2) =>
        n != null
            ? n >= 1e9
                ? `${(n / 1e9).toFixed(1)}B`
                : n >= 1e6
                    ? `${(n / 1e6).toFixed(1)}M`
                    : n.toFixed(decimals)
            : "—";

    // ── Not computed state ─────────────────────────────────────────────────────
    if (!loading && notComputed) {
        return (
            <div className="glass-panel p-12 flex flex-col items-center text-center space-y-6 animate-fade-up">
                <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-white/5 border border-white/10">
                    <span className="text-3xl font-black text-white/20">MF</span>
                </div>
                <div>
                    <h3 className="text-xl font-black text-white tracking-tight">
                        Not yet computed
                    </h3>
                    <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">
                        Run the Magic Formula analysis to compute Earnings Yield and Return
                        on Capital for this company.
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

    return (
        <div className="space-y-6 animate-fade-up">
            {error && (
                <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
                    <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                    <p className="text-sm text-white/60">{error}</p>
                </div>
            )}

            {/* ── Main metrics card ── */}
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
                    title="Magic Formula (Greenblatt)"
                    subtitle="Earnings Yield × Return on Capital — absolute metrics with industry context"
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

                <div className="flex flex-col lg:flex-row gap-8">
                    {/* Left: metrics */}
                    <div className="flex-1">
                        {loading ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <MetricSkeleton /><MetricSkeleton />
                                <MetricSkeleton /><MetricSkeleton />
                            </div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <Metric
                                    label="Earnings yield"
                                    value={fmtPct(v?.earnings_yield_pct)}
                                    hint="EBIT ÷ Enterprise Value"
                                    accent={
                                        (v?.earnings_yield_pct ?? 0) > 5
                                            ? "emerald"
                                            : (v?.earnings_yield_pct ?? 0) > 0
                                                ? "indigo"
                                                : "rose"
                                    }
                                />
                                <Metric
                                    label="Return on capital"
                                    value={fmtPct(v?.return_on_capital_pct)}
                                    hint="EBIT ÷ (NWC + NFA)"
                                    accent={
                                        (v?.return_on_capital_pct ?? 0) > 15
                                            ? "emerald"
                                            : (v?.return_on_capital_pct ?? 0) > 0
                                                ? "indigo"
                                                : "rose"
                                    }
                                />
                                <Metric
                                    label="Net working capital"
                                    value={fmtNum(v?.net_working_capital)}
                                    hint="Greenblatt NWC (excess cash excluded)"
                                />
                                <Metric
                                    label="Net fixed assets"
                                    value={fmtNum(v?.net_fixed_assets)}
                                    hint="PPE net — intangibles excluded"
                                />
                            </div>
                        )}

                        {/* Industry context strip */}
                        {!loading && ind && (
                            <div className="mt-4 rounded-xl bg-white/3 border border-white/8 px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-white/25">
                                    vs {ind.sector ?? "Industry"}
                                </span>
                                <ContextBadge direction={ind.earnings_yield_vs_industry} />
                                {ind.earnings_yield_premium_pct != null && (
                                    <span className="text-xs text-white/40 tabular-nums">
                                        {ind.earnings_yield_premium_pct > 0 ? "+" : ""}
                                        {ind.earnings_yield_premium_pct.toFixed(1)}pp vs implied industry EY
                                    </span>
                                )}
                                {ind.avg_ev_ebitda != null && (
                                    <span className="text-xs text-white/30 tabular-nums">
                                        Sector avg EV/EBITDA: {ind.avg_ev_ebitda.toFixed(1)}×
                                    </span>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Dividers */}
                    <div className="hidden lg:block w-px bg-white/8 self-stretch" />
                    <div className="block lg:hidden h-px bg-white/8" />

                    {/* Right: suitability ring */}
                    <div className="flex justify-center lg:justify-end">
                        <SuitabilitySidebar
                            loading={loading}
                            score={app?.score}
                            category={app?.category}
                            flags={app?.flags as never}
                            showDiagnostics={showDiagnostics}
                            onToggleDiagnostics={() => setShowDiagnostics((s) => !s)}
                        />
                    </div>
                </div>

                {/* AI summary */}
                {(loading || app?.suitability_summary) && (
                    <div className="mt-6">
                        {loading ? (
                            <div className="rounded-2xl border border-white/6 bg-white/3 px-5 py-4 space-y-2">
                                <Shimmer className="h-2 w-20" />
                                <Shimmer className="h-2 w-full" />
                                <Shimmer className="h-2 w-4/5" />
                            </div>
                        ) : app?.suitability_summary ? (
                            <div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/5 px-5 py-4">
                                <div className="flex items-center gap-2 mb-2">
                                    <Sparkles className="h-3 w-3 text-indigo-400/70" />
                                    <span className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70">
                                        AI Suitability Analysis
                                    </span>
                                </div>
                                <p className="text-[12px] leading-relaxed text-white/60">
                                    {app.suitability_summary}
                                </p>
                            </div>
                        ) : null}
                    </div>
                )}

                {/* Diagnostics drawer */}
                {showDiagnostics && (
                    <div className="mt-6 pt-6 border-t border-white/5 animate-fade-up">
                        <DiagnosticsList items={app?.flags as never} />
                    </div>
                )}

                {/* Sector exclusion callout */}
                {!loading && app?.excluded && app.exclusion_reason && (
                    <div className="mt-6 rounded-xl bg-rose-500/8 border border-rose-500/20 px-4 py-3">
                        <p className="text-[10px] font-black uppercase tracking-widest text-rose-400/70 mb-1">
                            Sector excluded
                        </p>
                        <p className="text-xs text-white/50 leading-relaxed">
                            {app.exclusion_reason}
                        </p>
                    </div>
                )}
            </div>

            {/* ── Formula inputs breakdown ── */}
            {!loading && inp && (
                <div className="glass-panel p-8">
                    <SectionHeader
                        title="Formula inputs"
                        subtitle="All Greenblatt-specific adjustments applied"
                    />
                    <div className="grid md:grid-cols-2 gap-x-8">
                        <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                            <Row label="TTM EBIT source" value={inp.ttm_ebit_source.replace(/_/g, " ")} />
                            <Row label="TTM EBIT" value={fmtNum(inp.ttm_ebit)} />
                            <Row label="Enterprise value" value={fmtNum(inp.enterprise_value)} />
                            <Row label="Balance sheet year" value={inp.fiscal_year_bs ?? "—"} />
                        </div>
                        <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                            <Row label="Current assets" value={fmtNum(inp.current_assets)} />
                            <Row label="− Excess cash" value={fmtNum(inp.cash_and_equivalents)} />
                            <Row label="Current liabilities" value={fmtNum(inp.current_liabilities)} />
                            <Row label="− Short-term debt" value={fmtNum(inp.short_term_debt)} />
                            <Row label="PPE net (NFA)" value={fmtNum(inp.ppe_net)} />
                            <Row label="Goodwill excluded" value={fmtNum(inp.goodwill_excluded)} />
                            <Row label="Intangibles excluded" value={fmtNum(inp.intangibles_excluded)} />
                        </div>
                    </div>
                    {v?.roic_delta_note && (
                        <div className="mt-4 rounded-xl bg-amber-500/8 border border-amber-500/20 px-4 py-3">
                            <p className="text-xs text-white/50 leading-relaxed">
                                {v.roic_delta_note}
                            </p>
                        </div>
                    )}
                    <p className="mt-4 text-[10px] text-white/20 leading-relaxed">
                        Greenblatt excludes goodwill, intangibles, and excess cash to isolate tangible operating capital.
                        Enterprise Value sourced from company_summary snapshot. Without a full universe,
                        Earnings Yield and ROC are absolute metrics — not a ranked score.
                    </p>
                </div>
            )}

            {/* ── Data quality ── */}
            {dq && !loading && (
                <div className="glass-panel p-6">
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-white/30">
                        <span>TTM coverage: <span className="text-white/50 font-bold">{dq.ttm_coverage}</span></span>
                        <span>EV source: <span className="text-white/50 font-bold">{dq.ev_source}</span></span>
                        {dq.bs_fiscal_year && (
                            <span>BS year: <span className="text-white/50 font-bold">{dq.bs_fiscal_year}</span></span>
                        )}
                        {dq.fallbacks_used && (
                            <span className="text-amber-400/60">Fallback data used — lower confidence</span>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}