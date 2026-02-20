'use client';

import { useState, useMemo } from 'react';
import { StockCard } from './stock-card';
import { PlusCircle, TrendingUp, DollarSign, TrendingDown, RefreshCw } from 'lucide-react';
import { StockTargetDialog } from './add-stock-dialog';
import { cn } from '@/lib/utils';
import { useWatchlist as useWatchlistInternal } from '@/features/watchlists/hooks/useWatchlist';
import type {
  StockPriceInfo,
  WatchlistWithStocks as WatchlistType,
} from '@/features/watchlists/types/watchlist.types';

interface WatchlistProps {
  watchlist?: WatchlistType;
}

/* ── Skeleton ──────────────────────────────────────────────────── */
function WatchlistSkeleton() {
  return (
    <div className="w-full max-w-6xl mx-auto space-y-8 animate-fade-up">
      {/* Summary row skeleton */}
      <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="glass-panel p-6 space-y-3">
            <div className="flex items-center justify-between">
              <div className="h-2.5 w-20 rounded-full bg-white/10 glass-shimmer" />
              <div className="h-4 w-4 rounded-full bg-white/10 glass-shimmer" />
            </div>
            <div className="h-8 w-12 rounded-lg bg-white/10 glass-shimmer" />
          </div>
        ))}
      </div>

      {/* Header row skeleton */}
      <div className="flex justify-between items-center">
        <div className="h-5 w-36 rounded-full bg-white/10 glass-shimmer" />
        <div className="h-9 w-28 rounded-xl bg-white/10 glass-shimmer" />
      </div>

      {/* Card grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="glass-panel p-6 space-y-4">
            <div className="space-y-2">
              <div className="h-5 w-16 rounded-full bg-white/10 glass-shimmer" />
              <div className="h-3 w-28 rounded-full bg-white/10 glass-shimmer" />
            </div>
            <div className="h-8 w-24 rounded-lg bg-white/10 glass-shimmer" />
            <div className="h-3 w-32 rounded-full bg-white/10 glass-shimmer" />
            <div className="h-px bg-white/5" />
            <div className="h-8 w-full rounded-xl bg-white/10 glass-shimmer" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Summary stat card ────────────────────────────────────────── */
interface SummaryCardProps {
  label: string;
  count: number;
  icon: React.ReactNode;
  isActive: boolean;
  isLoading?: boolean;
  accentColor: 'white' | 'emerald' | 'rose';
  onClick: () => void;
}

function SummaryCard({
  label,
  count,
  icon,
  isActive,
  isLoading,
  accentColor,
  onClick,
}: SummaryCardProps) {
  const accentMap = {
    white:   'text-white',
    emerald: 'text-emerald-400',
    rose:    'text-rose-400',
  };

  return (
    <button
      onClick={onClick}
      className={cn(
        'glass-panel p-6 text-left w-full transition-all duration-200 group',
        'hover:border-white/15 active:scale-[0.98]',
        isActive && 'glow-indigo border-indigo-500/30',
      )}
    >
      <div className="flex items-center justify-between mb-4">
        <p className="glass-overline">{label}</p>
        <div
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-xl transition-colors',
            isActive ? 'bg-indigo-500/20 text-indigo-400' : 'bg-white/5 text-white/30 group-hover:bg-white/10 group-hover:text-white/50',
          )}
        >
          {icon}
        </div>
      </div>
      <div className="flex items-end justify-between">
        <span className={cn('text-3xl font-black tracking-tighter', accentMap[accentColor])}>
          {count}
        </span>
        {isLoading && (
          <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse-glow" />
        )}
      </div>
    </button>
  );
}

