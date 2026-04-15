// web/src/app/api/auth/session/route.ts
import { NextRequest, NextResponse } from "next/server";
import {
  getAdminAuth,
  SESSION_COOKIE_NAME,
  SESSION_COOKIE_MAX_AGE_SECONDS,
  SESSION_COOKIE_EXPIRES_MS,
} from "@/lib/firebase-admin";
import { attachCsrfCookie } from "@/lib/csrf";
import { logSecurityEvent } from "@/lib/security-logger";

export async function POST(req: NextRequest) {
  let body: Record<string, unknown> = {};
  try {
    body = await req.json();
  } catch {
    // treat as empty body
  }

  const { idToken, action } = body as { idToken?: string; action?: string };
  const ip =
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  const isHttps = req.nextUrl.protocol === "https:";

  const cookieBase = {
    httpOnly: true,
    secure: isHttps,
    sameSite: "lax" as const,
    path: "/",
  };

  // ── CLEAR ────────────────────────────────────────────────────────────────
  if (action === "clear" || !idToken) {
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
  if (typeof idToken !== "string" || idToken.length < 20) {
    return NextResponse.json({ ok: false, error: "Invalid token format" }, { status: 400 });
  }

  // ── VERIFY + MINT SESSION COOKIE ──────────────────────────────────────────
  try {
    const adminAuth = getAdminAuth();
    const decoded = await adminAuth.verifyIdToken(idToken, true);
    const sessionCookie = await adminAuth.createSessionCookie(idToken, {
      expiresIn: SESSION_COOKIE_EXPIRES_MS,
    });

    const res = NextResponse.json({ ok: true });
    res.cookies.set({
      name: SESSION_COOKIE_NAME,
      value: sessionCookie,
      ...cookieBase,
      maxAge: SESSION_COOKIE_MAX_AGE_SECONDS,
    });
    attachCsrfCookie(res, isHttps);

    logSecurityEvent({
      type: "LOGIN_SUCCESS",
      severity: "INFO",
      userId: decoded.uid,
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