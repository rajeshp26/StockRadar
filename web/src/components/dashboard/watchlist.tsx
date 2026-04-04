"use client";

import { useMemo, useState, useCallback, useRef, useEffect, useLayoutEffect } from "react";
import { cn } from "@/lib/utils";
import { useQueries } from "@tanstack/react-query";
import { useWatchlist } from "@/features/watchlists/hooks/useWatchlist";
import type { WatchlistWithStocks, StockPriceInfo } from "@/features/watchlists/types/watchlist.types";
import { WATCHLIST_LIMITS } from "@/features/watchlists/types/watchlist.types";
import { StockCard } from "./stock-card";
import { StockListRow } from "./stock-list-row";
import { StockTargetDialog } from "./add-stock-dialog";
import { WatchlistSwitcher } from "./watchlist-switcher";
import { WatchlistToolbar, type SortKey, type ViewMode } from "./watchlist-toolbar";
import { WatchlistSectorView } from "./watchlist-sector-view";
import { QK } from "@/lib/query-keys";
import { GC } from "@/lib/query-client";
import type { CachedPrice } from "@/providers/GlobalSSEProvider";import {
  Plus, RefreshCw, Pencil, Check, X,
  BarChart2, AlertTriangle,
} from "lucide-react";

interface WatchlistProps {
  initialWatchlist?: WatchlistWithStocks;
}

// ── Summary card ─────────────────────────────────────────────────────────────
function SummaryCard({
  label, count, accent, active, onClick,
}: {
  label:   string;
  count:   number;
  accent:  "default" | "buy" | "sell";
  active:  boolean;
  onClick: () => void;
}) {
  const countColor = {
    default: "text-white",
    buy:     "text-emerald-400",
    sell:    "text-rose-400",
  }[accent];

  const activeBorder = {
    default: "border-white/20  shadow-[0_0_0_1px_rgba(255,255,255,0.12)]",
    buy:     "border-emerald-500/40 shadow-[0_0_16px_rgba(52,211,153,0.12)]",
    sell:    "border-rose-500/40    shadow-[0_0_16px_rgba(251,113,133,0.12)]",
  }[accent];

  return (
    <button
      onClick={onClick}
      className={cn(
        "glass-card rounded-2xl px-5 py-4 flex-1 text-left transition-all",
        active ? activeBorder : "hover:bg-white/5",
      )}
    >
      <p className="glass-overline mb-2">{label}</p>
      <p className={cn("text-2xl font-black tabular-nums", countColor)}>{count}</p>
    </button>
  );
}

// ── Inline rename ─────────────────────────────────────────────────────────────
function InlineRename({
  currentName, isRenaming, onSave, onCancel,
}: {
  currentName: string;
  isRenaming:  boolean;
  onSave:      (name: string) => void;
  onCancel:    () => void;
}) {
  const [draft, setDraft] = useState(currentName);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter")  onSave(draft);
    if (e.key === "Escape") onCancel();
  }

  return (
    <div className="flex items-center gap-2">
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value.slice(0, WATCHLIST_LIMITS.MAX_NAME_LENGTH))}
        onKeyDown={handleKeyDown}
        maxLength={WATCHLIST_LIMITS.MAX_NAME_LENGTH}
        className={cn(
          "bg-transparent border-b-2 border-indigo-500/60",
          "text-xl font-black text-white",
          "focus:outline-none focus:border-indigo-400",
          "min-w-0 w-48",
        )}
        aria-label="Rename watchlist"
      />
      <button
        onClick={() => onSave(draft)}
        disabled={isRenaming || !draft.trim()}
        className="h-7 w-7 flex items-center justify-center rounded-lg bg-indigo-500/15 border border-indigo-500/25 text-indigo-400 hover:bg-indigo-500/25 transition-colors disabled:opacity-30"
      >
        {isRenaming ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Check className="h-3 w-3" />}
      </button>
      <button
        onClick={onCancel}
        className="h-7 w-7 flex items-center justify-center rounded-lg bg-white/5 border border-white/8 text-white/30 hover:text-white/60 transition-colors"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

