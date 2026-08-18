// web/src/features/analysis/components/valuation-overview.tsx
"use client";
import { cn } from "@/lib/utils";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  CheckCircle2,
  Clock,
  AlertCircle,
  Loader2,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import {
  useValuationOverview,
  type MethodSummary,
  type MethodStatus,
} from "../hooks/useValuationOverview";
import type { IntrinsicMethod } from "./method-selector";

// ─────────────────────────────────────────────────────────────────────────────
// Props
// ─────────────────────────────────────────────────────────────────────────────

interface ValuationOverviewProps {
  symbol:          string;
  onSelectMethod?: (method: IntrinsicMethod) => void;
}

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────

function fmtCurrency(value: number | null, currency = "USD"): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", {
    style:                 "currency",
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
      day:   "numeric",
      year:  "numeric",
    });
  } catch {
    return "";
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: MethodStatus }) {
  if (status === "loading") {
    return (
      <span className="flex items-center gap-1 text-white/30 text-[10px] font-black uppercase tracking-widest">
        <Loader2 className="h-3 w-3 animate-spin" />
        Loading
      </span>
    );
  }
  if (status === "not_computed") {
    return (
      <span className="flex items-center gap-1 text-amber-400/70 text-[10px] font-black uppercase tracking-widest">
        <Clock className="h-3 w-3" />
        Not Run
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
  return (
    <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-black uppercase tracking-widest">
      <CheckCircle2 className="h-3 w-3" />
      Computed
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Upside chip
// ─────────────────────────────────────────────────────────────────────────────

function UpsideChip({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <span className="text-lg font-black text-white/20">—</span>
    );
  }
  const isPos = value >= 0;
  const Icon  = isPos ? TrendingUp : TrendingDown;
  return (
    <span
      className={cn(
        "flex items-center gap-1 text-lg font-black",
        isPos ? "text-emerald-400" : "text-rose-400"
      )}
    >
      <Icon className="h-4 w-4" />
      {fmtUpside(value)}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Score pill
// ─────────────────────────────────────────────────────────────────────────────

function ScorePill({
  score,
  category,
}: {
  score:    number | null;
  category: string | null;
}) {
  if (score == null) return null;
  const colour =
    category === "Good"    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" :
    category === "Caution" ? "bg-amber-500/15   text-amber-400   border-amber-500/25"   :
    category === "Poor"    ? "bg-rose-500/15    text-rose-400    border-rose-500/25"    :
                             "bg-white/5        text-white/40    border-white/10";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border",
        "text-[10px] font-black uppercase tracking-wider",
        colour,
      )}
    >
      {score}/100
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Single method row
// ─────────────────────────────────────────────────────────────────────────────

function MethodRow({
  method,
  isHighlighted,
  onClick,
}: {
  method:        MethodSummary;
  isHighlighted: boolean;
  onClick:       () => void;
}) {
  const isComputed = method.status === "computed";
  const isLoading  = method.status === "loading";

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left glass-card rounded-xl px-5 py-4",
        "flex items-center gap-4 transition-all duration-200",
        "hover:bg-white/[0.06] group",
        isHighlighted && "ring-1 ring-indigo-500/50 bg-indigo-500/5",
        !isComputed && !isLoading && "opacity-70",
      )}
    >
      {/* Method info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-0.5">
          <p className="text-sm font-black text-white tracking-tight">
            {method.label}
          </p>
          {isHighlighted && (
            <span className="px-1.5 py-0.5 rounded-md bg-indigo-500/20 border border-indigo-500/30 text-[9px] font-black uppercase tracking-widest text-indigo-300">
              Recommended
            </span>
          )}
        </div>
        <p className="text-xs text-white/35 truncate">{method.description}</p>
        {isComputed && method.lastComputedAt && (
          <p className="text-[10px] text-white/20 mt-0.5">
            Last run: {fmtDate(method.lastComputedAt)}
          </p>
        )}
      </div>

      {/* Intrinsic value */}
      <div className="text-right flex-shrink-0 w-24">
        {isLoading ? (
          <div className="h-4 w-16 rounded bg-white/5 animate-pulse ml-auto" />
        ) : isComputed ? (
          <p className="text-sm font-black text-white">
            {fmtCurrency(method.intrinsicValue, method.currency)}
          </p>
        ) : (
          <p className="text-sm font-black text-white/20">—</p>
        )}
        <p className="text-[10px] text-white/25 mt-0.5">Intrinsic</p>
      </div>

      {/* Upside/downside */}
      <div className="text-right flex-shrink-0 w-20">
        {isLoading ? (
          <div className="h-4 w-12 rounded bg-white/5 animate-pulse ml-auto" />
        ) : (
          <UpsideChip value={isComputed ? method.upsideDownside : null} />
        )}
        <p className="text-[10px] text-white/25 mt-0.5">vs Price</p>
      </div>

      {/* Score + status */}
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

      {/* Chevron */}
      <ChevronRight className="h-3.5 w-3.5 text-white/15 group-hover:text-white/40 flex-shrink-0 transition-colors" />
    </button>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Consensus badge
// ─────────────────────────────────────────────────────────────────────────────

function ConsensusBadge({ consensus }: { consensus: string }) {
  const map: Record<string, string> = {
    "Undervalued":   "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
    "Fairly Valued": "bg-blue-500/15    text-blue-400    border-blue-500/25",
    "Overvalued":    "bg-rose-500/15    text-rose-400    border-rose-500/25",
    "Mixed":         "bg-amber-500/15   text-amber-400   border-amber-500/25",
  };
  const colour = map[consensus] ?? "bg-white/5 text-white/40 border-white/10";
  return (
    <span
      className={cn(
        "px-3 py-1 rounded-xl border text-[11px] font-black uppercase tracking-widest",
        colour,
      )}
    >
      {consensus}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// AI Recommendation panel
// ─────────────────────────────────────────────────────────────────────────────

function AIRecommendationPanel({
  recommendation,
  loading,
  anyComputed,
}: {
  recommendation: ReturnType<typeof useValuationOverview>["recommendation"];
  loading:        boolean;
  anyComputed:    boolean;
}) {
  if (!anyComputed && !loading) {
    return (
      <div className="rounded-xl border border-white/5 bg-white/2 px-5 py-4 flex items-center gap-3">
        <Sparkles className="h-4 w-4 text-white/15 flex-shrink-0" />
        <p className="text-xs text-white/25 leading-relaxed">
          Run at least one valuation method to receive an AI recommendation on which approach best suits this company.
        </p>
      </div>
    );
  }

  if (loading || (!recommendation && anyComputed)) {
    return (
      <div className="rounded-xl border border-indigo-500/15 bg-indigo-500/5 px-5 py-4 flex items-center gap-3">
        <Loader2 className="h-4 w-4 text-indigo-400/50 flex-shrink-0 animate-spin" />
        <p className="text-xs text-white/35">Generating AI recommendation…</p>
      </div>
    );
  }

  if (!recommendation) return null;

  return (
    <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/5 px-5 py-5 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Sparkles className="h-4 w-4 text-indigo-400 flex-shrink-0" />
          <p className="text-sm font-black text-white tracking-tight">
            AI Recommendation
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ConsensusBadge consensus={recommendation.consensus} />
          <span className="text-[10px] font-black uppercase tracking-widest text-indigo-300 px-2 py-0.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
            {recommendation.bestMethodLabel}
          </span>
        </div>
      </div>

      {/* Reasoning */}
      <p className="text-sm text-white/65 leading-relaxed">
        {recommendation.reasoning}
      </p>

      {/* Confidence note */}
      {recommendation.confidenceNote && (
        <p className="text-[11px] text-white/30 leading-relaxed border-t border-white/5 pt-3">
          {recommendation.confidenceNote}
        </p>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function ValuationOverview({ symbol, onSelectMethod }: ValuationOverviewProps) {
  const {
    methods,
    recommendation,
    loadingRec,
    anyComputed,
    allLoading,
  } = useValuationOverview(symbol);

  const handleMethodClick = (id: IntrinsicMethod) => {
    onSelectMethod?.(id);
  };

  const bestMethodId = recommendation?.bestMethod;
  // Map backend method ids to frontend IntrinsicMethod ids
  const backendToFrontend: Record<string, IntrinsicMethod> = {
    rule1:           "rule1",
    dcf:             "dcf",
    ddm_gordon:      "ddm",
    owner_earnings:  "ownerEarnings",
    residual_income: "residualIncome",
  };
  const highlightedId = bestMethodId ? backendToFrontend[bestMethodId] : null;

  return (
    <div className="glass-panel p-8 space-y-6 animate-fade-up">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
          <TrendingUp className="h-4 w-4 text-indigo-400" />
        </div>
        <div>
          <h3 className="text-base font-black text-white tracking-tight">
            Valuation Overview
          </h3>
          <p className="text-[11px] text-white/35 mt-0.5">
            Compare intrinsic value estimates across methodologies
          </p>
        </div>
      </div>

      <div className="glass-divider" />

      {/* AI Recommendation */}
      <AIRecommendationPanel
        recommendation={recommendation}
        loading={loadingRec}
        anyComputed={anyComputed}
      />

      {/* Method rows */}
      <div className="space-y-2">
        {methods.map((method) => (
          <MethodRow
            key={method.id}
            method={method}
            isHighlighted={method.id === highlightedId}
            onClick={() => handleMethodClick(method.id)}
          />
        ))}
      </div>

      {/* Footer */}
      <p className="text-xs text-white/25 leading-relaxed border-t border-white/5 pt-4">
        Click any method to view full assumptions, diagnostics, and history.
        Values refresh automatically when individual methods are recomputed.
      </p>
    </div>
  );
}