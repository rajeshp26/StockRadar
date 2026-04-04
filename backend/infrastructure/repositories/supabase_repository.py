from typing import List, Dict, Any, Optional
from domain.interfaces.repository import WatchlistRepository
from database import supabase, get_supabase_user_client
from supabase import Client

class SupabaseWatchlistRepository(WatchlistRepository):
    def __init__(self, client: Client = supabase):
        self.client = client

    def _fetch_one(self, table: str, column: str, value) -> Optional[Dict[str, Any]]:
        """Single-row lookup. Returns None cleanly when 0 rows match.
        Uses limit(1) — not single() — so 0 rows returns None instead of
        raising APIError. Defined once here; never repeated at call sites."""
        res = (
            self.client.table(table)
            .select('*')
            .eq(column, value)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def find_user_by_auth_id(self, auth_id: str) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table('users')
            .select('user_id')
            .eq('auth_id', auth_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def find_watchlist_owner(self, watchlist_id: int) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table('watchlists')
            .select('user_id')
            .eq('id', watchlist_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def count_watchlist_items(self, watchlist_id: int) -> int:
        res = (
            self.client.table('watchlist_items')
            .select('watchlist_item_id', count='exact')
            .eq('watchlist_id', watchlist_id)
            .execute()
        )
        return res.count or 0

    def find_watchlist_item_with_owner(self, item_id: int) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table('watchlist_items')
            .select('watchlist_item_id, watchlists!inner(user_id)')
            .eq('watchlist_item_id', item_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def find_company_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        res = (
            self.client.table('companies')
            .select('company_id')
            .eq('ticker_symbol', symbol)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    def find_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        res = self.client.table('watchlists').select('*').eq('user_id', user_id).execute()
        return res.data or []

    def find_default_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        # IMPORTANT: `.single()` throws when 0 rows are returned (new users or no default set),
        # which bubbles up as a 500. Return None instead.
        res = (
            self.client.table('watchlists')
            .select('id, watchlist_name, is_default')
            .eq('user_id', user_id)
            .eq('is_default', True)
            .limit(1)
            .execute()
        )
        return (res.data[0] if res.data else None)

    def create_default(self, user_id: int, name: str) -> Dict[str, Any]:
        res = self.client.table('watchlists').insert({
            'user_id': user_id,
            'watchlist_name': name,
            'is_default': True
        }).execute()
        return res.data[0]

    def get_items_by_watchlist_id(self, watchlist_id: int) -> List[Dict[str, Any]]:
        res = self.client.table('watchlist_items').select(
            'watchlist_item_id, target_buy, target_sell, '
            'companies(company_id, ticker_symbol, company_name, sector, industry)'
        ).eq('watchlist_id', watchlist_id).execute()
        return res.data or []

class SupabaseUserRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def find_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        # IMPORTANT: `.single()` throws when 0 rows are returned (user exists in Firebase but not in DB),
        # which bubbles up as a 500. Return None instead so service can raise a controlled AppException.
        res = (
            self.client.table('users')
            .select('user_id')
            .eq('auth_id', firebase_uid)
            .limit(1)
            .execute()
        )
        return (res.data[0] if res.data else None)
