// src/features/watchlists/services/watchlist.service.ts
import type { AxiosInstance } from "axios";
import api from "@/lib/api";
import type {
  WatchlistWithStocks,
  WatchlistMeta,
  CreateWatchlistInput,
  RenameWatchlistInput,
} from "../types/watchlist.types";

// Add near top with other interfaces
export interface StockSearchResult {
  symbol:   string;
  name:     string;
  exchange: string;
  type:     string;
}

// ── Existing input types (unchanged) ───────────────────────────────────────
export interface AddStockInput {
  watchlist_id: number;
  symbol:       string;
  target_buy:   number | null;
  target_sell:  number | null;
}

export interface UpdateStockInput {
  item_id:     number;
  target_buy:  number | null;
  target_sell: number | null;
}

/**
 * WatchlistService (axios-based)
 * - All calls go through Next proxy (/api/proxy/*)
 * - Identity is injected at the proxy; never pass tokens from the browser
 * - Cookies (__session) are sent by axios (withCredentials: true)
 */
export class WatchlistService {
  private readonly api: AxiosInstance;

  constructor(client?: AxiosInstance) {
    this.api = client ?? api;
  }

  // ── Existing methods (UNCHANGED) ─────────────────────────────────────────

  async getDefaultWatchlist(): Promise<WatchlistWithStocks> {
    const res = await this.api.post<WatchlistWithStocks>(
      "/watchlists/default-with-items",
      {},
    );
    return res.data;
  }

  async getDefaultWatchlistStructure(): Promise<WatchlistWithStocks> {
    const res = await this.api.post<WatchlistWithStocks>(
      "/watchlists/default-structure",
      {},
    );
    return res.data;
  }

  async addStock(input: AddStockInput) {
    const res = await this.api.post("/watchlist-items", input);
    return res.data;
  }

  async updateStockTargets(input: UpdateStockInput) {
    const { item_id, ...data } = input;
    const res = await this.api.patch(`/watchlist-items/${item_id}`, data);
    return res.data;
  }

  async removeStock(itemId: number): Promise<void> {
    await this.api.post(`/watchlist-items/delete`, { item_id: itemId });
  }

  getWatchlistStreamUrl(): string {
    return `/api/proxy/watchlists/stream`;
  }

  // ── New methods — multi-watchlist ─────────────────────────────────────────

  /**
   * List all watchlists for the authenticated user (lightweight, no stock items).
   * Returns WatchlistMeta[] including stock_count per list.
   */
  async getAllWatchlists(): Promise<WatchlistMeta[]> {
    const res = await this.api.get<{ watchlists: WatchlistMeta[] }>("/watchlists");
    return res.data.watchlists;
  }

  /**
   * Create a new watchlist.
   * Backend enforces: max 5 per user, unique name per user.
   */
  async createWatchlist(input: CreateWatchlistInput): Promise<WatchlistMeta> {
    const res = await this.api.post<WatchlistMeta>("/watchlists", { name: input.name });
    return res.data;
  }

  // Add inside WatchlistService class
  async searchStocks(query: string): Promise<StockSearchResult[]> {
    if (!query.trim()) return [];
    const res = await this.api.get<{ results: StockSearchResult[] }>(
        `/stocks/search?q=${encodeURIComponent(query.trim())}`,
    );
    return res.data.results ?? [];
  }

  /**
   * Rename a watchlist.
   * Backend enforces: ownership check, unique name constraint.
   */
  async renameWatchlist(input: RenameWatchlistInput): Promise<void> {
    await this.api.patch(`/watchlists/${input.watchlist_id}`, { name: input.name });
  }

  /**
   * Delete a watchlist.
   * Backend rules: cannot delete the default watchlist.
   * Cascade delete removes all watchlist_items automatically.
   */
  async deleteWatchlist(watchlistId: number): Promise<void> {
    await this.api.delete(`/watchlists/${watchlistId}`);
  }

  /**
   * Get structure (symbols + targets, no live prices) for a specific watchlist.
   * Used when switching the active watchlist.
   */
  async getWatchlistStructureById(watchlistId: number): Promise<WatchlistWithStocks> {
    const res = await this.api.post<WatchlistWithStocks>(
      `/watchlists/${watchlistId}/structure`,
      {},
    );
    return res.data;
  }
}

export const watchlistService = new WatchlistService();