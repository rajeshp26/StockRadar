# Watchlist Null Price Bug — Root Cause Analysis & Fix Design

**Date:** 2026-07-25
**Severity:** High — 7 stocks permanently show no price data
**Affected Stocks:** RBLX, SIRI, AI, CHTR, NOW, U, INTU (any watchlist-only stock)
**Status:** Root cause confirmed via diagnostic scripts, design validated against all code paths

---

## 1. Issue Description

Certain stocks in the watchlist display `priceData= null` and `price=null` in the frontend while other stocks show valid prices. The issue persists indefinitely — affected stocks never self-heal.

**Console evidence:**
```
[PRICE-DIAG] RBLX: priceData= null price=null     ← always null
[PRICE-DIAG] MA: priceData= {symbol: 'MA', price: 539.66, ...} price=539.66  ← works
```

**Scope:** Any stock that exists only in `watchlist_items` (not in `portfolio_holdings`) is affected. The 7 listed stocks are the ones observed in the user's watchlist.

---

## 2. Architecture Overview — Price Data Flow

```
                          ┌─────────────────────────────────────────────┐
                          │         CURRENT_MARKET_DATA TABLE           │
                          │  (primary DB source for REST price API)     │
                          └──────────────┬──────────────────────────────┘
                                         │
                    ┌────────────────────┼────────────────────┐
                    │                    │                     │
            ┌───────▼───────┐   ┌───────▼───────┐   ┌───────▼───────┐
            │  PATH 1:       │   │  PATH 2:       │   │  PATH 3:       │
            │  REST API      │   │  Background    │   │  Price         │
            │  (on load)     │   │  Monitor       │   │  Ingestion Job │
            │                │   │  (every 10s)   │   │  (every 5-30m) │
            └───────┬───────┘   └───────┬───────┘   └───────┬───────┘
                    │                    │                     │
                    │  reads from        │  reads from         │  writes to
                    │  current_market_   │  yfinance API       │  current_market_
                    │  data (paginated)  │  (live)             │  data
                    │                    │                     │
                    ▼                    ▼                     │
            ┌─────────────────────────────────┐                │
            │     SSE QUEUE (per connection)   │                │
            │     asyncio.Queue(maxsize=200)   │                │
            │     (live updates ONLY)           │                │
            └──────────────┬──────────────────┘                │
                           │                                   │
                           ▼                                   │
            ┌─────────────────────────────────┐                │
            │     FRONTEND                     │                │
            │  useWatchlistPrices() → REST     │                │
            │    → seeds React Query cache     │                │
            │  GlobalSSEProvider               │                │
            │    → updates cache on live event │                │
            │  usePriceData(symbol)            │                │
            │    → StockCard displays price    │                │
            └─────────────────────────────────┘                │
                                                               │
                          ┌────────────────────────────────────┘
                          │  writes to current_market_data
                          │  (portfolio + watchlist stocks)
                          ▼
                 ┌─────────────────┐
                 │  INGESTION JOB   │
                 │  Processes both  │
                 │  portfolio AND   │
                 │  watchlist       │
                 └─────────────────┘
```

---

## 3. Root Cause Analysis — Three Independent Failures

### Failure 1: Queue Overflow (Primary — Immediate Impact)

**File:** `backend/api/watchlists.py:160`
```python
queue: asyncio.Queue = asyncio.Queue(maxsize=50)
```

**Evidence:**
- Watchlist has **63 stocks** (confirmed via DB query)
- Queue holds **50 events** maximum
- `_safe_put()` at line 37-53 uses **drop-oldest** backpressure
- First 13 stocks in iteration order are silently dropped

**Diagnostic proof:**
```
simulate_queue_overflow.py:
  Total watchlist symbols: 63
  Queue maxsize: 50
  DROPPED symbols: [VOO, VTI, BTO, ET, ARI, KMI, RBLX, SIRI, AI, CHTR, NOW, U, INTU]
  => RBLX, SIRI, AI, CHTR, NOW, U, INTU are all within the first 13 dropped
```

**Why the background monitor doesn't self-heal:**
The monitor at `main.py:86-125` DOES broadcast live prices for all subscribed symbols. However, examining the user's SSE logs shows events arriving for CHPY, JEPI, JEPQ (positions 52-63) but never for RBLX (position 7). The monitor broadcasts to `symbol_subscribers` which includes all symbols, but the `yf.Tickers()` call with 189 resolved symbols (63 × 3 suffixes) may silently fail for some tickers in the batch. Our diagnostic test with 11 tickers showed all 7 work, but the 189-ticker production batch is a different scenario.

**Impact:** Any watchlist with >50 stocks loses the first N-50 initial push events. These stocks show null prices until the background monitor fills in — which may never happen for some symbols.

**Fix:** Separate initial prices (REST API with pagination) from live updates (SSE queue). See Fix 1.

---

### Failure 2: `current_market_data` Not Refreshed for Watchlist-Only Stocks (Structural)

**File:** `backend/application/jobs/price_ingestion_job.py:31`
```python
holdings = repo.get_all_active_holdings()  # queries ONLY portfolio_holdings
```

**File:** `backend/infrastructure/repositories/price_repository.py:78-91`
```python
def get_all_active_holdings(self) -> List[Dict[str, Any]]:
    result = (
        self.client.table("portfolio_holdings")  # ← ONLY this table
        .select("holding_id, account_id, company_id, symbol, ...")
        .execute()
    )
    return result.data or []
```

**Additional finding — `price_source_preferences` table does not exist:**
```
Diagnostic output:
  postgrest.exceptions.APIError: Could not find the table
  'public.price_source_preferences' in the schema cache
```

This means the ingestion job's preference lookup at `price_ingestion_job.py:37` returns empty `{}`, and every stock is skipped at line 46-51:
```python
pref = prefs.get((cid, exchange))
if pref is None:
    logger.warning("[PRICE-INGEST] no preference ... — skipped")
    continue
```

**Impact:** The price ingestion job is effectively non-functional for ALL stocks. It refreshes zero prices. The system works only because of Path 2 (background monitor) and the one-time write on `add_stock_to_watchlist`.

---

### Failure 3: Background Monitor Has No DB Fallback

**File:** `backend/main.py:99-125`
```python
if not info:
    skipped_count += 1    # ← silently skipped, no DB fallback
    continue

# ... later ...
if current_price and prev_close:
    broadcast_stock_update(...)
else:
    skipped_count += 1    # ← silently skipped, no DB fallback
```

