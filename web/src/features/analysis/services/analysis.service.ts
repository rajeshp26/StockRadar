// web/src/features/analysis/services/analysis.service.ts
/**
 * Analysis service:
 * - Uses same-origin fetch with `credentials: "include"` so the proxy sees the __session cookie.
 * - Aligns strictly to backend contract:
 *     POST /valuations/{symbol}/rule1 returns Rule1Response:
 *       { valuation: {...camelCase}, applicability: {...}, dataQuality: {...} }
 */

type Json = Record<string, any>;

const DEFAULT_TIMEOUT_MS = 15_000;

/* -------------------------------------------------------------------------- */
/* Backend-aligned types                                                      */
/* -------------------------------------------------------------------------- */

export type Severity = "critical" | "high" | "medium" | "low" | "info";

export type DiagnosticFlag = {
  code: string;
  severity: Severity;
  message: string;
  evidence?: Record<string, any> | null;
  recommendation?: string | null;
};

export type Applicability = {
  score: number; // 0..100
  category: "Good" | "Caution" | "Poor";
  flags: DiagnosticFlag[];
};

export type DataQuality = {
  freshnessDays: Record<string, any>;
  fallbacksUsed: boolean;
  inputDecisions: Record<string, any>;
};

export type Rule1Valuation = {
  symbol: string;
  companyId: number;
  currency: string;

  eps0: number;
  growth: number;
  futurePE: number;

  futureEPS: number;
  futurePrice: number;

  discountRate: number;
  horizonYears: number;
  mos: number;

  stickerPrice: number;
  mosPrice: number;
};

export type Rule1Response = {
  valuation: Rule1Valuation;
  applicability: Applicability;
  dataQuality: DataQuality;
};

export type Rule1Outcome =
  | { status: "ok"; payload: Rule1Response }
  | { status: "error"; message: string; httpStatus?: number };

/* -------------------------------------------------------------------------- */
/* Endpoint helpers                                                           */
/* -------------------------------------------------------------------------- */

function apiPath(path: string) {
  return `/api/proxy${path}`;
}

/* -------------------------------------------------------------------------- */
/* Low-level fetch with timeout & credentials                                 */
/* -------------------------------------------------------------------------- */

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
/* Public API                                                                 */
/* -------------------------------------------------------------------------- */

/**
 * Compute Rule #1 valuation for the given ticker.
 * Backend contract:
 * 200 → Rule1Response { valuation, applicability, dataQuality }
 * Non-200 → { detail: "..."} (FastAPI) or { message: "..." }
 */
export async function fetchRule1Outcome(ticker: string): Promise<Rule1Outcome> {
  const url = apiPath(`/valuations/${encodeURIComponent(ticker)}/rule1`);

  let res: Response;
  try {
    // Body is optional for this endpoint; keep {} for consistency
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

/**
 * Convenience wrapper: returns Rule1Response or throws.
 */
export async function fetchRule1(ticker: string): Promise<Rule1Response> {
  const out = await fetchRule1Outcome(ticker);
  if (out.status === "ok") return out.payload;

  const err: any = new Error(out.message || "Failed to compute valuation.");
  err.status = out.httpStatus;
  throw err;
}