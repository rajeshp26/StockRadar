"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Info, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import { useFundamentals } from "../hooks/useFundamentals";
import { SectionHeader } from "./shared-ui";
import { MetricCard, ValuationGauge, MoatGaugeCard, MoatHistoryTable } from "./valuation-gauge";
import { IntrinsicValueCard, IntrinsicValueEmptyState } from "./intrinsic-value-card";
import type {
  FundamentalsResponse,
  MetricQuarterSeries,
  MetricComponent,
  QuarterDataPoint,
} from "../types/analysis.types";

function Shimmer({ className }: { className?: string }) {
  return <div className={cn("rounded-xl bg-white/5 glass-shimmer", className)} />;
}

function SectionError({ message }: { message: string }) {
  return (
    <div className="glass-panel p-6 text-center">
      <p className="text-xs text-rose-400/80">{message}</p>
    </div>
  );
}

// ── MetricBarChart (TradingView-style vertical bars) ─────────────────────────

function formatQuarterLabel(label: string): string {
  if (!label) return "";
  const parts = label.split(" ");
  if (parts.length >= 2) {
    const q = parts[0];
    const y = parts[1];
    return `${q}'${y.slice(2)}`;
  }
  // Annual labels are just the year
  return label;
}

type DisplayQuarter = {
  label: string;
  value: number | null;
  raw_value?: number | null;
  status?: "normal" | "not_applicable" | "insufficient_data";
  ttm_eps?: number | null;
  components?: MetricComponent[];
  quarter_end_price?: number | null;
};

const NM_THRESHOLD = 5000;

