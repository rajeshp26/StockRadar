export type Stock = {
  id: string;
  symbol: string;
  name: string;
  price: number;
  change: number;
  changePercent: number;
  targetBuy: number | null;
  targetSell: number | null;
};
