// web/src/lib/csrf.ts
/**
 * CSRF protection via the Double-Submit Cookie pattern with HMAC signing.
 *
 * HOW IT WORKS:
 *  1. On login, the session route calls attachCsrfCookie() which sets a
 *     JS-readable cookie (__csrf) containing an HMAC-signed random token.
 *  2. Client-side interceptor in api.ts reads this cookie and sends the value
 *     as the X-CSRF-Token request header on every mutating request.
 *  3. The proxy reads both the cookie and the header and validates them.
 *
 * WHY THIS IS SECURE:
 *  - The __csrf cookie has sameSite: strict — it is never sent cross-origin.
 *  - The HMAC signature prevents an attacker from forging valid tokens even if
 *    they know the pattern.
 *  - Timing-safe comparison prevents oracle attacks.
 *  - httpOnly: false is INTENTIONAL — the client must be able to read the cookie
 *    to copy it into the request header. (This is different from the session cookie.)
 */

import { createHmac, randomBytes, timingSafeEqual } from "crypto";
import type { NextRequest, NextResponse } from "next/server";

export const CSRF_COOKIE_NAME = "__csrf";
export const CSRF_HEADER_NAME = "X-CSRF-Token";

// ── Secret ───────────────────────────────────────────────────────────────────

function getCsrfSecret(): string {
    const secret = process.env.CSRF_SECRET;
    if (secret) return secret;

    if (process.env.NODE_ENV !== "production") {
        // Dev fallback — log a warning so developers know to set it
        console.warn(
            "[csrf] CSRF_SECRET not set. Using insecure dev fallback. " +
            "Set CSRF_SECRET in .env.local for development."
        );
        return "dev-csrf-secret-not-for-production-use-replace-me";
    }

    throw new Error(
        "[csrf] CSRF_SECRET environment variable is required in production."
    );
}

// ── Token generation ─────────────────────────────────────────────────────────

/**
 * Generate a cryptographically random HMAC-signed CSRF token.
 * Format: `<32-byte-hex>.<sha256-hmac-hex>`
 */
export function generateCsrfToken(): string {
    const random = randomBytes(32).toString("hex");
    const hmac = createHmac("sha256", getCsrfSecret())
        .update(random)
        .digest("hex");
    return `${random}.${hmac}`;
}

// ── Token validation ─────────────────────────────────────────────────────────

/**
 * Validate a CSRF token's HMAC signature.
 * Returns false for any malformed or tampered token.
 */
export function validateCsrfToken(token: string): boolean {
    if (!token || typeof token !== "string") return false;

    const dotIdx = token.lastIndexOf(".");
    if (dotIdx === -1) return false;

    const random = token.substring(0, dotIdx);
    const provided = token.substring(dotIdx + 1);

    if (!random || !provided) return false;

    const expected = createHmac("sha256", getCsrfSecret())
        .update(random)
        .digest("hex");

    try {
        const a = Buffer.from(provided.padEnd(expected.length, "0"), "hex");
        const b = Buffer.from(expected, "hex");
        // Length check first (avoids allocation mismatch in timingSafeEqual)
        if (a.length !== b.length) return false;
        return timingSafeEqual(a, b);
    } catch {
        return false;
    }
}

// ── Request-level validation ──────────────────────────────────────────────────

/**
 * Extract CSRF token from request headers.
 * We check headers only (not body) to avoid needing to parse the body twice.
 */
export function extractCsrfTokenFromRequest(request: NextRequest): string | null {
    return request.headers.get(CSRF_HEADER_NAME);
}

/**
 * Full CSRF validation for a server-side request.
 * Reads cookie from request and compares with header value.
 *
 * Returns true if valid, false if the request should be rejected with 403.
 */
export function validateRequestCsrf(request: NextRequest): boolean {
    const headerToken = extractCsrfTokenFromRequest(request);
    const cookieToken = request.cookies.get(CSRF_COOKIE_NAME)?.value;

    if (!headerToken || !cookieToken) return false;

    // Both must be structurally valid HMAC tokens (prevents trivial bypass with matching garbage)
    if (!validateCsrfToken(headerToken) || !validateCsrfToken(cookieToken)) return false;

    // And they must match each other (double-submit check)
    if (headerToken.length !== cookieToken.length) return false;
    try {
        return timingSafeEqual(Buffer.from(headerToken), Buffer.from(cookieToken));
    } catch {
        return false;
    }
}

// ── Cookie setter ─────────────────────────────────────────────────────────────

/**
 * Attach a CSRF cookie to an outgoing response.
 * Call this when minting a new session (login).
 *
 * NOTE: httpOnly is intentionally false — client JS must read this cookie
 *       to include in request headers. This is correct and by design.
 */
export function attachCsrfCookie(response: NextResponse, isHttps: boolean): string {
    const token = generateCsrfToken();

    response.cookies.set({
        name: CSRF_COOKIE_NAME,
        value: token,
        httpOnly: false,        // INTENTIONAL: client JS reads this
        secure: isHttps,
        sameSite: "strict",     // Stricter than session cookie — no cross-origin sending
        path: "/",
        maxAge: 60 * 60 * 24 * 5, // 5 days — match session cookie lifetime
    });

    return token;
}