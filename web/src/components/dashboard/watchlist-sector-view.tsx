"use client";
import { useMemo, useState, useCallback } from "react";
import { cn } from "@/lib/utils";
import { ChevronRight } from "lucide-react";
import type { StockPriceInfo } from "@/features/watchlists/types/watchlist.types";
import { StockListRow } from "./stock-list-row";

// ─── Types ────────────────────────────────────────────────────────────────────

interface SectorGroup {
  sector:    string;
  stocks:    StockPriceInfo[];
  isUnknown: boolean;
}

// ─── Constants ────────────────────────────────────────────────────────────────

// 11 distinct colours that read well against the dark glass surface.
// Assigned deterministically via hashSector() — same sector always gets same colour.
const SECTOR_DOTS = [
  "#818cf8", // indigo
  "#2dd4bf", // teal
  "#a78bfa", // violet
  "#fbbf24", // amber
  "#34d399", // emerald
  "#38bdf8", // sky
  "#fb923c", // orange
  "#f472b6", // pink
  "#fb7185", // rose
  "#22d3ee", // cyan
  "#a3e635", // lime
] as const;

// ─── Pure helpers ─────────────────────────────────────────────────────────────

// Stable, deterministic index from sector name — no random assignment on re-render.
function hashSector(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) {
    h = (h * 31 + name.charCodeAt(i)) & 0xffff;
  }
  return h;
}

// Groups stocks by sector. Known sectors sorted A→Z. Unknown always last.
function buildGroups(stocks: StockPriceInfo[]): SectorGroup[] {
  const UNKNOWN_KEY = "__unknown__";
  const map = new Map<string, StockPriceInfo[]>();

  for (const stock of stocks) {
    const key = stock.sector?.trim() || UNKNOWN_KEY;
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(stock);
  }

  return [...map.entries()]
    .map(([key, stocks]) => ({
      sector:    key === UNKNOWN_KEY ? "Unknown sector" : key,
      stocks,
      isUnknown: key === UNKNOWN_KEY,
    }))
    .sort((a, b) => {
      if (a.isUnknown) return  1;
      if (b.isUnknown) return -1;
      return a.sector.localeCompare(b.sector);
    });
}

// ─── Sector group header ──────────────────────────────────────────────────────

interface SectorGroupHeaderProps {
  group:    SectorGroup;
  dotColor: string;
  isOpen:   boolean;
  onToggle: () => void;
}

function SectorGroupHeader({
  group,
  dotColor,
  isOpen,
  onToggle,
}: SectorGroupHeaderProps) {
  // Struct-price avg change — same data source as the SummaryCard alert counts
  // in watchlist.tsx. Individual StockListRows show live prices via usePriceData.
  const avgChange = useMemo(() => {
    const valid = group.stocks.filter(
      (s) => s.changePercent != null && isFinite(s.changePercent),
    );
    if (!valid.length) return null;
    return valid.reduce((sum, s) => sum + s.changePercent, 0) / valid.length;
  }, [group.stocks]);

  // Struct-price alert counts — consistent with watchlist.tsx SummaryCard logic.
  const buyCount = useMemo(
    () =>
      group.stocks.filter(
        (s) => s.targetBuy != null && s.price != null && s.price <= s.targetBuy,
      ).length,
    [group.stocks],
  );
  const sellCount = useMemo(
    () =>
      group.stocks.filter(
        (s) => s.targetSell != null && s.price != null && s.price >= s.targetSell,
      ).length,
    [group.stocks],
  );

  return (
    <button
      onClick={onToggle}
      className={cn(
        "w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left",
        "glass-card transition-all duration-150",
        "hover:bg-white/[0.06]",
        group.isUnknown && "opacity-40",
      )}
    >
      {/* Expand/collapse indicator */}
      <ChevronRight
        className={cn(
          "h-3.5 w-3.5 text-white/30 flex-shrink-0 transition-transform duration-200",
          isOpen && "rotate-90",
        )}
      />

      {/* Deterministic sector colour dot */}
      <div
        className="h-2 w-2 rounded-full flex-shrink-0"
        style={{ backgroundColor: dotColor }}
      />

      {/* Sector name */}
      <span
        className={cn(
          "text-sm font-black tracking-tight",
          group.isUnknown ? "text-white/30" : "text-white",
        )}
      >
        {group.sector}
      </span>

      {/* Stock count badge */}
      <span className="text-[10px] font-bold text-white/25 bg-white/5 border border-white/8 rounded-full px-2 py-0.5 tabular-nums">
        {group.stocks.length}
      </span>

      {/* Avg change — struct price */}
      {avgChange != null && (
        <span
          className={cn(
            "text-xs font-bold tabular-nums",
            avgChange >= 0 ? "text-emerald-400" : "text-rose-400",
          )}
        >
          {avgChange >= 0 ? "+" : ""}
          {avgChange.toFixed(2)}%
        </span>
      )}

      {/* Alert pills — pushed to the right */}
      <div className="ml-auto flex items-center gap-2 flex-shrink-0">
        {buyCount > 0 && (
          <span
            className="glass-badge-buy"
            style={{ fontSize: "9px", padding: "2px 6px" }}
          >
            {buyCount} buy
          </span>
        )}
        {sellCount > 0 && (
          <span
            className="glass-badge-sell"
            style={{ fontSize: "9px", padding: "2px 6px" }}
          >
            {sellCount} sell
          </span>
        )}
      </div>
    </button>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

interface WatchlistSectorViewProps {
  stocks:   StockPriceInfo[];
  onEdit:   (stock: StockPriceInfo) => void;
  onRemove: (id: number) => void;
}

export function WatchlistSectorView({
  stocks,
  onEdit,
  onRemove,
}: WatchlistSectorViewProps) {
  const groups = useMemo(() => buildGroups(stocks), [stocks]);

  // All groups open by default. Not persisted to sessionStorage — collapse state
  // becomes stale when stocks are added/removed between visits, and the sector
  // view is most useful with all groups visible at once.
  const [openGroups, setOpenGroups] = useState<Set<string>>(
    () => new Set(groups.map((g) => g.sector)),
  );

  const toggleGroup = useCallback((sector: string) => {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(sector)) next.delete(sector);
      else next.add(sector);
      return next;
    });
  }, []);

  if (!groups.length) return null;

  return (
    <div className="space-y-1.5">
      {groups.map((group) => {
        const dotColor = SECTOR_DOTS[hashSector(group.sector) % SECTOR_DOTS.length];
        const isOpen   = openGroups.has(group.sector);

        return (
          <div key={group.sector}>
            <SectorGroupHeader
              group={group}
              dotColor={dotColor}
              isOpen={isOpen}
              onToggle={() => toggleGroup(group.sector)}
            />

            {isOpen && (
              <div className="mt-1 ml-5 space-y-1">
                {/* Column headers — scoped inside each open group so they
                    align precisely with the indented StockListRow content */}
                <div className="flex items-center gap-3 px-4 py-1">
                  <div className="w-8 flex-shrink-0" />
                  <p className="glass-overline w-32 flex-shrink-0">Symbol</p>
                  <p className="glass-overline w-24 flex-shrink-0 text-right hidden sm:block">Price</p>
                  <p className="glass-overline w-24 flex-shrink-0 text-right hidden md:block">Change</p>
                  <p className="glass-overline flex-1 hidden lg:block">Buy Target</p>
                  <p className="glass-overline flex-1 hidden xl:block">Sell Target</p>
                </div>

                {group.stocks.map((stock) => (
                  <StockListRow
                    key={stock.id}
                    stock={stock}
                    onEdit={onEdit}
                    onRemove={onRemove}
                  />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}