// web/src/features/watchlists/hooks/useWatchlist.ts
//
// CHANGES vs previous version:
//
//   REMOVED — SSE ownership
//     The EventSource, reconnect logic, streamEpoch, hasAutoEnrichedRef,
//     eventSourceRef, and reconnectTimeoutRef are all gone.
//     GlobalSSEProvider (src/providers/GlobalSSEProvider.tsx) now owns the
//     single session-wide SSE connection and writes prices into the React
//     Query cache at QK.price(symbol). Components read prices via usePriceData.
//
//   REMOVED — setStreamEpoch() calls in all mutations
//     Those calls existed solely to restart the component-scoped SSE after
//     mutations. With a global SSE that never tears down, there is nothing
//     to restart.
//
//   UNCHANGED — entire public contract
//     Every key in the return object, every function signature, every
//     behaviour observable by callers is identical. Drop-in replacement.
//
//   NOTE — prices / getPrice return values
//     These still exist for backward compatibility. They reflect whatever
//     price data the structure endpoint returns (typically null for live
//     prices). Components needing live prices should use usePriceData(symbol).
import { useState, useEffect, useCallback, useMemo } from "react";
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
  const { watchlistService }   = useServices();
  const { firebaseUser: user } = useAuth();
  const { toast }              = useToast();
  const queryClient            = useQueryClient();

  // ── Determine the initial active query ID ──────────────────────────────────
  const initialId = useMemo<number | "default">(
    () => options?.initialWatchlist?.watchlist_id ?? "default",
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [], // intentionally stable — only read on mount
  );

  const [activeQueryId, setActiveQueryId] = useState<number | "default">(initialId);

  // ── Pre-populate cache from initialWatchlist (synchronous path) ───────────
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
    queryKey:  QK.watchlists(),
    queryFn:   () => watchlistService.getAllWatchlists(),
    enabled:   !!user,
    staleTime: STALE.LISTS,
    gcTime:    GC.LISTS,
    retry:     1,
  });

  // ── Local stocks state (structure only) ──────────────────────────────────
  //
  // Holds the watchlist structure: symbol, name, id, targetBuy, targetSell.
  // Live prices are NO LONGER stored here — they live in QK.price(symbol)
  // entries written by GlobalSSEProvider. Components read prices via
  // usePriceData(symbol), which survives navigation without re-fetching.
  //
  // The useState initialiser still reads from cache on mount so that switching
  // back to the watchlist page shows the structure immediately.
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
  useEffect(() => {
    if (!structureQuery.data) return;
    setStocks(structureQuery.data.stocks ?? []);
    setWatchlistId(structureQuery.data.watchlist_id);
    setWatchlistName(structureQuery.data.name ?? "My Watchlist");
  }, [structureQuery.data]);

  // ── Mutation loading states ────────────────────────────────────────────────
  const [isCreating,  setIsCreating]  = useState(false);
  const [isRenaming,  setIsRenaming]  = useState(false);
  const [isDeleting,  setIsDeleting]  = useState(false);
  const [isSwitching, setIsSwitching] = useState(false);

  // ── Derived cap state ──────────────────────────────────────────────────────
  const stockCount       = stocks.length;
  const isWatchlistFull  = stockCount >= WATCHLIST_LIMITS.MAX_STOCKS;
  const allWatchlists    = allWatchlistsQuery.data ?? [];
  const isListCapReached = allWatchlists.length >= WATCHLIST_LIMITS.MAX_WATCHLISTS;

  // ── Prices map — backward-compat only ────────────────────────────────────
  // Reflects prices in the structure data (may be null if the structure
  // endpoint returns symbols+targets only). For live prices use usePriceData.
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

  // ── refresh ────────────────────────────────────────────────────────────────
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
      await queryClient.invalidateQueries({ queryKey: QK.watchlist(activeQueryId) });
      queryClient.setQueryData<WatchlistMeta[]>(QK.watchlists(), (prev) =>
        prev?.map((w) =>
          w.watchlist_id === watchlistId
            ? { ...w, stock_count: w.stock_count + 1 }
            : w,
        ),
      );
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
      setStocks((prev) =>
        prev.map((s) => (s.id === itemId ? { ...s, targetBuy, targetSell } : s)),
      );
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
      setStocks((prev) => prev.filter((s) => s.id !== itemId));
      await watchlistService.removeStock(itemId);
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
      toast({ title: "Stock Removed" });
    } catch (err) {
      await queryClient.invalidateQueries({ queryKey: QK.watchlist(activeQueryId) });
      toast({ title: "Error", description: "Could not remove stock.", variant: "destructive" });
    }
  };

  // ── switchWatchlist ────────────────────────────────────────────────────────
  const switchWatchlist = useCallback(
    async (id: number) => {
      if (id === watchlistId || isSwitching) return;
      setIsSwitching(true);
      try {
        setActiveQueryId(id);
        await queryClient.fetchQuery({
          queryKey:  QK.watchlist(id),
          queryFn:   () => watchlistService.getWatchlistStructureById(id),
          staleTime: STALE.WATCHLIST,
        });
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
        await queryClient.invalidateQueries({ queryKey: QK.watchlists() });
        setActiveQueryId(created.watchlist_id);
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
        queryClient.removeQueries({ queryKey: QK.watchlist(id) });
        if (id === watchlistId) {
          setActiveQueryId("default");
          await queryClient.invalidateQueries({ queryKey: QK.watchlist("default") });
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

  // ── Return value — contract identical to original ─────────────────────────
  return {
    stocks,
    isLoading:    structureQuery.isPending,
    loading:      structureQuery.isPending,
    error:        structureQuery.error ?? null,
    watchlistId,
    prices,
    getPrice,
    refresh,
    addStock,
    updateTargets,
    removeStock,
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