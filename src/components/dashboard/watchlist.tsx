
'use client';

import type { Stock, WatchlistItem } from '@/lib/types';
import { useEffect, useState, useCallback, useMemo } from 'react';
import { StockCard } from './stock-card';
import { Button } from '../ui/button';
import { PlusCircle, TrendingUp, DollarSign, Target } from 'lucide-react';
import { StockTargetDialog } from './add-stock-dialog'; // Renamed import
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '../auth/auth-provider';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { cn } from '@/lib/utils';

export function Watchlist() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const [isEditDialogOpen, setEditDialogOpen] = useState(false);
  const [editingStock, setEditingStock] = useState<Stock | null>(null);

  const { toast } = useToast();
  const { user, appUser, loading: isAuthLoading } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [watchlistItems, setWatchlistItems] = useState<any[]>([]);
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');
  const [isLive, setIsLive] = useState(false);

  const watchlistId = appUser?.default_watchlist_id;
  const firebase_uid = user?.uid;

  const fetchWatchlist = useCallback(async () => {
    if (!firebase_uid) {
      if (!isAuthLoading) setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const response = await api.post(`/watchlists/default-with-items`, {
         firebase_uid: firebase_uid,
      });
      const { items, stocks: fetchedStocks } = response.data;
      setWatchlistItems(items || []);
      setStocks(fetchedStocks || []);
    } catch (error) {
      console.error('Failed to fetch watchlist:', error);
      toast({ title: 'Error', description: 'Could not fetch watchlist.', variant: 'destructive' });
    } finally {
      setIsLoading(false);
    }
  }, [firebase_uid, toast, isAuthLoading]);

  // Real-time Subscription (SSE)
  useEffect(() => {
    if (!firebase_uid || isLoading) return;
    let eventSource: EventSource | null = null;
    let reconnectTimeout: NodeJS.Timeout;

    const connect = () => {
      const url = `/api/proxy/watchlists/stream?firebase_uid=${firebase_uid}`;
      eventSource = new EventSource(url);
      eventSource.onopen = () => setIsLive(true);
      eventSource.onmessage = (event) => {
        try {
          const update = JSON.parse(event.data);
          setStocks((currentStocks) => 
            currentStocks.map((s) => 
              s.symbol === update.symbol 
                ? { ...s, price: update.price, change: update.change, changePercent: update.changePercent } 
                : s
            )
          );
        } catch (e) {}
      };
      eventSource.onerror = () => {
        setIsLive(false);
        eventSource?.close();
        reconnectTimeout = setTimeout(connect, 5000);
      };
    };
    connect();
    return () => {
      eventSource?.close();
      clearTimeout(reconnectTimeout);
    };
  }, [firebase_uid, isLoading]);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  const handleAddStock = async (data: { symbol: string; targetBuy: number | null; targetSell: number | null }) => {
    if (!watchlistId || !firebase_uid) return;
    try {
      const response = await api.post('/watchlist-items', {
        firebase_uid: firebase_uid,
        watchlist_id: watchlistId,
        symbol: data.symbol,
        target_buy: data.targetBuy,
        target_sell: data.targetSell,
      });
      const { stock_data, watchlist_item } = response.data;
      setStocks(prev => [...prev, {
        ...stock_data,
        targetBuy: watchlist_item.target_buy,
        targetSell: watchlist_item.target_sell
      }]);
      toast({ title: 'Stock Added' });
    } catch (error: any) {
      toast({ title: 'Error', description: 'Could not add stock.', variant: 'destructive' });
    }
  };

  const handleUpdateStock = async (data: { targetBuy: number | null; targetSell: number | null }) => {
    if (!editingStock || !firebase_uid) return;
    try {
      const response = await api.patch(`/watchlist-items/${editingStock.id}`, {
        firebase_uid: firebase_uid,
        target_buy: data.targetBuy,
        target_sell: data.targetSell,
      });
      
      const updatedItem = response.data;
      setStocks(prev => prev.map(s => 
        s.id === editingStock.id 
          ? { ...s, targetBuy: updatedItem.target_buy, targetSell: updatedItem.target_sell } 
          : s
      ));
      
      toast({ title: 'Targets Updated' });
    } catch (error: any) {
      toast({ title: 'Error', description: 'Could not update targets.', variant: 'destructive' });
    }
  };

  const handleRemoveStock = async (stockId: number) => {
     if (!firebase_uid) return;
    try {
      await api.post(`/watchlist-items/delete`, { 
        firebase_uid: firebase_uid,
        item_id: stockId 
      });
      setStocks(prev => prev.filter(s => s.id !== stockId));
      toast({ title: 'Stock Removed' });
    } catch (error) {
      toast({ title: 'Error', variant: 'destructive' });
    }
  };

  const buyTriggeredStocks = useMemo(() => stocks.filter(stock => stock.targetBuy && stock.price <= stock.targetBuy), [stocks]);
  const sellTriggeredStocks = useMemo(() => stocks.filter(stock => stock.targetSell && stock.price >= stock.targetSell), [stocks]);

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case 'buy': return buyTriggeredStocks;
      case 'sell': return sellTriggeredStocks;
      default: return stocks;
    }
  }, [filter, stocks, buyTriggeredStocks, sellTriggeredStocks]);

  if (isLoading || isAuthLoading) {
    return (
      <div className="flex flex-1 items-start justify-center p-8">
        <div className="h-16 w-16 animate-spin rounded-full border-4 border-dashed border-primary"></div>
      </div>
    );
  }

  if (stocks.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
        <TrendingUp className="h-16 w-16 text-muted-foreground" />
        <h3 className="text-2xl font-bold tracking-tight">Your watchlist is empty</h3>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
        <StockTargetDialog open={isAddDialogOpen} onOpenChange={setAddDialogOpen} onSave={handleAddStock} />
      </div>
    );
  }

  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0">
       <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-3 mb-6">
        <Card className={cn('cursor-pointer hover:bg-muted/50', filter === 'all' && 'bg-muted')} onClick={() => setFilter('all')}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">All Stocks</CardTitle>
            <div className={cn("h-2 w-2 rounded-full", isLive ? "bg-green-500 animate-pulse" : "bg-gray-300")} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stocks.length}</div>
          </CardContent>
        </Card>
        <Card className={cn('cursor-pointer hover:bg-muted/50', filter === 'buy' && 'bg-muted')} onClick={() => setFilter('buy')}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Buy Alerts</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{buyTriggeredStocks.length}</div>
          </CardContent>
        </Card>
        <Card className={cn('cursor-pointer hover:bg-muted/50', filter === 'sell' && 'bg-muted')} onClick={() => setFilter('sell')}>
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
            stock={stock} 
            onRemove={() => handleRemoveStock(stock.id)} 
            onEdit={(s) => {
              setEditingStock(s);
              setEditDialogOpen(true);
            }}
          />
        ))}
      </div>
      
      {/* Add Dialog */}
      <StockTargetDialog 
        open={isAddDialogOpen} 
        onOpenChange={setAddDialogOpen} 
        onSave={handleAddStock} 
        mode="add"
      />
      
      {/* Edit Dialog */}
      <StockTargetDialog 
        open={isEditDialogOpen} 
        onOpenChange={setEditDialogOpen} 
        onSave={handleUpdateStock} 
        mode="edit"
        initialData={editingStock ? {
          symbol: editingStock.symbol,
          targetBuy: editingStock.targetBuy,
          targetSell: editingStock.targetSell
        } : undefined}
      />
    </div>
  );
}
