
'use client';

import type { Stock, WatchlistItem } from '@/lib/types';
import { useEffect, useState, useCallback, useMemo } from 'react';
import { StockCard } from './stock-card';
import { Button } from '../ui/button';
import { PlusCircle, TrendingUp, DollarSign, Target } from 'lucide-react';
import { AddStockDialog } from './add-stock-dialog';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '../auth/auth-provider';
import api from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { cn } from '@/lib/utils';

type AlertType = 'buy' | 'sell';
type TriggeredAlerts = {
  [stockId: string]: {
    [key in AlertType]?: boolean;
  };
};
type Notification = {
  id: string;
  title: string;
  description: string;
  timestamp: Date;
};

/**
 * The main component for displaying and managing the user's stock watchlist.
 * It handles fetching watchlist items, fetching real-time stock data from the backend,
 * and orchestrating add/remove operations.
 */
export function Watchlist() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [isAddDialogOpen, setAddDialogOpen] = useState(false);
  const { toast } = useToast();
  const { appUser, loading: isAuthLoading } = useAuth();
  const [isLoading, setIsLoading] = useState(true);
  const [watchlistItems, setWatchlistItems] = useState<any[]>([]);

  const [triggeredAlerts, setTriggeredAlerts] = useState<TriggeredAlerts>({});
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [filter, setFilter] = useState<'all' | 'buy' | 'sell'>('all');

  const watchlistId = appUser?.default_watchlist_id;

  const fetchWatchlist = useCallback(async () => {
    if (!watchlistId) {
      if (!isAuthLoading) setIsLoading(false);
      setStocks([]);
      setWatchlistItems([]);
      return;
    }
    setIsLoading(true);
    try {
      const response = await api.get(`/watchlists/${watchlistId}`);
      const { items, stocks: fetchedStocks } = response.data;
      setWatchlistItems(items || []);
      setStocks(fetchedStocks || []);
    } catch (error) {
      console.error('Failed to fetch watchlist:', error);
      toast({
        title: 'Error',
        description: 'Could not fetch your watchlist.',
        variant: 'destructive',
      });
      setStocks([]);
      setWatchlistItems([]);
    } finally {
      setIsLoading(false);
    }
  }, [watchlistId, toast, isAuthLoading]);

  const pollStockData = useCallback(async () => {
    if (!watchlistId || watchlistItems.length === 0) return;
    try {
      const response = await api.get(`/watchlists/${watchlistId}`);
      const { stocks: updatedStocks } = response.data;

      const newStocks: Stock[] = updatedStocks || [];
      setStocks(newStocks);
      
      const newTriggeredAlerts: TriggeredAlerts = { ...triggeredAlerts };
      const newNotifications: Notification[] = [];

      newStocks.forEach((stock) => {
        const hasBuyAlertBeenTriggered = triggeredAlerts[stock.id]?.buy;
        if (stock.targetBuy && stock.price <= stock.targetBuy && !hasBuyAlertBeenTriggered) {
          const notification: Notification = {
            id: `${stock.id}-buy-${Date.now()}`,
            title: 'Buy Alert!',
            description: `${stock.symbol} has reached your buy target of $${stock.targetBuy.toFixed(2)}. Current price: $${stock.price.toFixed(2)}`,
            timestamp: new Date(),
          };
          newNotifications.push(notification);
          if (!newTriggeredAlerts[stock.id]) newTriggeredAlerts[stock.id] = {};
          newTriggeredAlerts[stock.id].buy = true;
        }

        const hasSellAlertBeenTriggered = triggeredAlerts[stock.id]?.sell;
        if (stock.targetSell && stock.price >= stock.targetSell && !hasSellAlertBeenTriggered) {
          const notification: Notification = {
            id: `${stock.id}-sell-${Date.now()}`,
            title: 'Sell Alert!',
            description: `${stock.symbol} has reached your sell target of $${stock.targetSell.toFixed(2)}. Current price: $${stock.price.toFixed(2)}`,
            timestamp: new Date(),
          };
          newNotifications.push(notification);
if (!newTriggeredAlerts[stock.id]) newTriggeredAlerts[stock.id] = {};
          newTriggeredAlerts[stock.id].sell = true;
        }
      });

      if (newNotifications.length > 0) {
        newNotifications.forEach(n => toast({ title: n.title, description: n.description }));
        setNotifications(prev => [...prev, ...newNotifications]);
        setTriggeredAlerts(newTriggeredAlerts);
      }

    } catch (error) {
      console.error('Error polling stock data:', error);
    }
  }, [watchlistId, watchlistItems.length, toast, triggeredAlerts]);

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  useEffect(() => {
    const interval = setInterval(pollStockData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [pollStockData]);

  const handleAddStock = async (newStockData: Omit<WatchlistItem, 'id' | 'userId'>) => {
    if (!watchlistId) return;

    try {
      const response = await api.post('/watchlist-items', {
        watchlist_id: watchlistId,
        symbol: newStockData.symbol,
        target_buy: newStockData.targetBuy,
        target_sell: newStockData.targetSell,
      });

      const { stock_data, watchlist_item } = response.data;

      // Optimistically update UI
      setStocks(prev => [...prev, {
        ...stock_data,
        targetBuy: watchlist_item.target_buy,
        targetSell: watchlist_item.target_sell
      }]);
      setWatchlistItems(prev => [...prev, watchlist_item]);

      toast({
        title: 'Stock Added',
        description: `${stock_data.name} has been added to your watchlist.`,
      });
    } catch (error: any) {
      console.error('Error adding stock:', error);
      toast({
        title: 'Error Adding Stock',
        description: error.response?.data?.detail || 'Could not add the stock.',
        variant: 'destructive',
      });
    }
  };

  const handleRemoveStock = async (stockId: number) => {
    try {
      await api.delete(`/watchlist-items/${stockId}`);
      setStocks(prev => prev.filter(s => s.id !== stockId));
      toast({
        title: 'Stock Removed',
        description: 'The stock has been removed from your watchlist.',
      });
    } catch (error) {
      console.error('Error removing stock:', error);
      toast({
        title: 'Error',
        description: 'Could not remove the stock.',
        variant: 'destructive',
      });
    }
  };

  const buyTriggeredStocks = useMemo(() => stocks.filter(stock => stock.targetBuy && stock.price <= stock.targetBuy), [stocks]);
  const sellTriggeredStocks = useMemo(() => stocks.filter(stock => stock.targetSell && stock.price >= stock.targetSell), [stocks]);

  const filteredStocks = useMemo(() => {
    switch (filter) {
      case 'buy':
        return buyTriggeredStocks;
      case 'sell':
        return sellTriggeredStocks;
      default:
        return stocks;
    }
  }, [filter, stocks, buyTriggeredStocks, sellTriggeredStocks]);


  if (isLoading || isAuthLoading) {
    return (
      <div className="flex flex-1 items-start justify-center rounded-lg border border-dashed shadow-sm p-8">
        <div className="h-16 w-16 animate-spin rounded-full border-4 border-dashed border-primary"></div>
      </div>
    );
  }

  if (stocks.length === 0 && watchlistItems?.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center p-8">
        <TrendingUp className="h-16 w-16 text-muted-foreground" />
        <h3 className="text-2xl font-bold tracking-tight">
          Your watchlist is empty
        </h3>
        <p className="text-sm text-muted-foreground">
          Start tracking stocks by adding them to your watchlist.
        </p>
        <Button onClick={() => setAddDialogOpen(true)}>
          <PlusCircle className="mr-2 h-4 w-4" /> Add Stock
        </Button>
        <AddStockDialog
          open={isAddDialogOpen}
          onOpenChange={setAddDialogOpen}
          onAddStock={handleAddStock}
        />
      </div>
    );
  }

  return (
    <div className="w-full max-w-6xl mx-auto p-4 md:p-0">
       <div className="grid gap-4 md:grid-cols-3 lg:grid-cols-3 mb-6">
        <Card
            className={cn('cursor-pointer hover:bg-muted/50', filter === 'all' && 'bg-muted')}
            onClick={() => setFilter('all')}
          >
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">All Stocks</CardTitle>
            <Target className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stocks.length}</div>
            <p className="text-xs text-muted-foreground">
              Total stocks in your watchlist
            </p>
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
            <p className="text-xs text-muted-foreground">
              Stocks at or below your buy target
            </p>
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
            <p className="text-xs text-muted-foreground">
              Stocks at or above your sell target
            </p>
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
          <StockCard key={stock.id} stock={stock} onRemove={() => handleRemoveStock(stock.id)} />
        ))}
      </div>
       {filteredStocks.length === 0 && (
          <div className="col-span-1 md:col-span-2 lg:col-span-3 text-center text-muted-foreground py-10">
             {stocks.length > 0 && 'No stocks match the current filter.'}
          </div>
        )}
      <AddStockDialog
        open={isAddDialogOpen}
        onOpenChange={setAddDialogOpen}
        onAddStock={handleAddStock}
      />
    </div>
  );
}