// ── Full-cap notice modal ─────────────────────────────────────────────────────
function FullCapNotice({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="glass-panel relative w-full max-w-sm p-8 animate-fade-up text-center space-y-5">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-amber-500/15 border border-amber-500/25 mx-auto">
          <AlertTriangle className="h-6 w-6 text-amber-400" />
        </div>
        <div>
          <h3 className="text-lg font-black text-white">Watchlist Full</h3>
          <p className="text-sm text-white/40 mt-2 leading-relaxed">
            This watchlist has reached its {WATCHLIST_LIMITS.MAX_STOCKS}-stock limit.
            Use the watchlist switcher to create a new list for more stocks.
          </p>
        </div>
        <button
          onClick={onClose}
          className="glass-btn w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest"
        >
          Got it
        </button>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function Watchlist({ initialWatchlist }: WatchlistProps) {
  const wl = useWatchlist({ initialWatchlist });

  // ── Reactive price subscriptions for all stocks ───────────────────────────
  //
  // useQueries subscribes to every QK.price(symbol) cache entry.
  // When GlobalSSEProvider writes a new price via setQueryData, React Query
  // notifies these subscribers → Watchlist re-renders with fresh prices.
  //
  // enabled: false — no HTTP fetching from here, read-only cache subscriber.
  // Per-card display uses usePriceData in StockCard/StockListRow directly.
  // This block gives the PARENT access to prices for alert counts + sorting.
  const priceQueries = useQueries({
    queries: wl.stocks.map((s) => ({
      queryKey:        QK.price(s.symbol),
      queryFn:         () => Promise.resolve(null as CachedPrice | null),
      enabled:         false,
      staleTime:       Infinity,
      gcTime:          GC.PRICE,
      placeholderData: null as CachedPrice | null,
    })),
  });

  // Merge structure + cached prices into a single enriched list.
  // Falls back gracefully to whatever price the structure returned (usually null).
  const stocksWithPrices: StockPriceInfo[] = useMemo(
    () =>
      wl.stocks.map((s, i) => {
        const cached = priceQueries[i]?.data;
        return {
          ...s,
          price:         cached?.price         ?? s.price         ?? null,
          change:        cached?.change        ?? s.change        ?? null,
          changePercent: cached?.changePercent ?? s.changePercent ?? null,
        };
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [wl.stocks, priceQueries],
  );

  // ── Session-persistent view state ─────────────────────────────────────────
  // Survives navigation back/forward within the tab session.
  // typeof window guard makes initialiser safe for SSR / hydration.
  const ss = typeof window !== "undefined" ? sessionStorage : null;

  const [alertFilter, setAlertFilter] = useState<"all" | "buy" | "sell">(
    () => (ss?.getItem("wl:alertFilter") as "all" | "buy" | "sell" | null) ?? "all",
  );
  const [searchQuery, setSearchQuery] = useState("");
  const [sortKey,     setSortKey]     = useState<SortKey>(
    () => (ss?.getItem("wl:sortKey") as SortKey | null) ?? "default",
  );
  const [viewMode,    setViewMode]    = useState<ViewMode>(
    () => (ss?.getItem("wl:viewMode") as ViewMode | null) ?? "grid",
  );

  // Persist on every change. useLayoutEffect avoids a flash if StrictMode
  // double-invokes effects, since layout effects run synchronously.
  useLayoutEffect(() => {
    ss?.setItem("wl:alertFilter", alertFilter);
  }, [alertFilter, ss]);
  useLayoutEffect(() => {
    ss?.setItem("wl:sortKey", sortKey);
  }, [sortKey, ss]);
  useLayoutEffect(() => {
    ss?.setItem("wl:viewMode", viewMode);
  }, [viewMode, ss]);

  const [sortOpen,      setSortOpen]      = useState(false);
  const [renamingUI,    setRenamingUI]    = useState(false);
  const [addOpen,       setAddOpen]       = useState(false);
  const [editStock,     setEditStock]     = useState<StockPriceInfo | null>(null);
  const [showCapNotice, setShowCapNotice] = useState(false);

  // Debounce search input
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(searchQuery), 150);
    return () => clearTimeout(t);
  }, [searchQuery]);

  // Alert counts (full list, not filtered — so summary cards are always accurate)
  const buyAlertCount = useMemo(
    () => stocksWithPrices.filter((s) => s.targetBuy != null && s.price != null && s.price <= s.targetBuy).length,
    [stocksWithPrices],
  );
  const sellAlertCount = useMemo(
    () => stocksWithPrices.filter((s) => s.targetSell != null && s.price != null && s.price >= s.targetSell).length,
    [stocksWithPrices],
  );

  // Three-stage pipeline: alert filter → search → sort
  const processedStocks = useMemo(() => {
    let list = stocksWithPrices;

    if (alertFilter === "buy")
      list = list.filter((s) => s.targetBuy  != null && s.price != null && s.price <= s.targetBuy);
    if (alertFilter === "sell")
      list = list.filter((s) => s.targetSell != null && s.price != null && s.price >= s.targetSell);

    if (debouncedSearch.trim()) {
      const q = debouncedSearch.trim().toLowerCase();
      list = list.filter(
        (s) => s.symbol.toLowerCase().includes(q) || s.name.toLowerCase().includes(q),
      );
    }

    switch (sortKey) {
      case "symbol_asc":  list = [...list].sort((a, b) => a.symbol.localeCompare(b.symbol)); break;
      case "symbol_desc": list = [...list].sort((a, b) => b.symbol.localeCompare(a.symbol)); break;
      case "price_desc":  list = [...list].sort((a, b) => (b.price ?? 0) - (a.price ?? 0)); break;
      case "price_asc":   list = [...list].sort((a, b) => (a.price ?? 0) - (b.price ?? 0)); break;
      case "change_desc": list = [...list].sort((a, b) => (b.changePercent ?? 0) - (a.changePercent ?? 0)); break;
      case "change_asc":  list = [...list].sort((a, b) => (a.changePercent ?? 0) - (b.changePercent ?? 0)); break;
      case "buy_gap_asc":
        list = [...list].sort((a, b) => {
          const ga = a.targetBuy != null && a.price != null ? Math.abs((a.price - a.targetBuy) / a.targetBuy) : Infinity;
          const gb = b.targetBuy != null && b.price != null ? Math.abs((b.price - b.targetBuy) / b.targetBuy) : Infinity;
          return ga - gb;
        });
        break;
    }
    return list;
  }, [stocksWithPrices, alertFilter, debouncedSearch, sortKey]);

  const hasActiveFilters = alertFilter !== "all" || debouncedSearch.trim() !== "";
  const clearFilters = useCallback(() => { setAlertFilter("all"); setSearchQuery(""); }, []);

  const handleAddClick = useCallback(() => {
    if (wl.isWatchlistFull) setShowCapNotice(true);
    else setAddOpen(true);
  }, [wl.isWatchlistFull]);

  const handleRenameSave = useCallback(async (name: string) => {
    await wl.renameWatchlist(name);
    setRenamingUI(false);
  }, [wl]);

  // ── Loading ────────────────────────────────────────────────────────────────
  if (wl.isLoading) {
    return (
      <div className="space-y-6 animate-fade-up">
        <div className="glass-panel p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="h-7 w-48 rounded-xl bg-white/8 glass-shimmer" />
            <div className="h-9 w-28 rounded-xl bg-white/8 glass-shimmer" />
          </div>
          <div className="flex gap-3">
            {[0,1,2].map((i) => <div key={i} className="flex-1 h-20 rounded-2xl bg-white/5 glass-shimmer" />)}
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[0,1,2,3,4,5].map((i) => <div key={i} className="glass-card rounded-3xl h-48 glass-shimmer" />)}
        </div>
      </div>
    );
  }

  // ── Error ──────────────────────────────────────────────────────────────────
  if (wl.error) {
    return (
      <div className="glass-panel p-10 flex flex-col items-center text-center space-y-4">
        <div className="h-12 w-12 flex items-center justify-center rounded-2xl bg-rose-500/15 border border-rose-500/25">
          <AlertTriangle className="h-6 w-6 text-rose-400" />
        </div>
        <div>
          <h3 className="text-base font-black text-white">Failed to load watchlist</h3>
          <p className="text-sm text-white/35 mt-1">Something went wrong. Please try again.</p>
        </div>
        <button onClick={() => wl.refresh()} className="glass-btn inline-flex items-center gap-2 px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest">
          <RefreshCw className="h-3 w-3" /> Try Again
        </button>
      </div>
    );
  }

  // ── Main render ────────────────────────────────────────────────────────────
  return (
    <div className="space-y-5 animate-fade-up">

      {/* ── Header panel ──────────────────────────────────────────────────── */}
      
      <div className="glass-panel p-6 space-y-5">

        {/* Row: switcher + name + rename + add */}
        <div className="flex items-center gap-3 flex-wrap">

          <WatchlistSwitcher
            allWatchlists={wl.allWatchlists}
            activeId={wl.watchlistId}
            isListCapReached={wl.isListCapReached}
            isCreating={wl.isCreating}
            isDeleting={wl.isDeleting}
            onSwitch={wl.switchWatchlist}
            onCreate={wl.createWatchlist}
            onDelete={wl.deleteWatchlist}
          />

          {renamingUI ? (
            <InlineRename
              currentName={wl.watchlistName}
              isRenaming={wl.isRenaming}
              onSave={handleRenameSave}
              onCancel={() => setRenamingUI(false)}
            />
          ) : (
            <button
              onClick={() => setRenamingUI(true)}
              className="group flex items-center gap-2 rounded-xl px-2 py-1 hover:bg-white/5 transition-colors"
              title="Click to rename watchlist"
            >
              <span className="text-xl font-black text-white tracking-tight">
                {wl.watchlistName}
              </span>
              <Pencil className="h-3.5 w-3.5 text-white/20 group-hover:text-white/50 transition-colors" />
            </button>
          )}

          <div className="ml-auto">
            <button
              onClick={handleAddClick}
              disabled={wl.isSwitching}
              title={wl.isWatchlistFull ? `Watchlist is full (${WATCHLIST_LIMITS.MAX_STOCKS}/${WATCHLIST_LIMITS.MAX_STOCKS}). Create a new watchlist to add more.` : "Add stock"}
              className={cn(
                "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl",
                "text-[10px] font-black uppercase tracking-widest transition-all duration-150",
                wl.isWatchlistFull
                  ? "bg-white/5 border border-white/8 text-white/25 cursor-not-allowed"
                  : "bg-indigo-600 border border-indigo-500/50 text-white shadow-[0_4px_16px_rgba(99,102,241,0.3)] hover:bg-indigo-500 active:scale-[0.98]",
              )}
            >
              <Plus className="h-3.5 w-3.5" />
              {wl.isWatchlistFull
                ? `Full (${WATCHLIST_LIMITS.MAX_STOCKS}/${WATCHLIST_LIMITS.MAX_STOCKS})`
                : "Add Stock"
              }
            </button>
          </div>
        </div>

        {/* Summary cards */}
        <div className="flex gap-3">
          <SummaryCard label="All Stocks"  count={stocksWithPrices.length} accent="default" active={alertFilter === "all"}  onClick={() => setAlertFilter("all")} />
          <SummaryCard label="Buy Alerts"  count={buyAlertCount}    accent="buy"     active={alertFilter === "buy"}  onClick={() => setAlertFilter("buy")} />
          <SummaryCard label="Sell Alerts" count={sellAlertCount}   accent="sell"    active={alertFilter === "sell"} onClick={() => setAlertFilter("sell")} />
        </div>
      </div>

      {/* ── Toolbar (only when stocks exist) ─────────────────────────────── */}
      {wl.stocks.length > 0 && (
        <WatchlistToolbar
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          sortKey={sortKey}
          onSortChange={setSortKey}
          sortOpen={sortOpen}
          onSortOpenChange={setSortOpen}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          visibleCount={processedStocks.length}
          totalCount={stocksWithPrices.length}
          stockCount={wl.stockCount}
          isWatchlistFull={wl.isWatchlistFull}
          hasActiveFilters={hasActiveFilters}
          onClearFilters={clearFilters}
          alertFilter={alertFilter}
        />
      )}

      {/* ── Content ───────────────────────────────────────────────────────── */}
      {wl.stocks.length === 0 ? (
        <div className="glass-panel p-16 flex flex-col items-center text-center space-y-5">
          <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-indigo-500/10 border border-indigo-500/15">
            <BarChart2 className="h-7 w-7 text-indigo-400/50" />
          </div>
          <div>
            <h3 className="text-lg font-black text-white">No stocks yet</h3>
            <p className="text-sm text-white/30 mt-2 max-w-xs leading-relaxed">
              Add up to {WATCHLIST_LIMITS.MAX_STOCKS} stocks per watchlist to track prices and set buy/sell targets.
            </p>
          </div>
          <button
            onClick={() => setAddOpen(true)}
            className="bg-indigo-600 border border-indigo-500/50 text-white px-5 py-2.5 rounded-xl text-[10px] font-black uppercase tracking-widest inline-flex items-center gap-2 hover:bg-indigo-500 transition-colors"
          >
            <Plus className="h-3.5 w-3.5" /> Add First Stock
          </button>
        </div>
      ) : processedStocks.length === 0 ? (
        <div className="glass-panel p-12 flex flex-col items-center text-center space-y-4">
          <p className="text-base font-black text-white">No stocks match your filters</p>
          <p className="text-sm text-white/30">Try a different symbol or clear your filters.</p>
          <button onClick={clearFilters} className="glass-btn px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest">
            Clear Filters
          </button>
        </div>
      ) : viewMode === "grid" ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {processedStocks.map((stock) => (
            <StockCard
              key={stock.id}
              stock={stock}
              onEdit={() => setEditStock(stock)}
              onRemove={() => wl.removeStock(stock.id)}
            />
          ))}
        </div>
      ) : viewMode === "sector" ? (
        <WatchlistSectorView
          stocks={processedStocks}
          onEdit={(stock) => setEditStock(stock)}
          onRemove={(id) => wl.removeStock(id)}
        />
      ) : (
        <div className="space-y-1.5">
          {/* Column headers */}
          <div className="flex items-center gap-3 px-4 py-1">
            <div className="w-8 flex-shrink-0" />
            <p className="glass-overline w-32 flex-shrink-0">Symbol</p>
            <p className="glass-overline w-24 flex-shrink-0 text-right hidden sm:block">Price</p>
            <p className="glass-overline w-24 flex-shrink-0 text-right hidden md:block">Change</p>
            <p className="glass-overline flex-1 hidden lg:block">Buy Target</p>
            <p className="glass-overline flex-1 hidden xl:block">Sell Target</p>
          </div>
          {processedStocks.map((stock) => (
            <StockListRow
              key={stock.id}
              stock={stock}
              onEdit={(s) => setEditStock(s)}
              onRemove={(id) => wl.removeStock(id)}
            />
          ))}
        </div>
      )}

      {/* ── Switching overlay ─────────────────────────────────────────────── */}
      {wl.isSwitching && (
        <div className="fixed inset-0 z-40 flex items-center justify-center pointer-events-none">
          <div className="glass-panel px-6 py-4 flex items-center gap-3 rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.5)]">
            <RefreshCw className="h-4 w-4 animate-spin text-indigo-400" />
            <span className="text-sm font-bold text-white/60">Switching watchlist…</span>
          </div>
        </div>
      )}

      {/* ── Modals ────────────────────────────────────────────────────────── */}
      {showCapNotice && <FullCapNotice onClose={() => setShowCapNotice(false)} />}

      <StockTargetDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onSave={(data) => wl.addStock(data.symbol, data.targetBuy, data.targetSell)}
        mode="add"
      />

      <StockTargetDialog
        open={!!editStock}
        onOpenChange={(open) => { if (!open) setEditStock(null); }}
        onSave={(data) => {
          if (editStock) wl.updateTargets(editStock.id, data.targetBuy, data.targetSell);
          setEditStock(null);
        }}
        mode="edit"
        initialData={
          editStock
            ? { symbol: editStock.symbol, targetBuy: editStock.targetBuy, targetSell: editStock.targetSell }
            : undefined
        }
      />
    </div>
  );
}