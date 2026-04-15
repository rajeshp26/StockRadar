# 🛡️ Security Enhancement Design Document

**Document Version:** 1.0  
**Date:** April 2026  
**Target:** SOC 2 Ready  
**Status:** Planning

---

## 1. Executive Summary

### 1.1 Purpose

This document provides a comprehensive design for addressing security gaps identified in the StockerPro frontend application to achieve SOC 2 Ready security standards. It serves as the technical blueprint for implementation.

### 1.2 Current State Assessment

| Category | Current Rating | Target Rating |
|----------|---------------|--------------|
| Authentication | 7/10 | 9/10 |
| Authorization | 6/10 | 9/10 |
| API Security | 7/10 | 9/10 |
| Frontend Security | 5/10 | 9/10 |
| **Overall** | **6.5/10** | **9/10** |

### 1.3 Gaps Identified

1. **Server-Side Token Validation** - Commented out, not enforced
2. **Rate Limiting** - Not implemented on Next.js proxy
3. **Content Security Policy (CSP)** - Not configured
4. **CSRF Protection** - Not implemented
5. **Subresource Integrity** - Not used
6. **Security Audit Logging** - Minimal
7. **IP Allowlisting** - Uses wildcard `*`

---

## 2. Gap 1: Server-Side Token Validation

### 2.1 Problem

In `web/src/app/api/auth/session/route.ts`, token verification is commented out:

```typescript
// (Optional but recommended) Verify the token here for defense-in-depth:
// import { getAuth } from "firebase-admin/auth";
// await getAuth().verifyIdToken(idToken, /* checkRevoked= */true);
```

**Risk:** A malicious or revoked token could be used to mint a session cookie.

### 2.2 Design

#### Architecture

```
Browser → Firebase → ID Token → Next.js /api/auth/session (validate) → Backend
                                         ↓
                                   Firebase Admin SDK
                                         ↓
                                   Mint Session Cookie
```

#### Implementation

**File:** `web/src/app/api/auth/session/route.ts`

```typescript
import { getAuth } from "firebase-admin/auth";
import { initializeApp, getApps } from "firebase-admin/app";

const firebaseAdmin = initializeApp({
  credential: credential.Certial({
    projectId: process.env.FIREBASE_ADMIN_PROJECT_ID,
    clientEmail: process.env.FIREBASE_ADMIN_CLIENT_EMAIL,
    privateKey: process.env.FIREBASE_ADMIN_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  }),
}, 'admin');

export async function POST(req: NextRequest) {
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    // ignore; will treat as empty body
  }

  const { idToken, action } = body || {};
  const res = NextResponse.json({ ok: true });

  // Choose secure flag based on the incoming request's URL scheme.
  const isHttps = req.nextUrl.protocol === "https:";
  const cookieBase = {
    httpOnly: true,
    secure: isHttps,
    sameSite: "lax" as const,
    path: "/",
  };

  // Clear cookie
  if (action === "clear" || !idToken) {
    res.cookies.set({
      name: COOKIE_NAME,
      value: "",
      ...cookieBase,
      maxAge: 0,
    });
    return res;
  }

  if (typeof idToken !== "string" || idToken.length < 20) {
    return NextResponse.json(
      { ok: false, error: "Invalid token" },
      { status: 400 }
    );
  }

  try {
    // ✅ VERIFY TOKEN SERVER-SIDE
    const decodedToken = await getAuth().verifyIdToken(idToken, true);
    
    // Check if token was revoked
    if (decodedToken.disabled) {
      return NextResponse.json(
        { ok: false, error: "Token has been disabled" },
        { status: 401 }
      );
    }
    
    // Token is valid - proceed to mint cookie
    res.cookies.set({
      name: COOKIE_NAME,
      value: idToken,
      ...cookieBase,
      maxAge: COOKIE_MAX_AGE,
    });

    return res;
      
  } catch (error: any) {
    console.error("[Session] Token verification failed:", error);
    return NextResponse.json(
      { ok: false, error: "Invalid token" },
      { status: 401 }
    );
  }
}
```

#### Environment Variables Required

```bash
# .env.local (Server-side only)
FIREBASE_ADMIN_PROJECT_ID=your_project_id
FIREBASE_ADMIN_CLIENT_EMAIL=firebase-adminsdk@xxxxx.iam.gserviceaccount.com
FIREBASE_ADMIN_PRIVATE_KEY="-----BEGIN PRIVATE KEY..."
```

#### Dependencies

```bash
npm install firebase-admin
```

---

## 3. Gap 2: Rate Limiting

### 3.1 Problem

No rate limiting exists on the Next.js proxy. The backend has rate limiting (per existing docs), but the frontend proxy is unprotected.

**Risk:** Backend could be overwhelmed by client requests bypassing the backend rate limits.

### 3.2 Design

#### Architecture

