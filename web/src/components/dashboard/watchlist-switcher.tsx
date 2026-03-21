"use client";
import { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { cn } from "@/lib/utils";
import { Check, ChevronDown, Plus, Trash2, Star, AlertTriangle } from "lucide-react";
import type { WatchlistMeta } from "@/features/watchlists/types/watchlist.types";
import { WATCHLIST_LIMITS } from "@/features/watchlists/types/watchlist.types";

interface WatchlistSwitcherProps {
  allWatchlists:    WatchlistMeta[];
  activeId:         number | null;
  isListCapReached: boolean;
  isCreating:       boolean;
  isDeleting:       boolean;
  onSwitch:         (id: number) => void;
  onCreate:         (name: string) => void;
  onDelete:         (id: number) => void;
}

export function WatchlistSwitcher({
  allWatchlists,
  activeId,
  isListCapReached,
  isCreating,
  isDeleting,
  onSwitch,
  onCreate,
  onDelete,
}: WatchlistSwitcherProps) {
  const [open,          setOpen]          = useState(false);
  const [creating,      setCreating]      = useState(false);
  const [newName,       setNewName]       = useState("");
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  // ── Portal positioning ────────────────────────────────────────────────────
  // The dropdown is rendered into document.body via a portal so it escapes
  // any parent stacking context (backdrop-filter, transform, isolation).
  // Position is calculated from the trigger button's bounding rect.
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});

  const triggerRef   = useRef<HTMLButtonElement>(null);
  const dropdownRef  = useRef<HTMLDivElement>(null);
  const inputRef     = useRef<HTMLInputElement>(null);

  const activeList = allWatchlists.find((w) => w.watchlist_id === activeId);

  // Recalculate dropdown position whenever it opens or the window resizes/scrolls
  const updatePosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    setDropdownStyle({
      position: "fixed",
      top:      rect.bottom + 8,
      left:     rect.left,
      width:    288, // w-72
      zIndex:   9999,
    });
  }, []);

  useEffect(() => {
    if (!open) return;
    updatePosition();
    window.addEventListener("resize",  updatePosition);
    window.addEventListener("scroll",  updatePosition, true);
    return () => {
      window.removeEventListener("resize",  updatePosition);
      window.removeEventListener("scroll",  updatePosition, true);
    };
  }, [open, updatePosition]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      const target = e.target as Node;
      const clickedTrigger  = triggerRef.current?.contains(target);
      const clickedDropdown = dropdownRef.current?.contains(target);
      if (!clickedTrigger && !clickedDropdown) {
        setOpen(false);
        setCreating(false);
        setNewName("");
        setConfirmDelete(null);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  // Focus input when create form opens
  useEffect(() => {
    if (creating) inputRef.current?.focus();
  }, [creating]);

  const handleCreate = useCallback(() => {
    const name = newName.trim();
    if (!name) return;
    onCreate(name);
    setNewName("");
    setCreating(false);
    setOpen(false);
  }, [newName, onCreate]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter")  handleCreate();
      if (e.key === "Escape") { setCreating(false); setNewName(""); }
    },
    [handleCreate],
  );

  const handleDeleteClick = useCallback(
    (e: React.MouseEvent, id: number) => {
      e.stopPropagation();
      setConfirmDelete((prev) => (prev === id ? null : id));
    },
    [],
  );

  const handleConfirmDelete = useCallback(
    (e: React.MouseEvent, id: number) => {
      e.stopPropagation();
      onDelete(id);
      setConfirmDelete(null);
      setOpen(false);
    },
    [onDelete],
  );

  // ── Dropdown content ──────────────────────────────────────────────────────
  const dropdownContent = open ? (
    <div
      ref={dropdownRef}
      style={dropdownStyle}
      className={cn(
        "glass-panel rounded-2xl overflow-hidden",
        "shadow-[0_20px_60px_rgba(0,0,0,0.5)] bg-[#0d1117]",
        "animate-fade-up",
      )}
    >
      {/* Header */}
      <div className="px-4 pt-4 pb-2">
        <p className="glass-overline">Your Watchlists</p>
      </div>

      {/* Watchlist items */}
      <div className="max-h-64 overflow-y-auto">
        {allWatchlists.map((wl) => {
          const isActive     = wl.watchlist_id === activeId;
          const isFull       = wl.stock_count >= WATCHLIST_LIMITS.MAX_STOCKS;
          const isDefault    = wl.is_default;
          const isConfirming = confirmDelete === wl.watchlist_id;

          return (
            <div
              key={wl.watchlist_id}
              onClick={() => {
                if (!isActive) {
                  onSwitch(wl.watchlist_id);
                  setOpen(false);
                }
              }}
              className={cn(
                "flex items-center gap-3 px-4 py-3 cursor-pointer transition-colors",
                isActive
                  ? "bg-indigo-500/10 border-l-2 border-indigo-500"
                  : "hover:bg-white/5 border-l-2 border-transparent",
              )}
              role="option"
              aria-selected={isActive}
            >
              {/* Active check / default star */}
              <div className="w-4 flex-shrink-0">
                {isActive
                  ? <Check className="h-3.5 w-3.5 text-indigo-400" />
                  : isDefault
                  ? <Star  className="h-3 w-3 text-white/20" />
                  : null
                }
              </div>

              {/* Name + capacity bar */}
              <div className="flex-1 min-w-0">
                <p className={cn(
                  "text-sm font-bold truncate",
                  isActive ? "text-white" : "text-white/60",
                )}>
                  {wl.name}
                </p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <div className="h-1 w-20 rounded-full bg-white/8 overflow-hidden">
                    <div
                      className={cn(
                        "h-1 rounded-full transition-all",
                        isFull ? "bg-rose-500" : "bg-indigo-500/60",
                      )}
                      style={{
                        width: `${(wl.stock_count / WATCHLIST_LIMITS.MAX_STOCKS) * 100}%`,
                      }}
                    />
                  </div>
                  <span className={cn(
                    "text-[10px] font-bold tabular-nums",
                    isFull ? "text-rose-400" : "text-white/25",
                  )}>
                    {wl.stock_count}/{WATCHLIST_LIMITS.MAX_STOCKS}
                  </span>
                </div>
              </div>

              {/* Delete (non-default lists only) */}
              {!isDefault && (
                <div className="flex-shrink-0 flex items-center gap-1">
                  {isConfirming ? (
                    <>
                      <button
                        onClick={(e) => handleConfirmDelete(e, wl.watchlist_id)}
                        className="px-2 py-0.5 rounded-lg bg-rose-500/20 border border-rose-500/30 text-[10px] font-black text-rose-400 hover:bg-rose-500/30"
                        disabled={isDeleting}
                      >
                        Delete
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setConfirmDelete(null); }}
                        className="px-2 py-0.5 rounded-lg bg-white/5 border border-white/10 text-[10px] font-black text-white/40 hover:bg-white/10"
                      >
                        Cancel
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={(e) => handleDeleteClick(e, wl.watchlist_id)}
                      className="h-6 w-6 flex items-center justify-center rounded-lg hover:bg-rose-500/10 text-white/20 hover:text-rose-400 transition-colors"
                      aria-label={`Delete ${wl.name}`}
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Divider */}
      <div className="glass-divider mx-4" />

      {/* Create new section */}
      <div className="px-4 py-3">
        {creating ? (
          <div className="flex items-center gap-2">
            <input
              ref={inputRef}
              value={newName}
              onChange={(e) =>
                setNewName(e.target.value.slice(0, WATCHLIST_LIMITS.MAX_NAME_LENGTH))
              }
              onKeyDown={handleKeyDown}
              placeholder="Watchlist name…"
              maxLength={WATCHLIST_LIMITS.MAX_NAME_LENGTH}
              className={cn(
                "flex-1 px-3 py-2 rounded-xl text-sm font-medium text-white",
                "bg-white/5 border border-white/10 placeholder:text-white/20",
                "focus:outline-none focus:border-indigo-500/60 focus:ring-2 focus:ring-indigo-500/15",
              )}
            />
            <button
              onClick={handleCreate}
              disabled={!newName.trim() || isCreating}
              className={cn(
                "px-3 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all",
                newName.trim() && !isCreating
                  ? "bg-indigo-600 text-white hover:bg-indigo-500"
                  : "bg-white/5 text-white/20 cursor-not-allowed",
              )}
            >
              {isCreating ? "…" : "Add"}
            </button>
          </div>
        ) : isListCapReached ? (
          <div className="flex items-center gap-2 text-[10px] text-white/25">
            <AlertTriangle className="h-3 w-3 text-amber-500/50 flex-shrink-0" />
            <span>Maximum {WATCHLIST_LIMITS.MAX_WATCHLISTS} watchlists reached</span>
          </div>
        ) : (
          <button
            onClick={() => setCreating(true)}
            className={cn(
              "w-full flex items-center gap-2 px-3 py-2 rounded-xl",
              "text-sm font-bold text-indigo-400 hover:text-indigo-300",
              "hover:bg-indigo-500/8 transition-colors",
            )}
          >
            <Plus className="h-4 w-4" />
            Create New Watchlist
          </button>
        )}
      </div>
    </div>
  ) : null;

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <>
      {/* Trigger button — stays in normal document flow */}
      <button
        ref={triggerRef}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "flex items-center gap-2 px-4 py-2 rounded-xl",
          "glass-btn text-sm font-black text-white tracking-tight",
          "max-w-[220px]",
          open && "bg-white/10 border-white/15",
        )}
        aria-haspopup="listbox"
        aria-expanded={open}
      >
        <span className="truncate">
          {activeList?.name ?? "My Watchlist"}
        </span>
        {activeList && (
          <span className="text-[10px] font-bold text-white/30 flex-shrink-0 tabular-nums">
            {activeList.stock_count}/{WATCHLIST_LIMITS.MAX_STOCKS}
          </span>
        )}
        <ChevronDown
          className={cn(
            "h-3 w-3 text-white/40 flex-shrink-0 transition-transform",
            open && "rotate-180",
          )}
        />
      </button>

      {/* Dropdown — rendered into document.body via portal, escaping all
          stacking contexts created by backdrop-filter / transform on ancestors */}
      {typeof document !== "undefined" &&
        createPortal(dropdownContent, document.body)}
    </>
  );
}