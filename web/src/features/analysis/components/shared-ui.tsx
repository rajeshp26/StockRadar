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
   SCORE RING — circular SVG gauge with score + category
   NEW: replaces ScoreBar in summary cards
   ========================================================== */
export function ScoreRing({
  score,
  category,
  size = 120,
}: {
  score?:    number;
  category?: string;
  size?:     number;
}) {
  const normalized  = Math.max(0, Math.min(100, score ?? 0));
  const radius      = 46;
  const cx          = size / 2;
  const cy          = size / 2;
  const strokeW     = 8;
  // Arc spans 270° (from 135° to 45°, leaving a 90° gap at the bottom)
  const arcAngle    = 270;
  const circumference = 2 * Math.PI * radius;
  const arcLength   = (arcAngle / 360) * circumference;
  const filledLen   = (normalized / 100) * arcLength;
  // Rotation so gap is at the bottom: start at 135° from top
  const rotation    = 135;

  const trackColor  = "rgba(255,255,255,0.07)";
  const fillColor =
    category === "Good"    ? "#34d399" :  // emerald-400
    category === "Caution" ? "#fbbf24" :  // amber-400
    category === "Poor"    ? "#f87171" :  // rose-400
                             "rgba(99,102,241,0.8)"; // indigo fallback

  const glowColor =
    category === "Good"    ? "rgba(52,211,153,0.35)"  :
    category === "Caution" ? "rgba(251,191,36,0.35)"  :
    category === "Poor"    ? "rgba(248,113,113,0.35)" :
                             "rgba(99,102,241,0.35)";

  const labelColor =
    category === "Good"    ? "text-emerald-400" :
    category === "Caution" ? "text-amber-400"   :
    category === "Poor"    ? "text-rose-400"     :
                             "text-white/50";

  const categoryLabel =
    category === "Good"    ? "Good Suitability"    :
    category === "Caution" ? "Caution"             :
    category === "Poor"    ? "Poor Suitability"    :
                             "Evaluating…";

  return (
    <div className="flex flex-col items-center gap-3">
      {/* SVG ring */}
      <div className="relative" style={{ width: size, height: size }}>
        {/* Outer glow */}
        <div
          className="absolute inset-0 rounded-full blur-xl opacity-60 pointer-events-none"
          style={{ background: glowColor }}
          aria-hidden="true"
        />
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          aria-label={`Suitability score: ${score ?? 0} out of 100`}
        >
          {/* Background track */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={trackColor}
            strokeWidth={strokeW}
            strokeDasharray={`${arcLength} ${circumference}`}
            strokeDashoffset={0}
            strokeLinecap="round"
            transform={`rotate(${rotation} ${cx} ${cy})`}
          />
          {/* Filled arc */}
          <circle
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={fillColor}
            strokeWidth={strokeW}
            strokeDasharray={`${filledLen} ${circumference}`}
            strokeDashoffset={0}
            strokeLinecap="round"
            transform={`rotate(${rotation} ${cx} ${cy})`}
            style={{ transition: "stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)" }}
          />
          {/* Score number */}
          <text
            x={cx}
            y={cy - 6}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="white"
            fontSize={size * 0.22}
            fontWeight="900"
            fontFamily="inherit"
            letterSpacing="-1"
          >
            {score != null ? Math.round(score) : "—"}
          </text>
          {/* SCORE label */}
          <text
            x={cx}
            y={cy + size * 0.175}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="rgba(255,255,255,0.3)"
            fontSize={size * 0.09}
            fontWeight="700"
            fontFamily="inherit"
            letterSpacing="2"
          >
            SCORE
          </text>
        </svg>
      </div>

      {/* Category label */}
      <p className={cn("text-xs font-black uppercase tracking-widest text-center", labelColor)}>
        {categoryLabel}
      </p>
    </div>
  );
}

/* ==========================================================
   SCORE BAR — kept for any existing usage outside panels
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
      <div className="h-2 flex-1 max-w-[12rem] rounded-full bg-white/8 overflow-hidden">
        <div
          className={cn("h-2 rounded-full transition-all duration-700", barColor)}
          style={{ width: `${normalized}%` }}
        />
      </div>
      <span className="text-sm font-black text-white tabular-nums">
        {fmtInt(score)}<span className="text-white/30 font-medium"> / 100</span>
      </span>
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
          d.severity === "critical" || d.severity === "high" ? "text-rose-400"  :
          d.severity === "medium"                            ? "text-amber-400" :
          d.severity === "low"                               ? "text-sky-400"   :
                                                               "text-white/40";
        return (
          <div
            key={`${d.code}-${i}`}
            className={cn("glass-card rounded-2xl border p-5 transition-all", tone)}
          >
            <div className="flex items-center gap-3 mb-3">
              <span className="px-2.5 py-1 rounded-lg bg-white/10 border border-white/15 text-[10px] font-black tracking-widest text-white">
                {d.code}
              </span>
              <span className={cn("text-[9px] font-black uppercase tracking-widest", severityColor)}>
                {d.severity}
              </span>
            </div>
            <p className="text-sm leading-relaxed text-white/70">{d.message}</p>
            {d.evidence && (
              <div className="mt-3 rounded-xl bg-black/40 border border-white/5 p-3 overflow-x-auto">
                <pre className="text-[11px] text-indigo-300/80 font-mono leading-relaxed">
                  {JSON.stringify(d.evidence, null, 2)}
                </pre>
              </div>
            )}
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

/* ==========================================================
   SUITABILITY SIDEBAR — ring + flags + diagnostics toggle
   Used inside summary cards, right column
   ========================================================== */
export function SuitabilitySidebar({
  loading,
  score,
  category,
  flags,
  showDiagnostics,
  onToggleDiagnostics,
}: {
  loading:              boolean;
  score?:               number;
  category?:            string;
  flags?:               DiagnosticFlag[];
  showDiagnostics:      boolean;
  onToggleDiagnostics:  () => void;
}) {
  const flagCount  = flags?.length ?? 0;
  const topFlags   = flags?.slice(0, 3) ?? [];

  if (loading) {
    return (
      <div className="flex flex-col items-center gap-4 min-w-[160px]">
        <div className="h-[120px] w-[120px] rounded-full bg-white/5 glass-shimmer" />
        <div className="h-3 w-24 rounded-full bg-white/8 glass-shimmer" />
        <div className="h-2 w-36 rounded-full bg-white/5 glass-shimmer" />
        <div className="h-2 w-28 rounded-full bg-white/5 glass-shimmer" />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4 min-w-[160px] max-w-[200px]">
      {/* Circular score */}
      <ScoreRing score={score} category={category} size={120} />

      {/* Top flag pills */}
      {topFlags.length > 0 && (
        <div className="flex flex-wrap justify-center gap-1.5">
          {topFlags.map((f, i) => (
            <FlagPill key={`${f.code}-${i}`} text={f.code} />
          ))}
          {flagCount > 3 && (
            <span className="text-[10px] text-white/30 self-center">
              +{flagCount - 3} more
            </span>
          )}
        </div>
      )}

      {/* Diagnostics toggle */}
      {flagCount > 0 && (
        <button
          onClick={onToggleDiagnostics}
          className={cn(
            "w-full glass-btn px-3 py-2 rounded-xl",
            "text-[9px] font-black uppercase tracking-widest",
            "flex items-center justify-center gap-1.5",
            showDiagnostics && "bg-white/10 border-white/15",
          )}
        >
          <span>{showDiagnostics ? "Hide Details" : "Diagnostics"}</span>
          {!showDiagnostics && (
            <span className="px-1.5 py-0.5 rounded-md bg-white/10 text-white/60">
              {flagCount}
            </span>
          )}
        </button>
      )}
    </div>
  );
}