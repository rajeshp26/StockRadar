"""
Tests for PortfolioService._create_company_from_symbol with exchange_override.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.portfolio_service import PortfolioService
from providers.base import StockDetails


def _make_stock_details(symbol: str, exchange: str = "NMS", price: float = 100.0):
    return StockDetails(
        ticker_symbol=symbol,
        long_name=f"{symbol} Inc.",
        price=price,
        change=0.0,
        change_percent=0.0,
        exchange=exchange,
        sector=None,
        industry=None,
        currency="USD",
        description=None,
        website=None,
    )


@pytest.fixture
def mock_portfolio_repo():
    return MagicMock()


@pytest.fixture
def mock_financial_repo():
    return AsyncMock()


@pytest.fixture
def mock_stock_provider():
    provider = MagicMock()
    provider.get_stock_details = MagicMock()
    return provider


@pytest.fixture
def service(mock_portfolio_repo, mock_financial_repo, mock_stock_provider):
    return PortfolioService(mock_portfolio_repo, mock_financial_repo, stock_provider=mock_stock_provider)


class TestCreateCompanyFromSymbol:
    """Test _create_company_from_symbol with exchange_override."""

    @patch("application.services.portfolio_service.supabase")
    async def test_no_override_uses_unsuffixed_symbol(self, mock_supabase, service, mock_stock_provider):
        """Without exchange_override, should query the symbol as-is."""
        sd = _make_stock_details("AAPL", exchange="NMS")
        mock_stock_provider.get_stock_details.return_value = sd
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 1}])

        company_id = await service._create_company_from_symbol("AAPL")

        mock_stock_provider.get_stock_details.assert_called_once_with("AAPL")
        assert company_id == 1

    @patch("application.services.portfolio_service.supabase")
    async def test_tor_override_appends_to_suffix(self, mock_supabase, service, mock_stock_provider):
        """With exchange_override='TOR', should query symbol + '.TO'."""
        sd = _make_stock_details("TSLA.TO", exchange="TOR", price=32.57)
        mock_stock_provider.get_stock_details.return_value = sd
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 2}])

        company_id = await service._create_company_from_symbol("TSLA", exchange_override="TOR")

        mock_stock_provider.get_stock_details.assert_called_once_with("TSLA.TO")
        assert company_id == 2

    @patch("application.services.portfolio_service.supabase")
    async def test_van_override_appends_v_suffix(self, mock_supabase, service, mock_stock_provider):
        """With exchange_override='VAN', should query symbol + '.V'."""
        sd = _make_stock_details("SYM.V", exchange="VAN", price=10.0)
        mock_stock_provider.get_stock_details.return_value = sd
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 3}])

        company_id = await service._create_company_from_symbol("SYM", exchange_override="VAN")

        mock_stock_provider.get_stock_details.assert_called_once_with("SYM.V")
        assert company_id == 3

    @patch("application.services.portfolio_service.supabase")
    async def test_tor_override_fallback_on_failure(self, mock_supabase, service, mock_stock_provider):
        """When .TO lookup fails, should fall back to unsuffixed symbol."""
        # First call (.TO) returns None, second call (unsuffixed) returns data
        us_sd = _make_stock_details("META", exchange="NMS", price=608.0)
        mock_stock_provider.get_stock_details.side_effect = [None, us_sd]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 4}])

        company_id = await service._create_company_from_symbol("META", exchange_override="TOR")

        assert mock_stock_provider.get_stock_details.call_count == 2
        mock_stock_provider.get_stock_details.assert_any_call("META.TO")
        mock_stock_provider.get_stock_details.assert_any_call("META")
        assert company_id == 4

    @patch("application.services.portfolio_service.supabase")
    async def test_normal_suffix_retry_still_works(self, mock_supabase, service, mock_stock_provider):
        """When unsuffixed lookup fails, should still retry with .TO/.V suffixes."""
        mock_stock_provider.get_stock_details.side_effect = [
            None,           # unsuffixed
            _make_stock_details("SHOP.TO", exchange="TOR", price=120.0),  # .TO
        ]
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 5}])

        company_id = await service._create_company_from_symbol("SHOP")

        assert mock_stock_provider.get_stock_details.call_count == 2
        mock_stock_provider.get_stock_details.assert_any_call("SHOP")
        mock_stock_provider.get_stock_details.assert_any_call("SHOP.TO")
        assert company_id == 5

    @patch("application.services.portfolio_service.supabase")
    async def test_exchange_stored_from_sd(self, mock_supabase, service, mock_stock_provider):
        """The exchange stored in DB should come from StockDetails (e.g., 'TOR')."""
        sd = _make_stock_details("TSLA.TO", exchange="TOR", price=32.57)
        mock_stock_provider.get_stock_details.return_value = sd
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 6}])

        await service._create_company_from_symbol("TSLA", exchange_override="TOR")

        # Verify the stored ticker_symbol is the original, not the suffixed one
        payload = mock_supabase.table.return_value.insert.call_args[0][0]
        assert payload["ticker_symbol"] == "TSLA"
        assert payload["exchange"] == "TOR"

    @patch("application.services.portfolio_service.supabase")
    async def test_all_lookups_fail_creates_minimal(self, mock_supabase, service, mock_stock_provider):
        """When all lookups fail, should create minimal record with exchange='UNKNOWN'."""
        mock_stock_provider.get_stock_details.return_value = None
        mock_supabase.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"company_id": 7}])

        company_id = await service._create_company_from_symbol("UNKNOWN", exchange_override="TOR")

        payload = mock_supabase.table.return_value.insert.call_args[0][0]
        assert payload["exchange"] == "UNKNOWN"
        assert payload["ticker_symbol"] == "UNKNOWN"
        assert company_id == 7
