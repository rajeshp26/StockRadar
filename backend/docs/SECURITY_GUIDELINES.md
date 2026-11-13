# 🛡️ Security Guidelines & Implementation Status

This document outlines the security architecture of the StockerPro platform. It serves as both a guideline for best practices and a living document tracking the implementation status of key security features.

---

## 1. Authentication & Authorization

### A. Token Verification (Backend)
**STATUS: ✅ Implemented**

All protected endpoints verify the `Authorization: Bearer <ID_TOKEN>` header using the Firebase Admin SDK.

**Implementation Details:**
- A FastAPI dependency (`get_current_user_dep`) is used to extract and verify the token for most REST endpoints. The actual verification logic resides in `auth.py` and is injected at runtime in `main.py`.
- This dependency ensures that the user's `uid` is securely extracted from the decoded token, not from the request body.

### B. Identity Forwarding (Next.js Bridge)
**STATUS: ✅ Implemented**

The Next.js Proxy (`web/src/app/api/proxy/`) transparently forwards the `Authorization` header from the browser to the Python backend.

### C. Token Management (Frontend)
**STATUS: ✅ Implemented**

The frontend `api.ts` utility retrieves a fresh ID Token from Firebase before every authenticated request and attaches it to the headers.

---

## 2. Database Security: Supabase RLS

### A. Row-Level Security (RLS)
**STATUS: 🟡 In Progress / Partially Implemented**

While the application logic correctly filters data based on the authenticated user's `auth_id`, full Row-Level Security (RLS) policies at the database layer have not been enabled on all tables.

**Next Steps:**
- [ ] Enable RLS on all tables (`users`, `watchlists`, `watchlist_items`).
- [ ] Implement and apply policies that check `auth.uid()` against the user's `auth_id` on all `SELECT`, `INSERT`, `UPDATE`, and `DELETE` operations.

### B. Service Role vs. User Context
**STATUS: ✅ Implemented (via Strict Filtering)**

The Python backend currently operates with the `service_role` key but strictly enforces data access boundaries by filtering all database queries with a `WHERE` clause on the user's verified `auth_id`.

**Example (`backend/api/watchlists.py`):**
```python
items_res = supabase.table('watchlist_items') \
    .select('companies(ticker_symbol), watchlists(users(auth_id))') \
    .eq('watchlists.users.auth_id', auth_id) \
    .execute()
```
This approach effectively isolates user data, though it will be further enhanced by the RLS implementation.

---

## 3. Network & API Security

### A. CORS Policy
**STATUS: ✅ Implemented**

A strict CORS policy is enforced by the FastAPI backend.

**Implementation Details:**
- The `CORSMiddleware` is configured in `main.py`.
- Allowed origins are centrally managed in `config.py` and loaded based on the environment, ensuring only the frontend domains can communicate with the API.

### B. Rate Limiting
**STATUS: ✅ Implemented**

Basic rate limiting is in place to prevent abuse of API endpoints.

**Implementation Details:**
- The `slowapi` library is used.
- The limiter is configured in `main.py`, and for now, it keys off the client's IP address (`request.client.host`).

---

## 4. SSE (Server-Sent Events) Security
**STATUS: ✅ Implemented**

Since standard `EventSource` does not support custom headers, the real-time streaming endpoint is secured using a token-in-query-parameter mechanism.

**Implementation Details:**
1.  The frontend passes the user's Firebase ID Token as a query parameter: `/watchlists/stream?token=...`.
2.  The backend endpoint (`/api/watchlists/stream`) immediately verifies this token using `firebase_admin.auth.verify_id_token()` before establishing the persistent connection.

---

## 5. Implementation Roadmap (Archive)

This section archives the original implementation plan for historical reference.

### Phase 1: Infrastructure
- [X] Install `firebase-admin` in Python backend.
- [X] Implement `verify_firebase_token` dependency.
- [X] Update Frontend `api.ts` to attach tokens.
- [X] Update Next.js Bridge to forward headers.
- [X] Refactor `users/sync` and `watchlists` to use verified UID.

### Phase 2: Hardening
- [ ] Enable Supabase RLS.
- [X] Implement Rate Limiting (`slowapi`).
- [ ] Add Request Size validation.

### Phase 3: Monitoring & Secrets
- [ ] Implement Security Event Logging.
- [ ] Set up secret rotation for Supabase keys.
