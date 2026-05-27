"use client";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { RiskLayer, BusinessFragility, BalanceSheetRisk, ValuationCompressionRisk, EarningsStressRisk, DrawdownRisk } from "../types/analysis.types";

function MoatCategoryBadge({ category }: { category: string | null | undefined }) {
  if (!category) return null;
  const cfg: Record<string, string> = {
    Wide: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
    Narrow: "bg-amber-500/15 border-amber-500/30 text-amber-400",
    None: "bg-rose-500/15 border-rose-500/30 text-rose-400",
  };
  return (
    <span className={cn("px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest border", cfg[category] || "bg-white/8 border-white/15 text-white/50")}>
      {category}
    </span>
  );
}

function SeverityBadge({ category }: { category: string }) {
  const cfg: Record<string, string> = {
    low: "bg-emerald-500/15 border-emerald-500/30 text-emerald-400",
    moderate: "bg-amber-500/15 border-amber-500/30 text-amber-400",
    elevated: "bg-orange-500/15 border-orange-500/30 text-orange-400",
    high: "bg-rose-500/15 border-rose-500/30 text-rose-400",
    severe: "bg-red-500/15 border-red-500/30 text-red-400",
  };
  return (
    <span className={cn("px-2 py-0.5 rounded-full text-[9px] font-black uppercase tracking-widest border", cfg[category] || "bg-white/8 border-white/15 text-white/50")}>
      {category}
    </span>
  );
}

function MetricRow({ metric }: { metric: { name: string; label: string; status: string } }) {
  const statusColor = metric.status === "pass" ? "text-emerald-400" :
    metric.status === "caution" ? "text-amber-400" :
    metric.status === "fail" ? "text-rose-400" :
    "text-white/30";
  return (
    <div className="flex items-center justify-between gap-4 py-1.5 border-b border-white/5 last:border-0">
      <span className="text-[10px] font-semibold text-white/40">{metric.name}</span>
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold text-white/70 text-right tabular-nums">{metric.label}</span>
        <span className={cn("w-1.5 h-1.5 rounded-full", statusColor)} />
      </div>
    </div>
  );
}

function BusinessFragilitySection({ layer }: { layer: BusinessFragility }) {
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {layer.moat_category && <MoatCategoryBadge category={layer.moat_category} />}
        {layer.recurrence_classification && (
          <span className="text-[9px] text-white/40 uppercase tracking-widest">
            {layer.recurrence_classification} Recurrence
          </span>
        )}
      </div>
      {layer.roic_minus_wacc != null && (
        <p className="text-[10px] text-white/30">
          ROIC - WACC: <span className={layer.roic_minus_wacc > 0 ? "text-emerald-400" : "text-rose-400"}>
            {layer.roic_minus_wacc.toFixed(1)}%
          </span>
        </p>
      )}
      {layer.sector && <p className="text-[10px] text-white/30">{layer.sector}{layer.industry ? ` / ${layer.industry}` : ""}</p>}
    </div>
  );
}

function BalanceSheetSection({ layer }: { layer: BalanceSheetRisk }) {
  return (
    <div className="space-y-1">
      {layer.interest_coverage != null && (
        <p className="text-[10px] text-white/30">Interest Coverage: <span className="text-white/50 font-bold">{layer.interest_coverage.toFixed(1)}x</span></p>
      )}
      {layer.current_ratio != null && (
        <p className="text-[10px] text-white/30">Current Ratio: <span className="text-white/50 font-bold">{layer.current_ratio.toFixed(2)}</span></p>
      )}
      {layer.fcf_stability_pct != null && (
        <p className="text-[10px] text-white/30">FCF Stability: <span className="text-white/50 font-bold">{(layer.fcf_stability_pct * 100).toFixed(0)}%</span></p>
      )}
    </div>
  );
}

function ValuationSection({ layer }: { layer: ValuationCompressionRisk }) {
  return (
    <div className="space-y-1">
      {layer.pe_percentile != null && (
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-white/30">P/E (5y):</span>
          <div className="flex-1 h-1.5 rounded-full bg-white/8 overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-500",
                layer.pe_percentile > 70 ? "bg-rose-400" : layer.pe_percentile > 40 ? "bg-amber-400" : "bg-emerald-400"
              )}
              style={{ width: `${layer.pe_percentile}%` }}
            />
          </div>
          <span className="text-[10px] text-white/50 font-bold tabular-nums">{layer.pe_percentile.toFixed(0)}th</span>
        </div>
      )}
      {layer.pe_5y_min != null && layer.pe_5y_max != null && (
        <p className="text-[9px] text-white/25">Range: {layer.pe_5y_min.toFixed(0)} – {layer.pe_5y_max.toFixed(0)} (median: {layer.pe_5y_median?.toFixed(0)})</p>
      )}
      {layer.peg_ratio != null && (
        <p className="text-[10px] text-white/30">PEG: <span className={layer.peg_ratio < 1.5 ? "text-emerald-400" : layer.peg_ratio < 3 ? "text-amber-400" : "text-rose-400"}>{layer.peg_ratio.toFixed(2)}</span></p>
      )}
    </div>
  );
}