**Impact:** If yfinance returns empty `info` or null `currentPrice`/`prevClose` for a symbol, that symbol gets no real-time price update. There is no fallback to `current_market_data`.

---

## 4. Root Cause of Stale `current_market_data` Prices

All 167 `current_market_data` rows are stale — **166 of 167 are >30 days old**. The most recent update across the entire table is **12.8 days old** (2026-07-12). Most portfolio stocks were last updated around **2026-05-22** (2+ months ago). The 7 watchlist-only stocks were last updated in **Jan/Feb 2026** (5-6 months ago).

### 4.1 Every Code Path That Can Write to `current_market_data`

There are exactly **5 mechanisms** that interact with this table. Only 2 can write. Neither runs periodically.

#### Mechanism 1: `price_ingestion_job.py` — THE ONLY PERIODIC WRITER (BROKEN)

**Trigger:** Scheduled by `scheduler_worker.py:286-293` → `PriceIngestionScheduler` → runs `refresh_all_prices()` every 5-30 min during market hours.

**Code path — exact trace:**

```python
# price_ingestion_job.py:31 — Step 1: Get all stocks to refresh
holdings = repo.get_all_active_holdings()     # queries ONLY portfolio_holdings
company_ids = {h["company_id"] for h in holdings if h.get("company_id")}

# price_ingestion_job.py:37 — Step 2: Get source preferences
prefs = repo.get_price_source_preferences(list(company_ids))
```

`get_price_source_preferences()` at `price_repository.py:33-51`:
```python
def get_price_source_preferences(self, company_ids):
    try:
        result = (
            self.client.table("price_source_preferences")   # ← TABLE DOES NOT EXIST
            .select("company_id, exchange, preferred_source")
            .in_("company_id", company_ids)
            .execute()
        )
        ...
    except Exception as e:
        logger.error("Failed to fetch price source preferences: %s", e)
        return {}    # ← RETURNS EMPTY DICT
```

```python
# price_ingestion_job.py:42-51 — Step 3: Route stocks to sources
for h in holdings:
    cid = h.get("company_id")
    exchange = h.get("exchange_override") or "UNKNOWN"
    pref = prefs.get((cid, exchange))    # ← ALWAYS None (prefs is {})
    if pref is None:
        logger.warning("[PRICE-INGEST] no preference for (company=%s, exchange=%s) — skipped", cid, exchange)
        continue        # ← SKIPS EVERY SINGLE STOCK
```

```python
# price_ingestion_job.py:100-108 — Step 4: Write results
for (cid, exchange), data in prices.items():    # prices is {} — loop body never executes
    repo.upsert_price_source(...)               # ← NEVER CALLED
```

**Result:** Zero prices refreshed per cycle. The `prices` dict is empty because all stocks were skipped. `upsert_price_source()` is never called. `current_market_data` is never updated.

**Why the table is missing:** The migration script at `backend/scripts/add_price_sources_table.sql` creates both `price_sources` and `price_source_preferences` tables and seeds them with data (lines 22-63). This SQL was **never executed** against the Supabase database.

#### Mechanism 2: `background_price_monitor()` — SSE BROADCAST (READ-ONLY)

**Trigger:** `main.py:149` — `asyncio.create_task(background_price_monitor())` runs inside FastAPI lifespan.

**Code path — exact trace:**

```python
# main.py:53-63 — Fetch live prices from yfinance
tickers = yf.Tickers(resolved_symbols)    # ← reads from yfinance API

# main.py:86-126 — Process each symbol
for symbol in ...:
    info = tickers.tickers.get(symbol, {})
    current_price = info.get("currentPrice") or info.get("regularMarketPrice")
    prev_close = info.get("previousClose")

    # main.py:115-117 — CDR adjustment (reads from DB, does NOT write)
    # main.py:122 — Broadcast to SSE queues
    broadcast_stock_update(symbol, current_price, change, change_percent)
```

`broadcast_stock_update()` at `api/watchlists.py:291-306`:
```python
async def broadcast_stock_update(symbol, price, change, change_percent):
    uids = symbol_subscribers.get(symbol, set())
    payload = {"type": "price_update", "symbol": symbol, "price": float(price), ...}
    for uid in uids:
        for queue in user_queues.get(uid, []):
            _safe_put(queue, payload)    # ← pushes to in-memory SSE queue ONLY
```

**Result:** Prices flow to in-memory SSE queues → frontend receives them → UI shows current prices. But `current_market_data` is **never written to**. The moment the server restarts, all live prices are lost.

#### Mechanism 3: `watchlist_service.py` `_update_market_data()` — ONE-TIME ON ADD

**Trigger:** Only from `add_stock_to_watchlist()` at `watchlist_service.py:399`:
```python
if current_price is not None:
    await self._update_market_data(company_id, symbol, current_price)
```

**Write at** `watchlist_service.py:659`:
```python
supabase.table('current_market_data').upsert(
    market_data,
    on_conflict='company_id'
).execute()
```

**Result:** Writes a single row when a stock is first added to a watchlist. Never called again for that stock. This is why watchlist timestamps match add dates (Jan-Feb 2026).

#### Mechanism 4: `portfolio_service.py` `_fetch_and_store_prices()` — DEAD CODE

**Trigger:** **Nothing.** Grep for `await.*_fetch_and_store_prices` and `self._fetch_and_store_prices` returns **zero results** across the entire codebase. This method at `portfolio_service.py:713` is never called.

**Even if it were called, it skips existing rows:**
```python
# portfolio_service.py:725-733
existing = (
    supabase.table("current_market_data")
    .select("company_id")
    .eq("company_id", cid)
    .limit(1)
    .execute()
)
needs_current = not existing.data    # ← False if row already exists

# portfolio_service.py:738
if not needs_current and not needs_history:
    logger.debug("Prices already exist for %s — skipping", symbol)
    return    # ← SKIPS companies that already have ANY row
```

**Result:** Once a company has a single stale price row, this method will never refresh it.

#### Mechanism 5: `price_utils.py` `build_price_snapshot()` — READ-ONLY

**Code at** `price_utils.py:74-122`:
- Lines 82-88: `SELECT` from `current_market_data` (read)
- Lines 90-91: Reads CDR maps (read)
- Lines 94-121: Pure computation (no DB calls)

Called by `watchlist_service.py:277` and `api/watchlists.py:325` — both consumers, not writers.

### 4.2 Complete Chain of Failures

