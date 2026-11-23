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
 * Shape written into QK.price(symbol, securityId?).
 * Identical fields to useLivePrice's Quote type — intentional so both hooks
 * share one cache entry without any transformation.
 */
export interface CachedPrice {
  symbol:        string;
  securityId?:   number | null;
  price:         number | null;
  change:        number | null;
  changePercent: number | null;
  lastUpdated:   string | null;
  currency?:     string | null;
  source?:       string | null;
  isStale?:      boolean | null;
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
  const { session } = useAuth();

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
    // When status transitions from initializing → authenticated, session?.user?.id
    // changes from undefined → id, re-running this effect.
    if (!session?.user) return;

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
          if (process.env.NODE_ENV !== 'production') {
            console.log("[SSE-DIAG] First SSE message received — connection is live");
          }
        }

        let data: Record<string, unknown>;
        try {
          data = JSON.parse(event.data as string);
        } catch {
          if (process.env.NODE_ENV !== 'production') {
            console.warn("[SSE-DIAG] Malformed SSE frame (non-JSON):", event.data);
          }
          return; // keep-alive ping or malformed frame — ignore
        }

        const type = data.type as string | undefined;
        if (process.env.NODE_ENV !== 'production') {
          console.log("[SSE-DIAG] Received event:", type, "symbol:", data.symbol, "price:", data.price);
        }

        // ── Route: price_update (typed) OR legacy (no type field) ──────────
        if (type === "price_update" || (!type && typeof data.price === "number")) {
          const symbol = (data.symbol as string | undefined)?.toUpperCase();
          if (!symbol) {
            if (process.env.NODE_ENV !== 'production') {
              console.warn("[SSE-DIAG] price_update with no symbol — skipping");
            }
            return;
          }

          // A listing identity (security_id) makes each cached price specific to
          // the exact tradable row. META/NMS and META/NEO share a symbol but are
          // two instruments — keying only by symbol made them overwrite each
          // other. Identity-bearing events go to the listing cache; we also
          // mirror to the symbol-only key for legacy analysis subscribers.
          const securityId = typeof data.security_id === "number"
            ? data.security_id
            : null;
          const payload: CachedPrice = {
            symbol,
            securityId,
            price:         typeof data.price         === "number" ? data.price         : null,
            change:        typeof data.change        === "number" ? data.change        : null,
            changePercent: typeof data.changePercent === "number" ? data.changePercent : null,
            lastUpdated:   typeof data.lastUpdated   === "string" ? data.lastUpdated   : null,
            currency:      typeof data.currency      === "string" ? data.currency      : null,
            source:        typeof data.source        === "string" ? data.source        : null,
            isStale:       typeof data.isStale       === "boolean" ? data.isStale      : null,
          };
          const listingKey = QK.price(symbol, securityId);
          const current = queryClient.getQueryData<CachedPrice>(listingKey);
          if (data.lastUpdated && current?.lastUpdated && data.lastUpdated < current.lastUpdated) {
            return; // Drop stale update — cache is fresher
          }
          queryClient.setQueryData<CachedPrice>(listingKey, payload);
          if (securityId != null) {
            queryClient.setQueryData<CachedPrice>(QK.price(symbol), payload);
          }
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
            // Unknown method — fall back to invalidating the summary
            queryClient.invalidateQueries({ queryKey: QK.valuationSummary(sym) });
          }
          // Always invalidate the cross-method summary so it reflects the
          // newly available result
          queryClient.invalidateQueries({ queryKey: QK.valuationSummary(sym) });
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
  }, [session?.user?.id, queryClient]);

  return (
    <SSEContext.Provider value={{ isConnected }}>
      {children}
    </SSEContext.Provider>
  );
}