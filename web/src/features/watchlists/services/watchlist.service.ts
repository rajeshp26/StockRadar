import { AxiosInstance } from 'axios';
import { WatchlistWithStocks } from '../types/watchlist.types';

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

export class WatchlistService {
  private readonly api: AxiosInstance;

  constructor(api: AxiosInstance) {
    this.api = api;
  }

  async getDefaultWatchlist(): Promise<WatchlistWithStocks> {
    // SECURITY: We no longer send firebase_uid in the body.
    // The api client (Axios interceptor) attaches the ID Token automatically.
    const response = await this.api.post<WatchlistWithStocks>('/watchlists/default-with-items', {});
    return response.data;
  }

  async addStock(input: AddStockInput): Promise<any> {
    const response = await this.api.post('/watchlist-items', input);
    return response.data;
  }

  async updateStockTargets(input: UpdateStockInput): Promise<any> {
    const { item_id, ...data } = input;
    const response = await this.api.patch(`/watchlist-items/${item_id}`, data);
    return response.data;
  }

  async removeStock(itemId: number): Promise<void> {
    await this.api.post(`/watchlist-items/delete`, {
      item_id: itemId,
    });
  }

  async getWatchlistStreamUrl(idToken: string): Promise<string> {
    // SSE requires token in URL as headers are not supported by EventSource
    return `/api/proxy/watchlists/stream?token=${idToken}`;
  }
}
