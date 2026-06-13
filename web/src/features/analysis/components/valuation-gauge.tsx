"use client";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
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
  current, min, max, avg, label, bandLow, bandHigh, compact,
}: {
  current: number; min: number; max: number; avg: number; label: string;
  bandLow: number; bandHigh: number; compact?: boolean;
}) {
  const cx = 120;
  const cy = compact ? 90 : 112;
  const r = compact ? 68 : 86;
  const range = Math.max(max - min, 1);

  const threshold = avg * 1.5;
  const greenEndVal = Math.min(avg, max);
  const amberEndVal = Math.min(threshold, max);
  const redStartVal = Math.max(threshold, min);

  const minAngle = valueToAngle(min, min, max);
  const maxAngle = valueToAngle(max, min, max);
  const greenEndAngle = valueToAngle(greenEndVal, min, max);
  const amberEndAngle = valueToAngle(amberEndVal, min, max);
  const redStartAngle = valueToAngle(redStartVal, min, max);
  const currentAngle = valueToAngle(current, min, max);

  const hasGreen = greenEndVal > min && range > 0;
  const hasAmber = amberEndVal > greenEndVal && range > 0;
  const hasRed = max > redStartVal && range > 0;

  const needleEnd = polarToCartesian(cx, cy, r, currentAngle);
  const height = compact ? 120 : 150;
  const centerTextY = compact ? cy + 8 : cy + 12;
  const labelTextY = compact ? cy + 26 : cy + 34;
  const fontSize = compact ? 22 : 28;

  const valuation = getValuation(current, bandLow, bandHigh);

  return (
    <div className={compact ? "" : "mb-3"}>
      <div className="relative mx-auto" style={{ width: 240, height }}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 240 ${height}`}
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

          <text
            x={cx}
            y={centerTextY}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="white"
            fontSize={fontSize}
            fontWeight="900"
            fontFamily="inherit"
          >
            {fmt(current)}
          </text>
          <text
            x={cx}
            y={labelTextY}
            textAnchor="middle"
            dominantBaseline="middle"
            fill="rgba(255,255,255,0.4)"
            fontSize="10"
            fontWeight="700"
            fontFamily="inherit"
            letterSpacing="1.5"
          >
            {label}
          </text>
        </svg>
      </div>

      {!compact && (
        <>
          <div className="flex items-center justify-center gap-2 mt-1">
            <StatPill label="Min" value={fmt(min)} highlighted={false} />
            <StatPill label="Avg" value={fmt(avg)} highlighted={false} />
            <StatPill label="Max" value={fmt(max)} highlighted={false} />
            <StatPill label="Current" value={fmt(current)} highlighted={true} />
          </div>

          <div className="flex justify-center mt-2.5">
            <span
              className={cn(
                "text-[11px] font-semibold uppercase tracking-wide px-3 py-0.5 rounded-full border",
                valuation.className,
              )}
            >
              {valuation.label}
            </span>
          </div>
        </>
      )}

      {compact && (
        <div className="flex justify-center mt-1">
          <span
            className={cn(
              "text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border",
              valuation.className,
            )}
          >
            {valuation.label}
          </span>
        </div>
      )}
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
}

export function ValuationGauge({ config, unit, label }: ValuationGaugeProps) {
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
