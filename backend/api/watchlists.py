
from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from dependencies import get_user_id_from_header
from providers.yfinance_provider import YFinanceProvider

router = APIRouter()
stock_provider = YFinanceProvider()

def get_db_user_id(firebase_uid: str) -> int:
    user_res = supabase.table('users').select('user_id').eq('firebase_uid', firebase_uid).single().execute()
    if user_res.error or not user_res.data:
        raise HTTPException(status_code=403, detail="User not found.")
    return user_res.data['user_id']

@router.get("/watchlists/{watchlist_id}", tags=["Watchlists"])
def get_watchlist_by_id(watchlist_id: int, firebase_uid: str = Depends(get_user_id_from_header)):
    db_user_id = get_db_user_id(firebase_uid)
    
    # 1. Authorize and Fetch Watchlist
    watchlist_res = supabase.table('watchlists').select('id, user_id, watchlist_items!inner(watchlist_item_id, target_buy, target_sell, companies!inner(ticker_symbol, company_name))').eq('id', watchlist_id).single().execute()

    if watchlist_res.error or not watchlist_res.data:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    if watchlist_res.data['user_id'] != db_user_id:
        raise HTTPException(status_code=403, detail="Permission denied.")

    watchlist_data = watchlist_res.data
    watchlist_items = watchlist_data.get('watchlist_items', [])

    if not watchlist_items:
        return {"id": watchlist_id, "items": [], "stocks": []}

    # 2. Get symbols and fetch real-time data
    symbols = [item['companies']['ticker_symbol'] for item in watchlist_items if item.get('companies')]
    if not symbols:
         return {"id": watchlist_id, "items": watchlist_items, "stocks": []}
         
    all_tickers_data = stock_provider.get_tickers_data(symbols)
    
    # 3. Get market data from our DB
    company_ids = [item['companies']['company_id'] for item in watchlist_items if item.get('companies')]
    market_data_res = supabase.table('current_market_data').select('*').in_('company_id', company_ids).execute()
    market_data_map = {item['company_id']: item for item in market_data_res.data}
    
    # 4. Construct final response
    stocks_list = []
    for item in watchlist_items:
        company = item.get('companies')
        if not company:
            continue
            
        ticker_symbol = company['ticker_symbol']
        ticker_data = all_tickers_data.get(ticker_symbol)
        
        current_price = ticker_data.info.get('currentPrice') or ticker_data.info.get('regularMarketPrice')
        previous_close = ticker_data.info.get('previousClose')
        
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
            "targetSell": item.get('target_sell')
        })

    return {
        "id": watchlist_id,
        "items": watchlist_items,
        "stocks": stocks_list
    }
