from typing import Any

from database import supabase
from domain.interfaces.repository import WatchlistRepository
from supabase import Client


class SupabaseWatchlistRepository(WatchlistRepository):
    def __init__(self, client: Client = supabase):
        self.client = client

    def _fetch_one(self, table: str, column: str, value) -> dict[str, Any] | None:
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

    def find_user_by_auth_id(self, auth_id: str) -> dict[str, Any] | None:
        res = (
            self.client.table('users')
            .select('user_id')
            .eq('auth_id', auth_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None

    def find_watchlist_owner(self, watchlist_id: int) -> dict[str, Any] | None:
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

    def find_watchlist_item_with_owner(self, item_id: int) -> dict[str, Any] | None:
        # Query 1: Get item with companies (regular join - works with PostgREST)
        res = (
            self.client.table('watchlist_items')
            .select('watchlist_item_id, watchlist_id, companies(ticker_symbol)')
            .eq('watchlist_item_id', item_id)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        item = res.data[0]

        # Query 2: Get ownership via watchlist_id
        owner = self.find_watchlist_owner(item['watchlist_id'])
        if not owner:
            return None

        # Reconstruct in expected format for endpoint
        return {
            'watchlist_item_id': item['watchlist_item_id'],
            'watchlists': {'user_id': owner['user_id']},
            'companies': item.get('companies')
        }

    def find_company_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        res = (
            self.client.table('companies')
            .select('company_id')
            .eq('ticker_symbol', symbol)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    def find_by_user_id(self, user_id: int) -> list[dict[str, Any]]:
        res = self.client.table('watchlists').select('*').eq('user_id', user_id).execute()
        return res.data or []

    def find_default_by_user_id(self, user_id: int) -> dict[str, Any] | None:
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

    def create_default(self, user_id: int, name: str) -> dict[str, Any]:
        res = self.client.table('watchlists').insert({
            'user_id': user_id,
            'watchlist_name': name,
            'is_default': True
        }).execute()
        return res.data[0]

    def get_items_by_watchlist_id(self, watchlist_id: int) -> list[dict[str, Any]]:
        res = self.client.table('watchlist_items').select(
            'watchlist_item_id, target_buy, target_sell, security_id, '
            'companies(company_id, ticker_symbol, company_name, sector, industry)'
        ).eq('watchlist_id', watchlist_id).execute()
        return res.data or []

    def delete_item(self, item_id: int) -> None:
        """Delete a watchlist item by ID."""
        self.client.table("watchlist_items").delete().eq("watchlist_item_id", item_id).execute()

    def update_item_targets(
        self,
        item_id: int,
        target_buy: float | None,
        target_sell: float | None
    ) -> dict[str, Any] | None:
        """Update target prices for a watchlist item."""
        update_data = {}
        if target_buy is not None:
            update_data["target_buy"] = target_buy
        if target_sell is not None:
            update_data["target_sell"] = target_sell

        if not update_data:
            return None

        resp = (
            self.client.table("watchlist_items")
            .update(update_data)
            .eq("watchlist_item_id", item_id)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def user_has_symbol(self, user_id: int, symbol: str) -> bool:
        """Check if user has this symbol in ANY of their watchlists. Call BEFORE delete."""
        # Step 1: Get company_id from symbol
        company = self.find_company_by_symbol(symbol)
        if not company:
            return False

        # Step 2: Get user's watchlist IDs
        watchlists = self.find_by_user_id(user_id)
        if not watchlists:
            return False
        watchlist_ids = [w['id'] for w in watchlists]

        # Step 3: Check if company_id exists in any watchlist
        res = (
            self.client.table("watchlist_items")
            .select("watchlist_item_id")
            .in_("watchlist_id", watchlist_ids)
            .eq("company_id", company["company_id"])
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def get_user_symbols(self, user_id: int) -> list[str]:
        """Get all symbols user has across ALL watchlists. Used for bulk cleanup."""
        # Step 1: Get user's watchlist IDs
        watchlists = self.find_by_user_id(user_id)
        if not watchlists:
            return []
        watchlist_ids = [w['id'] for w in watchlists]

        # Step 2: Get items with companies embedding
        res = (
            self.client.table("watchlist_items")
            .select("companies(ticker_symbol)")
            .in_("watchlist_id", watchlist_ids)
            .execute()
        )
        return [
            row["companies"]["ticker_symbol"]
            for row in (res.data or [])
            if row.get("companies")
        ]

class SupabaseUserRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def find_by_firebase_uid(self, firebase_uid: str) -> dict[str, Any] | None:
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
