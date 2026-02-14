"use client";

import type { DiagnosticFlag } from "../types/analysis.types";
import { Badge } from "@/components/ui/badge";

export function fmtCurrency(n?: number | null, currency = "USD") {
  if (n == null || Number.isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
      minimumFractionDigits: 2,
    }).format(Number(n));
  } catch {
    return `$${Number(n).toFixed(2)}`;
  }
}

export function fmtPct(n?: number | null, digits = 1) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(Number(n) * 100).toFixed(digits)}%`;
}

export function fmtInt(n?: number | null) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(Number(n))}`;
}

export function fmtDateTime(iso?: string) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

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
        <div className={`h-2 rounded ${color}`} style={{ width: `${normalized}%` }} />
      </div>
      <span className="text-sm text-slate-600">{fmtInt(score)} / 100</span>
      {category ? <Badge variant="secondary">{category}</Badge> : null}
    </div>
  );
}

export function DiagnosticsList({ items }: { items?: DiagnosticFlag[] }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-500">No diagnostics.</p>;
  }

  return (
    <div className="space-y-2">
      {items.map((d, i) => {
        const tone =
          d.severity === "critical" || d.severity === "high"
            ? "border-rose-200 bg-rose-50 text-rose-700"
            : d.severity === "medium"
            ? "border-amber-200 bg-amber-50 text-amber-700"
            : d.severity === "low"
            ? "border-sky-200 bg-sky-50 text-sky-700"
            : "border-slate-200 bg-slate-50 text-slate-700";

        return (
          <div key={`${d.code}-${i}`} className={`rounded border p-3 ${tone}`}>
            <div className="flex items-center gap-2">
              <Badge variant="outline">{d.code}</Badge>
              <span className="text-xs uppercase tracking-wide">{d.severity}</span>
            </div>
            <p className="text-sm mt-1">{d.message}</p>

            {d.evidence ? (
              <pre className="mt-2 rounded bg-white/60 p-2 text-xs overflow-x-auto">
                {JSON.stringify(d.evidence, null, 2)}
              </pre>
            ) : null}

            {d.recommendation ? (
              <p className="text-xs mt-1">
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