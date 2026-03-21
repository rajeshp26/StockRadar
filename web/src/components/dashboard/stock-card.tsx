'use client';

import type { Stock } from '@/lib/types';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, X, Pencil, Target as TargetIcon, Clock, ArrowRight } from 'lucide-react';
import { useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { usePriceData } from '@/hooks/usePriceData';
import { prefetchAllValuations } from '@/features/analysis/utils/prefetch-valuations';
import { formatTimestamp } from '@/lib/time';

interface StockCardProps {
  stock: Stock;
  onRemove: (stockId: number) => void;
  onEdit: (stock: Stock) => void;
}

export function StockCard({ stock, onRemove, onEdit }: StockCardProps) {
  const router = useRouter();
  const queryClient = useQueryClient();

  /* ── Live price from shared cache (written by GlobalSSEProvider) ────────── */
  const priceData        = usePriceData(stock.symbol);
  const price            = priceData?.price         ?? null;
  const change           = priceData?.change        ?? null;
  const changePercent    = priceData?.changePercent ?? null;
  const isPositiveChange = (change ?? 0) >= 0;

  /* ── Hover prefetch — warms analysis cache 150 ms before click ─────────── */
  const prefetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handlePointerEnter = useCallback(() => {
    prefetchTimer.current = setTimeout(() => {
      prefetchAllValuations(stock.symbol, queryClient);
    }, 150);
  }, [stock.symbol, queryClient]);
  const handlePointerLeave = useCallback(() => {
    if (prefetchTimer.current) {
      clearTimeout(prefetchTimer.current);
      prefetchTimer.current = null;
    }
  }, []);

  

  const getBuyVariance = () => {
    if (!stock.targetBuy || price == null) return null;
    const diff        = price - stock.targetBuy;
    const diffPercent = (diff / stock.targetBuy) * 100;
    const isTargetHit = diff <= 0;
    return { diff, diffPercent, isTargetHit };
  };
  const buyVariance = getBuyVariance();

  const lastUpdatedTime = formatTimestamp(priceData?.lastUpdated ?? null, "relative");
  const sellHit = stock.targetSell != null && price != null && price >= stock.targetSell;

  /* ── Letter avatar color (deterministic by ticker) ─────── */
  const avatarColors = [
    'bg-indigo-500/20 text-indigo-300 ring-indigo-500/30',
    'bg-violet-500/20 text-violet-300 ring-violet-500/30',
    'bg-emerald-500/20 text-emerald-300 ring-emerald-500/30',
    'bg-amber-500/20  text-amber-300  ring-amber-500/30',
    'bg-rose-500/20   text-rose-300   ring-rose-500/30',
    'bg-sky-500/20    text-sky-300    ring-sky-500/30',
  ];
  const avatarClass = avatarColors[stock.symbol.charCodeAt(0) % avatarColors.length];

  return (
    <div
      className={cn(
        'glass-panel group relative cursor-pointer',
        'p-6 flex flex-col gap-4',
        'hover:border-white/15 hover:-translate-y-0.5',
        'transition-all duration-200',
        // Alert glow rings
        buyVariance?.isTargetHit && 'glow-emerald border-emerald-500/25',
        sellHit                   && 'glow-rose    border-rose-500/25',
      )}
      onClick={() => router.push(`/analysis/${stock.symbol}`)}
      onPointerEnter={handlePointerEnter}
      onPointerLeave={handlePointerLeave}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && router.push(`/analysis/${stock.symbol}`)}
      aria-label={`Analyze ${stock.symbol}`}
    >

      {/* ── Action buttons (visible on hover) ─────────────── */}
      <div className="absolute right-4 top-4 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-10">
        <button
          className="glass-card flex h-7 w-7 items-center justify-center rounded-xl text-white/40 hover:text-white transition-colors"
          onClick={(e) => { e.stopPropagation(); onEdit(stock); }}
          aria-label="Edit targets"
        >
          <Pencil className="h-3 w-3" />
        </button>
        <button
          className="glass-card flex h-7 w-7 items-center justify-center rounded-xl text-white/40 hover:text-rose-400 transition-colors"
          onClick={(e) => { e.stopPropagation(); onRemove(stock.id); }}
          aria-label="Remove stock"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* ── Header: avatar + ticker + name ────────────────── */}
      <div className="flex items-center gap-3 pr-16">
        <div
          className={cn(
            'flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-2xl ring-1 text-sm font-black',
            avatarClass,
          )}
          aria-hidden="true"
        >
          {stock.symbol[0]}
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-base font-black text-white tracking-tight">
              {stock.symbol}
            </span>
            {/* Alert badges */}
            {buyVariance?.isTargetHit && (
              <span className="glass-badge-buy">
                <TargetIcon className="h-2.5 w-2.5 mr-1" />
                Buy Hit
              </span>
            )}
            {sellHit && (
              <span className="glass-badge-sell">
                <TargetIcon className="h-2.5 w-2.5 mr-1" />
                Sell Hit
              </span>
            )}
          </div>
          <p className="text-xs text-white/35 truncate mt-0.5">{(stock as any).name}</p>
        </div>
      </div>

      {/* ── Price block ───────────────────────────────────── */}
      <div>
        <div className="text-3xl font-black tracking-tighter text-white">
          {price == null ? (
            <span className="text-white/20">—</span>
          ) : (
            `$${price.toFixed(2)}`
          )}
        </div>

        <div className="mt-1 flex items-center justify-between gap-2 flex-wrap">
          {change != null && changePercent != null ? (
            <div
              className={cn(
                'flex items-center gap-1 text-xs font-bold',
                isPositiveChange ? 'text-emerald-400' : 'text-rose-400',
              )}
            >
              {isPositiveChange
                ? <TrendingUp className="h-3.5 w-3.5" />
                : <TrendingDown className="h-3.5 w-3.5" />
              }
              <span>
                {isPositiveChange ? '+' : ''}{change.toFixed(2)} ({changePercent.toFixed(2)}%)
              </span>
            </div>
          ) : (
            <span className="text-[10px] text-white/25 font-medium">Price updating…</span>
          )}

          {lastUpdatedTime && (
            <span className="flex items-center gap-1 text-[9px] text-white/20 font-medium">
              <Clock className="h-2.5 w-2.5" />
              {lastUpdatedTime}
            </span>
          )}
        </div>
      </div>

      {/* ── Targets & variance ────────────────────────────── */}
      {(stock.targetBuy || stock.targetSell) && (
        <div className="border-t border-white/5 pt-4 space-y-2.5">
          <p className="glass-overline mb-3">Targets &amp; Variance</p>

          {stock.targetBuy && (
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-white/35 whitespace-nowrap">
                Buy at{' '}
                <span className="font-bold text-white/60">
                  ${stock.targetBuy.toFixed(2)}
                </span>
              </span>
              {buyVariance ? (
                <span
                  className={cn(
                    'font-bold text-right',
                    buyVariance.isTargetHit ? 'text-emerald-400' : 'text-amber-400',
                  )}
                >
                  {buyVariance.isTargetHit
                    ? '✓ HIT'
                    : `+$${buyVariance.diff.toFixed(2)} (${buyVariance.diffPercent.toFixed(1)}%)`}
                </span>
              ) : (
                <span className="text-white/20">—</span>
              )}
            </div>
          )}

          {stock.targetSell && (
            <div className="flex items-center justify-between gap-3 text-xs">
              <span className="text-white/35 whitespace-nowrap">
                Sell at{' '}
                <span className="font-bold text-white/60">
                  ${stock.targetSell.toFixed(2)}
                </span>
              </span>
              {price == null ? (
                <span className="text-white/20">—</span>
              ) : sellHit ? (
                <span className="font-bold text-rose-400">✓ HIT</span>
              ) : (
                <span className="text-white/35 font-medium text-right">
                  -${(stock.targetSell - price).toFixed(2)} (
                  {(((stock.targetSell - price) / price) * 100).toFixed(1)}%)
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Footer CTA ────────────────────────────────────── */}
      <div className="mt-auto flex items-center justify-end gap-1 text-[10px] font-black uppercase tracking-widest text-indigo-400/60 group-hover:text-indigo-400 transition-colors">
        Analyze
        <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-0.5" />
      </div>

    </div>
  );
}