'use client';

import type { Stock } from '@/lib/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { TrendingUp, TrendingDown, X, Pencil, Target as TargetIcon, Clock } from 'lucide-react';
import { format, isToday, isYesterday } from 'date-fns';
import { useRouter } from 'next/navigation';

interface StockCardProps {
  stock: Stock;
  onRemove: (stockId: number) => void;
  onEdit: (stock: Stock) => void;
}

export function StockCard({ stock, onRemove, onEdit }: StockCardProps) {
  const router = useRouter();
  const isPositiveChange = stock.change >= 0;

  // Buy Target Variance Calculation
  const getBuyVariance = () => {
    if (!stock.targetBuy) return null;
    const diff = stock.price - stock.targetBuy;
    const diffPercent = (diff / stock.targetBuy) * 100;
    const isTargetHit = diff <= 0;
    
    return {
      diff,
      diffPercent,
      isTargetHit
    };
  };

  const buyVariance = getBuyVariance();

  // Smart Timestamp Formatter
  const formatLastUpdated = (isoString?: string) => {
    if (!isoString) return null;
    try {
      const date = new Date(isoString);
      if (isToday(date)) {
        return format(date, 'h:mm a');
      } else if (isYesterday(date)) {
        return `Yesterday, ${format(date, 'h:mm a')}`;
      } else {
        return format(date, 'MMM d, h:mm a');
      }
    } catch (e) {
      return null;
    }
  };

  const lastUpdatedTime = formatLastUpdated(stock.lastUpdated);

  return (
    <Card
      className="relative overflow-hidden group cursor-pointer transition hover:bg-slate-50"
      onClick={() => router.push(`/analysis/${stock.symbol}`)}
    >
      <div className="absolute top-2 right-2 flex gap-1 z-10">
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => { e.stopPropagation(); onEdit(stock); }}
        >
          <Pencil className="h-3 w-3" />
          <span className="sr-only">Edit targets</span>
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-destructive hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={(e) => { e.stopPropagation(); onRemove(stock.id); }}
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Remove stock</span>
        </Button>
      </div>

      <CardHeader className="pb-2">
        <CardTitle className="text-xl font-bold flex items-center gap-2">
          {stock.symbol}
          {buyVariance?.isTargetHit && (
             <span className="bg-green-100 text-green-700 text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1 border border-green-200">
               <TargetIcon className="h-2 w-2" /> BUY HIT
             </span>
          )}
          {stock.targetSell && stock.price >= stock.targetSell && (
             <span className="bg-red-100 text-red-700 text-[10px] px-1.5 py-0.5 rounded-full flex items-center gap-1 border border-red-200">
               <TargetIcon className="h-2 w-2" /> SELL HIT
             </span>
          )}
        </CardTitle>
        <CardDescription className="truncate text-xs">{stock.name}</CardDescription>
      </CardHeader>

      <CardContent className="grid gap-2">
        <div>
          <div className="text-3xl font-bold tracking-tight">${stock.price.toFixed(2)}</div>
          <div className="flex items-center gap-2 flex-wrap">
            <div className={cn('flex items-center gap-1 text-sm font-medium', isPositiveChange ? 'text-green-500' : 'text-red-500')}>
              {isPositiveChange ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
              <span>
                {stock.change.toFixed(2)} ({stock.changePercent.toFixed(2)}%)
              </span>
            </div>
            {lastUpdatedTime && (
              <span className="text-[10px] text-muted-foreground/60 flex items-center gap-0.5 ml-auto whitespace-nowrap">
                <Clock className="h-2.5 w-2.5" /> As of {lastUpdatedTime}
              </span>
            )}
          </div>
        </div>

        {(stock.targetBuy || stock.targetSell) && (
          <div className="pt-3 border-t space-y-2 mt-1">
            <div className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground/60 mb-1">
              Targets & Variance
            </div>
            
            {stock.targetBuy && (
              <div className="flex justify-between items-center text-xs gap-2">
                <span className="text-muted-foreground whitespace-nowrap">
                  Buy at: <b className="text-foreground">${stock.targetBuy.toFixed(2)}</b>
                </span>
                {buyVariance && (
                  <span
                    className={cn(
                      "font-bold text-right",
                      buyVariance.isTargetHit ? "text-green-600" : "text-amber-600"
                    )}
                  >
                    {buyVariance.isTargetHit 
                      ? 'HIT' 
                      : `Gap: +$${buyVariance.diff.toFixed(2)} (+${buyVariance.diffPercent.toFixed(1)}%)`}
                  </span>
                )}
              </div>
            )}
            
            {stock.targetSell && (
              <div className="flex justify-between items-center text-xs gap-2">
                <span className="text-muted-foreground whitespace-nowrap">
                  Sell at: <b className="text-foreground">${stock.targetSell.toFixed(2)}</b>
                </span>
                {stock.price >= stock.targetSell ? (
                  <span className="text-red-600 font-bold text-xs text-right">HIT</span>
                ) : (
                  <span className="text-muted-foreground/70 font-medium text-right">
                    Gap: -${(stock.targetSell - stock.price).toFixed(2)} ({(((stock.targetSell - stock.price) / stock.price) * 100).toFixed(1)}%)
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Subtle intuitive hint */}
        <div className="text-right text-[11px] text-blue-600 font-medium mt-2 opacity-80">
          Analyze →
        </div>
      </CardContent>
    </Card>
  );
}