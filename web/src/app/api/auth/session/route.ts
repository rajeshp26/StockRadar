import { NextRequest, NextResponse } from "next/server";
import { jwtVerify } from "jose";
import { attachCsrfCookie } from "@/lib/csrf";
import { logSecurityEvent } from "@/lib/security-logger";

const SESSION_COOKIE_NAME = "__session";
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 5; // 5 days

export async function POST(req: NextRequest) {
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    // treat as empty body
  }

  const { accessToken, action } = body as { accessToken?: string; action?: string };
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  const isHttps = req.nextUrl.protocol === "https:";

  const cookieBase = {
    httpOnly: true,
    secure: isHttps,
    sameSite: "strict" as const,
    path: "/",
  };

  // ── CLEAR ────────────────────────────────────────────────────────────────
  if (action === "clear" || !accessToken) {
    const res = NextResponse.json({ ok: true });
    res.cookies.set({ name: SESSION_COOKIE_NAME, value: "", ...cookieBase, maxAge: 0 });
    res.cookies.set({
      name: "__csrf",
      value: "",
      httpOnly: false,
      secure: isHttps,
      sameSite: "strict" as const,
      path: "/",
      maxAge: 0,
    });
    logSecurityEvent({ type: "LOGOUT", severity: "INFO", ip, details: "Session cleared" });
    return res;
  }

  // ── BASIC VALIDATION ──────────────────────────────────────────────────────
  if (typeof accessToken !== "string" || accessToken.length < 20) {
    return NextResponse.json({ ok: false, error: "Invalid token format" }, { status: 400 });
  }

  // ── VERIFY TOKEN LOCALLY ──────────────────────────────────────────────────
  try {
    const secret = new TextEncoder().encode(process.env.SUPABASE_JWT_SECRET);
    const { payload } = await jwtVerify(accessToken, secret, {
      audience: "authenticated",
      algorithms: ["HS256"],
    });

    const res = NextResponse.json({ ok: true });
    res.cookies.set({
      name: SESSION_COOKIE_NAME,
      value: accessToken,
      ...cookieBase,
      maxAge: SESSION_MAX_AGE_SECONDS,
    });
    attachCsrfCookie(res, isHttps);

    logSecurityEvent({
      type: "LOGIN_SUCCESS",
      severity: "INFO",
      userId: payload.sub as string,
      ip,
      details: "Session cookie minted",
    });
    return res;
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("[Session] Token verification failed:", message);
    logSecurityEvent({
      type: "TOKEN_VERIFY_FAIL",
      severity: "WARNING",
      ip,
      details: `Verification failed: ${message.substring(0, 200)}`,
    });
    return NextResponse.json({ ok: false, error: "Invalid or revoked token" }, { status: 401 });
  }
}
