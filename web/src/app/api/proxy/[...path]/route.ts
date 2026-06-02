// src/app/api/proxy/[...path]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

/**
 * SECURE BRIDGE (Proxy) — Cookie-only authentication
 *
 * Design:
 *  All authentication flows through a single httpOnly __session cookie.
 *  The proxy reads the cookie and injects an `Authorization: Bearer <session>`
 *  header for the backend — unifying auth across axios, fetch, and EventSource.
 *
 *  No `Authorization` headers from the client are accepted — only the cookie
 *  is trusted. This eliminates the dual-path (ID token + session cookie) and
 *  ensures EventSource (which cannot set custom headers) is treated identically.
 *
 * CSRF strategy:
 *  - SameSite=Strict on the session cookie (browser-enforced CSRF prevention)
 *  - X-Requested-With: XMLHttpRequest required on mutating requests (defense-in-depth)
 *    The axios instance sends this header by default; EventSource (GET-only) is exempt.
 *    This avoids the timing pitfalls of the Double-Submit Cookie pattern.
 *
 * Config (env):
 *  - BACKEND_ORIGIN               (default: "http://127.0.0.1:8001")
 *  - PROXY_IDTOKEN_COOKIE         (default: "__session")
 *  - PROXY_REQUIRE_AUTH           (default: "false") → set "true" in prod
 */

// Runtime hints for stable streaming behavior in Next.js
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8001";
const PROXY_IDTOKEN_COOKIE = process.env.PROXY_IDTOKEN_COOKIE ?? "__session";

// ✅ Recommend enabling this in .env for prod
const REQUIRE_AUTH = (process.env.PROXY_REQUIRE_AUTH ?? "false").toLowerCase() === "true";

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function isSSERequest(req: NextRequest): boolean {
  return (req.headers.get("accept") ?? "").includes("text/event-stream");
}

function isMutating(method: string): boolean {
  return MUTATING_METHODS.has(method.toUpperCase());
}

function normalizeBearer(tokenOrHeader: string | null | undefined): string | null {
  if (!tokenOrHeader) return null;
  const raw = tokenOrHeader.trim();
  if (!raw) return null;
  if (/^bearer\s+/i.test(raw)) return raw;
  return `Bearer ${raw}`;
}

async function extractToken(): Promise<string | null> {
  try {
    const jar = await cookies();
    // Primary cookie
    const c = jar.get(PROXY_IDTOKEN_COOKIE)?.value;
    if (c) return normalizeBearer(c);

    // Optional fallbacks for other ecosystems
    const fallbacks = ["sb-access-token"];
    for (const name of fallbacks) {
      const v = jar.get(name)?.value;
      if (v) return normalizeBearer(v);
    }
  } catch {
    // no-op
  }
  return null;
}

/**
 * Build upstream URL. Strip any accidental `token` query param on ALL routes
 * so secrets never hit backend logs/storage even if a client misuses the API.
 */
function resolveTargetUrl(req: NextRequest, pathParts: string[]) {
  const url = new URL(req.url);

  // Hard strip any token param for safety on ALL routes
  if (url.searchParams.has("token")) {
    url.searchParams.delete("token");
  }

  const upstream = new URL(BACKEND_ORIGIN);
  upstream.pathname = `/${pathParts.join("/")}`;
  upstream.search = url.search;
  return upstream.toString();
}

/** Build a stable set of headers for the upstream request. */
function buildUpstreamHeaders(
  req: NextRequest,
  bearer: string | null,
  isSSE: boolean,
  hasBody: boolean
): Headers {
  const headers = new Headers();

  // Accept
  const accept = req.headers.get("accept");
  headers.set("Accept", accept ?? (isSSE ? "text/event-stream" : "application/json, text/plain, */*"));

  // Content-Type only when body exists
  const contentType = req.headers.get("content-type");
  if (hasBody && contentType) {
    headers.set("Content-Type", contentType);
  }

  // Identity Injection (authoritative)
  if (bearer) headers.set("Authorization", bearer);

  // Useful proxy headers
  const ip = req.headers.get("x-forwarded-for") ?? "";
  if (ip) headers.set("X-Forwarded-For", ip);
  headers.set("X-Forwarded-Proto", req.nextUrl.protocol.replace(":", ""));
  headers.set("X-Forwarded-Host", req.headers.get("host") ?? "localhost");

  return headers;
}

/** Attach standard security headers to every proxy response. */
function attachSecurityHeaders(headers: Headers): void {
  headers.set("X-Content-Type-Options", "nosniff");
  headers.set("X-Frame-Options", "DENY");
  headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
}

