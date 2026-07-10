"use client";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, TrendingUp, TrendingDown, Minus } from "lucide-react";
import type { GaugeConfig } from "../types/analysis.types";

const G = "#1D9E75";
const A = "#EF9F27";
const R = "#E24B4A";
const TRACK = "#B4B2A9";

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function valueToAngle(value: number, min: number, max: number): number {
  const range = Math.max(max - min, 1);
  const clamped = Math.max(min, Math.min(max, value));
  return 180 + ((clamped - min) / range) * 180;
}

function describeArc(cx: number, cy: number, r: number, fromAngle: number, toAngle: number): string {
  const start = polarToCartesian(cx, cy, r, fromAngle);
  const end = polarToCartesian(cx, cy, r, toAngle);
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${r} ${r} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
}

function fmt(v: number): string {
  return v.toFixed(1);
}

function getValuation(current: number, bandLow: number, bandHigh: number): { label: string; className: string } {
  if (current < bandLow) {
    return {
      label: "Undervalued",
      className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25",
    };
  }
  if (current > bandHigh) {
    return {
      label: "Overvalued",
      className: "bg-rose-500/15 text-rose-400 border-rose-500/25",
    };
  }
  return {
    label: "Fairly valued",
    className: "bg-amber-500/15 text-amber-400 border-amber-500/25",
  };
}

