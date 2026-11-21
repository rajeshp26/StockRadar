from unittest.mock import MagicMock, patch

import pytest

from application.services.watchlist_service import WatchlistService
from domain.entities.watchlist import WatchlistWithStocks
from shared.exceptions.base import NotFoundError


class TestWatchlistService:
    @pytest.fixture
    def mock_stock_provider(self):
        return MagicMock()

    @pytest.fixture
    def mock_watchlist_repo(self):
        return MagicMock()

    @pytest.fixture
    def mock_user_repo(self):
        return MagicMock()

    @pytest.fixture
    def mock_defeat_beta_provider(self):
        return MagicMock()

    @pytest.fixture
    def service(self, mock_stock_provider, mock_watchlist_repo, mock_user_repo, mock_defeat_beta_provider):
        return WatchlistService(mock_stock_provider, mock_watchlist_repo, mock_user_repo, defeat_beta_provider=mock_defeat_beta_provider)

    def test_get_db_user_id_success(self, service, mock_user_repo):
        # Arrange
        mock_user_repo.find_by_firebase_uid.return_value = {"user_id": 1}

        # Act
        user_id = service.get_db_user_id("test_uid")

        # Assert
        assert user_id == 1
        mock_user_repo.find_by_firebase_uid.assert_called_once_with("test_uid")

    def test_get_db_user_id_not_found(self, service, mock_user_repo):
        # Arrange
        mock_user_repo.find_by_firebase_uid.return_value = None

        # Act & Assert
        with pytest.raises(NotFoundError):
            service.get_db_user_id("invalid_uid")

    def test_get_default_watchlist_with_items_success(self, service, mock_user_repo, mock_watchlist_repo, mock_stock_provider):
        # Arrange
        mock_user_repo.find_by_firebase_uid.return_value = {"user_id": 1}
        mock_watchlist_repo.find_default_by_user_id.return_value = {
            "id": 10, "watchlist_name": "My Watchlist", "is_default": True
        }
        mock_watchlist_repo.get_items_by_watchlist_id.return_value = [
            {
                "watchlist_item_id": 100,
                "target_buy": 150,
                "target_sell": 200,
                "companies": {
                    "company_id": 5,
                    "ticker_symbol": "AAPL",
                    "company_name": "Apple Inc"
                }
            }
        ]

        # Mock Stock Provider
        mock_ticker = MagicMock()
        mock_ticker.info = {"currentPrice": 160.0, "previousClose": 155.0}
        mock_stock_provider.get_tickers_data.return_value = {"AAPL": mock_ticker}

        # Act — I1d: the service now reads market data / CDR overrides through
        # the module-level supabase client (not the injected stock provider).
        # Stub those lookups so this stays a unit test.
        with patch("application.services.watchlist_service.supabase") as mock_supabase:
            mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = MagicMock(data=[])
            result = service.get_default_watchlist_with_items("test_uid")

        # Assert
        assert isinstance(result, WatchlistWithStocks)
        assert result.watchlist_id == 10
        assert len(result.stocks) == 1
        assert result.stocks[0].symbol == "AAPL"
        assert result.stocks[0].price == 160.0
