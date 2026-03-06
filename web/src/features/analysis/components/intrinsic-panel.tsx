"use client";
import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useAnalysis } from "../hooks/useAnalysis";
import { useLivePrice } from "../hooks/useLivePrice";
import { useRule1History } from "../hooks/useRule1History";
import type { Rule1Valuation } from "../types/analysis.types";
import type { AnalysisAnalytics } from "@/features/analysis/analytics/analysis.analytics";
import { RefreshCw, AlertTriangle, Sparkles } from "lucide-react";
import {
  Metric,
  DiagnosticsList,
  SectionHeader,
  SuitabilitySidebar,
  fmtCurrency,
  fmtPct,
  fmtInt,
  fmtDateTime,
} from "./shared-ui";

/* ── Skeleton tile ────────────────────────────────────────────────────────── */
function MetricSkeleton() {
  return (
    <div className="glass-stat space-y-3">
      <div className="h-2 w-16 rounded-full bg-white/10 glass-shimmer" />
      <div className="h-8 w-24 rounded-lg bg-white/10 glass-shimmer" />
    </div>
  );
}

/* ── AI Analyst Note ──────────────────────────────────────────────────────── */
function AnalystNote({
  summary,
  loading,
}: {
  summary?: string | null;
  loading:  boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-2xl border border-white/6 bg-white/3 px-5 py-4 space-y-2">
        <div className="h-2 w-20 rounded-full bg-white/8 glass-shimmer" />
        <div className="h-2 w-full rounded-full bg-white/5 glass-shimmer" />
        <div className="h-2 w-4/5 rounded-full bg-white/5 glass-shimmer" />
        <div className="h-2 w-3/5 rounded-full bg-white/5 glass-shimmer" />
      </div>
    );
  }

  if (!summary) return null;

  return (
    <div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/5 px-5 py-4">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="h-3 w-3 text-indigo-400/70" />
        <span className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70">
          AI Suitability Analysis
        </span>
      </div>
      <p className="text-[12px] leading-relaxed text-white/60">
        {summary}
      </p>
    </div>
  );
}

