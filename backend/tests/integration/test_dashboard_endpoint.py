"""Integration tests for the /portfolio/dashboard bundle endpoint."""

from contextlib import nullcontext
from unittest import mock

import pytest
from starlette.requests import Request

from api.portfolio import _compute_overview_from_holdings, get_portfolio_dashboard

_DISPLAY_CCY_PATCH = mock.patch("api.portfolio._get_user_preferred_currency", return_value="USD")


# I1d: _passthrough_display helper retired with PortfolioService._apply_display_currency
# (removed in refactor 22942cc4). The dashboard path no longer applies a second
# display-currency conversion.


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
    """Dashboard reads live prices for holdings in exactly one price query.

    I1d: the previous version patched ``enrich_holdings_with_prices`` and
    ``_apply_display_currency``, both removed in refactor 22942cc4. Retargeted
    to the live path (``_get_dashboard_from_prices`` -> current_market_data).
    """
    with (
        mock.patch("api.portfolio.settings") as mock_settings,
        mock.patch("api.portfolio._resolve_db_user_id", return_value=1),
        mock.patch("api.portfolio.PortfolioRepository") as mock_repo_cls,
        mock.patch("api.portfolio.supabase") as mock_supa,
    ):
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        mock_settings.ENABLE_FX_CONVERSION = False
        mock_repo = mock.MagicMock()
        mock_repo_cls.return_value = mock_repo

        mock_repo.get_user_accounts.return_value = [
            {"account_id": 1, "account_name": "Test", "account_type": "brokerage",
             "currency": "USD", "portfolio_brokerages": {"brokerage_name": "TestBroker"}}
        ]
        mock_repo.get_user_all_holdings.return_value = [
            {"symbol": "AAPL", "company_id": 1, "quantity": 10, "total_cost": 1500.0,
             "account_id": 1, "average_cost": 150.0}
        ]
        mock_repo.get_accounts_dividends_by_year.return_value = []

        price_table = mock.MagicMock()
        price_table.select.return_value = price_table
        price_table.in_.return_value = price_table
        price_table.execute.return_value = mock.MagicMock(data=[
            {"company_id": 1, "current_price": 100.0,
             "last_updated": "2026-11-20T00:00:00Z"}
        ])

        def _table(name, *_a, **_kw):
            if name == "current_market_data":
                return price_table
            empty = mock.MagicMock()
            empty.select.return_value = empty
            empty.in_.return_value = empty
            empty.execute.return_value = mock.MagicMock(data=[])
            return empty

        mock_supa.table.side_effect = _table
        result = await get_portfolio_dashboard(_make_request(), {"sub": "test_auth_id"})

        assert price_table.execute.call_count == 1
        assert result.holdings[0].current_price == 100.0
        assert result.accounts is not None
        assert result.overview is not None


async def test_dashboard_returns_all_sections():
    """Dashboard response has accounts, overview, holdings keys."""
    with (
        mock.patch("api.portfolio.settings") as mock_settings,
        _DISPLAY_CCY_PATCH,
        nullcontext(),  # I1d: _apply_display_currency removed in 22942cc4
        mock.patch("api.portfolio._resolve_db_user_id", return_value=1),
        mock.patch("api.portfolio.PortfolioRepository") as mock_repo_cls,
    ):
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        mock_repo = mock.MagicMock()
        mock_repo_cls.return_value = mock_repo
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
    with (
        mock.patch("api.portfolio.settings") as mock_settings,
        _DISPLAY_CCY_PATCH,
        nullcontext(),  # I1d: _apply_display_currency removed in 22942cc4
        mock.patch("api.portfolio._resolve_db_user_id", return_value=1),
        mock.patch("api.portfolio.PortfolioRepository") as mock_repo_cls,
    ):
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        mock_repo = mock.MagicMock()
        mock_repo_cls.return_value = mock_repo
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
    with (
        mock.patch("api.portfolio.settings") as mock_settings,
        _DISPLAY_CCY_PATCH,
        nullcontext(),  # I1d: _apply_display_currency removed in 22942cc4
        mock.patch("api.portfolio._resolve_db_user_id", return_value=1),
        mock.patch("api.portfolio.PortfolioRepository") as mock_repo_cls,
    ):
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        mock_repo = mock.MagicMock()
        mock_repo_cls.return_value = mock_repo
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
    with (
        mock.patch("api.portfolio.settings") as mock_settings,
        _DISPLAY_CCY_PATCH,
        nullcontext(),  # I1d: _apply_display_currency removed in 22942cc4
        mock.patch("api.portfolio._resolve_db_user_id", return_value=1),
        mock.patch("api.portfolio.PortfolioRepository") as mock_repo_cls,
    ):
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        mock_repo = mock.MagicMock()
        mock_repo_cls.return_value = mock_repo
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
    with (
        mock.patch("api.portfolio.settings") as mock_settings,
        _DISPLAY_CCY_PATCH,
        nullcontext(),  # I1d: _apply_display_currency removed in 22942cc4
        mock.patch("api.portfolio._resolve_db_user_id", return_value=1),
        mock.patch("api.portfolio.PortfolioRepository") as mock_repo_cls,
    ):
        mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
        mock_repo = mock.MagicMock()
        mock_repo_cls.return_value = mock_repo
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
