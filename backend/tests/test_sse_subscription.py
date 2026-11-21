import asyncio

# Import the functions to test - they use module-level state
# so we need to import and manipulate directly
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, 'C:/Project/StockerPro/StockerPro/backend')

from collections import defaultdict


class TestSSEHelpers:
    """Tests for SSE subscription helpers."""

    @pytest.fixture
    def clean_state(self):
        """Clean SSE state before and after each test."""
        # Store original state
        import api.watchlists as watchlists_module

        # Backup original state
        original_user_queues = watchlists_module.user_queues.copy()
        original_symbol_subscribers = watchlists_module.symbol_subscribers.copy()

        # Clean state
        watchlists_module.user_queues = defaultdict(list)
        watchlists_module.symbol_subscribers = defaultdict(set)

        yield watchlists_module

        # Restore original state
        watchlists_module.user_queues = original_user_queues
        watchlists_module.symbol_subscribers = original_symbol_subscribers

    @pytest.mark.asyncio
    async def test_subscribe_symbol_adds_to_registry(self, clean_state):
        """Test that subscribe_symbol adds user to symbol_subscribers."""
        from api.watchlists import subscribe_symbol, symbol_subscribers

        # Act
        result = await subscribe_symbol("AAPL", "user_123")

        # Assert
        assert result is True
        assert "user_123" in symbol_subscribers["AAPL"]
        assert symbol_subscribers["AAPL"] == {"user_123"}

    @pytest.mark.asyncio
    async def test_subscribe_symbol_idempotent(self, clean_state):
        """Test that subscribing twice is idempotent."""
        from api.watchlists import subscribe_symbol, symbol_subscribers

        # Act
        await subscribe_symbol("AAPL", "user_123")
        await subscribe_symbol("AAPL", "user_123")

        # Assert
        assert symbol_subscribers["AAPL"] == {"user_123"}  # Only once

    @pytest.mark.asyncio
    async def test_subscribe_multiple_users(self, clean_state):
        """Test that multiple users can subscribe to same symbol."""
        from api.watchlists import subscribe_symbol, symbol_subscribers

        # Act
        await subscribe_symbol("AAPL", "user_1")
        await subscribe_symbol("AAPL", "user_2")
        await subscribe_symbol("AAPL", "user_3")

        # Assert
        assert symbol_subscribers["AAPL"] == {"user_1", "user_2", "user_3"}

    @pytest.mark.asyncio
    async def test_unsubscribe_symbol_removes_user(self, clean_state):
        """Test that unsubscribe_symbol removes user from symbol_subscribers."""
        from api.watchlists import subscribe_symbol, symbol_subscribers, unsubscribe_symbol

        # Arrange
        await subscribe_symbol("AAPL", "user_123")

        # Act
        result = await unsubscribe_symbol("AAPL", "user_123")

        # Assert
        assert result is True
        assert "AAPL" not in symbol_subscribers  # Symbol removed when empty

    @pytest.mark.asyncio
    async def test_unsubscribe_symbol_keeps_others(self, clean_state):
        """Test that unsubscribing one user keeps others."""
        from api.watchlists import subscribe_symbol, symbol_subscribers, unsubscribe_symbol

        # Arrange
        await subscribe_symbol("AAPL", "user_1")
        await subscribe_symbol("AAPL", "user_2")

        # Act
        await unsubscribe_symbol("AAPL", "user_1")

        # Assert
        assert "user_2" in symbol_subscribers["AAPL"]
        assert "AAPL" in symbol_subscribers  # Symbol kept

    @pytest.mark.asyncio
    async def test_unsubscribe_symbol_idempotent(self, clean_state):
        """Test that unsubscribing non-existent subscription is safe."""
        from api.watchlists import symbol_subscribers, unsubscribe_symbol

        # Act - should not raise
        result = await unsubscribe_symbol("AAPL", "user_123")

        # Assert
        assert result is True
        assert "AAPL" not in symbol_subscribers

    @pytest.mark.asyncio
    async def test_broadcast_with_retry_success(self, clean_state):
        """Test that broadcast_with_retry succeeds on first try."""
        from api.watchlists import broadcast_with_retry, subscribe_symbol, user_queues

        # Arrange
        await subscribe_symbol("AAPL", "user_123")
        queue = asyncio.Queue()
        user_queues["user_123"].append(queue)

        # Act
        result = await broadcast_with_retry("AAPL", 150.0, 2.5, 1.69)

        # Assert
        assert result is True
        assert not queue.empty()
        msg = await queue.get()
        assert msg["symbol"] == "AAPL"
        assert msg["price"] == 150.0
        assert msg["change"] == 2.5

    @pytest.mark.asyncio
    async def test_broadcast_with_retry_no_subscribers(self, clean_state):
        """Test that broadcast_with_retry returns True when no subscribers."""
        from api.watchlists import broadcast_with_retry

        # Act - no one subscribed
        result = await broadcast_with_retry("AAPL", 150.0, 2.5, 1.69)

        # Assert
        assert result is True  # Should not raise


