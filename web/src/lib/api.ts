// web/src/lib/api.ts
import axios, {
  AxiosError,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from "axios";
import { getUnauthorizedHandler } from "@/features/auth/services/token-manager";

// --- Security & Reliability defaults ---
const isProd = process.env.NODE_ENV === "production";

// In production we expect an explicit backend URL.
// In development we use the Next.js proxy.
const baseURL = isProd
  ? (process.env.NEXT_PUBLIC_API_URL as string)
  : process.env.NEXT_PUBLIC_API_URL || "/api/proxy";

// Fail fast if prod URL is missing (prevents accidental proxy use in prod)
if (isProd && !baseURL) {
  // eslint-disable-next-line no-console
  console.error(
    "[API] NEXT_PUBLIC_API_URL is not set in production. Requests will fail."
  );
}

export const api = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
    // Optional: identify XHR to backend logs
    "X-Requested-With": "XMLHttpRequest",
  },
  // Reasonable client-side guardrails
  timeout: 12_000, // 12s
  // Don’t automatically treat 4xx as success
  validateStatus: (status) => status >= 200 && status < 300,
  /**
   * CRITICAL:
   * Ensure the browser sends the __session cookie on:
   *  - client-side navigation (RSC waterfalls)
   *  - standard CSR requests
   * so the proxy can mint Authorization to the backend.
   */
  withCredentials: true,
});

// --- Utilities ---
const redactUrl = (url: string | undefined) =>
  (url || "").replace(/(token=)[^&]+/i, "$1<redacted>");

const method = (cfg?: AxiosRequestConfig) =>
  (cfg?.method || "get").toUpperCase();

function logRequest(cfg: InternalAxiosRequestConfig) {
  if (isProd) return cfg; // disable noisy logs in prod
  const safeUrl = `${cfg.baseURL || ""}${redactUrl(cfg.url)}`;
  // Avoid printing headers (contains Authorization)
  // eslint-disable-next-line no-console
  console.debug(`[API] → ${method(cfg)} ${safeUrl}`);
  return cfg;
}

function logResponse(resp: any) {
  if (isProd) return resp;
  const safeUrl = `${resp.config?.baseURL || ""}${redactUrl(resp.config?.url)}`;
  // eslint-disable-next-line no-console
  console.debug(`[API] ← ${method(resp.config)} ${safeUrl} ${resp.status}`);
  return resp;
}

function toErrorMessage(err: unknown): string {
  // Backend standard: { detail: string } or { message: string }
  const ax = err as AxiosError<any>;
  const msg =
    ax?.response?.data?.detail ||
    ax?.response?.data?.message ||
    ax?.message ||
    "Request failed";
  return msg;
}

// --- Interceptors ---
// Safety net: never allow callers to disable credentials
api.interceptors.request.use(
  (cfg) => {
    cfg.withCredentials = true; // enforce cookie inclusion

    /**
     * SAFETY NORMALIZATION (non-breaking):
     * Prevent accidental double-proxy paths such as:
     *   baseURL="/api/proxy" + url="/api/proxy/valuations/..."  => "/api/proxy/api/proxy/..."
     *
     * If caller mistakenly passes "/api/proxy/..." as url, strip it once.
     */
    if (typeof cfg.url === "string" && cfg.url.startsWith("/api/proxy/")) {
      cfg.url = cfg.url.replace(/^\/api\/proxy/, "");
    } else if (cfg.url === "/api/proxy") {
      cfg.url = "/";
    }

    return logRequest(cfg);
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (resp) => logResponse(resp),
  (error: AxiosError) => {
    const status = error.response?.status;

    // Normalize the error for callers
    const normalized = new Error(toErrorMessage(error)) as Error & {
      status?: number;
      code?: string;
      raw?: AxiosError;
    };
    normalized.status = status;
    normalized.code = (error as any)?.code;
    normalized.raw = error;

    // Security: on 401/403, trigger global unauthorized handler (real sign-out)
    if (status === 401 || status === 403) {
      // eslint-disable-next-line no-console
      console.warn("[API] Unauthorized – triggering sign-out");
      try {
        getUnauthorizedHandler()?.(); // non-blocking
      } catch {
        /* no-op */
      }
    }

    // Respect server rate limits: do NOT auto-retry 429 here
    // (UI can throttle buttons instead of hammering the server)
    return Promise.reject(normalized);
  }
);

// Optional: lightweight retry for transient network errors on safe methods
// (Avoid retrying POST/PATCH/DELETE to respect idempotency and rate limits)
const NETWORK_ERROR_CODES = new Set([
  "ECONNABORTED",
  "ERR_NETWORK",
  "ETIMEDOUT",
]);

api.interceptors.response.use(undefined, async (error: any) => {
  const rawErr = error?.raw || error;
  const cfg = rawErr?.config as InternalAxiosRequestConfig & {
    __retryCount?: number;
  };
  const methodName = method(cfg);
  const isSafeMethod = methodName === "GET" || methodName === "HEAD";

  if (
    cfg &&
    isSafeMethod &&
    NETWORK_ERROR_CODES.has(rawErr?.code || error?.code) &&
    (cfg.__retryCount || 0) < 2 // up to 2 retries
  ) {
    cfg.__retryCount = (cfg.__retryCount || 0) + 1;
    const backoffMs = [400, 1000][cfg.__retryCount - 1]; // simple backoff
    await new Promise((r) => setTimeout(r, backoffMs));
    return api.request(cfg);
  }

  // pass through normalized error from previous interceptor
  return Promise.reject(error);
});

export default api;