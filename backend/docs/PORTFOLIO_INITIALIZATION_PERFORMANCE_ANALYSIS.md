# Portfolio Page Initialization: Performance Analysis & Proposal

## Executive Summary

The portfolio page computes the same enriched holdings data **3× per page load** across 3 separate endpoints — accounts, overview, and holdings — each running `enrich_holdings_with_prices` independently. That means 3× the `current_market_data` queries, 3× the price enrichment, 3× the JSON serialization. In the typical case (~900ms for 50 holdings, 0 exchange-override) this is redundant but not catastrophic. But the architecture doesn't scale: any growth in holdings or accounts linearly increases the duplicated work, and exchange-override users hit 5–10s due to synchronous yfinance calls.

The solution is a single dashboard view-model endpoint (`/portfolio/dashboard`) with one enrichment pass, batched database queries (dividends, transactions), and deferred FIFO computation. Instrumentation is the first dependency — all priorities below are guesses until measured.

---

## Implementation Plan (Ordered)

1. **[15 min]** Add instrumentation (§8.1 timing decorator + §8.3 EXPLAIN ANALYZE) → P0-1
2. **[15 min]** CREATE INDEX on portfolio_dividends(account_id, fiscal_year) → P0-5
3. **[30 min]** Wrap yfinance in asyncio.to_thread() (§9.9) → P0-5
4. **[3 hrs]** Add batched repo methods: get_accounts_dividends_by_year, get_accounts_transactions (§9.1) → P0-2
5. **[1.5 days]** Build /portfolio/dashboard endpoint using batched methods + single enrichment + _compute_overview_from_holdings (§9.4) → P0-3
6. **[30 min]** Frontend: prefetch on hover targeting dashboard endpoint (§9.3) → P0-4a
7. **[15 min]** Frontend: remove serial loading in PortfolioTabShell (§9.6) → P0-4a
8. **[1 day]** Frontend: wire PortfolioTabShell to usePortfolioDashboard hook, deprecate individual calls on initial load (§9.6) → P0-4b
9. **[30 min]** Lazy performance chart (IntersectionObserver) (§9.7) → P1
10. **[Measure]** If performance chart >2s, add lazy cache (§9.5)

**Dependencies:** 4 → 5 → 7 → 8. Items 1, 2, 3 are independent and can start immediately.

---

## 1. Page Transition Sequence (Current State)

### Watchlist → Portfolio Navigation

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. User clicks "Portfolio" in nav (header.tsx:14)              │
│ 2. Next.js App Router: /dashboard → /portfolio                 │
│ 3. (authenticated)/layout.tsx mounts GlobalSSEProvider         │
│    (SSE stays connected, no new connection needed)             │
│ 4. portfolio/page.tsx renders PortfolioTabShell                │
│ 5. PortfolioTabShell triggers usePortfolioAccounts()           │
│ 6. PortfolioTabShell shows loading skeleton                    │
│ 7. On data: renders OverviewTab → triggers N more queries      │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Full API Call Waterfall (Initial Page Load)

### Phase 1 — `PortfolioTabShell` (Serial)

| # | Call | Endpoint | Backend Work |
|---|------|----------|-------------|
| **1** | `usePortfolioAccounts()` | `GET /portfolio/accounts` | Fetches accounts; **for each account**: fetches holdings + enriches with prices (2 batch queries: `current_market_data` + `price_history`) |

### Phase 2 — `OverviewTab` (Fires in parallel after Phase 1)

| # | Call | Endpoint | Backend Work |
|---|------|----------|-------------|
| **2** | `usePortfolioOverview(accountIds)` | `GET /portfolio/overview` | Fetches ALL holdings (1 query) + companies enrichment (1 query) + current_market_data batch (1 query) + price_history fallback (1 query) + **dividends per account** (N queries) |
| **3** | `useAllHoldings()` | `GET /portfolio/holdings` | Fetches ALL holdings (1 query) + companies enrichment (1 query) + current_market_data batch (1 query) + price_history fallback (1 query) |

### Phase 3 — `PortfolioPerformanceChart` (Fires in parallel after Phase 2)

| # | Call | Endpoint | Backend Work |
|---|------|----------|-------------|
| **4** | `usePortfolioPerformance('1Y')` | `GET /portfolio/performance?period=1Y` | Transactions per account (N queries) + paginated price_history (1+ queries) + CPU-intensive FIFO lot calculation O(n*m) |
| **5** | `useBenchmarks()` | `GET /benchmarks` | Single query to `benchmark_config` |

### Total Database Roundtrips (3–5 accounts)

| Operation | `portfolio_accounts` | `portfolio_holdings` | `companies` | `current_market_data` | `price_history` | `portfolio_transactions` | `portfolio_dividends` | **Total** |
|-----------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| `/accounts` | 1 | N (per account) | — | 1 | 1 | — | — | **3+N** |
| `/overview` | — | 1 | 1 | 1 | 1 | — | N | **4+N** |
| `/holdings` | — | 1 | 1 | 1 | 1 | — | — | **4** |
| `/performance` | — | — | — | — | paginated | N | — | **N+** |
| **Total** | **1** | **2+N** | **2** | **3** | **3+** | **N** | **N** | **~15–25+** |

---

## 3. Root Causes of Slowness

### Issue 1: N+1 Queries Everywhere

Three different code paths iterate accounts individually instead of batching:

**A. Account enrichment** (`backend/api/portfolio.py:166-172`):
```python
for acc in accounts:
    holdings = await service.enrich_holdings_with_prices(
        repo.get_account_holdings(acc["account_id"])  # N queries
    )
```

**B. Dividend query** (`backend/application/services/portfolio_service.py:1122-1128`):
```python
for account in accounts:
    account_divs = self.portfolio_repo.get_account_dividends_by_year(
        account["account_id"], current_year  # N queries
    )
```

**C. Transaction query** (`portfolio_service.py:1769-1771`):
```python
for aid in account_ids:
    txns = self.portfolio_repo.get_account_transactions(aid, ...)  # N queries
```

### Issue 2: Redundant Work — Same Data Fetched 3–4 Times

| Data | Fetched By | Redundancy |
|------|-----------|-----------|
| Full holdings list | `/accounts` (per account), `/overview`, `/holdings` | **3×** |
| `current_market_data` prices | `/accounts`, `/overview`, `/holdings` | **3×** |
| `price_history` fallback | `/accounts`, `/overview`, `/holdings`, `/performance` | **3–4×** |
| Company info | `/overview` (via `_get_holdings`), `/holdings` (via `_get_holdings`) | **2×** |

### Issue 3: `/portfolio/accounts` Does Expensive Enrichment It Doesn't Need

The accounts endpoint only needs `holdings_count` and `total_value` — but it fetches the full holdings list and enriches every holding with market prices (2 batch queries + per-account holdings query). These could be replaced with a single aggregate SQL query.

### Issue 4: CPU-Intensive FIFO Performance Calculation

`get_portfolio_performance()` (`portfolio_service.py:1736-1915`):
- Fetches all trade transactions (N queries)
- Downloads all `price_history` for the period (paginated)
- Rebuilds FIFO lots from scratch for all pre-period transactions
- Computes daily snapshots O(n*m)

This runs on **every page load** with no caching layer. There's no pre-computed performance table being used.

### Issue 5: Serial Frontend Waterfall

`PortfolioTabShell.tsx:39-47` blocks rendering of all tab content until `usePortfolioAccounts()` resolves:
```tsx
if (accountsLoading) {
    return <Skeleton />;
}
```

The resolution of accounts triggers `OverviewTab` mount, which triggers `usePortfolioOverview` and `useAllHoldings`, which in turn trigger performance chart queries. This creates a strict serial chain.

### Issue 6: React Query Cache Is Warmed Only on First Visit

- **Watchlist** can use SSR with `initialData` hydration
- **Portfolio** has no server-side prefetching
- `staleTime: 2 min` means every navigation back to portfolio within 2 min is instant, but the **first navigation** from dashboard always pays full cost
- No `prefetchQuery` in the router or link hover handlers

### Issue 7: Auth Resolution Adds Latency

Every portfolio endpoint calls `_resolve_db_user_id(auth_id)` which does a `users` table lookup. While `_resolve_user` has an in-memory cache (after first call), each endpoint still incurs this on first invocation during the waterfall. **However, this is likely negligible (~3ms) compared to enrichment-heavy code paths (hundreds of ms).** Marked as lower priority — optimize only if measurement identifies it as an outlier.

### Issue 8: Missing Database Indexes (One of Five Proposed Is Actually Missing)

**Problem:** Even with batched queries (`in_` filter), the underlying PostgreSQL queries may do sequential scans. A codebase audit (see §7.1) checked all five proposed indexes against actual schema:

| Table | Proposed Index | Audit Result |
|-------|---------------|-------------|
| `portfolio_holdings` | `(account_id)` | **Already covered.** UNIQUE constraint on `(account_id, company_id)` provides leading-column index. |
| `portfolio_transactions` | `(account_id, transaction_date)` | **Already covered.** `uq_transaction_fingerprint` partial unique index has these as leading columns. |
| `portfolio_dividends` | `(account_id, fiscal_year)` | **Genuinely missing.** No index beyond PK on `dividend_id`. |
| `current_market_data` | `(company_id)` | **Already covered.** PK on `(company_id)`. |
| `price_history` | `(company_id, price_date)` | **Already covered.** PK on `(company_id, price_date)` + `idx_price_history_company_date_desc`. |

**Impact:** The `portfolio_dividends` table lacks an index on `(account_id, fiscal_year)`, so the per-account dividend query in `get_user_portfolio_overview()` and dividend dashboard endpoints hits a sequential scan. For a user with many dividend records, this adds measurable latency. However, the other four proposed indexes already exist, so indexing is not the dominant bottleneck the original analysis assumed.

---

## 4. Impact Assessment

> **⚠️ Important note on estimates:** The "Current State" values below span a wide range because latency depends heavily on data volume (number of holdings, transaction count, exchange-override symbols hitting yfinance) and network conditions. The timing budget in §7.7 gives a per-component breakdown. **These are hypotheses until measured.** See §8 for the measurement plan.

| Factor | Typical Case (50 holdings, 0 exchange-override) | Worst Case (150 holdings, 10 exchange-override, ALL period) | Target |
|--------|:---:|:---:|:---:|
| API calls on load | 5 | 5 | 1–2 |
| Database roundtrips | 15–25 | 30–50+ | 3–6 |
| Backend compute | FIFO ~150ms | FIFO ~2s + yfinance ~5s blocking | Lazy-loaded or cached |
| First-load time (est.) | **~900ms** | **5–10s** | **< 1.5s (typical)** |
| Cache hit (subsequent, within 5 min) | ~instant | ~instant | ~instant |

**3–8s claim in earlier drafts conflated typical and worst-case. The worst-case is dominated by synchronous yfinance calls (see §7.5 async-blocking note).**

---

## 5. Proposed Solution

### A. Frontend — Enable Speculative Prefetching (1 day — includes endpoint wiring)

1. **Prefetch on link hover** — Use TanStack Query's `queryClient.prefetchQuery()` in the `Header` nav link's `onMouseEnter` to warm the accounts cache before the user even clicks.
2. **Remove serial blocking** — Make `PortfolioTabShell` render children immediately with the accounts data being optional (show account chip once resolved, but render tabs immediately).
3. **Defer non-critical queries** — Move benchmark loading and performance chart to `lazy` or use `enabled` flags that only fire when the chart enters the viewport (IntersectionObserver pattern).

