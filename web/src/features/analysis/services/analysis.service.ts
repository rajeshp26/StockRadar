// web/src/features/analysis/services/analysis.service.ts
/**
 * Analysis service:
 * - Uses same-origin fetch with `credentials: "include"` so the proxy sees the __session cookie.
 * - Aligns strictly to backend contract.
 */
import { api } from "@/lib/api";

import type {
  Rule1Response,
  Rule1History,
  DdmResponse,
  DdmHistory,
  DdmVariant,
  DcfResponse,
  DcfHistory,
} from "../types/analysis.types";

type Json = Record<string, any>;

const DEFAULT_TIMEOUT_MS = 15_000;

function apiPath(path: string) {
  return `/api/proxy${path}`;
}

async function doFetch(
  input: RequestInfo,
  init: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      credentials: "include",
      cache: "no-store",
      signal: controller.signal,
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init.headers || {}),
      },
    });
  } finally {
    clearTimeout(id);
  }
}

async function readJsonSafe<T = Json>(res: Response): Promise<T | null> {
  try {
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* RULE #1                                                                     */
/* -------------------------------------------------------------------------- */

export type Rule1Outcome =
  | { status: "ok"; payload: Rule1Response }
  | { status: "error"; message: string; httpStatus?: number };

export async function fetchRule1Outcome(ticker: string): Promise<Rule1Outcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1`);

  let res: Response;
  try {
    res = await doFetch(url, { method: "POST", body: JSON.stringify({}) });
  } catch (err: any) {
    return {
      status: "error",
      message: err?.message || "Network error while computing valuation.",
    };
  }

  if (res.ok) {
    const body = await readJsonSafe<Rule1Response>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return {
        status: "error",
        message: "Invalid response from server (missing valuation payload).",
        httpStatus: 502,
      };
    }
    return { status: "ok", payload: body };
  }

  const errorBody = (await readJsonSafe<Json>(res)) || {};
  const message =
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`;

  return { status: "error", message, httpStatus: res.status };
}

export async function fetchRule1History(ticker: string): Promise<Rule1History> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1/history`);

  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return { symbol: ticker.toUpperCase(), items: [] };
  }

  if (res.ok) {
    const body = await readJsonSafe<Rule1History>(res);
    if (body && typeof body === "object" && Array.isArray(body.items)) {
      return body;
    }
  }
  return { symbol: ticker.toUpperCase(), items: [] };
}

/* -------------------------------------------------------------------------- */
/* DDM                                                                          */
/* -------------------------------------------------------------------------- */

export type DdmOutcome =
  | { status: "ok"; payload: DdmResponse }
  | { status: "error"; message: string; httpStatus?: number };

export async function fetchDdmOutcome(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmOutcome> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm?variant=${encodeURIComponent(
      variant
    )}`
  );

  let res: Response;
  try {
    res = await doFetch(url, { method: "POST", body: JSON.stringify({}) });
  } catch (err: any) {
    return {
      status: "error",
      message: err?.message || "Network error while computing DDM.",
    };
  }

  if (res.ok) {
    const body = await readJsonSafe<DdmResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return {
        status: "error",
        message: "Invalid response from server (missing DDM payload).",
        httpStatus: 502,
      };
    }
    return { status: "ok", payload: body };
  }

  const errorBody = (await readJsonSafe<Json>(res)) || {};
  const message =
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`;

  return { status: "error", message, httpStatus: res.status };
}

/**
 * DDM History pattern:
 * - Must NEVER break the Analysis page.
 * - If endpoint is missing or returns non-200, return empty list.
 *
 * Expected backend endpoint (recommended):
 *   GET /valuations/:symbol/ddm/history?variant=gordon|two_stage
 */
export async function fetchDdmHistory(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmHistory> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm/history?variant=${encodeURIComponent(
      variant
    )}`
  );

  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return { symbol: ticker.toUpperCase(), items: [] };
  }

  if (res.ok) {
    const body = await readJsonSafe<DdmHistory>(res);
    if (body && typeof body === "object" && Array.isArray(body.items)) {
      return body;
    }
    return { symbol: ticker.toUpperCase(), items: [] };
  }

  return { symbol: ticker.toUpperCase(), items: [] };
}

// ---------------------------
// DCF (FIXED: return AxiosResponse.data, not AxiosResponse)
// ---------------------------

export async function fetchDcfValuation(
  symbol: string,
  options?: {
    force?: boolean;
    overrides?: Record<string, unknown>;
  }
): Promise<DcfResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/valuations/${encodeURIComponent(symbol)}/dcf${qs}`);

  let res: Response;
  try {
    res = await doFetch(url, {
      method: "POST",
      body: JSON.stringify(options?.overrides ?? {}),
    });
  } catch (err: any) {
    throw new Error(err?.message || "Network error while computing DCF.");
  }

  if (res.ok) {
    const body = await readJsonSafe<DcfResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      throw new Error("Invalid response from server (missing DCF payload).");
    }
    return body;
  }

  const errorBody = (await readJsonSafe<Json>(res)) || {};
  const message =
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`;

  throw new Error(message);
}

/**
 * DCF History pattern:
 * - Must NEVER break the Analysis page.
 * - If endpoint is missing or returns non-200, return empty list.
 */
export async function fetchDcfHistory(symbol: string): Promise<DcfHistory> {
  const url = apiPath(`/valuations/${encodeURIComponent(symbol)}/dcf/history`);

  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return { symbol: symbol.toUpperCase(), items: [] };
  }

  if (res.ok) {
    const body = await readJsonSafe<DcfHistory>(res);
    if (body && typeof body === "object" && Array.isArray(body.items)) {
      return body;
    }
  }

  return { symbol: symbol.toUpperCase(), items: [] };
}