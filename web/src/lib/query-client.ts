// web/src/lib/query-client.ts
import { QueryClient } from "@tanstack/react-query";

// ─────────────────────────────────────────────────────────────────────────────
// Stale-time constants (ms)
// Data is served from cache without a network request while within stale time.
// ─────────────────────────────────────────────────────────────────────────────
export const STALE = {
  VALUATION:  10 * 60 * 1_000,  // 10 min — Rule #1 / DCF / DDM results
  HISTORY:    15 * 60 * 1_000,  // 15 min — historical snapshots
  PRICE:           30 * 1_000,  // 30 sec — live quote
  WATCHLIST:   2 * 60 * 1_000,  // 2 min  — watchlist structure
  LISTS:       5 * 60 * 1_000,  // 5 min  — all-watchlists metadata
} as const;

// ─────────────────────────────────────────────────────────────────────────────
// GC-time constants (ms)
// Data is kept in memory even after ALL components using it have unmounted.
// This is the key fix: navigating away and back serves data instantly.
// ─────────────────────────────────────────────────────────────────────────────
export const GC = {
  VALUATION:  30 * 60 * 1_000,  // 30 min
  HISTORY:    60 * 60 * 1_000,  // 60 min
  PRICE:       5 * 60 * 1_000,  // 5 min
  WATCHLIST:  10 * 60 * 1_000,  // 10 min
  LISTS:      15 * 60 * 1_000,  // 15 min
} as const;

/**
 * Factory — called once per app lifecycle via ReactQueryProvider.
 * Defaults are conservative: callers opt-in to refetchOnWindowFocus
 * per hook where it makes sense (e.g. live price, not valuations).
 */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry:                1,
        retryDelay:         500,
        refetchOnWindowFocus: false,  // hooks opt-in explicitly
        throwOnError:        false,   // don't bubble to ErrorBoundary by default
      },
    },
  });
}