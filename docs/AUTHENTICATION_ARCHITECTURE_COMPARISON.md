# Authentication Architecture: Current vs Proposed Design

**Date:** 2026-05-30  
**Status:** Analysis Complete  
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture (Dual-Path)](#2-current-architecture-dual-path)
   - 2.1 [Architecture Diagram](#21-architecture-diagram)
   - 2.2 [Component Scope](#22-component-scope)
   - 2.3 [Sequence Diagram: Login](#23-sequence-diagram-login)
   - 2.4 [Sequence Diagram: API Call](#24-sequence-diagram-api-call)
   - 2.5 [Sequence Diagram: SSE Connection](#25-sequence-diagram-sse-connection)
3. [Proposed Architecture (Cookie-Only)](#3-proposed-architecture-cookie-only)
   - 3.1 [Architecture Diagram](#31-architecture-diagram)
   - 3.2 [Component Scope](#32-component-scope)
   - 3.3 [Sequence Diagram: Login](#33-sequence-diagram-login)
   - 3.4 [Sequence Diagram: API Call](#34-sequence-diagram-api-call)
   - 3.5 [Sequence Diagram: SSE Connection](#35-sequence-diagram-sse-connection)
4. [API Call Comparison Table](#4-api-call-comparison-table)
5. [Flaws in Current Design](#5-flaws-in-current-design)
6. [Why the Proposed Design Is Best](#6-why-the-proposed-design-is-best)
7. [Migration Path](#7-migration-path)

---

## 1. Executive Summary

StockerPro currently uses a **dual-path authentication** system where Firebase ID tokens are sent via `Authorization: Bearer` header (by axios-based services) AND Firebase session cookies are sent via `__session` cookie (by fetch-based services and SSE). This inconsistency creates security vulnerabilities, maintenance burden, and bugs.

The proposed design eliminates the dual-path entirely, adopting a **cookie-only BFF (Backend for Frontend)** pattern where all authentication flows through an httpOnly session cookie — never exposing tokens to JavaScript.

---

## 2. Current Architecture (Dual-Path)

### 2.1 Architecture Diagram

```
                          ┌───────────────────────┐
                          │    Firebase Auth SDK   │
                          │    (client-side)       │
                          └──────┬────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │                         │
                    ▼                         ▼
         ┌──────────────────┐    ┌──────────────────────┐
         │  ID Token (JWT)  │    │  Session Cookie       │
         │  (in memory)     │    │  (httpOnly, lax)      │
         └────────┬─────────┘    └──────────┬───────────┘
                  │                          │
                  ▼                          ▼
    ┌──────────────────────┐    ┌──────────────────────────┐
    │  token-manager.ts    │    │  Browser auto-sends      │
    │  sets axios default  │    │  cookie on all requests  │
    │  Authorization: Bearer│   │  (withCredentials)       │
    └──────────┬───────────┘    └──────────┬───────────────┘
               │                           │
               │       ┌───────────────────┘
               │       │
               ▼       ▼
    ┌────────────────────────────────────┐
    │     Next.js Proxy                  │
    │  (api/proxy/[...path]/route.ts)    │
    │                                    │
    │  Token Resolution (priority):      │
    │  1. Authorization header ─────┬─── │  ← axios calls
    │  2. __session cookie ─────────┤    │  ← fetch/SSE calls
    │  3. Fallback cookies ─────────┘    │
    │                                    │
    │  Injects: Authorization: Bearer    │
    └──────────────────┬─────────────────┘
                       │
                       ▼
    ┌────────────────────────────────────┐
    │     Backend (auth.py)              │
    │                                    │
    │  Verification (fallback chain):    │
    │  1. verify_id_token(token) ────┐   │  ← for ID tokens
    │  2. verify_session_cookie(tok)─┘   │  ← for session cookies
    │  3. X-Verified-UID (SSE only)      │
    │                                    │
    │  BUG: id_token_error deleted by    │
    │  Python after except block         │
    └──────────────────┬─────────────────┘
                       │
                       ▼
    ┌────────────────────────────────────┐
    │     Firebase Admin SDK / Supabase  │
    └────────────────────────────────────┘
```

### 2.2 Component Scope

| Component | Technology | Location | Responsibility | Auth Role |
|-----------|-----------|----------|---------------|-----------|
| **Firebase Auth SDK** | JavaScript SDK | Client browser | User login, token lifecycle, `onIdTokenChanged` | Generates **ID token** |
| **AuthProvider** | React + Firebase | `web/src/providers/auth-provider.tsx` | Auth state machine, coordinates login/logout | Calls `getIdToken()`, `persistSessionCookie()`, `setAuthToken()` |
| **TokenManager** | TypeScript | `web/src/features/auth/services/token-manager.ts` | Sets/clears axios default `Authorization` header | Writes ID token to axios defaults |
| **Axios Instance** | Axios | `web/src/lib/api.ts` | HTTP client for watchlist, portfolio, auth services | Sends `Authorization: Bearer <id_token>` + `__session` cookie |
| **Fetch-Based Services** | Native fetch | `web/src/features/analysis/services/analysis.service.ts`, `moat.service.ts`, `useDividendAnalysis.ts` | HTTP client for analysis, moat, dividend | Sends `__session` cookie only (no header) |
| **SSE Connections** | EventSource | `web/src/providers/GlobalSSEProvider.tsx`, `useValuationStream.ts` | Real-time price/valuation updates | Sends `__session` cookie only (cannot set headers) |
| **Session Handler** | Next.js Route | `web/src/app/api/auth/session/route.ts` | Exchanges ID token for session cookie | Verifies ID token via Firebase Admin, mints session cookie |
| **Next.js Proxy** | Next.js Route | `web/src/app/api/proxy/[...path]/route.ts` | Forwards requests to backend, injects auth | Resolves token from headers or cookies, injects `Authorization` |
| **Backend Auth** | FastAPI + Firebase Admin | `backend/auth.py` | Verifies tokens, returns user identity | Dual verification: `verify_id_token` → `verify_session_cookie` fallback |
| **All Backend APIs** | FastAPI | `backend/api/*.py` (74 endpoints) | Business logic | Uses `Depends(get_current_user_dep)` |
| **Super Investors API** | FastAPI | `backend/api/super_investors.py` | Public data (2 endpoints) | **No auth** |

### 2.3 Sequence Diagram: Login

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│  User   │     │ Firebase SDK  │     │ AuthProvider │     │  Next.js   │     │ Firebase │
│ Browser │     │   (client)    │     │   (React)    │     │   Routes   │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └─────┬──────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │ signInWithEmailAndPassword()           │                  │                 │
     │─────────────────>│                     │                  │                 │
     │                  │                     │                  │                 │
     │                  │ onIdTokenChanged    │                  │                 │
     │                  │────────────────────>│                  │                 │
     │                  │                     │                  │                 │
     │                  │  getIdToken()       │                  │                 │
     │                  │<────────────────────│                  │                 │
     │                  │────id_token─────────│                  │                 │
     │                  │                     │                  │                 │
     │                  │                     │ setAuthToken(token)               │
     │                  │                     │──────────────────│                 │
     │                  │                     │  (sets axios     │                 │
     │                  │                     │   Authorization) │                 │
     │                  │                     │                  │                 │
     │                  │                     │ POST /api/auth/session            │
     │                  │                     │ { idToken }      │                 │
     │                  │                     │─────────────────>│                 │
     │                  │                     │                  │ verifyIdToken()│
     │                  │                     │                  │────────────────>
     │                  │                     │                  │ createSession  │
     │                  │                     │                  │ Cookie()       │
     │                  │                     │                  │<────────────────
     │                  │                     │                  │                 │
     │                  │                     │ Set-Cookie:      │                 │
     │                  │                     │ __session=...    │                 │
     │                  │                     │<─────────────────│                 │
     │                  │                     │                  │                 │
     │                  │                     │ POST /users/sync │                 │
     │                  │                     │ (Bearer + cookie)│                 │
     │                  │                     │─────────────────>│                 │
     │                  │                     │    [Forwarded to Backend]         │
     │                  │                     │                  │                 │
     │       [ID token in axios defaults + __session cookie set]                   │
     └──────────────────┴─────────────────────┴──────────────────┴─────────────────┘
```

**Problem:** After login, **two credentials exist** — the ID token in the axios `Authorization` header AND the `__session` cookie. They are separate, redundant, and one is accessible to JavaScript.

### 2.4 Sequence Diagram: API Call

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  User   │     │   Service     │     │  Next.js    │     │   Backend    │     │ Firebase │
│ Browser │     │ (axios/fetch) │     │   Proxy     │     │   (auth.py)  │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └──────┬───────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │                  │                     │                  │                 │
     │   ┌─── AXIOS CALL (watchlist, portfolio, auth) ───┐       │                 │
     │   │              │                     │           │       │                 │
     │   │              │ GET /api/proxy/...  │           │       │                 │
     │   │              │ Authorization:      │           │       │                 │
     │   │              │   Bearer <id_token> │           │       │                 │
     │   │              │ Cookie: __session   │           │       │                 │
     │   │              │─────────────────────>           │       │                 │
     │   │              │                     │           │       │                 │
     │   │              │                     │ extractTokenFromHeaders():          │
     │   │              │                     │ → finds Authorization header        │
     │   │              │                     │           │       │                 │
     │   │              │                     │ GET /path │       │                 │
     │   │              │                     │ Authorization: Bearer <id_token>    │
     │   │              │                     │──────────────────>                   │
     │   │              │                     │           │       │                 │
     │   │              │                     │           │ verify_id_token(token)  │
     │   │              │                     │           │       │────────────────>
     │   │              │                     │           │       │                 │
     │   │              │                     │           │ 200 ✓ │                 │
     │   │              │                     │<──────────────────│                 │
     │   │              │<─────────────────────│           │       │                 │
     │   │              │                     │           │       │                 │
     │   └─── WORKS (ID token found) ─────────┘           │       │                 │
     │                                                     │       │                 │
     │   ┌─── FETCH CALL (analysis, moat, dividend) ──────┐│       │                 │
     │   │              │                     │           ││       │                 │
     │   │              │ GET /api/proxy/...  │           ││       │                 │
     │   │              │ (NO Authorization) │           ││       │                 │
     │   │              │ Cookie: __session   │           ││       │                 │
     │   │              │─────────────────────>           ││       │                 │
     │   │              │                     │           ││       │                 │
     │   │              │                     │ extractTokenFromHeaders(): null     │
     │   │              │                     │ extractTokenFromCookies():          │
     │   │              │                     │ → finds __session cookie            │
     │   │              │                     │           ││       │                 │
     │   │              │                     │ GET /path ││       │                 │
     │   │              │                     │ Authorization: Bearer <session_cookie>│
     │   │              │                     │──────────────────>                   │
     │   │              │                     │           ││       │                 │
     │   │              │                     │           ││ verify_id_token()───►FAIL│
     │   │              │                     │           ││ (session cookie is NOT │
     │   │              │                     │           ││  an ID token)          │
     │   │              │                     │           ││       │                 │
     │   │              │                     │           ││ verify_session_cookie()│
     │   │              │                     │           ││────────────────────────>
     │   │              │                     │           ││       │                 │
     │   │              │                     │           ││ 200 ✓ │                 │
     │   │              │                     │<──────────────────││                 │
     │   │              │<─────────────────────│           │       │                 │
     │   │              │                     │           │       │                 │
     │   └─── WORKS (but via slow fallback) ──┘           │       │                 │
     │                                                     │       │                 │
     │   ┌─── SSE CONNECTION (EventSource) ───────────────┐│       │                 │
     │   │              │                     │           ││       │                 │
     │   │              │ EventSource(        │           ││       │                 │
     │   │              │   /api/proxy/stream)│           ││       │                 │
     │   │              │ (NO headers possible)           ││       │                 │
     │   │              │ Cookie: __session   │           ││       │                 │
     │   │              │─────────────────────>           ││       │                 │
     │   │              │                     │           ││       │                 │
     │   │              │                     │ extractTokenFromHeaders(): null     │
     │   │              │                     │ extractTokenFromCookies():          │
     │   │              │                     │ → finds __session cookie            │
     │   │              │                     │           ││       │                 │
     │   │              │                     │ For SSE:  ││       │                 │
     │   │              │                     │ decode cookie → extract uid         │
     │   │              │                     │ inject X-Verified-UID header        │
     │   │              │                     │           ││       │                 │
     │   │              │                     │ GET /stream (X-Verified-UID)        │
     │   │              │                     │──────────────────>                   │
     │   │              │                     │           ││       │                 │
     │   │              │                     │           ││ _is_trusted_proxy() ✓  │
     │   │              │                     │           ││ return {uid} (skip     │
     │   │              │                     │           ││ token verification)    │
     │   │              │                     │           ││ 200 ✓                 │
     │   │              │                     │<──────────────────││                 │
     │   │              │<─────────────────────│           │       │                 │
     │   └─── WORKS (via special SSE path) ───┘           │       │                 │
```

**Problem:** Three different code paths with different auth mechanisms, three different resolutions. The fetch path relies on a slow dual-verification fallback chain. The SSE path requires special-cased logic.

### 2.5 Sequence Diagram: SSE Connection

```
┌─────────┐     ┌──────────────────┐     ┌─────────────┐     ┌──────────────┐
│  User   │     │  GlobalSSEProvider│    │  Next.js    │     │   Backend    │
│ Browser │     │  (EventSource)    │     │   Proxy     │     │  watchlists  │
└────┬────┘     └───────┬──────────┘     └──────┬──────┘     └──────┬───────┘
     │                  │                       │                  │
     │                  │ new EventSource(       │                  │
     │                  │   '/api/proxy/         │                  │
     │                  │   watchlists/stream',  │                  │
     │                  │   { withCredentials:   │                  │
     │                  │     true })            │                  │
     │                  │──────────────────────>│                  │
     │                  │                       │                  │
     │                  │ [Cookie: __session]   │                  │
     │                  │ [NO Authorization]    │                  │
     │                  │                       │                  │
     │                  │                       │ extractTokenFrom │
     │                  │                       │ Headers(): → null │
     │                  │                       │                  │
     │                  │                       │ extractTokenFrom │
     │                  │                       │ Cookies():       │
     │                  │                       │ → __session=xxx  │
     │                  │                       │                  │
     │                  │                       │ isSSEPath(): true │
     │                  │                       │                  │
     │                  │                       │ decode session   │
     │                  │                       │ cookie to get uid│
     │                  │                       │                  │
     │                  │                       │ GET /watchlists/ │
     │                  │                       │   stream         │
     │                  │                       │ X-Verified-UID:  │
     │                  │                       │   <uid>          │
     │                  │                       │─────────────────>│
     │                  │                       │                  │
     │                  │                       │                  │ get_current_user()
     │                  │                       │                  │ → _is_trusted_proxy() ✓
     │                  │                       │                  │ → return {uid}
     │                  │                       │                  │
     │                  │                       │   SSE stream     │
     │                  │                       │<─────────────────│
     │                  │  SSE events            │                  │
     │                  │<──────────────────────│                  │
     │    price_update  │                       │                  │
     │<─────────────────│                       │                  │
```

**Problem:** SSE requires a completely separate auth path (`X-Verified-UID`) with its own special handling in both proxy and backend. This is fragile and adds complexity.

---

## 3. Proposed Architecture (Cookie-Only)

### 3.1 Architecture Diagram

```
                         ┌───────────────────────┐
                         │    Firebase Auth SDK   │
                         │    (client-side)       │
                         └──────┬────────────────┘
                                │
                    ┌───────────┘
                    ▼
         ┌──────────────────────┐
         │  ID Token (JWT)      │
         │  (in JS memory only) │
         │  NEVER sent to API   │
         └──────────┬───────────┘
                    │
                    ▼
         ┌──────────────────────────────────────┐
         │  BFF Session Endpoint               │
         │  POST /api/auth/session             │
         │                                     │
         │  Verify ID Token → Create Session   │
         │  Cookie → Return httpOnly cookie    │
         └──────────────────┬──────────────────┘
                            │
                            ▼
         ┌──────────────────────────────────────────┐
         │  __session Cookie                        │
         │  (httpOnly, Secure, SameSite=Strict)     │
         │  Single credential for ALL requests      │
         └──────────────────┬───────────────────────┘
                            │
               ┌────────────┴────────────┐
               │                         │
               ▼                         ▼
     ┌──────────────────┐     ┌───────────────────────┐
     │  Axios services  │     │  Fetch / EventSource  │
     │  (withCred: true)│     │  (cred: "include")    │
     │  NO Authorization│     │  NO Authorization     │
     │  header          │     │  header               │
     └────────┬─────────┘     └───────────┬───────────┘
              │                           │
              └──────────┬────────────────┘
                         │
                         ▼
              ┌──────────────────────────────┐
              │  Next.js Proxy               │
              │  (api/proxy/[...path]/...)   │
              │                              │
              │  Token Resolution:           │
              │  1. __session cookie ONLY    │
              │     (no Authorization header │
              │      fallback)               │
              │                              │
              │  Injects for ALL requests:   │
              │  Authorization: Bearer       │
              │    <session_cookie>          │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Backend (auth.py)           │
              │                              │
              │  Single verification:        │
              │  verify_session_cookie(token)│
              │  (check_revoked=True)        │
              │                              │
              │  SSE: X-Verified-UID         │
              │  still supported but         │
              │  unified                    │
              └──────────────┬───────────────┘
                             │
                             ▼
              ┌──────────────────────────────┐
              │  Firebase Admin SDK          │
              └──────────────────────────────┘
```

### 3.2 Component Scope

| Component | Technology | Location | Responsibility | Auth Role |
|-----------|-----------|----------|---------------|-----------|
| **Firebase Auth SDK** | JavaScript SDK | Client browser | User login, token lifecycle | Generates **ID token (JS memory only)** |
| **AuthProvider** | React + Firebase | `web/src/providers/auth-provider.tsx` | Auth state machine | Calls `getIdToken()` only for session exchange; **removes `setAuthToken()`** |
| **TokenManager** | TypeScript | `web/src/features/auth/services/token-manager.ts` | **REMOVED** | No longer needed |
| **Axios Instance** | Axios | `web/src/lib/api.ts` | HTTP client | Sends **only `__session` cookie** (withCredentials: true; **no Authorization header**) |
| **Fetch-Based Services** | Native fetch | `web/src/features/analysis/services/*.ts` | HTTP client | Sends `__session` cookie only (unchanged) |
| **SSE Connections** | EventSource | `web/src/providers/GlobalSSEProvider.tsx` | Real-time updates | Sends `__session` cookie only (unchanged) |
| **BFF Session Handler** | Next.js Route | `web/src/app/api/auth/session/route.ts` | Exchanges ID token for session cookie | Verifies ID token, mints session cookie (unchanged) |
| **Next.js Proxy** | Next.js Route | `web/src/app/api/proxy/[...path]/route.ts` | Forwards requests to backend | Reads **only `__session` cookie**; **removes `extractTokenFromHeaders()`** |
| **Backend Auth** | FastAPI + Firebase Admin | `backend/auth.py` | Verifies session cookie | **Single** verification: `verify_session_cookie` only; removes `verify_id_token` fallback |
| **All Backend APIs** | FastAPI | `backend/api/*.py` | Business logic | Uses `Depends(get_current_user_dep)` (unchanged) |
| **Super Investors API** | FastAPI | `backend/api/super_investors.py` | Public data | **No auth** (unchanged, optionally add auth) |

### 3.3 Sequence Diagram: Login

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│  User   │     │ Firebase SDK  │     │ AuthProvider │     │  Next.js   │     │ Firebase │
│ Browser │     │   (client)    │     │   (React)    │     │   Routes   │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └─────┬──────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │ signInWithEmailAndPassword()           │                  │                 │
     │─────────────────>│                     │                  │                 │
     │                  │                     │                  │                 │
     │                  │ onIdTokenChanged    │                  │                 │
     │                  │────────────────────>│                  │                 │
     │                  │                     │                  │                 │
     │                  │  getIdToken()       │                  │                 │
     │                  │<────────────────────│                  │                 │
     │                  │────id_token─────────│                  │                 │
     │                  │                     │                  │                 │
     │  ╔══════════════════════════════════════════════════════════════════════╗   │
     │  ║  NO setAuthToken() — token never leaves AuthProvider               ║   │
     │  ║  ID token lives only in JS memory, never stored or sent to API     ║   │
     │  ╚══════════════════════════════════════════════════════════════════════╝   │
     │                  │                     │                  │                 │
     │                  │                     │ POST /api/auth/session            │
     │                  │                     │ { idToken }      │                 │
     │                  │                     │─────────────────>│                 │
     │                  │                     │                  │ verifyIdToken()│
     │                  │                     │                  │────────────────>
     │                  │                     │                  │ createSession  │
     │                  │                     │                  │ Cookie()       │
     │                  │                     │                  │<────────────────
     │                  │                     │                  │                 │
     │                  │                     │ Set-Cookie:      │                 │
     │                  │                     │ __session=...    │                 │
     │                  │                     │ (httpOnly,       │                 │
     │                  │                     │  Secure,         │                 │
     │                  │                     │  SameSite=Strict)│                 │
     │                  │                     │<─────────────────│                 │
     │                  │                     │                  │                 │
     │                  │                     │ POST /users/sync │                 │
     │                  │                     │ (cookie only)    │                 │
     │                  │                     │─────────────────>│                 │
     │                  │                     │    [Forwarded to Backend]         │
     │                  │                     │                  │                 │
     │     [Single credential: __session cookie set. No ID token in headers.]     │
     └──────────────────┴─────────────────────┴──────────────────┴─────────────────┘
```

### 3.4 Sequence Diagram: API Call

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌──────────────┐     ┌──────────┐
│  User   │     │   Service     │     │  Next.js    │     │   Backend    │     │ Firebase │
│ Browser │     │ (axios/fetch) │     │   Proxy     │     │   (auth.py)  │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └──────┬───────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │                  │                     │                  │                 │
     │   ┌─── ALL CALLS (axios, fetch, EventSource) ───┐        │                 │
     │   │              │                     │         │        │                 │
     │   │              │ GET /api/proxy/...  │         │        │                 │
     │   │              │ (NO Authorization)  │         │        │                 │
     │   │              │ Cookie: __session   │         │        │                 │
     │   │              │────────>│           │         │        │                 │
     │   │              │         │           │         │        │                 │
     │   │              │         │ extractTokenFromHeaders(): null               │
     │   │              │         │ (removed — no longer reads header)             │
     │   │              │         │           │         │        │                 │
     │   │              │         │ extractTokenFromCookies():                     │
     │   │              │         │ → finds __session cookie (always)             │
     │   │              │         │           │         │        │                 │
     │   │              │         │ GET /path │         │        │                 │
     │   │              │         │ Authorization: Bearer <session_cookie>         │
     │   │              │         │──────────>│         │        │                 │
     │   │              │         │           │         │        │                 │
     │   │              │         │           │ verify_session_cookie(token)       │
     │   │              │         │           │         │────────────────────────>
     │   │              │         │           │         │        │                 │
     │   │              │         │           │         │ 200 ✓  │                 │
     │   │              │         │           │<────────────────│                  │
     │   │              │         │<──────────│         │        │                 │
     │   │              │         │           │         │        │                 │
     │   └─── EVERYTHING WORKS THE SAME WAY ──┘         │        │                 │
     │                                                   │        │                 │
     │   ╔══════════════════════════════════════════════════════════════════════╗  │
     │   ║  Single code path. Single verification. No fallback chain.          ║  │
     │   ║  No UnboundLocalError bug. No dual-maintenance burden.             ║  │
     │   ╚══════════════════════════════════════════════════════════════════════╝  │
```

### 3.5 Sequence Diagram: SSE Connection

```
┌─────────┐     ┌──────────────────┐     ┌─────────────┐     ┌──────────────┐
│  User   │     │  GlobalSSEProvider│    │  Next.js    │     │   Backend    │
│ Browser │     │  (EventSource)    │     │   Proxy     │     │  watchlists  │
└────┬────┘     └───────┬──────────┘     └──────┬──────┘     └──────┬───────┘
     │                  │                       │                  │
     │                  │ new EventSource(       │                  │
     │                  │   '/api/proxy/         │                  │
     │                  │   watchlists/stream',  │                  │
     │                  │   { withCredentials:   │                  │
     │                  │     true })            │                  │
     │                  │──────────────────────>│                  │
     │                  │                       │                  │
     │                  │ [Cookie: __session]   │                  │
     │                  │                       │                  │
     │                  │                       │ extractTokenFrom │
     │                  │                       │ Cookies():       │
     │                  │                       │ → __session=xxx  │
     │                  │                       │                  │
     │                  │                       │ Inject:           │
     │                  │                       │ Authorization:   │
     │                  │                       │   Bearer <cookie>│
     │                  │                       │                  │
     │                  │                       │ GET /watchlists/ │
     │                  │                       │   stream         │
     │                  │                       │ Authorization:   │
     │                  │                       │   Bearer <cookie>│
     │                  │                       │─────────────────>│
     │                  │                       │                  │
     │                  │                       │                  │ get_current_user()
     │                  │                       │                  │ → verify_session_cookie()
     │                  │                       │                  │   (same as all other calls)
     │                  │                       │                  │
     │                  │                       │   SSE stream     │
     │                  │                       │<─────────────────│
     │                  │  SSE events            │                  │
     │                  │<──────────────────────│                  │
     │    price_update  │                       │                  │
     │<─────────────────│                       │                  │
     │                  │                       │                  │
     │  ╔══════════════════════════════════════════════════════════╗│
     │  ║  SSE now uses the same auth path as EVERY other request ║│
     │  ║  No X-Verified-UID special case needed                  ║│
     │  ╚══════════════════════════════════════════════════════════╝│
```

---

## 4. API Call Comparison Table

| # | Method | Path | Auth (Current) | Auth (Proposed) | Transport (Current) | Transport (Proposed) |
|---|--------|------|---------------|----------------|-------------------|--------------------|
| 1 | GET | `/health` | None | None | — | — |
| 2 | GET | `/ready` | None | None | — | — |
| 3 | GET | `/scheduler/status` | None | None | — | — |
| 4 | POST | `/users/sync` | Bearer ID token + Cookie | Cookie only | `Authorization` header + `__session` | `__session` only |
| 5-31 | All portfolio endpoints (27) | Bearer ID token + Cookie | Cookie only | `Authorization` header + `__session` | `__session` only |
| 32-40 | All watchlist endpoints (9) | Bearer ID token + Cookie | Cookie only | `Authorization` header + `__session` | `__session` only |
| 41-45 | All watchlist-item endpoints (5) | Bearer ID token + Cookie | Cookie only | `Authorization` header + `__session` | `__session` only |
| 46-61 | All valuation endpoints (16) | Bearer ID token + Cookie | Cookie only | `Authorization` header + `__session` | `__session` only |
| 62 | POST | `/valuations/{symbol}/chat` | Bearer ID token + Cookie | Cookie only | `Authorization` header + `__session` | `__session` only |
| 63-74 | All analysis endpoints (12) | Cookie only | Cookie only | `__session` only | `__session` only |
| 75 | GET | `/analysis/{symbol}/super-investors` | None | None | — | — |
| 76 | GET | `/analysis/{symbol}/super-investors/history` | None | None | — | — |

**Key Changes:**
- **Endpoints 4-62 (63 endpoints):** Currently send redundant `Authorization: Bearer <id_token>` header + `__session` cookie. Proposed sends `__session` cookie only — header removed.
- **Endpoints 63-74 (12 endpoints):** Already send cookie only. No change needed.
- **Endpoints 75-76 (2 endpoints):** Public, no auth. No change needed.
- **Endpoints 1-3 (3 endpoints):** Health checks, no auth. No change needed.

---

## 5. Flaws in Current Design

### 5.1 Security Flaws

| # | Flaw | Severity | Detail |
|---|------|----------|--------|
| **F1** | **ID token exposed to XSS** | **Critical** | `token-manager.ts:18` stores the Firebase ID token in `axios.defaults.headers.common['Authorization']`. This header is sent to the API on every request. If an XSS vulnerability exists anywhere in the app, the attacker can read the token from memory or exfiltrate it via a request they trigger. The token can be used to impersonate the user until it expires (typically 1 hour). |
| **F2** | **Dual credentials increase attack surface** | **High** | The system maintains two valid credentials for each user: the ID token and the session cookie. An attacker needs to steal only one. The ID token is the weaker link (JS-accessible) and effectively bypasses the security of the httpOnly session cookie. |
| **F3** | **Token in Authorization header can leak via proxy logs** | **Medium** | The ID token travels in the `Authorization` header through the Next.js proxy to the backend. Any middleware, logging framework, or error handler that logs headers will capture the token. The `__session` cookie also traverses the proxy, but cookies are commonly redacted in logs. |
| **F4** | **CSRF protection weakened** | **Medium** | With `SameSite=Lax` on the session cookie (current setting) + `Authorization: Bearer` header present on all axios requests, mutating requests have two parallel protections. But the fetch-based services rely solely on the cookie — if `SameSite` is ever downgraded or a subdomain vulnerability exists, they're exposed. |
| **F5** | **X-Verified-UID creates auth bypass vector** | **High** | The proxy injects `X-Verified-UID` for SSE connections, which the backend trusts from localhost. While restricted to trusted proxy hosts, this is an additional auth path that must be maintained and audited separately. Any mistake in the proxy's session cookie verification can lead to auth bypass. |

### 5.2 Architectural Flaws

| # | Flaw | Severity | Detail |
|---|------|----------|--------|
| **A1** | **UnboundLocalError bug in auth.py** | **High** | `backend/auth.py:159` references `id_token_error` which Python 3 deletes after the `except` block on line 152. This causes a crash when session cookie verification fails but the ID token exception was already cleaned up. This is a production crash bug. |
| **A2** | **Dual fallback chain is slow** | **Medium** | Every request from fetch-based services (12 endpoints + SSE) triggers two Firebase Admin SDK calls: `verify_id_token` (fails) → `verify_session_cookie` (succeeds). Each verification is an HTTP call to Google's servers, adding 200-600ms latency to every request. |
| **A3** | **Three code paths for auth** | **Medium** | Axios calls send Bearer header → proxy reads header → backend verifies ID token. Fetch calls send cookie → proxy reads cookie → backend verifies session cookie (after failing ID token). SSE sends cookie → proxy reads cookie + decodes UID → backend trusts X-Verified-UID. Three different paths, three different maintenance burdens. |
| **A4** | **Inconsistent behavior between services** | **Medium** | Some services (watchlist, portfolio) use axios and "work" while others (analysis, moat) use fetch and appear to work but take a different path. A developer adding a new service may not know which pattern to follow, leading to subtle bugs. |
| **A5** | **X-Verified-UID trusts localhost by IP** | **Low** | `backend/auth.py:28` trusts `127.0.0.1`, `::1`, `localhost`, `::ffff:127.0.0.1`. If the proxy runs on a different host or behind a reverse proxy, this trust model breaks. It also prevents horizontal scaling where the proxy and backend might be on different hosts. |
| **A6** | **Fragile SSE auth** | **Medium** | SSE depends on the proxy correctly decoding the session cookie and injecting `X-Verified-UID`. If the cookie format changes (Firebase SDK update), if the session cookie is near expiration, or if the proxy can't decode the JWT, SSE silently fails. |

### 5.3 Maintenance Flaws

| # | Flaw | Severity | Detail |
|---|------|----------|--------|
| **M1** | **Firebase Admin SDK quota wasted** | **Low** | Every fetch-based API call generates 2 Firebase Admin verification calls (one failing, one succeeding). This doubles Firebase Admin SDK usage, consuming quota unnecessarily. |
| **M2** | **Two files manage auth tokens** | **Low** | `token-manager.ts` manages the axios Bearer header, while the proxy's `extractTokenFromCookies()` manages the cookie path. Any auth change requires updating both files, often with inconsistent results. |

---

## 6. Why the Proposed Design Is Best

### 6.1 Security Superiority

| Threat | Current Design | Proposed Design |
|--------|---------------|----------------|
| **XSS stealing credentials** | ID token accessible via `axios.defaults.headers` — XSS can read and exfiltrate it | httpOnly cookie — JavaScript **cannot** read it. XSS gains nothing. |
| **CSRF** | `SameSite=Lax` + `Authorization` header (redundant, but works) | `SameSite=Strict` + `X-Requested-With: XMLHttpRequest` custom header — **double-submit pattern** |
| **Token leakage in logs** | ID token sent in `Authorization` header — may be logged by middleware/proxy | Session cookie sent in `Cookie` header — standard log redaction practice |
| **Credential theft surface** | **Two** credentials exist (ID token + session cookie) | **One** credential exists (session cookie) |
| **Session revocation** | Must revoke both the ID token and the session cookie separately | `verify_session_cookie(check_revoked=True)` — single revocation check |
| **Man-in-the-middle** | ID token + cookie travel over HTTP if TLS is misconfigured | Cookie marked `Secure` — **only** sent over HTTPS |

### 6.2 Architectural Superiority

| Aspect | Current Design | Proposed Design |
|--------|---------------|----------------|
| **Auth paths** | 3 (Bearer header, cookie fallback, X-Verified-UID SSE) | **1** (cookie → session cookie verification) |
| **Verification calls per request** | 2 for fetch/analysis (id_token fails → session_cookie succeeds) | **1** (session cookie only) |
| **SSE handling** | Special-cased with `X-Verified-UID` header injection | **Unified** — same `Authorization: Bearer` as all other requests |
| **Proxy logic** | Reads headers + cookies (dual source of truth) | Reads **only** cookies (single source of truth) |
| **Backend auth logic** | 3-way check: X-Verified-UID → verify_id_token → verify_session_cookie | **1 check**: verify_session_cookie. SSE Path simplified. |
| **Token source of truth** | Split between `token-manager.ts` (in-memory) and `__session` cookie (httpOnly) | **Single source of truth**: the `__session` cookie |
| **Service consistency** | Different services use different auth transports | **All services identical** — cookie only |
| **Python bug** | `UnboundLocalError` on line 159 due to exception variable scoping | **Eliminated** — no fallback chain, no unused variable reference |

### 6.3 Compliance and Standards

| Standard | Current | Proposed |
|----------|---------|---------|
| **OWASP Session Management** | ❌ Dual credential violates "single session identifier" principle | ✅ Single httpOnly cookie |
| **OWASP XSS Prevention** | ❌ Token in axios headers is XSS-accessible | ✅ httpOnly cookie not accessible to JS |
| **OWASP CSRF Prevention** | ✅ Partial (SameSite=Lax + header) | ✅ SameSite=Strict + Custom Header |
| **SOC 2 Access Control** | ⚠️ Two credentials mean inconsistent audit trail | ✅ Single credential, consistent logging |
| **Principle of Least Privilege** | ❌ Token file has broad access to all API routes | ✅ Cookie scoped to path `/` with httpOnly |

### 6.4 The Single True Fix for the Production Bug

The `UnboundLocalError` on `backend/auth.py:159` is a symptom of the dual-path design. The fix is not to save the variable — it's to **eliminate the path that creates the error**.

```
Current:  try verify_id_token → FAIL → try verify_session_cookie → FAIL → crash
Proposed: try verify_session_cookie → FAIL → 401
```

No fallback = no dead variable reference = no bug.

---

## 7. Migration Path

### Phase 1: Backend Simplification (1 day)

| Step | File | Change |
|------|------|--------|
| 1.1 | `backend/auth.py` | Remove `verify_id_token` call. Keep `verify_session_cookie` as single verification. Remove `X-Verified-UID` path for SSE (proxy will now send session cookie as `Authorization: Bearer` instead). |
| 1.2 | `backend/auth.py` | Keep `X-Verified-UID` as optional fallback for backward compat during rollout. Add deprecation warning log. |

### Phase 2: Proxy Simplification (1 day)

| Step | File | Change |
|------|------|--------|
| 2.1 | `web/src/app/api/proxy/[...path]/route.ts` | Remove `extractTokenFromHeaders()` call. Proxy reads only `__session` cookie. |
| 2.2 | Same file | Remove `isSSEPath()` special-casing. All requests get same `Authorization: Bearer <cookie>` treatment. |
| 2.3 | Same file | Line 123 now always injects the session cookie as Bearer token. |

### Phase 3: Frontend Cleanup (1 day)

| Step | File | Change |
|------|------|--------|
| 3.1 | `web/src/providers/auth-provider.tsx` | Remove `setAuthToken(token)` calls (lines 99-100, 181-182). |
| 3.2 | `web/src/features/auth/services/token-manager.ts` | **Delete file.** No longer needed. |
| 3.3 | `web/src/providers/auth-provider.tsx` | Update imports — remove `setAuthToken` reference. |
| 3.4 | `web/src/providers/auth-provider.tsx` | Keep `persistSessionCookie()` call (still needed to create the session cookie). |

### Phase 4: Cookie Hardening (0.5 day)

| Step | File | Change |
|------|------|--------|
| 4.1 | `web/src/app/api/auth/session/route.ts` | Change `sameSite: "lax"` → `sameSite: "strict"` on line 28. |
| 4.2 | Same file | Ensure `secure: true` is enforced in production (already conditional on `isHttps`). |

### Rollback Plan

- The proxy change is the most critical — if removed first, the backend still accepts `Authorization: Bearer` (Phase 1 optional until fully tested).
- Keep `token-manager.ts` deleted file in version control history; restoring it plus reverting proxy is the rollback.
- Phase 1, 2, and 3 can be deployed independently as long as at least one auth path works at each step.
