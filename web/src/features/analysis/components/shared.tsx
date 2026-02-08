// src/features/analysis/components/shared.tsx
"use client";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { DiagnosticFlag } from "../types/analysis.types";

/* ----------------------------------------------------------
   Metric block — used in “How We Arrived Here”
   ---------------------------------------------------------- */
export function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number | JSX.Element;
  hint?: string;
}) {
  return (
    <div className="rounded border p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-medium">{value}</div>
      {hint ? <div className="text-xs text-slate-400 mt-1">{hint}</div> : null}
    </div>
  );
}

/* ----------------------------------------------------------
   Score bar — supports suitability summaries across panels
   ---------------------------------------------------------- */
export function ScoreBar({
  score,
  category,
}: {
  score?: number;
  category?: string;
}) {
  const normalized = Math.max(0, Math.min(100, score ?? 0));

  const color =
    category === "Good"
      ? "bg-emerald-600"
      : category === "Caution"
      ? "bg-amber-600"
      : category === "Poor"
      ? "bg-rose-600"
      : "bg-slate-600";

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-44 rounded bg-slate-200">
        <div
          className={`h-2 rounded ${color}`}
          style={{ width: `${normalized}%` }}
        />
      </div>
      <span className="text-sm text-slate-600">
        {Number.isFinite(score) ? `${score} / 100` : "—"}
      </span>
      {category ? <Badge variant="secondary">{category}</Badge> : null}
    </div>
  );
}

/* ----------------------------------------------------------
   Diagnostics list — shared across analysis methods
   ---------------------------------------------------------- */
export function DiagnosticsList({ items }: { items?: DiagnosticFlag[] }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-500">No diagnostics.</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((d, i) => {
        const tone =
          d.severity === "critical"
            ? "border-rose-200 bg-rose-50 text-rose-700"
            : d.severity === "high"
            ? "border-rose-200 bg-rose-50 text-rose-700"
            : d.severity === "medium"
            ? "border-amber-200 bg-amber-50 text-amber-700"
            : d.severity === "low"
            ? "border-sky-200 bg-sky-50 text-sky-700"
            : "border-slate-200 bg-slate-50 text-slate-700";

        return (
          <div key={`${d.code}-${i}`} className={`rounded border p-3 ${tone}`}>
            {/* Header */}
            <div className="flex items-center gap-2">
              <Badge variant="outline">{d.code}</Badge>
              <span className="text-xs uppercase tracking-wide">{d.severity}</span>
            </div>

            {/* Message */}
            <p className="text-sm mt-1">{d.message}</p>

            {/* Evidence */}
            {d.evidence ? (
              <pre className="mt-2 rounded bg-white/60 p-2 text-xs text-slate-700 overflow-x-auto">
                {JSON.stringify(d.evidence, null, 2)}
              </pre>
            ) : null}

            {/* Recommendation */}
            {d.recommendation ? (
              <p className="text-xs text-slate-600 mt-1">
                <span className="font-medium">Recommendation: </span>
                {d.recommendation}
              </p>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/* ----------------------------------------------------------
   Shared Skeletons — used for compact metric groups
   ---------------------------------------------------------- */
export function MetricSkeletonGrid({ count = 6 }: { count?: number }) {
  return (
    <div className="grid md:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-16" />
      ))}
    </div>
  );
}

export function SummarySkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Skeleton className="h-20" />
      <Skeleton className="h-20" />
      <Skeleton className="h-20" />
    </div>
  );
}