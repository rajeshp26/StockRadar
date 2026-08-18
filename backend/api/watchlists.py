#/backend/api/watchlists.py
import asyncio
import json
import logging
from collections import defaultdict
from shared.time_utils import now_iso
from typing import Dict, Set, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from dependencies import get_current_user_dep, get_watchlist_service, get_watchlist_repository, limiter
from application.services.watchlist_service import WatchlistService
from infrastructure.repositories.supabase_repository import (
    SupabaseWatchlistRepository,
)

from shared.exceptions.base import AppException
from database import supabase

router = APIRouter()
logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────
MAX_WATCHLISTS_PER_USER  = 5
MAX_STOCKS_PER_WATCHLIST = 50
MAX_NAME_LENGTH          = 50

# -----------------------------------------------------------------------------
# SSE in-memory state
# -----------------------------------------------------------------------------
user_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
symbol_subscribers: Dict[str, Set[str]] = defaultdict(set)


def _safe_put(queue: asyncio.Queue, payload: dict) -> bool:
    """Non-blocking put with drop-oldest backpressure.

    If queue is full, removes the oldest item to make room for the new one.
    This ensures the newest price always reaches the client (latest-wins).
    """
    if queue.full():
        try:
            queue.get_nowait()  # drop oldest
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(payload)
        return True
    except asyncio.QueueFull:
        logger.warning("[SSE] Queue full after drop-oldest — dropping event")
        return False





# ── Helper ─────────────────────────────────────────────────────────────────
def _resolve_db_user_id(auth_id: str) -> int:
    """Resolve Firebase auth_id → internal user_id. Raises 403 if not found."""
    res = (
        supabase.table("users")
        .select("user_id")
        .eq("auth_id", auth_id)
        .single()
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=403, detail="User not found.")
    return res.data["user_id"]


def _assert_watchlist_ownership(watchlist_id: int, db_user_id: int) -> dict:
    """
    Fetch watchlist row and verify ownership.
    Returns the row on success. Raises 404 if not found or not owned.
    """
    res = (
        supabase.table("watchlists")
        .select("id, user_id, watchlist_name, is_default")
        .eq("id", watchlist_id)
        .single()
        .execute()
    )
    if not res.data or res.data["user_id"] != db_user_id:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    return res.data


# ── Request models ──────────────────────────────────────────────────────────
class CreateWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        v = " ".join(v.strip().split())
        if not v:
            raise ValueError("Watchlist name cannot be empty.")
        return v


class RenameWatchlistRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=MAX_NAME_LENGTH)

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        v = " ".join(v.strip().split())
        if not v:
            raise ValueError("Watchlist name cannot be empty.")
        return v


# =============================================================================
# EXISTING ENDPOINTS (UNCHANGED)
# =============================================================================

