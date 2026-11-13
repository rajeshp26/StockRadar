# Authentication Migration: Firebase → Supabase Auth

**Date:** 2026-06-01  
**Status:** Design Phase  
**Version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Why Migrate](#2-why-migrate)
3. [Current Architecture (Firebase)](#3-current-architecture-firebase)
4. [Proposed Architecture (Supabase)](#4-proposed-architecture-supabase)
5. [Architecture Comparison](#5-architecture-comparison)
6. [Local JWT Verification: The Key Security Improvement](#6-local-jwt-verification-the-key-security-improvement)
7. [Detailed Component Changes](#7-detailed-component-changes)
8. [Environment Variables](#8-environment-variables)
9. [Data Model Changes](#9-data-model-changes)
10. [Migration Path](#10-migration-path)
11. [Rollback Plan](#11-rollback-plan)

---

## 1. Executive Summary

StockerPro currently depends on **two authentication providers**: Firebase (identity) and Supabase (database). Firebase handles sign-up, sign-in, token lifecycle, and session verification — but it also requires the Firebase Admin SDK to make HTTPS calls to Google's servers on **every single API request** (200-600ms added latency). This dual-provider setup has caused an SSL certificate issue in development, adds external dependency risk in production, and introduces unnecessary complexity.

The migration replaces Firebase Auth entirely with **Supabase Auth**, consolidating to a single provider. The critical architectural improvement is shifting from **network-bound token verification** (Firebase Admin SDK HTTPS calls) to **local JWT signature verification** (cached JWKS public keys), eliminating per-request network latency and external dependency for auth.

### Key Metrics

| Metric | Current (Firebase) | Proposed (Supabase) |
|--------|-------------------|---------------------|
| Auth providers | 2 (Firebase + Supabase) | **1** (Supabase) |
| Token verification | HTTPS call to Google servers | **Local JWKS verification** |
| Auth latency per request | 200-600ms | **~0ms** (CPU only) |
| Offline-capable auth | No | **Yes** (with cached JWKS) |
| SSL dependency | Yes (failing in dev) | **No** (own Supabase instance) |
| Database ⇔ Auth integration | Firebase UID → Supabase FK | **Direct user ID** |

---

## 2. Why Migrate

### 2.1 Security

| # | Issue | Current (Firebase) | Proposed (Supabase) |
|---|-------|-------------------|---------------------|
| **S1** | **Per-request external network call** | Every API request calls Firebase servers to verify session cookie. Creates a DoS vector: if Firebase is unreachable, auth is unreachable. | JWT verified **locally** using cached public keys. Supabase outage does not block authentication — only token minting. |
| **S2** | **SSL chain dependency** | Firebase Admin SDK requires Node.js to verify Google's SSL chain. Fails on misconfigured CA stores (current dev blocker). | Supabase JWT verification is a local RSA operation. No SSL needed for auth verification. |
| **S3** | **Attack surface: two providers** | Two sets of credentials to secure (Firebase service account + Supabase service role key). Two SDKs with potential vulnerabilities. | Single Supabase service role key. One SDK to audit. |
| **S4** | **User data synchronization** | Firebase UID stored in Supabase `users.auth_id`. Must keep in sync. Race conditions possible on first login. | Supabase Auth users are **native** to Supabase. The `auth.users` table is authoritative. No sync needed. |

### 2.2 Performance

```
Current path per API request:
  Proxy → Backend → verify_session_cookie()
                     ↓
              HTTPS → Google Firebase servers
                     ↓
              200-600ms network latency
                     ↓
              returns { uid, ... }

Proposed path per API request:
  Proxy → Backend → verify_jwt(token)
                     ↓
              Local RSA verify (80-150μs)
                     ↓
              returns { sub, ... }
```

- **~3000x faster** auth verification (microseconds vs milliseconds)
- **Zero external network calls** for auth on steady-state requests
- **Offline-capable** — if Supabase has a brief outage, existing sessions continue to work (tokens are verified locally; only new logins need Supabase)

### 2.3 Maintainability

| Aspect | Firebase | Supabase |
|--------|----------|----------|
| SDKs required | `firebase` + `firebase-admin` (web), `firebase_auth` + `firebase_core` (mobile), `firebase-admin` (backend) | `@supabase/supabase-js` (web), `supabase_flutter` (mobile), `supabase` (backend — **already installed**) |
| Lines of auth code | ~600 lines across 15+ files | ~300 lines across 8 files (halved) |
| Infrastructure files | `firebase.json`, `.firebaserc`, `apphosting.yaml`, `firestore.rules` | None to remove |
| Env vars required | 14 Firebase vars (6 client + 8 admin) | **5 vars** (URL + anon key + service role key — **3 of which already exist**) |

### 2.4 SSL Issue Root Cause

The current dev SSL error (`unable to verify the first certificate`) occurs because:

1. `POST /api/auth/session` calls `adminAuth.verifyIdToken(idToken)` which makes an HTTPS request to `https://www.googleapis.com/identitytoolkit/...`
2. Google's servers present a certificate chain that Node.js v24's bundled CA store cannot fully verify on this Windows machine
3. The session cookie is never created → no cookie on subsequent requests → all API calls return 401

With Supabase Auth, the session endpoint calls **your own Supabase instance's REST API** (same origin as database calls) or verifies the JWT locally. No SSL chain dependency beyond what your browser already trusts for your Supabase dashboard.

---

## 3. Current Architecture (Firebase)

### 3.1 Auth Flow

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐     ┌───────────┐
│  Client  │     │  Next.js     │     │  Proxy      │     │  Backend     │     │ Firebase  │
│ (Web/Mob)│     │  Session API │     │  [...path]  │     │  (FastAPI)   │     │  Servers  │
└────┬─────┘     └──────┬───────┘     └──────┬──────┘     └──────┬───────┘     └─────┬─────┘
     │                   │                    │                  │                   │
     │ 1. signInWith     │                    │                  │                   │
     │    EmailPassword()│                    │                  │                   │
     │──────────────────>│                    │                  │                   │
     │                   │                    │                  │                   │
     │ 2. ID Token       │                    │                  │                   │
     │<──────────────────│                    │                  │                   │
     │                   │                    │                  │                   │
     │ 3. POST /auth/    │                    │                  │                   │
     │    session        │                    │                  │                   │
     │    { idToken }    │                    │                  │                   │
     │──────────────────>│                    │                  │                   │
     │                   │ 4. verifyIdToken() │                  │                   │
     │                   │──────────────────────────────────────────────────────────>│
     │                   │                    │                  │                   │
     │                   │ 5. createSession-  │                  │                   │
     │                   │    Cookie()        │                  │                   │
     │                   │<──────────────────────────────────────────────────────────│
     │                   │                    │                  │                   │
     │ 6. Set-Cookie:    │                    │                  │                   │
     │    __session      │                    │                  │                   │
     │<──────────────────│                    │                  │                   │
     │                   │                    │                  │                   │
     │ 7. GET /api/proxy │                    │                  │                   │
     │    /watchlists    │                    │                  │                   │
     │    Cookie: ______ │                    │                  │                   │
     │───────────────────────────────────────>│                  │                   │
     │                   │                    │ 8. Extract       │                   │
     │                   │                    │    __session     │                   │
     │                   │                    │    → Bearer      │                   │
     │                   │                    │                  │                   │
     │                   │                    │ 9. GET /watchlists                 │
     │                   │                    │    Authorization                   │
     │                   │                    │    : Bearer <c>                    │
     │                   │                    │──────────────────>                  │
     │                   │                    │                  │ 10. verify_      │
     │                   │                    │                  │     session_     │
     │                   │                    │                  │     cookie()     │
     │                   │                    │                  │─────────────────>│
     │                   │                    │                  │                 │
     │                   │                    │                  │ 11. { uid }     │
     │                   │                    │                  │<─────────────────│
     │                   │                    │                  │                 │
     │                   │                    │ 12. 200 { data } │                 │
     │                   │                    │<──────────────────│                 │
     │ 13. 200 { data }  │                    │                  │                 │
     │<───────────────────────────────────────│                  │                 │
```

**Problem:** Steps 4-5 and 10 each require an HTTPS call to Google's servers. Steps 4-5 happen on every login. Step 10 happens on **every single API request** — all 74 authenticated endpoints.

### 3.2 External Dependencies Per Request

```
Browser → Next.js → FastAPI → (wait for Firebase) → response
                ↕               ↕
          No external      verify_session_cookie()
          call (BFF)          ↓
                          HTTPS to Google servers
                              ↓
                          200-600ms
```

### 3.3 Files Using Firebase

| Layer | Files | Lines |
|-------|-------|-------|
| Backend | `auth.py`, `config.py`, `main.py` | ~250 |
| Web server | `firebase-admin.ts`, `session/route.ts` | ~180 |
| Web client | `index.ts`, `config.ts`, `provider.tsx`, `client-provider.tsx`, `auth-provider.tsx`, `login-form.tsx`, `signup-form.tsx`, `auth.service.ts` | ~700 |
| Web Firestore | `use-doc.tsx`, `use-collection.tsx`, `non-blocking-updates.tsx`, `errors.ts`, `error-emitter.ts`, `FirebaseErrorListener.tsx` | ~200 |
| Mobile | `firebase_config.dart`, `auth_provider.dart`, `auth_interceptor.dart`, `main.dart` | ~200 |
| Tests | `helpers.py`, `conftest.py`, `generate_test_token.py` | ~300 |
| Infrastructure | `firebase.json`, `.firebaserc`, `apphosting.yaml`, `firestore.rules` | — |
| **Total** | **~30 files** | **~1,800 lines** |

---

## 4. Proposed Architecture (Supabase)

### 4.1 Auth Flow

```
┌──────────┐     ┌──────────────┐     ┌─────────────┐     ┌──────────────┐
│  Client  │     │  Next.js     │     │  Proxy      │     │  Backend     │
│ (Web/Mob)│     │  Session API │     │  [...path]  │     │  (FastAPI)   │
└────┬─────┘     └──────┬───────┘     └──────┬──────┘     └──────┬───────┘
     │                   │                    │                  │
     │ 1. supabase.auth  │                    │                  │
     │    .signInWith-   │                    │                  │
     │    Password()     │                    │                  │
     │──────────────────>│                    │                  │
     │                   │  (Supabase Auth    │                  │
     │                   │   server validates │                  │
     │                   │   credentials)     │                  │
     │                   │                    │                  │
     │ 2. access_token   │                    │                  │
     │    (JWT)          │                    │                  │
     │<──────────────────│                    │                  │
     │                   │                    │                  │
     │ 3. POST /auth/    │                    │                  │
     │    session        │                    │                  │
     │    { accessToken }│                    │                  │
     │──────────────────>│                    │                  │
     │                   │ 4. Verify JWT      │                  │
     │                   │    signature       │                  │
     │                   │    (local JWKS)    │                  │
     │                   │                    │                  │
     │ 5. Set-Cookie:    │                    │                  │
     │    __session=JWT  │                    │                  │
     │<──────────────────│                    │                  │
     │                   │                    │                  │
     │ 6. GET /api/proxy │                    │                  │
     │    /watchlists    │                    │                  │
     │    Cookie: ______ │                    │                  │
     │───────────────────────────────────────>│                  │
     │                   │                    │ 7. Extract       │
     │                   │                    │    __session     │
     │                   │                    │    → Bearer      │
     │                   │                    │                  │
     │                   │                    │ 8. GET /watchlists                │
     │                   │                    │    Authorization                   │
     │                   │                    │    : Bearer <JWT>                  │
     │                   │                    │──────────────────>                  │
     │                   │                    │                  │ 9. Verify JWT  │
     │                   │                    │                  │    signature   │
     │                   │                    │                  │    (local)     │
     │                   │                    │                  │    ~80μs       │
     │                   │                    │                  │                │
     │                   │                    │ 10. 200 { data } │                │
     │                   │                    │<──────────────────│                │
     │ 11. 200 { data }  │                    │                  │                │
     │<───────────────────────────────────────│                  │                │
```

**Key difference:** Steps 4 and 9 are **local CPU operations** — no network calls. The JWKS public keys are fetched once from `https://project.supabase.co/auth/v1/.well-known/jwks.json` and cached indefinitely (they only change on key rotation).

### 4.2 External Dependencies Per Request

```
Browser → Next.js → FastAPI → (local verify) → response
                ↕               ↕
          No external      verify_jwt(token) 
          call (BFF)          ↓
                          CPU local RSA
                              ↓
                          ~80μs
```

### 4.3 JWKS Key Caching Strategy

```python
# Backend (auth.py) — simplified
_jwks_cache = {"keys": None, "fetched_at": 0}
JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
JWKS_CACHE_TTL = 86400  # 24 hours; keys rotate rarely

def _get_jwks_keys() -> list[dict]:
    """Fetch and cache Supabase JWKS public keys."""
    now = time.time()
    if _jwks_cache["keys"] and (now - _jwks_cache["fetched_at"]) < JWKS_CACHE_TTL:
        return _jwks_cache["keys"]
    resp = requests.get(JWKS_URL, timeout=5)
    resp.raise_for_status()
    _jwks_cache["keys"] = resp.json()["keys"]
    _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]

def verify_jwt(token: str) -> dict:
    """Verify a Supabase JWT locally using cached JWKS keys."""
    unverified = jwt.get_unverified_header(token)
    key = next(k for k in _get_jwks_keys() if k["kid"] == unverified["kid"])
    public_key = RSAAlgorithm.from_jwk(json.dumps(key))
    return jwt.decode(
        token, public_key,
        algorithms=["RS256"],
        audience="authenticated",
        options={"require": ["exp", "sub"]}
    )
```

---

## 5. Architecture Comparison

### 5.1 Auth Flow Comparison

| Step | Current (Firebase) | Proposed (Supabase) |
|------|-------------------|---------------------|
| **Sign-up** | `createUserWithEmailAndPassword()` → Firebase servers | `supabase.auth.signUp()` → Supabase Auth server |
| **Sign-in** | `signInWithEmailAndPassword()` → Firebase servers | `supabase.auth.signInWithPassword()` → Supabase Auth server |
| **Token exchange** | Send ID token → verifyIdToken() via HTTPS → createSessionCookie() via HTTPS | Send access_token JWT → verify JWT signature **locally** → set cookie |
| **Session cookie** | Firebase session cookie (opaque, Firebase-specific format) | Supabase access_token JWT (standard JWT, self-verifiable) |
| **Request auth** | Proxy reads `__session` → injects Bearer → backend calls `verify_session_cookie()` via HTTPS to Firebase | Proxy reads `__session` → injects Bearer → backend verifies JWT **locally** |
| **User resolution** | Firebase UID → query Supabase `users` table by `auth_id` | JWT `sub` claim IS the Supabase user ID. Direct lookup. |

### 5.2 Performance Comparison

```
Firebase (Current):
  Login:     verifyIdToken() HTTPS  +  createSessionCookie() HTTPS  = 400-1200ms
  API call:  verify_session_cookie() HTTPS                          = 200-600ms

Supabase (Proposed):
  Login:     JWT sign-in HTTPS          +  local JWT verify         = 200-400ms
  API call:  local JWT verify (cached)                              = 80-150μs
```

### 5.3 Security Comparison

| Threat | Firebase | Supabase |
|--------|----------|----------|
| **DoS via auth server** | Firebase down = no auth possible | Auth verified locally; only new logins blocked during Supabase outage |
| **MitM on verify calls** | Requires trust in Google's CA chain (failing in dev) | No verify-time network calls; JWKS fetched once over HTTPS |
| **Credential leak** | Firebase service account JSON (file or env vars) | Supabase service_role key (already existing env var) |
| **Token verification** | Opaque Firebase session cookie format | Standard JWT (RS256), verifiable by any JWT library |

### 5.4 Code Comparison

| File | Firebase (current) | Supabase (proposed) |
|------|-------------------|---------------------|
| `backend/auth.py` | 118 lines (Firebase Admin init + verify_session_cookie) | ~60 lines (JWKS fetch + local JWT verify) |
| `web/src/providers/auth-provider.tsx` | 294 lines (Firebase SDK + session cookie management) | ~150 lines (Supabase SDK + session cookie management) |
| `web/src/lib/firebase-admin.ts` | 76 lines (Firebase Admin singleton) | **Removed** (no server-side Admin SDK needed) |
| `web/src/firebase/` directory | 7 files (index, config, provider, client-provider, errors, error-emitter, non-blocking-login, non-blocking-updates) | **Removed** (replaced by `src/lib/supabase.ts` — 1 file) |
| `web/src/firebase/firestore/` directory | 2 files (use-doc, use-collection) | **Removed or migrated** to Supabase Realtime |
| `mobile/` firebase files | 4 files | **Removed** (replaced by supabase_flutter) |

---

## 6. Local JWT Verification: The Key Security Improvement

### 6.1 Why It Matters

Every authentication system must verify that a presented token was legitimately issued. There are two approaches:

**Network-bound (Firebase):**
```
token → HTTPS call to issuer → "yes, this token is valid" → 200-600ms
```

**Local (Supabase with JWKS):**
```
token → fetch public key once → verify RSA signature locally → 80-150μs
```

The local approach is:
- **Faster** by orders of magnitude
- **More reliable** — no network dependency for steady-state auth
- **Offline-tolerant** — cached JWKS keys work even during brief Supabase outages
- **More secure against certain attacks** — no token verification endpoint to DoS

### 6.2 JWKS Explained

JWKS (JSON Web Key Set) is a standard format for distributing public keys:

```json
// GET https://project.supabase.co/auth/v1/.well-known/jwks.json
{
  "keys": [{
    "kty": "RSA",
    "kid": "abc123def456",
    "n": "0vx7agoebG...",  // RSA modulus (base64url)
    "e": "AQAB",            // RSA exponent
    "alg": "RS256",
    "use": "sig"
  }]
}
```

These keys are:
- **Fetched once** on first auth verification and cached
- **Re-fetched only on key rotation** (Supabase rotates keys rarely, typically only on manual action)
- **Public** — no secret to protect
- **Standard** — any JWT library (PyJWT, jsonwebtoken, dart_jsonwebtoken) can use them

### 6.3 Trust Model

```
Firebase:
  Client → Firebase SDK → Firebase Auth servers (trust Google's CA)
         → ID Token → Next.js → Firebase Admin SDK → Google's servers (trust Google's CA)
         → Session Cookie → Proxy → Backend → Firebase Admin → Google's servers (trust Google's CA)

Supabase:
  Client → Supabase SDK → Supabase Auth (trust your Supabase TLS)
         → JWT → Next.js → local verify (trust: one-time JWKS fetch over TLS)
         → JWT → Proxy → Backend → local verify (trust: cached JWKS, never re-fetches)
```

With Supabase, TLS trust is required once (JWKS fetch) instead of every single request. This is the same cryptographic trust model used by Vercel, Netlify, Clerk, and Auth0.

---

## 7. Detailed Component Changes

### 7.1 Backend (Python/FastAPI)

#### 7.1.1 `backend/auth.py` — 🔴 Rewrite

**Current:** Firebase Admin SDK init + `verify_session_cookie()`. 118 lines.

**Changes:**
- Remove `firebase_admin` imports
- Remove `initialize_firebase_app()` function
- Add `_get_jwks_keys()` — fetches and caches Supabase JWKS public keys
- Add `verify_jwt()` — verifies JWT locally using cached JWKS
- Rewrite `get_current_user()` to call `verify_jwt()` instead of `verify_session_cookie()`
- Return dict with `sub` (user ID) and `email` from JWT claims

```python
# Proposed structure:
import httpx
from jwt import decode as jwt_decode, get_unverified_header
from jwt.algorithms import RSAAlgorithm

JWKS_URL = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
_jwks = {"keys": None, "fetched": 0}

def _get_public_key(kid: str) -> str:
    if not _jwks["keys"] or time.time() - _jwks["fetched"] > 86400:
        resp = httpx.get(JWKS_URL, timeout=5)
        resp.raise_for_status()
        _jwks["keys"] = resp.json()["keys"]
        _jwks["fetched"] = time.time()
    key = next(k for k in _jwks["keys"] if k["kid"] == kid)
    return RSAAlgorithm.from_jwk(json.dumps(key))

def get_current_user(request: Request):
    auth_header = request.headers.get(AUTHORIZATION_HEADER)
    # ... extract Bearer token ...
    unverified = get_unverified_header(token)
    public_key = _get_public_key(unverified["kid"])
    decoded = jwt_decode(token, public_key, algorithms=["RS256"],
                         audience="authenticated",
                         options={"require": ["exp", "sub"]})
    return decoded
```

#### 7.1.2 `backend/config.py` — 🟡 Update

**Changes:**
- Remove `FIREBASE_PROJECT_ID`, `FIREBASE_ADMIN_*` fields
- Ensure `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are required
- Add `SUPABASE_JWT_SECRET` or `SUPABASE_ANON_KEY` if needed for JWT verification fallback

#### 7.1.3 `backend/main.py` — 🟡 Update

**Changes:**
- Replace `from auth import get_current_user, initialize_firebase_app` with `from auth import get_current_user`
- Remove `initialize_firebase_app()` from startup lifespan
- Keep `app.dependency_overrides[get_current_user_dep] = get_current_user`

#### 7.1.4 `backend/requirements.in` — 🟢 Remove dependency

**Changes:**
- Remove `firebase-admin==7.4.0`
- Add `PyJWT[crypto]` if not already present (already listed as transitive)
- Add `httpx` (already listed) — used for JWKS fetch

#### 7.1.5 `backend/infrastructure/repositories/supabase_repository.py` — 🟡 Update

**Current:**
```python
def find_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict]:
```

**Changes:**
- Rename to `find_by_auth_id()` (or keep as-is if column name stays `auth_id`)
- The Supabase JWT `sub` claim contains the Supabase user UUID, which is already the value stored in `auth_id`
- No schema migration needed if the column name stays — only the semantic meaning changes (was Firebase UID, now Supabase user UUID)

#### 7.1.6 `backend/api/users.py` — 🟡 Update

**Current:** `POST /users/sync` receives Firebase UID from token, upserts user in Supabase.

**Changes:**
- The JWT `sub` IS the Supabase user ID — no need to look up or create by Firebase UID
- Simplify to: if JWT is valid, the user exists in Supabase Auth. Upsert by Supabase user UUID instead of Firebase UID.

#### 7.1.7 All Other Backend API Files — ✅ No change

Files: `watchlists.py`, `portfolio.py`, `valuations.py`, `analysis.py`, `chat.py`, `stocks.py`, `watchlist_items.py`

These all use `Depends(get_current_user_dep)` which is overridden to `get_current_user`. The returned dict format changes slightly (Firebase: `{uid, sub}` → Supabase: `{sub, email, role}`) but all endpoints access `token["sub"]` for the user ID, which is the same key.

#### 7.1.8 `backend/application/services/watchlist_service.py` — 🟡 Update

**Changes:**
- `get_db_user_id()` calls `self.user_repo.find_by_firebase_uid(firebase_uid)` 
- Rename to `find_by_auth_id()` or keep as-is. The parameter name changes from `firebase_uid` to `auth_id`.

### 7.2 Web (Next.js/TypeScript)

#### 7.2.1 `web/package.json` — 🔴 Update dependencies

**Changes:**
- Remove `firebase@^11.9.1`
- Remove `firebase-admin@^13.8.0`
- Add `@supabase/supabase-js@^2.49.0`

#### 7.2.2 `web/src/lib/firebase-admin.ts` — 🔴 **Delete**

**Reason:** No server-side Firebase Admin SDK needed. JWT verification on the session endpoint will use `@supabase/supabase-js` server-client or direct JWKS verification.

**Replacement:** `web/src/lib/supabase-admin.ts` (optional) — server-side Supabase client with service_role key for admin operations.

#### 7.2.3 `web/src/lib/api.ts` — 🟢 Minor update

**Changes:**
- Remove `import { getUnauthorizedHandler } from "@/features/auth/services/token-manager"` — the handler pattern stays but moves
- Keep all other logic (CSRF, withCredentials, retry)

#### 7.2.4 `web/src/lib/supabase.ts` — 🆕 **New file**

Client-side Supabase singleton:
```typescript
import { createBrowserClient } from "@supabase/ssr";

const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

export default supabase;
```

#### 7.2.5 `web/src/firebase/` — 🔴 **Delete entire directory**

**Files to delete:**
- `config.ts`
- `index.ts`
- `provider.tsx`
- `client-provider.tsx`
- `errors.ts`
- `error-emitter.ts`
- `non-blocking-login.tsx`
- `non-blocking-updates.tsx`
- `firestore/use-doc.tsx`
- `firestore/use-collection.tsx`

**Replacement:** A single `web/src/lib/supabase.ts` file. Firestore hooks either migrate to Supabase Realtime or get removed.

#### 7.2.6 `web/src/providers/auth-provider.tsx` — 🔴 Rewrite

**Current:** Uses Firebase `onIdTokenChanged`, `getIdToken()`, `createUserWithEmailAndPassword`, `signOut`.

**Changes:**
- Replace Firebase SDK calls with Supabase SDK calls:
  - `onIdTokenChanged` → `supabase.auth.onAuthStateChange()`
  - `getIdToken()` → `supabase.auth.getSession()` (access_token)
  - `createUserWithEmailAndPassword()` → `supabase.auth.signUp()`
  - `signOut()` → `supabase.auth.signOut()`
- Keep the `persistSessionCookie()` pattern — send Supabase access_token to `/api/auth/session`
- Keep the 45-minute periodic refresh pattern — use `supabase.auth.refreshSession()` instead
- Keep `registerUnauthorizedHandler()` for 401/403 handling

**Key simplification:** No need to force-refresh tokens separately — Supabase SDK handles refresh automatically via the `refresh_token`.

```typescript
// Before (Firebase):
const idToken = await firebaseUser.getIdToken(forceRefresh);
await fetch('/api/auth/session', {
  method: 'POST',
  body: JSON.stringify({ idToken }),
});

// After (Supabase):
const { data: { session } } = await supabase.auth.getSession();
await fetch('/api/auth/session', {
  method: 'POST',
  body: JSON.stringify({ accessToken: session.access_token }),
});
```

#### 7.2.7 `web/src/app/api/auth/session/route.ts` — 🟡 Update

**Current:** Receives `idToken`, verifies via `adminAuth.verifyIdToken()`, mints via `adminAuth.createSessionCookie()`.

**Changes:**
- Receive `accessToken` instead of `idToken`
- Verify the JWT locally using `@supabase/supabase-js` server client or `jose` library
- Set the `__session` cookie with the access_token value (no need to mint a new token — the Supabase JWT IS the session)
- OR use `supabase-admin` to call Supabase Auth's `GET /auth/v1/user` endpoint to verify server-side

**Option A (simpler, recommended):**
```typescript
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function POST(req: NextRequest) {
  const { accessToken } = await req.json();
  const cookieStore = await cookies();

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => cookieStore.getAll() } }
  );

  // This calls Supabase's /auth/v1/user endpoint to verify the token
  const { data: { user }, error } = await supabase.auth.getUser(accessToken);

  if (error) return NextResponse.json({ error: "Invalid token" }, { status: 401 });

  // Set the access_token as the session cookie
  const res = NextResponse.json({ ok: true });
  res.cookies.set({
    name: SESSION_COOKIE_NAME,
    value: accessToken,
    httpOnly: true,
    secure: isHttps,
    sameSite: "strict",
    path: "/",
    maxAge: 60 * 60 * 24 * 5, // 5 days
  });
  return res;
}
```

**Option B (local verify, better performance):**
Same as Option A but uses `jose` library to verify the JWT signature locally using cached JWKS keys.

#### 7.2.8 `web/src/app/api/proxy/[...path]/route.ts` — ✅ No change

The proxy already reads `__session` cookie and injects it as `Authorization: Bearer`. The cookie value now contains a Supabase JWT instead of a Firebase session cookie, but the proxy treats both identically — it's just a string.

#### 7.2.9 `web/src/components/auth/login-form.tsx` — 🟡 Update

**Changes:**
- Replace `import { signInWithEmailAndPassword } from 'firebase/auth'` with `import supabase from '@/lib/supabase'`
- Replace `signInWithEmailAndPassword(auth, email, password)` with `supabase.auth.signInWithPassword({ email, password })`
- The `onAuthStateChange` listener in `auth-provider.tsx` picks up the session

#### 7.2.10 `web/src/components/auth/signup-form.tsx` — 🟡 Update

**Changes:**
- Replace `useAuth().signUpWithEmail(email, password, fullName)` with `supabase.auth.signUp({ email, password, options: { data: { full_name: fullName } } })`
- Or keep the provider method but update its internal implementation

#### 7.2.11 `web/src/app/layout.tsx` — 🟡 Update

**Changes:**
- Remove `FirebaseClientProvider` from the provider tree
- Add `SupabaseProvider` or direct supabase initialization in `AuthProvider`

#### 7.2.12 `web/src/features/auth/services/auth.service.ts` — 🟡 Update

**Changes:**
- `exchangeTokenForUser()` currently posts to `/users/sync` with email/username from FirebaseUser
- Update to use email/username from Supabase user object
- The `/users/sync` endpoint itself also updates (backed), but the service call signature stays

#### 7.2.13 `web/src/features/auth/services/token-manager.ts` — ✅ No change

This file only stores a callback for 401/403 handling. No Firebase dependency.

#### 7.2.14 `web/src/components/FirebaseErrorListener.tsx` — 🔴 **Delete**

Firestore permission error listener. No longer needed.

#### 7.2.15 `web/.env.example` — 🔴 Update

**Changes:**
- Remove all `NEXT_PUBLIC_FIREBASE_*` vars (9 vars)
- Remove all `FIREBASE_ADMIN_*` vars (5 vars)
- Add `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`

#### 7.2.16 Firestore Hooks — 🔴 **Delete or Replace**

**Files:**
- `web/src/firebase/firestore/use-doc.tsx` — Real-time document subscription
- `web/src/firebase/firestore/use-collection.tsx` — Real-time collection subscription
- `web/src/firebase/non-blocking-updates.tsx` — fire-and-forget writes

**Options:**
1. **Delete** if these features are unused (check for imports across the codebase)
2. **Replace** with Supabase Realtime equivalents using `supabase.channel()` 
3. **Keep Firestore** during a transitional period (add a firestore guard that only initializes if Firebase config env vars exist)

### 7.3 Mobile (Flutter/Dart)

#### 7.3.1 `mobile/pubspec.yaml` — 🟡 Update

**Changes:**
- Remove `firebase_core: ^3.1.0`
- Remove `firebase_auth: ^5.1.0`
- Remove `firebase_analytics: ^11.0.0`
- Remove `firebase_crashlytics: ^4.0.0`
- Add `supabase_flutter: ^2.8.0`

#### 7.3.2 `mobile/lib/main.dart` — 🟡 Update

**Changes:**
- Replace `Firebase.initializeApp()` with `Supabase.initialize(url, anonKey)`
- Remove Firebase Auth instance verification

#### 7.3.3 `mobile/lib/core/config/firebase_config.dart` — 🔴 **Delete**

Replace with Supabase config (or inline the URL and anon key in `main.dart`).

#### 7.3.4 `mobile/lib/features/auth/providers/auth_provider.dart` — 🔴 Rewrite

**Changes:**
- Replace `FirebaseAuth.instance.authStateChanges()` with `Supabase.instance.client.auth.onAuthStateChange`
- Replace `FirebaseAuth.instance.signOut()` with `supabase.auth.signOut()`
- Update user sync to use Supabase user data

#### 7.3.5 `mobile/lib/core/api/auth_interceptor.dart` — 🟡 Update

**Changes:**
- Replace Firebase token retrieval with Supabase session access token
- `user.getIdToken(true)` → `supabase.auth.currentSession!.accessToken`

### 7.4 Tests

#### 7.4.1 `tests/e2e/helpers.py` — 🔴 Rewrite

**Current:** Uses Firebase Admin SDK to create custom tokens, exchanges them for ID tokens via REST API.

**Changes:**
- Use Supabase service_role key to create users via `supabase.auth.admin.createUser()` or direct DB insert into `auth.users` table
- Generate test JWTs using `supabase.auth.admin.generateLink()` or by signing JWTs directly with `SUPABASE_JWT_SECRET`

```python
# Proposed approach:
from supabase import create_client

def get_auth_headers():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    # Sign in as the test user
    resp = supabase.auth.sign_in_with_password({
        "email": "test@stockerpro.dev",
        "password": TEST_USER_PASSWORD,
    })
    token = resp.session.access_token
    return {"Authorization": f"Bearer {token}"}
```

#### 7.4.2 `tests/e2e/conftest.py` — 🟡 Update

**Changes:**
- Update `e2e_auth_headers` fixture to use new Supabase-based `get_auth_headers()`

#### 7.4.3 `backend/scripts/generate_test_token.py` — 🔴 Rewrite

**Changes:**
- Replace Firebase custom token generation with Supabase JWT generation
- Use `SUPABASE_JWT_SECRET` to sign custom JWTs for test users

#### 7.4.4 `tests/backend/test_auth.py` — 🟡 Update

**Changes:**
- Replace `@patch("firebase_admin.auth.verify_session_cookie")` with `@patch("auth.verify_jwt")` or `@patch("auth._get_public_key")`
- Test cases remain the same (valid token → success, missing token → 401, expired token → 401)

### 7.5 Infrastructure

#### 7.5.1 `firebase.json` — 🔴 **Delete**

Firebase Hosting configuration. No longer needed if not using Firebase Hosting.

#### 7.5.2 `.firebaserc` — 🔴 **Delete**

Firebase project reference.

#### 7.5.3 `apphosting.yaml` — 🔴 **Delete**

Firebase App Hosting configuration. Replace with alternative platform config (e.g., `vercel.json`, `render.yaml`, Dockerfile).

#### 7.5.4 `firestore.rules` — 🔴 **Delete**

Firestore security rules. No longer needed.

#### 7.5.5 `backend/.env.example` — 🟡 Update

**Changes:**
- Remove `FIREBASE_PROJECT_ID` line
- Add comment that `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` serve both database and auth

---

## 8. Environment Variables

### 8.1 Before (Firebase) — 14 env vars

```
# Web (.env.local)
NEXT_PUBLIC_FIREBASE_API_KEY
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN
NEXT_PUBLIC_FIREBASE_PROJECT_ID
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID
NEXT_PUBLIC_FIREBASE_APP_ID
NEXT_PUBLIC_FIREBASE_MEASUREMENT_ID
FIREBASE_ADMIN_PRIVATE_KEY_ID
FIREBASE_ADMIN_PRIVATE_KEY
FIREBASE_ADMIN_CLIENT_EMAIL
FIREBASE_ADMIN_CLIENT_ID
FIREBASE_ADMIN_CLIENT_X509_CERT_URL

# Backend (.env)
FIREBASE_PROJECT_ID
```

### 8.2 After (Supabase) — 5 env vars

```
# Web (.env.local)
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY

# Backend (.env)
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
```

Note: `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` already exist in `backend/.env` — they are currently used for database access.

---

## 9. Data Model Changes

### 9.1 Current Schema

```sql
-- Supabase users table (currently stores Firebase UID)
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id TEXT NOT NULL UNIQUE,       -- Firebase UID
    email TEXT,
    username TEXT,
    -- ...
);

-- Query: find by Firebase UID
SELECT user_id FROM users WHERE auth_id = 'firebase_uid_here';
```

### 9.2 Proposed Schema

Supabase Auth automatically creates a row in `auth.users` when a user signs up. The `auth.users.id` is the UUID that appears as the `sub` claim in JWTs.

```sql
-- Same users table — only the semantic meaning of auth_id changes
CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    auth_id UUID NOT NULL UNIQUE REFERENCES auth.users(id),  -- Now references Supabase auth.users!
    email TEXT,
    username TEXT,
    -- ...
);

-- Query: find by JWT sub claim (same query, different value origin)
SELECT user_id FROM users WHERE auth_id = 'supabase_user_uuid_from_jwt_sub';
```

**No schema migration needed.** The `auth_id` column already stores user identifiers as strings. The only change is that:
- **Before:** `auth_id = "abc123def456"` (Firebase UID — 28-char string)
- **After:** `auth_id = "123e4567-e89b-12d3-a456-426614174000"` (Supabase user UUID — UUID format)

---

## 10. Migration Path

### Phase 0: Preparation (1 day)

| Step | File | Change |
|------|------|--------|
| 0.1 | `backend/requirements.in` | Remove `firebase-admin==7.4.0`. Add `PyJWT[crypto]` explicitly. |
| 0.2 | `web/package.json` | Remove `firebase` and `firebase-admin`. Add `@supabase/supabase-js` and `@supabase/ssr`. |
| 0.3 | `mobile/pubspec.yaml` | Remove `firebase_core`, `firebase_auth`, `firebase_analytics`, `firebase_crashlytics`. Add `supabase_flutter`. |
| 0.4 | All `.env` files | Update example files. Remove Firebase vars, add Supabase vars. |

### Phase 1: Backend (1.5 days)

| Step | File | Change |
|------|------|--------|
| 1.1 | `backend/auth.py` | Rewrite — remove Firebase Admin init, add JWKS fetch + local JWT verify |
| 1.2 | `backend/config.py` | Remove `FIREBASE_PROJECT_ID`, `FIREBASE_ADMIN_*` fields |
| 1.3 | `backend/main.py` | Remove `initialize_firebase_app()` call from startup |
| 1.4 | `backend/api/users.py` | Update `/users/sync` to use Supabase user UUID instead of Firebase UID |
| 1.5 | `backend/infrastructure/repositories/supabase_repository.py` | Rename `find_by_firebase_uid` to `find_by_auth_id` |

### Phase 2: Web — Server-Side (1 day)

| Step | File | Change |
|------|------|--------|
| 2.1 | `web/src/lib/firebase-admin.ts` | **Delete** |
| 2.2 | `web/src/lib/supabase.ts` | **Create** — client-side Supabase singleton |
| 2.3 | `web/src/lib/supabase-admin.ts` | **Create** — server-side Supabase client with service_role key (optional) |
| 2.4 | `web/src/app/api/auth/session/route.ts` | Update to verify Supabase JWT and set as session cookie |

### Phase 3: Web — Client-Side (2 days)

| Step | File | Change |
|------|------|--------|
| 3.1 | `web/src/firebase/` | **Delete entire directory** (all 10 files) |
| 3.2 | `web/src/providers/auth-provider.tsx` | Rewrite — replace all Firebase SDK calls with Supabase SDK |
| 3.3 | `web/src/components/auth/login-form.tsx` | Update to use `supabase.auth.signInWithPassword()` |
| 3.4 | `web/src/components/auth/signup-form.tsx` | Update to use `supabase.auth.signUp()` |
| 3.5 | `web/src/features/auth/services/auth.service.ts` | Update user data extraction from Supabase user |
| 3.6 | `web/src/app/layout.tsx` | Remove `FirebaseClientProvider`, add Supabase initialization in AuthProvider |
| 3.7 | `web/src/components/FirebaseErrorListener.tsx` | **Delete** |

### Phase 4: Mobile (1.5 days)

| Step | File | Change |
|------|------|--------|
| 4.1 | `mobile/lib/core/config/firebase_config.dart` | **Delete** |
| 4.2 | `mobile/lib/main.dart` | Replace Firebase init with Supabase init |
| 4.3 | `mobile/lib/features/auth/providers/auth_provider.dart` | Rewrite — Supabase SDK instead of Firebase |
| 4.4 | `mobile/lib/core/api/auth_interceptor.dart` | Update to use Supabase access_token |

### Phase 5: Tests (1 day)

| Step | File | Change |
|------|------|--------|
| 5.1 | `tests/e2e/helpers.py` | Rewrite — generate Supabase test tokens instead of Firebase |
| 5.2 | `tests/e2e/conftest.py` | Update fixture to new helpers |
| 5.3 | `tests/backend/test_auth.py` | Update mocks from Firebase to JWKS/JWT |
| 5.4 | `backend/scripts/generate_test_token.py` | Rewrite for Supabase |

### Phase 6: Cleanup (0.5 day)

| Step | File | Change |
|------|------|--------|
| 6.1 | `firebase.json` | **Delete** |
| 6.2 | `.firebaserc` | **Delete** |
| 6.3 | `apphosting.yaml` | **Delete** (or update deployment platform) |
| 6.4 | `firestore.rules` | **Delete** |
| 6.5 | `web/.env.example` | Clean — only Supabase vars remain |
| 6.6 | `backend/.env.example` | Clean — no more Firebase vars |

---

## 11. Rollback Plan

### 11.1 During Migration

Each phase can be deployed independently. The proxy and session endpoint are the critical path:

1. **Phase 1 (Backend)** is backward-compatible: the backend accepts `Authorization: Bearer <any_token>`. If Supabase verification fails, the backend returns 401 — same as if Firebase verification failed.
2. **Phase 2-3 (Web)** must be deployed together: if the client sends a Firebase ID token to the session endpoint but the endpoint expects a Supabase JWT, login fails.
3. **Phase 4 (Mobile)** is independent of web.

**Dual-running strategy:**
During migration, the backend can temporarily accept both Firebase session cookies AND Supabase JWTs:

```python
def get_current_user(request):
    token = extract_bearer(request)
    try:
        # Try Supabase JWT first (new)
        return verify_supabase_jwt(token)
    except:
        # Fall back to Firebase session cookie (old) — deprecated
        logger.warning("Fallback to Firebase verification — remove after migration")
        return verify_firebase_session_cookie(token)
```

This allows the proxy to inject either token type during the transition.

### 11.2 Full Rollback

If migration fails:

1. **Revert `backend/auth.py`** to Firebase Admin SDK version (git revert)
2. **Revert `backend/requirements.in`** to include `firebase-admin`
3. **Revert `web/package.json`** to include `firebase` and `firebase-admin`
4. **Restore `web/src/firebase/` directory** from git history
5. **Restore Firebase environment variables**
6. **Keep Supabase database as-is** (it didn't change)

The rollback is low-risk because the data model (`users.auth_id` column) doesn't change — only the value stored in it changes. Firebase UIDs and Supabase user UUIDs are both storable as strings in `auth_id`.

---

## Appendix A: File Change Summary

### 🔴 Rewrite or Replace (10 files)

| File | Reason |
|------|--------|
| `backend/auth.py` | Replace Firebase Admin + verify_session_cookie with JWKS + local JWT verify |
| `web/src/providers/auth-provider.tsx` | Replace Firebase SDK with Supabase SDK throughout |
| `web/src/app/api/auth/session/route.ts` | Accept Supabase JWT, verify, set as cookie |
| `web/src/components/auth/login-form.tsx` | Replace Firebase signInWithEmailPassword with Supabase |
| `web/src/components/auth/signup-form.tsx` | Replace Firebase createUserWithEmailPassword with Supabase |
| `mobile/lib/features/auth/providers/auth_provider.dart` | Replace Firebase Auth with Supabase Auth |
| `mobile/lib/core/api/auth_interceptor.dart` | Replace Firebase token with Supabase access_token |
| `mobile/lib/main.dart` | Replace Firebase.initializeApp with Supabase.initialize |
| `tests/e2e/helpers.py` | Replace Firebase token gen with Supabase |
| `backend/scripts/generate_test_token.py` | Replace Firebase custom token with Supabase JWT |

### 🟡 Update (15 files)

| File | Change |
|------|--------|
| `backend/config.py` | Remove Firebase settings |
| `backend/main.py` | Remove initialize_firebase_app() |
| `backend/requirements.in` | Remove firebase-admin |
| `backend/dependencies.py` | Minor — update doc comments |
| `backend/api/users.py` | Update user sync for Supabase user ID |
| `backend/infrastructure/repositories/supabase_repository.py` | Rename find_by_firebase_uid → find_by_auth_id |
| `backend/application/services/watchlist_service.py` | Update to call find_by_auth_id |
| `backend/.env.example` | Remove Firebase vars |
| `web/package.json` | Remove firebase/firebase-admin, add @supabase/supabase-js |
| `web/src/lib/api.ts` | Minor import update |
| `web/src/features/auth/services/auth.service.ts` | Update user data extraction |
| `web/src/app/layout.tsx` | Remove FirebaseClientProvider |
| `web/.env.example` | Replace Firebase vars with Supabase vars |
| `mobile/pubspec.yaml` | Replace Firebase deps with Supabase deps |
| `tests/backend/test_auth.py` | Update mocks from Firebase to JWKS/JWT |

### 🟢 No Change (major files)

| File | Reason |
|------|--------|
| `web/src/app/api/proxy/[...path]/route.ts` | Already token-agnostic — just passes cookie as Bearer |
| `web/src/lib/csrf.ts` | No auth dependency |
| `web/src/lib/security-logger.ts` | No auth dependency |
| `web/src/features/auth/types/auth.types.ts` | User interface is provider-agnostic |
| `web/src/features/auth/services/token-manager.ts` | Just a callback registry |
| All backend API route files | Use `Depends(get_current_user_dep)` — injection point unchanged |
| `web/src/lib/firebase-admin.ts` | **Deleted** instead of modified |

### 🔴 Delete (15 files)

| File | Reason |
|------|--------|
| `web/src/lib/firebase-admin.ts` | Supabase has no server-side Admin SDK equivalent needed |
| `web/src/firebase/config.ts` | Replaced by `src/lib/supabase.ts` |
| `web/src/firebase/index.ts` | Replaced by `src/lib/supabase.ts` |
| `web/src/firebase/provider.tsx` | Supabase SDK is used directly |
| `web/src/firebase/client-provider.tsx` | Supabase SDK is used directly |
| `web/src/firebase/errors.ts` | Firestore-specific |
| `web/src/firebase/error-emitter.ts` | Firestore-specific |
| `web/src/firebase/non-blocking-login.tsx` | Firebase-specific |
| `web/src/firebase/non-blocking-updates.tsx` | Firestore-specific |
| `web/src/firebase/firestore/use-doc.tsx` | Firestore-specific |
| `web/src/firebase/firestore/use-collection.tsx` | Firestore-specific |
| `web/src/components/FirebaseErrorListener.tsx` | Firestore-specific |
| `mobile/lib/core/config/firebase_config.dart` | Supabase config is simpler |
| `firebase.json` | No longer using Firebase Hosting |
| `.firebaserc` | No longer using Firebase |
| `apphosting.yaml` | No longer using Firebase App Hosting |
| `firestore.rules` | No longer using Firestore |

### 🆕 Create (2 files)

| File | Purpose |
|------|---------|
| `web/src/lib/supabase.ts` | Client-side Supabase singleton (createBrowserClient) |

**Total: ~40 files changed, ~1,800 lines of auth code replaced.**

---

## Appendix B: Code Change Examples

### B.1 Backend Auth — Before vs After

**Before (`backend/auth.py`):**
```python
from firebase_admin import auth, credentials
import firebase_admin

def initialize_firebase_app():
    # 50 lines of Firebase Admin init logic
    # ...

def get_current_user(request: Request):
    token = extract_bearer(request)
    decoded_token = auth.verify_session_cookie(token, check_revoked=True)
    return decoded_token
    # HTTPS call to Firebase — 200-600ms
```

**After:**
```python
from jwt import decode as jwt_decode, get_unverified_header, PyJWKClient

_jwks_client = None

def get_current_user(request: Request):
    token = extract_bearer(request)
    global _jwks_client
    if not _jwks_client:
        _jwks_client = PyJWKClient(f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json")
    signing_key = _jwks_client.get_signing_key_from_jwt(token)
    decoded = jwt_decode(
        token, signing_key.key,
        algorithms=["RS256"],
        audience="authenticated",
        options={"require": ["exp", "sub"]}
    )
    return decoded
    # Local RSA — 80-150μs, no network
```

### B.2 Auth Provider — Before vs After

**Before (`auth-provider.tsx`):**
```typescript
import { onIdTokenChanged, signOut as firebaseSignOut } from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
const { auth } = initializeFirebase();

// onIdTokenChanged listener
onIdTokenChanged(auth, async (firebaseUser) => {
  const idToken = await firebaseUser.getIdToken();
  await fetch('/api/auth/session', { body: JSON.stringify({ idToken }) });
});

// Sign out
await firebaseSignOut(auth);
await clearSessionCookie();
```

**After:**
```typescript
import { createBrowserClient } from '@supabase/ssr';
const supabase = createBrowserClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
);

// onAuthStateChange listener
supabase.auth.onAuthStateChange(async (event, session) => {
  if (session) {
    await fetch('/api/auth/session', { body: JSON.stringify({ accessToken: session.access_token }) });
  }
});

// Sign out
await supabase.auth.signOut();
await clearSessionCookie();
```

### B.3 Login Form — Before vs After

**Before (`login-form.tsx`):**
```typescript
import { signInWithEmailAndPassword } from 'firebase/auth';
import { initializeFirebase } from '@/firebase';
const { auth } = initializeFirebase();

await signInWithEmailAndPassword(auth, email, password);
```

**After:**
```typescript
import supabase from '@/lib/supabase';

await supabase.auth.signInWithPassword({ email, password });
```

---

*End of document.*
