export type Stock = {
  id: number;
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  targetBuy: number | null;
  targetSell: number | null;
  lastUpdated?: string;
};

export type WatchlistItem = {
  id: number;
  userId: string;
  symbol: string;
  targetBuy: number | null;
  targetSell: number | null;
};
