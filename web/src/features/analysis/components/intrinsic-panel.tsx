"use client";

import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useAnalysis } from "../hooks/useAnalysis";
import { useLivePrice } from "../hooks/useLivePrice";
import { useRule1History } from "../hooks/useRule1History";
import type { Rule1Valuation } from "../types/analysis.types";
import type { AnalysisAnalytics } from "@/features/analysis/analytics/analysis.analytics";
import { RefreshCw, ChevronDown, ChevronUp, AlertTriangle } from "lucide-react";
import {
  Metric,
  ScoreBar,
  DiagnosticsList,
  FlagPill,
  SectionHeader,
  fmtCurrency,
  fmtPct,
  fmtInt,
  fmtDateTime,
} from "./shared-ui";

/* ── Skeleton tile ──────────────────────────────────────────── */
function MetricSkeleton() {
  return (
    <div className="glass-stat space-y-3">
      <div className="h-2 w-16 rounded-full bg-white/10 glass-shimmer" />
      <div className="h-8 w-24 rounded-lg bg-white/10 glass-shimmer" />
    </div>
  );
}

/* ── Table row ──────────────────────────────────────────────── */
function HistoryRow({
  cells,
  isHeader,
}: {
  cells:    React.ReactNode[];
  isHeader?: boolean;
}) {
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

/* ── Main component ─────────────────────────────────────────── */
export function IntrinsicPanel({
  symbol,
  analytics,
}: {
  symbol:     string;
  analytics?: AnalysisAnalytics;
}) {
  /* ── All hooks (logic unchanged) ─────────────────────────── */
  const {
    loading, error, valuation, applicability,
    dataQuality, freshness, recompute,
  } = useAnalysis(symbol, { analytics });

  const {
    loading: loadingHistory,
    error: historyError,
    history,
    reload: reloadHistory,
  } = useRule1History(symbol);

  const [recomputing,      setRecomputing]      = useState(false);
  const [showDiagnostics,  setShowDiagnostics]  = useState(false);

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

  /* ── Summary section ─────────────────────────────────────── */
  const summary = useMemo(() => {
    const curr = valuation?.currency ?? "USD";
    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Intrinsic Value Summary"
          subtitle="Rule #1 methodology · Phil Town"
          action={
            <div className="flex items-center gap-2">
              {freshness?.lastEvaluatedDisplay && (
                <span className="text-[10px] text-white/25 hidden md:inline">
                  Last run: {freshness.lastEvaluatedDisplay}
                </span>
              )}
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
            </div>
          }
        />

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <MetricSkeleton />
            <MetricSkeleton />
            <MetricSkeleton />
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
    );
  }, [loading, valuation, freshness, recomputing, loadingPrice, price, priceCcy, handleRecompute]);

  /* ── Breakdown section ───────────────────────────────────── */
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
            <Metric label="EPS₀"          value={fmtCurrency(eps0, curr)}         />
            <Metric label="Growth"         value={fmtPct(growth)}                  />
            <Metric label="Future EPS"     value={fmtCurrency(futureEPS, curr)}    />
            <Metric label="Future P/E"     value={fmtInt(futurePE)}                />
            <Metric label="Discount Rate"  value={fmtPct(discountRate)}            />
            <Metric label="Horizon"        value={`${horizonYears ?? "—"} yrs`}    />
            <Metric label="MOS %"          value={fmtPct(mosPct)}                  />
          </div>
        )}
      </div>
    );
  }, [loading, valuation, dataQuality?.inputDecisions]);

  /* ── Suitability section ─────────────────────────────────── */
  const suitability = useMemo(() => {
    const flagCount = applicability?.flags?.length ?? 0;

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Model Suitability"
          subtitle="How well Rule #1 applies to this stock"
          action={
            <button
              onClick={() => setShowDiagnostics((v) => !v)}
              className={cn(
                "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                "text-[10px] font-black uppercase tracking-widest",
                showDiagnostics && "bg-white/10 border-white/15",
              )}
            >
              {showDiagnostics
                ? <><ChevronUp   className="h-3 w-3" /> Hide Diagnostics</>
                : <><ChevronDown className="h-3 w-3" /> Diagnostics {flagCount > 0 && `(${flagCount})`}</>
              }
            </button>
          }
        />

        {loading ? (
          <div className="h-6 w-64 rounded-full bg-white/10 glass-shimmer" />
        ) : (
          <div className="space-y-5">
            <ScoreBar score={applicability?.score} category={applicability?.category} />

            {/* Flag pills */}
            {(applicability?.flags?.length ?? 0) > 0 && (
              <div className="flex flex-wrap gap-2">
                {applicability!.flags.slice(0, 4).map((f, i) => (
                  <FlagPill key={`${f.code}-${i}`} text={f.code} />
                ))}
                {applicability!.flags.length > 4 && (
                  <span className="text-xs text-white/30 self-center">
                    +{applicability!.flags.length - 4} more
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Diagnostics drawer */}
        {showDiagnostics && (
          <div className="mt-6 pt-6 border-t border-white/5 animate-fade-up">
            <DiagnosticsList items={applicability?.flags} />
          </div>
        )}
      </div>
    );
  }, [loading, applicability, showDiagnostics]);

  /* ── History section ─────────────────────────────────────── */
  const historyCard = useMemo(() => {
    const items = history?.items ?? [];
    const curr  = valuation?.currency ?? "USD";

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
                <RefreshCw className="h-3 w-3" />
                Retry
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
          /* Custom glass table — avoids shadcn Table light-mode inheritance */
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

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div className="space-y-6 animate-fade-up">
      {/* Error banner */}
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-white/60">{error}</p>
        </div>
      )}

      {summary}
      {breakdown}
      {suitability}

      {/* Divider */}
      <div className="glass-divider" />

      {historyCard}
    </div>
  );
}