function EarningsSection({ layer }: { layer: EarningsStressRisk }) {
  return (
    <div className="space-y-1">
      {layer.eps_cagr_5y != null && (
        <p className="text-[10px] text-white/30">EPS CAGR (5y): <span className={layer.eps_cagr_5y >= 0.1 ? "text-emerald-400" : "text-rose-400"}>{(layer.eps_cagr_5y * 100).toFixed(1)}%</span></p>
      )}
      {layer.revenue_cagr_5y != null && (
        <p className="text-[10px] text-white/30">Revenue CAGR (5y): <span className={layer.revenue_cagr_5y >= 0.1 ? "text-emerald-400" : "text-amber-400"}>{(layer.revenue_cagr_5y * 100).toFixed(1)}%</span></p>
      )}
      {layer.operating_margin_trend && (
        <p className="text-[10px] text-white/30">Margin Trend: <span className={layer.operating_margin_trend === "expanding" ? "text-emerald-400" : layer.operating_margin_trend === "contracting" ? "text-rose-400" : "text-amber-400"}>{layer.operating_margin_trend}</span></p>
      )}
    </div>
  );
}

function DrawdownSection({ layer }: { layer: DrawdownRisk }) {
  return (
    <div className="space-y-1">
      {layer.max_drawdown_5y != null && (
        <p className="text-[10px] text-white/30">Max DD (5y): <span className="text-rose-400">{(layer.max_drawdown_5y * 100).toFixed(1)}%</span></p>
      )}
      {layer.beta_5y != null && (
        <p className="text-[10px] text-white/30">Beta (5y): <span className={layer.beta_5y < 1.2 ? "text-emerald-400" : layer.beta_5y < 1.5 ? "text-amber-400" : "text-rose-400"}>{layer.beta_5y.toFixed(2)}</span></p>
      )}
      {layer.crisis_drawdowns && layer.crisis_drawdowns.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {layer.crisis_drawdowns.slice(0, 2).map((c, i) => (
            <span key={i} className="px-1.5 py-0.5 rounded bg-rose-500/10 border border-rose-500/20 text-[8px] text-rose-400/70">
              {c.crisis_name}: {(c.max_drawdown * 100).toFixed(0)}%
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function RiskLayerCard({
  layer,
}: {
  layer: RiskLayer;
}) {
  const [expanded, setExpanded] = useState(false);

  const severityColor =
    layer.category === "low" ? "border-l-emerald-500/50" :
    layer.category === "moderate" ? "border-l-amber-500/50" :
    layer.category === "elevated" ? "border-l-orange-500/50" :
    layer.category === "high" ? "border-l-rose-500/50" :
    "border-l-red-500/50";

  return (
    <div className={cn("glass-panel rounded-2xl border-l-4 p-5 transition-all", severityColor)}>
      <div className="flex items-start justify-between mb-3 cursor-pointer" onClick={() => setExpanded(!expanded)}>
        <div>
          <h4 className="text-sm font-black text-white tracking-tight">{layer.display_name}</h4>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-2xl font-black tracking-tighter text-white tabular-nums">
              {layer.score.toFixed(1)}
            </span>
            <span className="text-[10px] text-white/30 font-medium">/ 10</span>
            <SeverityBadge category={layer.category} />
          </div>
        </div>
        <div className="flex-shrink-0 text-white/20">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </div>
      </div>

      {expanded && (
        <div className="space-y-3 animate-fade-up">
          {/* Metrics */}
          <div className="rounded-xl bg-white/3 border border-white/8 px-3 py-2">
            {layer.metrics.slice(0, 6).map((m, i) => (
              <MetricRow key={i} metric={m} />
            ))}
          </div>

          {/* Layer-specific content */}
          {layer.name === "business_fragility" && <BusinessFragilitySection layer={layer as BusinessFragility} />}
          {layer.name === "balance_sheet" && <BalanceSheetSection layer={layer as BalanceSheetRisk} />}
          {layer.name === "valuation_compression" && <ValuationSection layer={layer as ValuationCompressionRisk} />}
          {layer.name === "earnings_stress" && <EarningsSection layer={layer as EarningsStressRisk} />}
          {layer.name === "drawdown_risk" && <DrawdownSection layer={layer as DrawdownRisk} />}
        </div>
      )}
    </div>
  );
}
