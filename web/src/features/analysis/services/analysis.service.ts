// web/src/features/analysis/services/analysis.service.ts
/**
 * Analysis service:
 * - Uses same-origin fetch with `credentials: "include"` so the proxy sees the __session cookie.
 * - Aligns strictly to backend contract.
 *
 * FETCH PATTERN (two functions per method):
 *   fetch*Cached  → GET  — pure cache read, ~50ms, used as React Query queryFn
 *   fetch*Outcome → POST — gate logic + optional recompute, used only for Recompute button
 *
 * The GET functions return 404 when no valuation has been computed yet.
 * Callers should handle 404 by showing a "Run computation" CTA, not an error state.
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
  OwnerEarningsResponse,
  OwnerEarningsHistory,
  ResidualIncomeResponse,
  ResidualIncomeHistory,
  MagicFormulaResponse,
  CANSlimResponse,
  MurphyAnalysisResponse,
  SuperInvestorData,
} from "../types/analysis.types";

import type { OverviewRecommendation } from "../hooks/useValuationOverview";

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

/**
 * GET — Pure cache read. Used as React Query queryFn.
 * Returns { status: "not_computed" } when backend returns 404.
 * Never triggers recomputation.
 */
export type Rule1CachedOutcome =
  | { status: "ok"; payload: Rule1Response }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

export async function fetchRule1Cached(ticker: string): Promise<Rule1CachedOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) {
    return { status: "not_computed" };
  }
  if (res.ok) {
    const body = await readJsonSafe<Rule1Response>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message: (errorBody?.detail as string) || `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/**
 * POST — Gate logic + optional recompute. Used only by Recompute button.
 */
export async function fetchRule1Outcome(ticker: string): Promise<Rule1Outcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "POST", body: JSON.stringify({}) });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error while computing valuation." };
  }
  if (res.ok) {
    const body = await readJsonSafe<Rule1Response>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing valuation payload).", httpStatus: 502 };
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
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  }
  return { symbol: ticker.toUpperCase(), items: [] };
}

/* -------------------------------------------------------------------------- */
/* DDM                                                                         */
/* -------------------------------------------------------------------------- */

export type DdmOutcome =
  | { status: "ok"; payload: DdmResponse }
  | { status: "error"; message: string; httpStatus?: number };

export type DdmCachedOutcome =
  | { status: "ok"; payload: DdmResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET — Pure cache read. */
export async function fetchDdmCached(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmCachedOutcome> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm?variant=${encodeURIComponent(variant)}`
  );
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<DdmResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message: (errorBody?.detail as string) || `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/** POST — Gate logic + optional recompute. */
export async function fetchDdmOutcome(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmOutcome> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm?variant=${encodeURIComponent(variant)}`
  );
  let res: Response;
  try {
    res = await doFetch(url, { method: "POST", body: JSON.stringify({}) });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error while computing DDM." };
  }
  if (res.ok) {
    const body = await readJsonSafe<DdmResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing DDM payload).", httpStatus: 502 };
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

export async function fetchDdmHistory(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmHistory> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm/history?variant=${encodeURIComponent(variant)}`
  );
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return { symbol: ticker.toUpperCase(), items: [] };
  }
  if (res.ok) {
    const body = await readJsonSafe<DdmHistory>(res);
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  }
  return { symbol: ticker.toUpperCase(), items: [] };
}

/* -------------------------------------------------------------------------- */
/* DCF                                                                         */
/* -------------------------------------------------------------------------- */

export type DcfCachedOutcome =
  | { status: "ok"; payload: DcfResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET — Pure cache read. */
export async function fetchDcfCached(symbol: string): Promise<DcfCachedOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(symbol)}/dcf`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<DcfResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message: (errorBody?.detail as string) || `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/** POST — Gate logic + optional recompute. */
export async function fetchDcfValuation(
  symbol: string,
  options?: { force?: boolean; overrides?: Record<string, unknown> }
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
  throw new Error(
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`
  );
}

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
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  }
  return { symbol: symbol.toUpperCase(), items: [] };
}

/* -------------------------------------------------------------------------- */
/* OWNER EARNINGS                                                              */
/* -------------------------------------------------------------------------- */

