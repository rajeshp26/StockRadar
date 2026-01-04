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
    if (!user) return;
    
    try {
      setIsLoading(true);
      // No longer passing user.uid here
      const data = await watchlistService.getDefaultWatchlist();
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
  }, [user, watchlistService, toast]);

  const addStock = async (symbol: string, targetBuy: number | null, targetSell: number | null) => {
    if (!watchlistId) return;
    try {
      await watchlistService.addStock({
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
    try {
      await watchlistService.updateStockTargets({
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
    try {
      await watchlistService.removeStock(itemId);
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
    if (!user || !watchlistId) return;

    let eventSource: EventSource | null = null;

    const setupStream = async () => {
      // Get a fresh token for the SSE URL
      const idToken = await user.getIdToken();
      const streamUrl = await watchlistService.getWatchlistStreamUrl(idToken);
      
      eventSource = new EventSource(streamUrl);

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
        console.error('SSE Error:', err);
        eventSource?.close();
      };
    };

    setupStream();

    return () => {
      eventSource?.close();
    };
  }, [user, watchlistId, watchlistService]);

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
