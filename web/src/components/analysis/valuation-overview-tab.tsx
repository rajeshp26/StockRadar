"use client";

import { cn } from "@/lib/utils";
import { useValuationOverview, type MethodSummary } from "@/features/analysis/hooks/useValuationOverview";
import type { IntrinsicMethod } from "@/features/analysis/components/method-selector";
import {
  TrendingUp,
  TrendingDown,
  CheckCircle2,
  Clock,
  AlertCircle,
  Ban,
  ChevronRight,
  Loader2,
  Sparkles,
} from "lucide-react";

// ─────────────────────────────────────────────────────────────────────────────
// Formatting helpers
// ─────────────────────────────────────────────────────────────────────────────

function fmtCurrency(value: number | null, currency = "USD"): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

function fmtUpside(value: number | null): string {
  if (value == null) return "—";
  const pct = value * 100;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return "";
  }
}

const REASON_LABEL: Record<string, string> = {
  NEGATIVE_EPS: "Negative EPS — method not meaningful",
  NOT_MEANINGFUL: "Company profile makes this method not meaningful",
  NO_MEANINGFUL_VALUE: "No meaningful intrinsic value computable",
  MISSING_SNAPSHOT: "Published result missing valuation data",
  SECTION_BUILD_ERROR: "Section could not be built",
};

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: MethodSummary["status"] }) {
  if (status === "not_computed") {
    return (
      <span className="flex items-center gap-1 text-amber-400/70 text-[10px] font-black uppercase tracking-widest">
        <Clock className="h-3 w-3" />
        Not Run
      </span>
    );
  }
  if (status === "not_applicable") {
    return (
      <span className="flex items-center gap-1 text-slate-400/80 text-[10px] font-black uppercase tracking-widest">
        <Ban className="h-3 w-3" />
        Not Applicable
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="flex items-center gap-1 text-rose-400/70 text-[10px] font-black uppercase tracking-widest">
        <AlertCircle className="h-3 w-3" />
        Error
      </span>
    );
  }
  if (status === "loading") {
    return (
      <span className="flex items-center gap-1 text-blue-400/70 text-[10px] font-black uppercase tracking-widest">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading
      </span>
    );
  }
  if (status === "stale") {
    return (
      <span className="flex items-center gap-1 text-amber-400 text-[10px] font-black uppercase tracking-widest">
        <Clock className="h-3 w-3" />
        Stale
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-black uppercase tracking-widest">
      <CheckCircle2 className="h-3 w-3" />
      Computed
    </span>
  );
}

function UpsideChip({ value }: { value: number | null }) {
  if (value == null) {
    return <span className="text-lg font-black text-white/20">—</span>;
  }
  const isPos = value >= 0;
  const Icon = isPos ? TrendingUp : TrendingDown;
  return (
    <span className={cn("flex items-center gap-1 text-lg font-black", isPos ? "text-emerald-400" : "text-rose-400")}>
      <Icon className="h-4 w-4" />
      {fmtUpside(value)}
    </span>
  );
}

function ScorePill({ score, category }: { score: number | null; category: string | null }) {
  if (score == null) return null;
  const colour =
    category === "Good"
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
      : category === "Caution"
        ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
        : category === "Poor"
          ? "bg-rose-500/15 text-rose-400 border-rose-500/25"
          : "bg-white/5 text-white/40 border-white/10";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-black uppercase tracking-wider",
        colour,
      )}
    >
      {score}/100
    </span>
  );
}

function MethodRow({
  method,
  onSelect,
}: {
  method: MethodSummary;
  onSelect?: (method: IntrinsicMethod) => void;
}) {
  const isComputed = method.status === "computed" || method.status === "stale";
  const isClickable = isComputed && !!onSelect;
  const reasonText = method.reasonCode ? (REASON_LABEL[method.reasonCode] ?? method.reasonCode) : null;

  return (
    <button
      type="button"
      disabled={!isClickable}
      onClick={() => isClickable && onSelect(method.id)}
      className={cn(
        "w-full text-left glass-card rounded-xl px-5 py-4 flex items-center gap-4 transition-all duration-200",
        !isComputed && "opacity-70",
        isClickable && "hover:bg-white/[0.04] cursor-pointer",
      )}
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-black text-white tracking-tight">{method.label}</p>
        <p className="text-xs text-white/45 truncate mt-0.5">{method.description}</p>
        {isComputed && method.lastComputedAt && (
          <p className="text-xs text-white/50 mt-0.5">Last run: {fmtDate(method.lastComputedAt)}</p>
        )}
        {method.status === "not_applicable" && reasonText && (
          <p className="text-xs text-slate-400/70 mt-0.5 truncate">{reasonText}</p>
        )}
        {method.errorMessage && method.status === "error" && (
          <p className="text-xs text-rose-400/60 mt-0.5 truncate">{method.errorMessage}</p>
        )}
      </div>
      <div className="text-right flex-shrink-0 w-24">
        {isComputed ? (
          <p className="text-sm font-black text-white">{fmtCurrency(method.intrinsicValue, method.currency)}</p>
        ) : (
          <p className="text-sm font-black text-white/20">—</p>
        )}
        <p className="text-xs text-white/45 mt-0.5">Intrinsic</p>
      </div>
      <div className="text-right flex-shrink-0 w-20">
        <UpsideChip value={isComputed ? method.upsideDownside : null} />
        <p className="text-xs text-white/45 mt-0.5">vs Price</p>
      </div>
      <div className="text-right flex-shrink-0 w-28 space-y-1">
        {isComputed ? (
          <ScorePill score={method.score} category={method.category} />
        ) : (
          <StatusBadge status={method.status} />
        )}
        {isComputed && (
          <div className="flex justify-end">
            <StatusBadge status={method.status} />
          </div>
        )}
      </div>
      {isClickable && <ChevronRight className="h-3.5 w-3.5 text-white/15 flex-shrink-0" />}
    </button>
  );
}