@router.post("/watchlists/default-with-items", tags=["Watchlists"], status_code=200)
def get_default_watchlist_with_items(
    request: Request,
    service: WatchlistService = Depends(get_watchlist_service),
    user: dict = Depends(get_current_user_dep),
):
    try:
        auth_id = user["sub"]
        return service.get_default_watchlist_with_items(auth_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        print(f"[ERROR] get_default_watchlist_with_items: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/watchlists/default-structure", tags=["Watchlists"], status_code=200)
def get_default_watchlist_structure(
    request: Request,
    service: WatchlistService = Depends(get_watchlist_service),
    user: dict = Depends(get_current_user_dep),
):
    try:
        auth_id = user["sub"]
        return service.get_default_watchlist_structure(auth_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        print(f"[ERROR] get_default_watchlist_structure: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.get("/watchlists/stream", tags=["Watchlists"])
async def stream_watchlist_updates(
    request: Request,
    user: dict = Depends(get_current_user_dep),
):
    auth_id = user["sub"]

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        user_queues[auth_id].append(queue)
        try:
            items_res = (
                supabase.table("watchlist_items")
                .select("companies(company_id, ticker_symbol), watchlists(users(auth_id))")
                .eq("watchlists.users.auth_id", auth_id)
                .execute()
            )
            rows = items_res.data or []
            user_symbols = [
                row["companies"]["ticker_symbol"]
                for row in rows
                if row.get("companies")
            ]
            for sym in user_symbols:
                symbol_subscribers[sym].add(auth_id)

            # Initial prices are now served via REST (GET /watchlists/:id/prices).
            # SSE stream handles live updates only.

            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            try:
                if queue in user_queues.get(auth_id, []):
                    user_queues[auth_id].remove(queue)
                if not user_queues.get(auth_id):
                    user_queues.pop(auth_id, None)
                    for sym in list(symbol_subscribers.keys()):
                        symbol_subscribers[sym].discard(auth_id)
                        if not symbol_subscribers[sym]:
                            symbol_subscribers.pop(sym, None)
            except Exception:
                pass

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@router.get("/stocks/{symbol}/quote", tags=["MarketData"], status_code=200)
def get_stock_quote(
    symbol: str,
    user: dict = Depends(get_current_user_dep),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    sym = (symbol or "").upper().strip()
    if not sym:
        raise HTTPException(status_code=400, detail="Missing symbol")
    c = (
        supabase.table("companies")
        .select("company_id,currency,cdr_ratio")
        .eq("ticker_symbol", sym)
        .limit(1)
        .execute()
    )
    company = c.data[0] if c.data else None
    if not company:
        raise HTTPException(status_code=404, detail=f"Symbol '{sym}' not found")
    company_id = company["company_id"]
    currency   = company.get("currency") or "USD"
    cdr_ratio  = company.get("cdr_ratio")

    # Check if this is a CDR holding (exchange_override = "TOR" in holdings)
    is_cdr = False
    try:
        hold_check = (
            supabase.table("portfolio_holdings")
            .select("exchange_override")
            .eq("company_id", company_id)
            .eq("exchange_override", "TOR")
            .limit(1)
            .execute()
        )
        is_cdr = bool(hold_check.data)
    except Exception:
        pass

    md = (
        supabase.table("current_market_data")
        .select("current_price,close_price,last_updated")
        .eq("company_id", company_id)
        .limit(1)
        .execute()
    )
    row = md.data[0] if md.data else None
    if not row:
        return {"symbol": sym, "currency": currency, "price": None,
                "change": None, "changePercent": None, "lastUpdated": None}
    price       = row.get("current_price")
    prev_close  = row.get("close_price")
    last_updated = row.get("last_updated")

    # Apply CDR adjustment if this is a CDR holding
    if is_cdr:
        from shared.snapshot_builder import CDR_RATIO as _CDR_RATIO
        ratio = float(cdr_ratio) if cdr_ratio is not None else float(_CDR_RATIO)
        if price is not None:
            price = float(price) / ratio
        if prev_close is not None:
            prev_close = float(prev_close) / ratio

    change = change_percent = None
    try:
        if price is not None and prev_close is not None:
            p, pc  = float(price), float(prev_close)
            change = p - pc
            change_percent = (change / pc) * 100 if pc else 0.0
    except Exception:
        pass
    return {
        "symbol":        sym,
        "currency":      currency,
        "price":         float(price)          if price          is not None else None,
        "change":        float(change)         if change         is not None else None,
        "changePercent": float(change_percent) if change_percent is not None else None,
        "lastUpdated":   last_updated,
    }


async def broadcast_stock_update(symbol: str, price: float, change: float, change_percent: float):
    uids = symbol_subscribers.get(symbol, set())
    if not uids:
        return
    payload = {
        "type":          "price_update",
        "symbol":        symbol,
        "price":         float(price),
        "change":        float(change),
        "changePercent": float(change_percent),
        "lastUpdated":   now_iso(),
        "source":        "live",
    }
    for uid in uids:
        for queue in user_queues.get(uid, []):
            _safe_put(queue, payload)

async def broadcast_valuation_ready(symbol: str, method: str, company_id: int) -> None:
    uids = symbol_subscribers.get(symbol, set())
    if not uids:
        return
    payload = {
        "type":      "valuation_ready",
        "symbol":    symbol,
        "method":    method,
        "companyId": company_id,
    }
    for uid in uids:
        for queue in user_queues.get(uid, []):
            _safe_put(queue, payload)


async def _push_initial_prices(rows: list, queue: asyncio.Queue) -> None:
    """Push one-time price snapshot from current_market_data into SSE queue."""
    from shared.price_utils import build_price_snapshot

    try:
        if not rows:
            return

        company_ids = list({
            row["companies"]["company_id"]
            for row in rows
            if row.get("companies") and "company_id" in row["companies"]
        })
        if not company_ids:
            return

        snapshots = build_price_snapshot(supabase, company_ids, source="db_cached")

        for row in rows:
            company = row.get("companies") or {}
            cid = company.get("company_id")
            symbol = company.get("ticker_symbol")
            if cid is None or not symbol:
                continue
            snap = snapshots.get(cid)
            if not snap:
                continue

            payload = {
                "type":          "price_update",
                "symbol":        symbol,
                "price":         snap["price"],
                "change":        snap["change"],
                "changePercent": snap["changePercent"],
                "lastUpdated":   snap["lastUpdated"],
                "source":        "cached",
                "isStale":       snap["isStale"],
            }
            _safe_put(queue, payload)
    except Exception as e:
        logger.warning(f"[SSE] Failed to push initial prices: {e}")


# =============================================================================
# SSE Subscription Helpers
# =============================================================================

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


# =============================================================================
# NEW ENDPOINTS — Multi-Watchlist
# =============================================================================

# ── GET /watchlists ───────────────────────────────────────────────────────
@router.get("/watchlists", tags=["Watchlists"], status_code=200)
@limiter.limit("30/minute")
def list_watchlists(
    request: Request,
    user: dict = Depends(get_current_user_dep),
):
    """
    List all watchlists for the authenticated user.
    Returns lightweight metadata (no stock items) + stock_count per list.
    Ordered: default first, then by created_at ascending.
    """
    try:
        auth_id    = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        res = (
            supabase.table("watchlists")
            .select("id, watchlist_name, is_default, created_at, watchlist_items(count)")
            .eq("user_id", db_user_id)
            .order("is_default", desc=True)
            .order("created_at",  desc=False)
            .execute()
        )

        watchlists = []
        for row in res.data or []:
            count_rows  = row.get("watchlist_items") or []
            stock_count = count_rows[0]["count"] if count_rows else 0
            watchlists.append({
                "watchlist_id": row["id"],
                "name":         row["watchlist_name"],
                "is_default":   row["is_default"],
                "stock_count":  stock_count,
            })

        return {"watchlists": watchlists}

    except HTTPException:
        raise
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        print(f"[ERROR] list_watchlists: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ── POST /watchlists ──────────────────────────────────────────────────────
@router.post("/watchlists", tags=["Watchlists"], status_code=201)
@limiter.limit("10/minute")
def create_watchlist(
    request: Request,
    body: CreateWatchlistRequest,
    user: dict = Depends(get_current_user_dep),
):
    """
    Create a new watchlist.

    Constraints enforced here (server-side, not just UI):
    - Max 5 watchlists per user → 409
    - Unique name per user     → 409 (also enforced by DB unique constraint)
    - Name: 1–50 chars, trimmed, whitespace-collapsed
    """
    try:
        auth_id    = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        # Hard cap: count existing watchlists
        count_res = (
            supabase.table("watchlists")
            .select("id", count="exact")
            .eq("user_id", db_user_id)
            .execute()
        )
        if (count_res.count or 0) >= MAX_WATCHLISTS_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=f"Maximum of {MAX_WATCHLISTS_PER_USER} watchlists reached. "
                       "Delete an existing watchlist to create a new one.",
            )

        try:
            ins = (
                supabase.table("watchlists")
                .insert({
                    "user_id":        db_user_id,
                    "watchlist_name": body.name,
                    "is_default":     False,
                })
                .execute()
            )
        except Exception as db_err:
            if "unique_user_watchlist_name" in str(db_err) or "duplicate" in str(db_err).lower():
                raise HTTPException(
                    status_code=409,
                    detail=f"A watchlist named '{body.name}' already exists.",
                )
            raise

        row = ins.data[0] if ins.data else {}
        return {
            "watchlist_id": row.get("id"),
            "name":         row.get("watchlist_name"),
            "is_default":   row.get("is_default", False),
            "stock_count":  0,
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] create_watchlist: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ── PATCH /watchlists/{watchlist_id} ─────────────────────────────────────
@router.patch("/watchlists/{watchlist_id}", tags=["Watchlists"], status_code=200)
@limiter.limit("20/minute")
def rename_watchlist(
    request: Request,
    watchlist_id: int,
    body: RenameWatchlistRequest,
    user: dict = Depends(get_current_user_dep),
):
    """
    Rename a watchlist.

    Security: ownership verified before any write.
    Uniqueness: enforced by DB constraint (unique_user_watchlist_name).
    """
    try:
        auth_id    = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        existing   = _assert_watchlist_ownership(watchlist_id, db_user_id)

        try:
            upd = (
                supabase.table("watchlists")
                .update({"watchlist_name": body.name})
                .eq("id", watchlist_id)
                .execute()
            )
        except Exception as db_err:
            if "unique_user_watchlist_name" in str(db_err) or "duplicate" in str(db_err).lower():
                raise HTTPException(
                    status_code=409,
                    detail=f"A watchlist named '{body.name}' already exists.",
                )
            raise

        row = upd.data[0] if upd.data else {}
        return {
            "watchlist_id": row.get("id", watchlist_id),
            "name":         row.get("watchlist_name", body.name),
            "is_default":   row.get("is_default", existing["is_default"]),
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] rename_watchlist: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ── DELETE /watchlists/{watchlist_id} ────────────────────────────────────
@router.delete("/watchlists/{watchlist_id}", tags=["Watchlists"], status_code=204)
@limiter.limit("10/minute")
async def delete_watchlist(
    request: Request,
    watchlist_id: int,
    user: dict = Depends(get_current_user_dep),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
):
    """
    Delete a watchlist with SSE cleanup.

    Rules:
    - The default watchlist cannot be deleted.
    - Cascade delete removes all watchlist_items.
    - SSE subscriptions for orphaned symbols are cleaned up.
    """
    try:
        auth_id    = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        existing   = _assert_watchlist_ownership(watchlist_id, db_user_id)

        if existing["is_default"]:
            raise HTTPException(
                status_code=400,
                detail="The default watchlist cannot be deleted.",
            )

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


# ── POST /watchlists/{watchlist_id}/structure ─────────────────────────────
@router.post("/watchlists/{watchlist_id}/structure", tags=["Watchlists"], status_code=200)
@limiter.limit("30/minute")
def get_watchlist_structure_by_id(
    request: Request,
    watchlist_id: int,
    user: dict = Depends(get_current_user_dep),
    service: WatchlistService = Depends(get_watchlist_service),
):
    """
    Get structure (symbols + targets, no live prices) for a specific watchlist.
    Mirrors /watchlists/default-structure but for any owned watchlist by ID.

    NOTE: WatchlistService.get_watchlist_structure_by_id(auth_id, watchlist_id)
    must be implemented in application/services/watchlist_service.py,
    mirroring get_default_watchlist_structure() but accepting watchlist_id.
    """
    try:
        auth_id    = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        _assert_watchlist_ownership(watchlist_id, db_user_id)  # security gate

        return service.get_watchlist_structure_by_id(auth_id, watchlist_id)

    except HTTPException:
        raise
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        print(f"[ERROR] get_watchlist_structure_by_id: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# ── GET /watchlists/{watchlist_id}/prices ─────────────────────────────────
@router.get("/watchlists/{watchlist_id}/prices", tags=["Watchlists"], status_code=200)
@limiter.limit("30/minute")
def get_watchlist_prices(
    request: Request,
    watchlist_id: int,
    user: dict = Depends(get_current_user_dep),
):
    """Return current prices for all stocks in a watchlist.

    Used by the frontend on initial load instead of relying on the SSE
    initial push. Paginated at 50 stocks per page (default).
    """
    from shared.price_utils import build_price_snapshot

    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        _assert_watchlist_ownership(watchlist_id, db_user_id)

        page = max(1, int(request.query_params.get("page", 1)))
        page_size = min(100, max(1, int(request.query_params.get("page_size", 50))))

        items_res = (
            supabase.table("watchlist_items")
            .select("companies(company_id, ticker_symbol)")
            .eq("watchlist_id", watchlist_id)
            .execute()
        )
        rows = items_res.data or []
        stocks = [
            {
                "company_id": row["companies"]["company_id"],
                "symbol": row["companies"]["ticker_symbol"],
            }
            for row in rows
            if row.get("companies") and "company_id" in row["companies"]
        ]

        total = len(stocks)
        start = (page - 1) * page_size
        end = min(start + page_size, total)
        page_stocks = stocks[start:end]

        company_ids = [s["company_id"] for s in page_stocks]
        price_snapshot = build_price_snapshot(supabase, company_ids, source="db_cached")

        results = []
        for s in page_stocks:
            cid = s["company_id"]
            ps = price_snapshot.get(cid, {})
            results.append({
                "company_id": cid,
                "symbol": s["symbol"],
                "price": ps.get("price"),
                "prevClose": ps.get("prevClose"),
                "change": ps.get("change"),
                "changePercent": ps.get("changePercent"),
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

    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] get_watchlist_prices: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")