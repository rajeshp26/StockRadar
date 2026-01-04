
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, Set, List, Optional
from collections import defaultdict
from datetime import datetime
from firebase_admin import auth as firebase_auth

from dependencies import get_watchlist_service, verify_firebase_token, limiter
from application.services.watchlist_service import WatchlistService
from shared.exceptions.base import AppException
from database import supabase

router = APIRouter()

# SSE state
user_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
symbol_subscribers: Dict[str, Set[str]] = defaultdict(set)

@router.post("/watchlists/default-with-items", tags=["Watchlists"], status_code=200)
def get_default_watchlist_with_items(
    request: Request,
    service: WatchlistService = Depends(get_watchlist_service),
    user_token: dict = Depends(verify_firebase_token)
):
    """
    Retrieves the default watchlist. 
    IDENTITY: Uses the 'uid' from the verified Firebase token, NOT the request body.
    """
    try:
        firebase_uid = user_token["uid"]
        # Logic: We fetch the watchlist belonging to the authenticated user.
        return service.get_default_watchlist_with_items(firebase_uid)
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
        # VERIFICATION: Always verify the token before opening the stream
        decoded_token = firebase_auth.verify_id_token(token)
        firebase_uid = decoded_token["uid"]
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async def event_generator():
        queue = asyncio.Queue()
        user_queues[firebase_uid].append(queue)
        
        try:
            # IDENTITY-SCOPED QUERY: Only subscribe to symbols in the user's watchlist
            # Note: This query assumes your schema allows filtering by firebase_uid via joins
            items_res = supabase.table('watchlist_items') \
                .select('companies(ticker_symbol)') \
                .eq('watchlists.users.firebase_uid', firebase_uid) \
                .execute()
            
            user_symbols = [item['companies']['ticker_symbol'] for item in items_res.data if item.get('companies')]
            for sym in user_symbols:
                symbol_subscribers[sym].add(firebase_uid)
                
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield f"data: {json.dumps(data)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if queue in user_queues[firebase_uid]:
                user_queues[firebase_uid].remove(queue)
            if not user_queues[firebase_uid]:
                del user_queues[firebase_uid]
                for sym in list(symbol_subscribers.keys()):
                    symbol_subscribers[sym].discard(firebase_uid)
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
