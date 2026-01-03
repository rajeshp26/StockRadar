# 🛡️ Security Guidelines & Implementation Plan

## 🚩 Critical Vulnerability: Identity Propagation Trust
The current model where the backend trusts `firebase_uid` from request bodies is a **critical authentication bypass vulnerability**. This must be replaced with proper Token Verification.

---

## 1. Authentication & Authorization (CRITICAL)

### A. Token Verification (Backend)
All protected endpoints must verify the `Authorization: Bearer <ID_TOKEN>` header using the Firebase Admin SDK.

**Implementation Goal:**
- Use a FastAPI dependency to extract and verify the token.
- Extract the `uid` from the decoded token instead of the request body.

### B. Identity Forwarding (Next.js Bridge)
The Next.js Proxy must transparently forward the `Authorization` header from the browser to the Python backend.

### C. Token Management (Frontend)
The frontend `api.ts` must retrieve a fresh ID Token from Firebase before every request and attach it to the headers.

---

## 2. Database Security: Supabase RLS

### A. Row-Level Security (RLS)
We must move away from "Admin-level" database access. 
- Enable RLS on all tables (`users`, `watchlists`, `watchlist_items`).
- Use policies that check the `firebase_uid` against the authenticated user context.

### B. Service Role vs. User Context
The Python backend should either:
1.  Set the user context in the Supabase client for every request.
2.  Maintain strict `WHERE` clause filtering based on the verified `uid` from the token.

---

## 3. Network & API Security

### A. CORS Policy
Strictly limit allowed origins to the frontend production and development domains.
```python
allow_origins=["http://localhost:9002", "https://your-production-app.web.app"]
```

### B. Rate Limiting
Implement rate limiting to prevent:
- Brute-force ticker discovery.
- DoS attacks on the `yfinance` provider.
- Wallet/Database exhaustion.

---

## 4. SSE (Server-Sent Events) Security
Since standard `EventSource` does not support custom headers:
1.  The frontend will pass the ID Token via a short-lived query parameter: `/watchlists/stream?token=...`.
2.  The backend will verify this token **before** establishing the stream.

---

## 5. Implementation Roadmap

### 🔴 Phase 1: Infrastructure (Fix Today)
1. [ ] Install `firebase-admin` in Python backend.
2. [ ] Implement `verify_firebase_token` dependency.
3. [ ] Update Frontend `api.ts` to attach tokens.
4. [ ] Update Next.js Bridge to forward headers.
5. [ ] Refactor `users/sync` and `watchlists` to use verified UID.

### 🟡 Phase 2: Hardening (This Week)
1. [ ] Enable Supabase RLS.
2. [ ] Implement Rate Limiting (`slowapi`).
3. [ ] Add Request Size validation.

### 🟢 Phase 3: Monitoring & Secrets
1. [ ] Implement Security Event Logging.
2. [ ] Set up secret rotation for Supabase keys.
