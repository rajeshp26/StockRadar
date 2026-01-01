
import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from database import supabase
from providers.yfinance_provider import YFinanceProvider
from typing import Dict, Set, List
from collections import defaultdict
from datetime import datetime

router = APIRouter()
stock_provider = YFinanceProvider()

# SSE state
user_queues: Dict[str, List[asyncio.Queue]] = defaultdict(list)
symbol_subscribers: Dict[str, Set[str]] = defaultdict(set)

class UidRequest(BaseModel):
    firebase_uid: str

def get_db_user_id(firebase_uid: str) -> int:
    try:
        user_res = supabase.table('users').select('user_id').eq('firebase_uid', firebase_uid).single().execute()
        if not user_res.data:
            raise HTTPException(status_code=403, detail="User not found.")
        return user_res.data['user_id']
    except Exception as e:
        print(f"[ERROR] get_db_user_id: {e}")
        raise HTTPException(status_code=403, detail="User not found or database error.")

@router.post("/watchlists/default-with-items", tags=["Watchlists"], status_code=200)
def get_default_watchlist_with_items(req: UidRequest):
    """
    Idempotent endpoint to get or create a default watchlist.
    """
    try:
        db_user_id = get_db_user_id(req.firebase_uid)

        # 1. Find or Create Default Watchlist
        watchlist_res = supabase.table('watchlists').select('id, watchlist_name, is_default') \
                                         .eq('user_id', db_user_id).eq('is_default', True).single().execute()
        
        watchlist_id = None
        watchlist_name = "My Watchlist"
        is_default = True

        if watchlist_res.data:
            watchlist_id = watchlist_res.data['id']
            watchlist_name = watchlist_res.data['watchlist_name']
            is_default = watchlist_res.data['is_default']
        else:
            # Create a new default watchlist if not found
            new_watchlist_res = supabase.table('watchlists').insert({
                'user_id': db_user_id,
                'watchlist_name': watchlist_name,
                'is_default': True
            }).execute()
            
            if not new_watchlist_res.data:
                raise HTTPException(status_code=500, detail="Failed to create default watchlist.")
            
            watchlist_id = new_watchlist_res.data[0]['id']

        # 2. Fetch Watchlist Items
        items_res = supabase.table('watchlist_items').select(
            'watchlist_item_id, target_buy, target_sell, companies(company_id, ticker_symbol, company_name)'
        ).eq('watchlist_id', watchlist_id).execute()

        if not items_res.data:
            return {"watchlist_id": watchlist_id, "name": watchlist_name, "is_default": is_default, "items": [], "stocks": []}
        
        raw_watchlist_items = items_res.data
        symbols = [item['companies']['ticker_symbol'] for item in raw_watchlist_items if item.get('companies')]
        company_ids = [item['companies']['company_id'] for item in raw_watchlist_items if item.get('companies')]

        # 3. Fetch Market Data
        all_tickers_data = {} 
        if symbols:
            all_tickers_data = stock_provider.get_tickers_data(symbols)

        market_data_map = {}
        if company_ids:
            market_data_res = supabase.table('current_market_data').select('*').in_('company_id', company_ids).execute()
            if market_data_res.data:
                market_data_map = {item['company_id']: item for item in market_data_res.data}

        # 4. Combine data
        stocks_list = []
        for item in raw_watchlist_items:
            company = item.get('companies')
            if not company: continue
                
            ticker_symbol = company['ticker_symbol']
            ticker_data = all_tickers_data.get(ticker_symbol)
            
            current_price = None
            previous_close = None
            last_updated = None

            if ticker_data:
              current_price = ticker_data.info.get('currentPrice') or ticker_data.info.get('regularMarketPrice')
              previous_close = ticker_data.info.get('previousClose') or ticker_data.info.get('regularMarketPreviousClose')

            db_market_data = market_data_map.get(company['company_id'])
            if db_market_data:
                last_updated = db_market_data.get('last_updated')
                if current_price is None or previous_close is None:
                    current_price = float(db_market_data.get('current_price', 0))
                    previous_close = float(db_market_data.get('close_price')) if db_market_data.get('close_price') else current_price

            if current_price is None or previous_close is None:
                continue

            change = current_price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else 0
            
            stocks_list.append({
                "id": item['watchlist_item_id'],
                "symbol": ticker_symbol,
                "name": company['company_name'],
                "price": current_price,
                "change": change,
                "changePercent": change_percent,
                "targetBuy": item.get('target_buy'),
                "targetSell": item.get('target_sell'),
                "lastUpdated": last_updated # Changed to camelCase
            })

        return {
            "watchlist_id": watchlist_id,
            "name": watchlist_name,
            "is_default": is_default,
            "items": raw_watchlist_items,
            "stocks": stocks_list
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] get_default_watchlist_with_items: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

@router.get("/watchlists/stream", tags=["Watchlists"])
async def stream_watchlist_updates(firebase_uid: str, request: Request):
    """
    SSE endpoint for real-time stock updates.
    """
    if not firebase_uid:
        raise HTTPException(status_code=400, detail="firebase_uid is required")

    async def event_generator():
        queue = asyncio.Queue()
        user_queues[firebase_uid].append(queue)
        
        try:
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
                    data = await asyncio.wait_for(queue.get(), timeout=2.0)
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
        "lastUpdated": now_iso # Changed to camelCase
    }
    
    for uid in uids:
        for queue in user_queues.get(uid, []):
            await queue.put(update_payload)