function fmtValue(v: number | null | undefined, unit: string): string {
  if (v == null) return "\u2014";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(1)}\u00d7`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  if (unit === "score") return v.toFixed(0);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

export { fmtValue };

function StatPill({ label, value, highlighted }: { label: string; value: string; highlighted: boolean }) {
  return (
    <div
      className={cn(
        "flex flex-col items-center px-3 py-1.5 rounded-lg min-w-[52px] transition-colors",
        highlighted
          ? "bg-white/[0.10] border border-white/20"
          : "bg-white/[0.04] border border-white/[0.08]",
      )}
    >
      <span className="text-[10px] text-white/40 font-medium uppercase tracking-wider leading-none mb-0.5">
        {label}
      </span>
      <span
        className={cn(
          "text-[13px] font-semibold tabular-nums leading-none",
          highlighted ? "text-white" : "text-white/70",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function GaugeSvg({
  current, min, max, avg, label, bandLow, bandHigh, compact, benchmark = "history",
  sectorP05, sectorP50, sectorP95,
}: {
  current: number; min: number; max: number; avg: number; label: string;
  bandLow: number; bandHigh: number; compact?: boolean; benchmark?: "history" | "sector";
  sectorP05?: number | null; sectorP50?: number | null; sectorP95?: number | null;
}) {
  // When benchmark=sector and sector stats are available, override gauge range
  const useSector = benchmark === "sector" && sectorP05 != null && sectorP50 != null && sectorP95 != null;
  const effMin = useSector ? Math.min(min, sectorP05!) : min;
  const effMax = useSector ? Math.max(max, sectorP95!) : max;
  const effAvg = useSector ? sectorP50! : avg;
  const effBandLow = useSector ? sectorP50! : bandLow;
  const effBandHigh = useSector ? Math.max(sectorP50! * 1.5, sectorP95!) : bandHigh;

  const r = compact ? 68 : 82;
  const cx = compact ? 125 : 130;
  const cy = compact ? 95 : 115;
  const viewW = compact ? 250 : 270;
  const viewH = compact ? 170 : 180;
  const range = Math.max(effMax - effMin, 1);

  const greenEndVal = Math.min(effAvg, effMax);
  const threshold = effAvg * 1.5;
  const amberEndVal = Math.min(threshold, effMax);
  const redStartVal = Math.max(threshold, effMin);

  const minAngle = valueToAngle(effMin, effMin, effMax);
  const maxAngle = valueToAngle(effMax, effMin, effMax);
  const greenEndAngle = valueToAngle(greenEndVal, effMin, effMax);
  const amberEndAngle = valueToAngle(amberEndVal, effMin, effMax);
  const redStartAngle = valueToAngle(redStartVal, effMin, effMax);
  const currentAngle = valueToAngle(current, effMin, effMax);

  const hasGreen = greenEndVal > effMin && range > 0;
  const hasAmber = amberEndVal > greenEndVal && range > 0;
  const hasRed = effMax > redStartVal && range > 0;

  const needleEnd = polarToCartesian(cx, cy, r, currentAngle);
  const heightVal = compact ? 170 : 180;

  const valuation = getValuation(current, effBandLow, effBandHigh);

  // ── Scale labels ──────────────────────────────────────────────────
  function tickEnds(v: number, inner = 10, outer = 3) {
    const a = Math.min(maxAngle, Math.max(minAngle, valueToAngle(v, effMin, effMax)));
    const pi = polarToCartesian(cx, cy, r - inner, a);
    const po = polarToCartesian(cx, cy, r - outer, a);
    return { x1: pi.x, y1: pi.y, x2: po.x, y2: po.y };
  }
  function valLabelPos(v: number, off = 18) {
    const a = Math.min(maxAngle, Math.max(minAngle, valueToAngle(v, effMin, effMax)));
    return polarToCartesian(cx, cy, r + off, a);
  }
  function zoneMid(a1: number, a2: number) {
    return (a1 + a2) / 2;
  }
  function zonePos(a: number) {
    return polarToCartesian(cx, cy, r - 28, a);
  }

  const minT = tickEnds(effMin);
  const avgT = tickEnds(greenEndVal);
  const thrT = tickEnds(amberEndVal);
  const maxT = tickEnds(effMax);
  const minLP = valLabelPos(effMin);
  const avgLP = valLabelPos(greenEndVal);
  const thrLP = valLabelPos(amberEndVal);
  const maxLP = valLabelPos(effMax);
  const greenZoneP = zonePos(zoneMid(minAngle, greenEndAngle));
  const amberZoneP = zonePos(zoneMid(greenEndAngle, amberEndAngle));
  const redZoneP = zonePos(zoneMid(amberEndAngle, maxAngle));

  return (
    <div className={compact ? "" : "mb-3"}>
      <div className="relative mx-auto" style={{ width: compact ? 250 : 270, height: heightVal }}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${viewW} ${viewH}`}
          aria-label={`${label} Gauge: ${fmt(current)}`}
        >
          <path
            d={describeArc(cx, cy, r, minAngle, maxAngle)}
            fill="none"
            stroke={TRACK}
            strokeWidth="10"
            strokeLinecap="butt"
          />

          {hasGreen && (
            <path
              d={describeArc(cx, cy, r, minAngle, greenEndAngle)}
              fill="none"
              stroke={G}
              strokeWidth="10"
              strokeLinecap="butt"
            />
          )}

          {hasAmber && (
            <path
              d={describeArc(cx, cy, r, greenEndAngle, amberEndAngle)}
              fill="none"
              stroke={A}
              strokeWidth="10"
              strokeLinecap="butt"
            />
          )}

          {hasRed && (
            <path
              d={describeArc(cx, cy, r, redStartAngle, maxAngle)}
              fill="none"
              stroke={R}
              strokeWidth="10"
              strokeLinecap="butt"
            />
          )}

          {/* Zone labels */}
          {hasGreen && (
            <text x={greenZoneP.x} y={greenZoneP.y} fill={G} fontSize="10" fontWeight="bold" textAnchor="middle" dominantBaseline="middle">Undervalued</text>
          )}
          {hasAmber && (
            <text x={amberZoneP.x} y={amberZoneP.y} fill={A} fontSize="10" fontWeight="bold" textAnchor="middle" dominantBaseline="middle">Fair</text>
          )}
          {hasRed && (
            <text x={redZoneP.x} y={redZoneP.y} fill={R} fontSize="10" fontWeight="bold" textAnchor="middle" dominantBaseline="middle">Overvalued</text>
          )}

          {/* Tick marks */}
          <line {...minT} stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
          <line {...avgT} stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
          <line {...thrT} stroke="rgba(255,255,255,0.4)" strokeWidth="2" />
          <line {...maxT} stroke="rgba(255,255,255,0.4)" strokeWidth="2" />

          {/* Value labels on scale */}
          <text x={minLP.x} y={minLP.y} fill="rgba(255,255,255,0.6)" fontSize="10" textAnchor="middle" dominantBaseline="middle">{fmt(min)}</text>
          <text x={avgLP.x} y={avgLP.y} fill="rgba(255,255,255,0.6)" fontSize="10" textAnchor="middle" dominantBaseline="middle">{fmt(greenEndVal)}</text>
          <text x={thrLP.x} y={thrLP.y} fill="rgba(255,255,255,0.6)" fontSize="10" textAnchor="middle" dominantBaseline="middle">{fmt(amberEndVal)}</text>
          <text x={maxLP.x} y={maxLP.y} fill="rgba(255,255,255,0.6)" fontSize="10" textAnchor="middle" dominantBaseline="middle">{fmt(max)}</text>

          <line
            x1={cx}
            y1={cy}
            x2={needleEnd.x}
            y2={needleEnd.y}
            stroke="white"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <circle cx={cx} cy={cy} r="3.5" fill="white" />
          <circle cx={needleEnd.x} cy={needleEnd.y} r="3.5" fill="white" />
        </svg>
      </div>

      <div className={cn("font-bold text-white/90 tracking-tight text-center", compact ? "text-2xl" : "text-[32px]")}>
        {fmt(current)}
      </div>

      {!compact && (
        <div className="flex items-center justify-center gap-2 mt-1">
          <StatPill label="Min" value={fmt(min)} highlighted={false} />
          <StatPill label="Avg" value={fmt(avg)} highlighted={false} />
          <StatPill label="Max" value={fmt(max)} highlighted={false} />
          <StatPill label="Current" value={fmt(current)} highlighted={true} />
        </div>
      )}

      <div className="flex justify-center mt-2">
        <span
          className={cn(
            "text-[11px] font-semibold uppercase tracking-wide px-3 py-0.5 rounded-full border",
            valuation.className,
            )}
          >
            {valuation.label}
        </span>
      </div>
    </div>
  );
}

