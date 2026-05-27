"use client";
import { cn } from "@/lib/utils";
import { AlertTriangle } from "lucide-react";
import type { CompositeScore } from "../types/analysis.types";

export function RiskHero({
  composite,
}: {
  composite: CompositeScore;
}) {
  const { score, category, maximum_expected_loss_pct: maximumExpectedLossPct, bear_case: bearCase } = composite;

  const ringColor =
    category === "Very Low Downside" ? "#34d399" :
    category === "Moderate" ? "#fbbf24" :
    category === "Elevated" ? "#fb923c" :
    "#f87171";

  const glowColor =
    category === "Very Low Downside" ? "rgba(52,211,153,0.35)" :
    category === "Moderate" ? "rgba(251,191,36,0.35)" :
    category === "Elevated" ? "rgba(251,146,60,0.35)" :
    "rgba(248,113,113,0.35)";

  const labelColor =
    category === "Very Low Downside" ? "text-emerald-400" :
    category === "Moderate" ? "text-amber-400" :
    category === "Elevated" ? "text-orange-400" :
    "text-rose-400";

  const size = 140;
  const radius = 54;
  const cx = size / 2;
  const cy = size / 2;
  const strokeW = 10;
  const arcAngle = 270;
  const circumference = 2 * Math.PI * radius;
  const arcLength = (arcAngle / 360) * circumference;
  const normalized = Math.max(0, Math.min(100, score ?? 0));
  const filledLen = (normalized / 100) * arcLength;
  const rotation = 135;

  return (
    <div className="flex flex-col lg:flex-row items-center gap-8 p-6">
      <div className="flex flex-col items-center gap-4">
        <div className="relative" style={{ width: size, height: size }}>
          <div
            className="absolute inset-0 rounded-full blur-xl opacity-60 pointer-events-none"
            style={{ background: glowColor }}
            aria-hidden="true"
          />
          <svg
            width={size}
            height={size}
            viewBox={`0 0 ${size} ${size}`}
            aria-label={`Composite risk score: ${score} out of 100`}
          >
            <circle
              cx={cx} cy={cy} r={radius}
              fill="none" stroke="rgba(255,255,255,0.07)"
              strokeWidth={strokeW}
              strokeDasharray={`${arcLength} ${circumference}`}
              strokeDashoffset={0}
              strokeLinecap="round"
              transform={`rotate(${rotation} ${cx} ${cy})`}
            />
            <circle
              cx={cx} cy={cy} r={radius}
              fill="none" stroke={ringColor}
              strokeWidth={strokeW}
              strokeDasharray={`${filledLen} ${circumference}`}
              strokeDashoffset={0}
              strokeLinecap="round"
              transform={`rotate(${rotation} ${cx} ${cy})`}
              style={{ transition: "stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)" }}
            />
            <text
              x={cx} y={cy - 6}
              textAnchor="middle" dominantBaseline="middle"
              fill="white" fontSize={size * 0.2} fontWeight="900"
              fontFamily="inherit" letterSpacing="-1"
            >
              {score != null ? Math.round(score) : "—"}
            </text>
            <text
              x={cx} y={cy + size * 0.17}
              textAnchor="middle" dominantBaseline="middle"
              fill="rgba(255,255,255,0.3)"
              fontSize={size * 0.08} fontWeight="700"
              fontFamily="inherit" letterSpacing="2"
            >
              COMPOSITE
            </text>
          </svg>
        </div>
        <p className={cn("text-sm font-black uppercase tracking-widest text-center", labelColor)}>
          {category}
        </p>
      </div>

      <div className="flex flex-col gap-4">
        <div className="glass-stat px-6 py-4 text-center">
          <p className="glass-overline">Maximum Expected Loss</p>
          <p className={cn(
            "text-4xl font-black tracking-tighter",
            maximumExpectedLossPct == null ? "text-white/30" :
            maximumExpectedLossPct > 20 ? "text-rose-400" :
            maximumExpectedLossPct > 10 ? "text-amber-400" :
            "text-emerald-400"
          )}>
            {maximumExpectedLossPct != null ? `${maximumExpectedLossPct.toFixed(1)}%` : "N/A"}
          </p>
          <p className="text-[10px] text-white/30 mt-1">Probability-weighted worst case</p>
        </div>

        {bearCase && bearCase.downside_pct < 0 && (
          <div className="rounded-xl bg-white/5 border border-white/10 px-5 py-3">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-3 w-3 text-amber-400" />
              <p className="text-[9px] font-black uppercase tracking-widest text-amber-400/70">Bear Case</p>
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
              <span className="text-white/40">Downside</span>
              <span className="text-white/70 font-bold text-right">{(bearCase.downside_pct * 100).toFixed(1)}%</span>
              <span className="text-white/40">Exit P/E</span>
              <span className="text-white/70 font-bold text-right">{bearCase.exit_pe_ratio.toFixed(1)}x</span>
              <span className="text-white/40">Future Value</span>
              <span className="text-white/70 font-bold text-right">${bearCase.future_value.toFixed(2)}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
