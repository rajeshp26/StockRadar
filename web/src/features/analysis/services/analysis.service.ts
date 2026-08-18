// web/src/features/analysis/services/analysis.service.ts
/**
 * Analysis service:
 * - Uses the shared axios instance (api) for all HTTP requests.
 * - The axios instance automatically sets X-Requested-With and X-CSRF-Token headers
 *   required by the Next.js proxy's CSRF protection.
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
  SuperInvestorHistoryData,
  StockVsIndexResponse,
  MoatResponse,
  RiskAssessmentResponse,
  FundamentalsResponse,
} from "../types/analysis.types";

type Json = Record<string, any>;
const DEFAULT_TIMEOUT_MS = 15_000;

function apiPath(path: string) {
  return path;
}

function errMessage(err: unknown): string {
  return (err as any)?.message || "Request failed";
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as Rule1Response;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) {
      return { status: "not_computed" };
    }
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

/**
 * POST — Gate logic + optional recompute. Used only by Recompute button.
 */
export async function fetchRule1Outcome(ticker: string): Promise<Rule1Outcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1`);
  try {
    const resp = await api.post(url, {}, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as Rule1Response;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing valuation payload).", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

export async function fetchRule1History(ticker: string): Promise<Rule1History> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1/history`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as Rule1History;
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  } catch {
    /* fall through to empty default */
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as DdmResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

/** POST — Gate logic + optional recompute. */
export async function fetchDdmOutcome(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmOutcome> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm?variant=${encodeURIComponent(variant)}`
  );
  try {
    const resp = await api.post(url, {}, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as DdmResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing DDM payload).", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

export async function fetchDdmHistory(
  ticker: string,
  variant: DdmVariant = "gordon"
): Promise<DdmHistory> {
  const url = apiPath(
    `/valuations/${encodeURIComponent(ticker)}/ddm/history?variant=${encodeURIComponent(variant)}`
  );
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as DdmHistory;
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  } catch {
    /* fall through */
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as DcfResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

/** POST — Gate logic + optional recompute. */
export async function fetchDcfValuation(
  symbol: string,
  options?: { force?: boolean; overrides?: Record<string, unknown> }
): Promise<DcfResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/valuations/${encodeURIComponent(symbol)}/dcf${qs}`);
  try {
    const resp = await api.post(url, options?.overrides ?? {}, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as DcfResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      throw new Error("Invalid response from server (missing DCF payload).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

export async function fetchDcfHistory(symbol: string): Promise<DcfHistory> {
  const url = apiPath(`/valuations/${encodeURIComponent(symbol)}/dcf/history`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as DcfHistory;
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  } catch {
    /* fall through */
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as OwnerEarningsResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

/** POST — Gate logic + optional recompute. */
export async function fetchOwnerEarningsOutcome(
  ticker: string
): Promise<OwnerEarningsOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/owner_earnings`);
  try {
    const resp = await api.post(url, {}, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as OwnerEarningsResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing Owner Earnings payload).", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

export async function fetchOwnerEarningsHistory(ticker: string): Promise<OwnerEarningsHistory> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/owner_earnings/history`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as OwnerEarningsHistory;
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  } catch {
    /* fall through */
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as ResidualIncomeResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

/** POST — Gate logic + optional recompute. */
export async function fetchResidualIncomeOutcome(
  ticker: string
): Promise<ResidualIncomeOutcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/residual_income`);
  try {
    const resp = await api.post(url, {}, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as ResidualIncomeResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server (missing Residual Income payload).", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

export async function fetchResidualIncomeHistory(ticker: string): Promise<ResidualIncomeHistory> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/residual_income/history`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as ResidualIncomeHistory;
    if (body && typeof body === "object" && Array.isArray(body.items)) return body;
  } catch {
    /* fall through */
  }
  return { symbol: ticker.toUpperCase(), items: [] };
}

/* -------------------------------------------------------------------------- */
/* VALUATION SUMMARY (canonical cross-method read model, §6.1)                */
/*                                                                            */
/* Single GET /analysis/{symbol}/valuation-summary replaces the per-method    */
/* GETs + /overview as the page's valuation critical path. One request, one   */
/* SQL view, zero compute on the request path.                                */
/* -------------------------------------------------------------------------- */

export type ValuationMethodKey =
  | "rule1"
  | "dcf"
  | "ddm_gordon"
  | "owner_earnings"
  | "residual_income";

export type ValuationMethodStatus =
  | "available"
  | "stale"
  | "not_computed"
  | "not_applicable"
  | "failed_without_previous_result";

/** Per-method section of the summary contract (v_valuation_latest_runs). */
export type MethodSummaryResponse = {
  method: ValuationMethodKey;
  status: ValuationMethodStatus;
  reasonCode: string | null;      // e.g. "NEGATIVE_EPS" | "NOT_MEANINGFUL" | "MISSING_SNAPSHOT"
  intrinsicValue: number | null;
  referencePrice: number | null;
  referencePriceAsOf: string | null;
  upsideDownside: number | null;
  computedAt: string | null;
  inputAsOf: string | null;
  modelVersion: string | null;
  freshnessDays: number | null;
  score: number | null;
  category: string | null;
  currency: string;
  refresh: unknown;               // future extension — always null today
};

export type RecommendationSummary = {
  status: "pending" | "disabled" | "available";
  reasonCode: string | null;      // e.g. "PROVIDER_NOT_CONFIGURED"
  text: string | null;            // deterministic or AI summary text (never silent-null contract)
  generatedAt: string | null;
  sourceSnapshotVersion: string | null;
  provider: string | null;
  model: string | null;
};

export type ValuationSummaryResponse = {
  symbol: string;
  currency: string;
  sector: string | null;
  generatedAt: string;
  methods: Record<ValuationMethodKey, MethodSummaryResponse>;
  recommendation: RecommendationSummary;
};

/**
 * GET — Canonical cross-method valuation summary from the published read model.
 * One request on the page's critical path. 404 only for unknown symbols.
 */
export async function fetchValuationSummary(
  symbol: string
): Promise<ValuationSummaryResponse> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/valuation-summary`);
  const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
  const body = resp.data as ValuationSummaryResponse;
  if (!body || typeof body !== "object" || !body.methods) {
    throw new Error("Invalid response from server (missing valuation summary).");
  }
  return body;
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as MagicFormulaResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return {
      status: "error",
      message: errMessage(err),
      httpStatus: status,
    };
  }
}

/** GET with force=true — triggers recompute, used only by Recompute button. */
export async function fetchMagicFormulaValuation(
  symbol: string,
  options?: { force?: boolean }
): Promise<MagicFormulaResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/magic-formula${qs}`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as MagicFormulaResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      throw new Error("Invalid response from server (missing Magic Formula payload).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
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
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as CANSlimResponse;
    if (!body || typeof body !== "object" || !body.letters) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return {
      status: "error",
      message: errMessage(err),
      httpStatus: status,
    };
  }
}

/** GET with force=true — triggers recompute, used only by Recompute button. */
export async function fetchCANSlimValuation(
  symbol: string,
  options?: { force?: boolean }
): Promise<CANSlimResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/canslim${qs}`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as CANSlimResponse;
    if (!body || typeof body !== "object" || !body.letters) {
      throw new Error("Invalid response from server (missing CANSlim payload).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
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
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/technical/murphy`);
  try {
    const resp = await api.get(url, { timeout: 20_000 });
    const body = resp.data as MurphyAnalysisResponse;
    if (!body || typeof body !== "object" || !body.synthesis) {
      throw new Error("Invalid response from server (missing Murphy analysis payload).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

/* ── Super Investors ──────────────────────────────────────────────────────────── */

export async function fetchSuperInvestors(
  symbol: string
): Promise<SuperInvestorData> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/super-investors`);
  try {
    const resp = await api.get(url, { timeout: 30_000 });
    const body = resp.data as SuperInvestorData;
    if (!body || typeof body !== "object") {
      throw new Error("Invalid response from server (missing super investor data).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

/* -------------------------------------------------------------------------- */
/* STOCK VS INDEX                                                              */
/* -------------------------------------------------------------------------- */

/** GET — Stock vs Index outperformance analysis (live, stateless). */
export async function fetchStockVsIndex(
  symbol: string,
  benchmarkSymbols: string[] = ["SPY"],
  years: number = 3
): Promise<StockVsIndexResponse> {
  const bmParam = benchmarkSymbols.map(s => encodeURIComponent(s)).join(",");
  const url = apiPath(
    `/analysis/${encodeURIComponent(symbol)}/stock-vs-index?benchmark_symbols=${bmParam}&years=${years}`
  );
  try {
    const resp = await api.get(url, { timeout: 20_000 });
    const body = resp.data as StockVsIndexResponse;
    if (!body || typeof body !== "object" || !body.symbol) {
      throw new Error("Invalid response from server (missing stock vs index payload).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

/** GET — List available benchmarks from the analysis API. */
export async function fetchBenchmarks(): Promise<{ role: string; symbol: string; name: string; market: string; description?: string }[]> {
  const url = apiPath("/analysis/benchmarks");
  try {
    const resp = await api.get(url, { timeout: 10_000 });
    const body = resp.data as { role: string; symbol: string; name: string; market: string; description?: string }[];
    return body || [];
  } catch {
    return [];
  }
}

export async function fetchSuperInvestorsHistory(
  symbol: string
): Promise<SuperInvestorHistoryData> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/super-investors/history`);
  try {
    const resp = await api.get(url, { timeout: 30_000 });
    const body = resp.data as SuperInvestorHistoryData;
    if (!body || typeof body !== "object") {
      throw new Error("Invalid response from server (missing history data).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

/* -------------------------------------------------------------------------- */
/* MOAT ANALYSIS � Economic moat durability                                   */
/* Returns not_computed when no cached run exists. Same pattern as Magic      */
/* Formula (GET + force GET for recompute).                                   */
/* -------------------------------------------------------------------------- */

export type MoatCachedOutcome =
  | { status: "ok"; payload: MoatResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

/** GET � Pure cache read. Returns not_computed when backend has no cached run. */
export async function fetchMoatCached(
  symbol: string
): Promise<MoatCachedOutcome> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/moat`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as MoatResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      return { status: "error", message: "Invalid response from server.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return {
      status: "error",
      message: errMessage(err),
      httpStatus: status,
    };
  }
}

/** GET with force=true � triggers recompute, used only by Recompute button. */
export async function fetchMoatValuation(
  symbol: string,
  options?: { force?: boolean }
): Promise<MoatResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/moat${qs}`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as MoatResponse;
    if (!body || typeof body !== "object" || !body.valuation) {
      throw new Error("Invalid response from server (missing Moat payload).");
    }
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

// ── Risk Assessment ──

export type RiskCachedOutcome =
  | { status: "ok"; payload: RiskAssessmentResponse }
  | { status: "not_computed" }
  | { status: "error"; message: string; httpStatus?: number };

export async function fetchRiskCached(symbol: string): Promise<RiskCachedOutcome> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/risk-assessment`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as RiskAssessmentResponse;
    if (!body || !body.composite) {
      return { status: "error", message: "Invalid response.", httpStatus: 502 };
    }
    return { status: "ok", payload: body };
  } catch (err: any) {
    const status = err?.response?.status ?? err?.status;
    if (status === 404) return { status: "not_computed" };
    return { status: "error", message: errMessage(err), httpStatus: status };
  }
}

export async function fetchRiskAssessment(symbol: string, options?: { force?: boolean }): Promise<RiskAssessmentResponse> {
  const qs = options?.force ? "?force=true" : "";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/risk-assessment${qs}`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as RiskAssessmentResponse;
    if (!body || !body.composite) throw new Error("Invalid response.");
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

// ── Fundamentals ──

export async function fetchFundamentals(symbol: string, frequency?: string): Promise<FundamentalsResponse> {
  const freq = frequency ?? "quarterly";
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/fundamentals?frequency=${freq}`);
  try {
    const resp = await api.get(url, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as FundamentalsResponse;
    if (!body || body.success === false) throw new Error(body?.error || "Invalid response.");
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}

export async function fetchRiskAiNarrative(symbol: string): Promise<{ narrative: string; model: string }> {
  const url = apiPath(`/analysis/${encodeURIComponent(symbol)}/risk-assessment/ai`);
  try {
    const resp = await api.post(url, {}, { timeout: DEFAULT_TIMEOUT_MS });
    const body = resp.data as { narrative: string; model: string };
    if (!body || !body.narrative) throw new Error("Invalid response.");
    return body;
  } catch (err: any) {
    throw new Error(errMessage(err));
  }
}
