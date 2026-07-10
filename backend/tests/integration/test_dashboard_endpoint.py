"""Integration tests for the /portfolio/dashboard bundle endpoint."""

from unittest import mock
import pytest
from starlette.requests import Request
from starlette.datastructures import URL, Headers, QueryParams

from api.portfolio import get_portfolio_dashboard, _compute_overview_from_holdings
from application.services.portfolio_service import PortfolioService

_DISPLAY_CCY_PATCH = mock.patch("api.portfolio._get_user_preferred_currency", return_value="USD")


async def _passthrough_display(holdings, display_currency):
    return holdings


def _make_request() -> Request:
    """Build a minimal starlette Request that passes slowapi's isinstance check."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/portfolio/dashboard",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_compute_overview_from_holdings():
    """_compute_overview_from_holdings aggregates correctly."""
    holdings = [
        {"current_value": 1500.0, "total_cost": 1000.0},
        {"current_value": 2500.0, "total_cost": 2000.0},
    ]
    accounts = [{"account_id": 1, "account_name": "Test"}]
    result = _compute_overview_from_holdings(holdings, accounts, 1, 100.0)
    assert result["total_value"] == 4000.0
    assert result["total_cost_basis"] == 3000.0
    assert result["total_gain_loss"] == 1000.0
    assert result["ytd_dividends"] == 100.0
    assert result["holdings_count"] == 2
    assert result["accounts_count"] == 1


@pytest.mark.asyncio
async def test_dashboard_single_enrichment_call():
    """Dashboard endpoint should call enrich_holdings_with_prices exactly once."""
    from api.portfolio import _get_portfolio_service
    enrich_count = 0
    original_enrich = PortfolioService.enrich_holdings_with_prices

    async def tracking_enrich(self, holdings, account_base_currency=None):
        nonlocal enrich_count
        enrich_count += 1
        if not holdings:
            return holdings
        for h in holdings:
            h["current_price"] = 100.0
            h["current_value"] = float(h.get("quantity", 0) or 0) * 100.0
            h["unrealized_gain_loss"] = 0.0
            h["unrealized_gain_loss_pct"] = 0.0
            h["company_name"] = h.get("symbol", "Unknown")
            h["value_currency"] = account_base_currency or "USD"
        return holdings

    with mock.patch.object(PortfolioService, "enrich_holdings_with_prices", tracking_enrich):
        with mock.patch.object(PortfolioService, "_apply_display_currency") as mock_display:
            async def passthrough(holdings, display_currency):
                return holdings
            mock_display.side_effect = passthrough
            with mock.patch("api.portfolio.settings") as mock_settings:
                mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
                mock_settings.ENABLE_FX_CONVERSION = True
                with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                    with mock.patch("api.portfolio._get_user_preferred_currency", return_value="USD"):
                        with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                            mock_repo = mock.MagicMock()
                            MockRepo.return_value = mock_repo

                            mock_repo.get_user_accounts.return_value = [
                                {"account_id": 1, "account_name": "Test", "account_type": "brokerage",
                                 "currency": "USD", "portfolio_brokerages": {"brokerage_name": "TestBroker"}}
                            ]
                            mock_repo.get_user_all_holdings.return_value = [
                                {"symbol": "AAPL", "company_id": 1, "quantity": 10, "total_cost": 1500.0,
                                 "account_id": 1, "average_cost": 150.0}
                            ]
                            mock_repo.get_accounts_dividends_by_year.return_value = []

                            request = _make_request()
                            user = {"sub": "test_auth_id"}

                            result = await get_portfolio_dashboard(request, user)

                            assert enrich_count == 1
                            assert result.accounts is not None
                            assert result.overview is not None
                            assert result.holdings is not None


async def test_dashboard_returns_all_sections():
    """Dashboard response has accounts, overview, holdings keys."""
    with mock.patch("api.portfolio.settings") as mock_settings:
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        with _DISPLAY_CCY_PATCH:
            with mock.patch.object(PortfolioService, "_apply_display_currency", side_effect=_passthrough_display):
                with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                    with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                        mock_repo = mock.MagicMock()
                        MockRepo.return_value = mock_repo
                        mock_repo.get_user_accounts.return_value = [
                            {"account_id": 1, "account_name": "Test", "account_type": "brokerage",
                             "currency": "USD", "portfolio_brokerages": {"brokerage_name": "Test"}}
                        ]
                        mock_repo.get_user_all_holdings.return_value = []
                        mock_repo.get_accounts_dividends_by_year.return_value = []

                        request = _make_request()
                        user = {"sub": "test_auth_id"}
                        result = await get_portfolio_dashboard(request, user)

                        assert result.accounts is not None
                        assert result.overview is not None
                        assert result.holdings is not None


@pytest.mark.asyncio
async def test_dashboard_empty_accounts():
    """User with zero accounts -> accounts:[], counts are 0."""
    with mock.patch("api.portfolio.settings") as mock_settings:
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        with _DISPLAY_CCY_PATCH:
            with mock.patch.object(PortfolioService, "_apply_display_currency", side_effect=_passthrough_display):
                with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                    with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                        mock_repo = mock.MagicMock()
                        MockRepo.return_value = mock_repo
                        mock_repo.get_user_accounts.return_value = []
                        mock_repo.get_user_all_holdings.return_value = []
                        mock_repo.get_accounts_dividends_by_year.return_value = []

                        request = _make_request()
                        user = {"sub": "test_auth_id"}
                        result = await get_portfolio_dashboard(request, user)

                        assert result.accounts == []
                        assert result.overview.total_value == 0.0
                        assert result.overview.holdings_count == 0
                        assert result.overview.accounts_count == 0
                        assert result.holdings == []


@pytest.mark.asyncio
async def test_dashboard_includes_ytd_dividends():
    """User has dividends this year -> ytd_dividends > 0 in overview."""
    with mock.patch("api.portfolio.settings") as mock_settings:
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        with _DISPLAY_CCY_PATCH:
            with mock.patch.object(PortfolioService, "_apply_display_currency", side_effect=_passthrough_display):
                with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                    with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                        mock_repo = mock.MagicMock()
                        MockRepo.return_value = mock_repo
                        mock_repo.get_user_accounts.return_value = [
                            {"account_id": 1, "account_name": "Test", "account_type": "brokerage",
                             "currency": "USD", "portfolio_brokerages": {"brokerage_name": "Test"}}
                        ]
                        mock_repo.get_user_all_holdings.return_value = []
                        mock_repo.get_accounts_dividends_by_year.return_value = [
                            {"amount": 100.0}, {"amount": 50.0}
                        ]

                        request = _make_request()
                        user = {"sub": "test_auth_id"}
                        result = await get_portfolio_dashboard(request, user)

                        assert result.overview.ytd_dividends == 150.0


@pytest.mark.asyncio
async def test_dashboard_holdings_summary_fields():
    """Holdings summary contains only expected fields."""
    with mock.patch("api.portfolio.settings") as mock_settings:
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        with _DISPLAY_CCY_PATCH:
            with mock.patch.object(PortfolioService, "_apply_display_currency", side_effect=_passthrough_display):
                with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                    with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                        mock_repo = mock.MagicMock()
                        MockRepo.return_value = mock_repo
                        mock_repo.get_user_accounts.return_value = [
                            {"account_id": 1, "account_name": "Test", "account_type": "brokerage",
                             "currency": "USD", "portfolio_brokerages": {"brokerage_name": "Test"}},
                        ]
                        mock_repo.get_user_all_holdings.return_value = [
                            {"symbol": "AAPL", "company_id": 1, "quantity": 10, "total_cost": 1500.0,
                             "account_id": 1, "average_cost": 150.0}
                        ]
                        mock_repo.get_accounts_dividends_by_year.return_value = []

                        request = _make_request()
                        user = {"sub": "test_auth_id"}

                        mock_supa_table = mock.MagicMock()
                        mock_supa_table.select.return_value = mock_supa_table
                        mock_supa_table.in_.return_value = mock_supa_table
                        mock_supa_table.order.return_value = mock_supa_table
                        mock_supa_table.execute.return_value = mock.MagicMock(data=[])
                        with mock.patch("application.services.portfolio_service.supabase") as mock_supa:
                            mock_supa.table.return_value = mock_supa_table
                            result = await get_portfolio_dashboard(request, user)

                for h in result.holdings:
                    expected_keys = {"company_id", "symbol", "company_name", "quantity", "current_price",
                                     "current_value", "total_cost", "unrealized_gain_loss",
                                     "unrealized_gain_loss_pct", "value_currency"}
                    assert set(h.model_dump().keys()) == expected_keys


@pytest.mark.asyncio
async def test_dashboard_accounts_summary_fields():
    """Accounts summary contains only expected fields."""
    with mock.patch("api.portfolio.settings") as mock_settings:
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        with _DISPLAY_CCY_PATCH:
            with mock.patch.object(PortfolioService, "_apply_display_currency", side_effect=_passthrough_display):
                with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                    with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                        mock_repo = mock.MagicMock()
                        MockRepo.return_value = mock_repo
                        mock_repo.get_user_accounts.return_value = [
                            {"account_id": 1, "account_name": "Test", "account_type": "brokerage",
                             "currency": "USD", "portfolio_brokerages": {"brokerage_name": "Test"}},
                        ]
                        mock_repo.get_user_all_holdings.return_value = [
                            {"symbol": "AAPL", "company_id": 1, "quantity": 10, "total_cost": 1500.0,
                             "account_id": 1, "average_cost": 150.0}
                        ]
                        mock_repo.get_accounts_dividends_by_year.return_value = []

                        request = _make_request()
                        user = {"sub": "test_auth_id"}

                        mock_supa_table2 = mock.MagicMock()
                        mock_supa_table2.select.return_value = mock_supa_table2
                        mock_supa_table2.in_.return_value = mock_supa_table2
                        mock_supa_table2.order.return_value = mock_supa_table2
                        mock_supa_table2.execute.return_value = mock.MagicMock(data=[])
                        with mock.patch("application.services.portfolio_service.supabase") as mock_supa:
                            mock_supa.table.return_value = mock_supa_table2
                            result = await get_portfolio_dashboard(request, user)

                for acc in result.accounts:
                    expected_keys = {"account_id", "account_name", "account_type",
                                     "brokerage_name", "currency", "holdings_count",
                                     "total_value", "total_cost", "gain_loss",
                                     "gain_loss_pct", "value_currency"}
                    assert set(acc.model_dump().keys()) == expected_keys
