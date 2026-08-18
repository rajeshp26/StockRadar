// web/src/features/analysis/hooks/useValuationStream.ts
//
// ─────────────────────────────────────────────────────────────────────────────
// DEPRECATED — do not add new call sites.
//
// Responsibilities moved to GlobalSSEProvider (src/providers/GlobalSSEProvider.tsx):
//   • valuation_ready events  → queryClient.invalidateQueries(QK.<method>)
//   • price_update events     → queryClient.setQueryData(QK.price(symbol))
//
// GlobalSSEProvider opens ONE connection for the entire authenticated session.
// This hook was opening a SECOND concurrent connection to the same endpoint.
//
// Existing call site removed: src/app/(authenticated)/analysis/[symbol]/page.tsx
// Safe to delete this file once no remaining imports exist.
//
//
// Listens to the existing /watchlists/stream SSE connection and invalidates
// React Query cache entries when the backend signals a valuation is ready.
//
// Design decisions:
//
//   1. Reuses the existing SSE stream — no second connection.
//      The stream already multiplexes price events. This hook adds a listener
//      for the new "valuation_ready" event type.
//
//   2. Uses queryClient.invalidateQueries() rather than setQueryData().
//      The backend computed the valuation asynchronously in a background task.
//      We don't have the payload here — we only know it's ready. Invalidating
//      causes React Query to refetch on next render, which picks up the result
//      via the existing GET cache-read endpoints. This is the correct pattern
//      for push-triggered cache invalidation.
//
//   3. Only invalidates when the symbol matches the current analysis page.
//      Events for other symbols (different watchlist stocks) are ignored.
//      This prevents unnecessary refetches on unrelated data.
//
//   4. Typed event routing — "price_update" events are passed through to the
//      existing price handler (if provided) so this hook is a drop-in addition
//      to the stream consumer, not a replacement.
//
//   5. Reconnect on error with exponential backoff — mirrors professional
//      SSE client patterns (Stripe, Pusher, etc.). Max backoff: 30 seconds.

"use client";

import { useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { QK } from "@/lib/query-keys";

// ── Method → query key mapping ────────────────────────────────────────────────
// Maps the backend method string to the React Query key factory.
// Must stay in sync with QK definitions and backend ALLOWED_METHODS.

const METHOD_TO_QK: Record<string, (symbol: string) => readonly unknown[]> = {
  rule1:           (s) => QK.rule1(s),
  dcf:             (s) => QK.dcf(s),
  ddm_gordon:      (s) => QK.ddm(s, "gordon"),
  ddm_two_stage:   (s) => QK.ddm(s, "two_stage"),
  owner_earnings:  (s) => QK.ownerEarnings(s),
  residual_income: (s) => QK.residualIncome(s),
};

// ── Hook ──────────────────────────────────────────────────────────────────────

export interface ValuationStreamOptions {
  /** The ticker symbol currently displayed on the analysis page. */
  symbol: string;
  /**
   * Optional: forward price_update events to an existing price handler.
   * Pass the handler from useLivePrice or any existing SSE consumer.
   */
  onPriceUpdate?: (event: PriceUpdateEvent) => void;
}

export interface PriceUpdateEvent {
  symbol:        string;
  price:         number;
  change:        number;
  changePercent: number;
  lastUpdated:   string;
}

export function useValuationStream({
  symbol,
  onPriceUpdate,
}: ValuationStreamOptions): void {
  const queryClient  = useQueryClient();
  const upperSymbol  = symbol.toUpperCase();
  const backoffRef   = useRef<number>(1_000);  // start at 1s
  const esRef        = useRef<EventSource | null>(null);
  const mountedRef   = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    function connect() {
      if (!mountedRef.current) return;

      // Reuse the existing watchlist stream endpoint.
      // Credentials are included so the server can verify the session cookie.
      const es = new EventSource("/api/proxy/watchlists/stream", {
        withCredentials: true,
      });
      esRef.current = es;

      es.onmessage = (event: MessageEvent) => {
        // Reset backoff on successful message
        backoffRef.current = 1_000;

        let data: Record<string, unknown>;
        try {
          data = JSON.parse(event.data as string);
        } catch {
          return; // keep-alive or malformed — ignore
        }

        const type = data.type as string | undefined;

        // ── Route: valuation_ready ─────────────────────────────────────────
        if (type === "valuation_ready") {
          const eventSymbol = (data.symbol as string | undefined)?.toUpperCase();
          const method      = data.method as string | undefined;

          // Only act on events for the symbol currently displayed
          if (eventSymbol !== upperSymbol || !method) return;

          const qkFactory = METHOD_TO_QK[method];
          if (!qkFactory) {
            // Unknown method — invalidate the summary which aggregates all methods
            queryClient.invalidateQueries({
              queryKey: QK.valuationSummary(upperSymbol),
            });
            return;
          }

          // Invalidate the specific method cache → triggers background refetch
          queryClient.invalidateQueries({
            queryKey: qkFactory(upperSymbol),
          });

          // Also invalidate the summary since a new method result is available
          queryClient.invalidateQueries({
            queryKey: QK.valuationSummary(upperSymbol),
          });

          return;
        }

        // ── Route: price_update ────────────────────────────────────────────
        if (type === "price_update" && onPriceUpdate) {
          onPriceUpdate(data as unknown as PriceUpdateEvent);
          return;
        }

        // ── Legacy: no type field (old price events before type was added) ──
        // Backward compat: if no type but has price field, treat as price event
        if (!type && typeof data.price === "number" && onPriceUpdate) {
          onPriceUpdate(data as unknown as PriceUpdateEvent);
        }
      };

      es.onerror = () => {
        if (!mountedRef.current) return;
        es.close();
        esRef.current = null;

        // Exponential backoff: 1s → 2s → 4s → 8s → 16s → 30s (cap)
        const delay = Math.min(backoffRef.current, 30_000);
        backoffRef.current = Math.min(backoffRef.current * 2, 30_000);

        setTimeout(() => {
          if (mountedRef.current) connect();
        }, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current = false;
      esRef.current?.close();
      esRef.current = null;
    };
  }, [upperSymbol, queryClient, onPriceUpdate]);
}