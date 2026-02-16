"use client";

import { useEffect, useMemo, useState } from "react";

type Quote = {
  symbol: string;
  currency?: string | null;
  price: number | null;
  change: number | null;
  changePercent: number | null;
  lastUpdated: string | null;
};

/**
 * Symbol-scoped live price hook (Phase 3)
 *
 * IMPORTANT:
 * - Must NOT depend on watchlist state (Option B).
 * - Fetches a lightweight quote via proxy: /api/proxy/stocks/{symbol}/quote
 * - Polls periodically for updates; Watchlist SSE remains watchlist-only.
 */
export function useLivePrice(symbol: string): {
  price: number | null;
  change: number | null;
  changePercent: number | null;
  lastUpdated: string | null;
  currency: string | null;
  loading: boolean;
  error: string | null;
} {
  const upper = (symbol ?? "").toUpperCase().trim();

  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState<boolean>(!!upper);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!upper) return;

    let cancelled = false;
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const fetchQuote = async () => {
      try {
        if (!cancelled) {
          setLoading(true);
          setError(null);
        }

        const res = await fetch(`/api/proxy/stocks/${upper}/quote`, {
          method: "GET",
          cache: "no-store",
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          const msg = body?.detail || `Failed to load price (${res.status})`;
          throw new Error(msg);
        }

        const data = (await res.json()) as Quote;

        if (!cancelled) {
          setQuote(data);
        }
      } catch (e: any) {
        if (!cancelled) {
          setError(e?.message ?? "Failed to load price");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    // Initial fetch immediately
    void fetchQuote();

    // Poll (lightweight) — tune this later if needed
    intervalId = setInterval(() => {
      void fetchQuote();
    }, 10_000);

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
    };
  }, [upper]);

  return useMemo(() => {
    return {
      price: quote?.price ?? null,
      change: quote?.change ?? null,
      changePercent: quote?.changePercent ?? null,
      lastUpdated: quote?.lastUpdated ?? null,
      currency: (quote?.currency as string) ?? null,
      loading,
      error,
    };
  }, [quote, loading, error]);
}