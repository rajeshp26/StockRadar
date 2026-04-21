# StockerPro SSE Subscription System - Design Document

**Version:** 1.0
**Date:** 2026-04-15
**Status:** Ready for Implementation

---

## 1. Problem Statement

When a user adds a stock to their watchlist, the current price is not updating in the UI due to:
1. Missing repository methods causing 500 errors on delete
2. SSE subscriptions not updated dynamically when stocks are added/removed
3. Duplicate YFinance fetches (service and API both fetch price)

---

## 2. Design Principles

| Principle | Application |
|-----------|-------------|
| **Single Responsibility** | Service = business logic. API = orchestration. SSE = subscriptions. |
| **DRY** | Service returns complete data. API doesn't re-fetch. |
| **YAGNI** | No event bus, no Redis, no new frameworks. |
| **Transaction Safety** | Check state BEFORE mutation. |
| **Non-Breaking** | Add keys to return dict, don't remove existing ones. |

---

## 3. Solution Overview

### 3.1 Add Stock Flow

```
User POST /watchlist-items
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 1. Validate (auth, ownership, 50 stock cap)           │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 2. Service.add_stock()                                  │
│    - Get/create company                                  │
│    - Fetch price from YFinance (ONCE)                   │
│    - Update market data                                 │
│    - Insert watchlist_item                              │
│    - Returns: COMPLETE data (price, change, name)     │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 3. Subscribe to SSE                                     │
│    subscribe_symbol(symbol, auth_id)                     │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 4. Broadcast current price (with retry)                  │
│    broadcast_stock_update(...)                            │
│    Uses service data — NO re-fetch needed               │
└────────────────────────────────────────────────────────────┘
         │
         ▼
      Return 201
```

### 3.2 Delete Stock Flow

```
User POST /watchlist-items/delete
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 1. Verify ownership, get symbol                         │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 2. Check BEFORE delete: does user have symbol else?     │
│    remaining = repo.user_has_symbol(user_id, symbol)     │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 3. Delete from database                                 │
│    repo.delete_item(item_id)                             │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 4. If NOT remaining: unsubscribe                         │
│    if not remaining: unsubscribe_symbol(symbol, auth_id) │
└────────────────────────────────────────────────────────────┘
         │
         ▼
      Return 204
```

### 3.3 Delete Watchlist Flow

```
User DELETE /watchlists/{id}
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 1. Verify ownership, not default                       │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 2. Get symbols BEFORE delete                             │
│    items = repo.get_items_by_watchlist_id(id)            │
│    watchlist_symbols = {extract ticker_symbols}          │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 3. Delete watchlist (cascade deletes items)               │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 4. Single query: get remaining symbols                   │
│    remaining = set(repo.get_user_symbols(user_id))       │
│    orphaned = watchlist_symbols - remaining               │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ 5. Unsubscribe all orphaned symbols                      │
│    for symbol in orphaned:                               │
│        unsubscribe_symbol(symbol, auth_id)                │
└────────────────────────────────────────────────────────────┘
         │
         ▼
      Return 204
```

---

## 4. Files to Change

| File | Change | Lines |
|------|--------|-------|
| `domain/interfaces/repository.py` | Add 2 abstract methods | ~10 |
| `supabase_repository.py` | Add 4 methods | ~50 |
| `watchlist_service.py` | Enhance return dict, add 1 method | ~50 |
| `watchlists.py` | Add SSE helpers, update delete | ~35 |
| `watchlist_items.py` | Add SSE orchestration, remove re-fetch | ~25 |
| **Total** | | **~170 lines** |

---

## 5. Implementation Details

### 5.1 Repository Interface

**File:** `domain/interfaces/repository.py`

```python
@abstractmethod
def delete_item(self, item_id: int) -> None:
    pass

@abstractmethod
def update_item_targets(
    self,
    item_id: int,
    target_buy: Optional[float],
    target_sell: Optional[float]
) -> Optional[Dict[str, Any]]:
    pass
```

