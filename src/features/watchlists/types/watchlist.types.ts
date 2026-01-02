export interface StockPriceInfo {
  id: number;
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  targetBuy: number | null;
  targetSell: number | null;
  lastUpdated: string | null;
}

export interface WatchlistWithStocks {
  watchlist_id: number;
  name: string;
  is_default: boolean;
  stocks: StockPriceInfo[];
}
