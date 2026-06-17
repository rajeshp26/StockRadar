"use client";

import { useMemo } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { ArrowRight, Edit2, Trash2 } from "lucide-react";
import type { StockPriceInfo } from "@/features/watchlists/types/watchlist.types";
import { usePriceData } from "@/hooks/usePriceData";

interface StockListRowProps {
  stock:        StockPriceInfo;
  onEdit:       (stock: StockPriceInfo) => void;
  onRemove:     (id: number) => void;
}

const AVATAR_COLORS = [
  "from-indigo-600/80 to-indigo-800/60 border-indigo-500/30",
  "from-violet-600/80 to-violet-800/60 border-violet-500/30",
  "from-sky-600/80    to-sky-800/60    border-sky-500/30",
  "from-emerald-600/80 to-emerald-800/60 border-emerald-500/30",
  "from-rose-600/80   to-rose-800/60   border-rose-500/30",
  "from-amber-600/80  to-amber-800/60  border-amber-500/30",
] as const;

export function StockListRow({ stock, onEdit, onRemove }: StockListRowProps) {
  const avatarColor = AVATAR_COLORS[stock.symbol.charCodeAt(0) % AVATAR_COLORS.length];

  /* ── Live price from shared cache (written by GlobalSSEProvider) ────────── */
  const priceData  = usePriceData(stock.symbol);
  const isPositive = (priceData?.change ?? 0) >= 0;
  const changeColor = isPositive ? "text-emerald-400" : "text-rose-400";

  const buyVariance = useMemo(() => {
    if (stock.targetBuy == null || priceData?.price == null) return null;
    const gap = ((priceData.price - stock.targetBuy) / stock.targetBuy) * 100;
    return { gap, isTargetHit: priceData.price <= stock.targetBuy };
  }, [priceData?.price, stock.targetBuy]);

  const sellVariance = useMemo(() => {
    if (stock.targetSell == null || priceData?.price == null) return null;
    const gap = ((priceData.price - stock.targetSell) / stock.targetSell) * 100;
    return { gap, isTargetHit: priceData.price >= stock.targetSell };
  }, [priceData?.price, stock.targetSell]);

  const hasBuyAlert  = buyVariance?.isTargetHit;
  const hasSellAlert = sellVariance?.isTargetHit;

  return (
    <div
      className={cn(
        "group glass-card rounded-xl px-4 py-3",
        "flex items-center gap-3 transition-all",
        hasBuyAlert  && "border-emerald-500/30 shadow-[0_0_12px_rgba(52,211,153,0.12)]",
        hasSellAlert && "border-rose-500/30    shadow-[0_0_12px_rgba(251,113,133,0.12)]",
      )}
    >
      {/* Avatar */}
      <div className={cn(
        "h-8 w-8 flex-shrink-0 flex items-center justify-center",
        "rounded-xl bg-gradient-to-br border text-xs font-black text-white",
        avatarColor,
      )}>
        {stock.symbol[0]}
      </div>

      {/* Symbol + Name */}
      <div className="w-32 flex-shrink-0 min-w-0">
        <p className="text-sm font-black text-white truncate">{stock.symbol}</p>
        <p className="text-[10px] text-white/30 truncate">{stock.name}</p>
      </div>

      {/* Price */}
      <div className="w-24 flex-shrink-0 text-right hidden sm:block">
        <p className="text-sm font-black text-white tabular-nums">
          {priceData?.price != null ? `$${priceData.price.toFixed(2)}` : "—"}
        </p>
      </div>

      {/* Change */}
      <div className="w-24 flex-shrink-0 text-right hidden md:block">
        {priceData?.changePercent != null ? (
          <span className={cn("text-xs font-bold tabular-nums", changeColor)}>
            {isPositive ? "+" : ""}{priceData.changePercent.toFixed(2)}%
          </span>
        ) : (
          <span className="text-xs text-white/20">—</span>
        )}
      </div>

      {/* Buy target */}
      <div className="flex-1 min-w-0 hidden lg:flex items-center gap-2">
        {buyVariance != null ? (
          <div className="flex items-center gap-1.5">
            <span className={cn(
              "px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest",
              buyVariance.isTargetHit
                ? "bg-emerald-500/15 border border-emerald-500/25 text-emerald-400"
                : "bg-white/5 border border-white/8 text-white/30",
            )}>
              Buy
            </span>
            <span className={cn(
              "text-[10px] font-bold tabular-nums",
              buyVariance.isTargetHit ? "text-emerald-400" : "text-white/30",
            )}>
              ${stock.targetBuy?.toFixed(2)}
              {buyVariance.gap != null && (
                <span className="ml-1">
                  ({buyVariance.gap >= 0 ? "+" : ""}{buyVariance.gap.toFixed(1)}%)
                </span>
              )}
            </span>
          </div>
        ) : (
          <span className="text-[10px] text-white/15">No buy target</span>
        )}
      </div>

      {/* Sell target */}
      <div className="flex-1 min-w-0 hidden xl:flex items-center gap-2">
        {sellVariance != null ? (
          <div className="flex items-center gap-1.5">
            <span className={cn(
              "px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-widest",
              sellVariance.isTargetHit
                ? "bg-rose-500/15 border border-rose-500/25 text-rose-400"
                : "bg-white/5 border border-white/8 text-white/30",
            )}>
              Sell
            </span>
            <span className={cn(
              "text-[10px] font-bold tabular-nums",
              sellVariance.isTargetHit ? "text-rose-400" : "text-white/30",
            )}>
              ${stock.targetSell?.toFixed(2)}
            </span>
          </div>
        ) : (
          <span className="text-[10px] text-white/15">No sell target</span>
        )}
      </div>

      {/* Actions */}
      <div className="flex-shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={() => onEdit(stock)}
          className="h-7 w-7 flex items-center justify-center rounded-lg glass-card text-white/30 hover:text-white transition-colors"
          aria-label={`Edit ${stock.symbol}`}
        >
          <Edit2 className="h-3 w-3" />
        </button>
        <button
          onClick={() => onRemove(stock.id)}
          className="h-7 w-7 flex items-center justify-center rounded-lg glass-card text-white/30 hover:text-rose-400 transition-colors"
          aria-label={`Remove ${stock.symbol}`}
        >
          <Trash2 className="h-3 w-3" />
        </button>
        <Link
          href={`/analysis/${stock.symbol}`}
          prefetch={true}
          className="h-7 px-2 flex items-center gap-1 rounded-lg glass-card text-white/30 hover:text-indigo-400 transition-colors"
          aria-label={`Analyse ${stock.symbol}`}
        >
          <span className="text-[10px] font-black uppercase tracking-widest">Analyse</span>
          <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}