/* ── Main Watchlist ──────────────────────────────────────────── */
export function Watchlist({ watchlist }: WatchlistProps) {
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const [isEditDialogOpen, setEditDialogOpen] = useState(false);
  const [editingStock, setEditingStock] = useState<StockPriceInfo | null>(null);
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');

  const {
    stocks,
    isLoading,
    error,
    refresh,
    addStock,
    updateTargets,
    removeStock,
  } = watchlist
    ? useWatchlistInternal({ initialWatchlist: watchlist })
    : useWatchlistInternal();

  const isInitialLoading = isLoading && stocks.length === 0 && !error;

  const buyTriggeredStocks = useMemo(
    () =>
      stocks.filter(
        (stock) =>
          stock.targetBuy != null &&
          typeof (stock as any).price === 'number' &&
          (stock as any).price <= stock.targetBuy,
      ),
    [stocks],
  );

  const sellTriggeredStocks = useMemo(
    () =>
      stocks.filter(
        (stock) =>
          stock.targetSell != null &&
          typeof (stock as any).price === 'number' &&
          (stock as any).price >= stock.targetSell,
      ),
    [stocks],
  );

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case 'buy':  return buyTriggeredStocks;
      case 'sell': return sellTriggeredStocks;
      default:     return stocks;
    }
  }, [filter, stocks, buyTriggeredStocks, sellTriggeredStocks]);

  /* ── Skeleton state ───────────────────────────────────────── */
  if (isInitialLoading) return <WatchlistSkeleton />;

  /* ── Error state ──────────────────────────────────────────── */
  if (error) {
    return (
      <div className="w-full max-w-lg mx-auto animate-fade-up">
        <div className="glass-panel p-10 text-center space-y-6">
          <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-rose-500/10 border border-rose-500/20">
            <TrendingDown className="h-7 w-7 text-rose-400" />
          </div>
          <div>
            <h3 className="text-lg font-black text-white tracking-tight">
              Failed to load watchlist
            </h3>
            <p className="mt-2 text-sm text-white/40 leading-relaxed">{error.message}</p>
          </div>
          <button
            onClick={() => void refresh()}
            className="glass-btn-primary inline-flex items-center gap-2 px-6 py-3 text-xs font-black uppercase tracking-widest"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  /* ── Empty state ──────────────────────────────────────────── */
  if (!isLoading && stocks.length === 0) {
    return (
      <div className="w-full max-w-md mx-auto animate-fade-up">
        <div className="glass-panel p-16 flex flex-col items-center text-center space-y-6">
          {/* Icon */}
          <div className="relative">
            <div className="h-20 w-20 rounded-3xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
              <TrendingUp className="h-9 w-9 text-indigo-400" />
            </div>
            <div className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-indigo-500 flex items-center justify-center shadow-glow-indigo">
              <PlusCircle className="h-3 w-3 text-white" />
            </div>
          </div>

          <div>
            <h3 className="text-2xl font-black text-white tracking-tighter">
              Your watchlist is empty
            </h3>
            <p className="mt-2 text-sm text-white/40 leading-relaxed max-w-xs">
              Add your first stock to start tracking prices and setting targets.
            </p>
          </div>

          <button
            onClick={() => setAddDialogOpen(true)}
            className="glass-btn-primary inline-flex items-center gap-2 px-8 py-3.5 text-xs font-black uppercase tracking-widest rounded-2xl"
          >
            <PlusCircle className="h-4 w-4" />
            Add First Stock
          </button>
        </div>

        <StockTargetDialog
          open={isAddDialogOpen}
          onOpenChange={setAddDialogOpen}
          onSave={(data) => addStock(data.symbol, data.targetBuy, data.targetSell)}
        />
      </div>
    );
  }

  /* ── Title map ────────────────────────────────────────────── */
  const titleMap = {
    buy:  'Buy Alert Stocks',
    sell: 'Sell Alert Stocks',
    all:  'My Watchlist',
  };

  /* ── Normal render ────────────────────────────────────────── */
  return (
    <div className="w-full max-w-6xl mx-auto space-y-8 animate-fade-up">

      {/* ── Summary row ─────────────────────────────────────── */}
      <div className="grid gap-4 grid-cols-1 md:grid-cols-3">
        <SummaryCard
          label="All Stocks"
          count={stocks.length}
          icon={<TrendingUp className="h-4 w-4" />}
          isActive={filter === 'all'}
          isLoading={isLoading}
          accentColor="white"
          onClick={() => setFilter('all')}
        />
        <SummaryCard
          label="Buy Alerts"
          count={buyTriggeredStocks.length}
          icon={<DollarSign className="h-4 w-4" />}
          isActive={filter === 'buy'}
          accentColor="emerald"
          onClick={() => setFilter('buy')}
        />
        <SummaryCard
          label="Sell Alerts"
          count={sellTriggeredStocks.length}
          icon={<DollarSign className="h-4 w-4" />}
          isActive={filter === 'sell'}
          accentColor="rose"
          onClick={() => setFilter('sell')}
        />
      </div>

      {/* ── Section header ──────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-black text-white tracking-tight">
            {titleMap[filter]}
          </h2>
          <span className="glass-card px-2.5 py-0.5 text-[10px] font-black text-white/40 rounded-full">
            {filteredStocks.length}
          </span>
        </div>

        <button
          onClick={() => setAddDialogOpen(true)}
          className="glass-btn-primary inline-flex items-center gap-2 px-5 py-2.5 text-[10px] font-black uppercase tracking-widest rounded-xl"
        >
          <PlusCircle className="h-3.5 w-3.5" />
          Add Stock
        </button>
      </div>

      {/* ── Stock grid ──────────────────────────────────────── */}
      {filteredStocks.length === 0 ? (
        <div className="glass-panel p-12 flex flex-col items-center text-center space-y-3">
          <p className="text-sm font-bold text-white/30 uppercase tracking-widest">
            No {filter === 'buy' ? 'buy' : 'sell'} alerts triggered
          </p>
          <p className="text-xs text-white/20">
            Stocks will appear here when price crosses your target.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredStocks.map((stock) => (
            <StockCard
              key={stock.id}
              stock={stock as any}
              onRemove={() => removeStock(stock.id)}
              onEdit={(s) => {
                setEditingStock(s as any);
                setEditDialogOpen(true);
              }}
            />
          ))}
        </div>
      )}

      {/* ── Dialogs ─────────────────────────────────────────── */}
      <StockTargetDialog
        open={isAddDialogOpen}
        onOpenChange={setAddDialogOpen}
        onSave={(data) => addStock(data.symbol, data.targetBuy, data.targetSell)}
        mode="add"
      />
      <StockTargetDialog
        open={isEditDialogOpen}
        onOpenChange={setEditDialogOpen}
        onSave={(data) =>
          editingStock &&
          updateTargets(editingStock.id, data.targetBuy, data.targetSell)
        }
        mode="edit"
        initialData={
          editingStock
            ? {
                symbol:     editingStock.symbol,
                targetBuy:  editingStock.targetBuy,
                targetSell: editingStock.targetSell,
              }
            : undefined
        }
      />
    </div>
  );
}