### 5.2 Repository Implementation

**File:** `infrastructure/repositories/supabase_repository.py`

```python
def delete_item(self, item_id: int) -> None:
    """Delete a watchlist item by ID."""
    self.client.table("watchlist_items").delete().eq("watchlist_item_id", item_id).execute()


def update_item_targets(
    self,
    item_id: int,
    target_buy: Optional[float],
    target_sell: Optional[float]
) -> Optional[Dict[str, Any]]:
    """Update target prices for a watchlist item."""
    update_data = {}
    if target_buy is not None:
        update_data["target_buy"] = target_buy
    if target_sell is not None:
        update_data["target_sell"] = target_sell

    if not update_data:
        return None

    resp = (
        self.client.table("watchlist_items")
        .update(update_data)
        .eq("watchlist_item_id", item_id)
        .execute()
    )
    return resp.data[0] if resp.data else None


def user_has_symbol(self, user_id: int, symbol: str) -> bool:
    """Check if user has this symbol in ANY of their watchlists. Call BEFORE delete."""
    res = (
        self.client.table("watchlist_items")
        .select("watchlist_item_id")
        .eq("watchlists.user_id", user_id)
        .eq("companies.ticker_symbol", symbol)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def get_user_symbols(self, user_id: int) -> List[str]:
    """Get all symbols user has across ALL watchlists. Used for bulk cleanup."""
    res = (
        self.client.table("watchlist_items")
        .select("companies(ticker_symbol)")
        .eq("watchlists.user_id", user_id)
        .execute()
    )
    return [
        row["companies"]["ticker_symbol"]
        for row in (res.data or [])
        if row.get("companies")
    ]
```

### 5.3 Service Changes

**File:** `application/services/watchlist_service.py`

#### 5.3.1 Enhance add_stock_to_watchlist return (lines 320-329)

**Current return:**
```python
return {
    "watchlist_item_id": watchlist_item["watchlist_item_id"],
    "company_id": company_id,
    "symbol": symbol,
    "current_price": current_price,
    "financials_loading": True,
    "is_new_stock": is_new_company,
    "message": "Stock added. Loading financial data...",
}
```

**Enhanced return:**
```python
# Calculate change from price data already fetched
prev_close = getattr(sd, 'previous_close', None) if sd else None
if current_price and prev_close:
    change = float(current_price) - float(prev_close)
    pct = (float(change) / float(prev_close)) * 100
else:
    change = 0.0
    pct = 0.0

return {
    "watchlist_item_id": watchlist_item["watchlist_item_id"],
    "company_id": company_id,
    "symbol": symbol,
    "company_name": company.get("company_name"),  # From line 282 fetch
    "current_price": current_price,
    "previous_close": prev_close,
    "change": change,
    "change_percent": pct,
    "financials_loading": True,
    "is_new_stock": is_new_company,
    "message": "Stock added. Loading financial data...",
}
```

#### 5.3.2 Add get_watchlist_structure_by_id

```python
def get_watchlist_structure_by_id(self, firebase_uid: str, watchlist_id: int) -> Dict[str, Any]:
    """Get structure (symbols + targets) for a specific watchlist by ID."""
    db_user_id = self.get_db_user_id(firebase_uid)

    watchlist = (
        supabase.table("watchlists")
        .select("id, watchlist_name, is_default, user_id")
        .eq("id", watchlist_id)
        .limit(1)
        .execute()
    ).data[0] if True else None

    if not watchlist or watchlist["user_id"] != db_user_id:
        raise NotFoundError("Watchlist not found")

    raw_items = self.watchlist_repo.get_items_by_watchlist_id(watchlist_id)

    stocks = []
    for item in raw_items or []:
        company = item.get("companies")
        if not company:
            continue
        stocks.append({
            "id": item["watchlist_item_id"],
            "symbol": company["ticker_symbol"],
            "name": company["company_name"],
            "sector": company.get("sector"),
            "industry": company.get("industry"),
            "targetBuy": item.get("target_buy"),
            "targetSell": item.get("target_sell"),
            "price": None,
            "change": None,
            "changePercent": None,
            "lastUpdated": None,
        })

    return {
        "watchlist_id": watchlist_id,
        "name": watchlist["watchlist_name"],
        "is_default": watchlist.get("is_default", False),
        "stocks": stocks,
    }
```

