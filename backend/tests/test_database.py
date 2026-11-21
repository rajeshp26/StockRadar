"""
Tests for database.py — Supabase client lazy initialization with timeout.

I1d: database.py was reworked to create the client lazily and wrap it in
TimedClient (tracing.py, §4.1 timing instrument). These tests are retargeted to
that live contract so they prove it rather than asserting the pre-refactor
direct-client shape.
"""
from unittest.mock import MagicMock, patch


class TestSupabaseClientInit:
    _trigger = staticmethod(lambda db: db.get_supabase())

    @staticmethod
    def _reload_database():
        import importlib

        import database
        importlib.reload(database)
        return database

    def test_client_uses_sync_client_options(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()
            self._trigger(database)

            mock_create.assert_called_once()
            _, kwargs = mock_create.call_args
            assert "options" in kwargs

            from supabase.lib.client_options import SyncClientOptions
            assert isinstance(kwargs["options"], SyncClientOptions)

    def test_client_has_timeout_configured(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()
            self._trigger(database)

            opts = mock_create.call_args.kwargs["options"]
            assert opts.postgrest_client_timeout == 30

    def test_client_has_storage_configured(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()
            self._trigger(database)

            opts = mock_create.call_args.kwargs["options"]
            assert hasattr(opts, "storage")
            assert opts.storage is not None

    def test_timeout_shorter_than_default(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()
            self._trigger(database)

            opts = mock_create.call_args.kwargs["options"]
            assert opts.postgrest_client_timeout < 120

    def test_client_receives_url_and_key(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()
            self._trigger(database)

            url, key = mock_create.call_args.args[0], mock_create.call_args.args[1]
            assert url.startswith("http")
            assert len(key) > 10

    def test_get_supabase_user_client_returns_same_client(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()

            result = database.get_supabase_user_client()
            # get_supabase() now wraps the raw client in a TimedClient (§4.1
            # timing instrument). The contract is "returns the same singleton",
            # not "is the raw create_client() mock".
            assert result is database.get_supabase()
            assert result._inner is mock_client

    def test_get_supabase_user_client_with_token(self):
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()

            result = database.get_supabase_user_client(id_token="test-token")
            # get_supabase_user_client() delegates to the same singleton
            # (wrapped in TimedClient); token param is accepted for API compat.
            assert result is database.get_supabase()
            assert result._inner is mock_client

    def test_client_is_created_lazily(self):
        """create_client is NOT called on import — only on first access."""
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()

            # Import/reload should NOT trigger create_client.
            mock_create.assert_not_called()

            # First access triggers it.
            _ = database.get_supabase()
            mock_create.assert_called_once()

    def test_proxy_delegates_to_real_client(self):
        """The supabase proxy attribute triggers lazy init on first use."""
        with patch("supabase.create_client") as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client

            database = self._reload_database()

            assert mock_create.call_count == 0
            # Accessing any attribute on the proxy triggers lazy init.
            _ = database.supabase.table
            mock_create.assert_called_once()

    def test_supabase_proxy_identity(self):
        """The supabase module attribute is a proxy object, not the raw client."""
        database = self._reload_database()

        from database import _LazySupabaseProxy
        assert isinstance(database.supabase, _LazySupabaseProxy)
