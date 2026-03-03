// web/src/features/watchlists/hooks/useWatchlist.ts
import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServices } from "@/shared/contexts/ServiceContext";
import {
  StockPriceInfo,
  WatchlistWithStocks,
  WatchlistMeta,
  WATCHLIST_LIMITS,
} from "../types/watchlist.types";
import { useAuth } from "@/providers/auth-provider";
import { useToast } from "@/hooks/use-toast";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";

interface UseWatchlistOptions {
  /**
   * Initial watchlist data provided by parent component.
   * When provided, the hook pre-populates the React Query cache immediately
   * so the component renders with data on the very first paint.
   */
  initialWatchlist?: WatchlistWithStocks;
}

export function useWatchlist(options?: UseWatchlistOptions) {
  const { watchlistService }  = useServices();
  const { firebaseUser: user } = useAuth();
  const { toast }             = useToast();
  const queryClient           = useQueryClient();

  // ── Determine the initial active query ID ──────────────────────────────────
  // "default" means "fetch the user's default watchlist".
  // After fetching we learn the real numeric ID and store it in watchlistId state.
  const initialId = useMemo<number | "default">(
    () => options?.initialWatchlist?.watchlist_id ?? "default",
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [], // intentionally stable — we only read this on mount
  );

  const [activeQueryId, setActiveQueryId] = useState<number | "default">(initialId);

  // ── Pre-populate cache from initialWatchlist (synchronous path) ───────────
  // This runs before any useEffect, so the query starts with data already
  // in cache — no loading state, no flicker on the first render.
  if (options?.initialWatchlist) {
    const cacheKey = QK.watchlist(options.initialWatchlist.watchlist_id);
    if (!queryClient.getQueryData(cacheKey)) {
      queryClient.setQueryData<WatchlistWithStocks>(cacheKey, options.initialWatchlist);
    }
  }

  // ── Watchlist structure query ───────────────────────────────────────────────
  const structureQuery = useQuery<WatchlistWithStocks, Error>({
    queryKey: QK.watchlist(activeQueryId),
    queryFn:  () =>
      activeQueryId === "default"
        ? watchlistService.getDefaultWatchlistStructure()
        : watchlistService.getWatchlistStructureById(activeQueryId as number),
    enabled:   !!user,
    staleTime: STALE.WATCHLIST,
    gcTime:    GC.WATCHLIST,
    retry:     1,
  });

  // ── All watchlists query (lightweight, for the switcher) ─────────────────
  const allWatchlistsQuery = useQuery<WatchlistMeta[], Error>({
    queryKey: QK.watchlists(),
    queryFn:  () => watchlistService.getAllWatchlists(),
    enabled:  !!user,
    staleTime: STALE.LISTS,
    gcTime:    GC.LISTS,
    retry:     1,
  });

  // ── Local stocks state ────────────────────────────────────────────────────
  //
  // WHY local state instead of reading structureQuery.data directly?
  // The SSE stream patches individual stock prices in-place. These patches
  // are ephemeral (not written back to the server) and must survive
  // re-renders without triggering full re-fetches. Local state lets SSE
  // update prices freely while React Query owns the authoritative structure.
  //
  // KEY PERFORMANCE DETAIL:
  // The useState initializer runs synchronously on mount and reads from the
  // React Query cache. On a return visit (cache is populated), stocks, name,
  // and watchlistId are all populated on the FIRST render — zero loading state,
  // zero flicker, zero network request needed.
  // ──────────────────────────────────────────────────────────────────────────

  const [stocks, setStocks] = useState<StockPriceInfo[]>(() => {
    const cached = queryClient.getQueryData<WatchlistWithStocks>(QK.watchlist(initialId));
    return cached?.stocks ?? options?.initialWatchlist?.stocks ?? [];
  });

  const [watchlistId, setWatchlistId] = useState<number | null>(() => {
    const cached = queryClient.getQueryData<WatchlistWithStocks>(QK.watchlist(initialId));
    return cached?.watchlist_id ?? options?.initialWatchlist?.watchlist_id ?? null;
  });

  const [watchlistName, setWatchlistName] = useState<string>(() => {
    const cached = queryClient.getQueryData<WatchlistWithStocks>(QK.watchlist(initialId));
    return cached?.name ?? options?.initialWatchlist?.name ?? "My Watchlist";
  });

  // ── Sync query data → local state ────────────────────────────────────────
  // Runs whenever the query data changes (initial fetch, invalidation after
  // mutation, or watchlist switch). Resets hasAutoEnrichedRef so the SSE
  // can re-enrich the new list's prices.
  useEffect(() => {
    if (!structureQuery.data) return;
    setStocks(structureQuery.data.stocks ?? []);
    setWatchlistId(structureQuery.data.watchlist_id);
    setWatchlistName(structureQuery.data.name ?? "My Watchlist");
    hasAutoEnrichedRef.current = false;
  }, [structureQuery.data]);

  // ── Mutation loading states (unchanged) ───────────────────────────────────
  const [isCreating,  setIsCreating]  = useState(false);
  const [isRenaming,  setIsRenaming]  = useState(false);
  const [isDeleting,  setIsDeleting]  = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);
  const [streamEpoch, setStreamEpoch] = useState(0);

  // ── SSE refs (completely unchanged) ───────────────────────────────────────
  const hasAutoEnrichedRef  = useRef(false);
  const eventSourceRef      = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Derived cap state ──────────────────────────────────────────────────────
  const stockCount       = stocks.length;
  const isWatchlistFull  = stockCount >= WATCHLIST_LIMITS.MAX_STOCKS;
  const allWatchlists    = allWatchlistsQuery.data ?? [];
  const isListCapReached = allWatchlists.length >= WATCHLIST_LIMITS.MAX_WATCHLISTS;

  // ── SSE setup (COMPLETELY UNCHANGED — zero logic modifications) ───────────
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

  // ── Prices map (unchanged) ─────────────────────────────────────────────────
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

  // ── refresh (replaces fetchWatchlist) ────────────────────────────────────
  const refresh = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: QK.watchlist(activeQueryId) });
  }, [queryClient, activeQueryId]);

  // ── addStock ───────────────────────────────────────────────────────────────
  const addStock = async (
    symbol:     string,
    targetBuy:  number | null,
    targetSell: number | null,
  ) => {
    if (!watchlistId) return;
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
      // Invalidate structure so the new stock appears after SSE re-enriches
      await queryClient.invalidateQueries({ queryKey: QK.watchlist(activeQueryId) });
      // Optimistic count update on the switcher list
      queryClient.setQueryData<WatchlistMeta[]>(QK.watchlists(), (prev) =>
        prev?.map((w) =>
          w.watchlist_id === watchlistId
            ? { ...w, stock_count: w.stock_count + 1 }
            : w,
        ),
      );
      setStreamEpoch((x) => x + 1);
      toast({ title: "Stock Added" });
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast({
        title:       "Error",
        description: detail ?? "Could not add stock.",
        variant:     "destructive",
      });
    }
  };

  // ── updateTargets ──────────────────────────────────────────────────────────
  const updateTargets = async (
    itemId:     number,
    targetBuy:  number | null,
    targetSell: number | null,
  ) => {
    try {
      await watchlistService.updateStockTargets({
        item_id:     itemId,
        target_buy:  targetBuy,
        target_sell: targetSell,
      });
      // Optimistic local update
      setStocks((prev) =>
        prev.map((s) => (s.id === itemId ? { ...s, targetBuy, targetSell } : s)),
      );
      // Keep query cache in sync so a subsequent invalidation returns correct data
      queryClient.setQueryData<WatchlistWithStocks>(
        QK.watchlist(activeQueryId),
        (prev) =>
          prev
            ? {
                ...prev,
                stocks: prev.stocks.map((s) =>
                  s.id === itemId ? { ...s, targetBuy, targetSell } : s,
                ),
              }
            : prev,
      );
      toast({ title: "Targets Updated" });
    } catch (err) {
      toast({ title: "Error", description: "Could not update targets.", variant: "destructive" });
    }
  };

  // ── removeStock ────────────────────────────────────────────────────────────
  const removeStock = async (itemId: number) => {
    try {
      // Optimistic removal (instant UI response)
      setStocks((prev) => prev.filter((s) => s.id !== itemId));
      await watchlistService.removeStock(itemId);
      // Keep cache consistent
      queryClient.setQueryData<WatchlistWithStocks>(
        QK.watchlist(activeQueryId),
        (prev) =>
          prev
            ? { ...prev, stocks: prev.stocks.filter((s) => s.id !== itemId) }
            : prev,
      );
      queryClient.setQueryData<WatchlistMeta[]>(QK.watchlists(), (prev) =>
        prev?.map((w) =>
          w.watchlist_id === watchlistId
            ? { ...w, stock_count: Math.max(0, w.stock_count - 1) }
            : w,
        ),
      );
      setStreamEpoch((x) => x + 1);
      toast({ title: "Stock Removed" });
    } catch (err) {
      // Revert by re-fetching the authoritative server state
      await queryClient.invalidateQueries({ queryKey: QK.watchlist(activeQueryId) });
      toast({ title: "Error", description: "Could not remove stock.", variant: "destructive" });
    }
  };

  // ── switchWatchlist ────────────────────────────────────────────────────────
  const switchWatchlist = useCallback(
    async (id: number) => {
      if (id === watchlistId || isSwitching) return;
      setIsSwitching(true);
      hasAutoEnrichedRef.current = false;
      try {
        setActiveQueryId(id);
        // fetchQuery: returns from cache instantly if fresh, otherwise fetches.
        // Either way, resolves before we clear isSwitching — the overlay
        // dismisses only when data is guaranteed available.
        await queryClient.fetchQuery({
          queryKey: QK.watchlist(id),
          queryFn:  () => watchlistService.getWatchlistStructureById(id),
          staleTime: STALE.WATCHLIST,
        });
        setStreamEpoch((x) => x + 1);
      } finally {
        setIsSwitching(false);
      }
    },
    [watchlistId, isSwitching, queryClient, watchlistService],
  );

  // ── createWatchlist ────────────────────────────────────────────────────────
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
        // Seed an empty structure in cache for the new list immediately
        // so switching to it is instant with no loading state
        const emptyStructure: WatchlistWithStocks = {
          watchlist_id: created.watchlist_id,
          name:         created.name,
          is_default:   false,
          stock_count:  0,
          stocks:       [],
        };
        queryClient.setQueryData<WatchlistWithStocks>(
          QK.watchlist(created.watchlist_id),
          emptyStructure,
        );
        // Refresh the switcher list
        await queryClient.invalidateQueries({ queryKey: QK.watchlists() });
        // Switch to the new list
        setActiveQueryId(created.watchlist_id);
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
    [isListCapReached, watchlistService, queryClient, toast],
  );

  // ── renameWatchlist ────────────────────────────────────────────────────────
  const renameWatchlist = useCallback(
    async (newName: string) => {
      if (!watchlistId) return;
      const trimmed = newName.trim();
      if (!trimmed || trimmed === watchlistName) return;

      const previousName = watchlistName;

      // Optimistic updates in local state + both caches
      setWatchlistName(trimmed);
      queryClient.setQueryData<WatchlistMeta[]>(QK.watchlists(), (prev) =>
        prev?.map((w) =>
          w.watchlist_id === watchlistId ? { ...w, name: trimmed } : w,
        ),
      );
      queryClient.setQueryData<WatchlistWithStocks>(
        QK.watchlist(activeQueryId),
        (prev) => (prev ? { ...prev, name: trimmed } : prev),
      );

      setIsRenaming(true);
      try {
        await watchlistService.renameWatchlist({
          watchlist_id: watchlistId,
          name:         trimmed,
        });
        toast({ title: "Watchlist Renamed" });
      } catch (err: any) {
        // Revert all optimistic updates on failure
        setWatchlistName(previousName);
        queryClient.setQueryData<WatchlistMeta[]>(QK.watchlists(), (prev) =>
          prev?.map((w) =>
            w.watchlist_id === watchlistId ? { ...w, name: previousName } : w,
          ),
        );
        queryClient.setQueryData<WatchlistWithStocks>(
          QK.watchlist(activeQueryId),
          (prev) => (prev ? { ...prev, name: previousName } : prev),
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
    [watchlistId, watchlistName, watchlistService, queryClient, activeQueryId, toast],
  );

  // ── deleteWatchlist ────────────────────────────────────────────────────────
  const deleteWatchlist = useCallback(
    async (id: number) => {
      const target = allWatchlists.find((w) => w.watchlist_id === id);
      if (!target) return;
      if (target.is_default) {
        toast({
          title:       "Cannot Delete",
          description: "The default watchlist cannot be deleted.",
          variant:     "destructive",
        });
        return;
      }
      setIsDeleting(true);
      try {
        await watchlistService.deleteWatchlist(id);
        // Evict the deleted list from cache
        queryClient.removeQueries({ queryKey: QK.watchlist(id) });
        // If we deleted the active list, fall back to the default
        if (id === watchlistId) {
          setActiveQueryId("default");
          await queryClient.invalidateQueries({ queryKey: QK.watchlist("default") });
          setStreamEpoch((x) => x + 1);
        }
        await queryClient.invalidateQueries({ queryKey: QK.watchlists() });
        toast({
          title:       "Watchlist Deleted",
          description: `"${target.name}" has been deleted.`,
        });
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
    [allWatchlists, watchlistId, watchlistService, queryClient, toast],
  );

  // ── Return value — contract is IDENTICAL to the original ─────────────────
  return {
    // ── Existing (UNCHANGED — all callers unaffected) ─────────────────────
    stocks,
    isLoading:   structureQuery.isPending,
    loading:     structureQuery.isPending,   // alias
    error:       structureQuery.error ?? null,
    watchlistId,
    prices,
    getPrice,
    refresh,
    addStock,
    updateTargets,
    removeStock,
    // ── New (unchanged names and types) ──────────────────────────────────
    watchlistName,
    allWatchlists,
    listsLoading: allWatchlistsQuery.isPending,
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