"use client";
import { useRef, useState, useEffect } from "react";
import { cn } from "@/lib/utils";

function fmt(v: number | null | undefined, unit: string): string {
  if (v == null) return "\u2014";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(1)}\u00d7`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  if (unit === "score") return v.toFixed(0);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

export function MetricRangeSlider({
  unit,
  positiveValues,
  naCount,
  totalCount,
  currentValue,
}: {
  unit: string;
  positiveValues: number[];
  naCount: number;
  totalCount: number;
  currentValue: number | null;
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

  if (positiveValues.length === 0) {
    if (naCount > 0) {
      return (
        <div className="mb-3 text-[11px] text-white/50 italic">
          All quarters have negative earnings — not meaningful
        </div>
      );
    }
    return null;
  }

  const min = Math.min(...positiveValues);
  const max = Math.max(...positiveValues);
  const avg = positiveValues.reduce((a, b) => a + b, 0) / positiveValues.length;
  const range = max - min || 1;

  const avgPos = ((avg - min) / range) * 100;

  let currentPos: number | null = null;
  let currentOutside = false;

  if (currentValue != null) {
    if (currentValue >= min && currentValue <= max) {
      currentPos = ((currentValue - min) / range) * 100;
    } else {
      currentOutside = true;
      currentPos = currentValue < min ? 0 : 100;
    }
  }

  const avgLabel = currentPos != null ? `avg ${fmt(avg, unit)}` : "";
  const curLabel = currentPos != null && !currentOutside ? `cur ${fmt(currentValue!, unit)}` : "";

  const CH = 6.5;
  const avgLabelW = avgLabel.length * CH;
  const curLabelW = curLabel.length * CH;

  const markersOverlap =
    trackWidth > 0 &&
    currentPos !== null &&
    !currentOutside &&
    Math.abs(avgPos - currentPos) * trackWidth / 100 < (avgLabelW + curLabelW) / 2 + 8;

  return (
    <div className="mb-3">
      <div className="flex items-center gap-1.5 text-[11px]">
        <span className="text-white/70 tabular-nums whitespace-nowrap">{fmt(min, unit)}</span>
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
                <div className="w-2 h-2 rotate-45 bg-white/95" />
              )}
            </div>
          )}
        </div>
        <span className="text-white/70 tabular-nums whitespace-nowrap">{fmt(max, unit)}</span>
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
              "absolute -translate-x-1/2 text-white/90 font-semibold transition-all duration-150",
              markersOverlap && "translate-y-[18px]",
            )}
            style={{ left: `${currentPos}%` }}
          >
            {curLabel}
          </span>
        )}
      </div>

      {currentOutside && currentValue != null && (
        <div className="text-[11px] text-rose-400 mt-0.5">
          cur {fmt(currentValue, unit)} ← outside positive range
        </div>
      )}
    </div>
  );
}
