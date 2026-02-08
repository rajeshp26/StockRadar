// src/features/analysis/services/analysis.service.ts

import type {
    Rule1Response,
    Rule1History,
    ApiError,
  } from "../types/analysis.types";
  
  /**
   * Optional overrides that map 1:1 to backend Rule1RequestOverrides.
   * All values are optional; when omitted, defaults/DB-resolved inputs are used.
   */
  export interface Rule1Overrides {
    discountRate?: number;   // 0..1
    horizonYears?: number;   // 1..50
    marginOfSafety?: number; // 0..1
    forceGrowth?: number;    // decimal (e.g., 0.12 for 12%)
    forceFuturePE?: number;  // >= 0
  }
  
  /**
   * Optional request options for fetches (timeout, abort, overrides).
   */
  export interface RequestOpts {
    signal?: AbortSignal;
    timeoutMs?: number;        // default applied if set (uses AbortController)
    overrides?: Rule1Overrides;
  }
  
  /* ---------------------------------- */
  /* Internal helpers                    */
  /* ---------------------------------- */
  
  const JSON_HEADERS: HeadersInit = {
    "Content-Type": "application/json",
  };
  
  /**
   * Build a fully qualified proxy path. We never call the backend directly.
   * This keeps tokens/keys hidden and centralizes logging/retries in the proxy.
   */
  function api(path: string) {
    return `/api/proxy${path}`;
  }
  
  /**
   * Parses a Response as JSON (when possible) and throws a typed error for non-2xx.
   */
  async function handleJson<T>(res: Response): Promise<T> {
    if (res.ok) {
      // 204 No Content will throw on json(); guard it.
      if (res.status === 204) return {} as T;
      return (await res.json()) as T;
    }
    let body: unknown = undefined;
    try {
      body = await res.json();
    } catch {
      // fall through
    }
  
    const detail =
      (body as ApiError)?.detail ??
      (typeof body === "string" ? body : res.statusText) ??
      "Request failed";
  
    // Surface rate-limit info if present
    const retryAfter = res.headers.get("retry-after");
    const more = retryAfter != null ? ` (retry after ${retryAfter}s)` : "";
  
    throw new Error(`${detail}${more}`);
  }
  
  /**
   * Wraps fetch with:
   *  - credentials: "include" (so proxy can attach Firebase token)
   *  - optional timeout via AbortController
   */
  async function doFetch(input: RequestInfo, init: RequestInit = {}, timeoutMs?: number) {
    if (!timeoutMs) {
      return fetch(input, { credentials: "include", ...init });
    }
  
    const ctrl = new AbortController();
    const id = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      return await fetch(input, {
        credentials: "include",
        signal: ctrl.signal,
        ...init,
      });
    } finally {
      clearTimeout(id);
    }
  }
  
  /* ---------------------------------- */
  /* Public API                          */
  /* ---------------------------------- */
  
  /**
   * Loads (or returns cached) Rule #1 valuation for a symbol by calling:
   *   POST /valuations/:symbol/rule1
   * with no `force` query (the backend decides cached vs recompute).
   *
   * Notes:
   *  - We use POST here because your backend route is POST-only.
   *  - If you later add a read-only GET, we can switch transparently.
   */
  export async function fetchRule1(
    symbol: string,
    opts: RequestOpts = {}
  ): Promise<Rule1Response> {
    if (!symbol) throw new Error("symbol is required");
    const { overrides, signal, timeoutMs } = opts;
  
    const url = api(`/valuations/${encodeURIComponent(symbol)}/rule1`);
    const res = await doFetch(
      url,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(overrides ?? {}),
        signal,
      },
      timeoutMs
    );
  
    return handleJson<Rule1Response>(res);
  }
  
  /**
   * Forces a recompute of Rule #1 valuation:
   *   POST /valuations/:symbol/rule1?force=true
   */
  export async function recomputeRule1(
    symbol: string,
    opts: RequestOpts = {}
  ): Promise<Rule1Response> {
    if (!symbol) throw new Error("symbol is required");
    const { overrides, signal, timeoutMs } = opts;
  
    const url = api(`/valuations/${encodeURIComponent(symbol)}/rule1`) + `?force=true`;
  
    const res = await doFetch(
      url,
      {
        method: "POST",
        headers: JSON_HEADERS,
        body: JSON.stringify(overrides ?? {}),
        signal,
      },
      timeoutMs
    );
  
    return handleJson<Rule1Response>(res);
  }
  
  /**
   * History:
   * Thin integration for valuation_runs history. If the endpoint is not available
   * in your environment yet, you can handle errors in the caller and show an empty state.
   *
   * Expected backend path:
   *   GET /valuations/:symbol/rule1/history
   */
  export async function fetchRule1History(
    symbol: string,
    opts: RequestOpts = {}
  ): Promise<Rule1History> {
    if (!symbol) throw new Error("symbol is required");
    const { signal, timeoutMs } = opts;
  
    const url = api(`/valuations/${encodeURIComponent(symbol)}/rule1/history`);
    const res = await doFetch(
      url,
      {
        method: "GET",
        headers: { "Accept": "application/json" },
        signal,
      },
      timeoutMs
    );
  
    // If the endpoint is not present or returns non-2xx, this will throw.
    // The hook will catch and degrade gracefully to an empty history.
    const data = await handleJson<Rule1History>(res);
  
    // Ensure a consistent shape back to the UI
    return {
      symbol: data?.symbol?.toUpperCase?.() ?? symbol.toUpperCase(),
      items: Array.isArray(data?.items) ? data.items : [],
    };
  }
  
  /**
   * Convenience wrapper for a single call site that wants the pair:
   * { valuation + meta, history }
   */
  export async function loadAnalysisBundle(
    symbol: string,
    opts: RequestOpts = {}
  ): Promise<{
    response: Rule1Response;
    history: Rule1History;
  }> {
    const [response, history] = await Promise.all([
      fetchRule1(symbol, opts),
      // If history fails, allow the caller to decide empty vs error
      fetchRule1History(symbol, opts).catch<Rule1History>(() => ({
        symbol: symbol.toUpperCase(),
        items: [],
      })),
    ]);
    return { response, history };
  }