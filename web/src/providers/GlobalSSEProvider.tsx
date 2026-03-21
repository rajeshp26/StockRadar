// web/src/providers/GlobalSSEProvider.tsx
//
// One EventSource for the entire authenticated session.
//
// Responsibilities (previously split across two hooks):
//   1. price_update events  → setQueryData(QK.price(symbol))
//      Previously: useWatchlist owned an EventSource and patched local stocks[] state.
//      Now: prices live in the React Query cache, survive navigation, instantly
//      available on back-navigation without waiting for a new SSE connection.
//
//   2. valuation_ready events → invalidateQueries(QK.<method>(symbol))
//      Previously: useValuationStream opened a SECOND connection to the same endpoint.
//      Now: same single connection handles both event types.
//
// Why this beats component-scoped SSE:
//   Component SSE:  open on mount → close on unmount → TCP handshake on every
//                   navigation → 1-5s blank prices on return visit.
//   Global SSE:     open on login → never close during navigation → prices in
//                   cache (gcTime 5 min) → instant render on every return visit.
"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useAuth } from "@/providers/auth-provider";
import { QK } from "@/lib/query-keys";
import type { DdmVariant } from "@/features/analysis/types/analysis.types";

// ─────────────────────────────────────────────────────────────────────────────
// Public types
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Shape written into QK.price(symbol).
 * Identical fields to useLivePrice's Quote type — intentional so both hooks
 * share one cache entry without any transformation.
 */
export interface CachedPrice {
  symbol:        string;
  price:         number | null;
  change:        number | null;
  changePercent: number | null;
  lastUpdated:   string | null;
  currency?:     string | null;
}

interface SSEContextValue {
  /** true once the first SSE message is received after (re)connect */
  isConnected: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// Context — optional; consume only when you need the indicator
// ─────────────────────────────────────────────────────────────────────────────

const SSEContext = createContext<SSEContextValue>({ isConnected: false });

/** Exposes connection status for optional UI dot indicators etc. */
export function useSSEStatus(): SSEContextValue {
  return useContext(SSEContext);
}

// ─────────────────────────────────────────────────────────────────────────────
// Valuation method → QK mapping  (must stay in sync with backend ALLOWED_METHODS)
// ─────────────────────────────────────────────────────────────────────────────

const METHOD_TO_QK: Record<string, (s: string) => readonly unknown[]> = {
  rule1:           (s) => QK.rule1(s),
  dcf:             (s) => QK.dcf(s),
  ddm_gordon:      (s) => QK.ddm(s, "gordon" as DdmVariant),
  ddm_two_stage:   (s) => QK.ddm(s, "two_stage" as DdmVariant),
  owner_earnings:  (s) => QK.ownerEarnings(s),
  residual_income: (s) => QK.residualIncome(s),
};

// ─────────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────────

const SSE_ENDPOINT    = "/api/proxy/watchlists/stream";
const INITIAL_BACKOFF = 1_000;   // 1 s
const MAX_BACKOFF     = 30_000;  // 30 s cap  (mirrors useValuationStream)

// ─────────────────────────────────────────────────────────────────────────────
// Provider
// ─────────────────────────────────────────────────────────────────────────────

export function GlobalSSEProvider({ children }: { children: React.ReactNode }) {
  const queryClient            = useQueryClient();
  const { firebaseUser: user } = useAuth();

  const [isConnected, setIsConnected] = useState(false);

  // Refs so the stable `connect` closure never captures stale state
  const esRef           = useRef<EventSource | null>(null);
  const backoffRef      = useRef<number>(INITIAL_BACKOFF);
  const timerRef        = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef      = useRef(true);
  const connectedRef    = useRef(false); // shadow of isConnected, avoids stale closure

  useEffect(() => {
    mountedRef.current = true;

    // Do not open a connection until the user is authenticated.
    // When status transitions from initializing → authenticated, user?.uid
    // changes from undefined → uid, re-running this effect.
    if (!user) return;

    function connect() {
      if (!mountedRef.current) return;

      const es = new EventSource(SSE_ENDPOINT, { withCredentials: true });
      esRef.current = es;

      es.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return;

        // First message proves the connection is live — reset backoff
        backoffRef.current = INITIAL_BACKOFF;
        if (!connectedRef.current) {
          connectedRef.current = true;
          setIsConnected(true);
        }

        let data: Record<string, unknown>;
        try {
          data = JSON.parse(event.data as string);
        } catch {
          return; // keep-alive ping or malformed frame — ignore
        }

        const type = data.type as string | undefined;

        // ── Route: price_update (typed) OR legacy (no type field) ──────────
        if (type === "price_update" || (!type && typeof data.price === "number")) {
          const symbol = (data.symbol as string | undefined)?.toUpperCase();
          if (!symbol) return;

          // Writing to QK.price(symbol) does two things at once:
          //   a) resets the stale timer → refetchInterval in useLivePrice
          //      finds the data fresh and silently skips its HTTP GET.
          //   b) notifies all useQuery(QK.price) subscribers (StockCard,
          //      useLivePrice) → instant re-render with new price.
          queryClient.setQueryData<CachedPrice>(QK.price(symbol), {
            symbol,
            price:         typeof data.price         === "number" ? data.price         : null,
            change:        typeof data.change        === "number" ? data.change        : null,
            changePercent: typeof data.changePercent === "number" ? data.changePercent : null,
            lastUpdated:   typeof data.lastUpdated   === "string" ? data.lastUpdated   : null,
            currency:      typeof data.currency      === "string" ? data.currency      : null,
          });
          return;
        }

        // ── Route: valuation_ready ─────────────────────────────────────────
        if (type === "valuation_ready") {
          const sym    = (data.symbol as string | undefined)?.toUpperCase();
          const method = data.method as string | undefined;
          if (!sym || !method) return;

          const qkFn = METHOD_TO_QK[method];
          if (qkFn) {
            queryClient.invalidateQueries({ queryKey: qkFn(sym) });
          } else {
            // Unknown method — fall back to invalidating the overview
            queryClient.invalidateQueries({ queryKey: QK.overview(sym) });
          }
          // Always invalidate the cross-method overview so it reflects the
          // newly available result
          queryClient.invalidateQueries({ queryKey: QK.overview(sym) });
        }
      };

      es.onerror = () => {
        if (!mountedRef.current) return;
        es.close();
        esRef.current       = null;
        connectedRef.current = false;
        setIsConnected(false);

        // Exponential backoff: 1 s → 2 s → 4 s … → 30 s cap
        const delay        = Math.min(backoffRef.current, MAX_BACKOFF);
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);

        timerRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, delay);
      };
    }

    connect();

    return () => {
      mountedRef.current   = false;
      connectedRef.current = false;
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      esRef.current?.close();
      esRef.current = null;
      setIsConnected(false);
    };

    // Re-run only when the user identity changes (login / logout).
    // queryClient is stable for the app lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.uid, queryClient]);

  return (
    <SSEContext.Provider value={{ isConnected }}>
      {children}
    </SSEContext.Provider>
  );
}