from fastapi import APIRouter, Depends, HTTPException
from database import supabase
from schemas import WatchlistCreate
from dependencies import get_user_id_from_header

router = APIRouter()

@router.get("/watchlists")
def get_user_watchlists(user_id: str = Depends(get_user_id_from_header)):
    response = supabase.table('watchlists').select('*, watchlist_items(*, companies(*))').eq('user_id', user_id).execute()
    if response.error:
        raise HTTPException(status_code=500, detail=response.error.message)
    return response.data

@router.get("/watchlists/default")
def get_default_watchlist(user_id: str = Depends(get_user_id_from_header)):
    response = supabase.table('watchlists').select('*, watchlist_items(*, companies(*))').eq('user_id', user_id).eq('is_default', True).single().execute()
    if response.error:
        if "PGRST116" in response.error.code:
            raise HTTPException(status_code=404, detail="Default watchlist not found.")
        raise HTTPException(status_code=500, detail=response.error.message)
    return response.data

@router.post("/watchlists", status_code=201)
def create_watchlist(watchlist: WatchlistCreate, user_id: str = Depends(get_user_id_from_header)):
    try:
        if watchlist.is_default:
            supabase.table('watchlists').update({'is_default': False}).eq('user_id', user_id).execute()

        response = supabase.table('watchlists').insert({
            'user_id': user_id,
            'watchlist_name': watchlist.watchlist_name,
            'description': watchlist.description,
            'is_default': watchlist.is_default
        }).execute()

        if response.error:
            if "23505" in response.error.code:
                 raise HTTPException(status_code=409, detail=f"A watchlist with the name '{'''' + watchlist.watchlist_name + '''''}' already exists.")
            raise HTTPException(status_code=500, detail=response.error.message)
        
        return response.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
