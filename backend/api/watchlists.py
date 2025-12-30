
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import supabase
from providers.yfinance_provider import YFinanceProvider

router = APIRouter()
stock_provider = YFinanceProvider()

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

# Existing /watchlists/default and /watchlists/details will be replaced by the new endpoint.
# Commenting them out for now during transition.

# @router.post("/watchlists/default", tags=["Watchlists"], status_code=200)
# def get_or_create_default_watchlist(req: UidRequest):
#     # ... (existing logic) ...

# @router.post("/watchlists/details", tags=["Watchlists"])
# def get_watchlist_by_id(req: UidRequest, body: dict):
#     # ... (existing logic) ...


@router.post("/watchlists/default-with-items", tags=["Watchlists"], status_code=200)
def get_default_watchlist_with_items(req: UidRequest):
    """
    Idempotent endpoint to get or create a default watchlist for the authenticated user
    and return all its associated items with current stock data.
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
            print(f"[DEBUG] Found existing default watchlist: {watchlist_id}")
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
            print(f"[DEBUG] Created new default watchlist: {watchlist_id}")

        # 2. Fetch Watchlist Items with Company Details
        # Using inner join to get company data directly
        items_res = supabase.table('watchlist_items').select(
            'watchlist_item_id, target_buy, target_sell, companies(company_id, ticker_symbol, company_name)'
        ).eq('watchlist_id', watchlist_id).execute()

        if not items_res.data:
            print(f"[DEBUG] No items found for watchlist {watchlist_id}")
            return {"watchlist_id": watchlist_id, "name": watchlist_name, "is_default": is_default, "items": [], "stocks": []}
        
        raw_watchlist_items = items_res.data
        symbols = [item['companies']['ticker_symbol'] for item in raw_watchlist_items if item.get('companies')]
        company_ids = [item['companies']['company_id'] for item in raw_watchlist_items if item.get('companies')]

        # 3. Fetch Current Market Data for all symbols
        all_tickers_data = {} 
        if symbols: # Only call yfinance if there are symbols to fetch
            all_tickers_data = stock_provider.get_tickers_data(symbols)

        market_data_map = {}
        if company_ids: # Only query Supabase market data if there are company_ids
            market_data_res = supabase.table('current_market_data').select('*').in_('company_id', company_ids).execute()
            if market_data_res.data:
                market_data_map = {item['company_id']: item for item in market_data_res.data}

        # 4. Combine data and format for frontend
        stocks_list = []
        for item in raw_watchlist_items:
            company = item.get('companies')
            if not company:
                continue
                
            ticker_symbol = company['ticker_symbol']
            ticker_data = all_tickers_data.get(ticker_symbol)
            
            current_price = None
            previous_close = None

            # Prioritize yfinance data
            if ticker_data:
              current_price = ticker_data.info.get('currentPrice') or ticker_data.info.get('regularMarketPrice')
              previous_close = ticker_data.info.get('previousClose') or ticker_data.info.get('regularMarketPreviousClose')

            # Fallback to database market data if yfinance is not available or incomplete
            if current_price is None or previous_close is None:
                db_market_data = market_data_map.get(company['company_id'])
                if db_market_data:
                    current_price = float(db_market_data.get('current_price', 0))
                    previous_close = float(db_market_data.get('close_price')) if db_market_data.get('close_price') else current_price

            # If still no valid price, skip or handle as appropriate
            if current_price is None or previous_close is None:
                print(f"[WARN] Could not get current or previous close price for {ticker_symbol}. Skipping.")
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
                "targetSell": item.get('target_sell')
            })

        return {
            "watchlist_id": watchlist_id,
            "name": watchlist_name,
            "is_default": is_default,
            "items": raw_watchlist_items, # Raw items for internal use if needed
            "stocks": stocks_list # Formatted stock data for display
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"[ERROR] get_default_watchlist_with_items: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="An internal server error occurred while fetching watchlist details.")
