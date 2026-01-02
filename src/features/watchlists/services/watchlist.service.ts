import { AxiosInstance } from 'axios';
import { WatchlistWithStocks, StockPriceInfo } from '../types/watchlist.types';

export interface AddStockInput {
  firebase_uid: string;
  watchlist_id: number;
  symbol: string;
  target_buy: number | null;
  target_sell: number | null;
}

export interface UpdateStockInput {
  firebase_uid: string;
  item_id: number;
  target_buy: number | null;
  target_sell: number | null;
}

export class WatchlistService {
  private readonly api: AxiosInstance;

  constructor(api: AxiosInstance) {
    this.api = api;
  }

  async getDefaultWatchlist(firebaseUid: string): Promise<WatchlistWithStocks> {
    const response = await this.api.post<WatchlistWithStocks>('/watchlists/default-with-items', {
      firebase_uid: firebaseUid,
    });
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

  async removeStock(firebaseUid: string, itemId: number): Promise<void> {
    await this.api.post(`/watchlist-items/delete`, {
      firebase_uid: firebaseUid,
      item_id: itemId,
    });
  }

  getWatchlistStreamUrl(firebaseUid: string): string {
    return `/api/proxy/watchlists/stream?firebase_uid=${firebaseUid}`;
  }
}
