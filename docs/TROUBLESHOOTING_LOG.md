# 📔 Troubleshooting Log: 502 Bad Gateway and 500 Internal Errors

## 🚩 Symptom
*   **Issue 1**: Frontend calls to `/api/proxy/...` return `502 Bad Gateway`.
*   **Issue 2**: Backend calls to `/watchlists/default-with-items` occasionally return `500 Internal Server Error` with `<ConnectionTerminated error_code:1...>` in logs.

## 🔍 Diagnostics Data
1.  **Issue 1 (502)**:
    *   Next.js Proxy (`src/app/api/proxy/[...path]/route.ts`) was configured to forward requests to `http://127.0.0.1:8001`.
    *   Backend (`start-backend.sh`) was starting Uvicorn on port `8000`.
    *   The "Bridge" (Next.js Proxy) could not connect to port 8001 because nothing was listening there.
2.  **Issue 2 (500)**:
    *   Logs showed: `[ERROR] get_default_watchlist_with_items: <ConnectionTerminated error_code:1, last_stream_id:9, additional_data:None>`.
    *   This is a known issue with `httpx` (used by the Supabase Python client) when interacting with certain HTTP/2 implementations where the connection is closed prematurely.

## ✅ Verified Fixes
1.  **Fix for 502**: Updated `start-backend.sh` to explicitly run Uvicorn on port `8001` to match the frontend proxy configuration.
    ```bash
    uvicorn main:app --app-dir backend --host 0.0.0.0 --port 8001 --reload
    ```
2.  **Fix for 500 (Potential)**: If the `ConnectionTerminated` error persists, the solution is to force the Supabase/httpx client to use HTTP/1.1 instead of HTTP/2. (Note: Currently monitoring; initial tests show successful recovery after port fix).

## 📝 Lessons Learned
*   Always verify the port mapping between the **Frontend Proxy** (the "Bridge") and the **Backend Service**.
*   In cloud workstation environments (like IDX), background processes might be started on different ports than expected if not explicitly managed in `dev.nix` or startup scripts.
