from typing import List, Dict, Any, Optional
from domain.interfaces.repository import WatchlistRepository
from database import supabase, get_supabase_user_client
from supabase import Client

class SupabaseWatchlistRepository(WatchlistRepository):
    def __init__(self, client: Client = supabase):
        self.client = client

    def find_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        res = self.client.table('watchlists').select('*').eq('user_id', user_id).execute()
        return res.data or []

    def find_default_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        res = self.client.table('watchlists').select('id, watchlist_name, is_default') \
            .eq('user_id', user_id).eq('is_default', True).single().execute()
        return res.data

    def create_default(self, user_id: int, name: str) -> Dict[str, Any]:
        res = self.client.table('watchlists').insert({
            'user_id': user_id,
            'watchlist_name': name,
            'is_default': True
        }).execute()
        return res.data[0]

    def get_items_by_watchlist_id(self, watchlist_id: int) -> List[Dict[str, Any]]:
        res = self.client.table('watchlist_items').select(
            'watchlist_item_id, target_buy, target_sell, companies(company_id, ticker_symbol, company_name)'
        ).eq('watchlist_id', watchlist_id).execute()
        return res.data or []

class SupabaseUserRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def find_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        res = self.client.table('users').select('user_id').eq('auth_id', firebase_uid).single().execute()
        return res.data
