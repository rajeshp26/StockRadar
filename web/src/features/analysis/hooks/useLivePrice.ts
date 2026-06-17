// web/src/features/analysis/hooks/useLivePrice.ts
"use client";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";
import { STALE, GC } from "@/lib/query-client";
import { useSSEStatus } from "@/providers/GlobalSSEProvider";

type Quote = {
  symbol:        string;
  currency?:     string | null;
  price:         number | null;
  change:        number | null;
  changePercent: number | null;
  lastUpdated:   string | null;
};

// ─────────────────────────────────────────────────────────────────────────────
// Hook
//
// Return contract is IDENTICAL to the original — no callers need changes.
//
// Key improvements over the original manual useEffect + setInterval approach:
//
//   1. Tab-visibility aware polling
//      refetchIntervalInBackground: false means the 30-second poll pauses
//      automatically when the user switches browser tabs, and resumes the
//      moment they return. No wasted requests in background tabs.
//
//   2. Request deduplication
//      If multiple components mount with the same symbol simultaneously,
//      React Query issues exactly ONE network request and shares the result.
//
//   3. Stale-while-revalidate on tab focus
//      When the user returns to the tab after more than 30s, they instantly
//      see the last known price while a fresh fetch runs in the background.
//
//   4. Adaptive SSE polling (NEW)
//      When the GlobalSSEProvider connection is healthy, the 30s HTTP poll
//      is disabled entirely — price data arrives via SSE push. If SSE
//      disconnects, the HTTP poll activates automatically as a fallback.
//      This eliminates redundant network traffic while maintaining resilience.
//
//   5. No manual cancelled flag or clearInterval bookkeeping needed.
// ─────────────────────────────────────────────────────────────────────────────

export function useLivePrice(symbol: string): {
  price:         number | null;
  change:        number | null;
  changePercent: number | null;
  lastUpdated:   string | null;
  currency:      string | null;
  loading:       boolean;
  error:         string | null;
} {
  const upper = (symbol ?? "").toUpperCase().trim();
  const { isConnected: sseConnected } = useSSEStatus();

  const { data, isPending, error } = useQuery<Quote, Error>({
    queryKey: QK.price(upper),
    queryFn:  async () => {
      const res = await fetch(`/api/proxy/stocks/${upper}/quote`, {
        method: "GET",
        cache:  "no-store",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.detail ?? `Failed to load price (${res.status})`);
      }
      return res.json() as Promise<Quote>;
    },
    enabled:                     !!upper,
    staleTime:                   STALE.PRICE,          // 30s
    gcTime:                      GC.PRICE,             // 5 min
    refetchInterval:             sseConnected ? false : STALE.PRICE,  // disable poll when SSE is connected
    refetchIntervalInBackground: false,                // pause when tab is hidden
    retry:                       1,
  });

  // useMemo preserved from original to maintain stable object reference
  return useMemo(
    () => ({
      price:         data?.price         ?? null,
      change:        data?.change        ?? null,
      changePercent: data?.changePercent ?? null,
      lastUpdated:   data?.lastUpdated   ?? null,
      currency:      (data?.currency as string) ?? null,
      loading:       isPending,
      error:         error?.message ?? null,
    }),
    [data, isPending, error],
  );
}