```
PRICE STALENESS ROOT CAUSE CHAIN
================================

1. scripts/add_price_sources_table.sql was NEVER executed against Supabase
   └─ price_source_preferences table does NOT exist
      └─ price_repository.get_price_source_preferences() returns {} (empty dict)
         └─ price_ingestion_job.refresh_all_prices() skips ALL stocks (line 46-51)
            └─ prices dict remains {} — no stocks routed to any source
               └─ upsert_price_source() is NEVER called
                  └─ current_market_data is NEVER UPDATED by the periodic job
                     └─ Prices remain at whatever value was last written

2. background_price_monitor() fetches live prices via yfinance every 10s
   └─ BUT only pushes to in-memory SSE queues (broadcast_stock_update → _safe_put)
      └─ Does NOT write to current_market_data
         └─ Live prices are ephemeral — lost on server restart

3. WatchlistService._update_market_data() writes to current_market_data
   └─ BUT only called ONCE in add_stock_to_watchlist() (line 399)
      └─ Never called periodically
         └─ Watchlist prices frozen at add-time (Jan-Feb 2026)

4. PortfolioService._fetch_and_store_prices() CAN write to current_market_data
   └─ BUT it is DEAD CODE — never called from anywhere
      └─ Even if called, would skip companies with existing rows (line 738)

5. price_utils.build_price_snapshot() is READ-ONLY
   └─ Only reads current_market_data for UI rendering
      └─ Never writes
```

### 4.3 Why the 167 Rows Have Different Staleness

| Staleness | Date Range | Origin |
|-----------|------------|--------|
| ~5-6 months (watchlist stocks) | Jan 31 - Feb 20, 2026 | One-time write when stocks were added to watchlist via `add_stock_to_watchlist()` |
| ~2 months (portfolio stocks) | May 22-23, 2026 | One-time write during portfolio import — likely a bulk re-import that triggered `_update_market_data` for each company |
| ~12.8 days (1 row) | Jul 12, 2026 | Stray write — possibly from a one-off script or manual intervention |

### 4.4 Why Portfolio Stocks Appear "Fresh" in the UI

The background monitor fetches live prices from yfinance every 10s and broadcasts them via SSE. The frontend receives these and updates its React Query cache — so the UI **shows** current prices for portfolio stocks even though `current_market_data` is stale.

The staleness only matters in two scenarios:
1. **Initial page load:** `build_price_snapshot()` reads from `current_market_data` → returns stale prices with `isStale: true`
2. **yfinance outage:** If yfinance is temporarily unavailable, there's no fallback to DB prices

This is why the bug manifests differently:
- **Portfolio stocks:** Live price works (monitor → yfinance → SSE → frontend). Initial push may show stale price briefly.
- **Watchlist-only stocks:** No initial push (queue overflow) + no live monitor update → permanent `null` until monitor cycles.

### 4.5 The Fix

The root cause is that `scripts/add_price_sources_table.sql` was never executed. Without it, the ingestion job is dead. Two fixes are needed:

1. **Immediate (Fix 2):** Remove the preference dependency — route all stocks to yfinance grouped by exchange. This makes the ingestion job functional without the missing table.
2. **Structural (Fix 1):** Serve initial prices via REST API instead of the SSE queue. This eliminates the queue overflow entirely.

Once Fix 2 is deployed, the ingestion job will start refreshing `current_market_data` every 5-30 min during market hours. Within one cycle, all 167 rows will have fresh prices.

---

## 5. Evidence Summary — Diagnostic Results

| Test | Script | Result |
|------|--------|--------|
| yfinance single ticker | `diagnose_yfinance.py` | All 7 tickers return valid data |
| yfinance batch ticker | `diagnose_yfinance.py` | All 7 tickers return valid data |
| Watchlist query returns all 7 | `diagnose_watchlist_query.py` | All 7 stocks found with valid `companies` join |
| `current_market_data` has rows | `diagnose_monitor_flow.py` STEP 3 | All 7 have non-null `current_price` (stale) |
| `build_price_snapshot` would return them | `diagnose_monitor_flow.py` STEP 3 | All pass the `current_price is not None` check |
| Queue overflow drops first 13 | `simulate_queue_overflow.py` | RBLX, SIRI, AI, CHTR, NOW, U, INTU all dropped |
| `price_source_preferences` table | `diagnose_monitor_flow.py` STEP 5 | **Table does not exist** |
| Monitor would broadcast | `diagnose_monitor_flow.py` STEP 4 | All 7 PASS the `if current_price and prev_close` check |
| `companies` table has all 7 | `diagnose_monitor_flow.py` STEP 2 | All 7 have valid `company_id` |

---

## 5. Design Proposal

### Design Criteria

| Criterion | Description |
|-----------|-------------|
| **Correctness** | Every stock in any watchlist must display a price |
| **Defense-in-depth** | No single point of failure; multiple fallback paths |
| **Minimal blast radius** | Each fix is isolated; changes don't interact |
| **Performance** | No multiplied API calls; batch where possible |
| **Simplicity** | Prefer constants over architecture changes |
| **Observability** | Every skip/failure is logged, never silent |
| **Backward compatibility** | Existing working stocks remain unaffected |

---

### Fix 1: Separate Initial Prices (REST) from Live Updates (SSE)

**Root cause:** The initial push puts ALL watchlist prices into a bounded SSE queue. With 63 stocks and `maxsize=50`, the first 13 are silently dropped. Bumping the queue size is a band-aid — any future watchlist growth (>500) breaks again.

**Design: Initial prices via REST API, live updates via SSE only.**

#### 1a. New REST endpoint — `GET /api/watchlists/:id/prices`

**File:** `backend/api/watchlists.py`

```python
@router.get("/prices/{watchlist_id}")
async def get_watchlist_prices(
    watchlist_id: int,
    current_user: AuthenticatedUser = Depends(require_auth),
):
    """Return current prices for all stocks in a watchlist.
    
    Used by the frontend on initial load instead of relying on the SSE
    initial push. Paginated at 50 stocks per page.
    """
    page = max(1, int(request.query_params.get("page", 1)))
    page_size = min(100, max(1, int(request.query_params.get("page_size", 50))))

    # Get watchlist + companies (same query as _push_initial_prices)
    wl = await _get_user_watchlist_for_prices(watchlist_id, current_user.id)
    if wl is None:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    stocks = wl.get("stocks", [])
    total = len(stocks)
    start = (page - 1) * page_size
    end = min(start + page_size, total)
    page_stocks = stocks[start:end]

    # Batch price snapshot (single DB query, same as build_price_snapshot)
    price_snapshot = build_price_snapshot([s["company_id"] for s in page_stocks])

    results = []
    for s in page_stocks:
        cid = s["company_id"]
        ps = price_snapshot.get(cid, {})
        results.append({
            "company_id": cid,
            "symbol": s["symbol"],
            "price": ps.get("price"),
            "prevClose": ps.get("prevClose"),
            "isStale": ps.get("isStale", True),
            "lastUpdated": ps.get("lastUpdated"),
            "source": ps.get("source", "unknown"),
        })

    return {
        "watchlist_id": watchlist_id,
        "prices": results,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }
```

