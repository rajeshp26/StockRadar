"use client";

import type { DiagnosticFlag } from "../types/analysis.types";
import { Badge } from "@/components/ui/badge";

/* --------------------------------------------------
 * Formatters
 * -------------------------------------------------- */
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

/* --------------------------------------------------
 * UI Primitives
 * -------------------------------------------------- */
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
    <div className="p-6 rounded-2xl bg-white/5 border border-white/5 flex flex-col justify-center">
      <p className="text-[10px] uppercase font-black text-slate-500 tracking-[0.2em] mb-3">
        {label}
      </p>
      <div className="text-3xl font-black text-white tracking-tight">
        {value}
      </div>
      {hint ? <div className="text-xs text-slate-400 mt-2">{hint}</div> : null}
    </div>
  );
}

/**
 * ✅ Suitability flag pill (DO NOT use Badge outline here)
 * Reason: Badge outline relies on theme tokens and becomes unreadable on dark/glass.
 */
export function FlagPill({ text }: { text: string }) {
  return (
    <span
      className="
        inline-flex items-center
        rounded-full px-3 py-1
        text-[10px] font-semibold tracking-widest uppercase
        bg-white/10 border border-white/30
        text-white
      "
    >
      {text}
    </span>
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
      ? "bg-emerald-500"
      : category === "Caution"
      ? "bg-amber-500"
      : category === "Poor"
      ? "bg-rose-500"
      : "bg-slate-500";

  return (
    <div className="flex items-center gap-3">
      <div className="h-2 w-44 rounded bg-white/10">
        <div className={`h-2 rounded ${color}`} style={{ width: `${normalized}%` }} />
      </div>
      <span className="text-sm text-slate-300">{fmtInt(score)} / 100</span>
      {category ? (
        <Badge className="bg-white/10 text-white border border-white/25">
          {category}
        </Badge>
      ) : null}
    </div>
  );
}

export function DiagnosticsList({ items }: { items?: DiagnosticFlag[] }) {
  if (!items || items.length === 0) {
    return <p className="text-sm text-slate-400 italic">No diagnostics available.</p>;
  }

  return (
    <div className="space-y-4">
      {items.map((d, i) => {
        const tone =
          d.severity === "critical" || d.severity === "high"
            ? "bg-rose-500/10 border-rose-500/25"
            : d.severity === "medium"
            ? "bg-amber-500/10 border-amber-500/25"
            : d.severity === "low"
            ? "bg-sky-500/10 border-sky-500/25"
            : "bg-white/5 border-white/20";

        return (
          <div key={`${d.code}-${i}`} className={`glass rounded-2xl border p-5 transition-all ${tone}`}>
            {/* Header */}
            <div className="flex items-center gap-3 mb-2">
              <Badge
                variant="outline"
                className="bg-white/10 border-white/30 text-white font-semibold tracking-wide"
              >
                {d.code}
              </Badge>
              <span className="text-[9px] uppercase tracking-widest text-slate-400">
                {d.severity}
              </span>
            </div>

            {/* Message */}
            <p className="text-sm leading-relaxed text-slate-200">{d.message}</p>

            {d.evidence ? (
              <div className="mt-3 rounded-xl bg-black/40 p-3 text-xs overflow-x-auto">
                <pre className="text-indigo-300">{JSON.stringify(d.evidence, null, 2)}</pre>
              </div>
            ) : null}

            {d.recommendation ? (
              <div className="mt-3 flex items-start gap-2 text-xs text-slate-300">
                <span className="text-amber-400 font-bold">Action:</span>
                <span>{d.recommendation}</span>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}