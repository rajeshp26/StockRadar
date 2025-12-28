from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from schemas import WatchlistItemCreate
from dependencies import get_user_id_from_header
from providers import stock_provider # <-- Import the new provider

router = APIRouter()

@router.post("/watchlist-items", status_code=201)
def add_stock_to_watchlist(item: WatchlistItemCreate, user_id: str = Depends(get_user_id_from_header)):
    # 1. Verify user owns the watchlist
    verify_response = supabase.table('watchlists').select('user_id').eq('id', item.watchlist_id).single().execute()
    if verify_response.error or not verify_response.data:
        raise HTTPException(status_code=404, detail="Watchlist not found.")
    if verify_response.data['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="You do not have permission to modify this watchlist.")

    # 2. Get Ticker Info using the new provider system
    ticker_info = stock_provider.get_ticker_info(item.ticker_symbol)
    if not ticker_info:
        raise HTTPException(status_code=400, detail=f"Invalid or unrecognized ticker symbol: {item.ticker_symbol}")

    ticker_str = ticker_info.ticker_symbol
    company_id = None

    # 3. Check if company exists in our DB
    company_res = supabase.table('companies').select('id').eq('ticker_symbol', ticker_str).single().execute()
    if company_res.data:
        company_id = company_res.data['id']
    else:
        # Company not found, create it
        insert_res = supabase.table('companies').insert({
            'ticker_symbol': ticker_str,
            'company_name': ticker_info.long_name
        }).execute()
        if insert_res.error:
            raise HTTPException(status_code=500, detail=f"Failed to create new company in database: {insert_res.error.message}")
        company_id = insert_res.data[0]['id']

    if not company_id:
        raise HTTPException(status_code=500, detail="Could not find or create company ID.")

    # 4. Add the item to the watchlist
    response = supabase.table('watchlist_items').insert({
        'watchlist_id': item.watchlist_id,
        'company_id': company_id,
        'target_buy': item.target_buy,
        'target_sell': item.target_sell,
        'position': item.position
    }).execute()

    if response.error:
        if "23505" in response.error.code: # unique_violation
            raise HTTPException(status_code=409, detail=f"{ticker_str} is already in this watchlist.")
        raise HTTPException(status_code=500, detail=response.error.message)
    
    return response.data

@router.delete("/watchlist-items/{watchlist_item_id}", status_code=204)
def remove_stock_from_watchlist(watchlist_item_id: int, user_id: str = Depends(get_user_id_from_header)):
    verify_response = supabase.table('watchlist_items').select('*, watchlists(user_id)').eq('watchlist_item_id', watchlist_item_id).single().execute()
    
    if verify_response.error or not verify_response.data:
        raise HTTPException(status_code=404, detail="Watchlist item not found.")
    
    if verify_response.data['watchlists']['user_id'] != user_id:
        raise HTTPException(status_code=403, detail="You do not have permission to delete this item.")

    response = supabase.table('watchlist_items').delete().eq('watchlist_item_id', watchlist_item_id).execute()

    if response.error:
        raise HTTPException(status_code=500, detail=response.error.message)
    
    return