**Pagination rationale:**
- Watchlist max: 50 stocks per watchlist (line 27). `page_size=50` returns everything in one call.
- If `MAX_STOCKS_PER_WATCHLIST` increases in the future, pagination handles it automatically.
- Frontend calls `GET /api/watchlists/{id}/prices?page_size=50` on mount — single request for current config.

#### 1b. Remove initial push from SSE endpoint

**File:** `backend/api/watchlists.py:152-207`

Remove `_push_initial_prices(queue, auth_id, watchlist_ids)` from the SSE generator. The SSE stream now only handles live updates:

```python
# Before (lines 152-155)
async def event_generator():
    auth_id = current_user.id
    queue = asyncio.Queue(maxsize=50)
    await _push_initial_prices(queue, auth_id, watchlist_ids)  # ← REMOVE THIS

# After
async def event_generator():
    auth_id = current_user.id
    queue = asyncio.Queue(maxsize=200)  # Only live updates — much smaller
```

The queue now only receives live broadcast events (price updates, not the initial snapshot). `maxsize=200` is generous for live updates — the monitor pushes at most ~63 events per 10s cycle, and the consumer drains continuously.

#### 1c. Frontend — fetch initial prices via REST

**File:** `web/src/hooks/usePriceData.ts`

```typescript
// Before: rely on SSE initial push to populate cache
export function usePriceData(symbol: string) {
  return useQuery({
    queryKey: ["price", symbol],
    queryFn: () => fetchPriceFromAPI(symbol),
    gcTime: GC.PRICE,
    staleTime: GC.PRICE,
  });
}

// After: seed cache from REST endpoint on watchlist load
export function useWatchlistPrices(watchlistId: number) {
  return useQuery({
    queryKey: ["watchlistPrices", watchlistId],
    queryFn: async () => {
      const res = await fetch(`/api/watchlists/${watchlistId}/prices?page_size=50`);
      const data = await res.json();
      // Populate individual price caches so usePriceData works immediately
      const prices: Record<string, PriceData> = {};
      for (const p of data.prices) {
        prices[p.symbol] = p;
      }
      return prices;
    },
    gcTime: GC.PRICE,
    staleTime: 60_000, // 1 min — SSE will keep it fresh
  });
}
```

**File:** `web/src/providers/GlobalSSEProvider.tsx`

On SSE connect, only subscribe to live updates — no initial price push expected from the stream. The REST endpoint handles initial data.

**What this does NOT fix:**
- Does not fix the ingestion job (Failure 2)
- Does not add DB fallback to the monitor (Failure 3)

**Validation against code paths:**

| Scenario | Before Fix | After Fix |
|----------|-----------|-----------|
| 63-stock watchlist initial load | 13 stocks dropped (queue overflow) | All 63 delivered via REST (paginated) |
| Watchlist > 50 stocks | Queue overflows, first N-50 dropped | REST pagination handles any size |
| Live price updates after initial load | Bounded queue (drop-oldest) | Unbounded initial load + bounded live queue (drop-oldest) |
| SSE reconnect | Old: re-pushes all via queue. New: only live events | REST fetch on reconnect (no queue pressure) |
| Memory per connection | 50 × 200B = 10KB (queue) | REST: 0 queue. Live: 200 × 200B = 40KB |
| Multiple users with overlapping symbols | Same behavior | REST is per-user. SSE fan-out unchanged |

---

### Fix 2: Expand Price Ingestion to Cover Watchlist Stocks

#### 2a. New Repository Method

**File:** `backend/infrastructure/repositories/price_repository.py`

**Add new method `get_all_active_symbols()`:**
```python
def get_all_active_symbols(self) -> List[Dict[str, Any]]:
    """Returns ALL unique (company_id, symbol, exchange) that any user
    cares about — portfolio holdings AND watchlist items combined.
    
    Deduplicates by company_id so a stock in both is only returned once.
    """
    seen: Dict[int, Dict[str, Any]] = {}

    # 1) Portfolio holdings (existing path)
    holdings = self.get_all_active_holdings()
    for h in holdings:
        cid = h.get("company_id")
        if cid and cid not in seen:
            seen[cid] = {
                "company_id": cid,
                "symbol": h["symbol"],
                "exchange_override": h.get("exchange_override") or "UNKNOWN",
            }

    # 2) Watchlist items (new path)
    try:
        wl_result = (
            self.client.table("watchlist_items")
            .select("company_id, companies(ticker_symbol, exchange)")
            .execute()
        )
        for row in (wl_result.data or []):
            cid = row.get("company_id")
            co = row.get("companies")
            if cid and co and cid not in seen:
                seen[cid] = {
                    "company_id": cid,
                    "symbol": co["ticker_symbol"],
                    "exchange_override": co.get("exchange") or "UNKNOWN",
                }
    except Exception as e:
        logger.error("Failed to fetch watchlist items for price refresh: %s", e)

    return list(seen.values())
```

**Query cost:** 2 global queries (same pattern as existing `get_all_active_holdings`).

**Deduplication:** Company in both portfolio and watchlist appears once.

**Error handling:** If `watchlist_items` query fails, falls back to portfolio-only (graceful degradation).

#### 2b. Rewrite Preference Logic — `supabase_market_data` Is a No-Op

**File:** `backend/application/jobs/price_ingestion_job.py`

**CRITICAL FINDING:** The `supabase_market_data` source is a no-op — `_fetch_supabase_prices()` at line 289-302 reads from `current_market_data` and the result is written back to `current_market_data`. This means any stock routed to `supabase_market_data` gets its price "refreshed" with the same stale value.

The original proposed fallback ("TOR → yfinance_tor, else → supabase_market_data") is **WRONG** — it would route US-listed watchlist stocks to a no-op source.

**Correct approach:** Route ALL watchlist stocks through yfinance, grouped by exchange:

