// web/src/features/analysis/components/owner-earnings-panel.tsx
"use client";
import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { useOwnerEarningsAnalysis } from "../hooks/useOwnerEarningsAnalysis";
import { useOwnerEarningsHistory } from "../hooks/useOwnerEarningsHistory";
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
        "grid-cols-[1.8fr_1fr_1fr_0.8fr_0.8fr_0.6fr_0.8fr]",
        isHeader
          ? "glass-overline border-b border-white/5"
          : "border-b border-white/5 last:border-0 hover:bg-white/3 transition-colors"
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

/* ── Owner Earnings breakdown row ─────────────────────────────────────────── */
function OeBreakdownRow({
  label,
  value,
  sign,
  currency,
}: {
  label: string;
  value?: number | null;
  sign: "+" | "−" | "=";
  currency: string;
}) {
  const signColor =
    sign === "+"
      ? "text-emerald-400"
      : sign === "−"
      ? "text-rose-400"
      : "text-indigo-400 font-black";

  return (
    <div className="flex items-center justify-between py-2 border-b border-white/5 last:border-0">
      <div className="flex items-center gap-3">
        <span
          className={cn(
            "w-5 text-center text-sm font-black font-mono",
            signColor
          )}
        >
          {sign}
        </span>
        <span className="text-xs text-white/50">{label}</span>
      </div>
      <span
        className={cn(
          "text-sm font-black tabular-nums",
          sign === "=" ? "text-indigo-400" : "text-white/80"
        )}
      >
        {fmtCurrency(value ?? null, currency)}
      </span>
    </div>
  );
}

/* ── Main component ───────────────────────────────────────────────────────── */
export function OwnerEarningsPanel({ symbol }: { symbol: string }) {
  const { loading, error, valuation, applicability, dataQuality, freshness, recompute } =
    useOwnerEarningsAnalysis(symbol);
  const {
    loading: loadingHistory,
    error: historyError,
    history,
    reload: reloadHistory,
  } = useOwnerEarningsHistory(symbol);

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
          title="Owner Earnings (Buffett)"
          subtitle={
            freshness?.lastEvaluatedDisplay
              ? `Last evaluated: ${freshness.lastEvaluatedDisplay}`
              : "OE = Net Income + D&A − CapEx ± ΔWorking Capital"
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
            )}

            {/* Owner Earnings formula badge */}
            {!loading && v && (
              <div className="mt-5 pt-5 border-t border-white/5 flex items-center gap-3 flex-wrap">
                <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-black uppercase tracking-widest text-indigo-400">
                  Owner Earnings
                </span>
                {v.baseOe != null && (
                <span className="text-[10px] text-white/25 font-mono">
                  {fmtCurrency(v.baseOe, curr)} / yr
                </span>
                )}
                {(v.oeGrowthRateUsed != null || v.discountRateUsed != null) && (
                <span className="text-[10px] text-white/20">
                    {v.oeGrowthRateUsed != null && `· growth ${fmtPct(v.oeGrowthRateUsed)}`}
                    {v.discountRateUsed != null && ` · discount ${fmtPct(v.discountRateUsed)}`}
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
          subtitle="Owner Earnings computation waterfall"
        />

        {loading ? (
          <div className="grid md:grid-cols-2 gap-8">
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-10 rounded-xl bg-white/5 glass-shimmer" />
              ))}
            </div>
            <div className="grid grid-cols-2 gap-4">
              {Array.from({ length: 4 }).map((_, i) => (
                <MetricSkeleton key={i} />
              ))}
            </div>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-8">
            {/* Left: OE waterfall */}
            <div>
              <p className="glass-overline mb-3">Owner Earnings Waterfall</p>
              <div className="rounded-2xl border border-white/8 px-5 py-3">
                <OeBreakdownRow
                  label="Net Income"
                  value={v?.netIncomeUsed}
                  sign="+"
                  currency={curr}
                />
                <OeBreakdownRow
                  label="Depreciation & Amortization"
                  value={v?.daUsed}
                  sign="+"
                  currency={curr}
                />
                <OeBreakdownRow
                  label="Capital Expenditure"
                  value={v?.capexUsed}
                  sign="−"
                  currency={curr}
                />
                <OeBreakdownRow
                  label="ΔWorking Capital"
                  value={v?.wcChangeUsed}
                  sign="−"
                  currency={curr}
                />
                <div className="mt-2 pt-2 border-t border-white/10">
                  <OeBreakdownRow
                    label="Owner Earnings"
                    value={v?.baseOe}
                    sign="="
                    currency={curr}
                  />
                </div>
              </div>
            </div>

            {/* Right: valuation assumptions */}
            <div className="grid grid-cols-2 gap-4">
              <Metric
                label="Growth Rate"
                value={fmtPct(v?.oeGrowthRateUsed ?? null)}
              />
              <Metric
                label="Discount Rate"
                value={fmtPct(v?.discountRateUsed ?? null)}
              />
              <Metric
                label="Horizon Years"
                value={fmtInt(v?.forecastYears ?? null)}
              />
              <Metric
                label="Terminal Growth"
                value={fmtPct(v?.terminalGrowthRateUsed ?? null)}
              />
              <Metric
                label="PV Forecast OE"
                value={fmtCurrency(v?.totalPvOe ?? null, curr)}
              />
              <Metric
                label="PV Terminal"
                value={fmtCurrency(v?.pvTerminalValue ?? null, curr)}
              />
              <Metric
                label="Enterprise Value"
                value={fmtCurrency(v?.enterpriseValue ?? null, curr)}
              />
              <Metric
                label="Shares Outstanding"
                value={fmtInt(v?.sharesOutstanding ?? null)}
              />
            </div>
          </div>
        )}
      </div>
    ),
    [loading, v, curr]
  );

  /* ── History section ──────────────────────────────────────────────────── */
  const historyCard = useMemo(() => {
    const items   = history?.items ?? [];
    const headers = ["Date", "Owner Earnings", "Intrinsic / Share", "Growth", "Discount", "Score", "Category"];

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Valuation History"
          subtitle="Previous Owner Earnings computation runs"
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
                  fmtCurrency(r.baseOe        ?? null, curr),
                  fmtCurrency(r.intrinsicValuePerShare ?? null, curr),
                  fmtPct(r.oeGrowthRateUsed                ?? null),
                  fmtPct(r.discountRateUsed              ?? null),
                  fmtInt(r.score                     ?? null),
                  r.category                         ?? "—",
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