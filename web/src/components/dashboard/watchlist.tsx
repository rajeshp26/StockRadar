'use client';

import { useState, useMemo } from 'react';
import { StockCard } from './stock-card';
import { Button } from '@/components/ui/button';
import { PlusCircle, TrendingUp, DollarSign } from 'lucide-react';
import { StockTargetDialog } from './add-stock-dialog';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';

// Feature-scoped hook (Option B)
import { useWatchlist as useWatchlistInternal } from '@/features/watchlists/hooks/useWatchlist';
import type { StockPriceInfo, WatchlistWithStocks as WatchlistType } from '@/features/watchlists/types/watchlist.types';

// Watchlist prop is now OPTIONAL (supports old “prefetched” usage and new “self-fetching” usage)
interface WatchlistProps {
  watchlist?: WatchlistType;
}

function WatchlistSkeleton() {
  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0 space-y-6">
      {/* Summary cards skeleton */}
      <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-4 w-4 rounded-full" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-12" />
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Title + button skeleton */}
      <div className="flex justify-between items-center">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-10 w-28" />
      </div>

      {/* Grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i}>
            <CardHeader>
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-4 w-24 mt-2" />
            </CardHeader>
            <CardContent className="space-y-3">
              <Skeleton className="h-6 w-24" />
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-10 w-full" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function Watchlist({ watchlist }: WatchlistProps) {
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const [isEditDialogOpen, setEditDialogOpen] = useState(false);
  const [editingStock, setEditingStock] = useState<StockPriceInfo | null>(null);
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');

  // If parent provides prefetched data, hook will skip initial fetch.
  // If not provided, hook will fetch (feature-scoped).
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

  // Phase 1: true initial shell loading state
  const isInitialLoading = isLoading && stocks.length === 0 && !error;

  const buyTriggeredStocks = useMemo(
    () => stocks.filter(stock =>
      stock.targetBuy != null &&
      typeof (stock as any).price === "number" &&
      (stock as any).price <= stock.targetBuy
    ),
    [stocks]
  );

  const sellTriggeredStocks = useMemo(() =>
      stocks.filter(stock =>
      stock.targetSell != null &&
      typeof (stock as any).price === "number" &&
      (stock as any).price >= stock.targetSell
    ),
    [stocks]
  );

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case 'buy': return buyTriggeredStocks;
      case 'sell': return sellTriggeredStocks;
      default: return stocks;
    }
  }, [filter, stocks, buyTriggeredStocks, sellTriggeredStocks]);

  // ---- Phase 1: Fast First Paint states ----

  // 1) Skeleton shell (renders instantly)
  if (isInitialLoading) {
    return <WatchlistSkeleton />;
  }

  // 2) Error state (non-blocking, with retry)
  if (error) {
    return (
      <div className="w-full max-w-3xl mx-auto p-4">
        <div className="bg-red-50 border border-red-200 rounded p-4">
          <h3 className="font-semibold text-red-900">Error</h3>
          <p className="text-sm text-red-700 mt-2">{error.message}</p>
          <Button className="mt-4" onClick={() => void refresh()}>
            Retry
          </Button>
        </div>
      </div>
    );
  }

  // 3) Empty state (only AFTER initial load completed)
  if (!isLoading && stocks.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
        <TrendingUp className="h-16 w-16 text-muted-foreground" />
        <h3 className="text-2xl font-bold tracking-tight">Your watchlist is empty</h3>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
        <StockTargetDialog
          open={isAddDialogOpen}
          onOpenChange={setAddDialogOpen}
          onSave={(data) => addStock(data.symbol, data.targetBuy, data.targetSell)}
        />
      </div>
    );
  }

  // ---- Normal render ----
  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0">
      <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-3 mb-6">
        <Card
          className={cn('cursor-pointer hover:bg-muted/50', filter === 'all' && 'bg-muted')}
          onClick={() => setFilter('all')}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">All Stocks</CardTitle>
            <div className={cn("h-2 w-2 rounded-full bg-green-500", { "animate-pulse": isLoading })} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stocks.length}</div>
          </CardContent>
        </Card>

        <Card
          className={cn('cursor-pointer hover:bg-muted/50', filter === 'buy' && 'bg-muted')}
          onClick={() => setFilter('buy')}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Buy Alerts</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{buyTriggeredStocks.length}</div>
          </CardContent>
        </Card>

        <Card
          className={cn('cursor-pointer hover:bg-muted/50', filter === 'sell' && 'bg-muted')}
          onClick={() => setFilter('sell')}
        >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Sell Alerts</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{sellTriggeredStocks.length}</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-between items-center mb-4">
        <h2 className="text-xl font-semibold">
          {filter === 'buy' && 'Buy Alert Stocks'}
          {filter === 'sell' && 'Sell Alert Stocks'}
          {filter === 'all' && 'My Watchlist'}
        </h2>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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

      <StockTargetDialog
        open={isAddDialogOpen}
        onOpenChange={setAddDialogOpen}
        onSave={(data) => addStock(data.symbol, data.targetBuy, data.targetSell)}
        mode="add"
      />

      <StockTargetDialog
        open={isEditDialogOpen}
        onOpenChange={setEditDialogOpen}
        onSave={(data) => editingStock && updateTargets(editingStock.id, data.targetBuy, data.targetSell)}
        mode="edit"
        initialData={
          editingStock
            ? {
                symbol: editingStock.symbol,
                targetBuy: editingStock.targetBuy,
                targetSell: editingStock.targetSell,
              }
            : undefined
        }
      />
    </div>
  );
}
``