async function proxy(request: NextRequest, method: string, pathParts: string[]) {
  const path = pathParts.join("/");
  const sse = isSSERequest(request);

  // CSRF defense-in-depth: require X-Requested-With on mutating requests.
  // The axios client sends this header by default. fetch() and EventSource
  // are GET-only and don't need it.
  if (isMutating(method) && !request.headers.get("X-Requested-With")) {
    console.warn(`[PROXY] Missing X-Requested-With header on ${method} /${path}`);
    return NextResponse.json(
      { detail: "CSRF protection: missing X-Requested-With header" },
      { status: 403 }
    );
  }

  // Token resolution — cookie only (no client-supplied Authorization header)
  const bearer = await extractToken();

  const targetUrl = resolveTargetUrl(request, pathParts);

  // Minimal, privacy-safe logs (DO NOT log tokens or full URLs with query)
  const authPresent = !!bearer;
  console.log(`[PROXY] ${method} /${path} | auth=${authPresent ? "present" : "absent"} sse=${sse}`);

  console.log(`[PROXY-DEBUG] ${method} /${path} | headers:`, {
    authorization: request.headers.get("authorization") ? "present" : "absent",
    cookie: request.headers.get("cookie") ? "present" : "absent",
    xRequestedWith: request.headers.get("x-requested-with") ? "present" : "absent",
  });

  // In secure deployments, block unauthenticated requests universally (SSE included).
  if (REQUIRE_AUTH && !bearer) {
    return NextResponse.json(
      { detail: "Unauthorized: missing session cookie at proxy." },
      { status: 401 }
    );
  }

  const hasBody = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
  const upstreamHeaders = buildUpstreamHeaders(request, bearer, sse, hasBody);

  // Buffer entire body to avoid Node.js ReadableStream / duplex issues with fetch
  let bodyBuffer: ArrayBuffer | undefined;
  if (hasBody) {
    try {
      bodyBuffer = await request.arrayBuffer();
    } catch (e) {
      console.error("[PROXY] Failed to read request body", e);
    }
  }

  const upstreamInit: RequestInit = {
    method,
    headers: upstreamHeaders,
    body: hasBody ? bodyBuffer : undefined,
    cache: "no-store",
  };

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, upstreamInit);
  } catch (e: any) {
    console.error("[PROXY] Upstream fetch failed:", e?.message ?? e);
    return NextResponse.json(
      { detail: "Bridge encountered an upstream error", error: String(e?.message ?? e) },
      { status: 502 }
    );
  }

  const contentType = upstream.headers.get("content-type") ?? "";
  if (contentType.includes("text/event-stream")) {
    const sseHeaders = new Headers();
    sseHeaders.set("Content-Type", "text/event-stream");
    sseHeaders.set("Cache-Control", "no-cache");
    sseHeaders.set("Connection", "keep-alive");
    sseHeaders.set("X-Accel-Buffering", "no");
    attachSecurityHeaders(sseHeaders);

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: sseHeaders,
    });
  }

  const passthroughHeaders = new Headers();
  if (contentType) passthroughHeaders.set("Content-Type", contentType);
  attachSecurityHeaders(passthroughHeaders);

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: passthroughHeaders,
  });
}

/* ----------------------------- Route handlers ----------------------------- */

export async function GET(
  request: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const params = await ctx.params;
  return proxy(request, "GET", params.path);
}

export async function POST(
  request: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const params = await ctx.params;
  return proxy(request, "POST", params.path);
}

export async function PUT(
  request: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const params = await ctx.params;
  return proxy(request, "PUT", params.path);
}

export async function PATCH(
  request: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const params = await ctx.params;
  return proxy(request, "PATCH", params.path);
}

export async function DELETE(
  request: NextRequest,
  ctx: { params: Promise<{ path: string[] }> }
) {
  const params = await ctx.params;
  return proxy(request, "DELETE", params.path);
}

/**
 * Optional: handle CORS preflight if you ever call this cross-origin.
 * For same-origin (recommended), this will rarely trigger.
 */
export async function OPTIONS() {
  const h = new Headers();
  h.set("Access-Control-Allow-Origin", "*");
  h.set("Access-Control-Allow-Methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS");
  h.set("Access-Control-Allow-Headers", "Authorization,Content-Type,Accept,X-Requested-With");
  h.set("Access-Control-Max-Age", "86400");
  return new NextResponse(null, { status: 204, headers: h });
}