function SliderTrack({
  unit, minVal, maxVal, avgVal, naCount, totalCount, currentValue, warnings,
}: {
  unit: string;
  minVal: number | null;
  maxVal: number | null;
  avgVal: number | null;
  naCount: number;
  totalCount: number;
  currentValue: number | null;
  warnings: string[];
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [trackWidth, setTrackWidth] = useState(0);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    const measure = () => setTrackWidth(el.offsetWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (minVal == null || maxVal == null || avgVal == null) {
    if (naCount > 0) {
      return (
        <div className="mb-3 text-[11px] text-white/50 italic">
          All quarters have negative earnings — not meaningful
        </div>
      );
    }
    if (warnings.length > 0) {
      return (
        <div className="mb-3 text-[11px] text-white/50 italic">{warnings[0]}</div>
      );
    }
    return null;
  }

  const range = maxVal - minVal || 1;
  const avgPos = ((avgVal - minVal) / range) * 100;

  let currentPos: number | null = null;
  let currentOutside = false;

  if (currentValue != null) {
    if (currentValue >= minVal && currentValue <= maxVal) {
      currentPos = ((currentValue - minVal) / range) * 100;
    } else {
      currentOutside = true;
      currentPos = currentValue < minVal ? 0 : 100;
    }
  }

  const avgLabel = currentPos != null ? `avg ${fmtValue(avgVal, unit)}` : "";
  const curLabel = currentPos != null && !currentOutside ? `cur ${fmtValue(currentValue!, unit)}` : "";

  const CH = 6.5;
  const avgLabelW = avgLabel.length * CH;
  const curLabelW = curLabel.length * CH;

  const markersOverlap =
    trackWidth > 0 &&
    currentPos !== null &&
    !currentOutside &&
    Math.abs(avgPos - currentPos) * trackWidth / 100 < (avgLabelW + curLabelW) / 2 + 8;

  const EDGE_PCT = 8;
  const nearLeftEdge = currentPos !== null && !currentOutside && currentPos < EDGE_PCT;
  const nearRightEdge = currentPos !== null && !currentOutside && currentPos > 100 - EDGE_PCT;

  return (
    <div className="mb-3">
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-white/70 tabular-nums whitespace-nowrap">{fmtValue(minVal, unit)}</span>
        <div ref={trackRef} className="relative flex-1 h-4 mx-1">
          <div className="absolute top-1/2 left-0 right-0 h-[3px] bg-white/30 -translate-y-1/2 rounded-full" />
          <div
            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 w-2 h-2 rounded-full bg-white/70"
            style={{ left: `${avgPos}%` }}
          />
          {currentPos !== null && (
            <div
              className={cn(
                "absolute top-1/2 -translate-x-1/2 -translate-y-1/2",
                currentOutside ? "z-20" : markersOverlap ? "z-20" : "z-10",
              )}
              style={{ left: `${currentPos}%` }}
            >
              {currentOutside ? (
                <span className="text-[11px] text-rose-400 leading-none">◄</span>
              ) : (
                <div className="relative flex items-center justify-center">
                  <div className="absolute w-5 h-5 rounded-full bg-blue-400/15 blur-[2px]" />
                  <div className="w-[14px] h-[14px] rotate-45 bg-blue-400 shadow-[0_0_10px_rgba(96,165,250,0.5)]" />
                </div>
              )}
            </div>
          )}
        </div>
        <span className="text-white/70 tabular-nums whitespace-nowrap">{fmtValue(maxVal, unit)}</span>
        {naCount > 0 && (
          <span className="text-rose-400/80 tabular-nums ml-1.5 whitespace-nowrap">
            {naCount}/{totalCount} N/A
          </span>
        )}
      </div>

      <div className="relative text-[10px] mt-0.5" style={{ height: markersOverlap ? "28px" : "16px" }}>
        <span
          className={cn(
            "absolute -translate-x-1/2 text-white/60 transition-all duration-150",
            markersOverlap && "translate-y-0.5",
          )}
          style={{ left: `${avgPos}%` }}
        >
          {avgLabel}
        </span>
        {currentPos !== null && !currentOutside && (
          <span
            className={cn(
              "absolute font-semibold transition-all duration-150 text-blue-400",
              nearLeftEdge
                ? "left-0 translate-x-0"
                : nearRightEdge
                  ? "right-0 left-auto translate-x-0"
                  : "-translate-x-1/2",
              markersOverlap && "translate-y-[18px]",
            )}
            style={{ left: nearLeftEdge || nearRightEdge ? undefined : `${currentPos}%` }}
          >
            {curLabel}
          </span>
        )}
      </div>

      {currentOutside && currentValue != null && (
        <div className="text-[11px] text-rose-400 mt-0.5">
          cur {fmtValue(currentValue, unit)} ← outside positive range
        </div>
      )}
    </div>
  );
}

export interface ValuationGaugeProps {
  config: GaugeConfig;
  unit: string;
  label: string;
  metricId: string;
  benchmark?: "history" | "sector";
}

export function ValuationGauge({ config, unit, label, benchmark = "history" }: ValuationGaugeProps) {
  if (config.display_mode === "disabled") {
    return (
      <div className="text-[11px] text-white/50 italic">
        {config.warnings[0] ?? "Not applicable for this instrument"}
      </div>
    );
  }

  if (config.display_mode === "gauge" || config.display_mode === "compact_gauge") {
    if (
      config.current_value == null ||
      config.min_value == null ||
      config.max_value == null ||
      config.avg_value == null ||
      config.band_low == null ||
      config.band_high == null
    ) {
      return (
        <div className="text-[11px] text-white/50 italic">Insufficient data for gauge display</div>
      );
    }

    return (
      <GaugeSvg
        current={config.current_value}
        min={config.min_value}
        max={config.max_value}
        avg={config.avg_value}
        label={label}
        bandLow={config.band_low}
        bandHigh={config.band_high}
        compact={config.display_mode === "compact_gauge"}
        benchmark={benchmark}
        sectorP05={config.sector_p05}
        sectorP50={config.sector_p50}
        sectorP95={config.sector_p95}
      />
    );
  }

  return (
    <SliderTrack
      unit={unit}
      minVal={config.min_value}
      maxVal={config.max_value}
      avgVal={config.avg_value}
      naCount={config.na_count}
      totalCount={config.total_quarters}
      currentValue={config.current_value}
      warnings={config.warnings}
    />
  );
}

// ── MiniGauge: compact arc gauge matching Design 4 reference ────────────────

function MiniGauge({ current, min, max, bandLow, bandHigh, percentile, mode }: {
  current: number; min: number; max: number;
  bandLow: number; bandHigh: number; percentile?: number;
  mode: "history" | "sector";
}) {
  const cx = 70;
  const cy = 65;
  const r = 50;
  const sweep = 180;
  const startAngle = 180;
  const endAngle = 360;

  const [pct, leftLabel, rightLabel] = mode === "history"
    ? [
        percentile != null
          ? Math.max(0, Math.min(100, percentile)) / 100
          : max > min
            ? Math.max(0, Math.min(1, (current - min) / (max - min)))
            : 0.5,
        fmt(min),
        fmt(max),
      ]
    : [
        bandHigh > bandLow
          ? Math.max(0, Math.min(1, (current - bandLow) / (bandHigh - bandLow)))
          : 0.5,
        fmt(bandLow),
        fmt(bandHigh),
      ];

  const valueAngle = startAngle + pct * sweep;
  const needleEnd = polarToCartesian(cx, cy, r, valueAngle);
  const gradId = `gaugeGrad_${mode}_${current}`.replace(/[^a-zA-Z0-9_]/g, "_");
  const arcLen = Math.PI * r * (sweep / 180);
  const offset = arcLen * (1 - pct);

  const valColor = mode === "history"
    ? percentile != null
      ? percentile >= 66 ? "#ff6565" : percentile >= 33 ? "#ffc700" : "#00c875"
      : "#ffc700"
    : current < bandLow ? "#00c875" : current > bandHigh ? "#ff6565" : "#ffc700";

  return (
    <svg className="w-[140px] h-[90px] mx-auto" viewBox="0 0 140 90" aria-label={`Gauge: ${fmt(current)}`}>
      <defs>
        <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="#00c875" />
          <stop offset="50%" stopColor="#ffc700" />
          <stop offset="100%" stopColor="#ff6565" />
        </linearGradient>
      </defs>
      <path
        d={describeArc(cx, cy, r, startAngle, endAngle)}
        fill="none"
        stroke="#2f3336"
        strokeWidth="10"
        strokeLinecap="round"
      />
      <path
        d={describeArc(cx, cy, r, startAngle, endAngle)}
        fill="none"
        stroke={`url(#${gradId})`}
        strokeWidth="10"
        strokeLinecap="round"
        strokeDasharray={arcLen}
        strokeDashoffset={offset}
        style={{ transition: "stroke-dashoffset 0.6s cubic-bezier(0.4,0,0.2,1)" }}
      />
      <text x="20" y="83" textAnchor="middle" fill="rgba(255,255,255,0.55)" fontSize="10" fontWeight="700" fontFamily="inherit" letterSpacing="-0.3">
        {leftLabel}
      </text>
      <text x="120" y="83" textAnchor="middle" fill="rgba(255,255,255,0.55)" fontSize="10" fontWeight="700" fontFamily="inherit" letterSpacing="-0.3">
        {rightLabel}
      </text>
      <circle cx={needleEnd.x} cy={needleEnd.y} r="6" fill={valColor} />
      <line x1={needleEnd.x} y1={needleEnd.y} x2={cx} y2={cy + 5} stroke={valColor} strokeWidth="2" />
    </svg>
  );
}

// ── MiniSparkline: centered full-width sparkline matching Design 4 reference ─

function MiniSparkline({ values, firstYear, delta, unit, invertDeltaColor }: {
  values?: number[]; firstYear?: string; delta?: number | null; unit: string; invertDeltaColor?: boolean;
}) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const last = values[values.length - 1];
  const first = values[0];
  const color = last >= first ? "#00c875" : "#ff6565";

  const points = values.map((v, i) => {
    const x = (i / (values.length - 1)) * 100;
    const y = 100 - ((v - min) / range) * 76 - 12;
    return { x: x.toFixed(1), y: y.toFixed(1) };
  });
  const ptsStr = points.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPts = `0,100 ${ptsStr} 100,100`;
  const gradId = `sg_${Math.random().toString(36).slice(2, 8)}`;

  return (
    <div className="mt-4 pt-4 border-t border-[#2f3336]">
      <svg className="w-full h-[52px]" viewBox="0 0 100 100" preserveAspectRatio="none">
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor={color} stopOpacity="0.25" />
            <stop offset="60%" stopColor={color} stopOpacity="0.08" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points={areaPts} fill={`url(#${gradId})`} />
        <polyline points={ptsStr} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="1.5" fill={color} opacity={i === points.length - 1 ? 1 : 0.35} />
        ))}
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="4" fill={color} stroke="#1c2023" strokeWidth="2" />
      </svg>
      <div className="flex justify-between mt-1.5 text-[10px] text-[#71767b]">
        <span className="font-medium">{firstYear ?? ""}</span>
        {delta != null && (
          <span className={cn("font-semibold flex items-center gap-0.5", (invertDeltaColor ? delta < 0 : delta >= 0) ? "text-[#ff6565]" : "text-[#00c875]")}>
            <span className="text-[11px] leading-none">{delta >= 0 ? "▲" : "▼"}</span>
            <span>{Math.abs(delta).toFixed(0)}% vs avg</span>
          </span>
        )}
        <span className="font-semibold text-white/70">Now</span>
      </div>
    </div>
  );
}

