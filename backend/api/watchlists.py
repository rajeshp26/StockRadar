
from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from dependencies import get_user_id_from_header
from providers.yfinance_provider import YFinanceProvider # Correct import

router = APIRouter()
stock_provider = YFinanceProvider() # Instantiate the provider

# Helper to convert firebase_uid to db_user_id
def get_db_user_id(firebase_uid: str) -> int:
    user_res = supabase.table('users').select('user_id').eq('firebase_uid', firebase_uid).single().execute()
    if user_res.error or not user_res.data:
        raise HTTPException(status_code=403, detail="User not found.")
    return user_res.data['user_id']

@router.get("/watchlists/{watchlist_id}", tags=["Watchlists"])
def get_watchlist_by_id(watchlist_id: int, firebase_uid: str = Depends(get_user_id_from_header)):
    """
    Retrieves a watchlist by its ID, using the YFinanceProvider to fetch
    real-time stock data for all items in the list.
    """
    # 1. Authorize User
    db_user_id = get_db_user_id(firebase_uid)
    watchlist_res = supabase.table('watchlists').select('id, user_id').eq('id', watchlist_id).single().execute()
    if watchlist_res.error or not watchlist_res.data:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    if watchlist_res.data['user_id'] != db_user_id:
        raise HTTPException(status_code=403, detail="User does not have permission.")

    # 2. Fetch Watchlist Items from DB
    items_res = supabase.table('watchlist_items').select('*').eq('watchlist_id', watchlist_id).execute()
    if items_res.error:
        raise HTTPException(status_code=500, detail="Failed to fetch watchlist items.")
    watchlist_items = items_res.data
    if not watchlist_items:
        return {"id": watchlist_id, "items": [], "stocks": []}

    # 3. Use the Provider to Fetch Bulk Real-Time Stock Data
    symbols = [item['symbol'] for item in watchlist_items]
    try:
        tickers_data = stock_provider.get_tickers_data(symbols)
        stocks_list = []
        for item in watchlist_items:
            symbol = item['symbol']
            ticker_obj = tickers_data.get(symbol)
            if not ticker_obj or not hasattr(ticker_obj, 'info') or not ticker_obj.info:
                continue # Skip if provider returned no data for this symbol

            info = ticker_obj.info
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            previous_close = info.get('previousClose')
            long_name = info.get('longName', symbol)

            if current_price and previous_close and long_name:
                change = current_price - previous_close
                change_percent = (change / previous_close) * 100
                stocks_list.append({
                    "id": item['id'],
                    "symbol": symbol,
                    "name": long_name,
                    "price": current_price,
                    "change": change,
                    "changePercent": change_percent,
                    "targetBuy": item.get('target_buy'),
                    "targetSell": item.get('target_sell')
                })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching real-time stock data: {e}")

    # 4. Return Combined Data
    return {
        "id": watchlist_id,
        "items": watchlist_items,
        "stocks": stocks_list
    }
