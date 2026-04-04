// src/features/watchlists/types/watchlist.types.ts

export const WATCHLIST_LIMITS = {
  MAX_STOCKS:      50,
  MAX_WATCHLISTS:  5,
  MAX_NAME_LENGTH: 50,
} as const;

// ── Existing types (unchanged) ──────────────────────────────────────────────
export interface StockPriceInfo {
  id:            number;
  symbol:        string;
  name:          string;
  sector:        string | null;
  industry:      string | null;
  price:         number;
  change:        number;
  changePercent: number;
  targetBuy:     number | null;
  targetSell:    number | null;
  lastUpdated:   string | null;
}

// ── Updated: stock_count added (backend already returns it from list endpoint)
export interface WatchlistWithStocks {
  watchlist_id: number;
  name:         string;
  is_default:   boolean;
  stock_count:  number;   // NEW — denormalised count, used for cap display
  stocks:       StockPriceInfo[];
}

// ── New: lightweight list item for the watchlist switcher ───────────────────
export interface WatchlistMeta {
  watchlist_id: number;
  name:         string;
  is_default:   boolean;
  stock_count:  number;
}

// ── New: service input types ────────────────────────────────────────────────
export interface CreateWatchlistInput {
  name: string;
}

export interface RenameWatchlistInput {
  watchlist_id: number;
  name:         string;
}