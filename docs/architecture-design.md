# StockerPro — Architecture & Design

## 1. High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (Next.js App)                      │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │          Root Layout (layout.tsx)                           │  │
│  │  ┌─────────────┐ ┌──────────┐ ┌───────────────┐           │  │
│  │  │ReactQuery   │ │Auth      │ │ServiceProvider│  Toaster   │  │
│  │  │Provider     │ │Provider  │ │              │           │  │
│  │  └─────────────┘ └──────────┘ └───────────────┘           │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  (authenticated) layout                                     │  │
│  │  ┌──────────┐ ┌───────────────┐                             │  │
│  │  │  Header  │ │  GlobalSSE    │  Redirect-to-login guard    │  │
│  │  └──────────┘ └───────────────┘                             │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  Page <Outlet>                                       │   │  │
│  │  │  /dashboard    → Watchlist (WatchlistTab)            │   │  │
│  │  │  /portfolio    → PortfolioTabShell                   │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  /super-investors (standalone, NOT inside authenticated)    │  │
│  │  No auth guard, no header, no SSE.                          │  │
│  │  Still has AuthProvider from root layout.                   │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Proxy Route: /api/proxy/[...path]                          │  │
│  │  Reads __session cookie → Authorization header → Backend    │  │
│  │  CSRF: X-Requested-With required for POST/PUT/PATCH/DELETE  │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Auth Route: /api/auth/session                              │  │
│  │  Verifies Supabase JWT → Sets __session + __csrf cookies    │  │
│  └─────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP (via proxy)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Backend (FastAPI, port 8001)                    │
│                                                                  │
│  main.py                                                         │
│  ├── app.dependency_overrides[get_current_user_dep] = get_current│
│  │   (from auth.py)                                              │
│  ├── Mounted routers: super_investors, watchlists, watchlist_item│
│  │   portfolio, users, analysis, chat, stocks, valuations        │
│  └── CORS: allows BACKEND_ORIGIN + proxy Origin header           │
│                                                                  │
│  auth.py — JWT verification (HS256 secret or JWKS cache)        │
│  config.py — Settings from .env                                  │
│  dependencies.py — get_current_user_dep() placeholder            │
│                                                                  │
│  api/                                                            │
│  ├── super_investors.py  — public (no auth dep)                 │
│  ├── watchlists.py       — auth required (get_current_user_dep)  │
│  ├── watchlist_items.py  — auth required                         │
│  ├── portfolio.py        — auth required                         │
│  └── users.py            — auth required                         │
│                                                                  │
│  application/services/                                           │
│  ├── watchlist_service.py  — business logic                      │
│  └── portfolio_service.py  — business logic                      │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    Supabase (Postgres + Auth)
```

## 2. Auth Flow (BFF Cookie Pattern)

### 2.1 Login Sequence

```
Browser                     Next.js                       Backend          Supabase
  │                           │                              │                │
  │──signInWithPassword()─────┘                              │                │
  │                          (Supabase client-side SDK)      │                │
  │◄─────session + tokens────│                              │                │
  │                           │                              │                │
  │──persistSessionCookie(id_token)──► /api/auth/session     │                │
  │                           │──jwtVerify(token, SUPABASE_JWT_SECRET)──►(local)│
  │                           │◄──OK                         │                │
  │                           │──Set-Cookie: __session=...   │                │
  │                           │   HttpOnly; Secure; Path=/    │                │
  │                           │──Set-Cookie: __csrf=...       │                │
  │                           │                              │                │
  │──exchangeTokenForUser()──► /api/proxy/users/sync ────────► /users/sync   │
  │                           │  (reads __session cookie,     │                │
  │                           │   injects Authorization header)│               │
  │◄─────User profile─────────│◄───────User profile──────────  │                │
```

### 2.2 Subsequent API Calls

```
Browser                     Next.js Proxy (/api/proxy/[...path])   Backend
  │                           │                                      │
  │──GET /api/proxy/          │                                      │
  │   super-investors/        │                                      │
  │   overview                │                                      │
  │   Cookie: __session=...   │                                      │
  │                           │──extractToken() → reads __session    │
  │                           │──normalizeBearer() → "Bearer <jwt>"  │
  │                           │──fetch(BACKEND_ORIGIN + path, {      │
  │                           │    headers: { Authorization: ... }   │
  │                           │  })                                  │
  │                           │─────────────────────────────────────►│
  │                           │                    ┌─────────────────┤
  │                           │                    │ auth.py         │
  │                           │                    │ get_current_user│
  │                           │                    │ verifies JWT    │
  │                           │                    └─────────────────┤
  │                           │◄────────────────────────────────────┘
  │◄─────JSON response────────│                                      │