### 5.4 SSE Helper Functions

**File:** `api/watchlists.py`

```python
# ── SSE Subscription Helpers ──────────────────────────────────────────────

async def subscribe_symbol(symbol: str, auth_id: str) -> bool:
    """Subscribe user to price updates for a symbol."""
    symbol_subscribers[symbol].add(auth_id)
    success = auth_id in symbol_subscribers.get(symbol, set())
    logger.info(f"SSE: {symbol} subscribed for {auth_id} (success={success})")
    return success


async def unsubscribe_symbol(symbol: str, auth_id: str) -> bool:
    """Unsubscribe user from price updates. Removes symbol if no subscribers remain."""
    symbol_subscribers[symbol].discard(auth_id)
    if symbol in symbol_subscribers and not symbol_subscribers[symbol]:
        del symbol_subscribers[symbol]
        logger.info(f"SSE: {symbol} removed (no subscribers)")
    return True


async def broadcast_with_retry(
    symbol: str,
    price: float,
    change: float,
    change_percent: float,
    max_retries: int = 3
) -> bool:
    """Broadcast price update with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            await broadcast_stock_update(symbol, price, change, change_percent)
            return True
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"SSE: broadcast failed after {max_retries} attempts for {symbol}: {e}")
                return False
            await asyncio.sleep(0.1 * (2 ** attempt))
    return False
```

### 5.5 API Orchestration - Add Stock

**File:** `api/watchlist_items.py`

```python
@router.post("/watchlist-items", status_code=201, response_model=AddStockResponse)
@limiter.limit("10/minute")
async def add_item_to_watchlist(
    request: Request,
    item: WatchlistItemIn,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user_dep),
    service: WatchlistService = Depends(get_watchlist_service),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
) -> AddStockResponse:
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id, repo)

        # Verify ownership
        watchlist = repo.find_watchlist_owner(item.watchlist_id)
        if not watchlist or watchlist["user_id"] != db_user_id:
            raise HTTPException(status_code=403, detail="Permission denied.")

        # Hard cap
        if repo.count_watchlist_items(item.watchlist_id) >= 50:
            raise HTTPException(status_code=409, detail="This watchlist is full (50/50 stocks).")

        symbol = item.symbol.upper()

        # ── 1. Business logic ──────────────────────────────────────────────
        svc_result = await service.add_stock_to_watchlist(
            user_id=db_user_id,
            symbol=symbol,
            watchlist_id=item.watchlist_id,
            target_buy=item.target_buy,
            target_sell=item.target_sell,
        )

        # ── 2. Subscribe to SSE ──────────────────────────────────────────────
        from api.watchlists import subscribe_symbol, broadcast_with_retry
        subscribed = await subscribe_symbol(svc_result["symbol"], auth_id)

        # ── 3. Broadcast with retry ─────────────────────────────────────────
        # Uses service data — NO re-fetch needed
        if subscribed and svc_result.get("current_price"):
            await broadcast_with_retry(
                svc_result["symbol"],
                svc_result["current_price"],
                svc_result.get("change", 0.0),
                svc_result.get("change_percent", 0.0)
            )

        # ── 4. Return response ─────────────────────────────────────────────
        # Uses service data — NO re-fetch needed
        return AddStockResponse(
            watchlist_item=WatchlistItemData(
                watchlist_item_id=svc_result["watchlist_item_id"],
                watchlist_id=item.watchlist_id,
                company_id=svc_result["company_id"],
                target_buy=item.target_buy,
                target_sell=item.target_sell,
            ),
            stock_data=StockData(
                id=svc_result["watchlist_item_id"],
                symbol=svc_result["symbol"],
                name=svc_result.get("company_name", svc_result["symbol"]),
                price=float(svc_result.get("current_price") or 0.0),
                change=float(svc_result.get("change") or 0.0),
                changePercent=float(svc_result.get("change_percent") or 0.0),
                lastUpdated=datetime.now().isoformat(),
            ),
            financials_loading=bool(svc_result.get("financials_loading", False)),
            is_new_stock=bool(svc_result.get("is_new_stock", False)),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] add_item_to_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
```

