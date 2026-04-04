export type Stock = {
  id: number;
  symbol: string;
  name: string;
  sector: string | null;
  industry: string | null;
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
