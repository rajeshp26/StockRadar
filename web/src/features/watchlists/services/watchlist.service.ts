// web/src/features/watchlists/services/watchlist.service.ts
import type { AxiosInstance } from "axios";
import api from "@/lib/api";
import type { WatchlistWithStocks } from "../types/watchlist.types";

export interface AddStockInput {
  watchlist_id: number;
  symbol: string;
  target_buy: number | null;
  target_sell: number | null;
}

export interface UpdateStockInput {
  item_id: number;
  target_buy: number | null;
  target_sell: number | null;
}

/**
 * WatchlistService (axios-based)
 * - All calls go through Next proxy (/api/proxy/*)
 * - Identity is injected at the proxy; never pass tokens from the browser
 * - Cookies (__session) are sent by axios (withCredentials: true) to enable proxy auth
 */
export class WatchlistService {
  private readonly api: AxiosInstance;

  /**
   * Default to the centralized api (withCredentials enforced).
   * Tests can inject a mock Axios instance.
   */
  constructor(client?: AxiosInstance) {
    this.api = client ?? api;
  }

  async getDefaultWatchlist(): Promise<WatchlistWithStocks> {
    // If backend supports GET, you may switch to GET here.
    const res = await this.api.post<WatchlistWithStocks>(
      "/watchlists/default-with-items",
      {}
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

  /**
   * SSE URL for real-time watchlist streaming.
   * Use on client:
   *   new EventSource(getWatchlistStreamUrl(), { withCredentials: true })
   */
  getWatchlistStreamUrl(): string {
    return `/api/proxy/watchlists/stream`;
  }
}

// Optional: a shared instance for convenience
export const watchlistService = new WatchlistService();