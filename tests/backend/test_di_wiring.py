import pytest
from unittest.mock import MagicMock
from application.services.watchlist_service import WatchlistService


class TestWatchlistServiceDI:
    """Verify the DI wiring: defeat_beta_provider is required and stored."""

    def test_requires_defeat_beta_provider(self):
        with pytest.raises(TypeError):
            WatchlistService(
                stock_provider=MagicMock(),
                watchlist_repo=MagicMock(),
                user_repo=MagicMock(),
            )

    def test_accepts_defeat_beta_provider(self):
        service = WatchlistService(
            MagicMock(), MagicMock(), MagicMock(), defeat_beta_provider=MagicMock()
        )
        assert service.defeat_beta_provider is not None

    def test_stores_defeat_beta_provider(self):
        provider = MagicMock()
        service = WatchlistService(
            MagicMock(), MagicMock(), MagicMock(), defeat_beta_provider=provider
        )
        assert service.defeat_beta_provider is provider

    def test_no_silent_fallback(self):
        """When defeat_beta_provider is passed as None explicitly, it must remain None (no degraded creation)."""
        service = WatchlistService(
            MagicMock(), MagicMock(), MagicMock(), defeat_beta_provider=None
        )
        assert service.defeat_beta_provider is None
