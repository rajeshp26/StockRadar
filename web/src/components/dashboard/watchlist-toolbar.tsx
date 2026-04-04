"use client";

import { useCallback, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { Search, X, ArrowUpDown, LayoutGrid, List, Layers, ChevronDown } from "lucide-react";
import { WATCHLIST_LIMITS } from "@/features/watchlists/types/watchlist.types";

export type SortKey =
  | "default"
  | "symbol_asc"
  | "symbol_desc"
  | "price_desc"
  | "price_asc"
  | "change_desc"
  | "change_asc"
  | "buy_gap_asc";

export type ViewMode = "grid" | "list" | "sector";

const SORT_OPTIONS: { key: SortKey; label: string }[] = [
  { key: "default",     label: "Date Added"          },
  { key: "symbol_asc",  label: "Symbol A → Z"        },
  { key: "symbol_desc", label: "Symbol Z → A"        },
  { key: "price_desc",  label: "Price: High → Low"   },
  { key: "price_asc",   label: "Price: Low → High"   },
  { key: "change_desc", label: "Best Performers"      },
  { key: "change_asc",  label: "Worst Performers"     },
  { key: "buy_gap_asc", label: "Closest to Buy Target"},
];

interface WatchlistToolbarProps {
  // Search
  searchQuery:       string;
  onSearchChange:    (q: string) => void;
  // Sort
  sortKey:           SortKey;
  onSortChange:      (k: SortKey) => void;
  sortOpen:          boolean;
  onSortOpenChange:  (v: boolean) => void;
  // View
  viewMode:          ViewMode;
  onViewModeChange:  (m: ViewMode) => void;
  // Result info
  visibleCount:      number;
  totalCount:        number;
  stockCount:        number;
  isWatchlistFull:   boolean;
  // Filter clear
  hasActiveFilters:  boolean;
  onClearFilters:    () => void;
  // Alert quick-filter (from existing summary cards)
  alertFilter:       "all" | "buy" | "sell";
}

export function WatchlistToolbar({
  searchQuery, onSearchChange,
  sortKey, onSortChange, sortOpen, onSortOpenChange,
  viewMode, onViewModeChange,
  visibleCount, totalCount, stockCount, isWatchlistFull,
  hasActiveFilters, onClearFilters,
  alertFilter,
}: WatchlistToolbarProps) {
  const sortRef  = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Close sort dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (sortRef.current && !sortRef.current.contains(e.target as Node)) {
        onSortOpenChange(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [onSortOpenChange]);

  // Keyboard shortcut: "/" focuses search
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "/" && document.activeElement?.tagName !== "INPUT") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  const activeSortLabel = SORT_OPTIONS.find((o) => o.key === sortKey)?.label ?? "Sort";

  const isFiltered = searchQuery.trim() !== "" || alertFilter !== "all";
  const showResultCount = isFiltered || totalCount > 10;

  const capacityPct = (stockCount / WATCHLIST_LIMITS.MAX_STOCKS) * 100;
  const showCapWarning = stockCount >= 40; // show at 40/50

  return (
    <div className="space-y-2">
      {/* ── Main toolbar row ─────────────────────────────────────────────── */}
      <div className="flex items-center gap-2">

        {/* Search */}
        <div className="relative flex-1 min-w-0 max-w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-white/25 pointer-events-none" />
          <input
            ref={searchRef}
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder='Search stocks… ("/" to focus)'
            className={cn(
              "w-full pl-9 pr-8 py-2.5 rounded-xl text-sm font-medium",
              "bg-white/5 border border-white/8 text-white",
              "placeholder:text-white/20",
              "focus:outline-none focus:border-indigo-500/50 focus:ring-2 focus:ring-indigo-500/10",
              "transition-all",
            )}
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-white/25 hover:text-white/60 transition-colors"
              aria-label="Clear search"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Sort dropdown */}
        <div ref={sortRef} className="relative">
          <button
            onClick={() => onSortOpenChange(!sortOpen)}
            className={cn(
              "glass-btn flex items-center gap-2 px-3 py-2.5 rounded-xl",
              "text-[10px] font-black uppercase tracking-widest whitespace-nowrap",
              sortOpen && "bg-white/10 border-white/15",
            )}
          >
            <ArrowUpDown className="h-3 w-3 text-white/40" />
            <span className="hidden sm:inline">{activeSortLabel}</span>
            <ChevronDown className={cn("h-3 w-3 text-white/30 transition-transform", sortOpen && "rotate-180")} />
          </button>

          {sortOpen && (
            <div className={cn(
              "absolute right-0 top-full mt-2 z-40 w-52",
              "glass-panel rounded-2xl py-2 shadow-[0_20px_60px_rgba(0,0,0,0.5)]",
              "animate-fade-up",
            )}>
              {SORT_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  onClick={() => { onSortChange(opt.key); onSortOpenChange(false); }}
                  className={cn(
                    "w-full flex items-center gap-3 px-4 py-2.5 text-xs font-bold text-left transition-colors",
                    sortKey === opt.key
                      ? "text-indigo-400 bg-indigo-500/8"
                      : "text-white/50 hover:text-white hover:bg-white/5",
                  )}
                >
                  {sortKey === opt.key && <span className="h-1 w-1 rounded-full bg-indigo-400 flex-shrink-0" />}
                  {sortKey !== opt.key && <span className="h-1 w-1 flex-shrink-0" />}
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* View toggle */}
        <div className="flex items-center bg-white/5 border border-white/8 rounded-xl p-1 gap-0.5">
          <button
            onClick={() => onViewModeChange("grid")}
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-lg transition-all",
              viewMode === "grid"
                ? "bg-white/15 text-white"
                : "text-white/25 hover:text-white/60",
            )}
            aria-label="Grid view"
            aria-pressed={viewMode === "grid"}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onViewModeChange("list")}
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-lg transition-all",
              viewMode === "list"
                ? "bg-white/15 text-white"
                : "text-white/25 hover:text-white/60",
            )}
            aria-label="List view"
            aria-pressed={viewMode === "list"}
          >
            <List className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onViewModeChange("sector")}
            className={cn(
              "h-7 w-7 flex items-center justify-center rounded-lg transition-all",
              viewMode === "sector"
                ? "bg-white/15 text-white"
                : "text-white/25 hover:text-white/60",
            )}
            aria-label="Sector view"
            aria-pressed={viewMode === "sector"}
          >
            <Layers className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* ── Result count + cap indicator ─────────────────────────────────── */}
      {(showResultCount || showCapWarning) && (
        <div className="flex items-center justify-between">
          {showResultCount ? (
            <div className="flex items-center gap-3">
              <span className="text-[10px] text-white/30 font-medium">
                Showing{" "}
                <span className="text-white/60 font-black">{visibleCount}</span>
                {" "}of{" "}
                <span className="text-white/60 font-black">{totalCount}</span>
                {" "}stocks
              </span>
              {hasActiveFilters && (
                <button
                  onClick={onClearFilters}
                  className="text-[10px] font-black uppercase tracking-widest text-indigo-400 hover:text-indigo-300 transition-colors"
                >
                  Clear filters
                </button>
              )}
            </div>
          ) : (
            <div /> // spacer
          )}

          {/* Capacity indicator — only at 40+ */}
          {showCapWarning && (
            <div className="flex items-center gap-2">
              <div className="h-1 w-20 rounded-full bg-white/8 overflow-hidden">
                <div
                  className={cn(
                    "h-1 rounded-full transition-all",
                    isWatchlistFull ? "bg-rose-500" : stockCount >= 45 ? "bg-amber-500" : "bg-indigo-500/60",
                  )}
                  style={{ width: `${Math.min(100, capacityPct)}%` }}
                />
              </div>
              <span className={cn(
                "text-[10px] font-black tabular-nums",
                isWatchlistFull   ? "text-rose-400"
                : stockCount >= 45 ? "text-amber-400"
                :                   "text-white/25",
              )}>
                {stockCount}/{WATCHLIST_LIMITS.MAX_STOCKS}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}