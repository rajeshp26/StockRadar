"use client";
import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLivePrice } from "@/features/analysis/hooks/useLivePrice";
import { formatTimestamp } from "@/lib/time";

interface LivePriceHeaderProps {
  symbol: string;
  initialPrice: number | null;
  initialChange: number | null;
  initialChangePercent: number | null;
  initialLastUpdated: string | null;
}

export function LivePriceHeader({
  symbol,
  initialPrice,
  initialChange,
  initialChangePercent,
  initialLastUpdated,
}: LivePriceHeaderProps) {
  const router = useRouter();
  const live = useLivePrice(symbol);
  const upperSymbol = symbol.toUpperCase();

  const price = live.price ?? initialPrice;
  const change = live.change ?? initialChange;
  const changePercent = live.changePercent ?? initialChangePercent;
  const lastUpdated = live.lastUpdated ?? initialLastUpdated;
  const isPositiveChange = (change ?? 0) >= 0;

  return (
    <div className="sticky top-14 z-20">
      <div className="glass-panel rounded-[1.75rem] p-6 relative overflow-hidden">
        <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-indigo-600/10 blur-[80px]" aria-hidden="true" />
        <div className="relative flex flex-col gap-4 md:flex-row md:items-center">
          <div className="flex items-center gap-4">
            <button
              onClick={() => router.back()}
              className="glass-btn flex h-9 w-9 items-center justify-center rounded-xl flex-shrink-0"
              aria-label="Go back"
            >
              <ArrowLeft className="h-4 w-4 text-white/60" />
            </button>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl bg-indigo-500/20 border border-indigo-500/30 text-sm font-black text-indigo-300">
                {upperSymbol[0]}
              </div>
              <h1 className="text-2xl font-black tracking-tighter text-white uppercase">{upperSymbol}</h1>
            </div>
          </div>
          <div className="flex items-baseline gap-3 md:ml-auto">
            <span className="text-2xl font-black text-white tracking-tight">
              {price != null ? `$${price.toFixed(2)}` : "—"}
            </span>
            {change != null && changePercent != null && (
              <span className={cn("text-sm font-bold", isPositiveChange ? "text-emerald-400" : "text-rose-400")}>
                {change >= 0 ? "+" : ""}{change.toFixed(2)} ({changePercent >= 0 ? "+" : ""}{changePercent.toFixed(2)}%)
              </span>
            )}
            {lastUpdated && (
              <span className="text-[10px] font-medium text-white/25 hidden md:inline">
                · {formatTimestamp(lastUpdated, "relative")}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
