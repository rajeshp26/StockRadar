# End-to-End Call Stack Analysis: `getDefaultWatchlist`

This document outlines the step-by-step analysis of the request flow for fetching a user's default watchlist, from the initial frontend trigger to the final backend database query.

**Conclusion:** The root cause of the error is a missing Axios interceptor in the frontend. This interceptor is responsible for attaching the Firebase authentication token to the API request header. Its absence causes the backend to reject the request as unauthenticated.

---

### **1. Frontend - The Hook (`useWatchlist.ts`)**

This is the origin of the request on the frontend.

*   **File:** `web/src/features/watchlists/hooks/useWatchlist.ts`
*   **Trigger:** A `useEffect` hook calls the `fetchWatchlist` function when the component mounts.
*   **Logic:**
    1.  It retrieves the `user` object from the `useAuth()` hook.
    2.  If the `user` exists, it calls `watchlistService.getDefaultWatchlist()`.
*   **Finding:** The call is made with **no arguments**. The user's ID is not explicitly passed at this stage.

---

### **2. Frontend - The Service (`watchlist.service.ts`)**

This layer abstracts the API call.

*   **File:** `web/src/features/watchlists/services/watchlist.service.ts`
*   **Trigger:** The `getDefaultWatchlist` method is called by the `useWatchlist` hook.
*   **Logic:**
    1.  It sends a `POST` request to the endpoint `/watchlists/default-with-items` with an empty JSON object `{}` as the body.
    2.  `return this.api.post<WatchlistWithItems>('/watchlists/default-with-items', {});`
*   **Finding:** A comment in the code explicitly states that the API client (Axios) is responsible for automatically attaching the user's ID token via an interceptor. This confirms the user's identity is expected to be in a request header, not the body.

---

### **3. Frontend - The HTTP Client (`api` object)**

This is the core component that configures how HTTP requests are made. The analysis shows this is the point of failure.

*   **File (`ServiceContext.tsx`):** `web/src/shared/contexts/ServiceContext.tsx`
    *   **Logic:** The `WatchlistService` is instantiated with an `api` object imported from `'@/lib/api'`.

*   **File (`tsconfig.json`):** `web/tsconfig.json`
    *   **Logic:** Defines the path alias `"@/*"` to map to `"./src/*"`. This means the import `'@/lib/api'` resolves to the file path `web/src/lib/api.ts`.

*   **File (`api.ts`):** `web/src/lib/api.ts`
    *   **CRITICAL FINDING:** This file is **empty**. The Axios instance and the crucial authentication interceptor, which should be defined here, are missing. This is the direct cause of the failure.

---

### **4. API Gateway / Proxy (`next.config.mjs`)**

The request from the frontend is proxied to the backend.

*   **File:** `web/next.config.mjs`
*   **Logic:** The configuration correctly rewrites requests from `/api/proxy/:path*` to the backend server at `http://127.0.0.1:8001/api/:path*`.
*   **Finding:** The proxy is working as expected.

---

### **5. Backend - The Endpoint (`watchlists.py`)**

This is the entry point for the request on the backend.

*   **File:** `backend/api/watchlists.py`
*   **Trigger:** A `POST` request to `/api/watchlists/default-with-items`.
*   **Logic:**
    1.  The endpoint requires a `User` object, which is provided by the `Depends(get_current_user)` dependency.
    2.  It then calls the service layer with the user's ID: `watchlist_service.get_default_watchlist_with_items(user.firebase_uid)`.
*   **Finding:** The backend log error `AttributeError: 'NoneType' object has no attribute 'firebase_uid'` confirms that the `get_current_user` dependency is returning `None`, because the request is unauthenticated.

---

### **6. Backend - The Authentication Dependency (`dependencies.py`)**

This is where the user's identity is verified from the request.

*   **File:** `backend/dependencies.py`
*   **Trigger:** Called by FastAPI for any endpoint that includes `Depends(get_current_user)`.
*   **Logic:**
    1.  It uses `HTTPBearer()` to extract the token from the `Authorization: Bearer <token>` header.
    2.  It attempts to verify the token using Firebase Admin SDK.
*   **Finding:** Because the frontend is not sending the `Authorization` header (due to the missing interceptor), this dependency fails to find a token, cannot verify a user, and returns `None`. This correctly triggers the error seen in the backend logs.