```

### 2.3 Auth Components

| File | Role |
|------|------|
| `web/src/app/api/auth/session/route.ts` | JWT verification, cookie set/clear |
| `web/src/app/api/proxy/[...path]/route.ts` | Cookie-to-header bridge + CSRF |
| `web/src/providers/auth-provider.tsx` | Auth context (status, user, session) |
| `web/src/features/auth/services/auth.service.ts` | `exchangeTokenForUser()` → `/users/sync` |
| `web/src/lib/api.ts` | Axios instance with CSRF interceptor |
| `backend/auth.py` | `verify_supabase_jwt()` → `get_current_user()` |
| `backend/dependencies.py` | `get_current_user_dep()` — placeholder (overridden) |
| `backend/config.py` | Settings (SUPABASE_JWT_SECRET, etc.) |

### 2.4 Proxy Route Details

- **File**: `web/src/app/api/proxy/[...path]/route.ts`
- **Cookie**: `__session` (configurable via `PROXY_IDTOKEN_COOKIE`)
- **Auth**: `PROXY_REQUIRE_AUTH=true` (default `false`, but set to `true` in `.env.local`)
- **CSRF**: Mutating methods (POST/PUT/PATCH/DELETE) require `X-Requested-With: XMLHttpRequest`
  - Axios instance (`api.ts`) sends this header automatically
  - Native `fetch()` calls must be wrapped to add this header
  - Super-investors service uses native `fetch` but only for GET endpoints → no CSRF issue
- **Extra token headers**: `PROXY_EXTRA_TOKEN_HEADERS=x-id-token,x-firebase-token` — reads these from request headers as auth fallbacks

### 2.5 CSRF Protection

- The proxy generates a `csrfToken` per request cycle
- For mutating methods: verifies `X-Requested-With: XMLHttpRequest` header
- For GET/HEAD/OPTIONS: no CSRF check
- The `__csrf` cookie is set by `/api/auth/session/route.ts` but is NOT verified by the proxy in the current implementation (only `X-Requested-With` header is checked)

### 2.6 Auth Configuration

- `NEXT_PUBLIC_SUPABASE_URL`: `https://viqdqgxcumcdhqxooplw.supabase.co`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Public anon key
- `SUPABASE_JWT_SECRET`: Symmetric HS256 key (same in frontend and backend `.env`)
- `BACKEND_ORIGIN`: `http://172.19.86.61:8001` — **NOT localhost** (remote IP)

## 3. Super Investors Feature (End-to-End)

### 3.1 Route & Layout

- **Page**: `web/src/app/super-investors/page.tsx`
- **URL**: `/super-investors`
- **Layout**: Standard — NOT inside `(authenticated)` route group
  - No `<Header />` rendered
  - No `<GlobalSSEProvider />` rendered
  - No auth guard redirect
  - DOES inherit `AuthProvider` from root layout
- **Component tree**: Root layout → page (no authenticated wrapper)

### 3.2 Data Flow

```
Browser (Client Component)             Next.js Proxy             Backend
  │                                     │                         │
  │──useQuery("superInvestorsOverview") │                         │
  │  └→ fetchSuperInvestorsOverview()  │                         │
  │       └→ doFetch("/api/proxy/      │                         │
  │            super-investors/         │                         │
  │            overview")              │                         │
  │    Cookie: __session=...           │──extractToken()          │
  │                                     │──fetch(BACKEND_ORIGIN + │
  │                                     │    "/super-investors/   │
  │                                     │     overview")          │
  │                                     │  Auth: Bearer <jwt>     │
  │                                     │────────────────────────►│
  │                                     │                         │──fetch all current quarter holdings ──► PostgreSQL
  │                                     │                         │──compute summary statistics
  │                                     │◄─── overview JSON ──────│
  │◄─── response ───────────────────────│                         │
```

### 3.3 Service Layer

**File**: `web/src/features/super-investors/services/super-investors-page.service.ts`

Uses native `fetch()` with `credentials: "include"` — NOT the Axios `api` instance.

