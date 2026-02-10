"use client";

import { useMemo } from "react";
import { useWatchlist } from "@/features/watchlists/hooks/useWatchlist";

/**
 * Returns live price info for a symbol from the watchlist state.
 * Assumes the symbol is present in the user's watchlist.
 */
export function useLivePrice(symbol: string): {
  price: number | null;
  change: number | null;
  changePercent: number | null;
  lastUpdated: string | null;
} {
  const { stocks } = useWatchlist();

  const upper = (symbol ?? "").toUpperCase();
  return useMemo(() => {
    const s = stocks.find((x) => x.symbol === upper);
    return {
      price: s?.price ?? null,
      change: s?.change ?? null,
      changePercent: s?.changePercent ?? null,
      lastUpdated: (s?.lastUpdated as string) ?? null,
    };
  }, [stocks, upper]);
}