```python
# Before (lines 42-55)
for h in holdings:
    cid = h.get("company_id")
    exchange = h.get("exchange_override") or "UNKNOWN"
    pref = prefs.get((cid, exchange))
    if pref is None:
        logger.warning("... skipped")
        continue

# After
yfinance_items_by_exchange: Dict[str, list] = {}
supabase_items = set()

for h in symbols:
    cid = h.get("company_id")
    exchange = h.get("exchange_override") or "UNKNOWN"
    pref = prefs.get((cid, exchange))

    if pref is None:
        # No preference — route to yfinance (the only source that actually fetches fresh data)
        if exchange not in yfinance_items_by_exchange:
            yfinance_items_by_exchange[exchange] = []
        yfinance_items_by_exchange[exchange].append((cid, h["symbol"], exchange))
        logger.debug(
            "[PRICE-INGEST] no preference for (company=%s, exchange=%s) — defaulting to yfinance",
            cid, exchange,
        )
    elif pref == "yfinance_tor":
        if exchange not in yfinance_items_by_exchange:
            yfinance_items_by_exchange[exchange] = []
        yfinance_items_by_exchange[exchange].append((cid, h["symbol"], exchange))
    elif pref == "supabase_market_data":
        supabase_items.add(cid)
    elif pref == "price_history_fallback":
        # price_history is not a real-time source — route to yfinance instead
        if exchange not in yfinance_items_by_exchange:
            yfinance_items_by_exchange[exchange] = []
        yfinance_items_by_exchange[exchange].append((cid, h["symbol"], exchange))
```

**And update the yfinance batch fetch (lines 59-84) to handle multiple exchanges:**

```python
# Before: single exchange assumed
if yfinance_items:
    symbols = list(set(item[1] for item in yfinance_items))
    exchange = yfinance_items[0][2]
    yf_results = await _fetch_yfinance_batch(symbols, exchange, ...)

# After: group by exchange
if yfinance_items_by_exchange:
    for exchange, items in yfinance_items_by_exchange.items():
        syms = list(set(item[1] for item in items))
        yf_results = await _fetch_yfinance_batch(syms, exchange, ...)
        symbol_to_cid = {item[1]: item[0] for item in items}
        for sym, result in yf_results.items():
            cid = symbol_to_cid.get(sym)
            if result["error"]:
                logger.warning("[PRICE-INGEST] symbol=%s exchange=%s error=%s", sym, exchange, result["error"])
                continue
            if cid and result["price"] is not None:
                prices[(cid, exchange)] = {
                    "price": result["price"],
                    "source": "yfinance",
                    "currency": "CAD" if exchange == "TOR" else "USD",
                    "ttl_seconds": 300,
                }
```

**Why this design:**
- `_resolve_symbol()` in `yfinance_provider.py:33-46` handles exchange suffixes — TOR stocks get `.TO` appended, US stocks are returned as-is
- Grouping by exchange ensures each batch call uses the correct suffix
- The `supabase_market_data` and `price_history_fallback` sources are effectively dead code — yfinance is the only source that fetches fresh prices
- No schema migration needed

#### 2c. Update `refresh_all_prices()` to Use New Method

**File:** `backend/application/jobs/price_ingestion_job.py:30-35`

```python
# Before
async def refresh_all_prices():
    holdings = repo.get_all_active_holdings()
    company_ids = {h["company_id"] for h in holdings if h.get("company_id")}

# After
async def refresh_all_prices():
    symbols = repo.get_all_active_symbols()
    company_ids = {s["company_id"] for s in symbols if s.get("company_id")}
```

And update line 42 to iterate over `symbols` instead of `holdings`.

**Impact on timing:**
- Current: processes ~150 portfolio holdings
- After: processes ~150 portfolio + ~50-100 watchlist stocks
- yfinance batch with `Semaphore(max_concurrent=5)` handles the increase
- Worst case: cycle takes ~2x longer (still under 60s, well within the 5-min interval)

**Validation against code paths:**

| Scenario | Before Fix | After Fix |
|----------|-----------|-----------|
| Portfolio stock refresh | Works (if preferences exist) | Works (same path) |
| Watchlist-only stock refresh | **Never refreshed** | Refreshed every 5-30 min |
| Stock in both portfolio + watchlist | Refreshed once | Refreshed once (deduped) |
| `price_source_preferences` missing | All stocks skipped | Fallback infers from exchange |
| `watchlist_items` query fails | N/A | Falls back to portfolio-only |
| Ingestion job timing | ~30s per cycle | ~60s per cycle (acceptable) |

---

### Fix 3: Background Monitor DB Fallback

**File:** `backend/main.py:86-125`

**Add fallback after yfinance extraction fails:**

```python
# After line 105 (where current_price and prev_close are extracted)
# and BEFORE the final if check at line 119:

if not (current_price and prev_close):
    # yfinance didn't return both values — try current_market_data as fallback
    cid = sym_to_cid.get(symbol)
    if cid is not None:
        try:
            md = _sb.table("current_market_data") \
                .select("current_price, close_price, last_updated") \
                .eq("company_id", cid) \
                .execute()
            row = (md.data or [{}])[0]
            fb_price = row.get("current_price")
            fb_close = row.get("close_price")
            if fb_price and fb_close:
                current_price = float(fb_price)
                prev_close = float(fb_close)
                logger.debug(
                    "[PRICE-MONITOR] %s: yfinance unavailable, used DB fallback price=%s",
                    symbol, current_price,
                )
        except Exception as e:
            logger.debug("[PRICE-MONITOR] %s: DB fallback failed: %s", symbol, e)
```

**Rationale:**
- Same query pattern as `build_price_snapshot` — consistent with codebase
- One extra DB query per failed symbol per cycle — failures are rare (our test showed all 7 work)
- This is a safety net, not a hot path
- Logged as debug, not warning — expected fallback behavior
- yfinance is always tried first (faster, more current); DB is fallback

**Validation against code paths:**

| Scenario | Before Fix | After Fix |
|----------|-----------|-----------|
| yfinance returns valid data | Broadcast live price | Broadcast live price (unchanged) |
| yfinance returns empty `.info` | **Symbol skipped forever** | Falls back to DB price |
| yfinance returns null `currentPrice` | **Symbol skipped forever** | Falls back to DB price |
| DB also has no row | N/A | Stays skipped (no data available) |
| DB price is stale | N/A | Broadcasts stale price with `isStale` flag |
| Performance impact | 0 extra queries | +1 query per failed symbol (rare) |