function MetricBarChart({
  metric,
  activeQuarters,
  activeIndices,
  buyQuarterIndex,
  filterNm,
  view,
}: {
  metric: MetricQuarterSeries;
  activeQuarters: DisplayQuarter[];
  activeIndices: number[];
  buyQuarterIndex: number | null;
  filterNm?: boolean;
  view?: "combo" | "absolute" | "yoy";
}) {
  const isCombo = view === "combo";
  const isAbs = view === "absolute";
  const isYoY = view !== "combo" && view !== "absolute";

  const hasRawValues = activeQuarters.some((q) => q.raw_value != null);

  const barValues = activeQuarters
    .map((q) => (isCombo || isAbs) && hasRawValues ? q.raw_value : q.value)
    .filter((v): v is number => v != null);

  const showLineAsPrimary = isYoY && hasRawValues;
  const showLineAsOverlay = isCombo && hasRawValues;
  const lineValues = (showLineAsPrimary || showLineAsOverlay)
    ? activeQuarters.map((q) => q.value).filter((v): v is number => v != null)
    : [];

  const hasAnyNonNormal = activeQuarters.some((q) => q.status && q.status !== "normal");
  const hasAnyQuarterData = activeQuarters.some((q) => q.ttm_eps != null || (q.components && q.components.length > 0));

  const isPctMetric = metric.unit === "%" && filterNm && isYoY;
  const nmValues = isPctMetric
    ? new Set(
        activeQuarters
          .map((q, i) => (q.value != null && Math.abs(q.value) > NM_THRESHOLD ? i : -1))
          .filter((i) => i >= 0),
      )
    : new Set<number>();

  const filteredBarValues = isPctMetric
    ? barValues.filter((v) => Math.abs(v) <= NM_THRESHOLD)
    : barValues;

  const allNoData = barValues.length === 0 && !hasAnyNonNormal && !hasAnyQuarterData;
  if (allNoData) {
    return (
      <div className="py-3">
        <span className="text-[13px] font-medium text-white/60">{metric.label}</span>
        <div className="mt-2 h-[120px] flex items-center justify-center">
          <span className="text-[11px] text-white/30 italic">No data</span>
        </div>
      </div>
    );
  }

  // ── Bar scale ──
  const rawMin = filteredBarValues.length > 0 ? Math.min(...filteredBarValues) : 0;
  const rawMax = filteredBarValues.length > 0 ? Math.max(...filteredBarValues) : 1;
  const hasNegative = rawMin < 0;
  const hasPositive = rawMax > 0;

  let clipMin = rawMin;
  let clipMax = rawMax;
  if (filteredBarValues.length >= 4) {
    const sorted = [...filteredBarValues].sort((a, b) => a - b);
    const q1 = sorted[Math.floor(sorted.length * 0.25)];
    const q3 = sorted[Math.floor(sorted.length * 0.75)];
    const iqr = q3 - q1;
    const lowerFence = q1 - 1.5 * iqr;
    const upperFence = q3 + 1.5 * iqr;
    if (lowerFence > rawMin) clipMin = lowerFence;
    if (upperFence < rawMax) clipMax = upperFence;
  }

  let yMin: number;
  let yMax: number;

  if (hasNegative && hasPositive) {
    const halfRange = Math.max(Math.abs(clipMin), Math.abs(clipMax)) || 1;
    yMin = -halfRange;
    yMax = halfRange;
  } else if (hasNegative) {
    yMin = clipMin * 1.2;
    yMax = 0;
  } else {
    yMin = 0;
    yMax = clipMax * 1.2 || 1;
  }

  const clippedAbove = new Set<number>();
  const clippedBelow = new Set<number>();
  if (isPctMetric) {
    for (let i = 0; i < activeQuarters.length; i++) {
      const v = activeQuarters[i].value;
      if (v != null) {
        if (v > yMax) clippedAbove.add(i);
        if (v < yMin) clippedBelow.add(i);
      }
    }
  }

  // ── Line scale (for combo mode or YoY % mode) ──
  let lineYMin = 0;
  let lineYMax = 1;
  let lineZeroY = 0;
  if ((isCombo || isYoY) && hasRawValues) {
    const lMin = lineValues.length > 0 ? Math.min(...lineValues) : 0;
    const lMax = lineValues.length > 0 ? Math.max(...lineValues) : 1;
    const lHasNeg = lMin < 0;
    const lHasPos = lMax > 0;
    if (lHasNeg && lHasPos) {
      const h = Math.max(Math.abs(lMin), Math.abs(lMax)) || 1;
      lineYMin = -h;
      lineYMax = h;
    } else if (lHasNeg) {
      lineYMin = lMin * 1.2;
      lineYMax = 0;
    } else {
      lineYMin = 0;
      lineYMax = lMax * 1.2 || 1;
    }
    lineZeroY = ((lineYMax - 0) / (lineYMax - lineYMin));
  }

  const chartHeight = 200;
  const padTop = 8;
  const padBottom = 8;
  const innerHeight = chartHeight - padTop - padBottom;
  const yRange = yMax - yMin || 1;
  const barZeroY = padTop + ((yMax - 0) / yRange) * innerHeight;
  const lineRange = lineYMax - lineYMin || 1;
  const lineZeroYPx = padTop + ((lineYMax - 0) / lineRange) * innerHeight;

  const gridLines = 4;
  const barGridSteps = Array.from({ length: gridLines }, (_, i) => {
    const val = yMin + (i / (gridLines - 1)) * yRange;
    const y = padTop + ((yMax - val) / yRange) * innerHeight;
    return { val, y };
  });

  const lineGridSteps = (showLineAsPrimary || showLineAsOverlay)
    ? Array.from({ length: gridLines }, (_, i) => {
        const val = lineYMin + (i / (gridLines - 1)) * lineRange;
        const y = padTop + ((lineYMax - val) / lineRange) * innerHeight;
        return { val, y };
      })
    : [];

  // ── SVG polyline for combo / YoY % modes ──
  let linePathD = "";
  let linePoints: { x: number; y: number; val: number }[] = [];
  if ((showLineAsPrimary || showLineAsOverlay) && lineValues.length > 0) {
    linePoints = activeQuarters
      .map((qp, i) => {
        const v = qp.value;
        if (v == null) return null;
        const x = i * 52 + 24;
        const y = padTop + ((lineYMax - v) / lineRange) * innerHeight;
        return { x, y, val: v };
      })
      .filter((p): p is NonNullable<typeof p> => p !== null);
    if (linePoints.length > 0) {
      linePathD = "M " + linePoints.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" L ");
    }
  }

  // ── Area fill path (fills from line DOWN to chart bottom) ──
  let areaPathD = "";
  if (linePoints.length >= 2) {
    const bottomY = chartHeight;
    const first = linePoints[0];
    const last = linePoints[linePoints.length - 1];
    areaPathD = `M ${first.x},${bottomY} ${linePoints.map((p) => `L ${p.x},${p.y}`).join(" ")} L ${last.x},${bottomY} Z`;
  }

  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrollState, setScrollState] = useState<"none" | "left" | "right" | "both">("none");
  const [hovering, setHovering] = useState(false);
  const [hoveredBar, setHoveredBar] = useState<{
    index: number;
    qp: DisplayQuarter;
  } | null>(null);

  const updateScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return setScrollState("none");
    const left = el.scrollLeft > 4;
    const right = el.scrollLeft + el.clientWidth < el.scrollWidth - 4;
    if (left && right) setScrollState("both");
    else if (left) setScrollState("left");
    else if (right) setScrollState("right");
    else setScrollState("none");
  }, []);

  const [scrollLeft, setScrollLeft] = useState(0);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    updateScroll();
    const onScroll = () => {
      updateScroll();
      setScrollLeft(el.scrollLeft);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    const ro = new ResizeObserver(updateScroll);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", onScroll);
      ro.disconnect();
    };
  }, [activeQuarters.length, updateScroll]);

  const scrollBy = (dir: "left" | "right") => {
    scrollRef.current?.scrollBy({ left: dir === "left" ? -156 : 156, behavior: "smooth" });
  };

  const showLeft = hovering && (scrollState === "left" || scrollState === "both");
  const showRight = hovering && (scrollState === "right" || scrollState === "both");

  const barUnit = showLineAsPrimary ? "%" : (isCombo || isAbs) && hasRawValues ? "$" : metric.unit;

  const totalWidth = activeQuarters.length * 52;

  return (
    <div>
      <div className="flex items-start">
        {/* Left Y-axis: bar scale (combo/abs) or line scale (YoY %) */}
        <div className="w-12 flex-shrink-0 relative overflow-hidden" style={{ height: chartHeight }}>
          <div className="absolute left-0 right-0 top-0 bottom-0 flex flex-col justify-between py-[8px]">
            {(showLineAsPrimary ? [...lineGridSteps] : [...barGridSteps]).reverse().map((g, i) => (
              <span key={i} className={cn(
                "text-[10px] tabular-nums text-right leading-none font-medium",
                showLineAsPrimary ? "text-purple-400/70" : "text-white/50",
              )}>
                {formatAxisValue(g.val, barUnit)}
              </span>
            ))}
          </div>
        </div>

        <div
          className="flex-1 min-w-0 relative"
          onMouseEnter={() => setHovering(true)}
          onMouseLeave={() => { setHovering(false); setHoveredBar(null); }}
        >
          <div ref={scrollRef} className="overflow-x-auto">
            <div className="inline-flex flex-col" style={{ minWidth: `${totalWidth}px` }}>
              <div className="relative" style={{ height: chartHeight }}>
                {/* Grid lines (bar scale or line scale) */}
                {(showLineAsPrimary ? lineGridSteps : barGridSteps).map((g, i) => (
                  <div
                    key={i}
                    className={cn(
                      "absolute left-0 right-0 border-t",
                      showLineAsPrimary ? "border-purple-500/10" : "border-white/8",
                    )}
                    style={{ top: `${(g.y / chartHeight) * 100}%` }}
                  />
                ))}

                {(showLineAsPrimary ? (lineYMin < 0 && lineYMax > 0) : (hasNegative && hasPositive)) && (
                  <div
                    className="absolute left-0 right-0 border-t border-white/30"
                    style={{ top: `${(showLineAsPrimary ? lineZeroYPx : barZeroY) / chartHeight * 100}%` }}
                  />
                )}

                {/* SVG overlay for combo / YoY % line */}
                {(showLineAsPrimary || showLineAsOverlay) && linePathD && (
                  <svg
                    className="absolute inset-0 pointer-events-none z-20"
                    width={totalWidth}
                    height={chartHeight}
                    viewBox={`0 0 ${totalWidth} ${chartHeight}`}
                  >
                    <defs>
                      <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#c084fc" stopOpacity="0.25" />
                        <stop offset="100%" stopColor="#c084fc" stopOpacity="0.02" />
                      </linearGradient>
                    </defs>
                    <path d={areaPathD} fill="url(#areaFill)" />
                    <path
                      d={linePathD}
                      fill="none"
                      stroke="#c084fc"
                      strokeWidth="2.5"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      className="drop-shadow-[0_0_6px_rgba(192,132,252,0.5)]"
                    />
                    {linePoints.map((p, i) => (
                      <circle
                        key={i}
                        cx={p.x}
                        cy={p.y}
                        r="3"
                        fill="#0a0e1a"
                        stroke="#c084fc"
                        strokeWidth="2"
                      />
                    ))}
                  </svg>
                )}

                {/* Bars (hidden in YoY % mode) */}
                {!showLineAsPrimary && (
                <div className="absolute left-0 right-0 top-0 bottom-0 flex items-end gap-1">
                  {activeQuarters.map((qp, i) => {
                    const qpStatus = qp.status ?? "normal";
                    const barV = (isCombo || isAbs) && hasRawValues ? (qp.raw_value ?? null) : qp.value;
                    const isNm = nmValues.has(i);
                    const effectiveValue = isNm ? null : barV;

                    if (barV == null && qpStatus === "normal" && !isNm) {
                      return (
                        <div key={i} className="w-12 flex-shrink-0 flex justify-center items-end h-full">
                          <div className="w-full h-px bg-white/5" />
                        </div>
                      );
                    }

                    const barHeight = effectiveValue != null
                      ? Math.abs(((effectiveValue - (hasNegative && !hasPositive ? yMin : 0)) / yRange) * innerHeight)
                      : 0;
                    const isBuy = buyQuarterIndex !== null && activeIndices[i] === buyQuarterIndex;
                    const barColor = effectiveValue != null && effectiveValue >= 0 ? "bg-emerald-500" : "bg-rose-500";

                    const isHollow = isNm || qpStatus === "not_applicable";
                    const isDashed = qpStatus === "insufficient_data";
                    const hasValue = effectiveValue !== null;

                    const isMixed = hasNegative && hasPositive;
                    const barPosStyle = isMixed && effectiveValue != null
                      ? effectiveValue >= 0
                        ? { bottom: `${chartHeight - barZeroY}px` }
                        : { top: `${barZeroY}px` }
                      : { bottom: 0 };

                    const isClippedAbove = clippedAbove.has(i);
                    const isClippedBelow = clippedBelow.has(i);

                    return (
                      <div
                        key={i}
                        data-testid={`bar-${i}`}
                        className="w-12 flex-shrink-0 relative"
                        style={{ height: chartHeight }}
                        onMouseEnter={() => setHoveredBar({ index: i, qp })}
                        onMouseLeave={() => setHoveredBar(null)}
                      >
                        {hasValue || isHollow || isDashed ? (
                          <div
                            className={cn(
                              "absolute left-0 w-full rounded-[3px] transition-all duration-200",
                              hasValue && "opacity-85 hover:opacity-100 hover:brightness-110",
                              isHollow && "border-[1.5px] opacity-70",
                              isDashed && "border-[1.5px] border-dashed opacity-50",
                              isHollow && barColor.replace("bg-", "border-"),
                              isDashed && barColor.replace("bg-", "border-"),
                              isHollow && barColor,
                              !isHollow && !isDashed && barColor,
                              isBuy && "ring-1 ring-blue-400",
                            )}
                            style={{ height: `${Math.max(barHeight, isHollow || isDashed ? 4 : 2)}px`, ...barPosStyle }}
                          />
                        ) : (
                          <div className="w-full h-px bg-white/5" />
                        )}
                        {isNm && (
                          <span className="absolute left-1/2 -translate-x-1/2 top-1/2 -translate-y-1/2 text-[8px] font-bold text-white/30 tracking-wider pointer-events-none">
                            NM
                          </span>
                        )}
                        {isClippedAbove && barV != null && (
                          <span className="absolute left-1/2 -translate-x-1/2 -top-3.5 text-[8px] font-bold text-rose-400/80 whitespace-nowrap pointer-events-none">
                            +{barV.toFixed(0)}%
                          </span>
                        )}
                        {isClippedBelow && barV != null && (
                          <span className="absolute left-1/2 -translate-x-1/2 -bottom-3.5 text-[8px] font-bold text-emerald-400/80 whitespace-nowrap pointer-events-none">
                            {barV.toFixed(0)}%
                          </span>
                        )}
                        {isBuy && (
                          <span className="absolute left-1/2 -translate-x-1/2 -bottom-3 text-[9px] text-blue-400 font-bold drop-shadow-lg pointer-events-none">
                            ▲
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
                )}
              </div>

              {/* X-axis labels */}
              <div className="flex gap-1 mt-1">
                {activeQuarters.map((qp, i) => (
                  <div key={i} className="w-12 flex-shrink-0 text-center">
                    <span className="text-[10px] text-white/50 tabular-nums leading-none font-medium">
                      {formatQuarterLabel(qp.label)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Left scroll fade */}
          <div
            className={cn(
              "absolute left-0 top-0 bottom-0 w-7 flex items-center justify-start pl-1 bg-gradient-to-r from-gray-900/70 to-transparent z-30 transition-opacity duration-200 pointer-events-none",
              showLeft ? "opacity-100" : "opacity-0",
            )}
          >
            <button
              onClick={() => scrollBy("left")}
              className="h-7 w-5 flex items-center justify-center rounded-r bg-white/10 hover:bg-white/20 backdrop-blur-sm pointer-events-auto transition-colors"
            >
              <ChevronLeft className="h-3.5 w-3.5 text-white/80" />
            </button>
          </div>
          <div
            className={cn(
              "absolute right-0 top-0 bottom-0 w-7 flex items-center justify-end pr-1 bg-gradient-to-l from-gray-900/70 to-transparent z-30 transition-opacity duration-200 pointer-events-none",
              showRight ? "opacity-100" : "opacity-0",
            )}
          >
            <button
              onClick={() => scrollBy("right")}
              className="h-7 w-5 flex items-center justify-center rounded-l bg-white/10 hover:bg-white/20 backdrop-blur-sm pointer-events-auto transition-colors"
            >
              <ChevronRight className="h-3.5 w-3.5 text-white/80" />
            </button>
          </div>
        </div>

        {/* Right Y-axis (line scale, combo mode only — hidden in YoY % mode) */}
        {showLineAsOverlay && (
          <div className="w-12 flex-shrink-0 relative overflow-hidden" style={{ height: chartHeight }}>
            <div className="absolute left-0 right-0 top-0 bottom-0 flex flex-col justify-between py-[8px]">
              {[...lineGridSteps].reverse().map((g, i) => (
                <span key={i} className="text-[10px] text-purple-400/70 tabular-nums text-left leading-none font-medium">
                  {g.val >= 0 ? "+" : ""}{g.val.toFixed(0)}%
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {hoveredBar && (
        <div
          className="pointer-events-none z-20"
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            overflow: "visible",
          }}
        >
          <div
            className="absolute bg-gray-900/90 backdrop-blur-lg px-2.5 py-1 rounded-md text-[11px] whitespace-nowrap shadow-lg border border-white/10"
            style={{
              left: Math.max(48, hoveredBar.index * 52 + 24 - scrollLeft),
              transform: "translateX(-50%)",
            }}
          >
              {(() => {
                const qp = hoveredBar.qp;
                const qpStatus = qp.status ?? "normal";
                const hasValue = qp.value !== null;
                const hasRaw = qp.raw_value != null;
                const showRaw = (isCombo || isAbs) && hasRaw;
                const availableComponents = qp.components?.filter((c) => c.value != null) ?? [];
                const missingComponents = qp.components?.filter((c) => c.value == null) ?? [];
                return (
                  <>
                    <div className="flex items-center gap-1.5">
                      <span className="text-white/80">{formatQuarterLabel(qp.label)}</span>
                      {showRaw ? (
                        <>
                          <span className={cn("font-semibold", qp.raw_value != null && qp.raw_value >= 0 ? "text-emerald-400" : "text-rose-400")}>
                            {qp.raw_value != null ? formatMetricValue(qp.raw_value, metric.unit === "%" ? "$" : metric.unit) : "—"}
                          </span>
                          <span className="text-white/20 text-[10px] mx-0.5">|</span>
                          <span className={cn("text-[11px]", qp.value != null && qp.value >= 0 ? "text-purple-400" : "text-purple-400")}>
                            {hasValue ? `${qp.value! >= 0 ? "+" : ""}${qp.value!.toFixed(1)}% YoY` : "—"}
                          </span>
                        </>
                      ) : (
                        <span className={cn("font-semibold", qp.value != null && qp.value >= 0 ? "text-emerald-400" : "text-rose-400")}>
                          {hasValue ? formatMetricValue(qp.value!, metric.unit) : "—"}
                        </span>
                      )}
                      {nmValues.has(hoveredBar.index) ? (
                        <span className="text-amber-400/70 text-[10px] font-medium">NM</span>
                      ) : qpStatus === "not_applicable" ? (
                        <span className="text-rose-400/70 text-[10px] font-medium">N/A</span>
                      ) : qpStatus === "insufficient_data" ? (
                        <span className="text-white/30 text-[10px] italic">insufficient data</span>
                      ) : null}
                    </div>
                    {qpStatus === "insufficient_data" && qp.components && qp.components.length > 0 && (
                    <div className="text-[10px] text-white/30 mt-0.5">
                      Only {availableComponents.length} of {qp.components.length} quarters on record
                    </div>
                  )}
                  {qpStatus === "insufficient_data" && missingComponents.length > 0 && (
                    <div className="text-[10px] text-white/20 mt-0.5">
                      Missing: {missingComponents.map((c) => c.label).join(", ")}
                    </div>
                  )}
                  {nmValues.has(hoveredBar.index) ? (
                    <div className="text-[10px] text-amber-400/60 mt-0.5">Prior period near zero — not meaningful</div>
                  ) : qpStatus === "not_applicable" ? (
                    <div className="text-[10px] text-rose-400/60 mt-0.5">Negative earnings</div>
                  ) : null}
                  {qp.components && qp.components.length > 0 && qp.ttm_eps != null && (
                    <div className="mt-1.5 pt-1.5 border-t border-white/10 space-y-0.5">
                      <div className="text-[10px] text-white/40">TTM EPS: <span className={cn("font-medium", qp.ttm_eps >= 0 ? "text-emerald-400" : "text-rose-400")}>{formatMetricValue(qp.ttm_eps, "x").replace("×", "")}</span></div>
                      {qp.components.map((c, ci) => (
                        <div key={ci} className="flex items-center gap-1 text-[10px]">
                          <span className="text-white/30">{c.label}:</span>
                          <span className={cn(
                            "tabular-nums",
                            c.value != null && c.value >= 0 ? "text-emerald-400" : "text-rose-400",
                            c.highlight === "driver" && "underline decoration-rose-500/60 decoration-dotted",
                          )}>
                            {c.value != null ? formatMetricValue(c.value, "x").replace("×", "") : "—"}
                          </span>
                          {c.highlight === "driver" && (
                            <span className="text-[9px] text-rose-400/60 ml-0.5">driver</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                  {qp.quarter_end_price != null && (
                    <div className="mt-1.5 pt-1.5 border-t border-white/10 text-[10px] text-white/30">
                      Quarter-end price: ${qp.quarter_end_price.toFixed(2)}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

function formatAxisValue(val: number, unit: string): string {
  if (unit === "%") return `${val >= 0 ? "+" : ""}${val.toFixed(0)}%`;
  if (unit === "x") return `${val.toFixed(1)}×`;
  if (unit === "$") {
    if (val === 0) return "$0";
    const abs = Math.abs(val);
    if (abs >= 1_000_000_000) return `${val >= 0 ? "+" : "-"}$${(abs / 1_000_000_000).toFixed(1)}B`;
    if (abs >= 1_000_000) return `${val >= 0 ? "+" : "-"}$${(abs / 1_000_000).toFixed(0)}M`;
    if (abs >= 1_000) return `${val >= 0 ? "+" : "-"}$${(abs / 1_000).toFixed(0)}K`;
    return `$${val.toFixed(2)}`;
  }
  if (unit === "score") return val.toFixed(0);
  return formatLargeValue(val, 1);
}

// ── StatusBadge ──────────────────────────────────────────────────────────────

function StatusBadge({ label }: { label: string }) {
  const color =
    label === "Intact"
      ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
      : label === "Watch"
        ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
        : "bg-rose-500/15 text-rose-400 border-rose-500/25";
  return (
    <span className={cn("text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border", color)}>
      {label}
    </span>
  );
}

// ── BenchmarkToggle ──────────────────────────────────────────────────────────

function BenchmarkToggle({
  value,
  onChange,
}: {
  value: "history" | "sector";
  onChange: (v: "history" | "sector") => void;
}) {
  return (
    <div className="flex items-center gap-1.5 bg-white/5 rounded-lg p-0.5 w-fit">
      <button
        onClick={() => onChange("history")}
        className={cn(
          "text-[10px] font-semibold px-2.5 py-1.5 rounded-md transition-colors",
          value === "history" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
        )}
      >
        vs History
      </button>
      <button
        onClick={() => onChange("sector")}
        className={cn(
          "text-[10px] font-semibold px-2.5 py-1.5 rounded-md transition-colors",
          value === "sector" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
        )}
      >
        vs Sector
      </button>
    </div>
  );
}

// ── FrequencyToggle ───────────────────────────────────────────────────────────

function FrequencyToggle({
  value,
  onChange,
}: {
  value: "quarterly" | "annual";
  onChange: (v: "quarterly" | "annual") => void;
}) {
  return (
    <div className="flex items-center gap-1.5 bg-white/5 rounded-lg p-0.5 w-fit">
      <button
        onClick={() => onChange("quarterly")}
        className={cn(
          "text-xs font-medium px-3 py-1.5 rounded-md transition-colors",
          value === "quarterly" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
        )}
      >
        Quarterly
      </button>
      <button
        onClick={() => onChange("annual")}
        className={cn(
          "text-xs font-medium px-3 py-1.5 rounded-md transition-colors",
          value === "annual" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
        )}
      >
        Annual
      </button>
    </div>
  );
}

// ── QuarterToggle ────────────────────────────────────────────────────────────

function QuarterToggle({
  value,
  onChange,
  showFromPurchase,
}: {
  value: "all" | "from_purchase";
  onChange: (v: "all" | "from_purchase") => void;
  showFromPurchase: boolean;
}) {
  return (
    <div className="flex items-center gap-1.5 bg-white/5 rounded-lg p-0.5 w-fit">
      <button
        onClick={() => onChange("all")}
        className={cn(
          "text-xs font-medium px-3 py-1.5 rounded-md transition-colors",
          value === "all" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
        )}
      >
        All
      </button>
      {showFromPurchase && (
        <button
          onClick={() => onChange("from_purchase")}
          className={cn(
            "text-xs font-medium px-3 py-1.5 rounded-md transition-colors",
            value === "from_purchase" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
          )}
        >
          From purchase
        </button>
      )}
    </div>
  );
}

function formatLargeValue(v: number, decimals: number = 1): string {
  const abs = Math.abs(v);
  if (abs === 0) return "0";
  if (abs >= 1_000_000_000_000) return `${(v / 1_000_000_000_000).toFixed(decimals)}T`;
  if (abs >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(decimals)}B`;
  if (abs >= 1_000_000) return `${(v / 1_000_000).toFixed(decimals)}M`;
  if (abs >= 1_000) return `${(v / 1_000).toFixed(decimals)}K`;
  return v.toFixed(decimals);
}

function formatMetricValue(v: number | null | undefined, unit: string): string {
  if (v == null) return "—";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(1)}×`;
  if (unit === "$") return `$${formatLargeValue(v)}`;
  if (unit === "score") return v.toFixed(0);
  if (unit === "$B") return `$${(v / 1_000_000_000).toFixed(1)}B`;
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

// ── Annual data grouping helper ──────────────────────────────────────────────

function groupQuartersByYear(
  quarters: QuarterDataPoint[],
): DisplayQuarter[] {
  const byYear = new Map<number, { label: string; value: number | null; raw_value?: number | null; maxQ: number; status?: "normal" | "not_applicable" | "insufficient_data"; ttm_eps?: number | null; components?: MetricComponent[]; quarter_end_price?: number | null }>();
  for (const q of quarters) {
    const existing = byYear.get(q.fiscal_year);
    if (!existing || q.fiscal_quarter > existing.maxQ) {
      byYear.set(q.fiscal_year, { label: String(q.fiscal_year), value: q.value, raw_value: q.raw_value, maxQ: q.fiscal_quarter, status: q.status, ttm_eps: q.ttm_eps, components: q.components, quarter_end_price: q.quarter_end_price });
    }
  }
  return Array.from(byYear.entries())
    .sort(([a], [b]) => a - b)
    .map(([, v]) => ({ label: v.label, value: v.value, raw_value: v.raw_value, status: v.status, ttm_eps: v.ttm_eps, components: v.components, quarter_end_price: v.quarter_end_price }));
}

// ── MetricChartSection ───────────────────────────────────────────────────────

function MetricChartSection({
  title,
  status,
  metrics,
  quarters,
  buyQuarterIndex,
  hasPortfolioPosition,
}: {
  title: string;
  status: string;
  metrics: MetricQuarterSeries[];
  quarters: string[];
  buyQuarterIndex: number | null;
  hasPortfolioPosition: boolean;
}) {
  const [viewMode, setViewMode] = useState<"all" | "from_purchase">("all");
  const [frequency, setFrequency] = useState<"quarterly" | "annual">("quarterly");
  const [filterNm, setFilterNm] = useState(true);
  const [view, setView] = useState<"combo" | "absolute" | "yoy">("combo");

  const hasPctMetric = metrics.some((m) => m.unit === "%");
  const allIndices = quarters.map((_, i) => i);
  const activeIndices = viewMode === "from_purchase" && buyQuarterIndex != null
    ? allIndices.slice(buyQuarterIndex)
    : allIndices;

  const sectionHasRawValues = metrics.some(
    (m) => m.quarters.some((q) => q.raw_value != null),
  );
  const showViewToggle = hasPctMetric && sectionHasRawValues;

  return (
    <div className="glass-panel rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h3 className="text-[16px] font-semibold text-white/90">{title}</h3>
        <StatusBadge label={status} />
        <div className="flex items-center gap-2 ml-auto">
          <QuarterToggle value={viewMode} onChange={setViewMode} showFromPurchase={hasPortfolioPosition} />
          <FrequencyToggle value={frequency} onChange={setFrequency} />
          {showViewToggle && (
            <div className="flex items-center gap-1 bg-white/5 rounded-lg p-0.5">
              <button
                onClick={() => setView("combo")}
                className={cn(
                  "text-[10px] font-semibold px-2 py-1 rounded-md transition-colors",
                  view === "combo" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
                )}
              >
                Combo
              </button>
              <button
                onClick={() => setView("absolute")}
                className={cn(
                  "text-[10px] font-semibold px-2 py-1 rounded-md transition-colors",
                  view === "absolute" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
                )}
              >
                Absolute
              </button>
              <button
                onClick={() => setView("yoy")}
                className={cn(
                  "text-[10px] font-semibold px-2 py-1 rounded-md transition-colors",
                  view === "yoy" ? "bg-white/10 text-white/80" : "text-white/40 hover:text-white/60",
                )}
              >
                YoY %
              </button>
            </div>
          )}
        </div>
      </div>

      {metrics.length === 0 ? (
        <p className="text-[13px] text-white/30 italic">No data available yet</p>
      ) : (
        <div className="flex flex-wrap gap-4">
          {metrics.map((m) => {
            const rawQuarters = activeIndices.map((i) => m.quarters[i]).filter(Boolean);
            const displayQuarters = frequency === "annual"
              ? groupQuartersByYear(rawQuarters)
              : rawQuarters.map((q) => ({ label: q.label ?? "", value: q.value, raw_value: q.raw_value, status: q.status, ttm_eps: q.ttm_eps, components: q.components, quarter_end_price: q.quarter_end_price }));
            const normalValues = displayQuarters
              .filter((q) => q.status === "normal" && q.value != null)
              .map((q) => q.value as number);
            const naCount = displayQuarters.filter((q) => q.status === "not_applicable").length;
            const currentValue = displayQuarters.length > 0 ? displayQuarters[displayQuarters.length - 1].value ?? null : null;
            return (
              <div
                key={m.metric_id}
                className="flex-1 min-w-[340px] bg-gradient-to-b from-white/[0.04] to-white/[0.01] border border-white/[0.08] rounded-xl p-4 hover:border-white/[0.14] transition-all duration-300"
              >
                <div className="flex items-center mb-2 gap-2">
                  <span className="text-[13px] font-medium text-white/70">{m.label}</span>
                </div>
                {m.gauge_config ? (
                  <ValuationGauge
                    config={m.gauge_config}
                    unit={m.unit}
                    label={m.label}
                    metricId={m.metric_id}
                  />
                ) : (
                  <ValuationGauge
                    config={{
                      display_mode: "slider",
                      benchmark: "none",
                      benchmark_value: null,
                      band_low: null,
                      band_high: null,
                      current_value: currentValue,
                      current_quarter_raw: currentValue,
                      min_value: normalValues.length > 0 ? Math.min(...normalValues) : null,
                      max_value: normalValues.length > 0 ? Math.max(...normalValues) : null,
                      avg_value: normalValues.length > 0 ? normalValues.reduce((a, b) => a + b, 0) / normalValues.length : null,
                      positive_count: normalValues.length,
                      total_quarters: displayQuarters.length,
                      na_count: naCount,
                      warnings: [],
                    }}
                    unit={m.unit}
                    label={m.label}
                    metricId={m.metric_id}
                  />
                )}
                <MetricBarChart
                  metric={m}
                  activeQuarters={displayQuarters}
                  activeIndices={activeIndices}
                  buyQuarterIndex={buyQuarterIndex}
                  filterNm={filterNm}
                  view={showViewToggle ? view : undefined}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── FundamentalsHeader ───────────────────────────────────────────────────────

function FundamentalsHeader({
  companyName,
  hasPosition,
  purchasePeriod,
  compositeScore,
}: {
  companyName?: string | null;
  hasPosition: boolean;
  purchasePeriod?: string | null;
  compositeScore?: number | null;
}) {
  const scoreColor =
    compositeScore != null
      ? compositeScore >= 70 ? "text-emerald-400"
        : compositeScore >= 40 ? "text-amber-400"
          : "text-rose-400"
      : "text-white/30";

  return (
    <div className="flex items-center justify-between flex-wrap gap-2">
      <div className="flex items-center gap-2">
        {companyName && <span className="text-[13px] text-white/60">{companyName}</span>}
        {compositeScore != null && (
          <span className={cn("text-[15px] font-bold tabular-nums", scoreColor)}>
            {compositeScore}/100
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-[11px]">
        {hasPosition && purchasePeriod && (
          <span className="text-blue-400/60 flex items-center gap-1">
            <Info className="h-3 w-3" />
            Purchased: {purchasePeriod}
          </span>
        )}
        {!hasPosition && companyName && (
          <span className="text-white/30 flex items-center gap-1">
            <Info className="h-3 w-3" />
            Portfolio position not held
          </span>
        )}
      </div>
    </div>
  );
}

// ── DataQualityFooter ────────────────────────────────────────────────────────

function DataQualityFooter({
  dataQuality,
  onRefresh,
}: {
  dataQuality: FundamentalsResponse["data_quality"];
  onRefresh: () => void;
}) {
  if (!dataQuality) return null;
  return (
    <div className="flex items-center justify-between text-[10px] text-white/20">
      <span>
        Data since {dataQuality.earliest_data_year ?? "?"}
        {dataQuality.quarterly_data_count != null && ` · ${dataQuality.quarterly_data_count} quarters`}
      </span>
      <button onClick={onRefresh} className="flex items-center gap-1 hover:text-white/40 transition-colors">
        <RefreshCw className="h-3 w-3" />
        Refresh
      </button>
    </div>
  );
}

// ── FundamentalsPanel ────────────────────────────────────────────────────────

export function FundamentalsPanel({ symbol }: { symbol: string }) {
  const { data, loading, error, refetch } = useFundamentals(symbol);
  const [valViewMode, setValViewMode] = useState<"all" | "from_purchase">("all");
  const [valFrequency, setValFrequency] = useState<"quarterly" | "annual">("quarterly");
  const [valBenchmark, setValBenchmark] = useState<"history" | "sector">("history");
  const [moatFrequency, setMoatFrequency] = useState<"quarterly" | "annual">("quarterly");

  if (loading) {
    return (
      <div className="space-y-5 animate-fade-up">
        <div className="glass-panel p-5 rounded-2xl space-y-4">
          <Shimmer className="h-4 w-48" />
          <Shimmer className="h-3 w-32" />
        </div>
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="glass-panel p-5 rounded-2xl space-y-3">
            <Shimmer className="h-4 w-36" />
            {[1, 2, 3, 4, 5].map((j) => (
              <Shimmer key={j} className="h-5 w-full" />
            ))}
          </div>
        ))}
      </div>
    );
  }

  if (error && !data) {
    return <SectionError message={`Failed to load fundamentals: ${error}`} />;
  }

  if (!data) {
    return <SectionError message="No fundamentals data available." />;
  }

  return (
    <div className="space-y-5 animate-fade-up">
      <div className="glass-panel p-5 rounded-2xl space-y-4">
        <SectionHeader title="Fundamentals" subtitle={data.company_name ?? undefined} />
        <FundamentalsHeader
          companyName={data.company_name}
          hasPosition={data.has_portfolio_position}
          purchasePeriod={data.purchase_period}
          compositeScore={data.composite_score}
        />
      </div>

      {data.sections.map((section) => {
        if (
          section.section_id === "valuation" &&
          section.current_price != null
        ) {
          const otherMetrics = section.metrics.filter(
            (m) => m.metric_id !== "price_vs_intrinsic",
          );
          const valAllIndices = data.quarters.map((_, i) => i);
          const valActiveIndices = valViewMode === "from_purchase" && data.buy_quarter_index != null
            ? valAllIndices.slice(data.buy_quarter_index)
            : valAllIndices;
          return (
            <div key={section.section_id} className="glass-panel rounded-2xl p-5 space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <h3 className="text-[16px] font-semibold text-white/90">{section.title}</h3>
                <span className={cn(
                  "text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border",
                  section.status.label === "Intact"
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
                    : section.status.label === "Watch"
                      ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
                      : "bg-rose-500/15 text-rose-400 border-rose-500/25",
                )}>
                  {section.status.label}
                </span>
                <div className="flex items-center gap-2 ml-auto">
                  <BenchmarkToggle value={valBenchmark} onChange={setValBenchmark} />
                  <QuarterToggle value={valViewMode} onChange={setValViewMode} showFromPurchase={data.has_portfolio_position} />
                  <FrequencyToggle value={valFrequency} onChange={setValFrequency} />
                </div>
              </div>
              {section.intrinsic_valuations && section.intrinsic_valuations.length > 0 ? (
                <IntrinsicValueCard
                  intrinsicValuations={section.intrinsic_valuations}
                  currentPrice={section.current_price}
                />
              ) : (
                <IntrinsicValueEmptyState currentPrice={section.current_price} />
              )}
              {otherMetrics.length > 0 && (
                <div className="flex flex-wrap gap-4">
                  {otherMetrics.map((m) => {
                    const rawQuarters = valActiveIndices.map((i) => m.quarters[i]).filter(Boolean);
                    const displayQuarters = valFrequency === "annual"
                      ? groupQuartersByYear(rawQuarters)
                      : rawQuarters.map((q) => ({ label: q.label ?? "", value: q.value, raw_value: q.raw_value, status: q.status, ttm_eps: q.ttm_eps, components: q.components, quarter_end_price: q.quarter_end_price }));
                    if (!m.gauge_config) return null;
                    return (
                      <MetricCard
                        key={m.metric_id}
                        config={m.gauge_config}
                        unit={m.unit}
                        label={m.label}
                        metricId={m.metric_id}
                        quarters={displayQuarters}
                        benchmark={valBenchmark}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          );
        }
        if (section.section_id === "moat") {
          const moatMetrics = section.metrics.filter(
            (m) => m.metric_id === "piotroski_f" || m.metric_id === "altman_z" || m.metric_id === "interest_coverage",
          );
          const moatAllIndices = data.quarters.map((_, i) => i);
          const moatActiveIndices = valViewMode === "from_purchase" && data.buy_quarter_index != null
            ? moatAllIndices.slice(data.buy_quarter_index)
            : moatAllIndices;
          const moatFiltered = moatMetrics.map((m) => {
            const rawQ = moatActiveIndices.map((i) => m.quarters[i]).filter(Boolean);
            return {
              metricId: m.metric_id,
              label: m.label,
              unit: m.unit,
              gauge_config: m.gauge_config,
              quarters: rawQ,
            };
          });
          return (
            <div key={section.section_id} className="glass-panel rounded-2xl p-5 space-y-4">
              <div className="flex items-center gap-3 flex-wrap">
                <h3 className="text-[16px] font-semibold text-white/90">{section.title}</h3>
                <span className={cn(
                  "text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border",
                  section.status.label === "Intact"
                    ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
                    : section.status.label === "Watch"
                      ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
                      : "bg-rose-500/15 text-rose-400 border-rose-500/25",
                )}>
                  {section.status.label}
                </span>
                <div className="flex items-center gap-2 ml-auto">
                  <FrequencyToggle value={moatFrequency} onChange={setMoatFrequency} />
                </div>
              </div>
              <div className="flex flex-wrap gap-4">
                {moatFiltered.map((m) => {
                  if (!m.gauge_config) return null;
                  return (
                    <MoatGaugeCard
                      key={m.metricId}
                      config={m.gauge_config}
                      unit={m.unit}
                      label={m.label}
                      metricId={m.metricId}
                      quarters={m.quarters}
                    />
                  );
                })}
              </div>
              <MoatHistoryTable
                metrics={moatFiltered.map((m) => ({
                  metricId: m.metricId,
                  label: m.label,
                  unit: m.unit,
                  quarters: m.quarters,
                }))}
                frequency={moatFrequency}
              />
            </div>
          );
        }
        return (
          <MetricChartSection
            key={section.section_id}
            title={section.title}
            status={section.status.label}
            metrics={section.metrics}
            quarters={data.quarters}
            buyQuarterIndex={data.buy_quarter_index}
            hasPortfolioPosition={data.has_portfolio_position}
          />
        );
      })}

      <DataQualityFooter dataQuality={data.data_quality} onRefresh={refetch} />
    </div>
  );
}
