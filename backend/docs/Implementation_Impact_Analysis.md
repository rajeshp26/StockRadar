# Implementation Impact Analysis Report
## StockerPro Authentication Architecture Redesign

**Document Version:** 1.0  
**Date:** 2026-04-14  
**Status:** Analysis Complete  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current State Assessment](#2-current-state-assessment)
3. [Gap Analysis: Design vs Implementation](#3-gap-analysis-design-vs-implementation)
4. [Impact Analysis by Component](#4-impact-analysis-by-component)
5. [Risk Assessment](#5-risk-assessment)
6. [Dependency Mapping](#6-dependency-mapping)
7. [Implementation Phasing](#7-implementation-phasing)
8. [Rollback Strategy](#8-rollback-strategy)

---

## 1. Executive Summary

### Problem Statement
The current authentication system has a fundamental design flaw: backend only accepts Firebase ID tokens (`verify_id_token()`), but `native fetch` and `EventSource` clients send session cookies, not Authorization headers.

### Current Behavior
| Request Type | Client | Auth Method | Result |
|-------------|--------|-------------|--------|
| POST | axios | Authorization header | ✓ 200 |
| GET | axios | Authorization header | ✓ 200 |
| GET | fetch | Cookie only | ✗ 401 |
| SSE | EventSource | Cookie only | ✗ 401 |

### Design Requirements
1. Backend must accept both ID tokens AND session cookies
2. Proxy must inject signed X-Verified-UID header for SSE
3. Backend must verify HMAC signature on X-Verified-UID
4. Backend must bind to private interface only

### Impact Summary
| Change Type | Files Affected | Impact Level | Effort |
|-------------|---------------|--------------|--------|
| Backend token verification | 1 | LOW | 1 hour |
| Proxy X-Verified-UID injection | 1 | MEDIUM | 2 hours |
| Backend HMAC verification | 1 | MEDIUM | 2 hours |
| Backend network binding | 1 | MEDIUM | 1 hour |
| SSE Redis Pub/Sub | 3+ | HIGH | 8+ hours |

---

## 2. Current State Assessment

### 2.1 Backend Authentication (`backend/auth.py`)

**Current Implementation:**
```python
def get_current_user(request: Request):
    # Path 1: X-Verified-UID (SSE only)
    verified_uid = request.headers.get("x-verified-uid")
    if verified_uid:
        if _is_trusted_proxy(request):  # Only IP check
            return {"uid": verified_uid, "sub": verified_uid}
        raise HTTPException(401)
    
    # Path 2: Bearer token
    token = auth_header[len("Bearer "):]
    decoded = auth.verify_id_token(token)  # ONLY accepts ID tokens!
    return decoded
```

**Key Observations:**
| Aspect | Current State |
|--------|---------------|
| ID Token verification | ✓ `verify_id_token()` |
| Session Cookie verification | ✗ NOT implemented |
| X-Verified-UID trust | IP-based only (`TRUSTED_PROXY_HOSTS`) |
| HMAC signature | ✗ NOT implemented |
| Timestamp validation | ✗ NOT implemented |

### 2.2 Proxy Route (`web/src/app/api/proxy/[...path]/route.ts`)

**Current Token Extraction:**
```typescript
// Lines 138-141
const tokenFromHeaders = extractTokenFromHeaders(request);  // Authorization header
const tokenFromCookies = await extractTokenFromCookies();    // __session cookie
const bearer = tokenFromHeaders ?? tokenFromCookies ?? null;
```

**Current Header Injection:**
```typescript
// Lines 122-123
if (bearer) headers.set("Authorization", bearer);
```

**Key Observations:**
| Aspect | Current State |
|--------|---------------|
| Authorization header extraction | ✓ Implemented |
| Cookie extraction | ✓ Implemented |
| X-Verified-UID for SSE | ✗ NOT implemented |
| HMAC signature | ✗ NOT implemented |
| UID extraction for SSE | ✗ NOT implemented |

### 2.3 SSE Implementation (`backend/api/watchlists.py`)

**Current Architecture:**
```python
# Global in-memory state (Lines 29-33)
user_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
symbol_subscribers: Dict[str, Set[str]] = defaultdict(set)
```

**Key Observations:**
| Aspect | Current State |
|--------|---------------|
| Subscription model | Symbol-based |
| Message delivery | In-memory asyncio queues |
| Multi-instance support | ✗ NOT supported |
| Redis Pub/Sub | ✗ NOT implemented |

### 2.4 Session Management (`web/src/app/api/auth/session/route.ts`)

**Current Cookie Config:**
```typescript
const cookieBase = {
  httpOnly: true,
  secure: isHttps,         // ← Issue: should be 'strict'
  sameSite: "lax" as const,  // ← Issue: should be 'strict' for financial app
  path: "/",
};
```

**Key Observations:**
| Aspect | Current State |
|--------|---------------|
| Cookie name | `__session` |
| HttpOnly | ✓ true |
| Secure | ✓ conditional |
| SameSite | `lax` (should be `strict`) |
| Expiration | 5 days |

---

## 3. Gap Analysis: Design vs Implementation

### 3.1 Authentication Flow Comparison

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    CURRENT vs REQUIRED AUTHENTICATION FLOW                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  CURRENT FLOW (BROKEN):                                                      │
│  ┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐          │
│  │ Browser │────▶│  Proxy    │────▶│  Backend  │────▶│ Firebase │          │
│  └─────────┘     └─────┬─────┘     └─────┬─────┘     └──────────┘          │
│       │                  │                │                                 │
│       │ Cookie            │ Forward as      │ verify_id_token()             │
│       │ (no header)       │ Bearer <cookie>│ FAILS! Session cookie          │
│       │                   │                │ not valid ID token             │
│       └──────────────────>│<───────────────│<─────────────────────────────  │
│                            │      401 Unauthorized                           │
│                                                                              │
│  REQUIRED FLOW (FIXED):                                                      │
│  ┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐          │
│  │ Browser │────▶│  Proxy    │────▶│  Backend  │────▶│ Firebase │          │
│  └─────────┘     └─────┬─────┘     └─────┬─────┘     └──────────┘          │
│       │                  │                │                                 │
│       │ Cookie            │ Forward as      │ Try verify_id_token()           │
│       │ (no header)      │ Bearer <cookie>│ If fails, try verify_session_ │
│       │                   │                │ cookie() ← NEW                 │
│       │                   │                │ Success!                       │
│       └──────────────────>│<───────────────│<─────────────────────────────  │
│                            │      200 OK                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Component Gap Matrix

| Component | Current | Required | Gap | Severity |
|-----------|---------|----------|-----|----------|
| **Backend Auth** | | | | |
| `verify_id_token()` | ✓ | ✓ | — | — |
| `verify_session_cookie()` | ✗ | ✓ | Add fallback | HIGH |
| HMAC verification | ✗ | ✓ | Not designed | HIGH |
| Timestamp validation | ✗ | ✓ | Not designed | MEDIUM |
| **Proxy Route** | | | | |
| Token extraction (headers) | ✓ | ✓ | — | — |
| Token extraction (cookies) | ✓ | ✓ | — | — |
| X-Verified-UID injection | ✗ | ✓ | Not implemented | HIGH |
| HMAC signing | ✗ | ✓ | Not implemented | HIGH |
| UID extraction | ✗ | ✓ | Not implemented | HIGH |
| **Backend Network** | | | | |
| Private interface binding | ✗ | ✓ | Not configured | HIGH |
| mTLS | ✗ | Optional | Not implemented | LOW |
| **SSE Architecture** | | | | |
| In-memory queues | ✓ | ✓ | — | — |
| Redis Pub/Sub | ✗ | ✓ | Not implemented | MEDIUM |
| **Session Cookie** | | | | |
| SameSite attribute | `lax` | `strict` | Change config | LOW |

---

## 4. Impact Analysis by Component

### 4.1 Backend Changes (`backend/auth.py`)

#### Change 1: Add `verify_session_cookie()` Fallback

**File:** `backend/auth.py`  
**Lines:** 117-120

**Current Code:**
```python
try:
    decoded_token = auth.verify_id_token(token)
    return decoded_token
except Exception as e:
    logger.error(f"Token verification failed: {e}")
    raise HTTPException(status_code=401, detail="Invalid or expired token")
```

**Required Change:**
```python
try:
    decoded_token = auth.verify_id_token(token)
    return decoded_token
except Exception:
    pass  # ID token failed, try session cookie

try:
    decoded_token = auth.verify_session_cookie(token, check_revoked=True)
    return decoded_token
except Exception as e:
    logger.error(f"Token verification failed: {e}")
    raise HTTPException(status_code=401, detail="Invalid or expired token")
```

**Impact:**
| Aspect | Impact |
|--------|--------|
| Backward compatibility | ✓ No breaking change |
| Existing axios calls | ✓ Continue to work |
| New fetch calls | ✓ Will now work |
| Error messages | May change slightly |
| Performance | +10-50ms for session cookie verification |

**Risk:** LOW - Adding fallback doesn't break existing functionality

---

#### Change 2: Add HMAC Signature Verification

**File:** `backend/auth.py`  
**Lines:** 31-35 (new function), 89-104 (modify)

**New Function Required:**
```python
import hmac
import hashlib
import base64
import time

PROXY_BACKEND_SECRET = os.getenv("PROXY_BACKEND_SECRET", "")
SIGNATURE_TTL_SECONDS = 300

def _verify_signed_uid(header_value: str) -> str | None:
    """Verify HMAC-signed X-Verified-UID header."""
    try:
        payload_b64, signature = header_value.split(".", 1)
        payload = base64.b64decode(payload_b64).decode()
        uid, timestamp_str = payload.split(":", 1)
        timestamp = int(timestamp_str)
        
        # Timestamp validation (5 minute TTL)
        if abs(int(time.time()) - timestamp) > SIGNATURE_TTL_SECONDS:
            return None
        
        # HMAC verification
        expected_sig = hmac.new(
            PROXY_BACKEND_SECRET.encode(),
            payload_b64.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(signature, expected_sig):
            return None
        
        return uid
    except:
        return None
```

**Impact:**
| Aspect | Impact |
|--------|--------|
| SSE authentication | Must be updated simultaneously |
| New dependency | `PROXY_BACKEND_SECRET` env var required |
| Configuration | Both proxy and backend must share secret |
| Rollback | Requires reverting proxy AND backend |

**Risk:** MEDIUM - Requires coordinated proxy/backend deployment

---

### 4.2 Proxy Changes (`web/src/app/api/proxy/[...path]/route.ts`)

#### Change 1: Add UID Extraction and HMAC Signing for SSE

**File:** `web/src/app/api/proxy/[...path]/route.ts`  
**Lines:** 66-83 (modify), 104-132 (modify)

**New Function Required:**
```typescript
import { createHmac } from 'crypto';

const PROXY_BACKEND_SECRET = process.env.PROXY_BACKEND_SECRET!;
const SIGNATURE_TTL_SECONDS = 300;

function signUID(uid: string): string {
  const timestamp = Math.floor(Date.now() / 1000);
  const payload = Buffer.from(`${uid}:${timestamp}`).toString('base64');
  const signature = createHmac('sha256', PROXY_BACKEND_SECRET)
    .update(payload)
    .digest('hex');
  return `${payload}.${signature}`;
}

function extractUIDFromSessionCookie(sessionCookie: string): string | null {
  try {
    const parts = sessionCookie.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString());
    return payload.uid;
  } catch {
    return null;
  }
}
```

**Modified buildUpstreamHeaders:**
```typescript
function buildUpstreamHeaders(
  req: NextRequest,
  bearer: string | null,
  isSSE: boolean,
  signedUID: string | null  // NEW parameter
): Headers {
  const headers = new Headers();
  // ... existing headers ...
  
  // Authorization header
  if (bearer) {
    headers.set("Authorization", bearer);
  }
  
  // X-Verified-UID with HMAC signature for SSE
  if (isSSE && signedUID) {
    headers.set("X-Verified-UID", signedUID);
  }
  
  return headers;
}
```

**Impact:**
| Aspect | Impact |
|--------|--------|
| Non-SSE requests | No change |
| SSE authentication | Requires new proxy logic |
| Configuration | `PROXY_BACKEND_SECRET` env var required |
| Backend must be updated | Simultaneously |

**Risk:** MEDIUM - SSE will fail until both proxy and backend updated

---

### 4.3 Network Configuration Changes

#### Change: Backend Private Interface Binding

**File:** `backend/main.py`  
**Lines:** Startup configuration

**Current:**
```python
# Likely using default (0.0.0.0) or unspecified
```

**Required:**
```python
uvicorn.run(
    app,
    host="127.0.0.1",  # Or private IP like "10.0.0.50"
    port=8001,
)
```

**Alternative: Docker Compose Configuration**
```yaml
# docker-compose.yml
services:
  backend:
    networks:
      - internal
    expose:
      - "8001:8001"

networks:
  internal:
    driver: bridge
    ipam:
      config:
        - subnet: 10.0.0.0/24
```

**Impact:**
| Aspect | Impact |
|--------|--------|
| Local development | May need adjustment |
| Production deployment | Depends on hosting |
| Cloud deployment | Firewall rules required |

**Risk:** MEDIUM - May break local development initially

---

### 4.4 SSE Architecture Changes (v2.0)

#### Redis Pub/Sub Implementation

**Files Affected:**
1. `backend/api/watchlists.py` - SSE endpoint
2. `backend/main.py` - Redis initialization
3. `docker-compose.yml` - Redis service (new)

**New Dependencies:**
```python
import redis.asyncio as redis
```

**Impact:**
| Aspect | Impact |
|--------|--------|
| Single-instance deployment | No change required |
| Multi-instance deployment | Major architectural change |
| Complexity | Significantly higher |
| Infrastructure | Redis service required |

**Risk:** HIGH - Major change, deferred to v2.0

---

## 5. Risk Assessment

### 5.1 Risk Matrix

| Risk | Likelihood | Impact | Mitigation | Owner |
|------|------------|--------|------------|-------|
| Session cookie verification breaks existing auth | LOW | HIGH | Test thoroughly | Backend |
| HMAC signature mismatch causes SSE failures | MEDIUM | MEDIUM | Deploy simultaneously | DevOps |
| Backend binding breaks local dev | MEDIUM | LOW | Document changes | DevOps |
| Redis Pub/Sub causes data loss | LOW | HIGH | Staged rollout | Backend |
| Environment variable missing | MEDIUM | HIGH | Default values + validation | DevOps |

### 5.2 Compatibility Analysis

#### Backward Compatibility
| Feature | Backward Compatible | Notes |
|---------|-------------------|-------|
| Backend token verification | ✓ | Adding fallback, not removing |
| Proxy header injection | ✓ | Only adds for SSE |
| Cookie configuration | ⚠️ | SameSite change may affect cross-origin |
| HMAC verification | ✓ | Only if PROXY_BACKEND_SECRET set |

#### Breaking Changes
| Change | Breaking | Migration Path |
|--------|----------|----------------|
| SameSite: 'strict' | ⚠️ | Users may need to log in again |
| Backend private binding | ⚠️ | Update startup scripts |
| Redis Pub/Sub | ✓ | v2.0 only |

---

## 6. Dependency Mapping

### 6.1 File Change Dependencies

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         IMPLEMENTATION DEPENDENCY GRAPH                        │
└─────────────────────────────────────────────────────────────────────────────┘

Phase 1: Backend Token Fallback (Hour 1)
├── backend/auth.py
│   └── Requires: Nothing (standalone)
└── Test: Verify GET requests work

Phase 2: Proxy X-Verified-UID (Hours 2-3)
├── web/src/app/api/proxy/[...path]/route.ts
│   └── Requires: PROXY_BACKEND_SECRET env var
├── backend/auth.py (modify X-Verified-UID handling)
│   └── Requires: Same secret as proxy
└── Test: SSE connections work

Phase 3: Network Hardening (Hour 4)
├── backend/main.py
│   └── Requires: Infrastructure config
├── docker-compose.yml (if applicable)
│   └── Requires: Network planning
└── Test: Local dev still works

Phase 4: Redis Pub/Sub (v2.0)
├── backend/api/watchlists.py
├── backend/main.py
├── docker-compose.yml
└── Test: Multi-instance deployments
```

### 6.2 Environment Variable Requirements

| Variable | Phase | Required For | Default |
|----------|-------|-------------|---------|
| `PROXY_BACKEND_SECRET` | 2 | Proxy + Backend HMAC | None (FAIL if missing) |
| `BACKEND_HOST` | 3 | Backend binding | `127.0.0.1` |
| `REDIS_HOST` | 4 | Redis Pub/Sub | `localhost` |

---

## 7. Implementation Phasing

### Phase 1: Backend Token Fallback (Quick Fix)
**Effort:** 1 hour | **Risk:** LOW | **Impact:** Fixes GET requests

```
Steps:
1. Backup current backend/auth.py
2. Add verify_session_cookie() fallback
3. Deploy to staging
4. Test with fetch-based requests
5. Deploy to production
6. Monitor error rates
```

**Verification:**
```bash
# Should now return 200
curl -H "Authorization: Bearer <session_cookie>" \
     http://localhost:8001/valuations/RBLX/rule1
```

---

### Phase 2: Proxy X-Verified-UID Injection
**Effort:** 2 hours | **Risk:** MEDIUM | **Impact:** Fixes SSE

```
Prerequisites:
- Phase 1 complete
- PROXY_BACKEND_SECRET generated and shared

Steps:
1. Backup current proxy/route.ts and backend/auth.py
2. Generate PROXY_BACKEND_SECRET (openssl rand -hex 32)
3. Update proxy: Add signUID(), extractUIDFromSessionCookie()
4. Update proxy: Inject X-Verified-UID for SSE
5. Update backend: Add _verify_signed_uid()
6. Update backend: Use signed header verification
7. Set PROXY_BACKEND_SECRET in both .env files
8. Deploy backend first
9. Deploy proxy second
10. Test SSE connection
11. Monitor both services
```

**Verification:**
- Browser DevTools → Network → Filter "watchlists/stream"
- Should see 200 status and SSE stream
- Should receive price_update events

---

### Phase 3: Network Hardening
**Effort:** 1 hour | **Risk:** MEDIUM | **Impact:** Security

```
Prerequisites:
- Phase 2 complete
- Infrastructure plan

Steps:
1. Update backend startup (uvicorn host parameter)
2. Update docker-compose.yml if applicable
3. Update firewall rules
4. Test local development
5. Test production deployment
6. Document configuration changes
```

**Verification:**
- Backend only accessible from proxy IP
- External direct access returns connection refused

---

### Phase 4: Redis Pub/Sub (v2.0)
**Effort:** 8+ hours | **Risk:** HIGH | **Impact:** Multi-instance support

```
Prerequisites:
- Phase 1-3 complete
- Redis infrastructure
- Load testing plan

Steps:
1. Add Redis to docker-compose.yml
2. Implement Redis Pub/Sub in watchlists.py
3. Add Redis health checks
4. Test single instance
5. Test multi-instance
6. Load test
7. Deploy to staging
8. Deploy to production
```

---

## 8. Rollback Strategy

### 8.1 Quick Rollback (Same Day)

| Phase | Rollback Steps | Time |
|-------|---------------|------|
| Phase 1 | Revert auth.py, redeploy | 5 min |
| Phase 2 | Revert proxy + auth.py, redeploy | 10 min |
| Phase 3 | Revert host binding, redeploy | 5 min |
| Phase 4 | Revert Redis changes, redeploy | 15 min |

### 8.2 Session Recovery

If issues persist after rollback:

```
1. Users may need to log out and log back in
2. Clear __session cookie from browser
3. Session cookie will be recreated on next login
4. No data loss - just re-authentication
```

### 8.3 Emergency Contacts

| Issue | Contact | Response Time |
|-------|---------|---------------|
| Backend auth failures | Backend team | 15 min |
| Proxy auth failures | Frontend team | 15 min |
| SSE connection failures | Frontend + Backend | 30 min |
| Infrastructure issues | DevOps | 1 hour |

---

## Appendix A: Code Change Reference

### A.1 Backend Auth Change (Phase 1)

```python
# backend/auth.py - Line 117-122 (modify)
# FROM:
try:
    decoded_token = auth.verify_id_token(token)
    return decoded_token
except Exception as e:
    logger.error(f"Token verification failed: {e}")
    raise HTTPException(status_code=401, detail="Invalid or expired token")

# TO:
# Try Firebase ID token first (short-lived)
try:
    decoded_token = auth.verify_id_token(token)
    return decoded_token
except Exception:
    pass  # ID token failed, try session cookie

# Try Firebase session cookie (long-lived)
try:
    decoded_token = auth.verify_session_cookie(token, check_revoked=True)
    return decoded_token
except Exception as e:
    logger.error(f"Token verification failed: {e}")
    raise HTTPException(status_code=401, detail="Invalid or expired token")
```

### A.2 Proxy X-Verified-UID (Phase 2)

```typescript
// web/src/app/api/proxy/[...path]/route.ts

// ADD: New imports and constants (top of file)
import { createHmac } from 'crypto';

const PROXY_BACKEND_SECRET = process.env.PROXY_BACKEND_SECRET ?? '';
const SIGNATURE_TTL_SECONDS = 300;

// ADD: Sign UID function
function signUID(uid: string): string {
  const timestamp = Math.floor(Date.now() / 1000);
  const payload = Buffer.from(`${uid}:${timestamp}`).toString('base64');
  const signature = createHmac('sha256', PROXY_BACKEND_SECRET)
    .update(payload)
    .digest('hex');
  return `${payload}.${signature}`;
}

// ADD: Extract UID from session cookie
function extractUIDFromSessionCookie(sessionCookie: string): string | null {
  try {
    const parts = sessionCookie.split('.');
    if (parts.length !== 3) return null;
    const payload = JSON.parse(Buffer.from(parts[1], 'base64').toString());
    return payload.uid;
  } catch {
    return null;
  }
}

// MODIFY: buildUpstreamHeaders signature and SSE handling
function buildUpstreamHeaders(
  req: NextRequest,
  bearer: string | null,
  isSSE: boolean,
  signedUID: string | null  // NEW parameter
): Headers {
  const headers = new Headers();
  // ... existing headers (Accept, Content-Type) ...
  
  // Authorization header
  if (bearer) {
    headers.set("Authorization", bearer);
  }
  
  // X-Verified-UID with HMAC signature for SSE
  if (isSSE && signedUID) {
    headers.set("X-Verified-UID", signedUID);
  }
  
  // ... existing proxy headers ...
  return headers;
}

// MODIFY: proxy() function
async function proxy(request: NextRequest, method: string, pathParts: string[]) {
  // ... existing code (lines 134-163) ...
  
  // ADD: Extract UID for SSE
  let signedUID: string | null = null;
  if (isSSE) {
    const sessionCookie = await cookies().then(j => j.get(PROXY_IDTOKEN_COOKIE)?.value);
    if (sessionCookie) {
      const uid = extractUIDFromSessionCookie(sessionCookie);
      if (uid) {
        signedUID = signUID(uid);
      }
    }
  }
  
  // MODIFY: Build headers with signedUID
  const upstreamHeaders = buildUpstreamHeaders(request, bearer, isSSE, signedUID);
  
  // ... rest unchanged ...
}
```

---

## Appendix B: Testing Checklist

### B.1 Pre-Deployment

- [ ] All code changes reviewed
- [ ] Environment variables configured
- [ ] Backups taken
- [ ] Rollback plan documented
- [ ] Team notified of maintenance window

### B.2 Post-Deployment (Phase 1)

- [ ] Watchlist loads (axios - existing behavior)
- [ ] GET /valuations/RBLX/rule1 returns 200
- [ ] GET /stocks/RBLX/quote returns 200
- [ ] No new 401 errors in logs

### B.3 Post-Deployment (Phase 2)

- [ ] SSE connection established (200)
- [ ] Price updates stream to dashboard
- [ ] No 401 errors on SSE endpoint
- [ ] HMAC signature verified in logs

### B.4 Post-Deployment (Phase 3)

- [ ] Local development still works
- [ ] Backend not accessible from external IP
- [ ] Proxy can still reach backend

---

*Document Version: 1.0*  
*Analysis Date: 2026-04-14*  
*Status: Ready for Implementation*