```
Request → Rate Limit Middleware → Proxy Handler → Backend
              ↓
        Check: IP + User + Endpoint
              ↓
        [Allow] or [Reject 429]
```

#### Implementation Options

**Option A: Upstash Redis (Recommended for production)**

Install:
```bash
npm install @upstash/ratelimit
```

**File:** `web/src/lib/rate-limit.ts`

```typescript
import { Ratelimit } from "@upstash/ratelimit";
import { Redis } from "@upstash/redis";

const ratelimit = new Ratelimit({
  redis: Redis.fromEnv(),
  limiter: Ratelimit.slidingWindow(10, "10 s"),
  prefix: "stockerpro:ratelimit:",
});

export const checkRateLimit = async (identifier: string) => {
  const { success } = await ratelimit.limit(identifier);
  return success;
};
```

**Option B: In-Memory (Development)**

```typescript
// web/src/lib/rate-limit.ts
const requestCounts = new Map<string, { count: number; resetTime: number }>();

const WINDOW_MS = 10_000;
const MAX_REQUESTS = 10;

export function checkRateLimit(identifier: string): boolean {
  const now = Date.now();
  const record = requestCounts.get(identifier);
  
  if (!record || now > record.resetTime) {
    requestCounts.set(identifier, { count: 1, resetTime: now + WINDOW_MS });
    return true;
  }
  
  if (record.count >= MAX_REQUESTS) {
    return false;
  }
  
  record.count++;
  return true;
}
```

**Integration in Proxy:**

```typescript
// web/src/app/api/proxy/[...path]/route.ts

export async function GET(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const params = await ctx.params;
  
  // Rate limit by IP + endpoint
  const ip = request.headers.get("x-forwarded-for")?.split(",")[0] ?? "unknown";
  const identifier = `${ip}:${params.path.join("/")}`;
  
  const allowed = await checkRateLimit(identifier);
  if (!allowed) {
    return NextResponse.json(
      { detail: "Rate limit exceeded. Please try again later." },
      { status: 429 }
    );
  }
  
  // ... existing proxy logic
}
```

#### Rate Limit Tiers

| Endpoint Type | Limit (per 10s) | Burst |
|---------------|------------------|-------|
| Read (GET) | 30 | 50 |
| Write (POST/PUT) | 10 | 15 |
| Auth (sign-in/up) | 5 | 5 |
| SSE Stream | 1 | 1 |

---

## 4. Gap 3: Content Security Policy (CSP)

### 4.1 Problem

No CSP headers are set. The app is vulnerable to XSS, data injection, and clickjacking attacks.

**Risk:** Malicious scripts could be injected to steal tokens or user data.

### 4.2 Design

#### Implementation

**File:** `web/src/middleware.ts`

```typescript
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const COOKIE_NAME = process.env.PROXY_IDTOKEN_COOKIE ?? "__session";
const COOKIE_MAX_AGE = 60 * 60;

export function middleware(request: NextRequest) {
  const response = NextResponse.next();
  
  const isDev = process.env.NODE_ENV !== "production";
  
  const csp = isDev
    ? "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' http://localhost:* ws://localhost:*; frame-ancestors 'none';"
    : "default-src 'self'; script-src 'self'; connect-src 'self' https://*.firebaseio.com wss://*.firebaseio.com https://*.googleapis.com; frame-ancestors 'none';";
  
  // CSP Header
  response.headers.set("Content-Security-Policy", csp);
  
  // Additional Security Headers
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("X-XSS-Protection", "1; mode=block");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  
  return response;
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico).*)",
  ],
};
```

---

## 5. Gap 4: CSRF Protection

### 5.1 Problem

No CSRF token validation. State-changing operations could be triggered from malicious sites.

**Risk:** Cross-site request forgery attacks on authenticated users.

### 5.2 Design

#### Double-Submit Cookie Pattern

**File:** `web/src/lib/csrf.ts`

```typescript
import { NextRequest, NextResponse } from "next/server";

export function generateCsrfToken(): string {
  return Buffer.from(crypto.randomUUID()).toString("base64url");
}

export async function setCsrfCookie(response: NextResponse, token: string) {
  response.cookies.set("csrf-token", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 24,
  });
}

export function validateCsrfToken(request: NextRequest, bodyToken?: string): boolean {
  const cookieToken = request.cookies.get("csrf-token")?.value;
  
  if (!cookieToken || !bodyToken) {
    return false;
  }
  
  return cookieToken === bodyToken;
}
```

#### Integration

```typescript
// web/src/app/api/auth/session/route.ts

export async function POST(req: NextRequest) {
  let body: any = {};
  try {
    body = await req.json();
  } catch {
    // ignore
  }

  const { idToken, action, csrfToken } = body || {};
  const res = NextResponse.json({ ok: true });

  // Validate CSRF for state-changing operations
  if (action !== "clear" && !validateCsrfToken(req, csrfToken)) {
    return NextResponse.json(
      { ok: false, error: "CSRF validation failed" },
      { status: 403 }
    );
  }
  
  // ... rest of handler
}
```