---

## 6. Validation Against All 10 Code Paths

### Scenario 1: SSE Connect → Initial Push

**Path:** `watchlists.py:152-207` → `_push_initial_prices` → `build_price_snapshot` → `_safe_put`

**Before fix:** 63 stocks → 13 dropped by queue overflow → client sees null for first 13.

**After Fix 1 (REST API):** 63 stocks → fetched via `GET /api/watchlists/:id/prices?page_size=50` → all 63 returned in one page → client seeds cache → `usePriceData` returns valid prices immediately.

**After Fix 2 (ingestion):** `current_market_data` stays fresh → REST endpoint returns non-stale prices → `isStale: false` in response.

**After Fix 3 (monitor fallback):** No change to this path (monitor is not involved in initial load).

**Edge case — reconnect:** Old `finally` at line 189-200 checks `if not user_queues.get(auth_id)` before cleaning up subscriptions. If new connection already added a queue, old cleanup is skipped. Safe.

---

### Scenario 2: Background Monitor Cycle

**Path:** `main.py:35-133` → `yf.Tickers()` → per-symbol extraction → `broadcast_stock_update`

**Before fix:** If yfinance fails for a symbol, it's skipped with `skipped_count += 1`.

**After Fix 3:** If yfinance fails, falls back to `current_market_data` → broadcasts DB price.

**Edge case — 189 tickers:** The `yf.Tickers()` call with 189 resolved symbols (63 × 3 suffixes) is a large batch. Our diagnostic test used 11 tickers. The production batch may behave differently. Fix 3 provides a safety net for symbols that fail in the large batch.

**Edge case — CDR adjustment:** `apply_cdr_adjustment` at line 112-117 uses batch-fetched maps. Watchlist-only `.TO` stocks won't have CDR adjustment (since `tor_cids` only includes portfolio_holdings with `exchange_override='TOR'`). This is a pre-existing limitation, not introduced by these fixes.

---

### Scenario 3: Price Ingestion Job

**Path:** `price_ingestion_job.py:29-119` → `get_all_active_holdings` → preference lookup → yfinance/supabase fetch → upsert

**Before fix:** Only processes `portfolio_holdings`. Watchlist-only stocks never refreshed. `price_source_preferences` table missing → all stocks skipped.

**After Fix 2:** Processes both `portfolio_holdings` and `watchlist_items`. Fallback infers exchange → correct source selected. Watchlist stocks now refreshed.

**Edge case — company in both:** `company_ids` set deduplicates → one fetch, one upsert. No duplicate work.

**Edge case — yfinance timeout:** `_fetch_yfinance_batch` uses `Semaphore(max_concurrent=5)` and `per_symbol_timeout=10`. More symbols = longer cycle but stays within timeout bounds.

---

### Scenario 4: Add Stock to Watchlist

**Path:** `watchlist_service.py:344-420` → `_get_or_create_company` → `get_stock_details` → `_update_market_data` → insert `watchlist_items`

**Before fix:** One-time write to `current_market_data` on add. No ongoing refresh.

**After Fix 2:** One-time write + ongoing refresh via ingestion job.

**Edge case — double YF call:** `get_stock_details` is called twice (line 391 and line 646). Pre-existing inefficiency, not introduced by these fixes.

**Edge case — 51st stock:** Adding a 51st stock to a 50-stock watchlist: REST pagination handles it automatically (`page_size=50` → 2 pages). No queue overflow possible.

---

### Scenario 5: Frontend Price Reading

**Path:** `GlobalSSEProvider.tsx:116-173` → `usePriceData` → `StockCard`

**Before fix:** Stale update check at line 160: `data.lastUpdated < current.lastUpdated` → drops older events. On first load, `current` is null → check passes.

**After fix:** No change to frontend code. The fix ensures SSE events are sent for all symbols, so the frontend receives them.

**Edge case — `gcTime`:** `usePriceData` uses `gcTime: GC.PRICE` (5 min). Prices survive navigation within 5 min. After 5 min, cache is cleared → shows placeholder until next SSE event.

---

### Scenario 6: Stale Price Handling

**Path:** `price_utils.py:61-71` → `_is_price_fresh` → `build_price_snapshot`

**Before fix:** `STALE_THRESHOLD_MIN = 5`. Prices older than 5 min → `isStale: true`. Stale prices ARE still sent (not suppressed).

**After Fix 2:** Ingestion job refreshes `current_market_data` every 5-30 min → prices stay within the 5-min freshness window during market hours → REST endpoint returns non-stale prices.

**After Fix 3:** Monitor fallback sends DB prices → may be stale → `isStale: true` flag propagates to frontend.

**Edge case — market closed:** During off-hours, ingestion job is suspended (scheduler returns empty plan). Prices from the last market-hours cycle remain in `current_market_data`. `isStale: true` is correct behavior.

---

### Scenario 7: CDR Adjustment

**Path:** `price_utils.py:11-58` → `get_cdr_maps_for_companies` → `apply_cdr_adjustment`

**Before fix:** CDR adjustment applies to stocks in `tor_cids` (from `portfolio_holdings` with `exchange_override='TOR'`).

**After fix:** No change. CDR adjustment logic is independent of these fixes.

**Pre-existing limitation:** Watchlist-only `.TO` stocks won't get CDR-adjusted because `tor_cids` only includes portfolio holdings. This is outside the scope of these fixes.

---

### Scenario 8: Multiple Users

**Path:** `symbol_subscribers` (in-memory dict) → `broadcast_stock_update` fan-out

**Before fix:** Each user has their own queue. `symbol_subscribers` is shared across users. Background monitor fetches deduplicated symbols.

**After fix:** No change. The queue size reduction (Fix 1b: maxsize=200 for live-only) is per-connection. Multiple users with overlapping watchlists benefit from shared yfinance fetches.

**Edge case — 100 concurrent users with 63 stocks each:** 100 queues × 200 slots × 200 bytes = 4MB. Negligible. Initial prices served via REST (no queue pressure).

---

### Scenario 9: SSE Disconnect/Reconnect

**Path:** `watchlists.py:189-200` (finally block) → `GlobalSSEProvider.tsx:195-209` (reconnect)

**Before fix:** Race condition: old `finally` could clean up new connection's subscriptions if timing is unlucky. But `if not user_queues.get(auth_id)` guard prevents this.

**After fix:** No change. The guard at line 193-194 is sufficient.

