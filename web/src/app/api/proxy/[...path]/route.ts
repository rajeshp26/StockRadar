// src/app/api/proxy/[...path]/route.ts
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";

/**
 * SECURE BRIDGE (Proxy) — Production-ready
 *
 * Responsibilities:
 *  1) Identity Injection: Extract Firebase (or future OIDC) ID token from headers/cookies
 *     and inject a guaranteed `Authorization: Bearer <token>` header to the backend.
 *  2) CORS Avoidance: Keep backend private by routing via same-origin Next.js API.
 *  3) SSE Piping: Stream Server-Sent Events through to the browser.
 *
 * Config (env):
 *  - BACKEND_ORIGIN               (default: "http://127.0.0.1:8001")
 *  - PROXY_IDTOKEN_COOKIE         (default: "__session")
 *  - PROXY_EXTRA_TOKEN_HEADERS    (default: "x-id-token,x-firebase-token")
 *  - PROXY_REQUIRE_AUTH           (default: "false") → set "true" in prod
 */

// Runtime hints for stable streaming behavior in Next.js
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BACKEND_ORIGIN = process.env.BACKEND_ORIGIN ?? "http://127.0.0.1:8001";
const PROXY_IDTOKEN_COOKIE = process.env.PROXY_IDTOKEN_COOKIE ?? "__session";
const EXTRA_TOKEN_HEADER_NAMES = (process.env.PROXY_EXTRA_TOKEN_HEADERS ??
  "x-id-token,x-firebase-token")
  .split(",")
  .map((h) => h.trim().toLowerCase())
  .filter(Boolean);

// ✅ Recommend enabling this in .env for prod
const REQUIRE_AUTH = (process.env.PROXY_REQUIRE_AUTH ?? "false").toLowerCase() === "true";

/** Treat this path as SSE (EventSource will include cookies automatically). */
function isSSEPath(path: string) {
  // Extend if you add more SSE endpoints later:
  return path.startsWith("watchlists/stream");
}

function normalizeBearer(tokenOrHeader: string | null | undefined): string | null {
  if (!tokenOrHeader) return null;
  const raw = tokenOrHeader.trim();
  if (!raw) return null;
  if (/^bearer\s+/i.test(raw)) return raw;
  return `Bearer ${raw}`;
}

function extractTokenFromHeaders(req: NextRequest): string | null {
  // 1) Standard Authorization header
  const auth = req.headers.get("authorization");
  if (auth && /^bearer\s+/i.test(auth)) return normalizeBearer(auth);

  // 2) Any configured extra headers carrying a raw token (no "Bearer " needed)
  for (const name of EXTRA_TOKEN_HEADER_NAMES) {
    const v = req.headers.get(name);
    if (v) {
      const norm = normalizeBearer(v);
      if (norm) return norm;
    }
  }
  return null;
}

function extractTokenFromCookies(): string | null {
  try {
    const jar = cookies();
    // Primary cookie
    const c = jar.get(PROXY_IDTOKEN_COOKIE)?.value;
    if (c) return normalizeBearer(c);

    // Optional fallbacks for other ecosystems
    const fallbacks = ["firebase_id_token", "sb-access-token"];
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
  const ip = req.headers.get("x-forwarded-for") ?? req.ip ?? "";
  if (ip) headers.set("X-Forwarded-For", ip);
  headers.set("X-Forwarded-Proto", req.nextUrl.protocol.replace(":", ""));
  headers.set("X-Forwarded-Host", req.headers.get("host") ?? "localhost");

  return headers;
}

async function proxy(request: NextRequest, method: string, pathParts: string[]) {
  const path = pathParts.join("/");
  const isSSE = isSSEPath(path);

  // Token resolution — cookie/headers only (no query token)
  const tokenFromHeaders = extractTokenFromHeaders(request);
  const tokenFromCookies = extractTokenFromCookies();
  const bearer = tokenFromHeaders ?? tokenFromCookies ?? null;

  const targetUrl = resolveTargetUrl(request, pathParts);

  // Minimal, privacy-safe logs (DO NOT log tokens or full URLs with query)
  const authPresent = !!bearer;
  console.log(`[PROXY] ${method} /${path} | auth=${authPresent ? "present" : "absent"} sse=${isSSE}`);

  // In secure deployments, block unauthenticated requests universally (SSE included).
  if (REQUIRE_AUTH && !bearer) {
    return NextResponse.json(
      { detail: "Unauthorized: missing ID token at proxy." },
      { status: 401 }
    );
  }

  const hasBody = !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
  const upstreamHeaders = buildUpstreamHeaders(request, bearer, isSSE, hasBody);

  const upstreamInit: RequestInit = {
    method,
    headers: upstreamHeaders,
    body: hasBody ? (request.body as unknown as ReadableStream | null) : undefined,
    // @ts-expect-error Node fetch hint for streaming request body
    duplex: hasBody ? "half" : undefined,
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

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: sseHeaders,
    });
  }

  const passthroughHeaders = new Headers();
  if (contentType) passthroughHeaders.set("Content-Type", contentType);

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
  h.set("Access-Control-Allow-Headers", "Authorization,Content-Type,Accept");
  h.set("Access-Control-Max-Age", "86400");
  return new NextResponse(null, { status: 204, headers: h });
}