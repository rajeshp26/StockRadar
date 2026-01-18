import { useState, useEffect, useCallback, useRef } from 'react';
import { useServices } from '@/shared/contexts/ServiceContext';
import { StockPriceInfo, WatchlistWithStocks } from '../types/watchlist.types';
import { useAuth } from '@/providers/auth-provider';
import { useToast } from '@/hooks/use-toast';

interface UseWatchlistOptions {
  /**
   * Initial watchlist data provided by parent component.
   * When provided, the hook skips its own initial fetch,
   * preventing the race condition with authentication.
   */
  initialWatchlist?: WatchlistWithStocks;
}

export function useWatchlist(options?: UseWatchlistOptions) {
  const [stocks, setStocks] = useState<StockPriceInfo[]>([]);
  const [isLoading, setIsLoading] = useState(!options?.initialWatchlist);
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const { watchlistService } = useServices();
  const { firebaseUser: user } = useAuth();
  const { toast } = useToast();

  // Track if we've initialized to prevent double-fetch
  const hasInitializedRef = useRef(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  /**
   * Fetch watchlist data from the backend.
   * Called on mount (unless initial data provided) and after mutations.
   */
  const fetchWatchlist = useCallback(async () => {
    if (!user) {
      console.log('[useWatchlist] No user, skipping fetch');
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      console.log('[useWatchlist] Fetching watchlist from service');
      const data = await watchlistService.getDefaultWatchlist();
      setStocks(data.stocks);
      setWatchlistId(data.watchlist_id);
      console.log('[useWatchlist] Watchlist fetched successfully:', {
        watchlistId: data.watchlist_id,
        stockCount: data.stocks.length,
      });
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('[useWatchlist] Failed to fetch watchlist:', error.message);
      setError(error);
      toast({
        title: 'Error',
        description: 'Failed to load watchlist.',
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  }, [user, watchlistService, toast]);

  /**
   * Initialize watchlist with data from parent (if provided)
   * or fetch from backend (if not provided).
   *
   * This solves the race condition:
   * - Parent fetches after auth is confirmed
   * - Parent passes data to this hook
   * - This hook uses provided data, skipping its own fetch
   */
  useEffect(() => {
    if (hasInitializedRef.current) return;

    if (options?.initialWatchlist) {
      // Use provided initial data
      console.log('[useWatchlist] Using initial watchlist data from parent');
      setWatchlistId(options.initialWatchlist.watchlist_id);
      // The initialWatchlist now includes stocks directly
      setStocks(options.initialWatchlist.stocks || []);
      setIsLoading(false);
    } else if (user) {
      // No initial data, fetch from backend
      console.log('[useWatchlist] No initial data, fetching from service');
      fetchWatchlist();
    }

    hasInitializedRef.current = true;
  }, [options?.initialWatchlist, user, fetchWatchlist]);

  /**
   * Add a new stock to the watchlist.
   */
  const addStock = async (
    symbol: string,
    targetBuy: number | null,
    targetSell: number | null
  ) => {
    if (!watchlistId) {
      console.warn('[useWatchlist] No watchlistId, cannot add stock');
      return;
    }

    try {
      console.log('[useWatchlist] Adding stock:', { symbol, targetBuy, targetSell });
      await watchlistService.addStock({
        watchlist_id: watchlistId,
        symbol,
        target_buy: targetBuy,
        target_sell: targetSell,
      });
      // Refresh watchlist to get updated data
      await fetchWatchlist();
      toast({ title: 'Stock Added' });
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('[useWatchlist] Failed to add stock:', error.message);
      toast({
        title: 'Error',
        description: 'Could not add stock.',
        variant: 'destructive',
      });
    }
  };

  /**
   * Update price targets for a stock.
   */
  const updateTargets = async (
    itemId: number,
    targetBuy: number | null,
    targetSell: number | null
  ) => {
    try {
      console.log('[useWatchlist] Updating targets:', { itemId, targetBuy, targetSell });
      await watchlistService.updateStockTargets({
        item_id: itemId,
        target_buy: targetBuy,
        target_sell: targetSell,
      });
      // Refresh watchlist to get updated data
      await fetchWatchlist();
      toast({ title: 'Targets Updated' });
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('[useWatchlist] Failed to update targets:', error.message);
      toast({
        title: 'Error',
        description: 'Could not update targets.',
        variant: 'destructive',
      });
    }
  };

  /**
   * Remove a stock from the watchlist.
   * Uses optimistic update to remove immediately from UI.
   */
  const removeStock = async (itemId: number) => {
    try {
      console.log('[useWatchlist] Removing stock:', { itemId });
      // Optimistic update: remove immediately from UI
      setStocks((prev) => prev.filter((s) => s.id !== itemId));
      await watchlistService.removeStock(itemId);
      toast({ title: 'Stock Removed' });
    } catch (err) {
      const error = err instanceof Error ? err : new Error(String(err));
      console.error('[useWatchlist] Failed to remove stock:', error.message);
      // On error, refresh to restore the removed stock
      await fetchWatchlist();
      toast({
        title: 'Error',
        description: 'Could not remove stock.',
        variant: 'destructive',
      });
    }
  };

  /**
   * Set up Server-Sent Events (SSE) for real-time stock price updates.
   * This is triggered after watchlistId is established.
   */
  useEffect(() => {
    if (!user || !watchlistId) {
      console.log('[useWatchlist] Skipping SSE setup. User:', !!user, 'WatchlistId:', watchlistId);
      return;
    }

    console.log('[useWatchlist] Setting up SSE stream for watchlist:', watchlistId);

    const setupStream = async () => {
      try {
        // Get a fresh token for the SSE URL
        const idToken = await user.getIdToken();
        const streamUrl = await watchlistService.getWatchlistStreamUrl(idToken);
        console.log('[useWatchlist] Connecting to SSE stream:', streamUrl);

        eventSourceRef.current = new EventSource(streamUrl);

        eventSourceRef.current.onmessage = (event) => {
          try {
            const update = JSON.parse(event.data);
            console.log('[useWatchlist] Received SSE update:', update);
            setStocks((prevStocks) =>
              prevStocks.map((stock) =>
                stock.symbol === update.symbol
                  ? {
                      ...stock,
                      price: update.price || stock.price,
                      ...update,
                    }
                  : stock
              )
            );
          } catch (err) {
            console.error('[useWatchlist] Error parsing SSE update:', err);
          }
        };

        eventSourceRef.current.onerror = (err) => {
          console.error('[useWatchlist] SSE Error:', err);
          eventSourceRef.current?.close();
          eventSourceRef.current = null;
          // Attempt to reconnect after delay
          setTimeout(() => {
            if (user && watchlistId) {
              console.log('[useWatchlist] Attempting SSE reconnection');
              setupStream();
            }
          }, 5000);
        };
      } catch (err) {
        console.error('[useWatchlist] Failed to setup SSE:', err);
      }
    };

    setupStream();

    return () => {
      if (eventSourceRef.current) {
        console.log('[useWatchlist] Closing SSE connection');
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [user, watchlistId, watchlistService]);

  return {
    stocks,
    isLoading,
    error,
    watchlistId,
    refresh: fetchWatchlist,
    addStock,
    updateTargets,
    removeStock,
  };
}