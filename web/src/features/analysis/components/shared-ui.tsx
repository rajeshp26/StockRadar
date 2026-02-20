"use client";

import { cn } from "@/lib/utils";
import type { DiagnosticFlag } from "../types/analysis.types";

/* ==========================================================
   FORMATTERS — untouched
   ========================================================== */
export function fmtCurrency(n?: number | null, currency = "USD") {
  if (n == null || Number.isNaN(n)) return "—";
  try {
    return new Intl.NumberFormat(undefined, {
      style:                "currency",
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

/* ==========================================================
   METRIC — stat tile used across all panels
   ========================================================== */
export function Metric({
  label,
  value,
  hint,
  accent,
}: {
  label:   string;
  value:   string | number | React.ReactNode;
  hint?:   string;
  accent?: "indigo" | "emerald" | "rose" | "amber";
}) {
  const valueColor = {
    indigo:  "text-indigo-400",
    emerald: "text-emerald-400",
    rose:    "text-rose-400",
    amber:   "text-amber-400",
  }[accent ?? ""] ?? "text-white";

  return (
    <div className="glass-stat">
      <p className="glass-overline">{label}</p>
      <div className={cn("text-3xl font-black tracking-tighter", valueColor)}>
        {value}
      </div>
      {hint && (
        <p className="text-[10px] text-white/30 leading-relaxed mt-1">{hint}</p>
      )}
    </div>
  );
}

/* ==========================================================
   FLAG PILL — suitability / applicability code badges
   ========================================================== */
export function FlagPill({ text }: { text: string }) {
  return (
    <span className="inline-flex items-center rounded-full px-3 py-1 text-[10px] font-black tracking-widest uppercase bg-white/8 border border-white/15 text-white/70">
      {text}
    </span>
  );
}

/* ==========================================================
   SCORE BAR — visual progress bar with category label
   ========================================================== */
export function ScoreBar({
  score,
  category,
}: {
  score?:    number;
  category?: string;
}) {
  const normalized = Math.max(0, Math.min(100, score ?? 0));

  const barColor =
    category === "Good"    ? "bg-emerald-500" :
    category === "Caution" ? "bg-amber-500"   :
    category === "Poor"    ? "bg-rose-500"     :
                             "bg-white/20";

  const labelColor =
    category === "Good"    ? "text-emerald-400 border-emerald-500/25 bg-emerald-500/10" :
    category === "Caution" ? "text-amber-400   border-amber-500/25   bg-amber-500/10"   :
    category === "Poor"    ? "text-rose-400    border-rose-500/25    bg-rose-500/10"     :
                             "text-white/40    border-white/15       bg-white/5";

  return (
    <div className="flex items-center gap-4">
      {/* Track */}
      <div className="h-2 flex-1 max-w-[12rem] rounded-full bg-white/8 overflow-hidden">
        <div
          className={cn("h-2 rounded-full transition-all duration-700", barColor)}
          style={{ width: `${normalized}%` }}
        />
      </div>

      {/* Numeric */}
      <span className="text-sm font-black text-white tabular-nums">
        {fmtInt(score)}<span className="text-white/30 font-medium"> / 100</span>
      </span>

      {/* Category badge */}
      {category && (
        <span className={cn(
          "px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest border",
          labelColor,
        )}>
          {category}
        </span>
      )}
    </div>
  );
}

/* ==========================================================
   DIAGNOSTICS LIST — expandable flag cards
   ========================================================== */
export function DiagnosticsList({ items }: { items?: DiagnosticFlag[] }) {
  if (!items || items.length === 0) {
    return (
      <p className="text-sm text-white/30 italic">No diagnostics available.</p>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((d, i) => {
        const tone =
          d.severity === "critical" || d.severity === "high"
            ? "border-rose-500/25   bg-rose-500/8"   :
          d.severity === "medium"
            ? "border-amber-500/25  bg-amber-500/8"  :
          d.severity === "low"
            ? "border-sky-500/25    bg-sky-500/8"    :
              "border-white/10      bg-white/5";

        const severityColor =
          d.severity === "critical" || d.severity === "high" ? "text-rose-400"   :
          d.severity === "medium"                            ? "text-amber-400"  :
          d.severity === "low"                               ? "text-sky-400"    :
                                                               "text-white/40";

        return (
          <div
            key={`${d.code}-${i}`}
            className={cn(
              "glass-card rounded-2xl border p-5 transition-all",
              tone,
            )}
          >
            {/* Header row */}
            <div className="flex items-center gap-3 mb-3">
              <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-[10px] font-black tracking-widest text-white">
                {d.code}
              </span>
              <span className={cn("text-[9px] font-black uppercase tracking-widest", severityColor)}>
                {d.severity}
              </span>
            </div>

            {/* Message */}
            <p className="text-sm leading-relaxed text-white/70">{d.message}</p>

            {/* Evidence block */}
            {d.evidence && (
              <div className="mt-3 rounded-xl bg-black/40 border border-white/5 p-3 overflow-x-auto">
                <pre className="text-[11px] text-indigo-300/80 font-mono leading-relaxed">
                  {JSON.stringify(d.evidence, null, 2)}
                </pre>
              </div>
            )}

            {/* Recommendation */}
            {d.recommendation && (
              <div className="mt-3 flex items-start gap-2 text-xs text-white/50">
                <span className="text-amber-400 font-black flex-shrink-0">Action:</span>
                <span className="leading-relaxed">{d.recommendation}</span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

/* ==========================================================
   SECTION HEADER — consistent card header pattern
   ========================================================== */
export function SectionHeader({
  title,
  subtitle,
  action,
}: {
  title:     string;
  subtitle?: string;
  action?:   React.ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h3 className="text-lg font-black text-white tracking-tight">{title}</h3>
        {subtitle && (
          <p className="text-xs text-white/35 mt-1">{subtitle}</p>
        )}
      </div>
      {action && <div className="flex-shrink-0">{action}</div>}
    </div>
  );
}