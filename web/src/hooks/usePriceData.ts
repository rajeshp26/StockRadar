// web/src/hooks/usePriceData.ts
//
// Pure cache subscriber — never fetches independently.
//
// Data flow:
//   GlobalSSEProvider (SSE event)
//     → queryClient.setQueryData(QK.price(symbol), payload)
//       → usePriceData re-renders all subscribers instantly
//
// On return navigation (within gcTime 5 min):
//   Cache still has the last-known price → component renders with real prices
//   on the FIRST paint, zero "Price updating…" flash.
//
// On first visit / cache miss:
//   Returns null until GlobalSSEProvider pushes the first price event for
//   this symbol. Components render their "—" / "Price updating…" placeholder
//   exactly as before — no regression.
"use client";

import { useQuery } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { GC } from "@/lib/query-client";
import type { CachedPrice } from "@/providers/GlobalSSEProvider";

/**
 * Reactively reads the most recent price snapshot for a symbol from the
 * shared React Query cache.
 *
 * @param symbol  Ticker symbol (case-insensitive).
 * @returns       CachedPrice when the cache has data, null otherwise.
 */
export function usePriceData(symbol: string): CachedPrice | null {
  const upper = (symbol ?? "").toUpperCase().trim();

  const { data } = useQuery<CachedPrice | null>({
    queryKey: QK.price(upper),
    // queryFn is never called — enabled: false prevents all auto-fetching.
    // We keep a no-op fn to satisfy TypeScript; React Query never invokes it.
    queryFn:  () => Promise.resolve(null),
    enabled:  false,    // GlobalSSEProvider is the only writer; we only read
    staleTime: Infinity, // data is never stale from this hook's perspective
    gcTime:    GC.PRICE, // 5 min — survives normal navigation back/forth
    // Return null (not undefined) when cache is empty so callers can use
    // simple `priceData?.price ?? null` without undefined guards.
    placeholderData: null,
  });

  return data ?? null;
}