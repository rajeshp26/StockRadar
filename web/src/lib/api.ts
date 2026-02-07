import axios, { AxiosError, AxiosRequestConfig, InternalAxiosRequestConfig } from 'axios';
import { getUnauthorizedHandler } from '@/features/auth/services/token-manager';

// --- Security & Reliability defaults ---
const isProd = process.env.NODE_ENV === 'production';

// In production we expect an explicit backend URL.
// In development we use the Next.js proxy.
const baseURL = isProd
  ? (process.env.NEXT_PUBLIC_API_URL as string)
  : (process.env.NEXT_PUBLIC_API_URL || '/api/proxy');

// Fail fast if prod URL is missing (prevents accidental proxy use in prod)
if (isProd && !baseURL) {
  // eslint-disable-next-line no-console
  console.error('[API] NEXT_PUBLIC_API_URL is not set in production. Requests will fail.');
}

export const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
    // Optional: identify XHR to backend logs
    'X-Requested-With': 'XMLHttpRequest',
  },
  // Reasonable client-side guardrails
  timeout: 12_000, // 12s
  // Don’t automatically treat 4xx as success
  validateStatus: (status) => status >= 200 && status < 300,
  // CORS/credentials: Bearer token is in header; no cookies for API calls
  withCredentials: false,
});

// --- Utilities ---
const redactUrl = (url: string | undefined) =>
  (url || '').replace(/(token=)[^&]+/i, '$1<redacted>');

const method = (cfg?: AxiosRequestConfig) => (cfg?.method || 'get').toUpperCase();

function logRequest(cfg: InternalAxiosRequestConfig) {
  if (isProd) return cfg; // disable noisy logs in prod
  const safeUrl = `${cfg.baseURL || ''}${redactUrl(cfg.url)}`;
  // Avoid printing headers (contains Authorization)
  // eslint-disable-next-line no-console
  console.debug(`[API] → ${method(cfg)} ${safeUrl}`);
  return cfg;
}

function logResponse(resp: any) {
  if (isProd) return resp;
  const safeUrl = `${resp.config?.baseURL || ''}${redactUrl(resp.config?.url)}`;
  // eslint-disable-next-line no-console
  console.debug(`[API] ← ${method(resp.config)} ${safeUrl} ${resp.status}`);
  return resp;
}

function toErrorMessage(err: unknown): string {
  // Backend standard: { detail: string }
  const ax = err as AxiosError<any>;
  const msg =
    ax?.response?.data?.detail ||
    ax?.response?.data?.message ||
    ax?.message ||
    'Request failed';
  return msg;
}

// --- Interceptors ---
api.interceptors.request.use(
  (cfg) => logRequest(cfg),
  (error) => Promise.reject(error),
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
      console.warn('[API] Unauthorized – triggering sign-out');
      try {
        getUnauthorizedHandler()?.(); // non-blocking
      } catch (_) { /* no-op */ }
    }

    // Respect server rate limits: do NOT auto-retry 429 here
    // (UI can throttle buttons instead of hammering the server)
    return Promise.reject(normalized);
  }
);

// Optional: lightweight retry for transient network errors on safe methods
// (We avoid retrying POST/PATCH/DELETE to respect rate limits and idempotency)
const NETWORK_ERROR_CODES = new Set(['ECONNABORTED', 'ERR_NETWORK', 'ETIMEDOUT']);
api.interceptors.response.use(undefined, async (error: any) => {
  const cfg = error?.config as InternalAxiosRequestConfig & { __retryCount?: number };
  const methodName = method(cfg);
  const isSafeMethod = methodName === 'GET' || methodName === 'HEAD';

  if (
    isSafeMethod &&
    NETWORK_ERROR_CODES.has(error?.code) &&
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