---

## 6. Gap 5: Subresource Integrity

### 6.1 Problem

External scripts loaded without integrity verification.

**Risk:** Compromised CDN or supply chain attacks.

### 6.2 Design

Add package security audit to CI/CD:

```bash
# package.json scripts
{
  "scripts": {
    "security:audit": "npm audit --audit-level=high",
    "security:audit:fix": "npm audit fix"
  }
}
```

Add to CI pipeline:
```bash
npm audit --audit-level=high || exit 1
```

---

## 7. Gap 6: Security Audit Logging

### 7.1 Problem

Minimal logging exists. SOC 2 requires comprehensive audit trails.

**Risk:** Cannot investigate security incidents.

### 7.2 Design

**File:** `web/src/lib/security-logger.ts`

```typescript
type SecurityEventType = "LOGIN_SUCCESS" | "LOGIN_FAILURE" | "TOKEN_VERIFY_FAIL" | "RATE_LIMIT" | "CSRF_FAIL" | "LOGOUT";
type SecuritySeverity = "INFO" | "WARNING" | "ERROR";

type SecurityEvent = {
  type: SecurityEventType;
  severity: SecuritySeverity;
  userId?: string;
  ip?: string;
  details: string;
  timestamp: Date;
};

export function logSecurityEvent(event: Omit<SecurityEvent, "timestamp">) {
  const fullEvent: SecurityEvent = { ...event, timestamp: new Date() };
  
  if (process.env.NODE_ENV === "production") {
    // Send to CloudWatch/SIEM
    console.log(JSON.stringify({ service: "security", ...fullEvent }));
  } else {
    console.log(JSON.stringify({ service: "security", ...fullEvent }));
  }
  
  return fullEvent;
}
```

---

## 8. Gap 7: IP Allowlisting

### 8.1 Problem

CORS allows all origins: `Access-Control-Allow-Origin: "*"`

**Risk:** Any website can make authenticated requests.

### 8.2 Design

```typescript
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS ?? "")
  .split(",")
  .map((s) => s.trim())
  .filter(Boolean);

function isOriginAllowed(origin: string): boolean {
  if (process.env.NODE_ENV !== "production") return true;
  return ALLOWED_ORIGINS.includes(origin);
}
```

**Environment:**

```bash
# .env.local
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:9002

# .env.production
ALLOWED_ORIGINS=https://stockerpro.app,https://www.stockerpro.app
```

---

## 9. Implementation Roadmap

### Phase 1: Critical Security (Weeks 1-2)

| Task | Dependencies |
|------|--------------|
| Implement server-side token validation | firebase-admin |
| Add rate limiting middleware | @upstash/ratelimit |
| Set up security audit logging | None |

### Phase 2: Protocol Security (Weeks 3-4)

| Task | Dependencies |
|------|--------------|
| Add CSP headers via middleware | None |
| Implement CSRF protection | None |
| Configure security headers | None |

### Phase 3: Hardening (Weeks 5-6)

| Task | Dependencies |
|------|--------------|
| Configure IP allowlisting | Environment vars |
| Set up security audit pipeline | CloudWatch/SIEM |
| Add security audit to CI/CD | None |

### Phase 4: Compliance (Weeks 7-8)

| Task | Dependencies |
|------|--------------|
| Document security procedures | None |
| Run security assessment | Phase 1-3 complete |
| Address findings | Assessment results |

---

## 10. Dependencies Summary

```bash
npm install firebase-admin @upstash/ratelimit @upstash/redis
```

---

## 11. New Files Created

| File | Purpose |
|------|---------|
| `web/src/lib/rate-limit.ts` | Rate limiting logic |
| `web/src/lib/csrf.ts` | CSRF token management |
| `web/src/lib/security-logger.ts` | Security event logging |
| `web/src/middleware.ts` | Security headers |

## 12. Modified Files

| File | Changes |
|------|--------|
| `web/src/app/api/auth/session/route.ts` | Add token validation + CSRF |
| `web/src/app/api/proxy/[...path]/route.ts` | Add rate limiting |
| `web/package.json` | Add dependencies |
| `.env.example` | Add new environment variables |

## 13. Security Checklist

- [ ] Server-side token validation implemented
- [ ] Rate limiting configured per endpoint tier
- [ ] CSP headers applied
- [ ] CSRF protection enabled
- [ ] Additional security headers configured
- [ ] Security audit logging functional
- [ ] IP allowlist configured for production
- [ ] Security tests written
- [ ] CI/CD security checks in place

---

**Document prepared for StockerPro Security Enhancement**
**Target: SOC 2 Ready**