**Functions**:
- `fetchSuperInvestorsOverview()` → `/api/proxy/super-investors/overview`
- `fetchTopStocks(quarter?, limit?)` → `/api/proxy/super-investors/top-stocks?quarter=X&limit=Y`
- `fetchOverlapData(quarter?, topN?, minWeight?)` → `/api/proxy/super-investors/overlap`
- `fetchActivityData(quarter?, minPurchase?)` → `/api/proxy/super-investors/activity`
- `fetchInvestors()` → `/api/proxy/super-investors/investors`
- `fetchInvestorByTag(tag)` → `/api/proxy/super-investors/investors/{tag}`
- `fetchSectorsData(quarter?)` → `/api/proxy/super-investors/sectors`

**Implementation detail**:
```typescript
async function doFetch<T>(path: string, params?: Record<string, string>): Promise<T> {
    const url = new URL(path, window.location.origin);
    if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    const res = await fetch(url.toString(), {
        credentials: "include",
        headers: { "Accept": "application/json" },
    });
    if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
    return res.json();
}
```

Key differences from Axios-based services:
- No `X-Requested-With` header (not needed for GET)
- No `Content-Type` (not sending body for GET)
- No retry interceptor
- No auth refresh logic
- Sends cookies via `credentials: "include"`

### 3.4 Type Definitions

**File**: `web/src/features/super-investors/types/super-investors-page.types.ts`

```typescript
export interface OverviewData {
    latest_quarter: string;    // e.g. "2025Q4"
    prev_quarter: string | null;  // Backend can return null
    total_investors: number;
    active_investors: number;
    total_holdings: number;
    new_positions: number;
    exited_positions: number;
    increased_positions: number;
    decreased_positions: number;
    total_value: number;
    sectors: SectorData[];
    top_stocks: TopStockData[];
    top_buys: TopStockData[];
    top_sells: TopStockData[];
    quarter_overview: QuarterOverview;
}
```

