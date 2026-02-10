import asyncio
import json
from collections import defaultdict
from datetime import datetime
from typing import Dict, Set, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from dependencies import get_current_user_dep
from application.services.watchlist_service import WatchlistService
from infrastructure.repositories.supabase_repository import (
    SupabaseUserRepository,
    SupabaseWatchlistRepository,
)
from providers.yfinance_provider import YFinanceProvider
from shared.exceptions.base import AppException
from database import supabase

router = APIRouter()

# -----------------------------------------------------------------------------
# SSE in‑memory state
# -----------------------------------------------------------------------------
# Each authenticated user (uid) gets one or more asyncio.Queue instances
# (per active SSE connection). We broadcast updates into the user's queues.
user_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)

# Track which users are subscribed to which symbols for targeted updates.
symbol_subscribers: Dict[str, Set[str]] = defaultdict(set)


def get_watchlist_service() -> WatchlistService:
    """Factory that wires the watchlist service to Supabase + providers."""
    user_repo = SupabaseUserRepository(client=supabase)
    watchlist_repo = SupabaseWatchlistRepository(client=supabase)
    stock_provider = YFinanceProvider()
    return WatchlistService(
        user_repo=user_repo,
        watchlist_repo=watchlist_repo,
        stock_provider=stock_provider,
    )


# -----------------------------------------------------------------------------
# Default watchlist with items (used by dashboard initial load)
# -----------------------------------------------------------------------------
@router.post("/watchlists/default-with-items", tags=["Watchlists"], status_code=200)
def get_default_watchlist_with_items(
    request: Request,
    service: WatchlistService = Depends(get_watchlist_service),
    user: dict = Depends(get_current_user_dep),
):
    """
    Retrieves the default watchlist for the authenticated user.

    IDENTITY:
    - Uses 'uid' from the verified token (Authorization header decoded by get_current_user_dep).
    - No identity is accepted from the request body for security.
    """
    try:
        auth_id = user["uid"]
        return service.get_default_watchlist_with_items(auth_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        print(f"[ERROR] get_default_watchlist_with_items: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


# -----------------------------------------------------------------------------
# Server‑Sent Events: real‑time price updates for the user's watchlist symbols
# -----------------------------------------------------------------------------
@router.get("/watchlists/stream", tags=["Watchlists"])
async def stream_watchlist_updates(
    request: Request,
    user: dict = Depends(get_current_user_dep),  # ✅ Identity via Authorization (proxy-injected)
):
    """
    SSE stream for real-time stock updates.

    SECURITY MODEL:
    - The Next.js proxy reads the HTTP-only __session cookie and injects
      `Authorization: Bearer <idToken>` to this backend.
    - `get_current_user_dep` validates the Authorization header (issuer/aud/exp/signature)
      and returns a dict that includes `uid`.
    - No tokens in query params or request body; no browser-accessible tokens.

    STREAM MODEL:
    - On connect: we resolve the user's symbols from Supabase and subscribe this connection.
    - When `broadcast_stock_update` is called (from background tasks), the update is
      delivered to all queues for the subscribed user.
    - Keep-alives are sent every 5s if there are no updates to keep the connection healthy.
    """
    auth_id: Optional[str] = user.get("uid")
    if not auth_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        user_queues[auth_id].append(queue)

        try:
            # Resolve symbols for this user from Supabase.
            # (Relational select: watchlist_items -> companies.ticker_symbol, watchlists.users.auth_id)
            items_res = (
                supabase.table("watchlist_items")
                .select("companies(ticker_symbol), watchlists(users(auth_id))")
                .eq("watchlists.users.auth_id", auth_id)
                .execute()
            )
            rows = items_res.data or []
            user_symbols = [
                row["companies"]["ticker_symbol"]
                for row in rows
                if row.get("companies")
            ]

            # Subscribe this user to all their symbols
            for sym in user_symbols:
                symbol_subscribers[sym].add(auth_id)

            # Stream loop
            while True:
                if await request.is_disconnected():
                    break

                try:
                    # Wait for an update destined to this user (or timeout for keep-alive)
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    # Keep the connection alive (comment frames are ignored by client)
                    yield ": keep-alive\n\n"

        finally:
            # Clean up this connection's queue
            try:
                if queue in user_queues.get(auth_id, []):
                    user_queues[auth_id].remove(queue)
                # If no more active queues for this user, drop their symbol subscriptions
                if not user_queues.get(auth_id):
                    user_queues.pop(auth_id, None)
                    for sym in list(symbol_subscribers.keys()):
                        symbol_subscribers[sym].discard(auth_id)
                        if not symbol_subscribers[sym]:
                            symbol_subscribers.pop(sym, None)
            except Exception:
                # Avoid throwing inside generator teardown
                pass

    # SSE-friendly headers
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


# -----------------------------------------------------------------------------
# Broadcast utility (called by your background_price_monitor)
# -----------------------------------------------------------------------------
async def broadcast_stock_update(symbol: str, price: float, change: float, change_percent: float):
    """
    Push a stock price update to all subscribed users for this symbol.
    Called by the background task that polls providers (yfinance).
    """
    uids = symbol_subscribers.get(symbol, set())
    if not uids:
        return

    now_iso = datetime.now().isoformat()
    payload = {
        "symbol": symbol,
        "price": float(price),
        "change": float(change),
        "changePercent": float(change_percent),
        "lastUpdated": now_iso,
    }

    for uid in uids:
        # For each active SSE connection for this user, enqueue the payload
        for queue in user_queues.get(uid, []):
            await queue.put(payload)