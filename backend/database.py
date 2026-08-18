"""
Supabase client — lazily initialized to avoid blocking on import.

Usage (unchanged):
    from database import supabase
    supabase.table("jobs").select("*").execute()
"""

from supabase import create_client, Client
from supabase.lib.client_options import SyncClientOptions
from supabase_auth import SyncMemoryStorage
from config import settings
from tracing import TimedClient


_client: Client = None

def get_supabase() -> Client:
    global _client
    if _client is None:
        raw = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
            options=SyncClientOptions(
                storage=SyncMemoryStorage(),
                postgrest_client_timeout=30,
            ),
        )
        # Wrap with the §4.1 timing instrument (times every sync .execute()).
        _client = TimedClient(raw)  # type: ignore[assignment]
    return _client


class _LazySupabaseProxy:
    """Delegates all attribute access to the lazily-initialized client."""

    def __getattr__(self, name: str):
        return getattr(get_supabase(), name)


supabase: Client = _LazySupabaseProxy()  # type: ignore[assignment]


def get_supabase_user_client(id_token: str = None) -> Client:
    return get_supabase()
