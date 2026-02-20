"use client";

import { cn } from "@/lib/utils";
import { VALUATION_METHODS } from "../valuation/methods";
import { TrendingUp, CheckCircle2 } from "lucide-react";

export function ValuationOverview() {
  const enabledMethods  = VALUATION_METHODS.filter((m) => m.enabled);
  const disabledMethods = VALUATION_METHODS.filter((m) => !m.enabled);

  return (
    <div className="glass-panel p-8 space-y-6 animate-fade-up">

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/15 border border-indigo-500/25">
          <TrendingUp className="h-4 w-4 text-indigo-400" />
        </div>
        <div>
          <h3 className="text-base font-black text-white tracking-tight">Valuation Overview</h3>
          <p className="text-[11px] text-white/35 mt-0.5">
            Compare intrinsic value estimates across methodologies
          </p>
        </div>
      </div>

      <div className="glass-divider" />

      {/* Enabled methods */}
      {enabledMethods.length > 0 && (
        <div className="space-y-3">
          <p className="glass-overline">Available Methods</p>
          <div className="space-y-2">
            {enabledMethods.map((method) => (
              <div
                key={method.id}
                className={cn(
                  "glass-card rounded-xl px-5 py-4",
                  "flex items-center justify-between gap-4",
                )}
              >
                <div className="min-w-0">
                  <p className="text-sm font-black text-white tracking-tight">
                    {method.label}
                  </p>
                  <p className="text-xs text-white/35 mt-0.5 truncate">
                    {method.description}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 flex-shrink-0 text-emerald-400">
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span className="text-[10px] font-black uppercase tracking-widest">
                    Enabled
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Disabled methods (if any) */}
      {disabledMethods.length > 0 && (
        <div className="space-y-3">
          <p className="glass-overline">Coming Soon</p>
          <div className="space-y-2">
            {disabledMethods.map((method) => (
              <div
                key={method.id}
                className="rounded-xl px-5 py-4 border border-white/5 bg-white/2 flex items-center justify-between gap-4 opacity-50"
              >
                <div className="min-w-0">
                  <p className="text-sm font-bold text-white/60 tracking-tight">
                    {method.label}
                  </p>
                  <p className="text-xs text-white/25 mt-0.5 truncate">
                    {method.description}
                  </p>
                </div>
                <span className="text-[10px] font-black uppercase tracking-widest text-white/20 flex-shrink-0">
                  Soon
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer hint */}
      <p className="text-xs text-white/25 leading-relaxed border-t border-white/5 pt-4">
        Select a method above to dive into assumptions, diagnostics, and historical valuations.
      </p>
    </div>
  );
}