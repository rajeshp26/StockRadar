// web/src/middleware.ts
/**
 * Next.js Edge Middleware — Security Headers
 *
 * Replaces the dead stub in web/src/proxy.ts.
 * Runs on every request before it reaches a route handler or page.
 *
 * Responsibilities:
 *  1. Content-Security-Policy (CSP) — prevents XSS and data injection
 *  2. Security headers — clickjacking, MIME sniffing, referrer, permissions
 *  3. HSTS — forces HTTPS in production
 *
 * ROLLOUT STRATEGY:
 *  Set NEXT_PUBLIC_CSP_REPORT_ONLY=true in .env.local first.
 *  Monitor browser console and fix all CSP violations.
 *  Then set NEXT_PUBLIC_CSP_REPORT_ONLY=false to enforce.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// ── CSP builder ───────────────────────────────────────────────────────────────

function buildCsp(isDev: boolean): string {
    if (isDev) {
        // Permissive in development — Next.js HMR and React DevTools need unsafe-inline/eval
        return [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob: https://images.unsplash.com",
            "font-src 'self' data:",
            "connect-src 'self'" +
            " http://localhost:*" +
            " ws://localhost:*" +
            " wss://localhost:*" +
            " https://viqdqgxcumcdhqxooplw.supabase.co" +
            " https://*.googleapis.com",
            "worker-src 'self' blob:",
            "frame-ancestors 'none'",
        ].join("; ");
    }

    // Production — strict
    // Note: style-src still needs unsafe-inline because shadcn/ui injects styles at runtime.
    // TODO Phase 3: add nonce support to remove unsafe-inline from script-src entirely.
    return [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob: https://images.unsplash.com",
        "font-src 'self' data:",
        "connect-src 'self'" +
        " https://viqdqgxcumcdhqxooplw.supabase.co" +
        " https://*.googleapis.com",
        "worker-src 'self' blob:",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "upgrade-insecure-requests",
    ].join("; ");
}

// ── Middleware ────────────────────────────────────────────────────────────────

export function middleware(request: NextRequest) {
    const response = NextResponse.next();
    const isDev = process.env.NODE_ENV !== "production";
    const csp = buildCsp(isDev);

    // Start with report-only mode to catch violations before enforcing.
    // Switch to "Content-Security-Policy" when all violations are resolved.
    const cspHeaderName =
        process.env.NEXT_PUBLIC_CSP_REPORT_ONLY === "true"
            ? "Content-Security-Policy-Report-Only"
            : "Content-Security-Policy";

    response.headers.set(cspHeaderName, csp);

    // Prevent clickjacking (belt + suspenders alongside CSP frame-ancestors)
    response.headers.set("X-Frame-Options", "DENY");

    // Prevent MIME type sniffing
    response.headers.set("X-Content-Type-Options", "nosniff");

    // Don't leak full URL to third parties in the Referer header
    response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");

    // Deny browser APIs StockerPro has no reason to use
    response.headers.set(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=(), bluetooth=()"
    );

    // HSTS: only set in production — setting this in dev permanently redirects localhost to HTTPS
    if (!isDev) {
        response.headers.set(
            "Strict-Transport-Security",
            "max-age=63072000; includeSubDomains; preload"
        );
    }

    // NOTE: X-XSS-Protection is intentionally absent.
    //       It is deprecated, ignored by modern browsers, and can introduce
    //       vulnerabilities in older IE. CSP handles XSS protection instead.

    return response;
}

export const config = {
    matcher: [
        // Apply to all routes except Next.js internals and static files
        "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|woff|woff2)$).*)",
    ],
};