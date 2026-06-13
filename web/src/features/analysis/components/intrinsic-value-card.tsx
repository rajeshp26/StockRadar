"use client";
import { cn } from "@/lib/utils";
import type { IntrinsicValuation } from "../types/analysis.types";

function computeAverageIV(vals: IntrinsicValuation[]): number {
  const positive = vals.filter((v) => v.intrinsic_value > 0);
  if (positive.length === 0) return 0;
  return positive.reduce((s, v) => s + v.intrinsic_value, 0) / positive.length;
}

function computeMOS(price: number, avgIV: number): number {
  return ((price - avgIV) / avgIV) * 100;
}

function badgeLabel(mos: number): string {
  if (mos > 5) return "Undervalued";
  if (mos < -5) return "Overvalued";
  return "Fairly Valued";
}

function badgeColor(mos: number): string {
  if (mos > 5) return "bg-emerald-500/15 text-emerald-400 border-emerald-500/25";
  if (mos < -5) return "bg-rose-500/15 text-rose-400 border-rose-500/25";
  return "bg-white/10 text-white/50 border-white/20";
}

function GaugeBar({
  price,
  avgIV,
  minIV,
  maxIV,
}: {
  price: number;
  avgIV: number;
  minIV: number;
  maxIV: number;
}) {
  const margin = (maxIV - minIV) * 0.2 || 1;
  const left = minIV - margin;
  const right = maxIV + margin;
  const range = right - left || 1;

  const pricePct = ((price - left) / range) * 100;
  const avgPct = ((avgIV - left) / range) * 100;

  const clampedPrice = Math.max(2, Math.min(98, pricePct));
  const clampedAvg = Math.max(2, Math.min(98, avgPct));

  const mid = right - margin;

  return (
    <div className="relative h-8 mt-2">
      <div className="absolute inset-0 rounded-full overflow-hidden">
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(to right, #10b981 0%, #10b981 33%, #6b7280 33%, #6b7280 66%, #ef4444 66%, #ef4444 100%)",
            opacity: 0.2,
          }}
        />
      </div>

      <div className="absolute inset-0 flex items-center px-1">
        <div className="relative w-full h-1.5 bg-white/10 rounded-full">
          <div
            className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-emerald-400 border-2 border-emerald-600 shadow-lg z-10 transition-all"
            style={{ left: `calc(${clampedPrice}% - 6px)` }}
            title="Current Price"
          />
          <div
            className="absolute top-1/2 -translate-y-1/2 w-2 h-2 rounded-full bg-white/80 border border-white/40 shadow z-20"
            style={{ left: `calc(${clampedAvg}% - 4px)` }}
            title="Average Intrinsic Value"
          />
        </div>
      </div>

      <div className="flex justify-between text-[10px] text-white/30 mt-1 px-1">
        <span>${left.toFixed(0)}</span>
        <span className="font-medium text-white/50">avg IV: ${avgIV.toFixed(2)}</span>
        <span>${right.toFixed(0)}</span>
      </div>
    </div>
  );
}

function MethodCard({
  method,
  intrinsicValue,
  currentPrice,
}: {
  method: string;
  intrinsicValue: number;
  currentPrice: number;
}) {
  const mos = ((currentPrice - intrinsicValue) / intrinsicValue) * 100;
  const isUndervalued = mos > 5;
  const isOvervalued = mos < -5;

  return (
    <div
      className={cn(
        "flex-1 min-w-[130px] bg-white/[0.03] border rounded-lg p-3",
        isUndervalued
          ? "border-emerald-500/20"
          : isOvervalued
            ? "border-rose-500/20"
            : "border-white/10",
      )}
    >
      <div className="text-[11px] text-white/50 font-medium">{method}</div>
      <div className="text-[15px] font-semibold text-white/90 mt-0.5">
        ${intrinsicValue.toFixed(2)}
      </div>
      <div
        className={cn(
          "text-[11px] font-medium mt-1",
          isUndervalued
            ? "text-emerald-400"
            : isOvervalued
              ? "text-rose-400"
              : "text-white/40",
        )}
      >
        {mos > 0 ? "+" : ""}
        {mos.toFixed(1)}%
      </div>
    </div>
  );
}

export function IntrinsicValueCard({
  intrinsicValuations,
  currentPrice,
}: {
  intrinsicValuations: IntrinsicValuation[];
  currentPrice: number;
}) {
  const avgIV = computeAverageIV(intrinsicValuations);
  const mos = computeMOS(currentPrice, avgIV);

  const positiveVals = intrinsicValuations.filter((v) => v.intrinsic_value > 0);
  const minIV = Math.min(...positiveVals.map((v) => v.intrinsic_value));
  const maxIV = Math.max(...positiveVals.map((v) => v.intrinsic_value));

  const isUndervalued = mos > 5;
  const isOvervalued = mos < -5;

  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 w-full">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[13px] font-medium text-white/70">Intrinsic Value</span>
        <span className={cn("text-[11px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full border", badgeColor(mos))}>
          {badgeLabel(mos)}
        </span>
      </div>

      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-[28px] font-bold text-white/90 tabular-nums">
          ${avgIV.toFixed(2)}
        </span>
        <span className="text-[13px] text-white/40">avg intrinsic</span>
      </div>

      <div className="text-[13px] text-white/50 mb-3">
        Current Price: <span className="font-semibold text-white/80">${currentPrice.toFixed(2)}</span>
        <span
          className={cn(
            "ml-2 font-medium",
            isUndervalued ? "text-emerald-400" : isOvervalued ? "text-rose-400" : "text-white/40",
          )}
        >
          ({mos > 0 ? "+" : ""}
          {mos.toFixed(1)}%)
        </span>
      </div>

      <GaugeBar price={currentPrice} avgIV={avgIV} minIV={minIV} maxIV={maxIV} />

      <div className="mt-4">
        <div className="text-[11px] text-white/40 font-medium mb-2">by Method</div>
        <div className="flex flex-wrap gap-2">
          {positiveVals.map((v) => (
            <MethodCard
              key={v.method}
              method={v.method}
              intrinsicValue={v.intrinsic_value}
              currentPrice={currentPrice}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export function IntrinsicValueEmptyState({
  currentPrice,
}: {
  currentPrice?: number | null;
}) {
  return (
    <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4 w-full">
      <div className="flex items-center gap-3 mb-3">
        <span className="text-[13px] font-medium text-white/70">Intrinsic Value</span>
      </div>
      {currentPrice != null && (
        <div className="text-[13px] text-white/50 mb-2">
          Current Price: <span className="font-semibold text-white/80">${currentPrice.toFixed(2)}</span>
        </div>
      )}
      <p className="text-[12px] text-white/30 italic">
        No intrinsic value data — run a DCF or other valuation first
      </p>
    </div>
  );
}
