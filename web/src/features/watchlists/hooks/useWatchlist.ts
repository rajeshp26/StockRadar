import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useServices } from "@/shared/contexts/ServiceContext";
import { StockPriceInfo, WatchlistWithStocks } from "../types/watchlist.types";
import { useAuth } from "@/providers/auth-provider";
import { useToast } from "@/hooks/use-toast";

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

  // Track if we've initialized to prevent double-fetch (but do not burn init before auth is ready)
  const hasInitializedRef = useRef(false);

  // SSE
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /**
   * Fetch watchlist data from the backend.
   * Called after auth is confirmed and after mutations.
   */
  const fetchWatchlist = useCallback(async () => {
    if (!user) {
      console.log("[useWatchlist] No user, skipping fetch");
      return;
    }

    try {
      setIsLoading(true);
      setError(null);

      console.log("[useWatchlist] Fetching watchlist from service");
      const data = await watchlistService.getDefaultWatchlist();

      setStocks(data.stocks);
      setWatchlistId(data.watchlist_id);

      console.log("[useWatchlist] Watchlist fetched successfully:", {
        watchlistId: data.watchlist_id,
        stockCount: data.stocks.length,
      });
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      console.error("[useWatchlist] Failed to fetch watchlist:", e.message);
      setError(e);
      toast({
        title: "Error",
        description: "Failed to load watchlist.",
        variant: "destructive",
      });
    } finally {
      setIsLoading(false);
    }
  }, [user, watchlistService, toast]);

  /**
   * Initialize watchlist:
   * - If initialWatchlist provided, use it.
   * - Otherwise, wait for `user` to exist, then fetch.
   *
   * ✅ Fix: do NOT set hasInitializedRef until we actually initialize.
   * This prevents the permanent "watchlistId stays null" bug when mounted before auth is ready.
   */
  useEffect(() => {
    if (hasInitializedRef.current) return;

    if (options?.initialWatchlist) {
      console.log("[useWatchlist] Using initial watchlist data from parent");
      setWatchlistId(options.initialWatchlist.watchlist_id);
      setStocks(options.initialWatchlist.stocks || []);
      setIsLoading(false);
      hasInitializedRef.current = true;
      return;
    }

    // ✅ Wait for auth to be available
    if (!user) return;

    console.log("[useWatchlist] No initial data, fetching from service");
    void (async () => {
      await fetchWatchlist();
      hasInitializedRef.current = true;
    })();
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
      console.warn("[useWatchlist] No watchlistId, cannot add stock");
      return;
    }

    try {
      console.log("[useWatchlist] Adding stock:", { symbol, targetBuy, targetSell });
      await watchlistService.addStock({
        watchlist_id: watchlistId,
        symbol,
        target_buy: targetBuy,
        target_sell: targetSell,
      });

      // Refresh watchlist to get updated data
      await fetchWatchlist();
      toast({ title: "Stock Added" });
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      console.error("[useWatchlist] Failed to add stock:", e.message);
      toast({
        title: "Error",
        description: "Could not add stock.",
        variant: "destructive",
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
      console.log("[useWatchlist] Updating targets:", { itemId, targetBuy, targetSell });
      await watchlistService.updateStockTargets({
        item_id: itemId,
        target_buy: targetBuy,
        target_sell: targetSell,
      });

      // Refresh watchlist to get updated data
      await fetchWatchlist();
      toast({ title: "Targets Updated" });
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      console.error("[useWatchlist] Failed to update targets:", e.message);
      toast({
        title: "Error",
        description: "Could not update targets.",
        variant: "destructive",
      });
    }
  };

  /**
   * Remove a stock from the watchlist.
   * Uses optimistic update to remove immediately from UI.
   */
  const removeStock = async (itemId: number) => {
    try {
      console.log("[useWatchlist] Removing stock:", { itemId });
      // Optimistic update
      setStocks((prev) => prev.filter((s) => s.id !== itemId));
      await watchlistService.removeStock(itemId);
      toast({ title: "Stock Removed" });
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      console.error("[useWatchlist] Failed to remove stock:", e.message);
      // On error, refresh to restore
      await fetchWatchlist();
      toast({
        title: "Error",
        description: "Could not remove stock.",
        variant: "destructive",
      });
    }
  };

  /**
   * Build a symbol->price map and a stable getPrice() accessor
   * ✅ Fix: useAnalysis expects either `prices[symbol]` or `getPrice(symbol)`
   */
  const prices = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of stocks) {
      const sym = (s.symbol || "").toUpperCase();
      if (sym && typeof (s as any).price === "number" && Number.isFinite((s as any).price)) {
        map[sym] = (s as any).price;
      }
    }
    return map;
  }, [stocks]);

  const getPrice = useCallback(
    (symbol: string) => {
      const sym = (symbol || "").toUpperCase();
      return sym ? prices[sym] ?? null : null;
    },
    [prices]
  );

  /**
   * Set up Server-Sent Events (SSE) for real-time stock price updates.
   * Triggered after watchlistId is established.
   */
  useEffect(() => {
    // Clear any scheduled reconnect when dependencies change
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (!user || !watchlistId) {
      console.log("[useWatchlist] Skipping SSE setup. User:", !!user, "WatchlistId:", watchlistId);
      return;
    }

    console.log("[useWatchlist] Setting up SSE stream for watchlist:", watchlistId);

    let cancelled = false;

    const setupStream = async () => {
      if (cancelled) return;

      try {
        const streamUrl = await watchlistService.getWatchlistStreamUrl();
        console.log("[useWatchlist] Connecting to SSE stream:", streamUrl);

        // Close any prior stream
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }

        eventSourceRef.current = new EventSource(streamUrl, { withCredentials: true });

        eventSourceRef.current.onmessage = (event) => {
          try {
            const update = JSON.parse(event.data);
            console.log("[useWatchlist] Received SSE update:", update);

            setStocks((prevStocks) =>
              prevStocks.map((stock) =>
                stock.symbol === update.symbol
                  ? {
                      ...stock,
                      price: update.price ?? (stock as any).price,
                      change: update.change ?? (stock as any).change,
                      changePercent: update.changePercent ?? (stock as any).changePercent,
                      lastUpdated: update.lastUpdated ?? (stock as any).lastUpdated,
                    }
                  : stock
              )
            );
          } catch (err) {
            console.error("[useWatchlist] Error parsing SSE update:", err);
          }
        };

        eventSourceRef.current.onerror = (err) => {
          console.error("[useWatchlist] SSE Error:", err);

          // Close and retry with backoff
          eventSourceRef.current?.close();
          eventSourceRef.current = null;

          if (cancelled) return;

          // Attempt to reconnect after delay
          reconnectTimeoutRef.current = setTimeout(() => {
            if (cancelled) return;
            if (user && watchlistId) {
              console.log("[useWatchlist] Attempting SSE reconnection");
              void setupStream();
            }
          }, 5000);
        };
      } catch (err) {
        console.error("[useWatchlist] Failed to setup SSE:", err);
      }
    };

    void setupStream();

    return () => {
      cancelled = true;

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      if (eventSourceRef.current) {
        console.log("[useWatchlist] Closing SSE connection");
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [user, watchlistId, watchlistService]);

  return {
    stocks,
    isLoading,
    loading: isLoading, // ✅ Alias for callers that expect `.loading`
    error,
    watchlistId,
    prices,             // ✅ Used by useAnalysis (wl.prices?.[symbol])
    getPrice,           // ✅ Used by useAnalysis (wl.getPrice(symbol))
    refresh: fetchWatchlist,
    addStock,
    updateTargets,
    removeStock,
  };
}
``