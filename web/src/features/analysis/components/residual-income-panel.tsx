// web/src/features/analysis/components/residual-income-panel.tsx
"use client";
import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useResidualIncomeAnalysis } from "../hooks/useResidualIncomeAnalysis";
import { useResidualIncomeHistory } from "../hooks/useResidualIncomeHistory";
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

/* ── AI analyst note ──────────────────────────────────────────────────────── */
function AnalystNote({
  summary,
  loading,
}: {
  summary?: string | null;
  loading: boolean;
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
      <p className="text-[12px] leading-relaxed text-white/60">{summary}</p>
    </div>
  );
}

/* ── History row ──────────────────────────────────────────────────────────── */
function HistoryRow({
  cells,
  isHeader,
}: {
  cells: React.ReactNode[];
  isHeader?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-2 px-4 py-3 text-xs",
        "grid-cols-[1.8fr_1fr_0.8fr_0.8fr_0.8fr_0.6fr_0.8fr]",
        isHeader
          ? "glass-overline border-b border-white/5"
          : "border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors",
      )}
    >
      {cells.map((cell, i) => (
        <div
          key={i}
          className={isHeader ? "" : "text-white/70 font-medium tabular-nums"}
        >
          {cell}
        </div>
      ))}
    </div>
  );
}

/* ── ROE vs CoE spread indicator ──────────────────────────────────────────── */
function RoeSpreadBadge({ roe0, costOfEquityUsed }: { roe0?: number | null; costOfEquityUsed?: number | null }) {
  if (roe0 == null || costOfEquityUsed == null) return null;
  const spread     = roe0 - costOfEquityUsed;
  const isPositive = spread >= 0;
  return (
    <div className={cn(
      "inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border text-[10px] font-black uppercase tracking-widest",
      isPositive
        ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400"
        : "bg-rose-500/10 border-rose-500/20 text-rose-400",
    )}>
      <span>ROE − CoE = {(spread * 100).toFixed(1)}%</span>
      <span>{isPositive ? "Value Creating ✅" : "Value Destroying ⚠️"}</span>
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */
export function ResidualIncomePanel({ symbol }: { symbol: string }) {
  const {
    loading,
    error,
    valuation,
    applicability,
    freshness,
    recompute,
  } = useResidualIncomeAnalysis(symbol);
  const {
    loading: loadingHistory,
    error: historyError,
    history,
    reload: reloadHistory,
  } = useResidualIncomeHistory(symbol);

  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [recomputing, setRecomputing] = useState(false);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await recompute();
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [recompute, reloadHistory]);

  const v    = valuation;
  const curr = v?.currency ?? "USD";

  /* ── Summary card ─────────────────────────────────────────────────────── */
  const summaryCard = useMemo(
    () => (
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
          title="Residual Income (Economic Profit)"
          subtitle={
            freshness?.lastEvaluatedDisplay
              ? `Last evaluated: ${freshness.lastEvaluatedDisplay}`
              : "RI = BV/Share + Σ [(ROE − CoE) × BV] / (1 + CoE)ᵗ + Terminal"
          }
          action={
            <button
              onClick={handleRecompute}
              disabled={loading || recomputing}
              className={cn(
                "glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl",
                "text-[10px] font-black uppercase tracking-widest",
                (loading || recomputing) && "opacity-50 cursor-not-allowed"
              )}
            >
              <RefreshCw
                className={cn("h-3 w-3", recomputing && "animate-spin")}
              />
              {recomputing ? "Recomputing…" : "Recompute"}
            </button>
          }
        />

        {/* Two-column layout */}
        <div className="flex flex-col lg:flex-row gap-8">
          {/* Left: key value metrics */}
          <div className="flex-1">
            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <MetricSkeleton />
                <MetricSkeleton />
                <MetricSkeleton />
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <Metric
                    label="Intrinsic Value / Share"
                    value={fmtCurrency(v?.intrinsicValuePerShare ?? null, curr)}
                    accent="indigo"
                  />
                  <Metric
                    label="Current Price"
                    value={fmtCurrency(v?.currentPrice ?? null, curr)}
                  />
                  <Metric
                    label="Upside / Downside"
                    value={fmtPct(v?.upsideDownsidePct ?? null)}
                    accent={
                      (v?.upsideDownsidePct ?? 0) >= 0 ? "emerald" : "rose"
                    }
                  />
                </div>

                {/* ROE vs CoE spread badge */}
                {v && (
                  <div className="mt-5 pt-5 border-t border-white/5 flex items-center gap-3 flex-wrap">
                    <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-black uppercase tracking-widest text-indigo-400">
                      Residual Income
                    </span>
                    <RoeSpreadBadge
                      roe0={v.roe0}
                      costOfEquityUsed={v.costOfEquityUsed}
                    />
                  </div>
                )}
              </>
            )}
          </div>

          {/* Dividers */}
          <div className="hidden lg:block w-px bg-white/8 self-stretch" />
          <div className="block lg:hidden h-px bg-white/8" />

          {/* Right: suitability ring */}
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

        {/* AI analyst note */}
        {(loading || applicability?.suitabilitySummary) && (
          <div className="mt-6">
            <AnalystNote
              summary={applicability?.suitabilitySummary}
              loading={loading}
            />
          </div>
        )}

        {/* Diagnostics drawer */}
        {showDiagnostics && (
          <div className="mt-6 pt-6 border-t border-white/5 animate-fade-up">
            <DiagnosticsList items={applicability?.flags} />
          </div>
        )}
      </div>
    ),
    [
      loading,
      v,
      curr,
      recomputing,
      handleRecompute,
      applicability,
      showDiagnostics,
      freshness,
    ]
  );

  /* ── How We Arrived section ───────────────────────────────────────────── */
  const howArrived = useMemo(
    () => (
      <div className="glass-panel p-8">
        <SectionHeader
          title="How We Arrived Here"
          subtitle="Input assumptions and derived values"
        />

        {loading ? (
          <div className="grid md:grid-cols-3 gap-4">
            {Array.from({ length: 9 }).map((_, i) => (
              <MetricSkeleton key={i} />
            ))}
          </div>
        ) : (
          <>
            {/* Row 1: Core inputs */}
            <div className="grid md:grid-cols-3 gap-4">
              <Metric
                label="Book Value / Share (BV₀)"
                value={fmtCurrency(v?.bvPerShare ?? null, curr)}
              />
              <Metric
                label="EPS (Earnings / Share)"
                value={fmtCurrency(v?.eps0 ?? null, curr)}
              />
              <Metric
                label="ROE"
                value={fmtPct(v?.roe0 ?? null)}
                hint="Return on Equity = EPS / BV"
              />
              <Metric
                label="Cost of Equity (CoE)"
                value={fmtPct(v?.costOfEquityUsed ?? null)}
                hint="Required return (e.g. CAPM)"
              />
              <Metric
                label="RI / Share"
                value={fmtCurrency(v?.ri0PerShare ?? null, curr)}
                accent={
                  (v?.ri0PerShare ?? 0) >= 0 ? "emerald" : "rose"
                }
                hint="(ROE − CoE) × BV"
              />
              <Metric
                label="Forecast Horizon"
                value={fmtInt(v?.forecastYears ?? null)}
                hint="Years of explicit RI forecast"
              />
            </div>

            {/* Row 2: Value build-up */}
            <div className="mt-4 pt-4 border-t border-white/5 grid md:grid-cols-3 gap-4">
              <Metric
                label="PV of Forecast RI"
                value={fmtCurrency(v?.totalPvRiPerShare ?? null, curr)}
              />
              <Metric
                label="PV of Terminal Value"
                value={fmtCurrency(v?.pvTerminalRiPerShare ?? null, curr)}
              />
              <Metric
                label="Intrinsic = BV + PV(RI) + PV(TV)"
                value={fmtCurrency(v?.intrinsicValuePerShare ?? null, curr)}
                accent="indigo"
              />
            </div>

            {/* CAPM inputs if available */}
            {(v?.betaUsed != null || v?.rfUsed != null || v?.erpUsed != null) && (
                <div className="mt-4 pt-4 border-t border-white/5 grid md:grid-cols-3 gap-4">
                {v.betaUsed != null && <Metric label="Beta (β)" value={v.betaUsed.toFixed(2)} />}
                {v.rfUsed   != null && <Metric label="Risk-Free Rate (rf)" value={fmtPct(v.rfUsed)} />}
                {v.erpUsed  != null && <Metric label="Equity Risk Premium" value={fmtPct(v.erpUsed)} />}
                </div>
            )}

            {/* Formula note */}
            <div className="mt-5 pt-4 border-t border-white/5">
              <p className="text-xs text-white/30 font-mono">
                Intrinsic ={" "}
                <span className="text-indigo-400/70">BV₀</span> + Σ{" "}
                <span className="text-indigo-400/70">
                  [(ROE − CoE) × BVₜ₋₁] / (1 + CoE)ᵗ
                </span>{" "}
                + Terminal
              </p>
            </div>
          </>
        )}
      </div>
    ),
    [loading, v, curr]
  );

  /* ── History section ──────────────────────────────────────────────────── */
  const historyCard = useMemo(() => {
    const items   = history?.items ?? [];
    const headers = ["Date", "Intrinsic / Share", "ROE", "CoE", "RI / Share", "Score", "Category"];

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Valuation History"
          subtitle="Previous Residual Income computation runs"
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
          <p className="text-sm text-white/30 italic">
            No history yet — run a computation to start tracking.
          </p>
        ) : (
          <div className="rounded-2xl overflow-hidden border border-white/8">
            <HistoryRow cells={headers} isHeader />
            {items.map((r, idx) => (
              <HistoryRow
                key={`${r.runAt}-${idx}`}
                cells={[
                  fmtDateTime(r.runAt),
                  fmtCurrency(r.intrinsicValuePerShare  ?? null, curr),
                  fmtPct(r.roe0                          ?? null),
                  fmtPct(r.costOfEquityUsed                 ?? null),
                  fmtCurrency(r.ri0PerShare  ?? null, curr),
                  fmtInt(r.score                        ?? null),
                  r.category                            ?? "—",
                ]}
              />
            ))}
          </div>
        )}
      </div>
    );
  }, [history, loadingHistory, historyError, reloadHistory, curr]);

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
      {howArrived}
      <div className="glass-divider" />
      {historyCard}
    </div>
  );
}