### 5.6 API Orchestration - Delete Stock

**File:** `api/watchlist_items.py`

```python
@router.post("/watchlist-items/delete", status_code=204)
@limiter.limit("20/minute")
async def remove_item_from_watchlist(
    request: Request,
    req: DeleteItemRequest,
    user_token: dict = Depends(get_current_user_dep),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
) -> None:
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id, repo)

        # ── 1. Verify ownership and get symbol ──────────────────────────────
        item = repo.find_watchlist_item_with_owner(req.item_id)
        if not item or item["watchlists"]["user_id"] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found.")

        symbol = item["companies"]["ticker_symbol"]

        # ── 2. Check BEFORE delete ──────────────────────────────────────────
        # Critical: check BEFORE delete to avoid race condition
        remaining = repo.user_has_symbol(db_user_id, symbol)

        # ── 3. Delete from database ─────────────────────────────────────────
        repo.delete_item(req.item_id)

        # ── 4. Unsubscribe only if no remaining copies ──────────────────────
        if not remaining:
            from api.watchlists import unsubscribe_symbol
            await unsubscribe_symbol(symbol, auth_id)

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] remove_item_from_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
```

### 5.7 API Orchestration - Delete Watchlist

**File:** `api/watchlists.py`

```python
@router.delete("/watchlists/{watchlist_id}", status_code=204)
@limiter.limit("20/minute")
async def delete_watchlist(
    watchlist_id: int,
    user: dict = Depends(get_current_user_dep),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
):
    try:
        auth_id = user.get("uid")
        db_user_id = _resolve_db_user_id(auth_id)

        # Verify ownership
        existing = _assert_watchlist_ownership(watchlist_id, db_user_id)

        if existing["is_default"]:
            raise HTTPException(status_code=400, detail="The default watchlist cannot be deleted.")

        # ── 1. Get symbols BEFORE delete (for cleanup) ──────────────────────
        items = repo.get_items_by_watchlist_id(watchlist_id)
        watchlist_symbols = {
            item["companies"]["ticker_symbol"]
            for item in items
            if item.get("companies")
        }

        # ── 2. Delete watchlist (cascade deletes items) ──────────────────────
        supabase.table("watchlists").delete().eq("id", watchlist_id).execute()

        # ── 3. OPTIMIZED: Get remaining symbols in single query ─────────────
        remaining = set(repo.get_user_symbols(db_user_id))
        orphaned = watchlist_symbols - remaining

        # ── 4. Unsubscribe all orphaned symbols ─────────────────────────────
        if orphaned:
            for symbol in orphaned:
                await unsubscribe_symbol(symbol, auth_id)

        return None

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] delete_watchlist: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")
```

---

## 6. Multi-User Scenarios

### 6.1 User A Adds Stock, User B Has Same Stock
```
Initial: symbol_subscribers = {"AAPL": {"user_b"}}

User A adds AAPL:
  subscribe_symbol("AAPL", "user_a") → {"AAPL": {"user_a", "user_b"}}
  broadcast_with_retry("AAPL", ...) → Both users receive AAPL updates ✓
```