function RecommendationCard({ rec }: { rec: NonNullable<ReturnType<typeof useValuationOverview>["recommendation"]> }) {
  const consensusColor =
    rec.consensus === "Undervalued"
      ? "text-emerald-400"
      : rec.consensus === "Overvalued"
        ? "text-rose-400"
        : rec.consensus === "Mixed"
          ? "text-amber-400"
          : "text-white/60";
  const isDeterministic = rec.status !== "available";

  return (
    <div className="glass-card rounded-xl px-5 py-4 space-y-3">
      <div className="flex items-center gap-2">
        <Sparkles className="h-4 w-4 text-indigo-400" />
        <p className="text-sm font-black text-white">{isDeterministic ? "Valuation Summary" : "AI Summary"}</p>
        {isDeterministic && (
          <span className="rounded-full border border-amber-500/25 bg-amber-500/10 px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-amber-400">
            Deterministic
          </span>
        )}
      </div>
      <div className="flex items-center gap-3">
        <span className={cn("text-xl font-black", consensusColor)}>{rec.consensus}</span>
        {rec.bestMethodLabel && (
          <>
            <span className="text-xs text-white/40">•</span>
            <span className="text-xs text-white/50">Best method: {rec.bestMethodLabel}</span>
          </>
        )}
      </div>
      <p className="text-xs text-white/45 leading-relaxed">{rec.reasoning}</p>
      {rec.confidenceNote && (
        <p className="text-[10px] text-white/30 italic">{rec.confidenceNote}</p>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="glass-panel p-8 text-center">
      <p className="text-sm text-white/40">No valuation data available yet.</p>
      <p className="text-xs text-white/25 mt-2">Click any method tab and run a computation to see results here.</p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function ValuationOverviewTab({
  symbol,
  onSelectMethod,
}: {
  symbol: string;
  onSelectMethod?: (method: IntrinsicMethod) => void;
}) {
  const { methods, recommendation, loadingRec, anyComputed, allLoading } = useValuationOverview(symbol);

  if (allLoading && !anyComputed) {
    return (
      <div className="glass-panel p-8 space-y-6 animate-fade-up">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
            <Loader2 className="h-4 w-4 text-indigo-400 animate-spin" />
          </div>
          <div>
            <h3 className="text-base font-black text-white tracking-tight">Valuation Overview</h3>
            <p className="text-[11px] text-white/35 mt-0.5">Loading valuation data...</p>
          </div>
        </div>
      </div>
    );
  }

  const hasAnyData = methods.some((m) => m.status !== "loading" && m.status !== "not_computed");

  if (!hasAnyData && !allLoading) {
    return (
      <div className="space-y-6 animate-fade-up">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
            <TrendingUp className="h-4 w-4 text-indigo-400" />
          </div>
          <div>
            <h3 className="text-base font-black text-white tracking-tight">Valuation Overview</h3>
            <p className="text-[11px] text-white/35 mt-0.5">Compare intrinsic value estimates across methodologies</p>
          </div>
        </div>
        <EmptyState />
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-up">
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
          <TrendingUp className="h-4 w-4 text-indigo-400" />
        </div>
        <div>
          <h3 className="text-base font-black text-white tracking-tight">Valuation Overview</h3>
          <p className="text-[11px] text-white/35 mt-0.5">Compare intrinsic value estimates across methodologies</p>
        </div>
      </div>

      {recommendation && <RecommendationCard rec={recommendation} />}

      {loadingRec && anyComputed && (
        <div className="glass-card rounded-xl px-5 py-3 flex items-center gap-2">
          <Loader2 className="h-3 w-3 text-indigo-400 animate-spin" />
          <span className="text-xs text-white/40">Loading valuation summary...</span>
        </div>
      )}

      <div className="space-y-2">
        {methods.map((m) => (
          <MethodRow key={m.id} method={m} onSelect={onSelectMethod} />
        ))}
      </div>

      <p className="text-xs text-white/25 leading-relaxed border-t border-white/5 pt-4">
        Values refresh automatically when individual methods are recomputed. Click any computed row to view details.
      </p>
    </div>
  );
}
