import { useState, useEffect, useCallback } from 'react';
import { useServices } from '@/shared/contexts/ServiceContext';
import { StockPriceInfo } from '../types/watchlist.types';
import { useAuth } from '@/components/auth/auth-provider';
import { useToast } from '@/hooks/use-toast';

export function useWatchlist() {
  const [stocks, setStocks] = useState<StockPriceInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  
  const { watchlistService } = useServices();
  const { user } = useAuth();
  const { toast } = useToast();

  const fetchWatchlist = useCallback(async () => {
    if (!user?.uid) return;
    
    try {
      setIsLoading(true);
      const data = await watchlistService.getDefaultWatchlist(user.uid);
      setStocks(data.stocks);
      setWatchlistId(data.watchlist_id);
    } catch (error) {
      console.error('Failed to fetch watchlist:', error);
      toast({
        title: 'Error',
        description: 'Failed to load watchlist.',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  }, [user?.uid, watchlistService, toast]);

  const addStock = async (symbol: string, targetBuy: number | null, targetSell: number | null) => {
    if (!user?.uid || !watchlistId) return;
    try {
      await watchlistService.addStock({
        firebase_uid: user.uid,
        watchlist_id: watchlistId,
        symbol,
        target_buy: targetBuy,
        target_sell: targetSell,
      });
      await fetchWatchlist();
      toast({ title: 'Stock Added' });
    } catch (error) {
      toast({ title: 'Error', description: 'Could not add stock.', variant: 'destructive' });
    }
  };

  const updateTargets = async (itemId: number, targetBuy: number | null, targetSell: number | null) => {
    if (!user?.uid) return;
    try {
      await watchlistService.updateStockTargets({
        firebase_uid: user.uid,
        item_id: itemId,
        target_buy: targetBuy,
        target_sell: targetSell,
      });
      await fetchWatchlist();
      toast({ title: 'Targets Updated' });
    } catch (error) {
      toast({ title: 'Error', description: 'Could not update targets.', variant: 'destructive' });
    }
  };

  const removeStock = async (itemId: number) => {
    if (!user?.uid) return;
    try {
      await watchlistService.removeStock(user.uid, itemId);
      setStocks(prev => prev.filter(s => s.id !== itemId));
      toast({ title: 'Stock Removed' });
    } catch (error) {
      toast({ title: 'Error', description: 'Could not remove stock.', variant: 'destructive' });
    }
  };

  useEffect(() => {
    fetchWatchlist();
  }, [fetchWatchlist]);

  // Real-time updates via SSE
  useEffect(() => {
    if (!user?.uid || !watchlistId) return;

    const streamUrl = watchlistService.getWatchlistStreamUrl(user.uid);
    const eventSource = new EventSource(streamUrl);

    eventSource.onmessage = (event) => {
      try {
        const update = JSON.parse(event.data);
        setStocks((prevStocks) =>
          prevStocks.map((stock) =>
            stock.symbol === update.symbol
              ? { ...stock, ...update }
              : stock
          )
        );
      } catch (err) {
        console.error('Error parsing SSE update:', err);
      }
    };

    eventSource.onerror = (err) => {
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [user?.uid, watchlistId, watchlistService]);

  return {
    stocks,
    isLoading,
    watchlistId,
    refresh: fetchWatchlist,
    addStock,
    updateTargets,
    removeStock,
  };
}