// ── HistoryTable: rich table matching Design 6 reference ─────────────────────

function HistoryTable({
  quarters,
  unit,
  avgValue,
  vsAvgDelta,
}: {
  quarters: { label: string; value: number | null; status?: string }[];
  unit: string;
  avgValue: number | null;
  vsAvgDelta?: number | null;
}) {
  const [open, setOpen] = useState(false);
  const reversed = [...quarters].reverse();
  const allValues = quarters
    .filter((q) => q.status === "normal" && q.value != null)
    .map((q) => q.value as number);
  if (allValues.length === 0) return null;

  const qMin = Math.min(...allValues);
  const qMax = Math.max(...allValues);

  function pctile(v: number): number {
    const below = allValues.filter((x) => x <= v).length;
    return Math.round((below / allValues.length) * 100);
  }

  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors"
      >
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
        History ({allValues.length} quarters)
      </button>
      {open && (
        <div className="mt-2 max-h-[260px] overflow-y-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[#71767b] border-b border-[#2f3336]">
                <th className="text-left py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">Quarter</th>
                <th className="text-right py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">Value</th>
                <th className="text-right py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">Change</th>
                <th className="text-right py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">vs Avg</th>
                <th className="text-right py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">%ile</th>
                <th className="text-left py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">Notes</th>
              </tr>
            </thead>
            <tbody>
              {reversed.map((q, i) => {
                const next = i < reversed.length - 1 ? reversed[i + 1] : null;
                const nextVal = next?.status === "normal" ? next.value : null;
                const change = (q.value != null && nextVal != null) ? ((q.value - nextVal) / nextVal) * 100 : null;
                const isNa = !q.value || q.status === "not_applicable";
                const isFirst = i === 0;
                const isOutlier = q.value != null && (q.value === qMax || q.value === qMin);
                const v = q.value;

                return (
                  <tr
                    key={i}
                    className={cn(
                      "border-b border-[rgba(47,51,54,0.4)]",
                      isFirst && "bg-[rgba(29,155,240,0.08)]",
                      isOutlier && v === qMax && "bg-[rgba(255,101,101,0.06)]",
                      isOutlier && v === qMin && "bg-[rgba(0,200,117,0.06)]",
                    )}
                  >
                    <td className="py-1.5 px-2 text-white/60">{q.label}</td>
                    <td className={cn(
                      "py-1.5 px-2 text-right tabular-nums font-semibold",
                      isNa ? "text-[#71767b] italic" : isFirst ? "text-[#00c875]" : "text-white/80",
                    )}>
                      {isNa ? "N/A" : fmtValue(v, unit)}
                    </td>
                    <td className="py-1.5 px-2 text-right tabular-nums">
                      {change != null ? (
                        <span className={cn(
                          "inline-flex items-center gap-0.5",
                          change > 0 ? "text-[#ff6565]" : change < 0 ? "text-[#00c875]" : "text-[#71767b]",
                        )}>
                          {change > 0 ? <TrendingUp size={10} /> : change < 0 ? <TrendingDown size={10} /> : <Minus size={10} />}
                          {Math.abs(change).toFixed(0)}%
                        </span>
                      ) : (
                        <span className="text-[#71767b]">—</span>
                      )}
                    </td>
                    <td className={cn(
                      "py-1.5 px-2 text-right tabular-nums",
                      !isNa && avgValue != null && v != null
                        ? v > avgValue ? "text-[#ff6565]" : "text-[#00c875]"
                        : "text-[#71767b]",
                    )}>
                      {!isNa && avgValue != null && v != null
                        ? `${v > avgValue ? "+" : ""}${((v - avgValue) / avgValue * 100).toFixed(0)}%`
                        : "—"}
                    </td>
                    <td className="py-1.5 px-2 text-right tabular-nums text-white/60">
                      {!isNa && v != null ? `${pctile(v)}th` : "—"}
                    </td>
                    <td className="py-1.5 px-2 text-[10px]">
                      {isFirst ? (
                        <span className="font-semibold text-white/70">Current</span>
                      ) : isNa && q.status === "not_applicable" ? (
                        <span className="text-[#71767b] italic">Net loss</span>
                      ) : isOutlier && v === qMax ? (
                        <span className="text-[#ff6565] font-semibold">Outlier</span>
                      ) : isOutlier && v === qMin ? (
                        <span className="text-[#00c875] font-semibold">Near 5Y low</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ── MetricCard: gauge card matching Design 4 reference ───────────────────────

export function MetricCard({
  config, unit, label, metricId, quarters, benchmark = "history",
}: {
  config: GaugeConfig;
  unit: string;
  label: string;
  metricId: string;
  quarters: { label: string; value: number | null; status?: string }[];
  benchmark?: "history" | "sector";
}) {
  const firstYear = quarters.length > 0 ? quarters[0].label.split(" ")[0] : undefined;

  if (config.display_mode === "disabled") {
    return (
      <div className="flex-1 min-w-[280px] bg-[#1c2023] border border-[#2f3336] rounded-xl p-5 text-center">
        <div className="text-[11px] text-white/50 italic">{config.warnings[0] ?? "Not applicable"}</div>
      </div>
    );
  }

  return (
    <div className="flex-1 min-w-[280px] bg-[#1c2023] border border-[#2f3336] rounded-xl p-5 text-center">
      <div className="flex items-center justify-center gap-2 mb-3">
        <span className="text-[13px] text-white/80 font-bold uppercase tracking-wider">{label}</span>
        <span className={cn(
          "text-[8px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded",
          benchmark === "history" ? "bg-white/5 text-white/30" : "bg-[rgba(29,155,240,0.15)] text-[#1d9bf0]",
        )}>
          {benchmark === "history" ? "HIST" : "SCTR"}
        </span>
      </div>

      <ValuationGauge config={config} unit={unit} label={label} metricId={metricId} benchmark={benchmark} />

      {benchmark === "history" && config.percentile != null && (
        <div className="mt-3 flex items-center justify-center gap-2">
          <span className={cn(
            "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold",
            config.percentile >= 66 ? "bg-[rgba(255,101,101,0.15)] text-[#ff6565]" :
            config.percentile >= 33 ? "bg-[rgba(255,199,0,0.15)] text-[#ffc700]" :
                                      "bg-[rgba(0,200,117,0.15)] text-[#00c875]",
          )}>
            <span className="w-2 h-2 rounded-full" style={{ background: "currentColor" }} />
            {Math.round(config.percentile)}th percentile
          </span>
        </div>
      )}

      <MiniSparkline
        values={config.sparkline_values}
        firstYear={firstYear}
        delta={config.vs_avg_delta}
        unit={unit}
      />

      <HistoryTable
        quarters={quarters}
        unit={unit}
        avgValue={config.historical_avg ?? config.avg_value}
        vsAvgDelta={config.vs_avg_delta}
      />
    </div>
  );
}


// ── Health-score gauge helpers ──────────────────────────────────────────────

export function getHealthLevel(value: number, metricId: string): {
  label: string; color: string; className: string;
} {
  if (metricId === "piotroski_f") {
    if (value >= 8) return { label: "Strong", color: "#00c875", className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" };
    if (value >= 4) return { label: "Fair", color: "#ffc700", className: "bg-amber-500/15 text-amber-400 border-amber-500/25" };
    return { label: "Weak", color: "#ff6565", className: "bg-rose-500/15 text-rose-400 border-rose-500/25" };
  }
  if (metricId === "altman_z") {
    if (value >= 2.99) return { label: "Safe", color: "#00c875", className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" };
    if (value >= 1.81) return { label: "Grey", color: "#ffc700", className: "bg-amber-500/15 text-amber-400 border-amber-500/25" };
    return { label: "Distress", color: "#ff6565", className: "bg-rose-500/15 text-rose-400 border-rose-500/25" };
  }
  if (metricId === "interest_coverage") {
    if (value >= 5) return { label: "Strong", color: "#00c875", className: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" };
    if (value >= 1.5) return { label: "Adequate", color: "#ffc700", className: "bg-amber-500/15 text-amber-400 border-amber-500/25" };
    return { label: "Weak", color: "#ff6565", className: "bg-rose-500/15 text-rose-400 border-rose-500/25" };
  }
  return { label: "Unknown", color: "#71767b", className: "bg-white/5 text-white/30" };
}

export function getHealthDescription(metricId: string): string {
  if (metricId === "piotroski_f") return "Score range: 0 (weak) → 9 (strong). ≥8 strong, ≤3 erosion.";
  if (metricId === "altman_z") return "Safe ≥ 2.99 · Grey 1.81–2.99 · Distress < 1.81";
  if (metricId === "interest_coverage") return "Strong ≥ 5.0 · Adequate 1.5–5.0 · Weak < 1.5";
  return "";
}

// ── HealthArc: a 180-degree semicircle with green/amber/red zones ──────────
// High values = green (strong), low values = red (weak) — opposite of MiniGauge.
// Shows tick marks and value labels at min, bandLow, bandHigh, and max.

function HealthArc({ current, min, max, bandLow, bandHigh, metricId }: {
  current: number; min: number; max: number; bandLow: number; bandHigh: number; metricId: string;
}) {
  const cx = 110, cy = 115, r = 75;
  const viewW = 220, viewH = 170;
  const range = Math.max(max - min, 1);
  const startAngle = 180;

  function valToAngle(v: number): number {
    return startAngle + ((v - min) / range) * 180;
  }

  const rawMaxAngle = Math.max(startAngle, valToAngle(max));
  const maxAngle = Math.min(rawMaxAngle, 360);
  const redEndAngle = Math.min(maxAngle, Math.max(startAngle, valToAngle(bandLow)));
  const amberEndAngle = Math.min(maxAngle, Math.max(startAngle, valToAngle(bandHigh)));
  const currentAngle = Math.min(maxAngle, Math.max(startAngle, valToAngle(current)));

  const needleEnd = polarToCartesian(cx, cy, r, currentAngle);

  function labelPos(v: number, off = 20) {
    const a = Math.min(maxAngle, Math.max(startAngle, valToAngle(v)));
    return polarToCartesian(cx, cy, r + off, a);
  }
  function tickEnds(v: number, inner = 10, outer = 3) {
    const a = Math.min(maxAngle, Math.max(startAngle, valToAngle(v)));
    const pi = polarToCartesian(cx, cy, r - inner, a);
    const po = polarToCartesian(cx, cy, r - outer, a);
    return { x1: pi.x, y1: pi.y, x2: po.x, y2: po.y };
  }
  function zoneLabelPos(a: number) {
    return polarToCartesian(cx, cy, r - 28, a);
  }

  const midRed = (startAngle + redEndAngle) / 2;
  const midAmber = (redEndAngle + amberEndAngle) / 2;
  const midGreen = (amberEndAngle + maxAngle) / 2;
  const redZonePos = zoneLabelPos(midRed);
  const amberZonePos = zoneLabelPos(midAmber);
  const greenZonePos = zoneLabelPos(midGreen);

  const minP = labelPos(min), maxP = labelPos(max);
  const lowP = labelPos(bandLow), highP = labelPos(bandHigh);
  const minT = tickEnds(min), maxT = tickEnds(max);
  const lowT = tickEnds(bandLow), highT = tickEnds(bandHigh);

  const zoneLabel = (z: "red" | "amber" | "green"): string => {
    if (metricId === "altman_z") {
      if (z === "red") return "Distress";
      if (z === "amber") return "Grey";
      return "Safe";
    }
    if (metricId === "piotroski_f") {
      if (z === "red") return "Weak";
      if (z === "amber") return "Fair";
      return "Strong";
    }
    if (z === "red") return "Weak";
    if (z === "amber") return "Adequate";
    return "Strong";
  };

  return (
    <svg className="w-[220px] h-[170px] mx-auto" viewBox={`0 0 ${viewW} ${viewH}`}>
      <path d={describeArc(cx, cy, r, startAngle, maxAngle)} fill="none" stroke="#2f3336" strokeWidth="14" strokeLinecap="round" />
      {bandLow > min && (
        <path d={describeArc(cx, cy, r, startAngle, redEndAngle)} fill="none" stroke="#ff6565" strokeWidth="14" strokeLinecap="round" />
      )}
      {bandHigh > bandLow && (
        <path d={describeArc(cx, cy, r, redEndAngle, amberEndAngle)} fill="none" stroke="#ffc700" strokeWidth="14" strokeLinecap="round" />
      )}
      {max > bandHigh && (
        <path d={describeArc(cx, cy, r, amberEndAngle, maxAngle)} fill="none" stroke="#00c875" strokeWidth="14" strokeLinecap="round" />
      )}
      {/* Zone labels */}
      {bandLow > min && (
        <text x={redZonePos.x} y={redZonePos.y} fill="#ff6565" fontSize="11" fontWeight="bold" textAnchor="middle" dominantBaseline="middle">{zoneLabel("red")}</text>
      )}
      {bandHigh > bandLow && (
        <text x={amberZonePos.x} y={amberZonePos.y} fill="#ffc700" fontSize="11" fontWeight="bold" textAnchor="middle" dominantBaseline="middle">{zoneLabel("amber")}</text>
      )}
      {max > bandHigh && (
        <text x={greenZonePos.x} y={greenZonePos.y} fill="#00c875" fontSize="11" fontWeight="bold" textAnchor="middle" dominantBaseline="middle">{zoneLabel("green")}</text>
      )}
      <line {...minT} stroke="rgba(255,255,255,0.5)" strokeWidth="2" />
      <line {...lowT} stroke="rgba(255,255,255,0.5)" strokeWidth="2" />
      <line {...highT} stroke="rgba(255,255,255,0.5)" strokeWidth="2" />
      <line {...maxT} stroke="rgba(255,255,255,0.5)" strokeWidth="2" />
      <text x={minP.x} y={minP.y} fill="rgba(255,255,255,0.7)" fontSize="12" textAnchor="middle" dominantBaseline="middle">{min.toFixed(1)}</text>
      <text x={lowP.x} y={lowP.y} fill="rgba(255,255,255,0.7)" fontSize="12" textAnchor="middle" dominantBaseline="middle">{bandLow.toFixed(1)}</text>
      <text x={highP.x} y={highP.y} fill="rgba(255,255,255,0.7)" fontSize="12" textAnchor="middle" dominantBaseline="middle">{bandHigh.toFixed(1)}</text>
      <text x={maxP.x} y={maxP.y} fill="rgba(255,255,255,0.7)" fontSize="12" textAnchor="middle" dominantBaseline="middle">{max.toFixed(1)}</text>
      <circle cx={needleEnd.x} cy={needleEnd.y} r="7" fill="white" />
      <line x1={needleEnd.x} y1={needleEnd.y} x2={cx} y2={cy + 5} stroke="white" strokeWidth="2.5" />
    </svg>
  );
}


// ── MoatGaugeCard: gauge + current value + explanation + sparkline ──────────

export function MoatGaugeCard({
  config, unit, label, metricId, quarters,
}: {
  config: GaugeConfig;
  unit: string;
  label: string;
  metricId: string;
  quarters: { label: string; value: number | null; status?: string }[];
}) {
  const health = config.current_value != null
    ? getHealthLevel(config.current_value, metricId)
    : null;
  const description = getHealthDescription(metricId);
  const hasData = config.current_value != null && config.min_value != null;

  return (
    <div className="flex-1 min-w-[280px] bg-[#1c2023] border border-[#2f3336] rounded-xl p-5 text-center">
      <div className="flex items-center justify-center gap-2 mb-3">
        <span className="text-[13px] text-white/80 font-bold uppercase tracking-wider">{label}</span>
        {health && (
          <span className={cn("text-[11px] font-bold uppercase tracking-wider px-2 py-0.5 rounded", health.className)}>
            {health.label}
          </span>
        )}
      </div>

      {hasData ? (
        <>
          <HealthArc
            current={config.current_value!}
            min={config.min_value!}
            max={config.max_value!}
            bandLow={config.band_low ?? 0}
            bandHigh={config.band_high ?? 0}
            metricId={metricId}
          />

          <div className="text-[36px] font-bold text-white/90 mt-2 tracking-tight">
            {metricId === "altman_z" && config.current_value != null
              ? config.current_value.toFixed(2)
              : fmtValue(config.current_value, unit)}
          </div>

          {description && (
            <div className="mt-2 text-[10px] text-white/40 leading-relaxed max-w-[220px] mx-auto">
              {description}
            </div>
          )}

          <MiniSparkline
            values={config.sparkline_values}
            firstYear={quarters.length > 0 ? quarters[0].label.split(" ")[0] : undefined}
            delta={config.vs_avg_delta}
            unit={unit}
            invertDeltaColor
          />
        </>
      ) : (
        <div className="text-[11px] text-white/50 italic py-8">No data available</div>
      )}
    </div>
  );
}


// ── MoatHistoryTable: yearly or quarterly comparison across all health metrics ─

export function MoatHistoryTable({
  metrics,
  frequency,
}: {
  metrics: { metricId: string; label: string; unit: string; quarters: { label: string; value: number | null }[] }[];
  frequency: "quarterly" | "annual";
}) {
  const [open, setOpen] = useState(false);

  // Collect unique columns across all metrics
  const allColumns = new Set<string>();
  const colValues: Record<string, Record<string, number | null>> = {};
  for (const m of metrics) {
    colValues[m.metricId] = {};
    for (const q of m.quarters) {
      const colKey = frequency === "annual"
        ? (q.label.split(" ").length >= 2 ? q.label.split(" ")[1] : q.label)
        : q.label;
      allColumns.add(colKey);
      // Keep the latest value for each column key (last quarter wins for annual)
      colValues[m.metricId][colKey] = q.value;
    }
  }
  const sortedCols = [...allColumns].sort();
  if (sortedCols.length === 0) return null;

  return (
    <div className="mt-4">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-[11px] text-white/40 hover:text-white/70 transition-colors"
      >
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
        History ({sortedCols.length} {frequency === "annual" ? "years" : "quarters"})
      </button>
      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-[#71767b] border-b border-[#2f3336]">
                <th className="text-left py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">Metric</th>
                {sortedCols.map((c) => (
                  <th key={c} className="text-right py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">{c}</th>
                ))}
                <th className="text-right py-1.5 px-2 font-semibold text-[10px] uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((m) => {
                const lastVal = sortedCols
                  .map((c) => colValues[m.metricId]?.[c])
                  .filter((v): v is number => v != null)
                  .pop();
                return (
                  <tr key={m.metricId} className="border-b border-[rgba(47,51,54,0.4)]">
                    <td className="py-1.5 px-2 text-white/60 font-semibold">{m.label}</td>
                    {sortedCols.map((c) => {
                      const v = colValues[m.metricId]?.[c];
                      const hl = v != null ? getHealthLevel(v, m.metricId) : null;
                      return (
                        <td
                          key={c}
                          className="py-1.5 px-2 text-right tabular-nums font-semibold"
                          style={hl ? { color: hl.color } : undefined}
                        >
                          {v != null ? (m.metricId === "altman_z" ? v.toFixed(2) : m.metricId === "interest_coverage" ? v.toFixed(1) : v.toFixed(0)) : "\u2014"}
                        </td>
                      );
                    })}
                    <td className="py-1.5 px-2 text-right">
                      {lastVal != null ? (
                        <span className={cn("text-[10px] font-semibold px-1.5 py-0.5 rounded", getHealthLevel(lastVal, m.metricId).className)}>
                          {getHealthLevel(lastVal, m.metricId).label}
                        </span>
                      ) : (
                        <span className="text-[10px] text-white/30 italic">No data</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