**Edge case — rapid reconnect:** Old `finally` runs after new connection sets up. New queue already exists → cleanup skipped. On reconnect, frontend re-fetches REST endpoint → fresh prices without queue pressure.

---

### Scenario 10: `get_all_active_symbols()` Impact

**Path:** New method in `price_repository.py` → called by `refresh_all_prices` (Fix 2c)

**Before fix:** 1 query (`portfolio_holdings`). ~150 stocks.

**After fix:** 2 queries (`portfolio_holdings` + `watchlist_items JOIN companies`). ~200-250 stocks.

**Query cost:** +1 query (~50-200ms). Negligible vs yfinance HTTP calls.

**Overlap handling:** `seen` dict deduplicates by `company_id`. No duplicate work.

**Error handling:** If `watchlist_items` query fails, returns portfolio-only (graceful degradation).

---

## 7. Risk Assessment

| Fix | Risk | Mitigation |
|-----|------|-----------|
| Fix 1 (REST API) | New endpoint + frontend change | Paginated endpoint is simple. Frontend change is isolated to `usePriceData` hook. |
| Fix 2 (ingestion expansion) | More symbols = longer job cycles | Semaphore limits concurrency. 60s cycle is acceptable. |
| Fix 2 (preference fallback) | Wrong source for unknown exchange | Only affects new watchlist stocks. Logged as debug. |
| Fix 3 (monitor DB fallback) | Extra DB query per failed symbol | Failures are rare. Query is fast (single PK lookup). |

---

## 8. Deployment Plan

**Phase 1 (Immediate — zero risk):**
- Fix 1a: Add `GET /api/watchlists/:id/prices` REST endpoint
- Fix 1b: Remove initial push from SSE endpoint
- Fix 1c: Frontend fetches initial prices via REST on watchlist load
- Deploy and verify all 63 stocks get initial prices via REST

**Phase 2 (Same day — low risk):**
- Fix 3: Add DB fallback to background monitor
- Deploy and verify monitor broadcasts for all symbols

**Phase 3 (Next sprint — moderate risk):**
- Fix 2a: Add `get_all_active_symbols()` to `PriceRepository`
- Fix 2b: Add preference fallback in `price_ingestion_job.py` (yfinance for all, grouped by exchange)
- Fix 2c: Update `refresh_all_prices()` to use new method
- Test with scheduler worker running
- Verify `current_market_data` stays fresh during market hours

---

## 9. Files to Modify

| File | Change | Fix # |
|------|--------|-------|
| `backend/api/watchlists.py` | Add `GET /prices/{watchlist_id}` REST endpoint | 1a |
| `backend/api/watchlists.py:152-155` | Remove `_push_initial_prices` from SSE generator | 1b |
| `web/src/hooks/usePriceData.ts` | Add `useWatchlistPrices()` REST hook | 1c |
| `backend/infrastructure/repositories/price_repository.py` | Add `get_all_active_symbols()` method | 2a |
| `backend/application/jobs/price_ingestion_job.py:31` | Use `get_all_active_symbols()` instead of `get_all_active_holdings()` | 2c |
| `backend/application/jobs/price_ingestion_job.py:42-55` | Rewrite preference logic (yfinance for all, grouped by exchange) | 2b |
| `backend/main.py:105-125` | Add DB fallback when yfinance fails | 3 |

---

## 10. Fact-Check Results

All findings verified against live database and source code on 2026-07-25.

### Verified Findings

| # | Claim | Evidence | Status |
|---|-------|----------|--------|
| 1 | Queue `maxsize=50` at `watchlists.py:160` | Source code read — confirmed `asyncio.Queue(maxsize=50)` | **CONFIRMED** |
| 2 | Watchlist has 63 stocks | DB query: all 5 users have 63 symbols | **CONFIRMED** |
| 3 | 63 > 50 → first 13 dropped | Simulation: `simulate_queue_overflow.py` drops VOO, VTI, BTO, ET, ARI, KMI, RBLX, SIRI, AI, CHTR, NOW, U, INTU | **CONFIRMED** |
| 4 | RBLX/SIRI/AI/CHTR/NOW/U/INTU are in first 13 | DB query: watchlist iteration order matches simulation | **CONFIRMED** |
| 5 | `price_source_preferences` table doesn't exist | Supabase API error: `PGRST205: Could not find the table 'public.price_source_preferences'` | **CONFIRMED** |
| 6 | Ingestion job queries only `portfolio_holdings` | Source: `price_repository.py:80-87` — `self.client.table("portfolio_holdings")` | **CONFIRMED** |
| 7 | 52 of 63 watchlist stocks are watchlist-only | DB query: 11 overlap (CLM, CRF, DCBO, DNUT, F, FIG, FOUR, GIS, MSFT, U, VZ), 52 watchlist-only | **CONFIRMED** |
| 8 | `current_market_data` has rows for all 63 | DB query: 167 total rows, all 63 watchlist company_ids present | **CONFIRMED** |
| 9 | Prices are 5-6 months stale | DB query: RBLX last_updated=2026-01-31, AI=2026-01-31, CHTR=2026-02-01, NOW=2026-02-01, SIRI=2026-01-31, INTU=2026-02-20, U=2026-02-20 | **CONFIRMED** |
| 10 | yfinance returns valid data for all 7 | Script: all 7 PASS in both single and batch mode with 21 tickers | **CONFIRMED** |
| 11 | `STALE_THRESHOLD_MIN = 5` | Source: `price_utils.py:8` — confirmed `STALE_THRESHOLD_MIN = 5` | **CONFIRMED** |
| 12 | `MAX_WATCHLISTS_PER_USER = 5`, `MAX_STOCKS_PER_WATCHLIST = 50` | Source: `watchlists.py:26-27` — confirmed | **CONFIRMED** |
| 13 | `SSE_UPDATE_INTERVAL_SECONDS = 10` | Source: `config.py:182-183` — confirmed default=10 | **CONFIRMED** |
| 14 | Background monitor has no DB fallback | Source: `main.py:99-125` — skips with `skipped_count += 1`, no DB read | **CONFIRMED** |
| 15 | CDR adjustment only for portfolio TOR stocks | Source: `price_utils.py:33-38` — `tor_cids` built from `portfolio_holdings` WHERE `exchange_override='TOR'` | **CONFIRMED** |
| 16 | SSE disconnect guard works | Source: `watchlists.py:193` — `if not user_queues.get(auth_id)` prevents cleanup if new queue exists | **CONFIRMED** |
| 17 | Watchlist stocks span 6 exchanges | DB query: ASE(2), NGM(2), NMS(13), NYQ(34), PCX(6), TOR(6) | **CONFIRMED** |

