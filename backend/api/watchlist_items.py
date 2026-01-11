
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field, field_validator
from database import supabase
from providers.yfinance_provider import YFinanceProvider
from services.sync_service import sync_service
from datetime import datetime
from dependencies import get_current_user_dep, limiter
import re

router = APIRouter()
stock_provider = YFinanceProvider()

# --- Helpers ---
def get_db_user_id(auth_id: str) -> int:
    res = supabase.table('users').select('user_id').eq('auth_id', auth_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="User not found.")
    return res.data['user_id']

# --- Models ---

class WatchlistItemData(BaseModel):
    watchlist_item_id: int
    watchlist_id: int
    company_id: int
    target_buy: float | None
    target_sell: float | None
    class Config:
        populate_by_name = True
        from_attributes = True

class StockData(BaseModel):
    id: int 
    symbol: str
    name: str
    price: float
    change: float
    changePercent: float
    lastUpdated: str | None = Field(None, alias="lastUpdated")
    class Config:
        populate_by_name = True

class AddStockResponse(BaseModel):
    watchlist_item: WatchlistItemData
    stock_data: StockData

class WatchlistItemIn(BaseModel):
    watchlist_id: int
    symbol: str = Field(..., min_length=1, max_length=10)
    target_buy: float | None = Field(None, ge=0)
    target_sell: float | None = Field(None, ge=0)

    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str):
        if not re.match(r'^[A-Z0-9.-]+$', v.upper()):
            raise ValueError('Invalid ticker symbol format')
        return v.upper()

class WatchlistItemUpdate(BaseModel):
    target_buy: float | None = Field(None, ge=0)
    target_sell: float | None = Field(None, ge=0)

class DeleteItemRequest(BaseModel):
    item_id: int

# --- Endpoints ---

@router.post("/watchlist-items", status_code=201, response_model=AddStockResponse)
@limiter.limit("10/minute")
async def add_item_to_watchlist(
    request: Request,
    item: WatchlistItemIn, 
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user_dep)
):
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        watchlist_res = supabase.table('watchlists').select('user_id').eq('id', item.watchlist_id).single().execute()
        if not watchlist_res.data or watchlist_res.data['user_id'] != db_user_id:
            raise HTTPException(status_code=403, detail="Permission denied.")

        stock_details = stock_provider.get_stock_details(item.symbol)
        if not stock_details:
            raise HTTPException(status_code=404, detail=f"Stock symbol '{item.symbol}' not found.")

        if stock_details.currency:
            supabase.table('currencies').upsert(
                {'code': stock_details.currency, 'name': stock_details.currency}, 
                on_conflict='code'
            ).execute()

        company_data = {
            'ticker_symbol': stock_details.ticker_symbol,
            'company_name': stock_details.long_name,
            'exchange': stock_details.exchange or 'UNKNOWN',
            'sector': stock_details.sector,
            'industry': stock_details.industry,
            'currency': stock_details.currency or 'USD',
            'description': stock_details.description,
            'website': stock_details.website,
            'next_earnings_date': stock_details.next_earnings_date.isoformat() if stock_details.next_earnings_date else None
        }
        
        company_res = supabase.table('companies').upsert(
            company_data, on_conflict='ticker_symbol,exchange'
        ).execute()
        
        if not company_res.data:
            raise HTTPException(status_code=500, detail="Database Error: Failed to upsert company.")
        
        company_id = company_res.data[0]['company_id']

        now_iso = datetime.now().isoformat()
        market_data = {
            'company_id': company_id,
            'current_price': stock_details.price,
            'open_price': stock_details.open_price,
            'high_price': stock_details.high_price,
            'low_price': stock_details.low_price,
            'close_price': stock_details.close_price,
            'volume': stock_details.volume,
            'market_state': stock_details.market_state,
            'last_updated': now_iso
        }
        supabase.table('current_market_data').upsert(market_data, on_conflict='company_id').execute()

        item_res = supabase.table('watchlist_items').insert({
            'watchlist_id': item.watchlist_id,
            'company_id': company_id,
            'target_buy': item.target_buy,
            'target_sell': item.target_sell
        }).execute()
        
        if not item_res.data:
            check_dup = supabase.table('watchlist_items').select('*').eq('watchlist_id', item.watchlist_id).eq('company_id', company_id).execute()
            if check_dup.data:
                raise HTTPException(status_code=409, detail="This stock is already in your watchlist.")
            raise HTTPException(status_code=500, detail="Database Error: Failed to insert watchlist item.")

        new_item_db = item_res.data[0]
        background_tasks.add_task(sync_service.sync_full_company_data, company_id, stock_details.ticker_symbol)

        stock_data_out = StockData(
            id=new_item_db['watchlist_item_id'],
            symbol=stock_details.ticker_symbol,
            name=stock_details.long_name,
            price=stock_details.price,
            change=stock_details.change,
            changePercent=stock_details.change_percent,
            lastUpdated=now_iso
        )

        watchlist_item_out = WatchlistItemData.model_validate(new_item_db)
        return AddStockResponse(watchlist_item=watchlist_item_out, stock_data=stock_data_out)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] add_item_to_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


@router.patch("/watchlist-items/{item_id}", response_model=WatchlistItemData)
@limiter.limit("20/minute")
def update_watchlist_item_targets(
    request: Request,
    item_id: int, 
    update: WatchlistItemUpdate,
    user_token: dict = Depends(get_current_user_dep)
):
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        item_res = supabase.table('watchlist_items') \
            .select('watchlist_item_id, watchlists!inner(user_id)') \
            .eq('watchlist_item_id', item_id) \
            .single().execute()
            
        if not item_res.data or item_res.data['watchlists']['user_id'] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found or permission denied.")

        update_res = supabase.table('watchlist_items').update({
            'target_buy': update.target_buy,
            'target_sell': update.target_sell
        }).eq('watchlist_item_id', item_id).execute()

        if not update_res.data:
            raise HTTPException(status_code=500, detail="Failed to update watchlist item.")

        return WatchlistItemData.model_validate(update_res.data[0])
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] update_watchlist_item_targets: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


@router.post("/watchlist-items/delete", status_code=204)
@limiter.limit("20/minute")
def remove_item_from_watchlist(
    request: Request,
    req: DeleteItemRequest,
    user_token: dict = Depends(get_current_user_dep)
):
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        item_res = supabase.table('watchlist_items').select('watchlist_item_id, watchlists!inner(user_id)').eq('watchlist_item_id', req.item_id).single().execute()
        if not item_res.data or item_res.data['watchlists']['user_id'] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found or permission denied.")

        supabase.table('watchlist_items').delete().eq('watchlist_item_id', req.item_id).execute()
        return
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] remove_item_from_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
