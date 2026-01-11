
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Set, List, Optional
from collections import defaultdict
from datetime import datetime
from firebase_admin import auth as firebase_auth

from dependencies import get_current_user_dep
from application.services.watchlist_service import WatchlistService
from infrastructure.repositories.supabase_repository import SupabaseUserRepository, SupabaseWatchlistRepository
from providers.yfinance_provider import YFinanceProvider
from shared.exceptions.base import AppException
from database import supabase

router = APIRouter()

# SSE state
user_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
symbol_subscribers: Dict[str, Set[str]] = defaultdict(set)

def get_watchlist_service() -> WatchlistService:
    user_repo = SupabaseUserRepository(client=supabase)
    watchlist_repo = SupabaseWatchlistRepository(client=supabase)
    stock_provider = YFinanceProvider()
    return WatchlistService(
        user_repo=user_repo, 
        watchlist_repo=watchlist_repo, 
        stock_provider=stock_provider
    )


@router.post("/watchlists/default-with-items", tags=["Watchlists"], status_code=200)
def get_default_watchlist_with_items(
    request: Request,
    service: WatchlistService = Depends(get_watchlist_service),
    user: dict = Depends(get_current_user_dep)
):
    """
    Retrieves the default watchlist. 
    IDENTITY: Uses the 'uid' from the verified Firebase token, NOT the request body.
    """
    try:
        auth_id = user["uid"]
        return service.get_default_watchlist_with_items(auth_id)
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        print(f"[ERROR] get_default_watchlist_with_items: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

@router.get("/watchlists/stream", tags=["Watchlists"])
async def stream_watchlist_updates(
    request: Request, 
    token: Optional[str] = None
):
    """
    SSE Stream for real-time stock updates.
    """
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
    
    try:
        decoded_token = firebase_auth.verify_id_token(token)
        auth_id = decoded_token["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async def event_generator():
        queue = asyncio.Queue()
        user_queues[auth_id].append(queue)
        
        try:
            # Corrected Query: Joins tables to filter by the user's auth_id
            items_res = supabase.table('watchlist_items') \
                .select('companies(ticker_symbol), watchlists(users(auth_id))') \
                .eq('watchlists.users.auth_id', auth_id) \
                .execute()
            
            user_symbols = [item['companies']['ticker_symbol'] for item in items_res.data if item.get('companies')]
            for sym in user_symbols:
                symbol_subscribers[sym].add(auth_id)
                
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if queue in user_queues[auth_id]:
                user_queues[auth_id].remove(queue)
            if not user_queues[auth_id]:
                del user_queues[auth_id]
                for sym in list(symbol_subscribers.keys()):
                    symbol_subscribers[sym].discard(auth_id)
                    if not symbol_subscribers[sym]:
                        del symbol_subscribers[sym]

    return StreamingResponse(event_generator(), media_type="text/event-stream")

async def broadcast_stock_update(symbol: str, price: float, change: float, change_percent: float):
    uids = symbol_subscribers.get(symbol, set())
    if not uids: return

    now_iso = datetime.now().isoformat()
    update_payload = {
        "symbol": symbol,
        "price": price,
        "change": change,
        "changePercent": change_percent,
        "lastUpdated": now_iso
    }
    
    for uid in uids:
        for queue in user_queues.get(uid, []):
            await queue.put(update_payload)