### Corrections to Original Document

| # | Original Claim | Corrected Finding | Impact |
|---|---------------|-------------------|--------|
| C1 | "Fix 2b: TOR → yfinance_tor, else → supabase_market_data" | **`supabase_market_data` is a no-op** — reads from `current_market_data` and writes back the same value. All watchlist stocks must route to yfinance. | **Fix 2b rewritten** — now groups yfinance items by exchange. All stocks default to yfinance. |
| C2 | "52 watchlist-only stocks" not mentioned | **52 of 63 watchlist stocks are watchlist-only** (not in any portfolio). The ingestion job doesn't refresh ANY of them. | **Scope is much larger** — not just 7 stocks, but 52 |
| C3 | "current_market_data has stale but non-null prices" | Prices are **5-6 months stale** (Jan/Feb 2026). `STALE_THRESHOLD_MIN = 5` means these are 50,000+ minutes stale. | **Staleness is extreme** — not "slightly stale" |
| C4 | "Ingestion job processes ~150 portfolio holdings" | Ingestion job processes 118 portfolio holdings but **all are skipped** because `price_source_preferences` table doesn't exist | **Ingestion job is completely non-functional** |
| C5 | "Fix 2 memory impact: ~2x longer cycles" | With 118 portfolio + 52 watchlist = 170 stocks (not 250). But the ingestion job is currently broken, so any fix is an improvement. | **More accurate scope** |

### Additional Findings Not in Original Document

| # | Finding | Evidence |
|---|---------|----------|
| A1 | `EXCHANGE_SUFFIX_MAP` handles TOR→.TO, VAN→.V | Source: `yfinance_provider.py:15-19` |
| A2 | `_resolve_symbol()` appends suffix for Canadian exchanges, returns as-is for US | Source: `yfinance_provider.py:33-46` |
| A3 | `_fetch_yfinance_batch()` takes single `exchange` param — broken for mixed exchanges | Source: `price_ingestion_job.py:60-61` — `exchange = yfinance_items[0][2]` |
| A4 | `add_stock_to_watchlist` calls `get_stock_details` twice (lines 391 and 646) | Source: `watchlist_service.py:391,646` — wasted HTTP call |
| A5 | All 5 users have identical 63-stock watchlist | DB query: same symbols across all users |
| A6 | Watchlist exchange distribution: NYQ(34), NMS(13), PCX(6), TOR(6), ASE(2), NGM(2) | DB query on `companies.exchange` |

### Fact-Check: Fix Proposals (Pre-Implementation)

| Fix | Verdict | Notes |
|-----|---------|-------|
| Fix 1: REST API for initial prices | **CORRECT** | Separates initial load (paginated REST) from live updates (SSE). Eliminates queue overflow entirely. |
| Fix 2a: `get_all_active_symbols()` | **CORRECT** | 2 global queries, deduplication by company_id, graceful degradation if watchlist query fails. |
| Fix 2b: Preference fallback | **WAS WRONG — CORRECTED** | Original: `supabase_market_data` is a no-op. Corrected: route all to yfinance grouped by exchange. |
| Fix 2c: Use new method | **CORRECT** | Simple swap of `get_all_active_holdings()` → `get_all_active_symbols()`. |
| Fix 3: Monitor DB fallback | **CORRECT** | Placement after line 117 (CDR adjustment) and before line 119 (if check) is correct. Single PK lookup is fast. |

### Fact-Check: Implementation Verification (Post-Implementation)

All fixes verified against actual code on 2026-07-25.

| Fix | Claim | Actual Code | Status |
|-----|-------|-------------|--------|
| 1a | `GET /watchlists/{watchlist_id}/prices` exists | `@router.get("/watchlists/{watchlist_id}/prices")` with `@limiter.limit("30/minute")` | **CONFIRMED** |
| 1a | Queries `watchlist_items` with `companies` join | `.select("companies(company_id, ticker_symbol)").eq("watchlist_id", watchlist_id)` | **CONFIRMED** |
| 1a | Uses `build_price_snapshot` | `build_price_snapshot(supabase, company_ids, source="db_cached")` | **CONFIRMED** |
| 1a | Returns paginated results | Returns `pagination` dict with `page`, `page_size`, `total`, `total_pages` | **CONFIRMED** |
| 1b | `_push_initial_prices` removed from SSE generator | No call in `event_generator()`; comment explains REST handles initial prices | **CONFIRMED** |
| 1b | Queue `maxsize` now 200 | `asyncio.Queue(maxsize=200)` at line 160 | **CONFIRMED** |
| 1c | `useWatchlistPrices` exists | Exported from `usePriceData.ts` | **CONFIRMED** |
| 1c | Fetches from `/api/proxy/watchlists/${watchlistId}/prices` | `fetch(\`/api/proxy/watchlists/${watchlistId}/prices?page_size=50\`)` | **CONFIRMED** |
| 1c | Seeds individual price caches | `queryClient.setQueryData<CachedPrice>(QK.price(p.symbol), cached)` | **CONFIRMED** |
| 2a | `get_all_active_symbols` exists | New method in `PriceRepository` querying both `portfolio_holdings` and `watchlist_items` | **CONFIRMED** |
| 2a | Deduplicates by `company_id` | Uses `seen` dict keyed by `company_id` | **CONFIRMED** |
| 2a | Graceful degradation on failure | `try/except` block logs error and continues | **CONFIRMED** |
| 2b | All stocks routed to yfinance | No `pref` lookup; all added to `yfinance_items_by_exchange` | **CONFIRMED** |
| 2b | Stocks grouped by exchange | `yfinance_items_by_exchange` dict; loop processes each exchange separately | **CONFIRMED** |
| 2b | `supabase_market_data` path removed | No reference in file | **CONFIRMED** |
| 2b | `_fetch_supabase_prices` removed | Function deleted from file | **CONFIRMED** |
| 2c | Uses `get_all_active_symbols()` | Line 31: `symbols = repo.get_all_active_symbols()` | **CONFIRMED** |
| 3 | DB fallback exists after CDR adjustment | Lines 119-140: queries `current_market_data` when yfinance fails | **CONFIRMED** |
| 3 | Logs the fallback | `logger.debug("[PRICE-MONITOR] %s: yfinance unavailable, used DB fallback price=%s", ...)` | **CONFIRMED** |
