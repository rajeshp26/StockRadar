"use client";

import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import type { DdmVariant, DdmValuation } from "../types/analysis.types";
import { useDdmAnalysis } from "../hooks/useDdmAnalysis";
import { useDdmHistory } from "../hooks/useDdmHistory";
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

/* ── History row ────────────────────────────────────────────── */
function HistoryRow({
  cells,
  isHeader,
}: {
  cells:     React.ReactNode[];
  isHeader?: boolean;
}) {
  return (
    <div
      className={cn(
        "grid gap-2 px-4 py-3 text-xs",
        "grid-cols-[1.8fr_0.9fr_1fr_0.7fr_0.7fr_0.6fr_0.8fr]",
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

/* ── Variant toggle (Gordon / Two-Stage) ────────────────────── */
const DDM_VARIANTS: { id: DdmVariant; label: string }[] = [
  { id: "gordon",    label: "Gordon"    },
  { id: "two_stage", label: "Two-Stage" },
];

function VariantToggle({
  value,
  onChange,
}: {
  value:    DdmVariant;
  onChange: (v: DdmVariant) => void;
}) {
  return (
    <div className="flex items-center gap-1 bg-white/5 rounded-xl p-1 border border-white/8">
      {DDM_VARIANTS.map(({ id, label }) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={cn(
            "px-4 py-1.5 rounded-lg text-[10px] font-black uppercase tracking-widest transition-all duration-200",
            value === id
              ? "bg-white/15 text-white shadow-sm border border-white/15"
              : "text-white/30 hover:text-white/60",
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

/* ── Main component ─────────────────────────────────────────── */
export function DdmPanel({ symbol }: { symbol: string }) {

  /* ── All hooks (logic unchanged) ─────────────────────────── */
  const [variant,         setVariant]         = useState<DdmVariant>("gordon");
  const [recomputing,     setRecomputing]     = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  const {
    loading, error, valuation, applicability,
    dataQuality, freshness, recompute,
  } = useDdmAnalysis(symbol, variant);

  const {
    loading: loadingHistory,
    error:   historyError,
    history,
    reload:  reloadHistory,
  } = useDdmHistory(symbol, variant);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await recompute();
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [recompute, reloadHistory]);

  /* ── Summary section ─────────────────────────────────────── */
  const summary = useMemo(() => {
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
          title="Dividend Discount Model (DDM)"
          subtitle={
            freshness?.lastEvaluatedDisplay
              ? `Last evaluated: ${freshness.lastEvaluatedDisplay}`
              : "Gordon Growth / Two-Stage dividend valuation"
          }
          action={
            <div className="flex items-center gap-3">
              {/* Variant toggle — replaces shadcn Tabs */}
              <VariantToggle value={variant} onChange={setVariant} />

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
            <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Metric
              label="Intrinsic Value"
              value={fmtCurrency(valuation?.intrinsicValue, curr)}
              accent="indigo"
            />
            <Metric
              label="Current Price"
              value={fmtCurrency(valuation?.currentPrice ?? null, curr)}
            />
            <Metric
              label="Upside / Downside"
              value={fmtPct(valuation?.upsideDownsidePct ?? null)}
              accent={(valuation?.upsideDownsidePct ?? 0) >= 0 ? "emerald" : "rose"}
            />
          </div>
        )}

        {/* Method footer tag */}
        {!loading && valuation && (
          <div className="mt-6 pt-5 border-t border-white/5 flex items-center gap-3">
            <span className="px-3 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/20 text-[10px] font-black uppercase tracking-widest text-indigo-400">
              {valuation.method ?? (variant === "gordon" ? "gordon" : "two_stage")}
            </span>
            <span className="text-[10px] text-white/25">
              {variant === "gordon"
                ? "Formula: D₁ / (k − g)"
                : "PV of high-growth dividends + Gordon terminal value"
              }
            </span>
          </div>
        )}
      </div>
    );
  }, [loading, valuation, freshness, recomputing, handleRecompute, variant]);

  /* ── How We Arrived section ──────────────────────────────── */
  const howArrived = useMemo(() => {
    const v: DdmValuation | undefined = valuation;
    const curr     = v?.currency ?? "USD";
    const decisions = (dataQuality?.inputDecisions as any)?.ddm;
    const d0Src     = decisions?.d0Source            as string | undefined;
    const kSrc      = decisions?.requiredReturn?.source as string | undefined;
    const gSrc      = decisions?.dividendGrowthRate?.source as string | undefined;
    const isTwoStage = (v?.method ?? "gordon") === "two_stage";

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="How We Arrived Here"
          subtitle="Input assumptions and derived values"
        />

        {loading ? (
          <div className="grid md:grid-cols-3 gap-4">
            {Array.from({ length: 6 }).map((_, i) => <MetricSkeleton key={i} />)}
          </div>
        ) : (
          <>
            {/* Core inputs — always shown */}
            <div className="grid md:grid-cols-3 gap-4">
              <Metric
                label="D₀ (Annual DPS)"
                value={fmtCurrency(v?.currentDps, curr)}
                hint={d0Src ? `Source: ${d0Src}` : undefined}
              />
              <Metric
                label="D₁ (Next Year DPS)"
                value={fmtCurrency(v?.nextYearDps, curr)}
              />
              <Metric
                label="g (Dividend Growth)"
                value={fmtPct(v?.dividendGrowthRate)}
                hint={gSrc ? `Source: ${gSrc}` : undefined}
              />
              <Metric
                label="k (Required Return)"
                value={fmtPct(v?.requiredReturn)}
                hint={kSrc ? `Source: ${kSrc}` : undefined}
              />
              <Metric
                label="Stability Check"
                value={
                  v
                    ? v.dividendGrowthRate < v.requiredReturn
                      ? "g < k ✅"
                      : "g ≥ k ⚠️"
                    : "—"
                }
                accent={
                  v
                    ? v.dividendGrowthRate < v.requiredReturn ? "emerald" : "rose"
                    : undefined
                }
              />
              <Metric
                label="Model"
                value={isTwoStage ? "Two-Stage" : "Gordon"}
              />
            </div>

            {/* Two-stage extras */}
            {isTwoStage && (
              <div className="mt-4 pt-4 border-t border-white/5 grid md:grid-cols-3 gap-4">
                <Metric label="High Growth Years (n)" value={v?.highGrowthYears ?? "—"} />
                <Metric label="High Growth Rate (g₁)" value={fmtPct(v?.highGrowthRate ?? null)} />
                <Metric label="Stable Growth (g₂)"    value={fmtPct(v?.stableGrowthRate ?? null)} />
                <Metric label="PV Stage 1"             value={fmtCurrency(v?.pvStage1 ?? null, curr)} />
                <Metric label="PV Terminal"            value={fmtCurrency(v?.pvTerminal ?? null, curr)} />
                <Metric label="Intrinsic = PV₁ + PVₜ" value={fmtCurrency(v?.intrinsicValue ?? null, curr)} accent="indigo" />
              </div>
            )}

            {/* Gordon formula hint */}
            {!isTwoStage && (
              <div className="mt-5 pt-4 border-t border-white/5">
                <p className="text-xs text-white/30">
                  Gordon model:{" "}
                  <span className="font-mono text-indigo-400/70">Intrinsic = D₁ / (k − g)</span>
                </p>
              </div>
            )}
          </>
        )}
      </div>
    );
  }, [loading, valuation, dataQuality, variant]);

  /* ── Suitability section ─────────────────────────────────── */
  const suitability = useMemo(() => {
    const flagCount = applicability?.flags?.length ?? 0;
    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Model Suitability"
          subtitle="How well DDM applies to this stock"
          action={
            <button
              onClick={() => setShowDiagnostics((s) => !s)}
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
    const headers = ["Date", "Method", "Intrinsic", "g", "k", "Score", "Category"];

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Valuation History"
          subtitle="Previous DDM computation runs"
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
                  r.method ?? (variant === "gordon" ? "gordon" : "two_stage"),
                  fmtCurrency(r.intrinsicValue       ?? null, curr),
                  fmtPct(r.dividendGrowthRate        ?? null),
                  fmtPct(r.requiredReturn            ?? null),
                  fmtInt(r.score                     ?? null),
                  r.category                         ?? "—",
                ]}
              />
            ))}
          </div>
        )}
      </div>
    );
  }, [loadingHistory, historyError, history, reloadHistory, valuation?.currency, variant]);

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div className="space-y-6 animate-fade-up">
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-white/60">{error}</p>
        </div>
      )}
      {summary}
      {howArrived}
      {suitability}
      <div className="glass-divider" />
      {historyCard}
    </div>
  );
}