class TestRepositoryMethods:
    """Tests for repository methods."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock Supabase client."""
        return MagicMock()

    def test_delete_item_calls_table_delete(self, mock_client):
        """Test that delete_item calls the correct Supabase method."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)

        # Act
        repo.delete_item(123)

        # Assert
        mock_client.table.assert_called_with("watchlist_items")
        mock_client.table.return_value.delete.assert_called()
        mock_client.table.return_value.delete.return_value.eq.assert_called_with("watchlist_item_id", 123)

    def test_update_item_targets_builds_update_data(self, mock_client):
        """Test that update_item_targets builds correct update payload."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)
        mock_client.table.return_value.update.return_value.eq.return_value.execute.return_value = MagicMock(data=[{"id": 1}])

        # Act
        result = repo.update_item_targets(123, target_buy=150.0, target_sell=200.0)

        # Assert
        mock_client.table.return_value.update.assert_called_with({"target_buy": 150.0, "target_sell": 200.0})

    def test_update_item_targets_returns_none_when_empty(self, mock_client):
        """Test that update_item_targets returns None when no targets provided."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)

        # Act
        result = repo.update_item_targets(123, target_buy=None, target_sell=None)

        # Assert
        assert result is None
        mock_client.table.return_value.update.assert_not_called()

    def test_user_has_symbol_returns_true(self, mock_client):
        """Test that user_has_symbol returns True when symbol exists."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)
        # I1d: user_has_symbol first resolves watchlist ids via find_by_user_id(),
        # then queries watchlist_items with .in_(...). Mock both real call steps.
        repo.find_by_user_id = MagicMock(return_value=[{"id": 1}])
        mock_client.table.return_value.select.return_value.in_.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"watchlist_item_id": 1}])

        # Act
        result = repo.user_has_symbol(1, "AAPL")

        # Assert
        assert result is True

    def test_user_has_symbol_returns_false(self, mock_client):
        """Test that user_has_symbol returns False when symbol doesn't exist."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)
        repo.find_by_user_id = MagicMock(return_value=[{"id": 1}])
        mock_client.table.return_value.select.return_value.in_.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        # Act
        result = repo.user_has_symbol(1, "AAPL")

        # Assert
        assert result is False

    def test_get_user_symbols_returns_list(self, mock_client):
        """Test that get_user_symbols returns list of symbols."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)
        # I1d: get_user_symbols resolves watchlist ids first, then uses .in_().
        repo.find_by_user_id = MagicMock(return_value=[{"id": 1}])
        mock_client.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[
            {"companies": {"ticker_symbol": "AAPL"}},
            {"companies": {"ticker_symbol": "MSFT"}},
            {"companies": None},
        ])

        # Act
        result = repo.get_user_symbols(1)

        # Assert
        assert result == ["AAPL", "MSFT"]

    def test_get_user_symbols_returns_empty_list(self, mock_client):
        """Test that get_user_symbols returns empty list when no symbols."""
        from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

        # Arrange
        repo = SupabaseWatchlistRepository(client=mock_client)
        mock_client.table.return_value.select.return_value.eq.return_value.execute.return_value = MagicMock(data=[])

        # Act
        result = repo.get_user_symbols(1)

        # Assert
        assert result == []
