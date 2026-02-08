// src/features/analysis/analytics/analysis.analytics.ts

/**
 * Production-ready analytics utility for the Analysis page.
 *
 * Supports:
 *  - Segment:  window.analytics?.track(eventName, props)
 *  - gtag:     window.gtag?.('event', eventName, props)
 *  - console:  console.debug(...)  (useful in dev)
 *  - custom:   supply your own callbacks via `custom` argument
 *
 * Usage:
 *   import { createAnalysisAnalytics } from "@/features/analysis/analytics/analysis.analytics";
 *   import { useAnalysis } from "@/features/analysis/hooks/useAnalysis";
 *
 *   const analytics = createAnalysisAnalytics({ backend: "gtag", prefix: "stockerpro_" });
 *   const { ... } = useAnalysis(symbol, { analytics });
 */

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export type AnalyticsBackend = "segment" | "gtag" | "console" | "custom";

export interface AnalyticsConfig {
  /** Choose the transport. Defaults to 'console' in development, otherwise 'gtag' (if present) or 'segment' (if present), else 'console'. */
  backend?: AnalyticsBackend;
  /** Prefix added to all event names, e.g. 'stockerpro_'. */
  prefix?: string;
  /** Master switch; when false, all calls are no-ops. Defaults to true. */
  enabled?: boolean;
  /** Attach common props (e.g., app version, user tier). These will be merged into every event. */
  common?: Record<string, unknown>;
}

/**
 * Public interface (aligns with the optional callbacks in useAnalysis.ts).
 * Re-declared here to avoid circular imports.
 */
export interface AnalysisAnalytics {
  onPageViewed?: (symbol: string) => void;
  onTabSelected?: (tab: string, symbol: string) => void;
  onRecomputed?: (symbol: string, durationMs: number, ok: boolean) => void;
  onHistoryViewed?: (symbol: string) => void;
  onError?: (symbol: string, message: string) => void;
}

/* ------------------------------------------------------------------ */
/* Internal helpers                                                    */
/* ------------------------------------------------------------------ */

declare global {
  interface Window {
    analytics?: { track?: (event: string, props?: Record<string, unknown>) => void };
    gtag?: (...args: any[]) => void;
  }
}

const DEFAULT_PREFIX = ""; // customize per app if desired

function chooseDefaultBackend(): AnalyticsBackend {
  if (typeof window !== "undefined") {
    if (typeof window.gtag === "function") return "gtag";
    if (window.analytics?.track) return "segment";
  }
  return "console";
}

function upper(s?: string) {
  return (s ?? "").toUpperCase();
}

function buildEventName(prefix: string | undefined, name: string) {
  const p = prefix ?? DEFAULT_PREFIX;
  return p ? `${p}${name}` : name;
}

function safeMerge<T extends object>(base: T, add?: Record<string, unknown>): T & Record<string, unknown> {
  return Object.assign({}, base, add ?? {});
}

/* ------------------------------------------------------------------ */
/* Factory                                                             */
/* ------------------------------------------------------------------ */

export function createAnalysisAnalytics(
  cfg: AnalyticsConfig = {},
  custom?: Partial<AnalysisAnalytics>
): AnalysisAnalytics {
  const enabled = cfg.enabled ?? true;
  const backend = cfg.backend ?? chooseDefaultBackend();
  const prefix = cfg.prefix ?? DEFAULT_PREFIX;
  const common = cfg.common ?? {};

  // Core sender per backend
  const send = (eventName: string, props?: Record<string, unknown>) => {
    if (!enabled) return;
    const name = buildEventName(prefix, eventName);
    const payload = safeMerge(props ?? {}, common);

    try {
      if (backend === "segment") {
        window.analytics?.track?.(name, payload);
      } else if (backend === "gtag") {
        // GA4 expects: gtag('event', name, params)
        window.gtag?.("event", name, payload);
      } else if (backend === "console") {
        // Local dev fallback
        // eslint-disable-next-line no-console
        console.debug(`[analytics:${name}]`, payload);
      } else {
        // 'custom' — if consumer provided custom callbacks, they'll run below.
        // We still allow console for visibility if nothing ran.
        // eslint-disable-next-line no-console
        console.debug(`[analytics-custom:${name}]`, payload);
      }
    } catch {
      // never throw from analytics
    }
  };

  // Concrete callbacks (with safe guards)
  const onPageViewed = (symbol: string) => {
    send("analysis_page_viewed", {
      symbol: upper(symbol),
      ts: new Date().toISOString(),
    });
    custom?.onPageViewed?.(symbol);
  };

  const onTabSelected = (tab: string, symbol: string) => {
    send("analysis_tab_selected", {
      symbol: upper(symbol),
      tab,
      ts: new Date().toISOString(),
    });
    custom?.onTabSelected?.(tab, symbol);
  };

  const onRecomputed = (symbol: string, durationMs: number, ok: boolean) => {
    send("rule1_recomputed", {
      symbol: upper(symbol),
      ok,
      durationMs: Math.max(0, Math.round(durationMs)),
      ts: new Date().toISOString(),
    });
    custom?.onRecomputed?.(symbol, durationMs, ok);
  };

  const onHistoryViewed = (symbol: string) => {
    send("rule1_history_viewed", {
      symbol: upper(symbol),
      ts: new Date().toISOString(),
    });
    custom?.onHistoryViewed?.(symbol);
  };

  const onError = (symbol: string, message: string) => {
    send("analysis_error", {
      symbol: upper(symbol),
      message,
      ts: new Date().toISOString(),
    });
    custom?.onError?.(symbol, message);
  };

  return { onPageViewed, onTabSelected, onRecomputed, onHistoryViewed, onError };
}

/* ------------------------------------------------------------------ */
/* Optional: tiny helper for tab analytics in your page component      */
/* ------------------------------------------------------------------ */

/**
 * Example usage in /analysis/[symbol]/page.tsx:
 *
 *   const analytics = createAnalysisAnalytics({ backend: "gtag", prefix: "stockerpro_" });
 *   ...
 *   <Tabs value={tab} onValueChange={(t) => {
 *     setTab(t);
 *     analytics.onTabSelected?.(t, upperSymbol);
 *   }}>
 */