/* ── Table row ────────────────────────────────────────────────────────────── */
function HistoryRow({ cells, isHeader }: { cells: React.ReactNode[]; isHeader?: boolean }) {
  return (
    <div
      className={cn(
        "grid gap-2 px-4 py-3 text-xs",
        "grid-cols-[1.8fr_1fr_1fr_0.8fr_0.8fr_0.6fr_0.8fr]",
        isHeader
          ? "glass-overline border-b border-white/5"
          : "border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors",
      )}
    >
      {cells.map((cell, i) => (
        <div key={i} className={isHeader ? "" : "text-white/70 font-medium tabular-nums"}>
          {cell}
        </div>
      ))}
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */
export function IntrinsicPanel({
  symbol,
  analytics,
}: {
  symbol:     string;
  analytics?: AnalysisAnalytics;
}) {
  const {
    loading, error, valuation, applicability,
    dataQuality, freshness, recompute,
  } = useAnalysis(symbol, { analytics });
  const {
    loading: loadingHistory,
    error:   historyError,
    history,
    reload:  reloadHistory,
  } = useRule1History(symbol);
  const [recomputing,     setRecomputing]     = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await recompute();
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [recompute, reloadHistory]);

  const { price, currency: priceCcy, loading: loadingPrice } = useLivePrice(symbol);

  /* ── Combined summary + suitability card ──────────────────────────────── */
  const summaryCard = useMemo(() => {
    const curr = valuation?.currency ?? "USD";
    return (
      <div className="glass-panel p-8 relative overflow-hidden">
        {/* Top accent line */}
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{ background: "linear-gradient(90deg, transparent, rgba(99,102,241,0.5) 40%, rgba(139,92,246,0.3) 70%, transparent)" }}
          aria-hidden="true"
        />

        <SectionHeader
          title="Intrinsic Value Summary"
          subtitle={
            freshness?.lastEvaluatedDisplay
              ? `Rule #1 methodology · Phil Town · Last run: ${freshness.lastEvaluatedDisplay}`
              : "Rule #1 methodology · Phil Town"
          }
          action={
            <button
              onClick={handleRecompute}
              disabled={recomputing}
              className={cn(
                "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                "text-[10px] font-black uppercase tracking-widest",
                recomputing && "opacity-50 cursor-not-allowed",
              )}
            >
              <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
              {recomputing ? "Recomputing…" : "Recompute"}
            </button>
          }
        />

        {/* Two-column layout: metrics left, suitability ring right */}
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left: value metrics */}
          <div className="flex-1">
            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <Metric
                  label="Sticker Price"
                  value={fmtCurrency(valuation?.stickerPrice, curr)}
                  accent="indigo"
                />
                <Metric
                  label="MOS Price"
                  value={fmtCurrency(valuation?.mosPrice, curr)}
                  accent="emerald"
                />
                <Metric
                  label="Current Price"
                  value={
                    loadingPrice ? (
                      <span className="text-white/30 text-xl">Loading…</span>
                    ) : price != null ? (
                      fmtCurrency(price, priceCcy ?? curr)
                    ) : (
                      <span className="text-white/30 text-xl">Not available</span>
                    )
                  }
                />
              </div>
            )}
          </div>

          {/* Divider */}
          <div className="hidden lg:block w-px bg-white/8 self-stretch" />
          <div className="block lg:hidden h-px bg-white/8" />

          {/* Right: suitability ring — no summary here, lives below full-width */}
          <div className="flex justify-center lg:justify-end">
            <SuitabilitySidebar
              loading={loading}
              score={applicability?.score}
              category={applicability?.category}
              flags={applicability?.flags}
              showDiagnostics={showDiagnostics}
              onToggleDiagnostics={() => setShowDiagnostics((s) => !s)}
            />
          </div>
        </div>

        {/* AI Analyst Note — full width, below the two-column row */}
        {(loading || applicability?.suitabilitySummary) && (
          <div className="mt-6">
            <AnalystNote summary={applicability?.suitabilitySummary} loading={loading} />
          </div>
        )}

        {/* Diagnostics — expands inline below */}
        {showDiagnostics && (
          <div className="mt-6 pt-6 border-t border-white/5 animate-fade-up">
            <DiagnosticsList items={applicability?.flags} />
          </div>
        )}
      </div>
    );
  }, [
    loading, valuation, freshness, recomputing, handleRecompute,
    loadingPrice, price, priceCcy,
    applicability, showDiagnostics,
  ]);

  /* ── Breakdown section (unchanged) ───────────────────────────────────── */
  const breakdown = useMemo(() => {
    const v: Rule1Valuation | undefined = valuation;
    const curr      = v?.currency ?? "USD";
    const decisions = dataQuality?.inputDecisions;
    const eps0 =
      v?.eps0 ??
      (typeof decisions?.eps0?.value === "number" ? decisions.eps0.value : undefined);
    const growth =
      v?.growth ??
      (typeof decisions?.growth?.valueClamped === "number" ? decisions.growth.valueClamped : undefined);
    const futurePE =
      v?.futurePE ??
      (typeof decisions?.futurePE?.selected === "number" ? decisions.futurePE.selected : undefined);
    const discountRate =
      v?.discountRate ??
      (typeof decisions?.assumptions?.discountRate === "number" ? decisions.assumptions.discountRate : undefined);
    const horizonYears =
      v?.horizonYears ??
      (typeof decisions?.assumptions?.horizonYears === "number" ? decisions.assumptions.horizonYears : undefined);
    const mosPct =
      v?.mos ??
      (typeof decisions?.assumptions?.mos === "number" ? decisions.assumptions.mos : undefined);
    const futureEPSDerived =
      typeof eps0 === "number" && typeof growth === "number" && typeof horizonYears === "number"
        ? eps0 * Math.pow(1 + growth, horizonYears)
        : undefined;
    const futureEPS =
      typeof v?.futureEPS === "number" && v.futureEPS > 0 ? v.futureEPS : futureEPSDerived;

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="How We Arrived Here"
          subtitle="Input assumptions and derived values"
        />
        {loading ? (
          <div className="grid md:grid-cols-3 gap-4">
            {Array.from({ length: 7 }).map((_, i) => <MetricSkeleton key={i} />)}
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-4">
            <Metric label="EPS₀"         value={fmtCurrency(eps0, curr)}         />
            <Metric label="Growth"        value={fmtPct(growth)}                  />
            <Metric label="Future EPS"    value={fmtCurrency(futureEPS, curr)}    />
            <Metric label="Future P/E"    value={fmtInt(futurePE)}                />
            <Metric label="Discount Rate" value={fmtPct(discountRate)}            />
            <Metric label="Horizon"       value={`${horizonYears ?? "—"} yrs`}    />
            <Metric label="MOS %"         value={fmtPct(mosPct)}                  />
          </div>
        )}
      </div>
    );
  }, [loading, valuation, dataQuality?.inputDecisions]);

  /* ── History section (unchanged) ─────────────────────────────────────── */
  const historyCard = useMemo(() => {
    const items   = history?.items ?? [];
    const curr    = valuation?.currency ?? "USD";
    const headers = ["Date", "Sticker", "MOS", "Growth", "Future P/E", "Score", "Category"];
    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Valuation History"
          subtitle="Previous computation runs"
          action={
            historyError ? (
              <button
                onClick={() => void reloadHistory()}
                className="glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest"
              >
                <RefreshCw className="h-3 w-3" /> Retry
              </button>
            ) : undefined
          }
        />
        {loadingHistory ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="h-10 rounded-xl bg-white/5 glass-shimmer" />
            ))}
          </div>
        ) : historyError ? (
          <div className="flex items-center gap-3 p-4 rounded-xl bg-rose-500/8 border border-rose-500/20">
            <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
            <p className="text-sm text-white/50">Could not load history.</p>
          </div>
        ) : items.length === 0 ? (
          <p className="text-sm text-white/30 italic">No history yet — run a computation to start tracking.</p>
        ) : (
          <div className="rounded-2xl overflow-hidden border border-white/8">
            <HistoryRow cells={headers} isHeader />
            {items.map((r, idx) => (
              <HistoryRow
                key={`${r.runAt}-${idx}`}
                cells={[
                  fmtDateTime(r.runAt),
                  fmtCurrency(r.stickerPrice, curr),
                  fmtCurrency(r.mosPrice, curr),
                  fmtPct(r.growth),
                  fmtInt(r.futurePE),
                  fmtInt(r.score),
                  r.category ?? "—",
                ]}
              />
            ))}
          </div>
        )}
      </div>
    );
  }, [loadingHistory, historyError, history, reloadHistory, valuation?.currency]);

  /* ── Render ───────────────────────────────────────────────────────────── */
  return (
    <div className="space-y-6 animate-fade-up">
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-white/60">{error}</p>
        </div>
      )}
      {summaryCard}
      {breakdown}
      <div className="glass-divider" />
      {historyCard}
    </div>
  );
}