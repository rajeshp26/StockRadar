
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from database import supabase
from providers.yfinance_provider import YFinanceProvider

router = APIRouter()
stock_provider = YFinanceProvider()

# --- Helpers ---
def get_db_user_id(firebase_uid: str) -> int:
    res = supabase.table('users').select('user_id').eq('firebase_uid', firebase_uid).single().execute()
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

class AddStockResponse(BaseModel):
    watchlist_item: WatchlistItemData
    stock_data: StockData

class WatchlistItemIn(BaseModel):
    firebase_uid: str
    watchlist_id: int
    symbol: str
    target_buy: float | None = None
    target_sell: float | None = None

class DeleteItemRequest(BaseModel):
    firebase_uid: str
    item_id: int

# --- Endpoints ---

@router.post("/watchlist-items", status_code=201, response_model=AddStockResponse)
def add_item_to_watchlist(item: WatchlistItemIn):
    try:
        db_user_id = get_db_user_id(item.firebase_uid)
        
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
        ).select('company_id').single().execute()
        
        if hasattr(company_res, 'error') and company_res.error:
            raise HTTPException(status_code=500, detail=f"Database Error (Company): {company_res.error.message}")
        
        company_id = company_res.data['company_id']

        market_data = {
            'company_id': company_id,
            'current_price': stock_details.price,
            'open_price': stock_details.open_price,
            'high_price': stock_details.high_price,
            'low_price': stock_details.low_price,
            'close_price': stock_details.close_price,
            'volume': stock_details.volume,
            'market_state': stock_details.market_state
        }
        supabase.table('current_market_data').upsert(market_data, on_conflict='company_id').execute()

        item_res = supabase.table('watchlist_items').insert({
            'watchlist_id': item.watchlist_id,
            'company_id': company_id,
            'target_buy': item.target_buy,
            'target_sell': item.target_sell
        }).select().single().execute()
        
        if hasattr(item_res, 'error') and item_res.error:
            if "unique_watchlist_company" in str(item_res.error.message):
                raise HTTPException(status_code=409, detail="This stock is already in your watchlist.")
            raise HTTPException(status_code=500, detail=f"Database Error: {item_res.error.message}")

        new_item_db = item_res.data

        stock_data_out = StockData(
            id=new_item_db['watchlist_item_id'],
            symbol=stock_details.ticker_symbol,
            name=stock_details.long_name,
            price=stock_details.price,
            change=stock_details.change,
            changePercent=stock_details.change_percent
        )

        watchlist_item_out = WatchlistItemData.model_validate(new_item_db)

        return AddStockResponse(watchlist_item=watchlist_item_out, stock_data=stock_data_out)
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] add_item_to_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


@router.post("/watchlist-items/delete", status_code=204)
def remove_item_from_watchlist(req: DeleteItemRequest):
    try:
        db_user_id = get_db_user_id(req.firebase_uid)
        
        item_res = supabase.table('watchlist_items').select('watchlist_item_id, watchlists!inner(user_id)').eq('watchlist_item_id', req.item_id).single().execute()
        if not item_res.data or item_res.data['watchlists']['user_id'] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found or permission denied.")

        delete_res = supabase.table('watchlist_items').delete().eq('watchlist_item_id', req.item_id).execute()

        if delete_res.error:
            raise HTTPException(status_code=500, detail=f"Database error: {delete_res.error.message}")
        
        return
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] remove_item_from_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")