export type OwnerEarningsOutcome =
  | { status: "ok"; payload: OwnerEarningsResponse }
  | { status: "error"; message: string; httpStatus?: number };

export type OwnerEarningsCachedOutcome =
  | { status: "ok"; payload: OwnerEarningsResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET — Pure cache read. */
export async function fetchOwnerEarningsCached(
  ticker: string
): Promise<OwnerEarningsCachedOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/owner_earnings`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<OwnerEarningsResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message: (errorBody?.detail as string) || `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/** POST — Gate logic + optional recompute. */
export async function fetchOwnerEarningsOutcome(
  ticker: string
): Promise<OwnerEarningsOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/owner_earnings`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "POST", body: JSON.stringify({}) });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error while computing Owner Earnings." };
  }
  if (res.ok) {
    const body = await readJsonSafe<OwnerEarningsResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing Owner Earnings payload).", httpStatus: 502 };
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

export async function fetchOwnerEarningsHistory(ticker: string): Promise<OwnerEarningsHistory> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/owner_earnings/history`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return { symbol: ticker.toUpperCase(), items: [] };
  }
  if (res.ok) {
    const body = await readJsonSafe<OwnerEarningsHistory>(res);
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  }
  return { symbol: ticker.toUpperCase(), items: [] };
}

/* -------------------------------------------------------------------------- */
/* RESIDUAL INCOME                                                             */
/* -------------------------------------------------------------------------- */

export type ResidualIncomeOutcome =
  | { status: "ok"; payload: ResidualIncomeResponse }
  | { status: "error"; message: string; httpStatus?: number };

export type ResidualIncomeCachedOutcome =
  | { status: "ok"; payload: ResidualIncomeResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET — Pure cache read. */
export async function fetchResidualIncomeCached(
  ticker: string
): Promise<ResidualIncomeCachedOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/residual_income`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<ResidualIncomeResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message: (errorBody?.detail as string) || `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/** POST — Gate logic + optional recompute. */
export async function fetchResidualIncomeOutcome(
  ticker: string
): Promise<ResidualIncomeOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/residual_income`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "POST", body: JSON.stringify({}) });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error while computing Residual Income." };
  }
  if (res.ok) {
    const body = await readJsonSafe<ResidualIncomeResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing Residual Income payload).", httpStatus: 502 };
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

export async function fetchResidualIncomeHistory(ticker: string): Promise<ResidualIncomeHistory> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/residual_income/history`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return { symbol: ticker.toUpperCase(), items: [] };
  }
  if (res.ok) {
    const body = await readJsonSafe<ResidualIncomeHistory>(res);
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  }
  return { symbol: ticker.toUpperCase(), items: [] };
}

/**
 * GET — Fetches cross-method overview with AI recommendation.
 * Returns null if no methods have been computed yet (backend returns empty data).
 * Never throws — returns null on any failure so the overview renders without it.
 */
export async function fetchOverviewSummary(
  symbol: string
): Promise<OverviewRecommendation | null> {
  const url = apiPath(`/valuations/${encodeURIComponent(symbol)}/overview`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch {
    return null;
  }
  if (!res.ok) return null;
  try {
    const body = await res.json();
    return (body?.recommendation as OverviewRecommendation) ?? null;
  } catch {
    return null;
  }
}

/* -------------------------------------------------------------------------- */
/* MAGIC FORMULA                                                               */
/* -------------------------------------------------------------------------- */
export type MagicFormulaCachedOutcome =
  | { status: "ok"; payload: MagicFormulaResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET — Pure cache read. Returns not_computed when backend has no cached run. */
export async function fetchMagicFormulaCached(
  symbol: string
): Promise<MagicFormulaCachedOutcome> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/magic-formula`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<MagicFormulaResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      return {
        status: "error",
        message: "Invalid response from server.",
        httpStatus: 502,
      };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message:
      (errorBody?.detail as string) ||
      `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/** GET with force=true — triggers recompute, used only by Recompute button. */
export async function fetchMagicFormulaValuation(
  symbol: string,
  options?: { force?: boolean }
): Promise<MagicFormulaResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/magic-formula${qs}`
  );
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    throw new Error(
      err?.message || "Network error while computing Magic Formula."
    );
  }
  if (res.ok) {
    const body = await readJsonSafe<MagicFormulaResponse>(res);
    if (!body || typeof body !== "object" || !body.valuation) {
      throw new Error("Invalid response from server (missing Magic Formula payload).");
    }
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error(
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`
  );
}

