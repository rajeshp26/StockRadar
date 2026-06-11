"use client";
import { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Info, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import { useFundamentals } from "../hooks/useFundamentals";
import { SectionHeader } from "./shared-ui";
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
  status?: "normal" | "not_applicable" | "insufficient_data";
  ttm_eps?: number | null;
  components?: MetricComponent[];
};

function MetricBarChart({
  metric,
  activeQuarters,
  activeIndices,
  buyQuarterIndex,
}: {
  metric: MetricQuarterSeries;
  activeQuarters: DisplayQuarter[];
  activeIndices: number[];
  buyQuarterIndex: number | null;
}) {
  const values = activeQuarters
    .map((q) => q.value)
    .filter((v): v is number => v !== null);

  const hasAnyNonNormal = activeQuarters.some((q) => q.status && q.status !== "normal");
  const hasAnyQuarterData = activeQuarters.some((q) => q.ttm_eps != null || (q.components && q.components.length > 0));

  if (values.length === 0 && !hasAnyNonNormal && !hasAnyQuarterData) {
    return (
      <div className="py-3">
        <span className="text-[13px] font-medium text-white/60">{metric.label}</span>
        <div className="mt-2 h-[120px] flex items-center justify-center">
          <span className="text-[11px] text-white/30 italic">No data</span>
        </div>
      </div>
    );
  }

  const rawMin = values.length > 0 ? Math.min(...values) : 0;
  const rawMax = values.length > 0 ? Math.max(...values) : 1;
  const hasNegative = rawMin < 0;
  const hasPositive = rawMax > 0;

  let yMin: number;
  let yMax: number;

  if (hasNegative && hasPositive) {
    const halfRange = Math.max(Math.abs(rawMin), Math.abs(rawMax)) || 1;
    yMin = -halfRange;
    yMax = halfRange;
  } else if (hasNegative) {
    yMin = rawMin * 1.2;
    yMax = 0;
  } else {
    yMin = 0;
    yMax = rawMax * 1.2 || 1;
  }

  const chartHeight = 200;
  const padTop = 8;
  const padBottom = 8;
  const innerHeight = chartHeight - padTop - padBottom;
  const yRange = yMax - yMin || 1;

  const zeroY = padTop + ((yMax - 0) / yRange) * innerHeight;

  const gridLines = 4;
  const gridSteps = Array.from({ length: gridLines }, (_, i) => {
    const val = yMin + (i / (gridLines - 1)) * yRange;
    const y = padTop + ((yMax - val) / yRange) * innerHeight;
    return { val, y };
  });

  const scrollRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<HTMLDivElement>(null);
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

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] font-medium text-white/70">{metric.label}</span>
        <span className={cn("text-[12px] tabular-nums font-medium", activeQuarters[activeQuarters.length - 1]?.status === "not_applicable" ? "text-rose-400/60" : "text-white/50")}>
          {activeQuarters[activeQuarters.length - 1]?.status === "not_applicable" ? "N/A" : formatMetricValue(values[values.length - 1], metric.unit)}
        </span>
      </div>

      <div className="flex items-start">
        <div className="w-12 flex-shrink-0 relative" style={{ height: chartHeight }}>
          <div className="absolute left-0 top-0 bottom-0 w-full flex flex-col justify-between py-[8px]">
            {gridSteps.map((g, i) => (
              <span key={i} className="text-[10px] text-white/50 tabular-nums text-right leading-none font-medium">
                {formatAxisValue(g.val, metric.unit)}
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
            <div className="inline-flex flex-col" style={{ minWidth: `${activeQuarters.length * 39}px` }}>
              <div className="relative" style={{ height: chartHeight }}>
                {gridSteps.map((g, i) => (
                  <div
                    key={i}
                    className="absolute left-0 right-0 border-t border-white/8"
                    style={{ top: `${(g.y / chartHeight) * 100}%` }}
                  />
                ))}

                {hasNegative && hasPositive && (
                  <div
                    className="absolute left-0 right-0 border-t border-white/30"
                    style={{ top: `${(zeroY / chartHeight) * 100}%` }}
                  />
                )}

              <div className="absolute left-0 right-0 top-0 bottom-0 flex items-end gap-[3px]">
                  {activeQuarters.map((qp, i) => {
                    const qpStatus = qp.status ?? "normal";

                    if (qp.value === null && qpStatus === "normal") {
                      return (
                        <div key={i} className="w-[36px] flex-shrink-0 flex justify-center items-end h-full">
                          <div className="w-full h-px bg-white/5" />
                        </div>
                      );
                    }

                    const barHeight = qp.value != null
                      ? Math.abs(((qp.value - (hasNegative && !hasPositive ? yMin : 0)) / yRange) * innerHeight)
                      : 0;
                    const isBuy = buyQuarterIndex !== null && activeIndices[i] === buyQuarterIndex;
                    const barColor = qp.value != null && qp.value >= 0 ? "bg-emerald-500" : "bg-rose-500";

                    const isHollow = qpStatus === "not_applicable";
                    const isDashed = qpStatus === "insufficient_data";
                    const hasValue = qp.value !== null;

                    return (
                      <div
                        key={i}
                        data-testid={`bar-${i}`}
                        className="w-[36px] flex-shrink-0 flex justify-center items-end h-full relative"
                        onMouseEnter={() => setHoveredBar({ index: i, qp })}
                        onMouseLeave={() => setHoveredBar(null)}
                      >
                        {hasValue || isHollow || isDashed ? (
                          <div
                            className={cn(
                              "w-full rounded-[3px] transition-all duration-200",
                              hasValue && "opacity-85 hover:opacity-100 hover:brightness-110",
                              isHollow && "border-[1.5px] opacity-70",
                              isDashed && "border-[1.5px] border-dashed opacity-50",
                              isHollow && barColor.replace("bg-", "border-"),
                              isDashed && barColor.replace("bg-", "border-"),
                              !isHollow && !isDashed && barColor,
                              isBuy && "ring-1 ring-blue-400",
                            )}
                            style={{ height: `${Math.max(barHeight, isHollow || isDashed ? 4 : 2)}px` }}
                          />
                        ) : (
                          <div className="w-full h-px bg-white/5" />
                        )}
                        {isBuy && (
                          <span className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] text-blue-400 font-bold drop-shadow-lg pointer-events-none">
                            ▲
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="flex gap-[3px] mt-1">
                {activeQuarters.map((qp, i) => (
                  <div key={i} className="w-[36px] flex-shrink-0 text-center">
                    <span className="text-[10px] text-white/50 tabular-nums leading-none font-medium">
                      {formatQuarterLabel(qp.label)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div
            className={cn(
              "absolute left-0 top-0 bottom-0 w-7 flex items-center justify-start pl-1 bg-gradient-to-r from-gray-900/70 to-transparent z-10 transition-opacity duration-200 pointer-events-none",
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
              "absolute right-0 top-0 bottom-0 w-7 flex items-center justify-end pr-1 bg-gradient-to-l from-gray-900/70 to-transparent z-10 transition-opacity duration-200 pointer-events-none",
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
              left: Math.max(36, hoveredBar.index * 39 + 18 - scrollLeft),
              transform: "translateX(-50%)",
            }}
          >
            {(() => {
              const qp = hoveredBar.qp;
              const qpStatus = qp.status ?? "normal";
              const hasValue = qp.value !== null;
              return (
                <>
                  <div className="flex items-center gap-1.5">
                    <span className="text-white/80">{formatQuarterLabel(qp.label)}</span>
                    {qpStatus === "not_applicable" && (
                      <span className="text-rose-400/70 text-[10px] font-medium">N/A</span>
                    )}
                    {qpStatus === "insufficient_data" && (
                      <span className="text-white/30 text-[10px] italic">insufficient data</span>
                    )}
                    {qpStatus === "not_applicable" && hasValue && (
                      <span className={cn("ml-0.5 font-semibold", qp.value! >= 0 ? "text-emerald-400" : "text-rose-400")}>
                        {formatMetricValue(qp.value!, metric.unit)}
                      </span>
                    )}
                  </div>
                  {hasValue && qpStatus === "normal" && (
                    <div className="flex items-center gap-1 mt-0.5">
                      <span className={cn("font-semibold", qp.value! >= 0 ? "text-emerald-400" : "text-rose-400")}>
                        {formatMetricValue(qp.value!, metric.unit)}
                      </span>
                    </div>
                  )}
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
                  {qpStatus === "not_applicable" && (
                    <div className="text-[10px] text-rose-400/60 mt-0.5">Negative earnings</div>
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
  if (unit === "$") return `$${val.toFixed(0)}`;
  if (unit === "score") return val.toFixed(0);
  return val.toFixed(1);
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

function formatMetricValue(v: number | null | undefined, unit: string): string {
  if (v == null) return "—";
  if (unit === "%") return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  if (unit === "x") return `${v.toFixed(1)}×`;
  if (unit === "$") return `$${v.toFixed(2)}`;
  if (unit === "score") return v.toFixed(0);
  return `${v >= 0 ? "+" : ""}${v.toFixed(2)}`;
}

// ── Annual data grouping helper ──────────────────────────────────────────────

function groupQuartersByYear(
  quarters: QuarterDataPoint[],
): DisplayQuarter[] {
  const byYear = new Map<number, { label: string; value: number | null; maxQ: number; status?: "normal" | "not_applicable" | "insufficient_data"; ttm_eps?: number | null; components?: MetricComponent[] }>();
  for (const q of quarters) {
    const existing = byYear.get(q.fiscal_year);
    if (!existing || q.fiscal_quarter > existing.maxQ) {
      byYear.set(q.fiscal_year, { label: String(q.fiscal_year), value: q.value, maxQ: q.fiscal_quarter, status: q.status, ttm_eps: q.ttm_eps, components: q.components });
    }
  }
  return Array.from(byYear.entries())
    .sort(([a], [b]) => a - b)
    .map(([, v]) => ({ label: v.label, value: v.value, status: v.status, ttm_eps: v.ttm_eps, components: v.components }));
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

  const allIndices = quarters.map((_, i) => i);
  const activeIndices = viewMode === "from_purchase" && buyQuarterIndex != null
    ? allIndices.slice(buyQuarterIndex)
    : allIndices;

  return (
    <div className="glass-panel rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h3 className="text-[16px] font-semibold text-white/90">{title}</h3>
        <StatusBadge label={status} />
        <div className="flex items-center gap-2 ml-auto">
          <QuarterToggle value={viewMode} onChange={setViewMode} showFromPurchase={hasPortfolioPosition} />
          <FrequencyToggle value={frequency} onChange={setFrequency} />
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
              : rawQuarters.map((q) => ({ label: q.label ?? "", value: q.value, status: q.status, ttm_eps: q.ttm_eps, components: q.components }));
            return (
              <div
                key={m.metric_id}
                className="flex-1 min-w-[340px] bg-white/[0.03] border border-white/[0.06] rounded-xl p-4"
              >
                <MetricBarChart
                  metric={m}
                  activeQuarters={displayQuarters}
                  activeIndices={activeIndices}
                  buyQuarterIndex={buyQuarterIndex}
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

      {data.sections.map((section) => (
        <MetricChartSection
          key={section.section_id}
          title={section.title}
          status={section.status.label}
          metrics={section.metrics}
          quarters={data.quarters}
          buyQuarterIndex={data.buy_quarter_index}
          hasPortfolioPosition={data.has_portfolio_position}
        />
      ))}

      <DataQualityFooter dataQuality={data.data_quality} onRefresh={refetch} />
    </div>
  );
}
