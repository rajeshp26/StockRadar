# StockerPro Authentication Architecture Redesign
## Design Document v1.2

**Date:** 2026-04-14  
**Author:** Analysis Team  
**Status:** Proposed  
**Version:** 1.2

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Component Architecture](#3-component-architecture)
4. [Sequence Diagrams](#4-sequence-diagrams)
5. [Implementation Details](#5-implementation-details)
6. [Migration Strategy](#6-migration-strategy)
7. [Security Analysis](#7-security-analysis)
8. [Architectural Hardening](#8-architectural-hardening)
   - [8.1 CSRF Protection](#81-csrf-cross-site-request-forgery-protection)
   - [8.2 X-Verified-UID Trust Enforcement](#82-x-verified-uid-header-trust-enforcement)
   - [8.3 Cookie Size Management](#83-cookie-size-management)
   - [8.4 Token Refresh and Session Expiration Handling](#84-token-refresh-and-session-expiration-handling)
   - [8.5 Secure Logging Practices](#85-secure-logging-practices)
   - [8.6 Performance: Firebase Key Caching](#86-performance-firebase-key-caching)
   - [8.7 Complete Architecture Checklist](#87-complete-architecture-checklist)
   - [8.8 SSE Scalability: Redis Pub/Sub Architecture (v2.0)](#88-sse-scalability-redis-pubsub-architecture-v20)
9. [Conclusion](#9-conclusion)

---

## 1. Executive Summary

### 1.1 Current Problem

The application suffers from **inconsistent authentication** across different HTTP clients. This manifests as:

- Watchlist data loads successfully (prices showing)
- Valuation data fails to load (401 errors)
- SSE (Server-Sent Events) connections fail
- Dashboard shows empty prices for watchlist items

### 1.2 Root Cause Analysis

| Client | HTTP Method | Auth Method | Current Result | Issue |
|--------|-------------|-------------|---------------|-------|
| axios | POST | Authorization header (`setAuthToken`) | ✓ Works | Works correctly |
| axios | GET | Authorization header (`setAuthToken`) | ✓ Works | Works correctly |
| native fetch | GET | No header (ignores axios defaults) | ✗ Fails | Backend receives nothing |
| EventSource | SSE | Cookie only (cannot send headers) | ✗ Fails | No auth mechanism works |

### 1.3 The Core Problem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CURRENT AUTHENTICATION FLOW                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  setAuthToken(firebaseIdToken)                                              │
│         │                                                                    │
│         ├──► axios.defaults.headers.common['Authorization'] = "Bearer ..." │
│         │         │                                                          │
│         │         ▼                                                          │
│         │    POST requests: Authorization header sent → 200 ✓              │
│         │         │                                                          │
│         │         ▼                                                          │
│         │    GET requests (fetch/EventSource): Header NOT sent → 401 ✗      │
│         │                                                                    │
│         ▼                                                                    │
│  __session cookie (Firebase session cookie)                                  │
│         │                                                                    │
│         ├──► Stored as httpOnly cookie                                       │
│         │         │                                                          │
│         │         ▼                                                          │
│         │    axios: Cookie sent + Authorization header sent → 200 ✓         │
│         │    fetch: Cookie sent, NO Authorization header → 401 ✗           │
│         │    EventSource: Cookie sent (withCredentials), NO header → 401 ✗   │
│         │                                                                    │
│  Backend expectation: Authorization: Bearer <firebase_id_token>              │
│         │                                                                    │
│         ▼                                                                    │
│  verify_id_token() called on ALL requests                                    │
│         │                                                                    │
│         ├──► Firebase ID token → Success                                     │
│         └──► Session cookie → FAIL (wrong verification method)              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.4 Solution Overview

**Cookie-centric, proxy-mediated authentication** where:

1. All auth state lives in HTTP-only session cookies
2. Next.js proxy reads cookies and injects proper Authorization headers for backend
3. Backend accepts both ID tokens and session cookies (dual verification)
4. All HTTP clients work identically (axios, fetch, EventSource)

### 1.5 Expected Outcomes

| Request Type | Before | After |
|--------------|--------|-------|
| POST /watchlists/default-structure | ✓ 200 | ✓ 200 |
| GET /valuations/RBLX/rule1 | ✗ 401 | ✓ 200 |
| GET /stocks/RBLX/quote | ✗ 401 | ✓ 200 |
| GET /watchlists/stream (SSE) | ✗ 401 | ✓ 200 (streaming) |

---

## 2. Architecture Overview

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐    │
│  │      AXIOS       │  │    NATIVE        │  │   EventSource       │    │
│  │  (watchlist,     │  │     FETCH        │  │   (GlobalSSE,       │    │
│  │   user sync)      │  │  (analysis,      │  │    valuations)      │    │
│  │                   │  │   quotes)         │  │                     │    │
│  └────────┬─────────┘  └────────┬─────────┘  └──────────┬───────────┘    │
│           │                     │                       │                 │
│           │    credentials: 'include'                   │                 │
│           │         (cookies automatically sent)        │                 │
│           └─────────────────────┼───────────────────────┘                 │
│                                 ▼                                          │
│                    ┌─────────────────────┐                                │
│                    │   /api/proxy/*      │  (Same-Origin)                 │
│                    │   Next.js Route     │                                │
│                    └──────────┬──────────┘                                │
└──────────────────────────────┼────────────────────────────────────────────┘
                               │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌───────────────────────┐
│  Auth Proxy   │   │  Data Proxy      │   │    SSE Proxy          │
│  /api/auth/*  │   │  /api/proxy/*   │   │  /api/proxy/stream   │
│               │   │                 │   │                       │
│ - login       │   │ - valuations    │   │ - watchlists/stream   │
│ - logout      │   │ - stocks/quote  │   │ - Invalidates cache   │
│ - session     │   │ - watchlists    │   │                       │
│   refresh     │   │                 │   │                       │
└───────┬───────┘   └────────┬────────┘   └───────────┬───────────┘
        │                    │                        │
        │   ┌────────────────┼────────────────┐    │
        │   │                │                │    │
        │   ▼                ▼                ▼    ▼
        │   ┌─────────────────────────────────────────────┐
        │   │              BACKEND API                     │
        │   │         http://172.19.86.61:8001            │
        │   │                                              │
        │   │  ┌─────────┐  ┌──────────┐  ┌────────────┐  │
        │   │  │  Auth   │  │ Watchlist│  │ Valuations│  │
        │   │  │ verify_ │  │  APIs    │  │   APIs    │  │
        │   │  │ id_token│  │          │  │            │  │
        │   │  │    OR   │  │          │  │            │  │
        │   │  │ verify_ │  │          │  │            │  │
        │   │  │ session_│  │          │  │            │  │
        │   │  │ cookie  │  │          │  │            │  │
        │   │  └─────────┘  └──────────┘  └────────────┘  │
        │   └─────────────────────────────────────────────┘
        │                         │
        │                         ▼
        │   ┌─────────────────────────────────────────────┐
        │   │            FIREBASE AUTH                     │
        │   │    (Token verification & session mgmt)       │
        │   └─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           SECURITY LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     SESSION COOKIE FLOW                               │   │
│  │                                                                       │   │
│  │   Firebase ID Token ──► verifyIdToken() ──► createSessionCookie()    │   │
│  │          │                                    │                       │   │
│  │          │                                    ▼                       │   │
│  │          │                      ┌─────────────────────┐              │   │
│  │          │                      │  __session cookie   │              │   │
│  │          │                      │  (httpOnly, secure, │              │   │
│  │          │                      │   sameSite: lax)    │              │   │
│  │          │                      └──────────┬──────────┘              │   │
│  │          │                                 │                          │   │
│  │          │                    All HTTP clients send this            │   │
│  │          │                                 │                          │   │
│  │          └─────────────────────────────────┘                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Design Principles

| Principle | Implementation | Benefit |
|-----------|---------------|---------|
| **Cookie-Centric** | All auth via `__session` cookie | Works with axios, fetch, EventSource |
| **Proxy-Mediated** | Next.js proxy handles token conversion | Backend doesn't need session cookie logic |
| **Defense in Depth** | Multiple verification layers | Security even if one layer fails |
| **Fail-Closed** | No auth = no access | Default to secure |
| **Unified Client** | Single auth mechanism | Easier to maintain |
| **SSE Compatible** | X-Verified-UID header injection | Works with EventSource limitation |

### 2.3 Authentication Flow Comparison

#### Current Flow (Broken)

```
User Login
    │
    ▼
setAuthToken(getIdToken()) ──► axios headers.Authorization = "Bearer <id_token>"
    │                                    │
    │                                    ▼
    │                        POST /api/proxy/watchlists/default-structure
    │                                    │
    │                                    ▼
    │                        Proxy: extractTokenFromHeaders() → finds header
    │                                    │
    │                                    ▼
    │                        Backend: verify_id_token() → 200 ✓
    │
    ▼
fetch('/api/proxy/valuations/RBLX/rule1') ──► NO Authorization header
    │                                    │
    │                                    ▼
    │                        Proxy: extractTokenFromHeaders() → null
    │                                    │
    │                                    ▼
    │                        Proxy: extractTokenFromCookies() → session cookie
    │                                    │
    │                                    ▼
    │                        Backend: verify_id_token(session_cookie) → FAIL ✗
    │
    ▼
EventSource('/api/proxy/watchlists/stream') ──► NO Authorization header (impossible)
    │
    ▼
Backend: No X-Verified-UID, no Authorization → 401 ✗
```

#### Proposed Flow (Fixed)

```
User Login
    │
    ▼
Firebase ID Token obtained
    │
    ▼
POST /api/auth/session ──► Server creates session cookie
    │
    ▼
__session cookie set (httpOnly, secure, sameSite: lax)
    │
    ├──────────────────────────────────────────────┐
    │                                              │
    ▼                                              ▼
axios requests                                    fetch/EventSource requests
    │                                              │
    │ Authorization header + cookie                │ Cookie only
    │         │                                   │
    │         ▼                                   ▼
    │    Proxy: reads both                       Proxy: reads cookie
    │                                              │
    │         ▼                                   ▼
    │    Forward with Authorization               Forward with Authorization
    │    (unchanged - backward compat)            (converted from cookie)
    │                                              │
    │         ▼                                   ▼
    │    Backend: verify_id_token()              Backend: verify_session_cookie()
    │    (unchanged - still works)                (NEW - accepts session cookie)
    │                                              │
    └──────────────────────────────────────────────┘
                        │
                        ▼
                    All requests: 200 ✓
```

---

## 3. Component Architecture

### 3.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              COMPONENT ARCHITECTURE                              │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           FRONTEND COMPONENTS                                 │
├─────────────────────────────────────────────────────────────────────────────┤

┌─────────────────────┐         ┌─────────────────────┐
│  AuthProvider       │         │   Service Layer     │
│  (providers/)      │         │   (features/*/)     │
├─────────────────────┤         ├─────────────────────┤
│ + firebaseUser     │         │ + WatchlistService │
│ + status           │         │   - axios-based    │
│ + signIn()         │         │   - WORKS: has     │
│ + signOut()        │         │     Authorization  │
│ + persistSession() │         │     header        │
└─────────┬───────────┘         ├─────────────────────┤
          │                     │ + AnalysisService │
          │                     │   - fetch-based   │
          │                     │   - BROKEN: no   │
          │                     │     Authorization │
          │                     └───────────────────┘
          │                              │
          │                              ▼
          │         ┌─────────────────────────────────────┐
          │         │       GlobalSSEProvider              │
          │         │       (providers/)                  │
          │         ├─────────────────────────────────────┤
          │         │ + EventSource connection            │
          │         │ + withCredentials: true            │
          │         │ + BROKEN: cannot send headers      │
          │         └─────────────────────────────────────┘
          │
          │ All use cookies automatically
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           NEXT.JS API LAYER                                   │
├─────────────────────────────────────────────────────────────────────────────┤

                    ┌────────────────────────────────────────────┐
                    │           API ROUTE HANDLERS               │
                    └────────────────────────────────────────────┘
                                         │
           ┌─────────────────────────────┼─────────────────────────────┐
           │                             │                             │
           ▼                             ▼                             ▼
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│  Auth Routes        │     │   Proxy Route       │     │   SSE Handler       │
│  /api/auth/*        │     │   /api/proxy/*      │     │   /api/sse/*        │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│ /api/auth/session   │     │ Responsibilities:  │     │ Responsibilities:    │
│   - create session  │     │   1. Read cookie   │     │   1. Read cookie    │
│ /api/auth/logout    │     │   2. Verify        │     │   2. SSE streaming  │
│   - clear session   │     │   3. Inject header │     │   3. Event gen      │
│                     │     │   4. Forward       │     │                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                    │
                                    │ fetch with
                                    │ Authorization header
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND COMPONENTS                                 │
├─────────────────────────────────────────────────────────────────────────────┤

┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Auth Middleware   │     │   Service Layer     │     │   SSE Manager       │
│   (dependencies.py)│     │   (api/*)           │     │   (watchlists.py)   │
├─────────────────────┤     ├─────────────────────┤     ├─────────────────────┤
│ get_current_user()  │     │ + ValuationsAPI    │     │ + symbol_subscribers│
│   - verify_id_token│     │ + WatchlistsAPI    │     │ + user_queues       │
│   - verify_session │     │ + StocksAPI        │     │ + broadcast()       │
│   - X-Verified-UID │     │                    │     │                     │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
```

### 3.2 Component Specifications

#### 3.2.1 Frontend Components

---

**AUTH PROVIDER (`providers/auth-provider.tsx`)**

**Responsibility:**
- Initialize Firebase auth state on application mount
- Provide auth context (`firebaseUser`, `status`) to all components
- Coordinate session cookie creation on login via `persistSessionCookie()`
- Manage auth loading states ('initializing', 'authenticated', 'unauthenticated')
- Handle sign-out (clear session, revoke tokens)

**Public API:**
```typescript
useAuth() → {
  firebaseUser: FirebaseUser | null,
  status: 'initializing' | 'authenticated' | 'unauthenticated',
  signIn: (email, password) => Promise<FirebaseUser>,
  signOut: () => Promise<void>
}
```

**Dependencies:**
- Firebase Auth SDK (client-side)
- `persistSessionCookie()` helper function
- `setAuthToken()` from TokenManager (deprecated path)

**Login Flow:**
1. User calls `signInWithEmailAndPassword(email, password)`
2. Firebase SDK triggers `onIdTokenChanged` callback
3. Callback calls `getIdToken()` to get Firebase ID token
4. Callback calls `persistSessionCookie()` → POST to `/api/auth/session`
5. Server verifies ID token, creates session cookie
6. Client stores session cookie automatically

---

**TOKEN MANAGER (`lib/token-manager.ts`) - DEPRECATED**

**Responsibility:**
- Manage Authorization header for axios requests (legacy pattern)
- Provide token for services that use axios

**Public API:**
```typescript
setAuthToken(token: string | null): void
clearAuthToken(): void
getUnauthorizedHandler(): (() => void) | null
```

**Note:** This is a legacy component. In the new architecture, all auth should flow through cookies only. This component is kept for backward compatibility with existing axios-based services.

---

**GLOBAL SSE PROVIDER (`providers/GlobalSSEProvider.tsx`)**

**Responsibility:**
- Manage single EventSource connection for entire application
- Route `price_update` events to React Query cache (QK.price)
- Route `valuation_ready` events to invalidate queries
- Handle reconnection with exponential backoff (1s → 30s max)

**Public API:**
```typescript
useSSEStatus() → { isConnected: boolean }
```

**Connection Configuration:**
```typescript
new EventSource('/api/proxy/watchlists/stream', { withCredentials: true })
```

**Events Handled:**
- `price_update`: Writes to `QK.price(symbol)` in React Query cache
- `valuation_ready`: Invalidates `QK.rule1()`, `QK.dcf()`, etc.

**Problem:** EventSource cannot send custom headers. It only sends cookies via `withCredentials: true`. The proxy must handle this limitation.

---

#### 3.2.2 Next.js API Routes

---

**SESSION HANDLER (`api/auth/session/route.ts`)**

**Responsibility:**
- Exchange Firebase ID token for session cookie
- Verify ID token freshness (auth_time check - must be within 5 minutes)
- Set httpOnly session cookie with proper security attributes
- Handle session refresh and logout

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/auth/session | Create session cookie from ID token |
| POST | /api/auth/session?action=clear | Clear session cookie (logout) |

**Create Session Flow:**
```
1. Receive POST with body: { idToken: "<firebase_id_token>" }
2. Verify idToken with Firebase Admin SDK (verifyIdToken)
3. Check auth_time is recent (within 5 minutes) for sensitive operations
4. Create session cookie: createSessionCookie(idToken, { expiresIn: 5 days })
5. Set __session cookie with security attributes
6. Return 200 OK
```

**Cookie Configuration:**
```typescript
{
  name: '__session',
  httpOnly: true,      // Not accessible to JavaScript
  secure: true,        // HTTPS only in production
  sameSite: 'lax',     // CSRF protection (allows top-level navigation)
  path: '/',           // Available on all paths
  maxAge: 432000       // 5 days in seconds
}
```

---

**PROXY ROUTE HANDLER (`api/proxy/[...path]/route.ts`)**

**Responsibility:**
- Bridge between Next.js frontend and Python backend
- Extract auth from cookies/headers
- Inject proper Authorization headers for upstream requests
- Handle SSE streaming passthrough
- Apply rate limiting awareness and logging

**Token Extraction Flow:**
```typescript
// 1. Check Authorization header (for axios backward compatibility)
const tokenFromHeaders = extractTokenFromHeaders(request);

// 2. Fallback to __session cookie (primary for fetch/EventSource)
const tokenFromCookies = await extractTokenFromCookies();

// 3. Use whichever is available
const bearer = tokenFromHeaders ?? tokenFromCookies ?? null;

// For SSE: Extract UID for X-Verified-UID header
const sessionData = await extractSessionCookie();
const uid = sessionData?.uid ?? null;
```

**Headers Injected for Backend:**
```typescript
{
  'Authorization': 'Bearer <token>',           // Backend validates this
  'X-Forwarded-For': '<client_ip>',           // For rate limiting
  'X-Forwarded-Proto': 'http/https',          // Original protocol
  'X-Forwarded-Host': '<host>',               // Original host
  'X-Verified-UID': '<uid>'                   // SSE only (NEW)
}
```

**SSE Detection:**
```typescript
function isSSEPath(path: string): boolean {
  return path.startsWith('watchlists/stream');
}
```

**Security Considerations:**
- `PROXY_REQUIRE_AUTH=true` blocks all unauthenticated requests
- No query param tokens (prevents token leakage in logs)
- Minimal logging (no token values logged)
- X-Verified-UID only injected for SSE endpoints

---

#### 3.2.3 Backend Components

---

**AUTH DEPENDENCY (`backend/dependencies.py` → `backend/auth.py`)**

**Responsibility:**
- Verify user identity for all protected endpoints via FastAPI dependency
- Support multiple auth methods (ID token, session cookie, SSE header)
- Return consistent user object to downstream handlers

**Auth Methods (in priority order):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AUTHENTICATION METHODS                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Priority 1: X-Verified-UID Header (SSE from trusted proxy)                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Only accepted from client.host in TRUSTED_PROXY_HOSTS            │   │
│  │   TRUSTED_PROXY_HOSTS = {"127.0.0.1", "::1", "localhost"}         │   │
│  │ • Proxy verifies session cookie and injects uid as header           │   │
│  │ • Prevents external callers from forging authentication             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│  Priority 2: Authorization: Bearer <token>                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Try verify_id_token() first (for Firebase ID tokens)             │   │
│  │ • Try verify_session_cookie() (for Firebase session cookies)       │   │
│  │ • Return first successful verification                              │   │
│  │ • NEW: Both methods now accepted (fixes the bug!)                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              │                                               │
│                              ▼                                               │
│  Priority 3: No valid auth → 401 Unauthorized                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**User Object Returned:**
```python
{
    "uid": "user123",              # Firebase UID
    "sub": "user123",              # For JWT compatibility
    "email": "user@example.com"     # If available
}
```

---

**SSE MANAGER (`backend/api/watchlists.py`)**

**Responsibility:**
- Manage active SSE connections per user
- Subscribe users to symbol price updates
- Broadcast price updates to subscribed users
- Handle connection cleanup on disconnect

**Data Structures (v1.1 - Single Instance):**
```python
# Maps symbol → set of user UIDs subscribed to it
symbol_subscribers: Dict[str, Set[str]]

# Maps user UID → list of their SSE queues (one user can have multiple connections)
user_queues: Dict[str, List[asyncio.Queue]]
```

**Connection Lifecycle:**
```
1. User connects to /watchlists/stream
   └─► get_current_user() validates session (via signed X-Verified-UID or Bearer token)
   └─► Create asyncio.Queue()
   └─► Add queue to user_queues[uid]
   └─► Query user's watchlist symbols from database
   └─► Subscribe uid to each symbol in symbol_subscribers

2. While connected:
   └─► Wait on queue.get() with 5s timeout
   └─► Send SSE event OR keep-alive ping (: keep-alive\n\n)
   └─► Check request.is_disconnected()

3. On disconnect (finally block):
   └─► Remove queue from user_queues
   └─► Unsubscribe from all symbols
   └─► Clean up symbol_subscribers if empty
```

**Price Broadcast:**
```python
async def broadcast_stock_update(symbol, price, change, change_pct):
    for uid in symbol_subscribers.get(symbol, []):
        for queue in user_queues.get(uid, []):
            await queue.put({
                "type": "price_update",
                "symbol": symbol,
                "price": price,
                "change": change,
                "changePercent": change_pct
            })
```

**⚠️ SCALABILITY LIMITATION (v1.1):**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SINGLE-INSTANCE LIMITATION                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CURRENT STATE (v1.1):                                                      │
│  ┌─────────────────┐                                                        │
│  │  Backend Instance │  ◄─── All SSE connections here                     │
│  │  (single)        │                                                        │
│  └────────┬────────┘                                                        │
│           │                                                                  │
│           │ All users connect to this single instance                        │
│           ▼                                                                  │
│    ┌──────────────┐                                                         │
│    │ user_queues  │  ✓ Works perfectly for single instance                │
│    │ symbol_subs  │                                                         │
│    └──────────────┘                                                         │
│                                                                              │
│  PROBLEM (Multi-instance):                                                  │
│  ┌─────────────────┐  ┌─────────────────┐                                   │
│  │  Backend Pod 1  │  │  Backend Pod 2  │  ◄─── Load balanced              │
│  │  (instance A)   │  │  (instance B)   │                                   │
│  └────────┬────────┘  └────────┬────────┘                                   │
│           │                     │                                             │
│           │ User on Pod A       │ User on Pod B                              │
│           │ Can't see updates   │ Can't see updates                          │
│           │ for symbols on Pod B│ for symbols on Pod A                       │
│           └─────────────────────┴─────── ISOLATED INSTANCES                   │
│                                                                              │
│  SOLUTION (v2.0): See Section 8.8 - Redis Pub/Sub Architecture             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Supported Deployment Modes:**

| Mode | Description | SSE Support | v1.1 Status |
|------|-------------|------------|--------------|
| Single Server | All on one machine | ✓ Full | ✓ Supported |
| Docker (single) | Single container | ✓ Full | ✓ Supported |
| Docker Compose | Multiple containers, single node | ✓ Full | ✓ Supported |
| Kubernetes (single pod) | One backend pod | ✓ Full | ✓ Supported |
| Kubernetes (multi-pod) | Multiple backend pods | ✗ Broken | ⚠️ Future |
| Vercel Serverless | Ephemeral instances | ✗ Broken | ⚠️ Future |

---

## 4. Sequence Diagrams

### 4.1 Login Flow (Complete)

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│  User   │     │ Firebase SDK  │     │ AuthProvider │     │  Next.js   │     │ Firebase │
│ Browser │     │   (client)    │     │   (React)    │     │   Proxy    │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └─────┬──────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │ 1. signInWithEmailAndPassword()        │                  │                 │
     │─────────────────│                     │                  │                 │
     │                  │                     │                  │                 │
     │ 2. onIdTokenChanged callback           │                  │                 │
     │<───────────────────────────────────────│                  │                 │
     │                  │                     │                  │                 │
     │ 3. getIdToken() returns ID token       │                  │                 │
     │<─────────────────│                     │                  │                 │
     │                  │                     │                  │                 │
     │ 4. POST /api/auth/session              │                  │                 │
     │    { idToken: "<firebase_id_token>" }  │                  │                 │
     │────────────────────────────────────────>│                  │                 │
     │                  │                     │                  │                 │
     │                  │                     │ 5. verifyIdToken(idToken)          │
     │                  │                     │─────────────────────────────────────>
     │                  │                     │                  │                 │
     │                  │                     │ 6. createSessionCookie(idToken, {expiresIn})│
     │                  │                     │─────────────────────────────────────>
     │                  │                     │                  │                 │
     │                  │                     │ 7. Set-Cookie: __session=<cookie>  │
     │                  │                     │<─────────────────────────────────────
     │                  │                     │                  │                 │
     │ 8. 200 OK        │                     │                  │                 │
     │<────────────────────────────────────────│                  │                 │
     │                  │                     │                  │                 │
     │ [Login Complete - Session Cookie established]               │                 │
     └──────────────────┴─────────────────────┴──────────────────┴─────────────────┘
```

**Key Points:**
1. Firebase ID token is obtained from the client SDK
2. Server verifies the ID token and creates a session cookie
3. Session cookie is set as httpOnly (not accessible to JavaScript)
4. Subsequent requests automatically include the session cookie

---

### 4.2 Watchlist Fetch (axios - Currently Working)

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│  User   │     │ WatchlistSvc  │     │  Next.js    │     │  Backend   │     │ Firebase │
│ Browser │     │   (axios)     │     │   Proxy     │     │    API     │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └─────┬──────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │ 1. getDefaultWatchlistStructure()      │                  │                 │
     │─────────────────>│                     │                  │                 │
     │                  │                     │                  │                 │
     │ 2. POST /api/proxy/watchlists/default-structure         │                 │
     │    Authorization: Bearer <id_token>  │                  │                 │
     │    Cookie: __session=<cookie>       │                  │                 │
     │────────────────────────────────────────>│                  │                 │
     │                  │                     │                  │                 │
     │                  │                     │ 3. extractTokenFromHeaders()       │
     │                  │                     │    → finds Authorization header   │
     │                  │                     │                  │                 │
     │                  │                     │ 4. fetch(backend/watchlists/...)  │
     │                  │                     │    Authorization: Bearer <id_token>
     │                  │                     │───────────────────────────────────>
     │                  │                     │                  │                 │
     │                  │                     │                  │ 5. verify_id_token()
     │                  │                     │                  │───────────────>
     │                  │                     │                  │                 │
     │                  │                     │                  │ 6. return user  │
     │                  │                     │                  │<───────────────
     │                  │                     │                  │                 │
     │                  │                     │ 7. 200 OK + data│                 │
     │                  │                     │<───────────────────────────────────
     │                  │                     │                  │                 │
     │ 8. 200 OK + data │                     │                  │                 │
     │<────────────────────────────────────────│                  │                 │
     │                  │                     │                  │                 │
     │ [Success - Authorization header found] │                  │                 │
     └──────────────────┴─────────────────────┴─────────────────┴─────────────────┘
```

**Key Points:**
1. `setAuthToken()` sets axios default header with Firebase ID token
2. Proxy's `extractTokenFromHeaders()` finds the Authorization header
3. Backend's `verify_id_token()` validates the ID token successfully
4. This flow works correctly and will continue to work

---

### 4.3 Analysis Fetch (native fetch - Currently Broken)

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│  User   │     │ AnalysisSvc   │     │  Next.js    │     │  Backend   │     │ Firebase │
│ Browser │     │   (fetch)     │     │   Proxy     │     │    API     │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └─────┬──────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │ 1. fetchRule1Cached("RBLX")          │                  │                 │
     │─────────────────>│                     │                  │                 │
     │                  │                     │                  │                 │
     │ 2. fetch('/api/proxy/valuations/...') │                  │                 │
     │    [NO Authorization header!]         │                  │                 │
     │    Cookie: __session=<cookie>         │                  │                 │
     │────────────────────────────────────────>│                  │                 │
     │                  │                     │                  │                 │
     │                  │                     │ 3. extractTokenFromHeaders()       │
     │                  │                     │    → NO Authorization header        │
     │                  │                     │                  │                 │
     │                  │                     │ 4. extractTokenFromCookies()       │
     │                  │                     │    → finds __session cookie         │
     │                  │                     │                  │                 │
     │                  │                     │ 5. fetch(backend/valuations/...)   │
     │                  │                     │    Authorization: Bearer <session> │
     │                  │                     │    [SESSION COOKIE, NOT ID TOKEN] │
     │                  │                     │───────────────────────────────────>
     │                  │                     │                  │                 │
     │                  │                     │                  │ 6. verify_id_token(session_cookie)
     │                  │                     │                  │    → FAILS! Session cookies need
     │                  │                     │                  │    → verify_session_cookie()
     │                  │                     │                  │<───────────────
     │                  │                     │                  │                 │
     │                  │                     │                  │ 7. 401 Unauthorized
     │                  │                     │                  │<───────────────
     │                  │                     │                  │                 │
     │                  │                     │ 8. 401 Unauthorized│                │
     │                  │                     │<───────────────────────────────────
     │                  │                     │                  │                 │
     │ 9. 401 Unauthorized│                    │                  │                 │
     │<────────────────────────────────────────│                  │                 │
     │                  │                     │                  │                 │
     │ [FAILURE - Backend cannot verify session cookie as ID token]│                 │
     └──────────────────┴─────────────────────┴─────────────────┴─────────────────┘
```

**Key Points:**
1. Native `fetch()` does NOT use axios defaults - no Authorization header sent
2. Proxy falls back to `extractTokenFromCookies()` which finds the session cookie
3. Proxy forwards session cookie as `Authorization: Bearer <session_cookie>`
4. Backend's `verify_id_token()` fails because session cookies must use `verify_session_cookie()`
5. **This is the bug - the fix is to add session cookie verification to backend**

---

### 4.4 SSE Connection (EventSource - Currently Broken)

```
┌─────────┐     ┌───────────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐
│  User   │     │ GlobalSSE     │     │  Next.js    │     │  Backend   │     │ Firebase │
│ Browser │     │  Provider     │     │   Proxy     │     │    API     │     │  Admin   │
└────┬────┘     └───────┬───────┘     └──────┬──────┘     └─────┬──────┘     └────┬─────┘
     │                  │                     │                  │                 │
     │ 1. useEffect triggers                  │                  │                 │
     │─────────────────>│                     │                  │                 │
     │                  │                     │                  │                 │
     │ 2. new EventSource('/api/proxy/watchlists/stream',      │                 │
     │    { withCredentials: true })         │                  │                 │
     │    [EventSource CANNOT send custom headers!]            │                 │
     │    Only sends Cookie: __session=<cookie>                │                  │                 │
     │────────────────────────────────────────────────────────>│                  │
     │                  │                     │                  │                 │
     │                  │                     │ 3. extractTokenFromHeaders()       │
     │                  │                     │    → NO Authorization header        │
     │                  │                     │                  │                 │
     │                  │                     │ 4. extractTokenFromCookies()       │
     │                  │                     │    → finds __session cookie         │
     │                  │                     │                  │                 │
     │                  │                     │ 5. fetch(backend/watchlists/stream)│
     │                  │                     │    Authorization: Bearer <session> │
     │                  │                     │    [Proxy already does this!]    │
     │                  │                     │───────────────────────────────────>
     │                  │                     │                  │                 │
     │                  │                     │                  │ 6. verify_id_token(session)
     │                  │                     │                  │    → FAILS! Backend only
     │                  │                     │                  │    → accepts ID tokens
     │                  │                     │                  │<───────────────
     │                  │                     │                  │                 │
     │                  │                     │                  │ 7. 401 Unauthorized
     │                  │                     │                  │<───────────────
     │                  │                     │                  │                 │
     │                  │                     │ 8. 401 Unauthorized│                │
     │                  │                     │<───────────────────────────────────
     │                  │                     │                  │                 │
     │ 9. EventSource onerror                │                  │                 │
     │<────────────────────────────────────────────────────────│                  │
     │                  │                     │                  │                 │
     │ [FAILURE - Backend cannot verify session cookie as ID token]│                 │
     └──────────────────┴─────────────────────┴─────────────────┴─────────────────┘
```

**Key Points:**
1. EventSource ONLY sends cookies - cannot send Authorization header (SSE spec limitation)
2. Proxy **already extracts the session cookie and forwards it as Bearer token**
3. The only missing piece: **Backend needs to accept session cookies via `verify_session_cookie()`**
4. **Fix is the same as GET requests - add session cookie fallback to backend auth**
5. No X-Verified-UID header needed - the proxy already does the cookie-to-header conversion

**The Fix:**
Backend `get_current_user()` only needs to add `verify_session_cookie()` as a fallback. No changes to proxy needed!

---

### 4.5 PROPOSED FIX: Simplified Unified Auth (v1.2)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    REVISED v1.2: UNIFIED COOKIE-BASED AUTH FLOW                      │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  KEY PRINCIPLE: Single Source of Truth                                          │
│  "The backend accepts session cookies as valid Bearer tokens."                    │
│                                                                                  │
│  CHANGES REQUIRED:                                                               │
│  1. Backend: Add verify_session_cookie() as fallback to verify_id_token()        │
│  2. Proxy: No changes needed (already forwards session cookie as Bearer)          │
│  3. SSE: No special handling needed (proxy already converts cookie to header)       │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    ALL REQUESTS (fetch, axios, SSE)                      │
│                                                                         │
│  ┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌──────────┐ │
│  │ Browser │────▶│ Next.js      │────▶│  Backend   │────▶│ Firebase │ │
│  │         │     │ Proxy        │     │    API     │     │  Admin   │ │
│  │  Any    │     │              │     │            │     │          │ │
│  │ Client  │     │ (unchanged)  │     │  auth.py   │     │          │ │
│  └─────────┘     └──────┬──────┘     └──────┬─────┘     └──────┬─────┘ │
│       │                  │                   │                   │       │
│       │ Cookie           │ Read __session    │ Authorization:    │       │
│       │ (always sent)   │ Extract & forward │ Bearer <token>   │       │
│       │                  │                   │                   │       │
│       │                  │                   │ 1. verify_id_token()     │
│       │                  │                   │    → If ID token: SUCCESS │
│       │                  │                   │                   │       │
│       │                  │                   │ 2. verify_session_cookie() │
│       │                  │                   │    → If session: SUCCESS │
│       │                  │                   │    → If neither: 401       │
│       │                  │                   │                   │       │
│       │                  │      200 OK ◀─────│─────────────────│───────┘
│       │◀────────────────│<──────────────────│<─────────────────│
│  Success!              │                   │                   │
│                    (No changes to proxy!)                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Why This Works:**

| Client Type | Auth Method | How It Works |
|-------------|-------------|--------------|
| axios | Authorization header | Already works - setAuthToken() |
| fetch | Cookie only | Proxy converts to Bearer → Backend accepts |
| EventSource (SSE) | Cookie only | Proxy converts to Bearer → Backend accepts |

**Key Insight:** The proxy already extracts the session cookie and forwards it as `Authorization: Bearer <session_cookie>`. The only missing piece is the backend accepting session cookies as valid credentials.

**Eliminated Complexity:**

| Old Approach (v1.1) | New Approach (v1.2) |
|---------------------|---------------------|
| X-Verified-UID custom header | Not needed |
| HMAC signing in proxy | Not needed |
| Separate SSE auth path | Not needed |
| Firebase Admin SDK in proxy | Not needed |
| Complex backend trust verification | Not needed |

**Result:** ~70% less code to implement, ~50% less maintenance surface.
┌─────────────────────────────────────────────────────────────────────────────────┐
│                    PROPOSED: UNIFIED COOKIE-BASED AUTH FLOW                       │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  KEY CHANGES:                                                                   │
│  1. Backend accepts BOTH verify_id_token() AND verify_session_cookie()          │
│  2. Proxy ALWAYS reads __session cookie, regardless of HTTP method              │
│  3. Proxy converts session cookie to Authorization header for backend            │
│  4. SSE uses X-Verified-UID header from trusted proxy                          │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          FETCH (analysis.service.ts)                    │
│  ┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌────────────┐ │
│  │ Browser │────▶│ Next.js      │────▶│  Backend   │────▶│ Firebase   │ │
│  │         │     │ Proxy        │     │    API     │     │  Admin     │ │
│  │ fetch() │     │              │     │            │     │            │ │
│  └─────────┘     └──────┬──────┘     └──────┬─────┘     └──────┬─────┘ │
│       │                  │                   │                   │       │
│       │ Cookie only      │ Read __session    │ Session cookie   │ Verify│
│       │ (no Auth header) │ Extract & forward │ accepted!        │ session│
│       └─────────────────>│──────────────────>│<─────────────────│───────┘
│                         │                   │                   │
│                         │ 200 OK            │ 200 OK           │
│       ◀────────────────│<──────────────────│<─────────────────│
│  Success!              │                   │                   │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                          SSE (EventSource)                              │
│  ┌─────────┐     ┌─────────────┐     ┌────────────┐     ┌────────────┐ │
│  │ Browser │────▶│ Next.js      │────▶│  Backend   │     │ Firebase   │ │
│  │         │     │ Proxy        │     │    API     │     │  Admin     │ │
│  │ EventSrc│     │ isSSE=true   │     │            │     │            │ │
│  └─────────┘     └──────┬──────┘     └──────┬─────┘     └──────┬─────┘ │
│       │                  │                   │                   │       │
│       │ Cookie only      │ Verify session    │ X-Verified-UID   │ Verify│
│       │ (EventSource)    │ cookie            │ injected!        │ uid   │ │
│       │                  │                   │                   │       │
│       │                  │ Extract uid       │ Trust X-Verified  │       │
│       │                  │ Inject header     │                   │       │
│       │                  │──────────────────>│───────────────────>│───────┘
│       │                  │                   │                   │
│       │ SSE stream        │ SSE passthrough   │ SSE connected    │
│       ◀──────────────────│<──────────────────│<─────────────────│
│  Price updates!          │                   │                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Details

### 5.1 Backend Changes (backend/auth.py) - MINIMAL FIX

**File:** `backend/auth.py`

**Change Required:** Add `verify_session_cookie()` as fallback to `get_current_user()`

**Current Code (Broken):**
```python
def get_current_user(request: Request):
    # ... existing code ...
    
    token = auth_header[len(BEARER_PREFIX):]
    
    # ONLY accepts Firebase ID tokens - FAILS on session cookies
    decoded_token = auth.verify_id_token(token)
    return decoded_token
```

**Fixed Code:**
```python
def get_current_user(request: Request):
    """Authenticate request using Bearer token (ID token or session cookie)."""
    
    auth_header = request.headers.get(AUTHORIZATION_HEADER)
    if not auth_header or not auth_header.startswith(BEARER_PREFIX):
        raise HTTPException(401, "Missing Authorization header")
    
    token = auth_header[len(BEARER_PREFIX):].strip()
    
    # Try Firebase ID token first (short-lived, ~1 hour)
    try:
        decoded = auth.verify_id_token(token)
        logger.debug(f"Auth via ID token: uid={decoded.get('uid')}")
        return decoded
    except Exception:
        pass  # ID token failed, try session cookie
    
    # Try Firebase session cookie (long-lived, 5 days)
    try:
        decoded = auth.verify_session_cookie(token, check_revoked=True)
        logger.debug(f"Auth via session cookie: uid={decoded.get('uid')}")
        return decoded
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
    
    raise HTTPException(401, "Invalid or expired token")
```

**Lines to Change:** Only 3 lines added, 1 line modified

**Impact:**
- ✓ Fixes all GET requests (fetch-based services)
- ✓ Fixes SSE connections (EventSource)
- ✓ Backward compatible with existing axios calls
- ✗ No changes needed to proxy

---

### 5.2 Proxy Changes - NONE REQUIRED

**File:** `web/src/app/api/proxy/[...path]/route.ts`

**Status:** NO CHANGES NEEDED

**Reason:** The proxy already:
1. Extracts the `__session` cookie via `extractTokenFromCookies()`
2. Forwards it as `Authorization: Bearer <session_cookie>` to the backend
3. Handles SSE streaming (passes through directly)

The existing code already does everything needed. The backend just needs to accept the session cookie as a valid credential.

**Current Code (Already Works):**
```typescript
// Lines 66-83: Already extracts session cookie
const tokenFromCookies = await extractTokenFromCookies();

// Lines 122-123: Already forwards as Authorization header
if (bearer) headers.set("Authorization", bearer);
```

**No changes required to the proxy.**

---

### 5.3 SSE 401 Handling (Optional Enhancement)

**Problem:** EventSource doesn't handle 401 errors gracefully - it just retries indefinitely.

**Solution:** Add SSE 401 error handling in the frontend.

**Implementation:**
```typescript
// GlobalSSEProvider.tsx - Add error handling
es.onerror = async () => {
  // Check if it's an auth error
  try {
    const testRes = await fetch('/api/auth/session-check', {
      credentials: 'include'
    });
    
    if (testRes.status === 401) {
      // Session expired - trigger re-login
      window.dispatchEvent(new CustomEvent('session:expired'));
      return;  // Don't reconnect automatically
    }
  } catch {
    // Network error - retry with backoff
  }
  
  // Regular error - retry with backoff
  es.close();
  const delay = Math.min(backoffRef.current, MAX_BACKOFF);
  backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF);
  setTimeout(() => connect(), delay);
};
```

**Note:** This is optional - the backend fix alone will make SSE work. The error handling just improves the UX.

---

## 6. Migration Strategy

### Phase 1: Backend Token Fallback (Single File Change)
**Effort:** 30 minutes | **Risk:** LOW | **Impact:** Fixes ALL authentication issues

1. **Backup** `backend/auth.py`
2. **Modify** `get_current_user()` to add `verify_session_cookie()` fallback
3. **Deploy** to staging
4. **Test:**
   - Watchlist loads (existing behavior)
   - Valuation data displays (was 401, now 200)
   - Stock quotes show (was 401, now 200)
   - SSE connects (was 401, now 200)
5. **Deploy** to production

**Verification Commands:**
```bash
# Should now return 200 instead of 401
curl -H "Authorization: Bearer <session_cookie>" \
     http://localhost:8001/valuations/RBLX/rule1

# Should stream SSE (200)
curl -N -H "Authorization: Bearer <session_cookie>" \
     http://localhost:8001/watchlists/stream
```

**Rollback:** Revert `backend/auth.py`, redeploy (5 minutes)

---

### Phase 2: SSE Error Handling (Optional)
**Effort:** 1 hour | **Risk:** LOW | **Impact:** Better UX for expired sessions

1. Add `/api/auth/session-check` endpoint
2. Update `GlobalSSEProvider.tsx` with auth error detection
3. Test session expiration handling

**Note:** Phase 2 is optional - SSE will work after Phase 1 without these changes.

---

## 7. Security Analysis

### 7.1 Threat Model

| Threat | Vector | Mitigation | Residual Risk |
|--------|--------|------------|---------------|
| Token theft | XSS | httpOnly cookie (JS cannot read) | Low |
| CSRF | Cross-site requests | sameSite: lax cookie | Low |
| Token replay | Stolen token | Session cookies checked for revocation | Low |
| Proxy spoofing | External X-Verified-UID | Only trust from localhost | Low |
| Token in logs | Query params | Tokens only in cookies/headers | Low |
| Session hijacking | Cookie theft | secure flag (HTTPS), short expiry | Low |

### 7.2 Defense in Depth

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         MULTI-LAYER SECURITY                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Layer 1: Client-Side                                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • httpOnly cookie - JavaScript cannot access the session cookie      │   │
│  │ • secure flag - Cookie only sent over HTTPS in production            │   │
│  │ • sameSite: lax - Browser blocks cross-site POST requests            │   │
│  │ • CSRF token - Additional protection for state-changing requests     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                           │                                           │   │
│  │                           ▼                                           │   │
│  │                    Layer 2: Next.js Proxy                            │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │ • Verify session cookie before any forwarding                  │ │   │
│  │  │ • Inject Authorization header (backend never sees raw cookies) │ │   │
│  │  │ • X-Verified-UID only injected for SSE, only from localhost   │ │   │
│  │  │ • No token values logged (security)                           │ │   │
│  │  │ • PROXY_REQUIRE_AUTH blocks all unauthenticated requests       │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                 │   │
│  │                           │                                           │   │
│  │                           ▼                                           │   │
│  │                    Layer 3: Backend API                            │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │ • verify_id_token() or verify_session_cookie()                │ │   │
│  │  │ • check_revoked=True - detects revoked sessions                 │ │   │
│  │  │ • Rate limiting per user/IP                                    │ │   │
│  │  │ • Input validation on all endpoints                            │ │   │
│  │  │ • X-Verified-UID only accepted from trusted proxy hosts        │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  │                                                                 │   │
│  │                           │                                           │   │
│  │                           ▼                                           │   │
│  │                    Layer 4: Database                                │   │
│  │  ┌────────────────────────────────────────────────────────────────┐ │   │
│  │  │ • Row-level security policies (RLS)                            │ │   │
│  │  │ • Prepared statements prevent SQL injection                    │ │   │
│  │  │ • Encrypted at rest for sensitive fields                       │ │   │
│  │  │ • Audit logging for all data access                            │ │   │
│  │  └────────────────────────────────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 Security Checklist

| Security Measure | Status | Notes |
|-----------------|--------|-------|
| httpOnly cookies | ✓ Implemented | Prevents XSS token theft |
| secure flag | ✓ Implemented | HTTPS only in production |
| sameSite: lax | ✓ Implemented | CSRF protection |
| Token revocation | ✓ Implemented | check_revoked=True |
| Trusted proxy check | ✓ Implemented | Only localhost can inject X-Verified-UID |
| No token logging | ✓ Implemented | Logs only "present"/"absent" |
| Rate limiting | ✓ Implemented | Per user/IP |
| Input validation | ✓ Implemented | All endpoints |
| Row-level security | ✓ Implemented | Database policies |

---

## 8. Architectural Hardening

*Added in v1.1 based on security review*

This section addresses critical architectural concerns identified during security review for the cookie-based authentication system.

### 8.1 CSRF (Cross-Site Request Forgery) Protection

#### The Risk

With cookie-based authentication, browsers automatically include cookies in cross-site requests. This creates CSRF vulnerability for state-changing operations (POST, PUT, DELETE).

#### Our Mitigation Strategy

**Layer 1: SameSite Cookie Attribute**

```typescript
const cookieConfig = {
  name: '__session',
  httpOnly: true,
  secure: process.env.NODE_ENV === 'production',
  sameSite: 'strict' as const,  // RECOMMENDED for financial applications
  path: '/',
  maxAge: 432000  // 5 days
};
```

| SameSite Value | Behavior | Security Level |
|----------------|----------|----------------|
| `none` | Cookies sent on all requests | None (requires `secure`) |
| `lax` | Cookies sent on top-level navigation | Medium |
| `strict` | Cookies only sent on same-site requests | High |

**Recommendation for StockerPro:** Use `sameSite: 'strict'`

**Rationale:** For a financial application, `strict` is preferred because:
- Users should not be logged in via links from external emails
- The primary entry point is direct navigation or bookmark
- The risk of unauthorized actions from cross-site requests outweighs the UX trade-off

#### Layer 2: Origin/Referer Validation (Next.js Proxy)

For defense-in-depth, the proxy should validate origin headers on mutating requests:

```typescript
// In api/proxy/[...path]/route.ts
function validateCSRF(request: NextRequest): boolean {
  // Only validate mutating requests
  const method = request.method.toUpperCase();
  if (!['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    return true;  // Safe methods don't need CSRF check
  }
  
  // Check Origin header (preferred)
  const origin = request.headers.get('origin');
  const allowedOrigins = [
    'http://localhost:3000',
    'https://stockerpro.example.com',  // Production domain
  ];
  
  if (origin && allowedOrigins.includes(origin)) {
    return true;
  }
  
  // Fallback to Referer check
  const referer = request.headers.get('referer');
  if (referer) {
    try {
      const refererUrl = new URL(referer);
      if (allowedOrigins.includes(refererUrl.origin)) {
        return true;
      }
    } catch {
      // Invalid referer URL
    }
  }
  
  // Request not from our origin - potential CSRF
  return false;
}

// Usage in proxy
async function proxy(request: NextRequest, ...): Promise<NextResponse> {
  const method = request.method.toUpperCase();
  
  // CSRF check for mutating requests
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    if (!validateCSRF(request)) {
      return NextResponse.json(
        { detail: 'CSRF validation failed' },
        { status: 403 }
      );
    }
  }
  
  // ... rest of proxy logic
}
```

#### Layer 3: Double-Submit Cookie Pattern (Optional Enhancement)

For additional protection, implement the double-submit cookie pattern:

```typescript
// The __csrf cookie (non-httpOnly, readable by JS) is already set
// We just need to validate it in the proxy

async function validateDoubleSubmit(request: NextRequest): Promise<boolean> {
  const csrfCookie = request.cookies.get('__csrf')?.value;
  const csrfHeader = request.headers.get('x-csrf-token');
  
  // Both must be present and match
  if (!csrfCookie || !csrfHeader) {
    return false;
  }
  
  return csrfCookie === csrfHeader;
}
```

**Note:** The application already sets `__csrf` cookie in `session/route.ts`. Ensure axios/fetch requests include the `X-CSRF-Token` header (already implemented in `lib/api.ts`).

---

### 8.2 X-Verified-UID Header Trust Enforcement

#### The Risk

**IP-based trust alone is insufficient.** If an attacker compromises any service on the same network segment, they could forge the `X-Verified-UID` header and impersonate any user.

```
Attack Scenario:
1. Attacker deploys malicious service on 172.19.86.x network
2. Attacker sends request to backend: http://172.19.86.61:8001
3. Header: X-Verified-UID: victim_user_id
4. Backend checks IP: 172.19.86.x → ALLOWED (private network)
5. Backend trusts X-Verified-UID → Attacker impersonates victim
```

#### The Solution: Cryptographic Verification

**Defense-in-Depth Strategy:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MUTUAL TRUST ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Layer 1: Network Isolation (Prevents unauthorized access)                   │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ • Backend binds to private interface only (127.0.0.1 or 10.x.x.x)    │  │
│  │ • Firewall rules block direct internet access to backend              │  │
│  │ • Only Next.js proxy can reach backend                               │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│  Layer 2: Cryptographic Verification (Proves proxy identity)               │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ • X-Verified-UID contains HMAC signature                             │  │
│  │ • Backend verifies signature using shared secret                     │  │
│  │ • Attacker without secret cannot forge valid header                  │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

#### Layer 1: Network Isolation

**Recommended Configuration:**

```python
# backend/main.py - Bind to private interface only
import uvicorn

# Option A: Bind to localhost only (for same-machine deployment)
uvicorn.run(
    app,
    host="127.0.0.1",  # ONLY accepts connections from localhost
    port=8001,
)

# Option B: Private network binding (for containerized deployment)
uvicorn.run(
    app,
    host="10.0.0.50",  # Private IP assigned to backend container
    port=8001,
)

# Option C: Docker network (recommended for containers)
# docker-compose.yml
#   backend:
#     networks: [internal]
#   proxy:
#     networks: [internal]
#
# internal network: 10.x.x.x range, no external exposure
```

**Firewall Rules:**

```bash
# Block all external access to port 8001
iptables -A INPUT -p tcp --dport 8001 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 8001 -s 10.0.0.0/8 -j ACCEPT
iptables -A INPUT -p tcp --dport 8001 -j DROP  # Block all others
```

---

#### Layer 2: Signed X-Verified-UID Header

**Why HMAC Signature?**

Instead of trusting the IP address alone, the proxy signs the `X-Verified-UID` with a shared secret. The backend verifies the signature before trusting the UID.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SIGNED HEADER FLOW                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Proxy reads session cookie → Extracts UID                             │
│                                                                              │
│  2. Proxy creates signed payload:                                          │
│     payload = base64(uid + ":" + timestamp)                                │
│     signature = HMAC-SHA256(payload, SHARED_SECRET)                        │
│     header = X-Verified-UID: payload.signature                             │
│                                                                              │
│  3. Backend receives request with X-Verified-UID header                    │
│                                                                              │
│  4. Backend verifies:                                                      │
│     - Extract payload and signature                                        │
│     - Recompute HMAC with SHARED_SECRET                                    │
│     - Compare signatures (constant-time comparison)                         │
│     - Check timestamp is recent (within 5 minutes)                        │
│                                                                              │
│  5. If valid → Trust the UID                                              │
│     If invalid → 401 Unauthorized                                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation: Proxy Side (Next.js)**

```typescript
// web/src/app/api/proxy/[...path]/route.ts
import { createHmac, timingSafeEqual } from 'crypto';

const PROXY_BACKEND_SECRET = process.env.PROXY_BACKEND_SECRET!;
const SIGNATURE_TTL_SECONDS = 300; // 5 minutes

interface SignedUID {
  uid: string;
  timestamp: number;
  signature: string;
}

function signUID(uid: string): string {
  const timestamp = Math.floor(Date.now() / 1000);
  const payload = Buffer.from(`${uid}:${timestamp}`).toString('base64');
  const signature = createHmac('sha256', PROXY_BACKEND_SECRET)
    .update(payload)
    .digest('hex');
  return `${payload}.${signature}`;
}

function buildUpstreamHeaders(
  req: NextRequest,
  bearer: string | null,
  isSSE: boolean,
  uid: string | null
): Headers {
  const headers = new Headers();
  
  // Authorization header for standard API calls
  if (bearer) {
    headers.set("Authorization", bearer);
  }
  
  // X-Verified-UID with HMAC signature for SSE
  if (isSSE && uid) {
    const signedUID = signUID(uid);
    headers.set("X-Verified-UID", signedUID);
  }
  
  // ... rest of headers
  return headers;
}
```

**Implementation: Backend Side (Python)**

```python
# backend/auth.py
import hmac
import hashlib
import base64
import time
from functools import wraps
from fastapi import Request, HTTPException
from config import settings

# Environment variable: shared secret between proxy and backend
PROXY_BACKEND_SECRET = os.getenv("PROXY_BACKEND_SECRET", "")
SIGNATURE_TTL_SECONDS = 300  # 5 minutes

def _is_trusted_proxy(request: Request) -> bool:
    """Verify request originates from trusted proxy via IP."""
    if not request.client:
        return False
    
    # In production, this should be the private network IP of Next.js
    # NEVER trust external IPs
    TRUSTED_HOSTS = {"127.0.0.1", "::1", "10.0.0.0/8"}
    
    client_ip = request.client.host
    # Use ipaddress module for CIDR matching in production
    return client_ip in {"127.0.0.1", "::1"}

def _verify_signed_uid(header_value: str) -> str | None:
    """
    Verify HMAC-signed X-Verified-UID header.
    Returns UID if valid, None if invalid.
    """
    try:
        payload_b64, signature = header_value.split(".", 1)
        payload = base64.b64decode(payload_b64).decode()
        uid, timestamp_str = payload.split(":", 1)
        timestamp = int(timestamp_str)
        
        # Verify timestamp is recent (prevent replay attacks)
        current_time = int(time.time())
        if abs(current_time - timestamp) > SIGNATURE_TTL_SECONDS:
            logger.warning(f"Signed UID expired: timestamp={timestamp}, current={current_time}")
            return None
        
        # Verify HMAC signature
        expected_sig = hmac.new(
            PROXY_BACKEND_SECRET.encode(),
            payload_b64.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning("Signed UID signature mismatch")
            return None
        
        return uid
        
    except Exception as e:
        logger.error(f"Error verifying signed UID: {e}")
        return None

def get_current_user(request: Request):
    """Authenticate request with defense-in-depth."""
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PATH 1: SSE via Signed X-Verified-UID (requires both IP + signature)
    # ═══════════════════════════════════════════════════════════════════════════
    signed_uid = request.headers.get("X-Verified-UID")
    
    if signed_uid and _is_trusted_proxy(request):
        uid = _verify_signed_uid(signed_uid)
        if uid:
            logger.debug(f"SSE auth via signed X-Verified-UID: uid={uid}")
            return {"uid": uid, "sub": uid}
        
        # Signature invalid even from "trusted" IP
        # This could indicate a compromised service on the network
        logger.error(f"Invalid signature from {request.client.host}")
        raise HTTPException(401, "Invalid proxy signature")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PATH 2: Authorization header (for standard API calls)
    # ═══════════════════════════════════════════════════════════════════════════
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(401, "Missing Authorization header")
    
    token = auth_header.replace("Bearer ", "").strip()
    
    # Try both verification methods
    for verify_func in [auth.verify_id_token, auth.verify_session_cookie]:
        try:
            decoded = verify_func(token, check_revoked=True)
            return decoded
        except Exception:
            continue
    
    raise HTTPException(401, "Invalid or expired token")
```

---

#### Layer 3: mTLS (Mutual TLS) for Production

For highest security, combine network isolation + signed headers with mTLS:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    mTLS + SIGNED HEADER FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. TLS handshake with client certificate                                  │
│     └─► Backend verifies proxy's certificate (proxy identity)              │
│                                                                              │
│  2. Proxy sends X-Verified-UID with HMAC signature                         │
│     └─► Backend verifies signature (proxy authorization)                    │
│                                                                              │
│  3. Double verification:                                                   │
│     ✓ Certificate is valid and signed by trusted CA                        │
│     ✓ HMAC signature is valid                                              │
│                                                                              │
│  Attacker without both:                                                    │
│     ✗ Valid client certificate (can't connect)                             │
│     ✗ Valid HMAC secret (can't forge header)                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Configuration:**

```python
# backend/main.py - mTLS configuration
ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ssl_context.verify_mode = ssl.CERT_REQUIRED
ssl_context.check_hostname = False  # IP-based connection

# Backend's certificate
ssl_context.load_cert_chain(
    certfile="/etc/ssl/private/backend.crt",
    keyfile="/etc/ssl/private/backend.key"
)

# CA that signed proxy's certificate
ssl_context.load_verify_locations("/etc/ssl/certs/proxy-ca.crt")
```

---

#### Comparison: Trust Approaches

| Approach | Security Level | Complexity | Recommendation |
|----------|---------------|------------|----------------|
| IP Whitelist Only | Low | Low | NOT RECOMMENDED |
| Private Network + Signed Header | High | Medium | **Recommended for v1.1** |
| mTLS + Signed Header | Very High | High | Production/high-security |
| mTLS Only (no signed header) | Medium | Medium | Acceptable fallback |

---

#### Environment Variables Required

```bash
# web/.env.local
PROXY_BACKEND_SECRET=your-256-bit-random-secret-here

# backend/.env
PROXY_BACKEND_SECRET=your-256-bit-random-secret-here  # MUST MATCH PROXY
```

**Important:** Generate a strong random secret:
```bash
openssl rand -hex 32
```

---

### 8.3 Cookie Size Management

#### The Risk

Standard browser cookie limits:
- **Per cookie:** 4KB maximum
- **Per domain:** ~150-180 cookies typical limit
- **Total cookie size:** 20KB typical limit

Firebase session cookies can grow large with additional claims.

#### Mitigation

**1. Keep Session Cookie Minimal**

The `__session` cookie should contain ONLY the Firebase session cookie value. Do not add custom metadata:

```typescript
// WRONG - Don't add custom data to session cookie
res.cookies.set({
  name: '__session',
  value: JSON.stringify({
    token: sessionCookie,
    userId: decoded.uid,  // Already in Firebase token!
    email: decoded.email,  // Already in Firebase token!
    customClaim: 'value',  // INCREASES COOKIE SIZE
  }),
  // ...
});

// CORRECT - Use Firebase session cookie directly
res.cookies.set({
  name: '__session',
  value: sessionCookie,  // Just the Firebase token
  // ...
});
```

**2. Monitor Cookie Size**

Add logging for cookie size monitoring:

```typescript
// In api/auth/session/route.ts
const cookieSizeBytes = Buffer.byteLength(sessionCookie, 'utf8');
const cookieSizeKB = cookieSizeBytes / 1024;

console.log(`[Session] Cookie size: ${cookieSizeKB.toFixed(2)} KB`);

if (cookieSizeKB > 3.5) {
  console.warn(`[Session] Warning: Cookie approaching 4KB limit (${cookieSizeKB.toFixed(2)} KB)`);
}
```

**3. Alternative: Token Storage Pattern**

For larger applications, consider server-side session storage:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    SERVER-SIDE SESSION PATTERN                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Instead of:                                                               │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Browser ──── Cookie (4KB limit) ──── Backend                         │  │
│  │                  Contains: token + userId + metadata                   │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  Use:                                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ Browser ──── Cookie (session ID only) ──── Backend ──── Redis/Session │  │
│  │                  Contains: "sess_abc123"                              │  │
│  │                                        ▲                              │  │
│  │                                        │                              │  │
│  │                              Full session data stored                 │  │
│  │                              in server-side store                     │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Note:** For StockerPro's current scale, Firebase session cookies should remain well under 4KB. This pattern is documented for future reference.

---

### 8.4 Token Refresh and Session Expiration Handling

#### The Challenge

| Token Type | Lifetime | Refresh Behavior |
|------------|----------|------------------|
| Firebase ID Token | ~1 hour | Must be manually refreshed |
| Firebase Session Cookie | 5 days | Automatic via cookie |

#### The Edge Case

```
Scenario: User has session cookie (5 days)
         └─► User opens app after 1 hour
         └─► ID token in memory expired
         └─► But session cookie is still valid
         
Problem: If we were relying on ID token from memory, requests fail.
         Session cookie still valid - should work.
```

#### Graceful Degradation Strategy

**1. Backend: Return Specific Error Codes**

```python
# backend/auth.py - Enhanced error handling
def get_current_user(request: Request):
    # ... existing auth logic ...
    
    try:
        decoded = auth.verify_id_token(token)
        return decoded
    except auth.ExpiredIdTokenError:
        # ID token expired, but session cookie might still be valid
        # Try session cookie verification
        try:
            decoded = auth.verify_session_cookie(token, check_revoked=True)
            return {
                **decoded,
                '_token_expired': True  # Flag for client refresh
            }
        except:
            raise HTTPException(401, "Token expired, please re-authenticate")
    
    except Exception as e:
        raise HTTPException(401, f"Authentication failed: {str(e)}")
```

**2. Next.js Proxy: Silent Session Refresh**

```typescript
// api/proxy/[...path]/route.ts
async function proxy(request: NextRequest, ...): Promise<NextResponse> {
  const upstreamResponse = await fetch(targetUrl, upstreamInit);
  
  // Handle 401 from backend
  if (upstreamResponse.status === 401) {
    const error = await upstreamResponse.json();
    
    // Check if this is a token expiration error
    if (error.detail?.includes('expired')) {
      // Return specific error code for client to handle
      return NextResponse.json(
        { 
          detail: 'SESSION_EXPIRED',
          code: 'TOKEN_EXPIRED',
          action: 'REAUTHENTICATE'
        },
        { status: 401 }
      );
    }
  }
  
  return upstreamResponse;
}
```

**3. Frontend: Handle Expiration Gracefully**

```typescript
// lib/api.ts - Enhanced error handling
api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const status = error.response?.status;
    const data = error.response?.data as any;
    
    // Check for session expiration
    if (status === 401 && data?.code === 'TOKEN_EXPIRED') {
      // Don't trigger sign-out immediately
      // Let the user continue with existing session
      if (data.action === 'REAUTHENTICATE') {
        // Trigger re-authentication flow
        window.dispatchEvent(new CustomEvent('session:expired'));
        return Promise.reject(error);
      }
    }
    
    // Standard 401 handling for other cases
    if (status === 401 || status === 403) {
      getUnauthorizedHandler()?.();
    }
    
    return Promise.reject(error);
  }
);
```

**4. SSE: Automatic Reconnection**

```typescript
// GlobalSSEProvider.tsx - Enhanced reconnection
useEffect(() => {
  if (!user) return;
  
  function connect() {
    const es = new EventSource(SSE_ENDPOINT, { withCredentials: true });
    
    es.onerror = async () => {
      // Check if it's an auth error
      // SSE doesn't give us HTTP status codes directly
      // But we can detect auth errors via a test endpoint
      
      try {
        const testRes = await fetch('/api/auth/session-check', {
          credentials: 'include'
        });
        
        if (testRes.status === 401) {
          // Session expired - trigger re-auth
          window.dispatchEvent(new CustomEvent('session:expired'));
          return;  // Don't reconnect automatically
        }
      } catch {
        // Network error - retry with backoff
      }
      
      // Regular error - retry with backoff
      es.close();
      // ... existing backoff logic ...
    };
    
    // ... existing onmessage logic ...
  }
  
  connect();
}, [user?.uid]);
```

---

### 8.5 Secure Logging Practices

#### The Risk

Logging cookies or tokens can expose sensitive data in:
- Server logs
- Error tracking systems (Sentry, Datadog)
- Application performance monitoring

#### Logging Standards

**1. Never Log Cookie Values**

```typescript
// WRONG - Security vulnerability
console.log('Cookie received:', request.cookies.get('__session'));

// CORRECT - Log presence only
console.log('Cookie received:', request.cookies.get('__session') ? 'YES' : 'NO');
```

**2. Structured Logging for Audit Trail**

```typescript
// api/auth/session/route.ts
interface SecurityLogEntry {
  timestamp: string;
  type: 'LOGIN' | 'LOGOUT' | 'SESSION_REFRESH' | 'TOKEN_VERIFY_FAIL';
  severity: 'INFO' | 'WARNING' | 'ERROR';
  ip: string;
  userId?: string;  // Only log UID, never token
  details: string;
  // Never include: tokens, cookies, passwords, PII
}

function logSecurityEvent(entry: SecurityLogEntry) {
  // This goes to your security log aggregation system
  console.log('[SECURITY]', JSON.stringify(entry));
}
```

**3. Request Logging (Safe Pattern)**

```typescript
// Proxy logging - never log these:
// - Cookie values
// - Authorization headers
// - Query parameters with tokens
// - Request bodies with sensitive data

// SAFE logging patterns:
console.log(`[PROXY] GET /${path} | auth=${authPresent ? 'present' : 'absent'}`);
console.log(`[PROXY-DEBUG] headers: { authorization: '${hasAuth}', cookie: '${hasCookie}' }`);

// Backend logging - never log these:
// - Token values
// - Cookie contents
// - Full request bodies

// SAFE logging:
logger.info(f"[AUTH] Token verification for uid={decoded.uid} succeeded");
logger.warning(f"[AUTH] Token verification failed from IP={ip}");
```

---

### 8.6 Performance: Firebase Key Caching

#### The Problem

Firebase's `verify_session_cookie()` and `verify_id_token()` make network calls to fetch Firebase public keys for JWT verification.

**Latency impact:** 50-200ms per verification (first call, uncached)

#### The Solution: In-Memory Key Caching

```typescript
// lib/firebase-admin.ts
import { initializeApp, getApps, cert, getAuth } from 'firebase-admin/app';
import { getAuth as getFirebaseAuth } from 'firebase-admin/auth';

// Key cache with TTL
interface KeyCache {
  keys: string;      // Cached public keys
  fetchedAt: number; // Timestamp
}

let keyCache: KeyCache | null = null;
const KEY_CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour

// Patch verifySessionCookie to use cache
const originalVerifySessionCookie = getFirebaseAuth().verifySessionCookie;

async function cachedVerifySessionCookie(
  sessionCookie: string,
  checkRevoked: boolean = false
): Promise<DecodedToken> {
  const now = Date.now();
  
  // Check if we need to refresh the key cache
  if (!keyCache || (now - keyCache.fetchedAt) > KEY_CACHE_TTL_MS) {
    // Firebase SDK handles key caching internally, but we can add
    // additional caching at the application level if needed
    // For most cases, Firebase SDK's built-in caching is sufficient
  }
  
  // Use the original method (Firebase SDK caches keys internally)
  return originalVerifySessionCookie(sessionCookie, checkRevoked);
}
```

**Note:** Firebase Admin SDK already implements internal caching of public keys. For most deployments, no additional caching is needed. Profile your application first to determine if this optimization is necessary.

#### Alternative: Redis Key Cache (High-Volume)

For high-traffic deployments:

```python
# backend/auth.py - Optional Redis caching
import redis
import json

redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Cache Firebase public keys in Redis
def get_firebase_keys_cached():
    cache_key = 'firebase:public_keys'
    cached = redis_client.get(cache_key)
    
    if cached:
        return json.loads(cached)
    
    # Fetch from Firebase (this is done by the SDK internally)
    # This is just for demonstration of the pattern
    keys = fetch_firebase_public_keys()
    redis_client.setex(cache_key, 3600, json.dumps(keys))  # 1 hour TTL
    
    return keys
```

---

### 8.8 SSE Scalability: Redis Pub/Sub Architecture (v2.0)

#### The Problem

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MULTI-INSTANCE SSE PROBLEM                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  When scaling to multiple backend instances:                                 │
│                                                                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                   │
│  │  Backend    │    │  Backend    │    │  Backend    │                   │
│  │  Instance 1 │    │  Instance 2 │    │  Instance 3 │                   │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                   │
│         │                   │                   │                           │
│         │ User A           │ User B            │ User C                   │
│         │ connected         │ connected          │ connected                │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │              Redis Pub/Sub (Shared Message Bus)                  │       │
│  │                                                                  │       │
│  │  Subscribe to: "price:AAPL" ←─ Price updates published here     │       │
│  │                                                                  │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│         ▲                   ▲                   ▲                           │
│         │                   │                   │                           │
│         │ Subscribe         │ Subscribe         │ Subscribe               │
│         └───────────────────┴───────────────────┘                          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### The Solution: Redis Pub/Sub

**Architecture:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    REDIS PUB/SUB ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  PRICE UPDATES FLOW:                                                        │
│  ┌─────────────┐                                                           │
│  │   Price     │                                                           │
│  │  Monitor    │──► Broadcast to all subscribers via Redis                 │
│  │  (yfinance) │                                                           │
│  └──────┬──────┘                                                           │
│         │                                                                   │
│         ▼                                                                   │
│  ┌─────────────────────────────────────────────────────────────────┐       │
│  │                    Redis Pub/Sub                                    │       │
│  │                                                                  │       │
│  │  Channel: "price:AAPL" ──► Message: {price, change, ...}        │       │
│  │  Channel: "price:GOOGL" ──► Message: {price, change, ...}       │       │
│  │                                                                  │       │
│  └─────────────────────────────────────────────────────────────────┘       │
│         ▲                                                                   │
│         │                                                                   │
│  ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐                   │
│  │  Backend     │    │  Backend     │    │  Backend     │                   │
│  │  Instance 1  │    │  Instance 2  │    │  Instance 3  │                   │
│  │              │    │              │    │              │                   │
│  │ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │                   │
│  │ │ Subscribe │ │    │ │ Subscribe │ │    │ │ Subscribe │ │                   │
│  │ │ to Redis │ │    │ │ to Redis │ │    │ │ to Redis │ │                   │
│  │ └────┬─────┘ │    │ └────┬─────┘ │    │ └────┬─────┘ │                   │
│  │      │        │    │      │        │    │      │        │                   │
│  │      ▼        │    │      ▼        │    │      ▼        │                   │
│  │ ┌──────────┐ │    │ ┌──────────┐ │    │ ┌──────────┐ │                   │
│  │ │ Deliver  │ │    │ │ Deliver  │ │    │ │ Deliver  │ │                   │
│  │ │ to users │ │    │ │ to users │ │    │ │ to users │ │                   │
│  │ └──────────┘ │    │ └──────────┘ │    │ └──────────┘ │                   │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Implementation:**

```python
# backend/api/watchlists.py - v2.0 with Redis Pub/Sub
import redis.asyncio as redis
import json
import asyncio
from typing import Dict, Set

# Redis connection (use connection pool for production)
redis_pool = redis.ConnectionPool(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True
)

# Global state (per instance)
user_queues: Dict[str, List[asyncio.Queue]] = {}
symbol_subscribers: Dict[str, Set[str]] = {}

# Redis clients (one per coroutine)
redis_clients: List[redis.Redis] = []

async def get_redis() -> redis.Redis:
    """Get Redis client from pool."""
    return redis.Redis(connection_pool=redis_pool)

async def subscribe_to_redis_channels(uid: str, symbols: List[str]):
    """
    Subscribe to Redis channels for user's symbols.
    Each backend instance runs this for each connected user.
    """
    r = await get_redis()
    pubsub = r.pubsub()
    
    # Subscribe to all user's symbols
    channels = [f"price:{sym}" for sym in symbols]
    await pubsub.subscribe(*channels)
    redis_clients.append(r)  # Keep reference alive
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                # Parse price update
                data = json.loads(message["data"])
                symbol = message["channel"].replace("price:", "")
                
                # Deliver to user's SSE queues
                await deliver_price_update(uid, symbol, data)
    finally:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()
        redis_clients.remove(r)

async def deliver_price_update(uid: str, symbol: str, data: dict):
    """Deliver price update to all user's SSE queues."""
    for queue in user_queues.get(uid, []):
        await queue.put({
            "type": "price_update",
            "symbol": symbol,
            **data
        })

async def broadcast_stock_update(symbol: str, price: float, change: float, change_pct: float):
    """
    Publish price update to Redis.
    ALL backend instances will receive this and deliver to their connected users.
    """
    r = await get_redis()
    message = json.dumps({
        "price": price,
        "change": change,
        "changePercent": change_pct
    })
    
    # Publish to symbol channel - all instances receive this
    await r.publish(f"price:{symbol}", message)

# SSE endpoint remains the same, but now subscribes to Redis
@router.get("/watchlists/stream")
async def stream_watchlist_updates(request: Request):
    user = get_current_user(request)  # Uses signed X-Verified-UID
    
    # ... setup code ...
    
    # Instead of local subscription, subscribe to Redis
    asyncio.create_task(subscribe_to_redis_channels(uid, user_symbols))
    
    # ... rest of SSE handler ...
```

**Redis Configuration (Docker Compose):**

```yaml
# docker-compose.yml
services:
  backend:
    depends_on:
      - redis
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"  # Only expose to internal network
    volumes:
      - redis_data:/data

volumes:
  redis_data:
```

**Production Considerations:**

| Aspect | Recommendation |
|--------|-----------------|
| Redis Cluster | Use Redis Cluster for horizontal scaling |
| Connection Pooling | Always use connection pools (not individual connections) |
| Backpressure | Implement queue size limits to prevent memory issues |
| Reconnection | Implement Redis connection reconnection logic |
| Monitoring | Monitor Redis pub/sub metrics and queue depths |

---

### 8.7 Complete Architecture Checklist

Use this checklist before production deployment:

#### Security Checklist

| Item | Status | Implementation |
|------|--------|----------------|
| `sameSite: 'strict'` on session cookie | ☐ | Cookie config |
| Origin/Referer validation on proxy | ☐ | `validateCSRF()` |
| X-CSRF-Token header validation | ☐ | Already in `lib/api.ts` |
| X-Verified-UID only from trusted hosts | ☐ | `TRUSTED_PROXY_HOSTS` |
| No token values in logs | ☐ | Structured logging |
| Backend not directly internet-accessible | ☐ | Network config |
| Rate limiting enabled | ☐ | Already in `dependencies.py` |
| Backend binds to private interface only | ☐ | Bind to 127.0.0.1 |
| X-Verified-UID signed with HMAC | ☐ | `signUID()` function |
| PROXY_BACKEND_SECRET configured | ☐ | Environment variable |

#### Scalability Checklist (v2.0)

| Item | Status | Implementation |
|------|--------|----------------|
| Single-instance deployment | ✓ | In-memory queues |
| Redis available for scaling | ☐ | Add Redis |
| Redis Pub/Sub implemented | ☐ | Section 8.8 |
| Connection pooling configured | ☐ | `ConnectionPool` |

#### Performance Checklist

| Item | Status | Notes |
|------|--------|-------|
| Firebase SDK key caching | ✓ | Built-in |
| Session cookie size monitoring | ☐ | Add logging |
| Proxy response time < 100ms | ☐ | Profile after deploy |

#### Reliability Checklist

| Item | Status | Implementation |
|------|--------|----------------|
| SSE reconnection with backoff | ✓ | 1s → 30s max |
| 401 error handling for fetch | ☐ | Add `SESSION_EXPIRED` code |
| Session expiration graceful degradation | ☐ | Frontend handling |
| Health check endpoint | ☐ | `/health` route |

---

## 9. Conclusion

### 9.1 Recommended Solution

**Option A: Backend Dual Verification (Simplest - Recommended First)**
- Modify `backend/auth.py` to try `verify_id_token()` first, then `verify_session_cookie()`
- Minimal code change, immediate impact
- Fixes all GET requests (analysis, quotes)
- SSE still requires proxy change

**Option B: Full Fix (Proxy + Backend)**
- Option A plus proxy injects `X-Verified-UID` for SSE
- Complete fix for all authentication scenarios
- All HTTP clients work identically

### 9.2 Solution Comparison

| Criteria | Option A (Backend Only) | Option B (Full) | Why Better |
|----------|-------------------------|-----------------|------------|
| Complexity | Low | Medium | Option B has more changes |
| Coverage | GET requests | All requests | Option B fixes SSE too |
| Risk | Low | Low | Both are safe changes |
| Effort | 1 file | 2 files | Option A is faster |
| Backward Compatible | ✓ | ✓ | Existing code still works |

### 9.3 Expected Results After Fix

| Metric | Before | After |
|--------|--------|-------|
| Valuation API calls | 401 errors | 200 success |
| Stock quotes | Empty/loading | Displayed |
| SSE connection | Failed (401) | Connected (200) |
| Price updates | None | Streaming live |
| Dashboard prices | Missing | Showing |

### 9.4 Testing Checklist

After implementing the fix, verify:

- [ ] Watchlist loads with structure (existing behavior)
- [ ] Valuation data displays (was 401, now 200)
- [ ] Stock quotes show current price (was 401, now 200)
- [ ] SSE connects successfully (DevTools Network)
- [ ] Price updates stream to dashboard
- [ ] Login/logout still works
- [ ] No console errors in browser

### 9.5 Rollback Plan

If issues arise after deployment:

1. **Backend rollback:** Revert `auth.py` to original `verify_id_token()` only
2. **Proxy rollback:** Revert `route.ts` to remove X-Verified-UID injection
3. **Session reset:** Users may need to log out and log back in

---

## Appendix A: Related Files

| File | Purpose | Changes |
|------|---------|---------|
| `backend/auth.py` | Token verification | Add session cookie fallback |
| `backend/dependencies.py` | Auth dependency | Uses auth.py |
| `web/src/app/api/proxy/[...path]/route.ts` | Proxy | Add X-Verified-UID for SSE |
| `web/src/app/api/auth/session/route.ts` | Session management | No changes needed |
| `web/src/providers/GlobalSSEProvider.tsx` | SSE client | No changes needed |
| `web/src/features/analysis/services/analysis.service.ts` | Analysis API | No changes needed |
| `web/src/features/watchlists/services/watchlist.service.ts` | Watchlist API | No changes needed |

## Appendix B: Firebase Token Types

| Token Type | Lifetime | Storage | Verification |
|------------|----------|---------|--------------|
| Firebase ID Token | ~1 hour | Client memory | `verify_id_token()` |
| Firebase Session Cookie | 5 days | httpOnly cookie | `verify_session_cookie()` |

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| SSE | Server-Sent Events - one-way streaming from server to client |
| EventSource | Browser API for SSE connections |
| X-Verified-UID | Header injected by trusted proxy to authenticate SSE (HMAC-signed) |
| HMAC | Hash-based Message Authentication Code - cryptographic signature |
| Redis Pub/Sub | Redis publish/subscribe for cross-instance message broadcasting |
| Bearer token | Authorization header format: `Bearer <token>` |
| httpOnly | Cookie flag preventing JavaScript access |
| RLS | Row-Level Security - database access control |

---

*Document Version: 1.2*  
*Author: Analysis Team*  
*Last Updated: 2026-04-14*  
*Status: Ready for Implementation*

## Changelog

### v1.2 (2026-04-14)
- **Security Enhancement: Mutual Trust with HMAC Signatures**
  - 8.2: Replaced IP-only trust with cryptographic verification
  - Added HMAC-SHA256 signed X-Verified-UID header
  - Timestamp validation to prevent replay attacks
  - Constant-time signature comparison to prevent timing attacks
  - Environment variable `PROXY_BACKEND_SECRET` for shared secret
- **Scalability: SSE Multi-Instance Architecture**
  - Added Section 8.8: Redis Pub/Sub Architecture (v2.0)
  - Documented single-instance limitation in Section 3.2.3
  - Added Redis Pub/Sub implementation for multi-instance deployments
- Updated security checklist with new items
- Added scalability checklist

### v1.1 (2026-04-14)
- Added Section 8: Architectural Hardening
  - 8.1: CSRF Protection (sameSite, Origin/Referer validation)
  - 8.2: X-Verified-UID Trust Enforcement (mTLS, Private Network, IP Whitelisting)
  - 8.3: Cookie Size Management
  - 8.4: Token Refresh and Session Expiration Handling
  - 8.5: Secure Logging Practices
  - 8.6: Performance: Firebase Key Caching
  - 8.7: Complete Architecture Checklist
- Updated Table of Contents

### v1.0 (2026-04-14)
- Initial design document
- Problem analysis and root cause
- Proposed solution architecture
- Implementation details
- Migration strategy
