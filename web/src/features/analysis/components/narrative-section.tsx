"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Info } from "lucide-react";
import * as Popover from "@radix-ui/react-popover";
import type { MetricQuarterSeries, MetricComponent, QuarterDataPoint } from "../types/analysis.types";

// ── Info definitions for each metric ──────────────────────────────────────

const METRIC_INFO: Record<string, { title: string; description: string; whatToLookFor: string }> = {
  eps_surprise: {
    title: "EPS Surprise",
    description:
      "EPS (Earnings Per Share) Surprise measures the percentage difference between a company's actual reported EPS and the consensus analyst estimate for that quarter.",
    whatToLookFor:
      "Consistent positive surprises (beats) suggest strong execution and potentially underestimated guidance. Watch for narrowing beats — it means analysts are catching up. Negative surprises (misses) can signal operational issues or overly optimistic guidance.",
  },
  revenue_surprise: {
    title: "Revenue Surprise",
    description:
      "Revenue Surprise measures the percentage difference between actual reported revenue and the consensus analyst estimate for that quarter.",
    whatToLookFor:
      "Revenue surprises are often more meaningful than EPS surprises because revenue is harder to manipulate. Consistent revenue beats indicate genuine business momentum. Watch for revenue beats that don't translate to EPS beats — it may signal margin pressure.",
  },
  beat_rate: {
    title: "Beat Rate",
    description:
      "Beat Rate is the percentage of quarters over a trailing period where the company reported EPS above the consensus analyst estimate.",
    whatToLookFor:
      "A beat rate above 60% is generally considered strong. Above 80% is exceptional. A declining beat rate may indicate the business is facing headwinds or that analyst models are improving. Rates below 40% warrant caution.",
  },
};

// ── InfoPopover ───────────────────────────────────────────────────────────

