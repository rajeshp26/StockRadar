"use client";
import { useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { RefreshCw, AlertTriangle, Sparkles } from "lucide-react";
import { useRiskAssessment } from "../hooks/useRiskAssessment";
import { RiskHero } from "./risk-hero";
import { RiskLayerCard } from "./risk-layer-card";
import { SectionHeader, fmtDateTime } from "./shared-ui";
import type { ScenarioResult, RiskAssessmentResponse } from "../types/analysis.types";

function Shimmer({ className }: { className?: string }) {
  return <div className={cn("rounded-xl bg-white/5 glass-shimmer", className)} />;
}

function ScenarioCard({ scenario }: { scenario: ScenarioResult }) {
  const isBearish = scenario.scenario === "bear" || scenario.scenario === "severe";
  const returnColor = scenario.total_return >= 0 ? "text-emerald-400" : "text-rose-400";
  const borderColor = isBearish ? "border-rose-500/25" : "border-white/8";

  return (
    <div className={cn("rounded-xl border p-4 bg-white/3", borderColor)}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-black uppercase tracking-widest text-white/50">{scenario.scenario}</span>
        <span className="text-[9px] text-white/30">{(scenario.probability * 100).toFixed(0)}% prob.</span>
      </div>
      <p className={cn("text-lg font-black tracking-tighter tabular-nums", returnColor)}>
        {scenario.total_return >= 0 ? "+" : ""}{(scenario.total_return * 100).toFixed(1)}%
      </p>
      <div className="mt-2 space-y-0.5 text-[10px] text-white/40">
        <p>EPS Growth: {(scenario.eps_growth * 100).toFixed(1)}%</p>
        <p>Exit P/E: {scenario.exit_pe.toFixed(1)}x</p>
        <p>Future Value: ${scenario.future_value.toFixed(2)}</p>
      </div>
    </div>
  );
}

export function RiskPanel({ symbol }: { symbol: string }) {
  const { data, loading, error, notComputed, recompute, generateAi } = useRiskAssessment(symbol);
  const [recomputing, setRecomputing] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const handleRecompute = useCallback(async () => {
    setRecomputing(true);
    try { await recompute(); } finally { setRecomputing(false); }
  }, [recompute]);

  const handleGenerateAi = useCallback(async () => {
    setAiLoading(true);
    setAiError(null);
    try {
      await generateAi();
    } catch (err: any) {
      setAiError(err?.message || "Failed to generate AI summary.");
    } finally {
      setAiLoading(false);
    }
  }, [generateAi]);

  if (loading) {
    return (
      <div className="space-y-6 animate-fade-up">
        <div className="glass-panel p-8">
          <div className="flex flex-col lg:flex-row items-center gap-6">
            <Shimmer className="h-[140px] w-[140px] rounded-full" />
            <div className="space-y-3 flex-1">
              <Shimmer className="h-12 w-32" />
              <Shimmer className="h-8 w-48" />
              <Shimmer className="h-6 w-40" />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="glass-panel p-5 rounded-2xl space-y-3">
              <Shimmer className="h-4 w-24" />
              <Shimmer className="h-8 w-16" />
              <Shimmer className="h-3 w-full" />
              <Shimmer className="h-3 w-3/4" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!loading && notComputed) {
    return (
      <div className="glass-panel p-12 flex flex-col items-center text-center space-y-6 animate-fade-up">
        <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-white/5 border border-white/10">
          <Shield className="h-9 w-9 text-white/25" />
        </div>
        <div>
          <h3 className="text-xl font-black text-white tracking-tight">Not yet computed</h3>
          <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-sm">
            Run the Risk Assessment to evaluate downside risk across 5 layers for {symbol}.
          </p>
        </div>
        <button onClick={handleRecompute} disabled={recomputing}
          className={cn("glass-btn inline-flex items-center gap-2 px-6 py-3 rounded-xl text-[10px] font-black uppercase tracking-widest", recomputing && "opacity-50 cursor-not-allowed")}>
          <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
          {recomputing ? "Computing\u2026" : "Run Analysis"}
        </button>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-panel p-8 animate-fade-up">
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <div className="flex-1">
            <p className="text-sm text-white/60">{error}</p>
          </div>
          <button onClick={() => window.location.reload()}
            className="glass-btn px-4 py-2 rounded-xl text-[9px] font-black uppercase tracking-widest">
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const layers = data.layers;
  const layerOrder = ["business_fragility", "balance_sheet", "valuation_compression", "earnings_stress", "drawdown_risk"] as const;
  const orderedLayers = layerOrder.map((k) => layers[k]).filter(Boolean);

  return (
    <div className="space-y-6 animate-fade-up">
      {error && (
        <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25">
          <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
          <p className="text-sm text-white/60">{error}</p>
        </div>
      )}

      <div className="glass-panel p-8 relative overflow-hidden">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{ background: "linear-gradient(90deg, transparent, rgba(99,102,241,0.5) 40%, rgba(139,92,246,0.3) 70%, transparent)" }}
          aria-hidden="true" />
        <SectionHeader
          title="Risk Assessment"
          subtitle="Composite downside risk across 5 layers"
          action={
            <button onClick={handleRecompute} disabled={recomputing}
              className={cn("glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest", recomputing && "opacity-50 cursor-not-allowed")}>
              <RefreshCw className={cn("h-3 w-3", recomputing && "animate-spin")} />
              {recomputing ? "Recomputing\u2026" : "Recompute"}
            </button>
          }
        />
        <RiskHero composite={data.composite} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {orderedLayers.slice(0, 3).map((layer) => (
          <RiskLayerCard key={layer.name} layer={layer} />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {orderedLayers.slice(3, 5).map((layer) => (
          <RiskLayerCard key={layer.name} layer={layer} />
        ))}
      </div>

      {/* Scenario Modeling */}
      {data.scenarios && data.scenarios.length > 0 && (
        <div className="glass-panel p-8">
          <SectionHeader
            title="Scenario Modeling"
            subtitle="Bull / Base / Bear / Severe projections (5-year)"
          />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {data.scenarios.map((scenario) => (
              <ScenarioCard key={scenario.scenario} scenario={scenario} />
            ))}
          </div>
        </div>
      )}

      {/* AI Narrative */}
      <div className="glass-panel p-8">
        <SectionHeader
          title="AI Summary"
          subtitle="AI-generated risk assessment narrative"
          action={
            <button onClick={handleGenerateAi} disabled={aiLoading}
              className={cn("glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest", aiLoading && "opacity-50 cursor-not-allowed")}>
              <Sparkles className={cn("h-3 w-3", aiLoading && "animate-pulse")} />
              {aiLoading ? "Generating..." : data.ai_narrative ? "Regenerate" : "Generate AI Summary"}
            </button>
          }
        />
        {aiError && (
          <div className="flex items-center gap-3 p-4 rounded-2xl bg-rose-500/8 border border-rose-500/25 mb-4">
            <AlertTriangle className="h-4 w-4 text-rose-400 flex-shrink-0" />
            <p className="text-sm text-white/60">{aiError}</p>
          </div>
        )}
        {aiLoading && (
          <div className="rounded-2xl border border-white/6 bg-white/3 px-5 py-4 space-y-2">
            <Shimmer className="h-2 w-20" />
            <Shimmer className="h-2 w-full" />
            <Shimmer className="h-2 w-4/5" />
            <Shimmer className="h-2 w-3/4" />
          </div>
        )}
        {data.ai_narrative?.narrative && !aiLoading && (
          <div className="rounded-2xl border border-indigo-500/15 bg-indigo-500/5 px-5 py-4">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="h-3 w-3 text-indigo-400/70" />
              <span className="text-[9px] font-black uppercase tracking-widest text-indigo-400/70">Risk Assessment</span>
              {data.ai_narrative.generated_at && (
                <span className="text-[9px] text-white/20 ml-auto">
                  {new Date(data.ai_narrative.generated_at).toLocaleDateString()}
                </span>
              )}
            </div>
            <p className="text-[12px] leading-relaxed text-white/60 whitespace-pre-line">
              {data.ai_narrative.narrative}
            </p>
          </div>
        )}
      </div>

      {/* Data Quality Footer */}
      <div className="glass-panel p-6">
        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-[11px] text-white/30">
          <span>Data source: <span className="text-white/50 font-bold">{data.data_quality.data_sources}</span></span>
          {data.data_quality.fiscal_year_end && (
            <span>FY end: <span className="text-white/50 font-bold">{data.data_quality.fiscal_year_end}</span></span>
          )}
          <span>Computed: <span className="text-white/50 font-bold">{fmtDateTime(data.data_quality.last_computed_at)}</span></span>
          {data.data_quality.fallbacks_used && (
            <span className="text-amber-400/60">Fallback data used — lower confidence</span>
          )}
          {!data.data_quality.fallbacks_used && (
            <span className="text-emerald-400/60">No fallbacks used</span>
          )}
        </div>
      </div>
    </div>
  );
}

function Shield({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