/* -------------------------------------------------------------------------- */
/* CANSLIM                                                                     */
/* -------------------------------------------------------------------------- */

export type CANSlimCachedOutcome =
  | { status: "ok"; payload: CANSlimResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET — Pure cache read. */
export async function fetchCANSlimCached(
  symbol: string
): Promise<CANSlimCachedOutcome> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/canslim`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    return { status: "error", message: err?.message || "Network error." };
  }
  if (res.status === 404) return { status: "not_computed" };
  if (res.ok) {
    const body = await readJsonSafe<CANSlimResponse>(res);
    if (!body || typeof body !== "object" || !body.letters) {
      return {
        status: "error",
        message: "Invalid response from server.",
        httpStatus: 502,
      };
    }
    return { status: "ok", payload: body };
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  return {
    status: "error",
    message:
      (errorBody?.detail as string) ||
      `Request failed with status ${res.status}`,
    httpStatus: res.status,
  };
}

/** GET with force=true — triggers recompute, used only by Recompute button. */
export async function fetchCANSlimValuation(
  symbol: string,
  options?: { force?: boolean }
): Promise<CANSlimResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/canslim${qs}`
  );
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" });
  } catch (err: any) {
    throw new Error(err?.message || "Network error while computing CANSlim.");
  }
  if (res.ok) {
    const body = await readJsonSafe<CANSlimResponse>(res);
    if (!body || typeof body !== "object" || !body.letters) {
      throw new Error("Invalid response from server (missing CANSlim payload).");
    }
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error(
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`
  );
}

/* -------------------------------------------------------------------------- */
/* MURPHY TECHNICAL                                                            */
/* Stateless — always computed fresh from live daily OHLCV.                   */
/* No not_computed state, no force param, no cache read variant.              */
/* -------------------------------------------------------------------------- */

/** GET — always fresh. Throws on any failure (no fallback empty state). */
export async function fetchMurphyTechnical(
  symbol: string
): Promise<MurphyAnalysisResponse> {
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/technical/murphy`
  );
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" }, 20_000); // 20s — live price fetch
  } catch (err: any) {
    throw new Error(
      err?.message || "Network error fetching technical analysis."
    );
  }
  if (res.ok) {
    const body = await readJsonSafe<MurphyAnalysisResponse>(res);
    if (!body || typeof body !== "object" || !body.synthesis) {
      throw new Error(
        "Invalid response from server (missing Murphy analysis payload)."
      );
    }
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error(
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`
  );
}

/* ── Super Investors ──────────────────────────────────────────────────────────── */

export async function fetchSuperInvestors(
  symbol: string
): Promise<SuperInvestorData> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/super-investors`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" }, 30_000);
  } catch (err: any) {
    throw new Error(err?.message || "Network error fetching super investors.");
  }
  if (res.ok) {
    const body = await readJsonSafe<SuperInvestorData>(res);
    if (!body || typeof body !== "object") {
      throw new Error("Invalid response from server (missing super investor data).");
    }
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error(
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`
  );
}

export async function fetchSuperInvestorsHistory(
  symbol: string
): Promise<SuperInvestorHistoryData> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/super-investors/history`);
  let res: Response;
  try {
    res = await doFetch(url, { method: "GET" }, 30_000);
  } catch (err: any) {
    throw new Error(err?.message || "Network error fetching super investor history.");
  }
  if (res.ok) {
    const body = await readJsonSafe<SuperInvestorHistoryData>(res);
    if (!body || typeof body !== "object") {
      throw new Error("Invalid response from server (missing history data).");
    }
    return body;
  }
  const errorBody = (await readJsonSafe<Json>(res)) || {};
  throw new Error(
    (errorBody?.detail as string) ||
    (errorBody?.message as string) ||
    `Request failed with status ${res.status}`
  );
}