**Type mismatch issue**:
- `prev_quarter` is typed as `string` but the `_empty_overview()` endpoint returns `null` — components accessing `prev_quarter` should handle null.
- Backend returns `latest_quarter` as non-nullable string in `_empty_overview()` (it's `None`).

### 3.5 Page Component

**File**: `web/src/app/super-investors/page.tsx`

- **Client component** (`"use client"`)
- Fetches all top-level data with parallel `useQuery` calls:
  - `superInvestorsOverview` (stale: 5 min, gc: 30 min)
  - `topStocksData`
  - `overlapData`
  - `activityData`
  - `investorsData`
  - `sectorsData`
- **Tab-based UI**: Overview | Top Stocks | Overlap | Activity | Investors | Sectors
- Each tab passes pre-fetched data or uses its own query (e.g., `useTopStocksQuery` vs `overview.top_stocks`)
- `fmtPct(v, decimals)` helper: multiplies by 100 for display (`v * 100`)
- `barWidth = Math.round(stock.investor_breadth_pct * 100)` — already a 0-1 decimal from backend

**Potential issues**:
1. All queries fire on mount — if any fails, the whole page gets `allErrors` shown, but individual tabs could still work
2. No loading skeleton — minimal loading states
3. No auth guard — if `PROXY_REQUIRE_AUTH=true` and user is not logged in, all API calls return 401
4. The page renders even if all queries error out (error message shown vs redacted data)

### 3.6 Backend Endpoints

**File**: `backend/api/super_investors.py` (~1500 lines)

**Important**: ALL endpoints are PUBLIC — NONE use `Depends(get_current_user_dep)`.

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/super-investors/overview` | GET | Summary stats for latest quarter | ❌ None |
| `/super-investors/top-stocks` | GET | Top stocks by investor breadth | ❌ None |
| `/super-investors/overlap` | GET | Overlap analysis between top investors | ❌ None |
| `/super-investors/activity` | GET | Recent buys/sells activity | ❌ None |
| `/super-investors/investors` | GET | All tracked investors list | ❌ None |
| `/super-investors/investors/{tag}` | GET | Single investor detail | ❌ None |
| `/super-investors/sectors` | GET | Sector-level allocation | ❌ None |
| `/analysis/{symbol}/super-investors` | GET | Super investor positions in a symbol | ❌ None |
| `/analysis/{symbol}/super-investors/history` | GET | Historical positions for a symbol | ❌ None |

Since auth is NOT required at the backend, the proxy still enforces auth if `PROXY_REQUIRE_AUTH=true`. The token is injected by the proxy, and the backend's auth override will run if the route uses `get_current_user_dep`. However, since these routes don't use the auth dependency, the backend doesn't verify the token — it just processes the request.

**Key data flow**:
1. Fetches all rows from `current_quarter_holdings` (a view/materialized table)
2. Groups and aggregates in Python (pandas-like operations with plain dicts)
3. Computes: sector breakdowns, top stocks by investor breadth, overlap matrix, activity tracking

Performance concerns:
- No pagination or streaming — loads ALL rows for the latest quarter
- Overlap analysis does O(n²) comparisons between top investors
- Activity endpoint diffs between current and previous quarter holdings

## 4. Watchlist Feature (End-to-End)

### 4.1 Route & Layout

- **Page**: `web/src/app/(authenticated)/dashboard/page.tsx`
- **URL**: `/dashboard`
- **Layout**: Inside `(authenticated)` → Header + GlobalSSEProvider + auth guard + redirect to `/login` if unauthenticated

### 4.2 Data Flow

```
Browser                     Next.js Proxy          Backend
  │                           │                      │
  │──useWatchlist()           │                      │
  │  └→ watchlistService      │                      │
  │     .getAllWatchlists()   │                      │
  │       └→ api.get(         │                      │
  │          "/proxy/         │                      │
  │          watchlists")     │                      │
  │    Cookie: __session=...  │──extractToken()      │
  │                           │──fetch(BACKEND_ORIGIN│
  │                           │  + "/watchlists")    │
  │                           │  Auth: Bearer <jwt>  │
  │                           │─────────────────────►│
  │                           │                      │──get_current_user → verify JWT
  │                           │                      │──fetch user's watchlists
  │                           │◄── watchlists JSON ──│
  │◄── response ─────────────│                      │
```

### 4.3 Hooks & Services

**Hook**: `web/src/features/watchlists/hooks/useWatchlist.ts`
- Uses `useServices()` to get `watchlistService` from ServiceContext
- Query keys: `["watchlists"]`, `["watchlist-items", id]`
- Mutations: `useCreateWatchlist`, `useUpdateWatchlist`, `useDeleteWatchlist`
- Item mutations: `useAddWatchlistItem`, `useRemoveWatchlistItem`, `useToggleWatched`

**Service**: `web/src/features/watchlists/services/watchlist.service.ts`
- Class-based service wrapping Axios `api` instance
- Methods: `getAllWatchlists()`, `createWatchlist()`, `updateWatchlist()`, `deleteWatchlist()`, `getWatchlistItems()`, `addWatchlistItem()`, `removeWatchlistItem()`, `toggleWatched()`
- Axios interceptor adds `X-Requested-With: XMLHttpRequest` for all requests

**Axios Instance** (`web/src/lib/api.ts`):
```typescript
export const api = axios.create({
    baseURL: "/api/proxy",
    withCredentials: true,
    headers: { "X-Requested-With": "XMLHttpRequest" },
});
```

### 4.4 Backend

**File**: `backend/api/watchlists.py` — Uses `Depends(get_current_user_dep)`
**File**: `backend/api/watchlist_items.py` — Uses `Depends(get_current_user_dep)`
**File**: `backend/application/services/watchlist_service.py` — Business logic

### 4.5 SSE (Server-Sent Events)

**Provider**: `web/src/providers/GlobalSSEProvider.tsx`
- Single EventSource connection to `/api/proxy/watchlists/stream`
- Receives real-time price updates for all watched stocks
- Shares data via React Query cache updates

## 5. Portfolio Feature (End-to-End)

### 5.1 Route & Layout

- **Page**: `web/src/app/(authenticated)/portfolio/page.tsx`
- **URL**: `/portfolio`
- **Layout**: Inside `(authenticated)` → Header + GlobalSSEProvider + auth guard

### 5.2 Data Flow

Same pattern as Watchlist:
- Axios `api` instance → `/api/proxy/portfolio/*` → Backend
- Wire: `PortfolioTabShell` → hooks → `PortfolioService` → Axios → Proxy → Backend
- Backend requires `get_current_user_dep`

## 6. Identified Issues & Recommendations

### Issue 1: Super Investors Page is NOT Inside Authenticated Layout

**Problem**: `/super-investors` is at `web/src/app/super-investors/page.tsx` — a standalone route NOT under `(authenticated)` group. The authenticated layout provides:
- `<Header />` with navigation links (currently Watchlist, Portfolio)
- Auth guard (redirect to `/login` if not logged in)
- `<GlobalSSEProvider />` for live prices
- Shared styled layout wrapper

Without it, users visiting `/super-investors`:
- See no header/nav bar (no way to navigate back to dashboard)
- Are not redirected to login if unauthenticated
- API calls will fail with 401 if `PROXY_REQUIRE_AUTH=true`
- Have no SSE connection (though Super Investors doesn't need live prices)

**Fix**: Move `super-investors` page inside `(authenticated)` route group, or add the Header component to the super-investors page.

### Issue 2: Missing Navigation Link for Super Investors

**File**: `web/src/components/header.tsx:12-15`

```typescript
const navLinks = [
    { href: "/dashboard", label: "Watchlist" },
    { href: "/portfolio", label: "Portfolio" },
    // ❌ Missing: { href: "/super-investors", label: "Super Investors" },
];
```

**Fix**: Add the link. Users have no way to discover the Super Investors page.

### Issue 3: Super Investors Service Uses Native `fetch` Instead of Axios

**File**: `web/src/features/super-investors/services/super-investors-page.service.ts`

Uses native `fetch()` with `credentials: "include"`. While GET requests work fine (no CSRF check), this service is inconsistent with the rest of the codebase:
- No automatic `X-Requested-With` header
- No centralized error handling / auth refresh
- Manual URL construction

**Recommendation**: Either migrate to use the Axios `api` instance, or keep as-is since all super-investors endpoints are GET-only.

### Issue 4: Type Mismatch — `prev_quarter` Can Be Null

**File**: `web/src/features/super-investors/types/super-investors-page.types.ts:4`
```typescript
prev_quarter: string | null;  // Currently typed as `string`
```

Backend `_empty_overview()` returns `None` for `prev_quarter`. The type should be `string | null`. Components accessing `prev_quarter` must handle null.

### Issue 5: Backend Performance — No Pagination

**File**: `backend/api/super_investors.py`

The `/super-investors/overview` endpoint fetches ALL holdings for the latest quarter (potentially thousands of rows) and computes aggregates in Python. For large datasets:
- This can cause timeouts
- Memory pressure
- Slow initial page load

**Recommendation**: Add server-side pagination or streaming, or move aggregation to SQL queries.

### Issue 6: Auth — `BACKEND_ORIGIN` Points to Remote IP

**File**: `web/.env.local:6`
```
BACKEND_ORIGIN=http://172.19.86.61:8001
```

This is a raw IP address — likely a development server, Docker container, or WSL instance. If the IP changes, the proxy will break.

**Recommendation**: Use `http://localhost:8001` for local development, or ensure the IP is stable.

### Issue 7: Auth — `exchangeTokenForUser` Fires After Auth State Change But Only on Session Refresh

**File**: `web/src/providers/auth-provider.tsx:169-186`

The `persistSessionCookie` call is awaited, then `exchangeTokenForUser` runs in the background. However:

```typescript
if (isNewSession) {
    await persistSessionCookie(session.access_token);
}
```

If `isNewSession` is false (e.g., the user already has a session), the user profile is NOT synced with the backend. This is fine on initial auth, but post-refresh, the `__session` cookie must still be present (set during initial login).

Potential issue: on page refresh, if the cookie expires but the Supabase session is still valid in memory, `onAuthStateChange` fires with the existing session. Since `isNewSession` is false, the cookie is NOT re-set. If the old cookie has expired, subsequent proxy calls will fail with 401.

**Recommendation**: Re-set the `__session` cookie on every `onAuthStateChange` event (not just when `isNewSession` is true), or set a long cookie max-age.

### Issue 8: Super Investors Page Has No Loading States

The page fetches 6 parallel queries on mount but only shows a minimal loading state. If queries take a long time, the user sees a blank page. Consider skeleton loaders or progressive rendering.

### Issue 9: Proxy `extractToken()` Fallbacks

**File**: `web/src/app/api/proxy/[...path]/route.ts:57-74`

```typescript
async function extractToken(): Promise<string | null> {
    const jar = await cookies();
    const c = jar.get(PROXY_IDTOKEN_COOKIE)?.value;
    if (c) return normalizeBearer(c);
    // Fallbacks...
    const fallbacks = ["sb-access-token", "sb-refresh-token"];
    for (const name of [...fallbacks, ...EXTRA_TOKEN_HEADERS]) {
        const v = jar.get(name)?.value;
        if (v) return normalizeBearer(v);
    }
    return null;
}
```

The fallback tokens (`sb-access-token`, `sb-refresh-token`) are potentially dangerous — they're raw Supabase tokens. If used as Authorization headers, the backend would try to verify them with `SUPABASE_JWT_SECRET`. The `sb-access-token` is a Supabase session token (JWK-verified by Supabase), not the user's id_token. This would fail verification and cause auth errors.

**Recommendation**: Remove fallback tokens or ensure only the proper `__session` cookie (which stores the `id_token`) is used.

## 7. Missing Components

### Not Yet Implemented

| Component | Location | Status |
|-----------|----------|--------|
| Login page | `/login` | Not found in codebase |
| Register/Signup | `/register` | Not found in codebase |
| Password reset | `/reset-password` | Not found in codebase |
| Landing page content | `/` | Minimal — no hero/signup CTA |
| User settings | `/settings` | Not found in codebase |
| Error pages | `/error`, custom 404 | Not implemented |

### Auth flow gaps

The login flow relies entirely on Supabase Auth client-side SDK. There's no custom login page — users would need to use Supabase's built-in auth UI or a custom component that hasn't been created yet. The `auth-provider.tsx` handles the `onAuthStateChange` event correctly, but there's no visible login UI in the codebase.

## 8. Environment Configuration

### Frontend (.env.local)

| Variable | Value | Purpose |
|----------|-------|---------|
| `NEXT_PUBLIC_SUPABASE_URL` | `https://viqdqgxcumcdhqxooplw.supabase.co` | Supabase API endpoint |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `eyJ...` | Client-side anon key |
| `BACKEND_ORIGIN` | `http://172.19.86.61:8001` | Backend URL for proxy |
| `PROXY_IDTOKEN_COOKIE` | `__session` | Cookie name for auth JWT |
| `PROXY_EXTRA_TOKEN_HEADERS` | `x-id-token,x-firebase-token` | Fallback auth sources |
| `PROXY_REQUIRE_AUTH` | `true` | Require auth for all proxy requests |
| `SUPABASE_JWT_SECRET` | `4zPq...` | HS256 key for JWT verification |

### Backend (.env)

| Variable | Value | Purpose |
|----------|-------|---------|
| `SUPABASE_URL` | `https://viqdqgxcumcdhqxooplw.supabase.co` | Supabase API endpoint |
| `SUPABASE_SERVICE_ROLE_KEY` | `sb_secret_...` | Server-side admin key |
| `SUPABASE_JWT_SECRET` | `4zPq...` | HS256 key for JWT verification |
| `OPEN_ROUTER_KEY` | `sk-or-...` | AI chat API key |
| `OPEN_ROUTER_MODEL` | `openai/gpt-oss-120b:free` | AI model |
| `EDGAR_IDENTITY` | `StockerPro rajeshp01@gmail.com` | SEC EDGAR registration |
| `ENABLE_SUPER_INVESTORS_SCHEDULER` | `false` | Disable background scheduler |

## 9. Summary of Findings

### Super Investors Dashboard — Likely "Not Working" Reasons

1. **No nav link** → user cannot navigate to `/super-investors` from the UI
2. **No auth guard** → if not logged in with a valid `__session` cookie, `PROXY_REQUIRE_AUTH=true` blocks all API calls
3. **Auth cookie might not be propagating** → `persistSessionCookie` only runs on `isNewSession = true`; on page refresh, if the cookie expired, API calls fail
4. **No Header component** → no way to navigate back to dashboard
5. **Page is outside authenticated layout** → inconsistent UX

### Recommended Immediate Fixes (Priority Order)

1. Add `{ href: "/super-investors", label: "Super Investors" }` to header nav links
2. Move `/super-investors` inside `(authenticated)` route group OR add Header to the page
3. Fix `prev_quarter` type to `string | null`
4. Ensure `persistSessionCookie` runs on every auth state change (remove `isNewSession` check)
5. Consider migrating super-investors service to Axios for consistency