### 6.2 User Deletes Stock (Still Has in Another Watchlist)
```
Watchlist A: [AAPL, MSFT], Watchlist B: [AAPL, GOOGL]

Delete AAPL from Watchlist A:
  user_has_symbol(user_id, "AAPL") → True (still in Watchlist B)
  delete_item()
  Do NOT unsubscribe
User continues receiving AAPL updates ✓
```

### 6.3 User Deletes Last Instance of Stock
```
Watchlist A: [AAPL]

Delete AAPL:
  user_has_symbol(user_id, "AAPL") → False
  delete_item()
  unsubscribe_symbol("AAPL", user_id)
Clean memory ✓
```

### 6.4 User Deletes Entire Watchlist
```
Watchlist A: [AAPL, MSFT], Watchlist B: [GOOGL]

Delete Watchlist A:
  Get symbols: [AAPL, MSFT]
  Delete watchlist (cascade)
  Get remaining: [GOOGL]
  orphaned = [AAPL, MSFT]
  unsubscribe AAPL, MSFT
GOOGL in Watchlist B → not touched ✓
```

---

## 7. Error Handling

| Error | Behavior | Log Level |
|-------|----------|-----------|
| subscribe_symbol fails | Continue, return False | ERROR |
| broadcast fails (1st try) | Retry with backoff | WARNING |
| broadcast fails (all tries) | Log error, continue | ERROR |
| delete_item fails | Return 500 | ERROR |
| user_has_symbol check fails | Skip unsubscribe, log warning | WARNING |

**Rationale:** SSE failures are non-fatal. Stock is added/deleted correctly in DB.

---

## 8. Testing Checklist

| Test | Component | What It Tests |
|------|-----------|---------------|
| `test_delete_item_removes_from_db` | Repository | delete_item method |
| `test_update_targets_modifies_values` | Repository | update_item_targets method |
| `test_user_has_symbol_true` | Repository | Symbol exists returns True |
| `test_user_has_symbol_false` | Repository | Symbol not exists returns False |
| `test_add_stock_returns_complete_data` | Service | Returns current_price, change, company_name |
| `test_subscribe_symbol_adds_to_registry` | SSE Helper | symbol_subscribers updated |
| `test_unsubscribe_removes_symbol` | SSE Helper | Symbol removed when empty |
| `test_unsubscribe_keeps_when_subscribers` | SSE Helper | Symbol kept when others exist |

---

## 9. Breaking Change Analysis

| Change | Breaking? | Evidence |
|--------|-----------|----------|
| Add repository methods | No | New methods only |
| Add keys to service return | No | Uses `.get()` with defaults |
| Add get_watchlist_structure_by_id | No | New method only |
| API removes re-fetch | No | Uses service data (same values) |
| API adds SSE calls | No | Adds functionality, doesn't remove |

---

## 10. Implementation Order

| Phase | Task | Files | Risk |
|-------|------|-------|------|
| 1 | Add repository interface methods | 1 file | None |
| 2 | Add repository implementation methods | 1 file | Low |
| 3 | Add SSE helpers | 1 file | Low |
| 4 | Enhance service return dict | 1 file | Medium |
| 5 | Add get_watchlist_structure_by_id | 1 file | Low |
| 6 | Update API add endpoint | 1 file | Medium |
| 7 | Update API delete endpoint | 1 file | Low |
| 8 | Update delete_watchlist | 1 file | Low |
| 9 | Write unit tests | New file | Low |
| 10 | Integration testing | Manual | Low |

---

## 11. Comparison

| Aspect | Before | After |
|--------|--------|-------|
| Delete stock | 500 error | Works ✓ |
| Update targets | 500 error | Works ✓ |
| SSE subscription | Static only | Dynamic on add ✓ |
| SSE unsubscription | None | Dynamic on delete ✓ |
| Watchlist deletion cleanup | None | Full cleanup ✓ |
| YFinance fetches | 2 per add | 1 per add ✓ |
| Layer separation | API re-fetched price | Service returns complete data ✓ |
| Company name | From re-fetch | From service ✓ |

---

**Document Status:** Ready for Implementation
