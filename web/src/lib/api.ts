// web/src/lib/api.ts
//
// SECURITY CHANGE FROM ORIGINAL:
//  - Added CSRF token injection for POST/PUT/PATCH/DELETE requests.
//    Reads __csrf cookie (set by server on login) and sends it as X-CSRF-Token header.
//    The proxy validates this header before forwarding mutating requests.
//
import axios, {
  AxiosError,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from "axios";
import { getUnauthorizedHandler } from "@/features/auth/services/token-manager";

// ── Base URL ──────────────────────────────────────────────────────────────────

const isProd = process.env.NODE_ENV === "production";

const baseURL = isProd
  ? (process.env.NEXT_PUBLIC_API_URL as string)
  : process.env.NEXT_PUBLIC_API_URL || "/api/proxy";

if (isProd && !baseURL) {
  console.error(
    "[API] NEXT_PUBLIC_API_URL is not set in production. Requests will fail."
  );
}

// ── Axios instance ────────────────────────────────────────────────────────────

export const api = axios.create({
  baseURL,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
    "X-Requested-With": "XMLHttpRequest",
  },
  timeout: 12_000,
  validateStatus: (status) => status >= 200 && status < 300,
  withCredentials: true,
});

// ── Utilities ─────────────────────────────────────────────────────────────────

const redactUrl = (url: string | undefined) =>
  (url || "").replace(/(token=)[^&]+/i, "$1<redacted>");

const method = (cfg?: AxiosRequestConfig) =>
  (cfg?.method || "get").toUpperCase();

function logRequest(cfg: InternalAxiosRequestConfig) {
  if (isProd) return cfg;
  const safeUrl = `${cfg.baseURL || ""}${redactUrl(cfg.url)}`;
  console.debug(`[API] → ${method(cfg)} ${safeUrl}`);
  return cfg;
}

function logResponse(resp: any) {
  if (isProd) return resp;
  const safeUrl = `${resp.config?.baseURL || ""}${redactUrl(resp.config?.url)}`;
  console.debug(`[API] ← ${method(resp.config)} ${safeUrl} ${resp.status}`);
  return resp;
}

function toErrorMessage(err: unknown): string {
  const ax = err as AxiosError<any>;
  return (
    ax?.response?.data?.detail ||
    ax?.response?.data?.message ||
    ax?.message ||
    "Request failed"
  );
}

// ── CSRF helper ───────────────────────────────────────────────────────────────

/**
 * Read the CSRF token from the __csrf cookie.
 * This cookie is set by the server on login and is intentionally JS-readable
 * (httpOnly: false) so we can copy it into request headers.
 */
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null; // SSR guard
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith("__csrf="));
  return match ? decodeURIComponent(match.split("=")[1]) : null;
}

// ── Request interceptors ──────────────────────────────────────────────────────

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

api.interceptors.request.use(
  (cfg) => {
    // Always enforce credentials (cookie inclusion)
    cfg.withCredentials = true;

    // Normalize accidental double-proxy paths
    if (typeof cfg.url === "string" && cfg.url.startsWith("/api/proxy/")) {
      cfg.url = cfg.url.replace(/^\/api\/proxy/, "");
    } else if (cfg.url === "/api/proxy") {
      cfg.url = "/";
    }

    // Inject CSRF token for state-changing requests
    if (MUTATING_METHODS.has(method(cfg))) {
      const csrfToken = getCsrfToken();
      if (csrfToken) {
        cfg.headers = cfg.headers ?? {};
        (cfg.headers as Record<string, string>)["X-CSRF-Token"] = csrfToken;
      } else if (isProd) {
        // In production, missing CSRF token on a mutating request is a problem.
        // Log it — the proxy will reject the request with 403 anyway.
        console.warn("[API] CSRF token missing for mutating request:", method(cfg), cfg.url);
      }
    }

    return logRequest(cfg);
  },
  (error) => Promise.reject(error)
);

// ── Response interceptors ─────────────────────────────────────────────────────

api.interceptors.response.use(
  (resp) => logResponse(resp),
  (error: AxiosError) => {
    const status = error.response?.status;

    const normalized = new Error(toErrorMessage(error)) as Error & {
      status?: number;
      code?: string;
      raw?: AxiosError;
    };
    normalized.status = status;
    normalized.code = (error as any)?.code;
    normalized.raw = error;

    if (status === 401 || status === 403) {
      console.warn("[API] Unauthorized – triggering sign-out");
      try {
        getUnauthorizedHandler()?.();
      } catch {
        /* no-op */
      }
    }

    return Promise.reject(normalized);
  }
);

// ── Lightweight retry for transient network errors on safe methods ────────────

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
    (cfg.__retryCount || 0) < 2
  ) {
    cfg.__retryCount = (cfg.__retryCount || 0) + 1;
    const backoffMs = [400, 1000][cfg.__retryCount - 1];
    await new Promise((r) => setTimeout(r, backoffMs));
    return api.request(cfg);
  }

  return Promise.reject(error);
});

export default api;