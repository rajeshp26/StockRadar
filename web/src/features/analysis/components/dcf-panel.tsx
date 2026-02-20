"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { fetchDcfValuation } from "../services/analysis.service";
import type { DcfResponse } from "../types/analysis.types";
import { useDcfHistory } from "../hooks/useDcfHistory";
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

/* ── History row (grid-based, no shadcn Table) ──────────────── */
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
        "grid-cols-[1.8fr_0.9fr_1fr_0.7fr_1fr_0.6fr_0.8fr]",
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
export function DcfPanel({ symbol }: { symbol: string }) {

  /* ── All hooks (logic unchanged) ─────────────────────────── */
  const [loading,         setLoading]         = useState(true);
  const [data,            setData]            = useState<DcfResponse | null>(null);
  const [error,           setError]           = useState<string | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [recomputing,     setRecomputing]     = useState(false);

  const {
    loading: loadingHistory,
    error:   historyError,
    history,
    reload:  reloadHistory,
  } = useDcfHistory(symbol);

  const load = useCallback(
    async (force = false) => {
      setLoading(true);
      setError(null);
      try {
        setData(await fetchDcfValuation(symbol, { force }));
      } catch (e: any) {
        setError(e?.message ?? "Failed to load DCF");
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [symbol],
  );

  useEffect(() => { void load(false); }, [load]);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try {
      await load(true);
      await reloadHistory();
    } finally {
      setRecomputing(false);
    }
  }, [load, reloadHistory]);

  const v            = data?.valuation;
  const applicability = data?.applicability;
  const curr         = v?.currency ?? "USD";

  /* ── Summary section ─────────────────────────────────────── */
  const summary = useMemo(() => (
    <div className="glass-panel p-8 relative overflow-hidden">
      {/* Top accent line */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 h-px"
        style={{ background: "linear-gradient(90deg, transparent, rgba(99,102,241,0.5) 40%, rgba(139,92,246,0.3) 70%, transparent)" }}
        aria-hidden="true"
      />

      <SectionHeader
        title="Discounted Cash Flow (DCF)"
        subtitle="Cash-flow based intrinsic value with full transparency"
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
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <MetricSkeleton /><MetricSkeleton /><MetricSkeleton />
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
            accent={(v?.upsideDownsidePct ?? 0) >= 0 ? "emerald" : "rose"}
          />
        </div>
      )}
    </div>
  ), [loading, v, curr, recomputing, handleRecompute]);

  /* ── How We Arrived section ──────────────────────────────── */
  const howArrived = useMemo(() => (
    <div className="glass-panel p-8">
      <SectionHeader
        title="How We Arrived Here"
        subtitle="Input assumptions and derived values"
      />
      {loading ? (
        <div className="grid md:grid-cols-3 gap-4">
          {Array.from({ length: 9 }).map((_, i) => <MetricSkeleton key={i} />)}
        </div>
      ) : (
        <div className="grid md:grid-cols-3 gap-4">
          <Metric label="Base FCF"           value={fmtCurrency(v?.baseFcf          ?? null, curr)} />
          <Metric label="Forecast Years"     value={fmtInt(v?.forecastYears         ?? null)}        />
          <Metric label="WACC"               value={fmtPct(v?.waccUsed              ?? null)}        />
          <Metric label="Terminal Method"    value={v?.terminalMethod               ?? "—"}          />
          <Metric label="Enterprise Value"   value={fmtCurrency(v?.enterpriseValue  ?? null, curr)} />
          <Metric label="Equity Value"       value={fmtCurrency(v?.equityValue      ?? null, curr)} />
          <Metric label="Net Debt"           value={fmtCurrency(v?.netDebtUsed      ?? null, curr)} />
          <Metric label="Shares Outstanding" value={fmtInt(v?.sharesOutstanding     ?? null)}        />
        </div>
      )}
    </div>
  ), [loading, v, curr]);

  /* ── Suitability section ─────────────────────────────────── */
  const suitability = useMemo(() => {
    const flagCount = applicability?.flags?.length ?? 0;
    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Model Suitability"
          subtitle="How well DCF applies to this stock"
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
    const headers = ["Date", "Terminal", "Intrinsic / Share", "WACC", "Enterprise", "Score", "Category"];

    return (
      <div className="glass-panel p-8">
        <SectionHeader
          title="Valuation History"
          subtitle="Previous DCF computation runs"
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
                  r.terminalMethod               ?? "—",
                  fmtCurrency(r.intrinsicValuePerShare ?? null, curr),
                  fmtPct(r.waccUsed              ?? null),
                  fmtCurrency(r.enterpriseValue  ?? null, curr),
                  fmtInt(r.score                 ?? null),
                  r.category                     ?? "—",
                ]}
              />
            ))}
          </div>
        )}
      </div>
    );
  }, [history, loadingHistory, historyError, reloadHistory, curr]);

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