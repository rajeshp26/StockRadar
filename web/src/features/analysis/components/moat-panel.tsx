"use client";
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { RefreshCw, AlertTriangle, Sparkles, FileText, Search } from "lucide-react";
import { useMoatAnalysis } from "../hooks/useMoatAnalysis";
import {
    Metric,
    SectionHeader,
    SuitabilitySidebar,
    DiagnosticsList,
} from "./shared-ui";
import { fetchMoatEvidence, fetchMoatAiNarrative, generateMoatAiNarrative, type MoatEvidenceData, type MoatAiNarrativeData } from "../services/moat.service";

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
            <span className="text-[11px] font-black uppercase tracking-widest text-white/30">{label}</span>
            <span className="text-sm font-bold text-white/70 text-right tabular-nums">{value}</span>
        </div>
    );
}

function ContextBadge({ direction }: { direction: string | null | undefined }) {
    if (!direction) return null;
    const cfg: Record<string, string> = {
        above: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
        below: "bg-rose-500/15 border-rose-500/30 text-rose-400",
        inline: "bg-white/8 border-white/15 text-white/50",
    };
    return (
        <span className={cn("px-2.5 py-1 rounded-full text-[10px] font-black uppercase tracking-widest border", cfg[direction] || cfg.inline)}>
            {direction} industry
        </span>
    );
}

function MoatCategoryBadge({ category }: { category: string | null | undefined }) {
    if (!category) return null;
    const cfg: Record<string, string> = {
        Wide: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
        Narrow: "bg-amber-500/15 border-amber-500/30 text-amber-400",
        None: "bg-rose-500/15 border-rose-500/30 text-rose-400",
        Unknown: "bg-white/8 border-white/15 text-white/50",
    };
    return (
        <span className={cn("px-3 py-1.5 rounded-full text-[10px] font-black uppercase tracking-widest border", cfg[category] || cfg.Unknown)}>
            {category} Moat
        </span>
    );
}