### B. Backend — Eliminate N+1 and Redundant Queries (4–5 days)

1. **Fix `/portfolio/accounts` enrichment** — Replace the per-account loop with a single holdings query + single price enrichment batch. Or better: use a simple aggregate SQL query to get `holdings_count` and `total_value` directly.

2. **Add backend data cache layer** — Cache the FIFO performance snapshots with an invalidation trigger on new transactions. This is the single biggest compute cost.

3. **Batch dividend queries** — Replace per-account dividend fetching with `in_("account_id", account_ids)` batch query.

4. **Batch transaction queries** — Replace per-account transaction fetching with `in_("account_id", account_ids)` batch query.

5. **Share price enrichment across requests** — Use a module-level TTL cache for `current_market_data` lookups (they're minute-level data anyway). See §9.2.

### C. Architecture — Restructure Data Flow (5–7 days)

1. **Introduce a `/portfolio/dashboard` bundle endpoint** — A single endpoint that returns accounts, overview, and holdings in one roundtrip. This eliminates 3 of the 5 API calls.

2. **Pre-compute performance snapshots** — Either via the existing `portfolio_performance` table (write on transaction import) or a scheduled background job. Remove the on-demand FIFO rebuild.

3. **Add React Query SSR hydration** — Use Next.js server components or `prefetchQuery` in the layout to hydrate the React Query cache before the client renders.

### D. Quick Wins (Can Ship in 1–2 Days)

1. **Add missing index on `portfolio_dividends(account_id, fiscal_year)`** — 15-minute migration, single `CREATE INDEX CONCURRENTLY` statement
2. **Batch the dividend query** in `get_user_portfolio_overview` — single `in_` query instead of N per-account queries
3. **Batch the transaction query** in `get_portfolio_performance` — single `in_` query instead of N per-account queries
4. **Add `prefetchQuery` on portfolio link hover** — zero-cost warm-up of the accounts cache
5. **Remove serial loading in PortfolioTabShell** — render tabs immediately, pass `undefined` accountIds

---

## 6. Recommended Priority Order

**Key change from prior drafts:** The dashboard view model is now the central P0 deliverable, and the batched repository methods are framed as its prerequisites (not independent tasks). Without batched dividend/transaction queries, the dashboard endpoint still does per-account loops internally — defeating the purpose. See the explicit dependency chain below.

### Dependency Map

```
P0-1 (measure) ─┬─→ P0-2 (batched repos) ──→ P0-3 (dashboard endpoint) ──→ P0-4 (frontend wiring)
                 │
                 └─→ P0-5 (index, yfinance fix) — independent, parallel
```

| Priority | Task | Effort | Impact | Depends On | Category |
|----------|------|--------|--------|------------|----------|
| **P0-1** | **Instrument everything** (endpoint timing, query tracing, yfinance latency) | **0.5 day** | **Prerequisite** | — | **Backend** |
| **P0-2** | **Batch dividend + transaction queries** in repository layer | **3–4 hrs** | **High** | P0-1 | **Backend** |
| **P0-3** | **Portfolio Dashboard View Model** (single endpoint, single enrichment, uses batched queries) | **1.5 days** | **Very High** | P0-2 | **Backend** |
| **P0-4a** | **Frontend: prefetch on hover + remove serial blocking** | **45 min** | **High** | P0-3 | **Frontend** |
| **P0-4b** | **Frontend: wire PortfolioTabShell to dashboard hook, deprecate old initial calls** | **1 day** | **High** | P0-4a | **Frontend** |
| **P0-5** | **Add `idx_portfolio_dividends_account_year` + wrap yfinance in `asyncio.to_thread()`** | **45 min** | **High for exchange-override users** | — | **Backend** |
| P1 | Lazy performance chart (IntersectionObserver) | 30 min | Medium | — | Frontend |
| P1 | N+1 fixes in individual endpoints (accounts, overview, holdings) | 2–4 hrs | Medium | P0-2 | Backend |
| P1 | Module-level TTL cache for market data | 1 hr | Medium | P0-3 | Backend |
| P2 | SSR hydration for portfolio data | 1-2 days | Medium | P0-3 | Fullstack |
| P2 | FIFO lazy cache (10-min TTL with invalidation on import) | 0.5 day | Low-Medium | P1 chart | Backend |
| P3 | Redis cache (if multi-instance) | 1 day | Low-Medium | — | Infrastructure |
| P3 | Materialized view for account summaries | 1-2 days | Medium | — | Backend |

**Why N+1 fixes for individual endpoints are now P1:** The dashboard endpoint replaces the three separate endpoints for initial page load. The individual endpoints still need batch queries for tab-switching and deep-link scenarios, but they're no longer on the initial-render critical path.

### Success Metrics

```
Primary:    enrich_holdings_with_prices calls per page load: 3 → 1
Secondary:  current_market_data queries per page load:      3 → 1
Tertiary:   Database roundtrips on first load:             15-25 → 3-6
Guard:      FIFO compute on first load:                    present → deferred
```

### Endpoint Lifecycle

| Endpoint | After Dashboard Ships | Rationale |
|----------|----------------------|-----------|
| `GET /portfolio/dashboard` | **New** — initial page load only | Single enrichment pass, one call |
| `GET /portfolio/accounts` | **Kept** — used by account detail pages, deep links | Different consumer; N+1 fixes still beneficial |
| `GET /portfolio/overview` | **Kept** — used by tab refresh, standalone overview links | Still needed independently |
| `GET /portfolio/holdings` | **Kept** — used by holdings tab with filters/sort | Dashboard returns summary only |
| `GET /portfolio/performance` | **Kept** — loaded lazily by chart | Already deferred; no change needed |

The old endpoints remain operational during the transition. The frontend replaces only the initial-load calls with the dashboard endpoint; tab-switching and deep links continue using individual endpoints. This means the N+1 fixes in individual endpoints (§9.1) are still worthwhile but at P1 priority.

---

## 7. Impact & Feasibility Analysis

This section validates which proposed changes are actually impactful (based on codebase audit) and which are feasible shifts.

### 7.1 Codebase Audit Results

Before theorizing further, the following were verified against the actual code:

| Audit Item | Finding | Source |
|-----------|---------|--------|
| **Supabase client singleton** | **Already exists.** `database.py` uses `_LazySupabaseProxy` → `get_supabase()` creates exactly one `_client` globally. `PortfolioRepository.__init__` uses this singleton. | `backend/database.py:15-38` |
| **`portfolio_holdings` index** | **Already covered.** UNIQUE constraint on `(account_id, company_id)` provides an index on leading column `account_id`. Proposed `idx_portfolio_holdings_account` is redundant. | `backend/docs/PORTFOLIO_DESIGN.md:190-210` |
| **`portfolio_transactions` index** | **Already covered.** `uq_transaction_fingerprint` partial unique index covers `(account_id, transaction_date, ...)`. Proposed `idx_portfolio_transactions_account_date` is redundant. | `backend/scripts/migrate_portfolio_transactions_unique.sql:10-13` |
| **`current_market_data` index** | **Already covered.** PK on `(company_id)`. Proposed index is a no-op. | `backend/docs/Supabase_Schema.md:723-737` |
| **`price_history` index** | **Already covered.** PK on `(company_id, price_date)` **and** `idx_price_history_company_date_desc` descending index already exists. Proposed index is duplicate. | `backend/docs/Supabase_Schema.md:916-930` |
| **`portfolio_dividends` index** | **Genuinely MISSING.** PK on `(dividend_id)` only. No index on `(account_id, fiscal_year)`. **This is the only missing index of the five proposed.** | `backend/docs/PORTFOLIO_DESIGN.md:218-230` |
| **No existing performance instrumentation** | Zero timing/logging decorators exist on any portfolio service or repository method. | Grep: `PERF\|timing\|elapsed` in `backend/application/services/` |
| **YFinanceProvider blocks event loop** | `get_stock_details()` uses synchronous `yf.Ticker()` → HTTP requests inside an async context. Called for exchange-override holdings in `enrich_holdings_with_prices`. | `backend/providers/yfinance_provider.py:54-113` |
| **API proxy adds overhead** | Every portfolio request goes through Next.js API proxy (`route.ts`) which adds ~2-5ms per hop plus `cookies()` async resolution. 5 endpoints = ~10-25ms proxy overhead. | `web/src/app/api/proxy/[...path]/route.ts:132-224` |

### 7.2 Revised Index Strategy (Replaces Section 11)

Of the five proposed indexes, **only one is actually needed**:

```sql
-- THE ONLY MISSING INDEX:
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_dividends_account_year
    ON portfolio_dividends (account_id, fiscal_year);
```

The other four proposed indexes are already covered by existing constraints or primary keys. The original analysis (§3 Issue 8) should have verified against actual schema before recommending all five.

**Feasibility:** Adding this single index is a 15-minute migration with zero risk. `CREATE INDEX CONCURRENTLY` doesn't lock the table in PostgreSQL 12+.

### 7.3 N+1 Query Elimination: Feasibility

| Query Pattern | Feasibility | Effort | Risk |
|--------------|-------------|--------|------|
| **Dividend query** (`get_account_dividends_by_year` in a loop) | **Straightforward.** Add `get_accounts_dividends_by_year()` batching method in `portfolio_repository.py`. Replace loop in `get_user_portfolio_overview()`. | 2-3 hours | Low |
| **Transaction query** (`get_account_transactions` in a loop) | **Straightforward.** Same pattern — batch method replacing the per-account loop in `get_portfolio_performance()` and `_get_cashflow_deltas()`. | 2-3 hours | Low |
| **Account enrichment** (`enrich_holdings_with_prices` per account in `/portfolio/accounts`) | **Moderate.** The account endpoint fetches holdings per account to compute `holdings_count` and `total_value`. These can be derived from a single batch query + enrich call. The `/portfolio/dashboard` bundle endpoint eliminates this entirely. | 4-6 hours | Low-Medium |

**Feasibility verdict:** All three N+1 patterns are low-risk, well-understood refactors following existing code patterns.

### 7.4 Redundant Enrichment Elimination: Feasibility

**Problem:** `enrich_holdings_with_prices` is called 3+ times per page load.

**Reality check:** The three call sites are in **different API endpoints** (`/accounts`, `/overview`, `/holdings`). A single-request cache (as proposed in §9.2) won't help because these are separate HTTP requests.

**What actually works:**
1. **Bundle endpoint** (`/portfolio/dashboard`): Single HTTP request, single `enrich_holdings_with_prices` call, data shared across response sections. **Very high impact.**
2. **Module-level TTL cache** (`market_cache.py`): Helps when the same user hits multiple endpoints in quick succession (e.g., tabs). **Moderate impact** — 30s TTL means the `/overview` call 50ms after `/accounts` can skip the DB query.

**Feasibility verdict:** The bundle endpoint is the correct solution. The module-level cache is a worthwhile complement but not a replacement.

### 7.5 FIFO Pre-computation: Feasibility

**Actual complexity analysis** (from `_compute_fifo_snapshots` at `portfolio_service.py:1608-1709`):

| Factor | 1Y Period | ALL Period |
|--------|-----------|------------|
| Snapshot dates (D) | ~52 (7-day step) | ~300+ (30-day step) |
| Holdings (H) | User-dependent | User-dependent |
| Price history entries (P) | ~252 trading days | ~1000+ days |
| Lot count | Sum of `(account, symbol)` pairs | Same |
| **Internal complexity** | D × H × P iterations with `sorted()` call per symbol per date | Same (scales) |

**Key inefficiency:** For each snapshot date, the algorithm iterates over ALL holdings and for each holding calls `sorted(price_map_for_sym.keys())` to find the nearest historical price. This sorts the same keys on every iteration. An O(P) scan per holding per date instead of O(P log P) would be significantly faster for large portfolios.

**Is this the bottleneck?** For small portfolios (<30 holdings): **No.** The algorithm completes in <100ms. For large portfolios (>100 holdings with 5+ years of data): **Potentially.** The inner loop does millions of iterations.

**Async-blocking note:** `enrich_holdings_with_prices()` calls `YFinanceProvider.get_stock_details()` for any holding with `exchange_override` (e.g., Canadian-listed stocks). That method (`yfinance_provider.py:54`) uses **synchronous** `yf.Ticker()` — an HTTP call to Yahoo Finance — inside an `async def` context. This blocks the entire event loop for the duration of the HTTP request (~200-500ms per symbol under normal conditions). For a user with 10 exchange-override holdings, this adds 2-5 seconds of serial wall-clock time. **Fix:** wrap in `asyncio.to_thread(self.stock_provider.get_stock_details, ...)` to offload the synchronous call to a thread pool.

**Feasibility of pre-computation:**
- **On-import recompute:** Feasible (call `get_portfolio_performance()` after parsing and store to `portfolio_performance` table). The import path is already async background processing.
- **Daily scheduled job:** Feasible but unnecessary for correctness — on-import is better.
- **Lazy cache:** Simplest option — cache result for 10 minutes, invalidate on trade/import.

**Feasibility verdict:** Pre-computation is feasible but should be **lower priority** than N+1 elimination for most users. The FIFO computation is not the dominant cost for typical portfolios (<100 holdings).

### 7.6 Frontend Changes: Feasibility

| Change | Feasibility | Notes |
|--------|-------------|-------|
| **Prefetch on hover** | **Trivial.** Add `onMouseEnter` to `<Link>`, call `queryClient.prefetchQuery()`. ~15 lines. | Must check if `header.tsx` has access to `queryClient` (it's in a `'use client'` component — yes). |
| **Remove serial blocking** | **Trivial.** Remove the `if (accountsLoading)` early return, render tabs with `accountIds = undefined`. ~5 lines. | Backend must treat `undefined` accountIds as "all accounts". All endpoints already do this. |
| **Bundle endpoint** | **Moderate.** New backend endpoint + new frontend hook + replace individual calls. ~1-2 days. | Can ship behind feature flag. |
| **Lazy chart (IntersectionObserver)** | **Trivial.** Wrap chart in `IntersectionObserver` with `react-intersection-observer`. ~30 lines. | `react-intersection-observer` may need to be added as a dependency (not currently in `package.json`). Alternative: native `IntersectionObserver` API. |
| **SSR hydration** | **Moderate.** Requires server component wrapper, server-side token access. ~1-2 days. | Current layout is `'use client'` — requires refactoring or separate parallel route. |

### 7.7 Estimated Timing Budget (Post-Optimization)

The target of "< 1.5s first load" needs a component-level breakdown to be actionable. Below are estimated timings for a typical user (3 accounts, 50 holdings, 1Y period). All numbers are estimates — final values depend on hosting region, Supabase plan, and data volume.

| Component | Current (5 calls) | Post-P0 (batched + prefetch) | Post-P1 (bundle + cache) |
|-----------|:---:|:---:|:---:|
| Network (DNS + TLS + connect) | ~150ms | ~150ms | ~150ms |
| API proxy overhead | ~25ms (5 × 5ms) | ~25ms | ~5ms (1 call) |
| DB: portfolio_holdings | ~80ms | ~80ms | ~80ms |
| DB: companies enrichment | ~40ms | ~40ms | ~40ms |
| DB: current_market_data | ~60ms (3×) | ~30ms (TTL cache) | ~30ms (TTL cache) |
| DB: portfolio_dividends | ~50ms (N queries) | ~15ms (batched) | ~15ms |
| DB: portfolio_transactions (FIFO) | ~40ms (N queries) | ~10ms (batched) | ~10ms |
| DB: price_history (FIFO) | ~60ms (paginated) | ~60ms | — (not on critical path) |
| Price enrichment compute | ~120ms (0 exchange-override) | ~60ms (shared cache) | ~60ms |
| **yfinance (exchange-override, 10 holdings)** | **~5000ms (synchronous)** | **~300ms (`to_thread`)** | **~300ms** |
| FIFO performance compute | ~150ms | ~150ms | — (deferred) |
| Python overhead + JSON | ~50ms | ~50ms | ~30ms |
| React render + reconciliation | ~80ms | ~80ms | ~80ms |
| **Total** | **~905ms** | **~690ms** | **~430ms** |

**Notes:**
- Post-P0 numbers assume dividend + transaction batching, prefetch on hover, and serial loading removal — no bundle endpoint yet.
- Post-P1 numbers assume the Portfolio Dashboard View Model endpoint with shared enrichment, FIFO deferred to the performance tab (lazy-loaded), and the TTL market data cache.
- The "FIFO performance compute" line moves from the critical path (blocking initial render) to the deferred path (lazy chart).
- The yfinance row applies **only** when holdings have exchange-override symbols (typically 0–5 holdings). Without exchange-overrides, that row is 0ms. With 10 holdings, it dominates the current budget.
- Network latency dominates — these estimates assume ~30ms RTT to the backend. Users farther from the server will see higher baseline.

### 7.8 Database-Side Aggregation Opportunity

**Observation:** Several account-level summaries (holdings count, total value, gain/loss) are currently computed by fetching all holdings into Python and aggregating in a loop. This is inherently aggregate-oriented work that PostgreSQL handles efficiently.

**Option 1 — PostgreSQL RPC:**
```sql
CREATE OR REPLACE FUNCTION get_account_summaries(p_user_id INT)
RETURNS TABLE(
    account_id INT,
    account_name TEXT,
    holdings_count BIGINT,
    total_value NUMERIC,
    total_cost_basis NUMERIC,
    unrealized_pl NUMERIC
) LANGUAGE SQL STABLE AS $$
    SELECT
        a.account_id,
        a.account_name,
        COUNT(h.holding_id)::BIGINT,
        COALESCE(SUM(h.shares * COALESCE(cmd.current_price, 0)), 0),
        COALESCE(SUM(h.shares * h.avg_cost_basis), 0),
        COALESCE(SUM(h.shares * (COALESCE(cmd.current_price, 0) - h.avg_cost_basis)), 0)
    FROM accounts a
    LEFT JOIN portfolio_holdings h ON h.account_id = a.account_id
    LEFT JOIN current_market_data cmd ON cmd.company_id = h.company_id
    WHERE a.user_id = p_user_id AND a.is_active = TRUE
    GROUP BY a.account_id, a.account_name;
$$;
```
Call via `supabase.rpc("get_account_summaries", {"p_user_id": uid}).execute()` — single roundtrip, zero Python processing.

**Option 2 — Materialized view:**
```sql
CREATE MATERIALIZED VIEW mv_account_summaries AS
SELECT ...;  -- same query
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_account_summaries;
```
Trades real-time accuracy for near-zero read cost. Refresh on trade import or every N minutes via a cron trigger.

**Tradeoff:** The View Model endpoint (§9.4) already eliminates redundant enrichment by computing account values from the single holdings pass. SQL aggregation would further reduce Python overhead but adds a new deployment dependency (RPC migration or materialized view refresh). **Recommended:** Implement this only if the View Model endpoint's Python-side aggregation measuredly dominates latency (profile with `cProfile` or equivalent).

### 7.9 Per-Feature Cost/Benefit

| Feature | Estimated Effort | Estimated Impact | Risk | Do First? |
|---------|-----------------|-----------------|------|-----------|
| Add missing `portfolio_dividends` index | 15 min | Medium (faster dividend queries) | Near-zero | **Yes** |
| Batch dividend query (N+1 fix) | 2-3 hrs | High (eliminates N DB roundtrips) | Low | **Yes** |
| Batch transaction query (N+1 fix) | 2-3 hrs | High (eliminates N DB roundtrips) | Low | **Yes** |
| Prefetch portfolio data on hover | 30 min | High (hides network latency) | Low | **Yes** |
| Remove serial loading in PortfolioTabShell | 15 min | Medium (parallelizes queries) | Low | **Yes** |
| `/portfolio/dashboard` bundle endpoint | 1-2 days | Very High (cuts 3 API calls → 1) | Medium | **After N+1 fixes** |
| Module-level TTL cache for market data | 1 hr | Medium (reduces redundant DB reads) | Low | **After bundle** |
| Lazy performance chart (IntersectionObserver) | 30 min | Medium (moves FIFO out of critical path) | Low | **After P0** |
| FIFO pre-computation (on-import) | 2-3 days | Medium-High if >100 holdings; Low otherwise | Medium | **Only if lazy-load + cache still slow** |
| SSR hydration | 1-2 days | Medium (warm cache on first visit) | Medium | **After bundle** |

---

## 8. Measurement & Telemetry Plan (Diagnose Before Fixing)

### 8.1 What to Measure

Before making changes, instrument the following to pinpoint the actual bottleneck:

#### Backend — Python logging (add to `portfolio_service.py` and `api/portfolio.py`)

```python
import time
import logging

logger = logging.getLogger(__name__)

# Decorator pattern for timing
def timed(logger_):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                return result
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                logger_.info(f"[TIMING] {fn.__name__} took {elapsed:.1f}ms")
        return wrapper
    return decorator
```

Apply to these critical methods:

| Method | File | Why |
|--------|------|-----|
| `enrich_holdings_with_prices` | `portfolio_service.py:497` | Core price enrichment — 2 DB batch queries per call |
| `get_user_portfolio_overview` | `portfolio_service.py:1068` | Calls enrich + N dividend queries |
| `get_portfolio_performance` | `portfolio_service.py:1736` | FIFO rebuild — most CPU-intensive |
| `_get_holdings` | `portfolio_repository.py:300` | Holdings DB query time |
| `get_user_accounts` | `portfolio_repository.py:93` | Accounts DB query time |
| `_get_portfolio_service` with `get_stock_details` | `portfolio_service.py:570` | External yfinance HTTP call for override exchanges |

#### Backend — Span-level metrics (structured logging)

```python
# Add to request handler in api/portfolio.py
@router.get("/portfolio/accounts")
async def list_accounts(request, user):
    span = {
        "endpoint": "/portfolio/accounts",
        "user_id": db_user_id,
        "account_count": 0,
        "db_queries": 0,
        "duration_ms": 0,
    }
    start = time.perf_counter()
    # ... existing logic, incrementing span["db_queries"] ...
    span["duration_ms"] = (time.perf_counter() - start) * 1000
    span["account_count"] = len(enriched_accounts)
    logger.info(f"[PERF_SPAN] {json.dumps(span)}")
```

#### Frontend — Navigation timing via User Timing API

```typescript
// In usePortfolio.ts — wrap data fetching
export function usePortfolioAccounts() {
    const { portfolioService } = useServices();
    const queryKey = QK.portfolioAccounts();

    return useQuery({
        queryKey,
        queryFn: async () => {
            const mark = `portfolio-accounts-start`;
            performance.mark(mark);
            const data = await portfolioService.getAccounts();
            performance.measure('portfolio-accounts', mark);
            const entries = performance.getEntriesByName('portfolio-accounts');
            console.log(`[PERF] /portfolio/accounts: ${entries[entries.length-1].duration.toFixed(0)}ms`);
            return data;
        },
        ...
    });
}
```

#### Frontend — Page-level navigation trace

```typescript
// In portfolio/page.tsx — trace full page load
export default function PortfolioPage() {
    const [isReady, setIsReady] = useState(false);
    const { status } = useAuth();

    useEffect(() => {
        if (status === 'authenticated' && !isReady) {
            performance.mark('portfolio-page-rendered');
            performance.measure('portfolio-full-load', 'navigationStart', 'portfolio-page-rendered');
            setIsReady(true);
        }
    }, [status, isReady]);

    // ... render ...
}
```

### 8.2 Supabase Query Performance

Enable Supabase query logging to capture actual DB execution time:

```sql
-- Run in Supabase SQL editor to enable query stats
-- Check pg_stat_statements for the most expensive queries
SELECT
    query,
    calls,
    total_exec_time / calls AS avg_ms,
    rows,
    shared_blks_hit,
    shared_blks_read
FROM pg_stat_statements
WHERE query LIKE '%portfolio_%'
   OR query LIKE '%current_market_data%'
   OR query LIKE '%price_history%'
ORDER BY total_exec_time DESC
LIMIT 20;
```

### 8.3 EXPLAIN ANALYZE Validation (Before Touching Code)

Before adding indexes or rewriting queries, verify the current query plans so you don't waste effort on tables that are already indexed.

```sql
-- Run against Supabase SQL editor
-- BEFORE adding indexes — check for Seq Scan vs Index Scan

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM portfolio_holdings
WHERE account_id = ANY(ARRAY[1,2,3,4,5]);

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM portfolio_transactions
WHERE account_id = ANY(ARRAY[1,2,3,4,5])
ORDER BY transaction_date DESC;

EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM portfolio_dividends
WHERE account_id = ANY(ARRAY[1,2,3,4,5]) AND fiscal_year = 2026;

-- If already Index Scan → skip that index, bottleneck is elsewhere
-- If Seq Scan → index will help significantly
```

**Apply the same queries AFTER adding indexes and compare:**
- `Seq Scan` → `Index Scan` = win
- `total_time` drop = win
- `buffers` (shared hit vs read) — more hits = better cache utilization

### 8.4 Expected Output

After instrumentation, you should be able to answer:

| Question | Action |
|----------|--------|
| Which DB query is slowest? | `pg_stat_statements` |
| Which endpoint takes the longest? | Span-level duration logs |
| Is the bottleneck DB, Python, or yfinance? | Timed decorator on each layer |
| How many times is `enrich_holdings_with_prices` called per page load? | Count `[TIMING]` log lines |
| What is the frontend waterfall timing? | User Timing API measures |

---

## 9. Detailed Solution Designs with Code Patterns

### 9.1 P0 — Batch Dividend & Transaction Queries (Backend)

**Problem:** `get_account_dividends_by_year` and `get_account_transactions` are called per-account.

**Solution:** Add batched repository methods with **chunking and per-chunk error isolation**.

**Design considerations:**
- Supabase `in_` filter accepts up to ~1000 values per batch (varies by pg version)
- A single large batch failure loses all data — chunking isolates failures
- Each failed chunk degrades gracefully to individual queries (N-per-chunk instead of N total)

```python
# backend/infrastructure/repositories/portfolio_repository.py

from typing import List, Dict, Any, Optional, Callable
import logging

logger = logging.getLogger(__name__)

# ── Shared chunking helper ────────────────────────────────────────────

def _batch_execute(
    account_ids: List[int],
    batch_fn: Callable[[List[int]], List[Dict[str, Any]]],
    single_fn: Callable[[int], List[Dict[str, Any]]],
    batch_size: int = 500,
) -> List[Dict[str, Any]]:
    """Execute a batch query across account_ids with chunking + fallback.

    ``batch_fn`` is called with a chunk of account_ids (e.g. 500 at a time).
    If a chunk fails, each account_id in that chunk is retried individually
    via ``single_fn`` so a partial failure doesn't lose all data.
    """
    if not account_ids:
        return []

    all_results: List[Dict[str, Any]] = []
    for i in range(0, len(account_ids), batch_size):
        chunk = account_ids[i:i + batch_size]
        try:
            results = batch_fn(chunk)
            all_results.extend(results)
        except Exception as e:
            logger.warning(
                f"Batch query failed for chunk {i//batch_size} "
                f"({len(chunk)} ids): {e}. Falling back to individual queries."
            )
            for aid in chunk:
                try:
                    all_results.extend(single_fn(aid))
                except Exception as e2:
                    logger.error(f"Individual query failed for account {aid}: {e2}")
    return all_results

# ── Dividend batch methods ────────────────────────────────────────────

def _batch_dividends(
    self, account_ids: List[int], fiscal_year: Optional[int] = None
) -> List[Dict[str, Any]]:
    query = (
        self.client.table("portfolio_dividends")
        .select("*")
        .in_("account_id", account_ids)
    )
    if fiscal_year is not None:
        query = query.eq("fiscal_year", fiscal_year)
    res = query.limit(10000).execute()  # Explicit safety limit
    return res.data or []

def get_accounts_dividends_by_year(
    self,
    account_ids: List[int],
    fiscal_year: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Batch query for dividends across multiple accounts with chunking + fallback."""
    return _batch_execute(
        account_ids,
        batch_fn=lambda chunk: self._batch_dividends(chunk, fiscal_year),
        single_fn=lambda aid: self.get_account_dividends_by_year(aid, fiscal_year),
        batch_size=500,
    )

# ── Transaction batch methods ─────────────────────────────────────────

def _batch_transactions(
    self,
    account_ids: List[int],
    limit: Optional[int] = None,
    activity_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    query = (
        self.client.table("portfolio_transactions")
        .select("*")
        .in_("account_id", account_ids)
    )
    if activity_types:
        query = query.in_("activity_type", activity_types)
    query = query.order("transaction_date", desc=True)
    if limit:
        query = query.limit(limit)
    res = query.execute()
    return res.data or []

def get_accounts_transactions(
    self,
    account_ids: List[int],
    limit: Optional[int] = None,
    activity_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Batch query for transactions across multiple accounts with chunking + fallback."""
    return _batch_execute(
        account_ids,
        batch_fn=lambda chunk: self._batch_transactions(chunk, limit, activity_types),
        single_fn=lambda aid: self.get_account_transactions(aid, limit, activity_types),
        batch_size=500,
    )
```

**Usage in `get_user_portfolio_overview`:**
```python
# Before:
# for account in accounts:
#     account_divs = self.portfolio_repo.get_account_dividends_by_year(account["account_id"], current_year)

# After (single query):
account_ids_list = [a["account_id"] for a in accounts]
all_divs = self.portfolio_repo.get_accounts_dividends_by_year(account_ids_list, current_year)
# Group by account_id:
from collections import defaultdict
divs_by_account = defaultdict(list)
for d in all_divs:
    divs_by_account[d["account_id"]].append(d)
ytd_dividends = sum(Decimal(str(d.get("amount") or 0)) for d in all_divs)
```

**Usage in `get_portfolio_performance`:**
```python
# Before:
# all_txns = []
# for aid in account_ids:
#     txns = self.portfolio_repo.get_account_transactions(aid, activity_types=["Trade"])
#     all_txns.extend(txns)

# After (single query):
all_txns = self.portfolio_repo.get_accounts_transactions(account_ids, activity_types=["Trade"])
```

### 9.2 P1 — Module-Level TTL Cache for Price Enrichment

**Problem:** `enrich_holdings_with_prices` calls `current_market_data` and `price_history` on every invocation. With the new View Model endpoint (§9.4), it runs once per page load — but across requests, each worker repeats the same lookup.

**Solution:** Module-level TTL cache eliminates redundant DB reads across requests within the same process.

```python
# backend/shared/market_cache.py
"""Thread-safe TTL cache for current_market_data lookups."""

import asyncio
import time
import logging
from typing import Dict, List
from database import supabase


logger = logging.getLogger(__name__)

_cache: Dict[str, any] = {"data": {}, "expires_at": 0.0}
TTL_SECONDS = 30  # Market data is stale after 30s anyway
_lock = asyncio.Lock()  # Prevents concurrent coroutines from double-fetching


MAX_CACHE_SIZE = 5000  # ~5000 tickers; flush if exceeded

async def get_cached_prices(company_ids: List[int]) -> Dict[int, float]:
    now = time.time()
    if now <= _cache["expires_at"]:
        # Return only what was requested from the full cached dataset
        return {cid: _cache["data"][cid] for cid in company_ids if cid in _cache["data"]}

    async with _lock:
        if now <= _cache["expires_at"]:
            return {cid: _cache["data"][cid] for cid in company_ids if cid in _cache["data"]}

        # Fetch ALL current prices — table is small (~5-10K rows).
        # This avoids the correctness bug where a prior request's subset
        # is silently returned for a different company_id set.
        res = (
            supabase.table("current_market_data")
            .select("company_id, current_price")
            .execute()
        )
        _cache["data"] = {
            row["company_id"]: float(row["current_price"])
            for row in (res.data or [])
            if row.get("current_price") is not None
        }
        # NOTE: If current_market_data exceeds ~15K rows (crypto, ETFs, intl tickers),
        # this full-table fetch becomes slow. Consider reverting to ID-batched fetch
        # or adding a row-count guard: count_res = supabase.table(...).select("count", count="exact")
        if not res.data:
            logger.warning("[CACHE] current_market_data returned empty — keeping stale cache")

        # Guard against unbounded growth
        if len(_cache["data"]) > MAX_CACHE_SIZE:
            _cache["data"] = {}
            logger.warning(f"[CACHE] Flushed ({MAX_CACHE_SIZE} entries exceeded)")

        _cache["expires_at"] = time.time() + TTL_SECONDS
        logger.debug(f"[CACHE] Refreshed {len(_cache['data'])} companies")

    return {cid: _cache["data"][cid] for cid in company_ids if cid in _cache["data"]}
```

**Multi-instance note:** Each uvicorn worker has its own `_cache`. With 4 workers and 30s TTL, the DB sees ~4× more reads than a shared cache. Acceptable at current scale; adopt Redis (or Supabase cache layer) if horizontal scaling makes this a measured bottleneck. Until then, in-process caching avoids the operational overhead of an external cache dependency.

**Why not a request-scoped cache instead?** The redundant `enrich_holdings_with_prices` calls happen *across HTTP requests* (accounts vs overview vs holdings endpoints), not within a single request. The View Model endpoint (§9.4) eliminates cross-request duplication by design. A request-scoped cache would only help within a single request — and once the View Model endpoint ships, there's only one enrichment call per page load. Request-scoped caching adds complexity with zero marginal benefit.

### 9.3 P0 — Frontend Prefetch on Nav Link Hover

**Problem:** Portfolio queries only start after navigation completes — no speculative fetching.

**Solution:** Wire `onMouseEnter` on the Portfolio nav link.

```typescript
// web/src/components/header.tsx
import { useQueryClient } from '@tanstack/react-query';
import { QK } from '@/lib/query-keys';
import { useServices } from '@/shared/contexts/ServiceContext';

export function Header() {
    const pathname = usePathname();
    const queryClient = useQueryClient();
    const { portfolioService } = useServices();

    const prefetchPortfolio = useCallback(() => {
        // Only prefetch if not already cached
        if (!queryClient.getQueryData(QK.portfolioDashboard())) {
            queryClient.prefetchQuery({
                queryKey: QK.portfolioDashboard(),
                queryFn: () => portfolioService.getDashboardData(),
                staleTime: STALE.PORTFOLIO,  // 2 min
            });
        }
    }, [queryClient, portfolioService]);

    // Transition note: The old portfolioAccounts key still fires for
    // account-detail pages; the dashboard prefetch only covers initial nav.

    return (
        // In the nav link rendering:
        <Link
            key={href}
            href={href}
            onMouseEnter={href === '/portfolio' ? prefetchPortfolio : undefined}
            // ...
        >
            {label}
        </Link>
    );
}
```

### 9.4 P0 — Portfolio Dashboard View Model

**Problem:** 3 separate API calls for accounts, overview, and holdings, each calling `enrich_holdings_with_prices` independently. The same 50 holdings get enriched 3 times per page load.

**Solution:** A single view-model endpoint that represents "everything needed for the initial portfolio page render." This is not a bundle of existing endpoints — it's a purpose-built dashboard view with a single enrichment pass.

**Design contract:**
```
PortfolioDashboardView = {
  accounts: AccountSummary[]
  overview: PortfolioOverview
  holdings: HoldingRow[]
}
```

- **Bounded scope:** Only fields rendered in the initial page view. No benchmarks, alerts, news, or recommendations. New features add new endpoints, not new fields here.
- **Single enrichment:** `enrich_holdings_with_prices` runs exactly once. Accounts and overview are derived from the same holdings array.
- **Payload optimization:** Use `select("account_id, account_name, ...")` instead of `select("*")`. With field projection, response for 200 holdings drops from ~80KB to ~20KB. Ensure gzip compression is enabled (on by default in FastAPI behind a reverse proxy).

```python
# backend/api/portfolio.py
from decimal import Decimal

def _compute_overview_from_holdings(
    all_holdings: List[Dict],
    accounts: List[Dict],
    db_user_id: int,
    ytd_dividends: float = 0.0,
) -> Dict:
    """Compute overview metrics from pre-enriched holdings.

    Unlike get_user_portfolio_overview(), this does NOT:
    - Re-fetch holdings from DB (they're already in all_holdings)
    - Re-enrich with prices (already done upstream)
    - Query dividends per-account (uses batched query from caller)

    It aggregates total_value, total_cost_basis, gain/loss from the
    enriched holdings list in a single O(n) pass instead.
    """
    total_value = Decimal("0")
    total_cost = Decimal("0")
    for h in all_holdings:
        total_value += Decimal(str(h.get("current_value") or 0))
        total_cost += Decimal(str(h.get("total_cost") or 0))
    total_gain = total_value - total_cost
    total_gain_pct = (
        (float(total_gain) / float(total_cost) * 100)
        if total_cost else 0.0
    )
    return {
        "total_value": float(total_value),
        "total_cost_basis": float(total_cost),
        "total_gain_loss": float(total_gain),
        "total_gain_loss_pct": round(total_gain_pct, 2),
        "ytd_dividends": ytd_dividends,
        "holdings_count": len(all_holdings),
        "accounts_count": len(accounts),
    }


@router.get("/portfolio/dashboard", tags=["Portfolio"], status_code=200)
async def get_portfolio_dashboard(
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> dict:
    """
    Portfolio Dashboard View Model — single enrichment pass.
    Returns accounts, overview, and holdings in one response.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        repo = PortfolioRepository()
        service = _get_portfolio_service()

        # Single holdings fetch — reused for accounts + overview
        accounts = repo.get_user_accounts(db_user_id, active_only=True)
        account_ids = [a["account_id"] for a in accounts]
        all_holdings = await service.enrich_holdings_with_prices(
            repo.get_user_all_holdings(db_user_id)
        ) if account_ids else []

        # Build enriched accounts (using the SAME all_holdings data)
        enriched_accounts = []
        for acc in accounts:
            acc_holdings = [h for h in all_holdings if h.get("account_id") == acc["account_id"]]
            enriched_accounts.append({
                "account_id": acc["account_id"],
                "account_name": acc["account_name"],
                "account_type": acc["account_type"],
                "brokerage_name": acc.get("portfolio_brokerages", {}).get("brokerage_name"),
                "currency": acc["currency"],
                "holdings_count": len(acc_holdings),
                "total_value": float(sum(h.get("current_value") or 0 for h in acc_holdings)),
            })

        # Batched dividend query feeds into overview — integration between §9.1 and §9.4
        from datetime import date
        current_year = date.today().year
        all_divs = repo.get_accounts_dividends_by_year(account_ids, current_year)
        ytd_dividends = sum(float(d.get("amount") or 0) for d in all_divs)

        overview = _compute_overview_from_holdings(
            all_holdings, accounts, db_user_id, ytd_dividends
        )

        # Holdings: only fields needed for the initial holdings table display.
        # Full details (sector, industry, price history) load on demand.
        holdings_summary = [{
            "symbol": h["symbol"],
            "company_name": h.get("company_name"),
            "quantity": float(h.get("quantity") or 0),
            "current_price": float(h.get("current_price") or 0),
            "current_value": float(h.get("current_value") or 0),
            "total_cost": float(h.get("total_cost") or 0),
            "unrealized_gain_loss": float(h.get("unrealized_gain_loss") or 0),
            "unrealized_gain_loss_pct": float(h.get("unrealized_gain_loss_pct") or 0),
        } for h in all_holdings]

        return {
            "accounts": enriched_accounts,
            "overview": {k: v for k, v in overview.items() if k in (
                "total_value", "total_cost_basis", "total_gain_loss",
                "total_gain_loss_pct", "ytd_dividends", "holdings_count", "accounts_count",
            )},
            "holdings": holdings_summary,
        }
    except Exception as e:
        ...
```

**Frontend hook:**
```typescript
// web/src/features/portfolio/hooks/usePortfolioDashboard.ts
export function usePortfolioDashboard() {
    const { portfolioService } = useServices();

    return useQuery({
        queryKey: QK.portfolioDashboard(),
        queryFn: () => portfolioService.getDashboardData(),
        staleTime: STALE.PORTFOLIO,
        gcTime: GC.PORTFOLIO,
    });
}
```

**Modified `PortfolioTabShell` to use bundle:**
```typescript
export function PortfolioTabShell({ initialTab }: PortfolioTabShellProps) {
    const { data: initialData, isLoading } = usePortfolioDashboard();
    // Replace usePortfolioAccounts() + derive overview/holdings from bundle
    const accounts = initialData?.accounts;
    const overview = initialData?.overview;
    const holdings = initialData?.holdings;
    // ...
}
```

**Frontend service method (uses existing proxy):**
```typescript
// web/src/features/portfolio/services/portfolioService.ts
class PortfolioService {
    async getDashboardData(): Promise<PortfolioDashboardResponse> {
        return apiClient.get('/portfolio/dashboard');
        // apiClient handles auth cookie forwarding through the Next.js API proxy
    }
}
```

### 9.5 P2 — FIFO Performance Cache (If Still Needed After Lazy Load)

**Problem:** `get_portfolio_performance()` rebuilds FIFO from scratch on every page load.

**Approach:** The chart is already deferred to a lazy load (§9.7). If the lazy-loaded chart still exceeds 2s after P0/P1 ship, add a 10-minute process-level TTL cache with invalidation on trade import:

```python
# backend/shared/portfolio_cache.py
_cache: Dict[str, any] = {}

def get_cached_performance(user_id: int, period: str) -> Optional[dict]:
    key = f"perf:{user_id}:{period}"
    entry = _cache.get(key)
    if entry and entry["expires_at"] > time.time():
        return entry["data"]
    return None

def invalidate_user_cache(user_id: int):
    """Call after every CSV import / manual trade for this user."""
    keys = [k for k in _cache if k.startswith(f"perf:{user_id}:")]
    for k in keys:
        del _cache[k]
```

Pre-computed snapshots (on-import or scheduled job) are a further fallback if the lazy cache proves insufficient — but not until measurement confirms FIFO is the remaining bottleneck.

### 9.6 P0-4 — Wire PortfolioTabShell to Dashboard Hook

**Problem:** Tabs wait for accounts to resolve before even starting their own queries.

**Solution:** After the dashboard endpoint ships (§9.4), `PortfolioTabShell` consumes the dashboard hook instead of individual endpoint hooks. The dashboard response provides accounts, overview, and holdings in a single pass.

```typescript
// web/src/features/portfolio/components/PortfolioTabShell.tsx (post-dashboard)

export function PortfolioTabShell({ initialTab }: PortfolioTabShellProps) {
    const { data: initialData, isLoading } = usePortfolioDashboard();
    const [selectedAccountId, setSelectedAccountId] = useState<number>();
    const activeTab = initialTab ?? "overview";

    // Derive all state from the single dashboard response
    const accounts = initialData?.accounts;
    const allAccountIds = accounts?.map(a => a.account_id);
    const accountIds = selectedAccountId ? [selectedAccountId] : allAccountIds;

    return (
        <div className="space-y-6">
            {/* Account chips show skeleton if loading */}
            {isLoading ? (
                <Skeleton className="h-12 w-full" />
            ) : accounts && accounts.length > 0 ? (
                <AccountChipStrip ... />
            ) : null}

            <TabBar ... />

            {/* Render tabs IMMEDIATELY — they handle their own loading states */}
            {renderTab()}
        </div>
    );
}
```

**In each tab hook, handle `undefined` accountIds gracefully:**
```typescript
export function usePortfolioOverview(accountIds?: number[]) {
    return useQuery({
        queryKey: [...QK.portfolioOverview(), accountIds ?? 'all'],
        queryFn: () => portfolioService.getPortfolioOverview(accountIds?.[0]),
        // enabled: true — always fire, undefined means "no filter" on backend
        staleTime: STALE.PORTFOLIO,
    });
}
```

### 9.7 P1 — Lazy Performance Chart (IntersectionObserver)

**Problem:** `PortfolioPerformanceChart` fires expensive FIFO computation even if the chart is below the fold.

**Solution:** Use IntersectionObserver to defer the expensive queries.

```typescript
// web/src/features/portfolio/components/LazyPerformanceChart.tsx
'use client';

import { useInView } from 'react-intersection-observer';  // or IntersectionObserver API

export function LazyPerformanceChart() {
    const { ref, inView } = useInView({ triggerOnce: true, rootMargin: '200px' });

    return (
        <div ref={ref} className="lg:col-span-2 min-h-[200px]">
            {inView ? (
                <PortfolioPerformanceChart />
            ) : (
                <div className="glass-panel p-6">
                    <div className="h-[300px] rounded-xl bg-white/[0.02]" />
                </div>
            )}
        </div>
    );
}
```

**Update `OverviewTab` to use lazy wrapper:**
```typescript
// Instead of: <PortfolioPerformanceChart />
// Use:       <LazyPerformanceChart />
```

### 9.8 P2 — React Query SSR Hydration

**Problem:** Portfolio has no server-side data prefetching.

**Solution:** Use Next.js server component with `prefetchQuery`.

```typescript
// web/src/app/(authenticated)/portfolio/page.tsx (partial server component)

// Keep this as a client component wrapper, but add a server component for prefetch:
// web/src/app/(authenticated)/portfolio/prefetch.tsx
import { makeQueryClient } from '@/lib/query-client';
import { QK } from '@/lib/query-keys';
import { dehydrate } from '@tanstack/react-query';
import { HydrationBoundary } from '@tanstack/react-query';

export default async function PortfolioPrefetchLayout({
    children,
}: {
    children: React.ReactNode;
}) {
    const queryClient = makeQueryClient();

    // Get auth token from server-side request
    const { cookies } = await import('next/headers');
    const session = (await cookies()).get('__session');

    if (session) {
        // Prefetch dashboard server-side — cache is available immediately on client
        const backendUrl = process.env.BACKEND_URL || 'http://localhost:8001';
        await queryClient.prefetchQuery({
            queryKey: QK.portfolioDashboard(),
            queryFn: async () => {
                const res = await fetch(`${backendUrl}/portfolio/dashboard`, {
                    headers: { Authorization: `Bearer ${session.value}` },
                    cache: 'no-store',
                });
                return res.json();
            },
            staleTime: STALE.PORTFOLIO,
        });
    }

    return (
        <HydrationBoundary state={dehydrate(queryClient)}>
            {children}
        </HydrationBoundary>
    );
}
```

### 9.9 P1 — Fix YFinance Async-Blocking

**Problem:** `enrich_holdings_with_prices()` calls `self.stock_provider.get_stock_details()` synchronously inside an `async def`, blocking the event loop for ~200-500ms per exchange-override holding.

**Solution:** Offload the synchronous yfinance call to a thread pool using `asyncio.to_thread()`.

```python
# backend/application/services/portfolio_service.py

async def enrich_holdings_with_prices(self, holdings):
    # ... existing setup ...
    override_cache: Dict[str, Optional[float]] = {}

    for h in holdings:
        exchange_override = h.get("exchange_override")
        if exchange_override:
            cache_key = f"{h.get('symbol')}:{exchange_override}"
            if cache_key not in override_cache:
                try:
                    # BEFORE: sd = self.stock_provider.get_stock_details(...)
                    #         blocks event loop for 200-500ms
                    sd = await asyncio.to_thread(
                        self.stock_provider.get_stock_details,
                        h["symbol"],
                        exchange=exchange_override,
                    )
                    override_cache[cache_key] = sd.price if sd else None
                except Exception:
                    override_cache[cache_key] = None
            price = override_cache[cache_key]
        else:
            price = price_map.get(cid)

        # ... rest of enrichment logic ...
```

**Impact:** For a user with 10 exchange-override holdings, this drops the blocking wall-clock time from ~3s (serial blocking) to ~300ms (parallel thread pool, or truly concurrent if the yfinance calls themselves are I/O-bound). The change is a single-line swap inside a loop with zero behavioral change.

---

## 10. Risk Assessment & Rollback Plan

### 10.1 Per-Change Risks

| Change | Risk | Mitigation | Rollback |
|--------|------|-----------|----------|
| Database indexes | Index write overhead on inserts/updates | Index only highly-read columns; monitor write latency | `DROP INDEX` statement |
| Batch queries (`in_`) | Supabase `in_` filter row limit (~1000) | **Chunking at 500 + per-chunk fallback to individual queries** | Revert to per-account loop |
| Prefetch on hover | Wastes bandwidth if user hovers but doesn't click | Only prefetch if cache is empty; small payload (~5KB) | Remove `onMouseEnter` handler |
| Dashboard endpoint | Larger single payload; partial failure affects all data | Return per-section success flags; client handles gracefully | Roll back to individual endpoints |
| yfinance `to_thread()` | Thread pool overhead for sync calls | `to_thread()` is standard Python, negligible overhead | Revert to direct synchronous call |
| Pre-computed FIFO | Snapshots may diverge from actual data if trades are missed | Recompute on every import + manual trade; periodic full recompute | Load from old FIFO path as fallback |
| Lazy chart | Users may see empty space briefly | `rootMargin: 200px` loads chart before user scrolls to it | Remove `LazyPerformanceChart`, render inline |

### 10.2 Feature Flag Strategy

```python
# Add a feature flag for the bundle endpoint
# backend/config.py
ENABLE_PORTFOLIO_DASHBOARD: bool = os.getenv("ENABLE_PORTFOLIO_DASHBOARD", "false").lower() == "true"

# backend/api/portfolio.py
if config.ENABLE_PORTFOLIO_DASHBOARD:
    router.add_api_route("/portfolio/dashboard", get_portfolio_dashboard)
```

```typescript
// Frontend feature flag
// web/src/lib/feature-flags.ts
export const FEATURES = {
    portfolioDashboard: process.env.NEXT_PUBLIC_ENABLE_PORTFOLIO_DASHBOARD === 'true',
    lazyPerformanceChart: process.env.NEXT_PUBLIC_LAZY_PERFORMANCE_CHART === 'true',
};
```

---

## 11. SQL Migration Script — Portfolio Indexes

> **⚠️ IMPORTANT:** After the codebase audit in §7.1, only **one** of the five originally-proposed indexes is actually needed. See §7.2 for the full rationale.

Run against the Supabase database (via SQL editor or migration tool) after verifying via `EXPLAIN ANALYZE` (see §8.3) that this index doesn't already exist.

```sql
-- backend/scripts/add_portfolio_indexes.sql
-- The ONLY missing index for portfolio query performance.
-- All other originally-proposed indexes already exist as PKs or unique constraints.
-- CONCURRENTLY prevents table locks — safe for production.

-- Dividends: compound filter on (account_id, fiscal_year) in the N+1 batch query.
--    Used by: get_user_portfolio_overview(), dividend dashboard endpoints.
--    Without this: sequential scan on portfolio_dividends for every overview load.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_portfolio_dividends_account_year
    ON portfolio_dividends (account_id, fiscal_year);
```

**Rollback** — if write performance degrades:
```sql
DROP INDEX IF EXISTS idx_portfolio_dividends_account_year;
```

---

## 12. Post-Deployment Monitoring & Regression Prevention

### 12.1 Baseline Alert

After deploying all P0 changes, record a baseline of portfolio query performance from `pg_stat_statements`:

```sql
-- Run weekly or after any deploy touching portfolio code
SELECT
    query,
    calls,
    ROUND(total_exec_time / calls, 2) AS avg_ms,
    ROUND(stddev_exec_time, 2) AS stddev_ms,
    ROWS / calls AS avg_rows
FROM pg_stat_statements
WHERE query LIKE '%portfolio_%'
   OR query LIKE '%current_market_data%'
   OR query LIKE '%price_history%'
ORDER BY total_exec_time DESC;
```

**Alert rule (manual or cron):** If `avg_ms` exceeds baseline + 20% for any portfolio query, investigate for regressions (e.g. a new code path that re-introduced N+1 or a missing index).

### 12.2 Application-Level Metrics

```python
# backend/shared/metrics.py
# Minimal route-level timing without Prometheus dependency

import time
import logging

logger = logging.getLogger("perf.portfolio")

class RouteTimer:
    """Context manager that logs endpoint duration with metadata."""
    def __init__(self, endpoint: str, user_id: int, account_count: int = 0, holdings_count: int = 0, cache_hit: bool = False):
        self.endpoint = endpoint
        self.user_id = user_id
        self.account_count = account_count
        self.holdings_count = holdings_count
        self.cache_hit = cache_hit
        self.start: float = 0.0

    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *args):
        elapsed = (time.perf_counter() - self.start) * 1000
        logger.info(
            f"[PERF] {self.endpoint} user={self.user_id} "
            f"accounts={self.account_count} holdings={self.holdings_count} "
            f"cache_hit={self.cache_hit} duration={elapsed:.1f}ms"
        )


# Usage in api/portfolio.py:
# with RouteTimer("/portfolio/dashboard", db_user_id,
#                  account_count=len(accounts), holdings_count=len(all_holdings)):
#     ... handler logic ...
```

### 12.3 Load Testing (P2)

Validate under concurrent load before promoting the bundle endpoint to production:

```bash
# Using k6 (https://k6.io)
k6 run --vus 50 --duration 2m load-test/portfolio-initial-data.js
```

**What to watch for:**
- Supabase connection pool exhaustion (default 15–30 concurrent connections on free plan)
- Response time distribution (p50, p95, p99)
- Module-level cache correctness under race conditions (double-check pattern already handled)

---

## 13. Test Plan

### 13.1 Test Layers

| Layer | Tool/Library | Scope | Runs in CI |
|-------|-------------|-------|-----------|
| Unit | `pytest` + `pytest-asyncio` + `mock` | Individual functions, cache logic, helper logic | Yes |
| Integration (DB) | `pytest` + `pg_stat_statements` + test DB | Batch queries, index performance, data correctness | Yes (with Supabase test project) |
| Integration (API) | `pytest` + `httpx.AsyncClient` | Endpoint responses, feature flags, error handling | Yes (with Supabase test project) |
| E2E (UI) | Playwright | Full page load, prefetch, lazy chart, tab navigation | Yes (with preview deployment) |
| Performance | `k6` | Load testing dashboard endpoint, TTFB, throughput | On-demand or nightly |

---

### 13.2 Unit Tests

#### 13.2.1 Market Cache (`backend/shared/market_cache.py`)

| Test | What it verifies | Edge cases |
|------|-----------------|------------|
| `test_cache_returns_cached_data_within_ttl` | Subsequent calls within 30s return cached data without DB hit | — |
| `test_cache_refreshes_after_ttl_expiry` | Call after 30s+ hits DB and updates cache | — |
| `test_double_check_pattern_prevents_duplicate_fetch` | Two concurrent coroutines: only one DB query, both get data | Concurrent `asyncio.gather` |
| `test_cache_returns_only_requested_ids` | Call with [1,2,3] doesn't return [4,5,6] from stale cache | Subset, superset, empty list |
| `test_cache_handles_empty_response_from_db` | DB returns empty → cache logs warning, keeps stale data | DB outage, cold start |
| `test_cache_flushes_on_max_size` | >5000 entries → cache resets | Boundary at 5000, 5001 |
| `test_cache_refresh_with_partial_db_data` | DB only returns 3 of 5 requested IDs → returns what it has | Partial data availability |

```python
# backend/tests/test_market_cache.py
@pytest.mark.asyncio
async def test_double_check_pattern_prevents_duplicate_fetch():
    """Two concurrent cache misses should result in exactly one DB query."""
    db_call_count = 0

    async def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        await asyncio.sleep(0.05)  # Simulate DB latency
        return Mock(data=[{"company_id": 1, "current_price": 150.0}])

    with mock.patch("database.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        # Fire two concurrent cache misses
        results = await asyncio.gather(
            get_cached_prices([1]),
            get_cached_prices([1]),
        )

        assert db_call_count == 1  # Lock prevented duplicate fetch
        assert results[0] == results[1] == {1: 150.0}
```

#### 13.2.2 Batch Repository Methods (`backend/infrastructure/repositories/portfolio_repository.py`)

| Test | What it verifies | Edge cases |
|------|-----------------|------------|
| `test_batch_dividends_single_query` | N account_ids → 1 `in_()` query (not N `eq()` queries) | — |
| `test_batch_dividends_matches_per_account` | Batch results equal the union of per-account results | Data correctness |
| `test_batch_transactions_single_query` | Same single-query assertion for transactions | — |
| `test_chunking_splits_large_batches` | >1000 ids → split into chunks of 500 | Exactly 1000, 1001, 0 |
| `test_chunk_fallback_on_partial_failure` | One chunk fails → remaining chunks still return data | — |
| `test_empty_account_ids` | Empty list → returns empty list, no queries fired | — |
| `test_batch_with_none_year` | `fiscal_year=None` → queries without year filter | — |

```python
# backend/tests/test_portfolio_batch_queries.py
@pytest.mark.asyncio
async def test_chunking_splits_large_batches():
    """Batch of 1500 account_ids should produce 3 chunks of 500."""
    repo = PortfolioRepository()
    account_ids = list(range(1, 1501))
    call_count = 0

    original_in = repo.client.table("portfolio_dividends").in_

    def tracking_in(field, values):
        nonlocal call_count
        call_count += 1
        assert len(values) <= 500, f"Chunk exceeded 500: {len(values)}"
        return Mock()

    with mock.patch.object(repo.client.table("portfolio_dividends"), "in_", tracking_in):
        repo.get_accounts_dividends_by_year(account_ids, 2025)
        assert call_count == 3  # 3 chunks of 500
```

#### 13.2.3 `_compute_overview_from_holdings`

| Test | What it verifies | Edge cases |
|------|-----------------|------------|
| `test_overview_from_single_holding` | $1000 value, $800 cost → $200 gain, 25% | — |
| `test_overview_from_multiple_holdings` | Sum across 5 holdings matches expected totals | — |
| `test_overview_no_holdings` | Empty list → $0 total, 0 count | — |
| `test_overview_zero_cost_basis` | Total gain=0, cost=0 → gain_pct=0 (no div-by-zero) | Division by zero |
| `test_overview_includes_ytd_dividends` | $50 ytd_dividends appears in output | — |

```python
# backend/tests/test_overview_computation.py
def test_overview_zero_cost_basis():
    """Empty holdings should not cause division by zero."""
    result = _compute_overview_from_holdings([], [], 1, 0.0)
    assert result["total_gain_loss_pct"] == 0.0
    assert result["total_value"] == 0.0
```

#### 13.2.4 RouteTimer

| Test | What it verifies | Edge cases |
|------|-----------------|------------|
| `test_route_timer_logs_duration` | Context manager logs expected fields | — |
| `test_route_timer_zero_holdings` | Logs correctly with zero counts | — |
| `test_route_timer_cache_hit_flag` | `cache_hit=True` appears in log output | — |

---

### 13.3 Integration Tests

#### 13.3.1 Database / Repository

| Test | Scenario | Verification |
|------|----------|-------------|
| `test_dividend_index_speeds_up_query` | Run `get_account_dividends_by_year` before and after `CREATE INDEX` | `EXPLAIN ANALYZE` shows seq scan → index scan; latency drops |
| `test_batch_dividends_returns_correct_data` | Insert 20 dividends across 5 accounts, batch query | Results match union of 5 per-account queries |
| `test_batch_transactions_returns_correct_data` | Insert 100 transactions across 3 accounts, batch query | Results match per-account union |
| `test_batch_vs_n_queries_comparison` | Measure DB calls with `pg_stat_statements` | `calls = 1` for batch, `calls = N` for loop |
| `test_market_cache_reduces_db_reads` | 10 enrichment calls → verify only 1 `current_market_data` query | `pg_stat_statements` count |

```python
# backend/tests/integration/test_repository_performance.py
@pytest.mark.asyncio
async def test_batch_vs_n_queries_comparison():
    """Batch query should produce exactly 1 DB call vs N sequential calls."""
    repo = PortfolioRepository(batch_mode=True)
    account_ids = [1, 2, 3, 4, 5]
    year = 2025

    # Reset pg_stat_statements
    with mock.patch("backend.infrastructure.repositories.database.execute_raw") as sql:
        # Capture SQL queries
        query_log = []

        def capture(sql_str, *args, **kwargs):
            query_log.append(sql_str)
            return Mock(data=[])

        sql.side_effect = capture

        result = await repo.get_accounts_dividends_by_year(account_ids, year)

        # Exactly 1 query with IN clause
        batch_queries = [q for q in query_log if "portfolio_dividends" in q]
        assert len(batch_queries) == 1
        assert "IN" in batch_queries[0] or "in_" in batch_queries[0]
```

#### 13.3.2 API Endpoint

| Test | Scenario | Verification |
|------|----------|-------------|
| `test_dashboard_returns_all_sections` | Call `GET /portfolio/dashboard` | Response has `accounts`, `overview`, `holdings` keys |
| `test_dashboard_response_matches_individual_endpoints` | Compare dashboard vs `accounts` + `overview` + `holdings` | Same data shape for common fields |
| `test_dashboard_single_enrichment_call` | Stub `enrich_holdings_with_prices` | Called exactly once |
| `test_dashboard_feature_flag_disabled` | Flag OFF → endpoint returns 404 | — |
| `test_dashboard_feature_flag_enabled` | Flag ON → endpoint returns 200 | — |
| `test_dashboard_with_exchange_override_holdings` | Account has 5 exchange-override holdings | Response includes prices, yfinance called in thread |
| `test_dashboard_empty_accounts` | User with zero accounts | `accounts: []`, counts are 0 |
| `test_dashboard_includes_ytd_dividends` | User has dividends this year | `ytd_dividends > 0` in overview |
| `test_dashboard_response_time_under_threshold` | Load under 500 holdings | Response time < 2s (excl. network) |

```python
# backend/tests/integration/test_dashboard_endpoint.py
@pytest.mark.asyncio
async def test_dashboard_single_enrichment_call():
    """Dashboard endpoint should call enrich_holdings_with_prices exactly once."""
    from backend.api.portfolio import get_portfolio_dashboard
    from backend.application.services.portfolio_service import PortfolioService

    enrich_count = 0
    original_enrich = PortfolioService.enrich_holdings_with_prices

    async def tracking_enrich(self, holdings):
        nonlocal enrich_count
        enrich_count += 1
        return await original_enrich(self, holdings)

    with mock.patch.object(PortfolioService, "enrich_holdings_with_prices", tracking_enrich):
        client = TestClient(app)
        response = await client.get("/portfolio/dashboard", headers={"Authorization": "Bearer test_token"})

        assert enrich_count == 1, f"Expected 1 enrich call, got {enrich_count}"
        assert response.status_code == 200
```

#### 13.3.3 YFinance Async Fix

| Test | Scenario | Verification |
|------|----------|-------------|
| `test_get_stock_details_runs_in_thread` | Call with exchange-override ticker | Runs in `to_thread`, doesn't block event loop |
| `test_get_stock_details_timeout` | yfinance takes >10s | Times out, returns cached/partial data |
| `test_get_stock_details_fallback_on_failure` | yfinance raises exception | Returns `None`, caller handles gracefully |

```python
# backend/tests/test_yfinance_provider.py
@pytest.mark.asyncio
async def test_get_stock_details_runs_in_thread():
    """YFinanceProvider.get_stock_details should run in executor to avoid blocking."""
    provider = YFinanceProvider()

    with mock.patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_thread:
        result = await provider.get_stock_details("AAPL", exchange_override=True)
        assert mock_thread.called
```

---

### 13.4 E2E Tests (Playwright)

All E2E tests run against a preview deployment with `ENABLE_PORTFOLIO_DASHBOARD=true`.

#### 13.4.1 Page Load Tests

| Test | Steps | Assertions | Target |
|------|-------|-----------|--------|
| `full-page-load` | Navigate to `/portfolio` | Accounts chip strip visible within 2s, holdings table visible within 3s | Critical path |
| `dashboard-single-request` | Navigate to `/portfolio`, intercept network | Only 1 request to `/portfolio/*` endpoints (the dashboard) | Network verification |
| `no_redundant_enrichment` | Navigate to `/portfolio`, intercept backend calls | `enrich_holdings_with_prices` called exactly once | Architecture verification |
| `old-endpoints-not-called-initially` | Navigate to `/portfolio` | No requests to `/portfolio/accounts`, `/portfolio/overview`, `/portfolio/holdings` on initial load | Feature flag correctness |

```typescript
// web/e2e/portfolio-load.spec.ts
import { test, expect } from '@playwright/test';

test('dashboard-single-request', async ({ page }) => {
    const requests: string[] = [];
    page.on('request', req => {
        if (req.url().includes('/portfolio/')) {
            requests.push(req.url());
        }
    });

    await page.goto('/portfolio');

    // Allow lazy chart request (its endpoint is /portfolio/performance, not dashboard)
    const dashboardRequests = requests.filter(u => u.includes('/portfolio/dashboard'));
    expect(dashboardRequests.length).toBe(1);
});
```

#### 13.4.2 Prefetch Tests

| Test | Steps | Assertions |
|------|-------|-----------|
| `prefetch-on-hover` | Hover over "Portfolio" nav link, then wait before clicking | Dashboard query fires on hover, cache is warm on navigation |
| `prefetch-skips-if-cached` | Hover twice → only 1 network request | — |
| `prefetch-expires-after-staletime` | Hover, wait 2+ min, click → fetches fresh data | — |

```typescript
// web/e2e/prefetch.spec.ts
test('prefetch-on-hover', async ({ page }) => {
    const requests: string[] = [];
    page.on('request', req => {
        if (req.url().includes('/portfolio/dashboard')) {
            requests.push(req.url());
        }
    });

    await page.goto('/dashboard');
    const navLink = page.locator('a[href="/portfolio"]');
    await navLink.hover();
    await page.waitForTimeout(500); // Wait for prefetch trigger

    expect(requests.length).toBe(1); // Prefetch fired on hover
});
```

#### 13.4.3 Lazy Loading Tests

| Test | Steps | Assertions |
|------|-------|-----------|
| `lazy-chart-not-loaded-initially` | Load `/portfolio` | No network request to `/portfolio/performance` |
| `lazy-chart-loads-on-scroll` | Scroll performance chart into viewport | `/portfolio/performance` request fires |
| `lazy-chart-trigger-once` | Scroll in and out → only 1 request | — |

```typescript
// web/e2e/lazy-chart.spec.ts
test('lazy-chart-not-loaded-initially', async ({ page }) => {
    const perfRequests: string[] = [];
    page.on('request', req => {
        if (req.url().includes('/portfolio/performance')) {
            perfRequests.push(req.url());
        }
    });

    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    expect(perfRequests.length).toBe(0); // No perf query until scroll
});

test('lazy-chart-loads-on-scroll', async ({ page }) => {
    const perfRequests: string[] = [];
    page.on('request', req => {
        if (req.url().includes('/portfolio/performance')) {
            perfRequests.push(req.url());
        }
    });

    await page.goto('/portfolio');
    await page.waitForLoadState('networkidle');

    // Scroll to bottom where chart is
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForTimeout(500);

    expect(perfRequests.length).toBe(1);
});
```

#### 13.4.4 Tab Navigation Tests

| Test | Steps | Assertions |
|------|-------|-----------|
| `tab-switch-uses-individual-endpoints` | Click "Holdings" tab | Calls `/portfolio/holdings` (not dashboard) |
| `tab-switch-preserves-dashboard-cache` | Switch tabs, switch back | No new dashboard request (staleTime not expired) |
| `account-filter-sends-correct-ids` | Select single account chip | Overview and holdings queries include `account_id` filter |

#### 13.4.5 Regression Tests

| Test | Steps | Assertions |
|------|-------|-----------|
| `watchlist-unaffected` | Navigate to `/dashboard` | No dashboard request, watchlist loads normally |
| `stock-detail-unaffected` | Navigate to `/stock/AAPL` | No dashboard request, stock detail loads normally |
| `portfolio-with-0-accounts` | User with no accounts | Empty state renders, no errors |
| `portfolio-with-1-account` | User with single account | Loads correctly, no warnings |
| `mobile-viewport` | 375×812 viewport | Layout renders correctly, no horizontal scroll |

---

### 13.5 Performance / Load Tests (k6)

#### 13.5.1 Dashboard Endpoint

```javascript
// k6/portfolio-dashboard.js
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
    stages: [
        { duration: '30s', target: 10 },  // Ramp to 10 VUs
        { duration: '1m', target: 50 },   // Ramp to 50 VUs
        { duration: '30s', target: 0 },   // Ramp down
    ],
    thresholds: {
        http_req_duration: ['p(95)<2000', 'p(99)<3000'],
        http_req_failed: ['rate<0.01'],
    },
};

export default function () {
    const res = http.get(
        'https://staging.example.com/portfolio/dashboard',
        { headers: { Authorization: `Bearer ${__ENV.TEST_TOKEN}` } }
    );
    check(res, {
        'status is 200': (r) => r.status === 200,
        'has accounts': (r) => r.json('accounts') !== undefined,
        'has overview': (r) => r.json('overview') !== undefined,
        'has holdings': (r) => r.json('holdings') !== undefined,
        'duration < 2s': (r) => r.timings.duration < 2000,
    });
    sleep(1);
}
```

| Metric | Threshold | Rationale |
|--------|-----------|----------|
| p95 response time | < 2s | 95% of users see < 2s |
| p99 response time | < 3s | Tail latency bound |
| Error rate | < 1% | 99%+ success rate |
| Throughput | > 50 req/s | Supports 50 concurrent users |

#### 13.5.2 Cache Hit Ratio Test

| Scenario | Verification |
|----------|-------------|
| 50 concurrent users, same 20 tickers | Cache hit ratio > 95% after initial burst |
| 50 concurrent users, random 200 tickers | Cache hit ratio > 80% (first requests miss, subsequent hits) |
| Cache cold start (after deployment) | All requests miss, system handles DB load |

---

### 13.6 Test Data Fixtures

```sql
-- backend/tests/fixtures/test_data.sql
-- Portfolio test data: 3 accounts, 15 holdings, 10 dividends, 30 transactions

INSERT INTO accounts (account_id, user_id, account_name, account_type, currency, is_active)
VALUES
    (1, 100, 'Taxable Brokerage', 'brokerage', 'USD', TRUE),
    (2, 100, 'Roth IRA', 'ira', 'USD', TRUE),
    (3, 100, '401(k)', '401k', 'USD', TRUE);

INSERT INTO portfolio_holdings (holding_id, account_id, company_id, symbol, shares, avg_cost_basis)
VALUES
    (1, 1, 1, 'AAPL', 10, 150.00),
    (2, 1, 2, 'MSFT', 5, 300.00),
    (3, 1, 3, 'GOOGL', 3, 2000.00),
    (4, 2, 1, 'AAPL', 5, 155.00),
    (5, 2, 4, 'AMZN', 8, 130.00),
    -- ... 10 more holdings
    ;

INSERT INTO portfolio_dividends (dividend_id, account_id, company_id, fiscal_year, amount, ex_date, pay_date)
VALUES
    (1, 1, 1, 2025, 100.00, '2025-01-15', '2025-02-01'),
    (2, 1, 2, 2025, 75.00, '2025-02-10', '2025-02-28'),
    -- ... 8 more dividends
    ;

INSERT INTO portfolio_transactions (transaction_id, account_id, company_id, transaction_date, ...)
VALUES
    -- 30 transactions across accounts and time range
    ;
```

**Fixture categories:**

| Fixture | Purpose | Data Volume |
|---------|---------|-------------|
| `minimal` | Basic smoke test | 1 account, 3 holdings |
| `standard` | Typical user | 3 accounts, 15 holdings, 10 dividends, 30 transactions |
| `large_portfolio` | Worst-case | 10 accounts, 200 holdings, 100 dividends, 500 transactions |
| `exchange_override` | yfinance path | 2 accounts, 5 exchange-override holdings |
| `empty` | Edge case | 0 accounts |

---

### 13.7 CI Integration

```yaml
# .github/workflows/test-portfolio.yml
name: Portfolio Performance Tests
on:
  pull_request:
    paths:
      - 'backend/application/services/portfolio_service.py'
      - 'backend/infrastructure/repositories/portfolio_repository.py'
      - 'backend/api/portfolio.py'
      - 'backend/providers/yfinance_provider.py'
      - 'backend/shared/market_cache.py'
      - 'web/src/features/portfolio/**'

jobs:
  unit-and-integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_DB: stockerpro_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install -r requirements-dev.txt
      - run: pytest backend/tests/ -v --cov=backend --cov-report=term-missing
        env:
          SUPABASE_URL: ${{ secrets.TEST_SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.TEST_SUPABASE_ANON_KEY }}

  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci
      - run: npx playwright install --with-deps
      - run: npx playwright test web/e2e/portfolio-*.spec.ts
        env:
          ENABLE_PORTFOLIO_DASHBOARD: true
          BASE_URL: ${{ secrets.PREVIEW_URL }}

  performance-gate:
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request' && contains(github.event.pull_request.labels.*.name, 'performance')
    steps:
      - uses: actions/checkout@v4
      - run: k6 run k6/portfolio-dashboard.js
        env:
          TEST_TOKEN: ${{ secrets.LOAD_TEST_TOKEN }}
```

**CI gates:**

| Gate | Trigger | Fail if |
|------|---------|---------|
| Unit + integration | Every PR touching portfolio code | Any test failure |
| E2E | Every PR touching portfolio code | Any E2E failure |
| Performance | PRs labeled `performance` | p95 > 2s or error rate > 1% |
| Bundle size | Every PR | Frontend bundle increases > 50KB |
| Index migration | PRs adding SQL migrations | `EXPLAIN` shows seq scan where index expected |

---

### 13.8 Test Coverage Summary

```
backend/
  tests/
    test_market_cache.py           # 7 tests
    test_portfolio_batch_queries.py # 7 tests
    test_overview_computation.py    # 5 tests
    test_yfinance_provider.py       # 3 tests
    test_route_timer.py             # 3 tests
    integration/
      test_repository_performance.py  # 5 tests
      test_dashboard_endpoint.py      # 8 tests
      test_feature_flags.py           # 3 tests
web/
  e2e/
    portfolio-load.spec.ts          # 3 tests
    prefetch.spec.ts                # 3 tests
    lazy-chart.spec.ts              # 3 tests
    tab-navigation.spec.ts          # 3 tests
    regression.spec.ts             # 5 tests
k6/
  portfolio-dashboard.js            # Load test
  portfolio-cache-hit.js            # Cache ratio test
```

**Total:** ~55 tests + 2 k6 scenarios. Coverage targets:
- **Backend core paths** (batch queries, cache, dashboard endpoint): 95%+
- **Frontend critical user paths** (page load, prefetch, lazy chart): 100% of E2E
- **Error/edge paths** (empty state, exchange-override, timeouts): 80%+

## 14. Files Referenced

| File | Role |
|------|------|
| `web/src/app/(authenticated)/portfolio/page.tsx` | Portfolio page entry |
| `web/src/features/portfolio/components/PortfolioTabShell.tsx` | Shell with serial loading |
| `web/src/features/portfolio/components/OverviewTab.tsx` | Default tab, fires overview + holdings queries |
| `web/src/features/portfolio/components/PortfolioPerformanceChart.tsx` | Fires performance + benchmarks queries |
| `web/src/features/portfolio/hooks/usePortfolio.ts` | All React Query hooks (20+ hooks) |
| `web/src/lib/query-client.ts` | Stale/GC time constants |
| `web/src/lib/query-keys.ts` | React Query key factory |
| `web/src/components/header.tsx` | Nav links — possible prefetch injection point |
| `web/src/app/(authenticated)/layout.tsx` | Auth guard + GlobalSSEProvider |
| `backend/api/portfolio.py` | All portfolio API endpoints |
| `backend/application/services/portfolio_service.py` | Business logic (enrich holdings, FIFO, overview) |
| `backend/infrastructure/repositories/portfolio_repository.py` | Database access layer |
| `backend/config.py` | Feature flags, settings |
| `backend/database.py` | Supabase client singleton (already exists) |
| `backend/providers/yfinance_provider.py` | Synchronous yfinance calls that block async event loop |
| `backend/shared/portfolio_cache.py` | Proposed TTL cache module |
| `backend/shared/market_cache.py` | Proposed market data cache |
| `backend/jobs/compute_portfolio_snapshots.py` | Proposed background job |
| `backend/scripts/add_portfolio_indexes.sql` | Proposed index migration script (single index) |
| `backend/docs/PORTFOLIO_DESIGN.md` | Portfolio table schema definitions |
| `backend/docs/Supabase_Schema.md` | Canonical schema (price_history, current_market_data indexes) |
| `backend/tests/test_market_cache.py` | Unit tests: market cache correctness + concurrency |
| `backend/tests/test_portfolio_batch_queries.py` | Unit tests: batch queries, chunking, fallback |
| `backend/tests/test_overview_computation.py` | Unit tests: `_compute_overview_from_holdings` |
| `backend/tests/test_yfinance_provider.py` | Unit tests: async-to-thread adapter |
| `backend/tests/test_route_timer.py` | Unit tests: instrumentation logging |
| `backend/tests/integration/test_repository_performance.py` | Integration tests: DB roundtrip counts |
| `backend/tests/integration/test_dashboard_endpoint.py` | Integration tests: view-model endpoint |
| `backend/tests/integration/test_feature_flags.py` | Integration tests: flag on/off behavior |
| `backend/tests/fixtures/test_data.sql` | Fixture data: minimal, standard, large, exchange-override |
| `web/e2e/portfolio-load.spec.ts` | E2E: page load assertions |
| `web/e2e/prefetch.spec.ts` | E2E: prefetch on hover |
| `web/e2e/lazy-chart.spec.ts` | E2E: deferred performance chart |
| `web/e2e/tab-navigation.spec.ts` | E2E: tab switch correctness |
| `web/e2e/regression.spec.ts` | E2E: regression scenarios |
| `k6/portfolio-dashboard.js` | Load test: dashboard endpoint |
| `k6/portfolio-cache-hit.js` | Load test: cache hit ratio |
| `.github/workflows/test-portfolio.yml` | CI pipeline for all portfolio tests |