function InfoPopover({ metricId }: { metricId: string }) {
  const info = METRIC_INFO[metricId];
  if (!info) return null;

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button
          type="button"
          className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-white/10 hover:bg-white/20 transition-colors cursor-pointer"
          aria-label={`Learn more about ${info.title}`}
        >
          <Info className="w-2.5 h-2.5 text-white/50" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="top"
          align="center"
          sideOffset={6}
          className="z-50 w-72 rounded-xl bg-[#1c2023] border border-[#2f3336] p-4 shadow-2xl"
        >
          <h4 className="text-[13px] font-semibold text-white/90 mb-2">{info.title}</h4>
          <p className="text-[11px] text-white/60 leading-relaxed mb-3">{info.description}</p>
          <div className="border-t border-white/10 pt-2">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-blue-400/80 block mb-1">
              What to look for
            </span>
            <p className="text-[11px] text-white/50 leading-relaxed">{info.whatToLookFor}</p>
          </div>
          <Popover.Arrow className="fill-[#1c2023]" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────

function getSurpriseColor(label: string | null | undefined): string {
  if (label === "beat") return "bg-emerald-500/15 text-emerald-400 border-emerald-500/25";
  if (label === "miss") return "bg-rose-500/15 text-rose-400 border-rose-500/25";
  if (label === "inline") return "bg-amber-500/15 text-amber-400 border-amber-500/25";
  return "bg-white/5 text-white/30 border-white/10";
}

function findComponent(components: MetricComponent[] | null | undefined, label: string): MetricComponent | undefined {
  return components?.find((c) => c.label === label);
}

function getLatestQuarter(quarters: QuarterDataPoint[]): QuarterDataPoint | null {
  if (quarters.length === 0) return null;
  return quarters[quarters.length - 1];
}

function groupByYear(quarters: QuarterDataPoint[]): { year: number; items: QuarterDataPoint[] }[] {
  const map = new Map<number, QuarterDataPoint[]>();
  for (const q of quarters) {
    if (q.fiscal_year == null) continue;
    const list = map.get(q.fiscal_year) ?? [];
    list.push(q);
    map.set(q.fiscal_year, list);
  }
  return Array.from(map.entries())
    .sort(([a], [b]) => b - a)
    .map(([year, items]) => ({ year, items }));
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(1)}%`;
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return "\u2014";
  if (Math.abs(v) >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(2)}B`;
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(2)}`;
}

// ── SurpriseCard ──────────────────────────────────────────────────────────

function SurpriseCard({
  metric,
  icon,
  accent,
}: {
  metric: MetricQuarterSeries;
  icon: string;
  accent: "blue" | "green";
}) {
  const { quarters } = metric;
  const latest = getLatestQuarter(quarters);
  const yearGroups = groupByYear(quarters);
  const accentBorder = accent === "blue" ? "border-blue-500/25" : "border-emerald-500/25";
  const accentBg = accent === "blue" ? "bg-blue-500/10" : "bg-emerald-500/10";
  const accentText = accent === "blue" ? "text-blue-400" : "text-emerald-400";

  // Snapshot values from latest quarter
  const latestLabel = latest?.narrative_label ?? null;
  const actualComp = latest ? findComponent(latest.components, `${metric.metric_id.startsWith("eps") ? "EPS" : "Revenue"} Actual`) : undefined;
  const estComp = latest ? findComponent(latest.components, `${metric.metric_id.startsWith("eps") ? "EPS" : "Revenue"} Estimate`) : undefined;

  return (
    <div className={cn(
      "flex-1 min-w-[300px] bg-gradient-to-b from-white/[0.04] to-white/[0.01] border border-white/[0.08] rounded-xl p-4 hover:border-white/[0.14] transition-all duration-300",
    )}>
      {/* Card Header with info icon */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">{icon}</span>
        <span className="text-[13px] font-medium text-white/70">{metric.label}</span>
        <InfoPopover metricId={metric.metric_id} />
      </div>

      {/* Current Quarter Snapshot */}
      {latest && (
        <div className={cn(
          "flex items-center justify-between p-3 rounded-lg border mb-4",
          accentBorder, accentBg,
        )}>
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-white/50">Latest: {latest.label}</span>
            <span className={cn(
              "text-[10px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded",
              getSurpriseColor(latestLabel),
            )}>
              {latestLabel ?? "N/A"}
            </span>
          </div>
          <div className="text-right">
            <div className="text-[15px] font-bold tabular-nums" style={{ color: latestLabel === "beat" ? "#4ade80" : latestLabel === "miss" ? "#f87171" : "#fbbf24" }}>
              {fmtPct(latest.value)}
            </div>
            {(actualComp || estComp) && (
              <div className="text-[10px] text-white/40">
                {actualComp && <span>Act. {fmtMoney(actualComp.value)} </span>}
                {estComp && <span>Est. {fmtMoney(estComp.value)}</span>}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Year-grouped Quarter Chips */}
      <div className="space-y-3">
        {yearGroups.map(({ year, items }) => (
          <div key={year}>
            <div className="text-[10px] font-semibold text-white/30 uppercase tracking-wider mb-1.5">{year}</div>
            <div className="grid grid-cols-4 gap-1.5">
              {items.map((q, i) => {
                const label = q.narrative_label ?? null;
                const hasData = q.value != null;
                return (
                  <div
                    key={i}
                    className={cn(
                      "flex flex-col items-center py-1.5 px-1 rounded-lg border transition-all duration-150",
                      hasData && label
                        ? label === "beat"
                          ? "bg-emerald-500/10 border-emerald-500/20"
                          : label === "miss"
                            ? "bg-rose-500/10 border-rose-500/20"
                            : "bg-amber-500/10 border-amber-500/20"
                        : "bg-white/[0.02] border-white/[0.06]",
                    )}
                  >
                    <span className={cn(
                      "text-[11px] font-bold tabular-nums",
                      hasData && label === "beat" ? "text-emerald-400"
                        : hasData && label === "miss" ? "text-rose-400"
                          : hasData && label === "inline" ? "text-amber-400"
                            : "text-white/30",
                    )}>
                      {hasData ? fmtPct(q.value) : "\u2014"}
                    </span>
                    <span className="text-[8px] text-white/30 mt-0.5">
                      Q{q.fiscal_quarter}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── BeatRateCard ──────────────────────────────────────────────────────────

function BeatRateCard({ metric }: { metric: MetricQuarterSeries }) {
  const { quarters } = metric;
  const yearGroups = groupByYear(quarters);
  const latest = getLatestQuarter(quarters);

  // Compute per-year beat rate from the underlying earnings data
  // Group all quarters by year and compute beat rate per year
  const perYearRate: { year: number; beat: number; total: number; rate: number }[] = [];
  for (const { year, items } of yearGroups) {
    const vals = items.map((q) => q.value).filter((v): v is number => v != null);
    const beat = vals.filter((v) => v > 0).length;
    const total = vals.length;
    perYearRate.push({
      year,
      beat,
      total,
      rate: total > 0 ? Math.round((beat / total) * 100) : 0,
    });
  }

  const maxRate = Math.max(...perYearRate.map((r) => r.rate), 1);

  return (
    <div className="flex-1 min-w-[300px] bg-gradient-to-b from-white/[0.04] to-white/[0.01] border border-white/[0.08] rounded-xl p-4 hover:border-white/[0.14] transition-all duration-300">
      {/* Card Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className="text-lg">{"\uD83C\uDFAF"}</span>
        <span className="text-[13px] font-medium text-white/70">{metric.label}</span>
        <InfoPopover metricId="beat_rate" />
      </div>

      {/* Overall beat rate snapshot */}
      {latest && latest.value != null && (
        <div className="flex items-center justify-between p-3 rounded-lg border border-purple-500/25 bg-purple-500/10 mb-4">
          <span className="text-[11px] text-white/50">Overall Beat Rate</span>
          <div className="text-right">
            <div className="text-[15px] font-bold tabular-nums text-purple-400">
              {Math.round(latest.value)}%
            </div>
            <div className="text-[10px] text-white/40">
              {quarters.filter((q) => q.value != null && q.value > 0).length} of {quarters.filter((q) => q.value != null).length} quarters
            </div>
          </div>
        </div>
      )}

      {/* Per-year bar chart */}
      <div className="space-y-3">
        {perYearRate.map(({ year, beat, total, rate }) => (
          <div key={year}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-semibold text-white/30 uppercase tracking-wider">{year}</span>
              <span className="text-[10px] text-white/40">{beat}/{total} beats</span>
            </div>
            <div className="relative h-6 bg-white/5 rounded-full overflow-hidden">
              <div
                className={cn(
                  "h-full rounded-full transition-all duration-500",
                  rate >= 60 ? "bg-gradient-to-r from-emerald-500 to-emerald-400"
                    : rate >= 30 ? "bg-gradient-to-r from-amber-500 to-amber-400"
                      : "bg-gradient-to-r from-rose-500 to-rose-400",
                )}
                style={{ width: `${Math.max((rate / maxRate) * 100, rate > 0 ? 8 : 0)}%` }}
              />
              <span className="absolute inset-0 flex items-center justify-end pr-2 text-[10px] font-bold tabular-nums text-white/80">
                {rate}%
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="flex gap-3 mt-3 pt-3 border-t border-white/10">
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-emerald-500" />
          <span className="text-[9px] text-white/40">High (\u226560%)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-amber-500" />
          <span className="text-[9px] text-white/40">Mid (30-59%)</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2 h-2 rounded-full bg-rose-500" />
          <span className="text-[9px] text-white/40">Low (&lt;30%)</span>
        </div>
      </div>
    </div>
  );
}

// ── NarrativeSection (exported) ───────────────────────────────────────────

export function NarrativeSection({
  metrics,
  status,
}: {
  metrics: MetricQuarterSeries[];
  status: string;
}) {
  const epsMetric = metrics.find((m) => m.metric_id === "eps_surprise");
  const revMetric = metrics.find((m) => m.metric_id === "revenue_surprise");
  const beatMetric = metrics.find((m) => m.metric_id === "beat_rate");

  return (
    <div className="glass-panel rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <h3 className="text-[16px] font-semibold text-white/90">Narrative</h3>
        <span className={cn(
          "text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border",
          status === "Intact"
            ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/25"
            : status === "Watch"
              ? "bg-amber-500/15 text-amber-400 border-amber-500/25"
              : "bg-rose-500/15 text-rose-400 border-rose-500/25",
        )}>
          {status}
        </span>
      </div>

      {!epsMetric && !revMetric && !beatMetric ? (
        <p className="text-[13px] text-white/30 italic">No earnings surprise data available</p>
      ) : (
        <div className="flex flex-wrap gap-4">
          {epsMetric && (
            <SurpriseCard metric={epsMetric} icon={"\uD83D\uDCC8"} accent="blue" />
          )}
          {revMetric && (
            <SurpriseCard metric={revMetric} icon={"\uD83D\uDCB0"} accent="green" />
          )}
          {beatMetric && (
            <BeatRateCard metric={beatMetric} />
          )}
        </div>
      )}
    </div>
  );
}