export function MoatPanel({ symbol }: { symbol: string }) {
    const { data, loading, error, notComputed, recompute } = useMoatAnalysis(symbol);
    const [recomputing, setRecomputing] = useState(false);
    const [showDiagnostics, setShowDiagnostics] = useState(false);
    const [evidence, setEvidence] = useState<MoatEvidenceData | null>(null);
    const [evidenceLoading, setEvidenceLoading] = useState(false);
    const [evidenceError, setEvidenceError] = useState<string | null>(null);
    const [aiNarrative, setAiNarrative] = useState<MoatAiNarrativeData | null>(null);
    const [aiLoading, setAiLoading] = useState(false);
    const [aiError, setAiError] = useState<string | null>(null);

    const handleRecompute = useCallback(async () => {
        setRecomputing(true);
        try { await recompute(); } finally { setRecomputing(false); }
    }, [recompute]);

    const handleFetchEvidence = useCallback(async (refresh = false) => {
        setEvidenceLoading(true);
        setEvidenceError(null);
        try {
            const result = await fetchMoatEvidence(symbol, refresh);
            setEvidence(result);
        } catch (err: any) {
            setEvidenceError(err?.message || "Failed to load evidence.");
        } finally {
            setEvidenceLoading(false);
        }
    }, [symbol]);

    const handleFetchAi = useCallback(async () => {
        setAiLoading(true);
        setAiError(null);
        try {
            const cached = await fetchMoatAiNarrative(symbol);
            if (cached.available) {
                setAiNarrative(cached);
                setAiLoading(false);
                return;
            }
            const generated = await generateMoatAiNarrative(symbol);
            setAiNarrative(generated);
        } catch (err: any) {
            setAiError(err?.message || "Failed to generate AI narrative.");
        } finally {
            setAiLoading(false);
        }
    }, [symbol]);

    const v = data?.valuation;
    const app = data?.applicability;
    const ind = data?.industry_context;
    const inp = data?.inputs;
    const dq = data?.data_quality;

    const fmtPct = (n: number | null | undefined, decimals = 2) =>
        n != null ? `${n.toFixed(decimals)}%` : "\u2014";
    const fmtNum = (n: number | null | undefined, decimals = 2) =>
        n != null
            ? n >= 1e9 ? `${(n / 1e9).toFixed(1)}B`
            : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M`
            : n.toFixed(decimals)
            : "\u2014";

    if (!loading && notComputed) {
        return (
            <div className="glass-panel p-12 flex flex-col items-center text-center space-y-6 animate-fade-up">
                <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-white/5 border border-white/10">
                    <span className="text-3xl font-black text-white/20">M</span>
                </div>
                <div>
                    <h3 className="text-xl font-black text-white tracking-tight">Not yet computed</h3>
                    <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">
                        Run the Moat analysis to evaluate this company&apos;s competitive advantage durability.
                    </p>
                </div>
                <button onClick={handleRecompute} disabled={recomputing}
                    className={cn("glass-btn inline-flex items-center gap-2 px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest", recomputing && "opacity-50 cursor-not-allowed")}>
                    <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
                    {recomputing ? "Computing\u2026" : "Run Analysis"}
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

            <div className="glass-panel p-8 relative overflow-hidden">
                <div className="pointer-events-none absolute inset-x-0 top-0 h-px"
                    style={{ background: "linear-gradient(90deg, transparent, rgba(99,102,241,0.5) 40%, rgba(139,92,246,0.3) 70%, transparent)" }}
                    aria-hidden="true" />
                <SectionHeader
                    title="Economic Moat Analysis"
                    subtitle="ROIC durability, margin strength, return stability, and capital efficiency"
                    action={
                        <button onClick={handleRecompute} disabled={loading || recomputing}
                            className={cn("glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest", (loading || recomputing) && "opacity-50 cursor-not-allowed")}>
                            <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
                            {recomputing ? "Recomputing\u2026" : "Recompute"}
                        </button>
                    }
                />

                <div className="flex flex-col lg:flex-row gap-8">
                    <div className="flex-1">
                        {loading ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <MetricSkeleton /><MetricSkeleton />
                                <MetricSkeleton /><MetricSkeleton />
                                <MetricSkeleton /><MetricSkeleton />
                            </div>
                        ) : (
                            <>
                                <div className="mb-6">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-white/25 mb-3">Core Moat Metrics</p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <Metric label="ROIC" value={fmtPct(v?.roic)} hint="Return on Invested Capital"
                                            accent={(v?.roic ?? 0) > (v?.wacc ?? 0) ? "emerald" : (v?.roic ?? 0) > 0 ? "indigo" : "rose"} />
                                        <Metric label="WACC" value={fmtPct(v?.wacc)} hint="Weighted Average Cost of Capital" />
                                        <Metric label="ROIC \u2212 WACC" value={fmtPct(v?.roic_minus_wacc)} hint="Economic moat spread"
                                            accent={(v?.roic_minus_wacc ?? 0) > 0 ? "emerald" : "rose"} />
                                        <Metric label="Moat Category" value={<MoatCategoryBadge category={v?.moat_category} />} hint="Overall durability rating" />
                                    </div>
                                </div>
                                <div className="mb-6">
                                    <p className="text-[10px] font-black uppercase tracking-widest text-white/25 mb-3">Margin Durability</p>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                        <Metric label="Gross margin" value={fmtPct(v?.gross_margin_pct)} />
                                        <Metric label="Operating margin" value={fmtPct(v?.operating_margin_pct)} />
                                        <Metric label="Net margin" value={fmtPct(v?.net_margin_pct)} />
                                    </div>
                                </div>
                                <div>
                                    <p className="text-[10px] font-black uppercase tracking-widest text-white/25 mb-3">Stability &amp; Efficiency</p>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                        <Metric label="ROIC 5y avg" value={fmtPct(v?.roic_5y_avg)} hint="Average ROIC over 5 years" />
                                        <Metric label="ROIC stability" value={fmtPct(v?.roic_5y_std)} hint="Std deviation (lower = more stable)" />
                                        <Metric label="Stability score" value={v?.roic_stability_score != null ? `${v.roic_stability_score.toFixed(0)}/100` : "\u2014"}
                                            hint="Consistency of returns" accent={(v?.roic_stability_score ?? 0) >= 70 ? "emerald" : (v?.roic_stability_score ?? 0) >= 40 ? "amber" : "rose"} />
                                        <Metric label="Capital efficiency" value={v?.capital_efficiency_score != null ? `${v.capital_efficiency_score.toFixed(0)}/100` : "\u2014"}
                                            hint="Asset turnover & reinvestment" accent={(v?.capital_efficiency_score ?? 0) >= 70 ? "emerald" : (v?.capital_efficiency_score ?? 0) >= 40 ? "amber" : "rose"} />
                                        <Metric label="Asset turnover" value={v?.asset_turnover != null ? v.asset_turnover.toFixed(2) : "\u2014"} hint="Revenue \u00f7 Total Assets" />
                                        <Metric label="Moat score" value={v?.moat_score != null ? `${v.moat_score.toFixed(0)}/100` : "\u2014"} hint="Overall composite score"
                                            accent={(v?.moat_score ?? 0) >= 70 ? "emerald" : (v?.moat_score ?? 0) >= 40 ? "amber" : "rose"} />
                                    </div>
                                </div>
                            </>
                        )}

                        {!loading && ind && (
                            <div className="mt-6 rounded-xl bg-white/3 border border-white/8 px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2">
                                <span className="text-[10px] font-black uppercase tracking-widest text-white/25">vs {ind.sector ?? "Industry"}</span>
                                <ContextBadge direction={ind.roic_vs_industry} />
                                {ind.avg_roic != null && <span className="text-xs text-white/40 tabular-nums">Industry avg ROIC: {ind.avg_roic.toFixed(1)}%</span>}
                                {ind.avg_margin != null && <span className="text-xs text-white/30 tabular-nums">Industry avg margin: {ind.avg_margin.toFixed(1)}%</span>}
                            </div>
                        )}
                    </div>

                    <div className="hidden lg:block w-px bg-white/8 self-stretch" />
                    <div className="block lg:hidden h-px bg-white/8" />

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

                {showDiagnostics && (
                    <div className="mt-6 pt-6 border-t border-white/5 animate-fade-up">
                        <DiagnosticsList items={app?.flags as never} />
                    </div>
                )}

                {!loading && app?.excluded && app.exclusion_reason && (
                    <div className="mt-6 rounded-xl bg-rose-500/8 border border-rose-500/20 px-4 py-3">
                        <p className="text-[10px] font-black uppercase tracking-widest text-rose-400/70 mb-1">Sector excluded</p>
                        <p className="text-xs text-white/50 leading-relaxed">{app.exclusion_reason}</p>
                    </div>
                )}
            </div>

            {!loading && inp && (
                <div className="glass-panel p-8">
                    <SectionHeader title="Inputs" subtitle="Raw financial data used for Moat computation" />
                    <div className="grid md:grid-cols-2 gap-x-8">
                        <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                            <Row label="NOPAT" value={fmtNum(inp.nopat)} />
                            <Row label="Invested capital" value={fmtNum(inp.invested_capital)} />
                            <Row label="Asset turnover" value={inp.asset_turnover != null ? inp.asset_turnover.toFixed(3) : "\u2014"} />
                            <Row label="Fiscal years used" value={inp.fiscal_years_used.toString()} />
                        </div>
                        <div className="rounded-2xl border border-white/8 overflow-hidden px-4">
                            <Row label="Gross margin" value={fmtPct(inp.gross_margin)} />
                            <Row label="Operating margin" value={fmtPct(inp.operating_margin)} />
                            <Row label="Net margin" value={fmtPct(inp.net_margin)} />
                            <Row label="ROIC 5y avg" value={fmtPct(inp.roic_5y_avg)} />
                            <Row label="ROIC volatility" value={inp.roic_volatility != null ? inp.roic_volatility.toFixed(3) : "\u2014"} />
                        </div>
                    </div>
                    <p className="mt-4 text-[10px] text-white/20 leading-relaxed">
                        ROIC = NOPAT / Invested Capital. Moat score composites ROIC spread,
                        margin durability, return stability, and capital efficiency into a 0\u2013100 rating.
                    </p>
                </div>
            )}

            {dq && !loading && (
                <div className="glass-panel p-6">
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-white/30">
                        <span>Data source: <span className="text-white/50 font-bold">{dq.data_sources}</span></span>
                        {dq.fiscal_year_end && <span>FY end: <span className="text-white/50 font-bold">{dq.fiscal_year_end}</span></span>}
                        <span>Quarters used: <span className="text-white/50 font-bold">{dq.quarters_used}</span></span>
                        {dq.fallbacks_used && <span className="text-amber-400/60">Fallback data used \u2014 lower confidence</span>}
                    </div>
                </div>
            )}

            {/* EDGAR Evidence Section */}
            <div className="glass-panel p-8">
                <SectionHeader
                    title="EDGAR 10-K Evidence"
                    subtitle="Keyword-based competitive advantage signals from SEC filings"
                    action={
                        <button onClick={() => handleFetchEvidence(false)} disabled={evidenceLoading}
                            className={cn("glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest", evidenceLoading && "opacity-50 cursor-not-allowed")}>
                            <FileText className={cn("h-3 w-3", evidenceLoading && "animate-pulse")} />
                            {evidenceLoading ? "Loading..." : "View Evidence"}
                        </button>
                    }
                />
                {evidenceError && (
                    <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25 mb-4">
                        <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                        <p className="text-sm text-white/60">{evidenceError}</p>
                    </div>
                )}
                {evidence && evidence.text_analysis_available && (
                    <div className="space-y-4">
                        <div className="flex items-center gap-3">
                            <span className="text-xs text-white/50">{evidence.total_keyword_matches} keyword matches found</span>
                            <button onClick={() => handleFetchEvidence(true)}
                                className="text-[10px] font-bold uppercase tracking-widest text-indigo-400 hover:text-indigo-300 transition-colors">
                                <Search className="h-3 w-3 inline mr-1" />
                                Refresh from EDGAR
                            </button>
                        </div>
                        <div className="grid gap-4">
                            {evidence.groups_found.map((group: string) => {
                                const matches = evidence.evidence_by_group[group] || [];
                                const groupLabel = group.replace(/_/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase());
                                return (
                                    <details key={group} className="group rounded-xl border border-white/8 bg-white/3 overflow-hidden">
                                        <summary className="px-4 py-3 cursor-pointer text-xs font-bold text-white/70 hover:text-white/90 transition-colors flex items-center justify-between">
                                            <span>{groupLabel}</span>
                                            <span className="text-[10px] text-white/30">{matches.length} matches</span>
                                        </summary>
                                        <div className="px-4 pb-4 space-y-2">
                                            {matches.slice(0, 5).map((m: { keyword: string; keyword_group: string; section: string; snippet: string | null; relevance_score: number; filing_date: string | null }, i: number) => (
                                                <div key={i} className="rounded-lg bg-black/30 border border-white/5 p-3">
                                                    <div className="flex items-center gap-2 mb-1">
                                                        <span className="px-1.5 py-0.5 rounded bg-indigo-500/20 text-[9px] font-bold text-indigo-300 uppercase">
                                                            {m.keyword}
                                                        </span>
                                                        {m.section && (
                                                            <span className="text-[9px] text-white/30 uppercase">{m.section.replace(/_/g, " ")}</span>
                                                        )}
                                                    </div>
                                                    {m.snippet && (
                                                        <p className="text-[11px] text-white/50 leading-relaxed">...{m.snippet}...</p>
                                                    )}
                                                </div>
                                            ))}
                                            {matches.length > 5 && (
                                                <p className="text-[10px] text-white/30 pt-1">+{matches.length - 5} more matches</p>
                                            )}
                                        </div>
                                    </details>
                                );
                            })}
                        </div>
                    </div>
                )}
                {evidence && !evidence.text_analysis_available && (
                    <div className="rounded-xl bg-white/3 border border-white/8 px-5 py-8 text-center">
                        <p className="text-sm text-white/40">No EDGAR text evidence available. Click &quot;Refresh from EDGAR&quot; to fetch and analyze 10-K filings.</p>
                        <button onClick={() => handleFetchEvidence(true)} disabled={evidenceLoading}
                            className="mt-4 glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-bold uppercase tracking-widest">
                            <Search className="h-3 w-3" />
                            Refresh from EDGAR
                        </button>
                    </div>
                )}
                {!evidence && !evidenceLoading && (
                    <div className="rounded-xl bg-white/3 border border-white/8 px-5 py-8 text-center">
                        <p className="text-sm text-white/40">Click &quot;View Evidence&quot; to load keyword analysis from EDGAR 10-K filings.</p>
                    </div>
                )}
                {evidenceLoading && (
                    <div className="space-y-3">
                        <Shimmer className="h-12 w-full" />
                        <Shimmer className="h-12 w-full" />
                        <Shimmer className="h-12 w-3/4" />
                    </div>
                )}
            </div>

            {/* AI Narrative Section */}
            <div className="glass-panel p-8">
                <SectionHeader
                    title="AI Moat Assessment"
                    subtitle="AI-generated competitive advantage analysis"
                    action={
                        <button onClick={handleFetchAi} disabled={aiLoading}
                            className={cn("glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest", aiLoading && "opacity-50 cursor-not-allowed")}>
                            <Sparkles className={cn("h-3 w-3", aiLoading && "animate-pulse")} />
                            {aiLoading ? "Generating..." : aiNarrative?.available ? "Regenerate" : "Generate AI"}
                        </button>
                    }
                />
                {aiError && (
                    <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25 mb-4">
                        <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
                        <p className="text-sm text-white/60">{aiError}</p>
                    </div>
                )}
                {aiLoading && (
                    <div className="rounded-2xl border border-white/6 bg-white/3 px-5 py-4 space-y-2">
                        <Shimmer className="h-2 w-20" />
                        <Shimmer className="h-2 w-full" />
                        <Shimmer className="h-2 w-4/5" />
                        <Shimmer className="h-2 w-3/4" />
                    </div>
                )}
                {aiNarrative?.available && aiNarrative.narrative.narrative && (
                    <div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/5 px-5 py-4">
                        <div className="flex items-center gap-2 mb-2">
                            <Sparkles className="h-3 w-3 text-indigo-400/70" />
                            <span className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70">AI Moat Assessment</span>
                            {aiNarrative.narrative.generated_at && (
                                <span className="text-[9px] text-white/20 ml-auto">
                                    {new Date(aiNarrative.narrative.generated_at).toLocaleDateString()}
                                </span>
                            )}
                        </div>
                        <p className="text-[12px] leading-relaxed text-white/60 whitespace-pre-line">
                            {aiNarrative.narrative.narrative}
                        </p>
                    </div>
                )}
            </div>
        </div>
    );
}