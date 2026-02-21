// src/features/watchlists/hooks/useWatchlist.ts
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useServices } from "@/shared/contexts/ServiceContext";
import {
  StockPriceInfo,
  WatchlistWithStocks,
  WatchlistMeta,
  WATCHLIST_LIMITS,
} from "../types/watchlist.types";
import { useAuth } from "@/providers/auth-provider";
import { useToast } from "@/hooks/use-toast";

interface UseWatchlistOptions {
  /**
   * Initial watchlist data provided by parent component.
   * When provided, the hook skips its own initial fetch.
   */
  initialWatchlist?: WatchlistWithStocks;
}

export function useWatchlist(options?: UseWatchlistOptions) {
  // ── Core watchlist state (existing) ──────────────────────────────────────
  const [stocks,      setStocks]      = useState<StockPriceInfo[]>([]);
  const [isLoading,   setIsLoading]   = useState(!options?.initialWatchlist);
  const [watchlistId, setWatchlistId] = useState<number | null>(null);
  const [watchlistName, setWatchlistName] = useState<string>("My Watchlist");
  const [error,       setError]       = useState<Error | null>(null);
  const [streamEpoch, setStreamEpoch] = useState(0);

  // ── Multi-watchlist state (new) ───────────────────────────────────────────
  const [allWatchlists,    setAllWatchlists]    = useState<WatchlistMeta[]>([]);
  const [listsLoading,     setListsLoading]     = useState(false);
  const [isCreating,       setIsCreating]       = useState(false);
  const [isRenaming,       setIsRenaming]       = useState(false);
  const [isDeleting,       setIsDeleting]       = useState(false);
  const [isSwitching,      setIsSwitching]      = useState(false);

  const { watchlistService } = useServices();
  const { firebaseUser: user } = useAuth();
  const { toast } = useToast();

  const hasInitializedRef    = useRef(false);
  const hasAutoEnrichedRef   = useRef(false);
  const eventSourceRef       = useRef<EventSource | null>(null);
  const reconnectTimeoutRef  = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Derived cap state ─────────────────────────────────────────────────────
  const stockCount       = stocks.length;
  const isWatchlistFull  = stockCount >= WATCHLIST_LIMITS.MAX_STOCKS;
  const isListCapReached = allWatchlists.length >= WATCHLIST_LIMITS.MAX_WATCHLISTS;

  // ── Fetch single watchlist structure (by ID or default) ──────────────────
  const fetchWatchlistById = useCallback(
    async (id: number) => {
      if (!user) return;
      try {
        setIsLoading(true);
        setError(null);
        const data = await watchlistService.getWatchlistStructureById(id);
        setStocks(data.stocks ?? []);
        setWatchlistId(data.watchlist_id);
        setWatchlistName(data.name ?? "My Watchlist");
      } catch (err) {
        const e = err instanceof Error ? err : new Error(String(err));
        setError(e);
        toast({ title: "Error", description: "Failed to load watchlist.", variant: "destructive" });
      } finally {
        setIsLoading(false);
      }
    },
    [user, watchlistService, toast],
  );

  const fetchWatchlist = useCallback(async () => {
    if (!user) return;
    try {
      setIsLoading(true);
      setError(null);
      const data = await watchlistService.getDefaultWatchlistStructure();
      setStocks(data.stocks ?? []);
      setWatchlistId(data.watchlist_id);
      setWatchlistName(data.name ?? "My Watchlist");
    } catch (err) {
      const e = err instanceof Error ? err : new Error(String(err));
      setError(e);
      toast({ title: "Error", description: "Failed to load watchlist.", variant: "destructive" });
    } finally {
      setIsLoading(false);
    }
  }, [user, watchlistService, toast]);

  // ── Fetch all watchlists (lightweight, for switcher) ─────────────────────
  const fetchAllWatchlists = useCallback(async () => {
    if (!user) return;
    try {
      setListsLoading(true);
      const lists = await watchlistService.getAllWatchlists();
      setAllWatchlists(lists);
    } catch (err) {
      // Non-critical — don't surface to user if switcher fails
      console.warn("[useWatchlist] Failed to fetch all watchlists:", err);
    } finally {
      setListsLoading(false);
    }
  }, [user, watchlistService]);

  // ── Initialization (existing logic preserved exactly) ────────────────────
  useEffect(() => {
    if (hasInitializedRef.current) return;

    if (options?.initialWatchlist) {
      setWatchlistId(options.initialWatchlist.watchlist_id);
      setStocks(options.initialWatchlist.stocks ?? []);
      setWatchlistName(options.initialWatchlist.name ?? "My Watchlist");
      setIsLoading(false);
      hasInitializedRef.current = true;
      void fetchAllWatchlists();
      return;
    }

    if (!user) return;

    void (async () => {
      await fetchWatchlist();
      await fetchAllWatchlists();
      hasInitializedRef.current = true;
    })();
  }, [options?.initialWatchlist, user, fetchWatchlist, fetchAllWatchlists]);

  // ── SSE setup (existing logic unchanged) ─────────────────────────────────
  useEffect(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (!user || !watchlistId) return;

    let cancelled = false;

    const setupStream = async () => {
      if (cancelled) return;
      try {
        const streamUrl = await watchlistService.getWatchlistStreamUrl();
        if (eventSourceRef.current) {
          eventSourceRef.current.close();
          eventSourceRef.current = null;
        }
        eventSourceRef.current = new EventSource(streamUrl, { withCredentials: true });

        eventSourceRef.current.onmessage = (event) => {
          try {
            const update = JSON.parse(event.data);
            hasAutoEnrichedRef.current = true;
            setStocks((prev) =>
              prev.map((stock) =>
                stock.symbol === update.symbol
                  ? {
                      ...stock,
                      price:         update.price         ?? stock.price,
                      change:        update.change        ?? stock.change,
                      changePercent: update.changePercent ?? stock.changePercent,
                      lastUpdated:   update.lastUpdated   ?? stock.lastUpdated,
                    }
                  : stock,
              ),
            );
          } catch (err) {
            console.error("[useWatchlist] Error parsing SSE update:", err);
          }
        };

        eventSourceRef.current.onerror = () => {
          eventSourceRef.current?.close();
          eventSourceRef.current = null;
          if (cancelled) return;
          reconnectTimeoutRef.current = setTimeout(() => {
            if (cancelled) return;
            if (user && watchlistId) void setupStream();
            if (!hasAutoEnrichedRef.current) {
              const enrichTimeout = setTimeout(async () => {
                if (hasAutoEnrichedRef.current) return;
                try {
                  const data = await watchlistService.getDefaultWatchlist();
                  setStocks(data.stocks ?? []);
                  setWatchlistId(data.watchlist_id);
                  hasAutoEnrichedRef.current = true;
                } catch (e) {
                  console.warn("[useWatchlist] Auto-enrichment failed:", e);
                }
              }, 1500);
              return () => clearTimeout(enrichTimeout);
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
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [user, watchlistId, watchlistService, streamEpoch]);

  // ── Prices map (existing, unchanged) ─────────────────────────────────────
  const prices = useMemo(() => {
    const map: Record<string, number> = {};
    for (const s of stocks) {
      const sym = (s.symbol ?? "").toUpperCase();
      if (sym && typeof s.price === "number" && Number.isFinite(s.price)) {
        map[sym] = s.price;
      }
    }
    return map;
  }, [stocks]);

  const getPrice = useCallback(
    (symbol: string) => {
      const sym = (symbol ?? "").toUpperCase();
      return sym ? (prices[sym] ?? null) : null;
    },
    [prices],
  );

  // ── Existing mutations (unchanged logic, cap check added to addStock) ─────

  const addStock = async (
    symbol: string,
    targetBuy: number | null,
    targetSell: number | null,
  ) => {
    if (!watchlistId) return;

    // Client-side cap guard (UX layer — backend enforces independently)
    if (isWatchlistFull) {
      toast({
        title:       "Watchlist Full",
        description: `This watchlist has reached its ${WATCHLIST_LIMITS.MAX_STOCKS}-stock limit. Create a new watchlist to add more stocks.`,
        variant:     "destructive",
      });
      return;
    }

    try {
      await watchlistService.addStock({
        watchlist_id: watchlistId,
        symbol,
        target_buy:   targetBuy,
        target_sell:  targetSell,
      });
      await fetchWatchlist();
      // Update the stock_count in allWatchlists optimistically
      setAllWatchlists((prev) =>
        prev.map((w) =>
          w.watchlist_id === watchlistId
            ? { ...w, stock_count: w.stock_count + 1 }
            : w,
        ),
      );
      setStreamEpoch((x) => x + 1);
      toast({ title: "Stock Added" });
    } catch (err: any) {
      // Propagate 409 cap error from backend verbatim
      const detail = err?.response?.data?.detail;
      toast({
        title:       "Error",
        description: detail ?? "Could not add stock.",
        variant:     "destructive",
      });
    }
  };

  const updateTargets = async (
    itemId: number,
    targetBuy: number | null,
    targetSell: number | null,
  ) => {
    try {
      await watchlistService.updateStockTargets({
        item_id:     itemId,
        target_buy:  targetBuy,
        target_sell: targetSell,
      });
      setStocks((prev) =>
        prev.map((s) =>
          s.id === itemId ? { ...s, targetBuy, targetSell } : s,
        ),
      );
      toast({ title: "Targets Updated" });
    } catch (err) {
      toast({ title: "Error", description: "Could not update targets.", variant: "destructive" });
    }
  };

  const removeStock = async (itemId: number) => {
    try {
      setStocks((prev) => prev.filter((s) => s.id !== itemId));
      await watchlistService.removeStock(itemId);
      setAllWatchlists((prev) =>
        prev.map((w) =>
          w.watchlist_id === watchlistId
            ? { ...w, stock_count: Math.max(0, w.stock_count - 1) }
            : w,
        ),
      );
      setStreamEpoch((x) => x + 1);
      toast({ title: "Stock Removed" });
    } catch (err) {
      await fetchWatchlist();
      toast({ title: "Error", description: "Could not remove stock.", variant: "destructive" });
    }
  };

  // ── New multi-watchlist operations ────────────────────────────────────────

  /** Switch the active watchlist. Restarts SSE for the new watchlist. */
  const switchWatchlist = useCallback(
    async (id: number) => {
      if (id === watchlistId || isSwitching) return;
      setIsSwitching(true);
      hasAutoEnrichedRef.current = false;
      try {
        await fetchWatchlistById(id);
        setStreamEpoch((x) => x + 1); // restart SSE
      } finally {
        setIsSwitching(false);
      }
    },
    [watchlistId, isSwitching, fetchWatchlistById],
  );

  /** Create a new watchlist and switch to it. */
  const createWatchlist = useCallback(
    async (name: string) => {
      if (isListCapReached) {
        toast({
          title:       "Limit Reached",
          description: `You can have at most ${WATCHLIST_LIMITS.MAX_WATCHLISTS} watchlists.`,
          variant:     "destructive",
        });
        return;
      }
      setIsCreating(true);
      try {
        const created = await watchlistService.createWatchlist({ name });
        await fetchAllWatchlists(); // refresh the full list with correct counts
        // Switch to the new (empty) list
        setWatchlistId(created.watchlist_id);
        setWatchlistName(created.name);
        setStocks([]);
        setStreamEpoch((x) => x + 1);
        toast({ title: "Watchlist Created", description: `"${created.name}" is ready.` });
      } catch (err: any) {
        const detail = err?.response?.data?.detail;
        toast({
          title:       "Error",
          description: detail ?? "Could not create watchlist.",
          variant:     "destructive",
        });
      } finally {
        setIsCreating(false);
      }
    },
    [isListCapReached, watchlistService, fetchAllWatchlists, toast],
  );

  /** Rename the active watchlist. */
  const renameWatchlist = useCallback(
    async (newName: string) => {
      if (!watchlistId) return;
      const trimmed = newName.trim();
      if (!trimmed || trimmed === watchlistName) return;

      const previousName = watchlistName;
      // Optimistic update
      setWatchlistName(trimmed);
      setAllWatchlists((prev) =>
        prev.map((w) =>
          w.watchlist_id === watchlistId ? { ...w, name: trimmed } : w,
        ),
      );

      setIsRenaming(true);
      try {
        await watchlistService.renameWatchlist({
          watchlist_id: watchlistId,
          name:         trimmed,
        });
        toast({ title: "Watchlist Renamed" });
      } catch (err: any) {
        // Revert on failure
        setWatchlistName(previousName);
        setAllWatchlists((prev) =>
          prev.map((w) =>
            w.watchlist_id === watchlistId ? { ...w, name: previousName } : w,
          ),
        );
        const detail = err?.response?.data?.detail;
        toast({
          title:       "Error",
          description: detail ?? "Could not rename watchlist.",
          variant:     "destructive",
        });
      } finally {
        setIsRenaming(false);
      }
    },
    [watchlistId, watchlistName, watchlistService, toast],
  );

  /** Delete a watchlist (cannot delete the default). Switches to default after. */
  const deleteWatchlist = useCallback(
    async (id: number) => {
      const target = allWatchlists.find((w) => w.watchlist_id === id);
      if (!target) return;
      if (target.is_default) {
        toast({ title: "Cannot Delete", description: "The default watchlist cannot be deleted.", variant: "destructive" });
        return;
      }

      setIsDeleting(true);
      try {
        await watchlistService.deleteWatchlist(id);
        // If we deleted the active one, switch to default
        if (id === watchlistId) {
          await fetchWatchlist(); // fallback to default
          setStreamEpoch((x) => x + 1);
        }
        await fetchAllWatchlists();
        toast({ title: "Watchlist Deleted", description: `"${target.name}" has been deleted.` });
      } catch (err: any) {
        const detail = err?.response?.data?.detail;
        toast({
          title:       "Error",
          description: detail ?? "Could not delete watchlist.",
          variant:     "destructive",
        });
      } finally {
        setIsDeleting(false);
      }
    },
    [allWatchlists, watchlistId, watchlistService, fetchWatchlist, fetchAllWatchlists, toast],
  );

  // ── Return value ──────────────────────────────────────────────────────────
  return {
    // ── Existing return values (UNCHANGED — all callers unaffected) ─────────
    stocks,
    isLoading,
    loading:     isLoading,   // alias
    error,
    watchlistId,
    prices,
    getPrice,
    refresh:     fetchWatchlist,
    addStock,
    updateTargets,
    removeStock,

    // ── New return values ──────────────────────────────────────────────────
    watchlistName,
    allWatchlists,
    listsLoading,
    stockCount,
    isWatchlistFull,
    isListCapReached,
    isSwitching,
    isCreating,
    isRenaming,
    isDeleting,
    switchWatchlist,
    createWatchlist,
    renameWatchlist,
    deleteWatchlist,
  };
}