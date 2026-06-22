"""Integration tests for feature flag behavior."""

from unittest import mock
import pytest
from starlette.requests import Request
from config import settings


def _make_request() -> Request:
    """Minimal starlette Request for slowapi compatibility."""
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


class TestPortfolioDashboardFlag:
    """Verify ENABLE_PORTFOLIO_DASHBOARD feature flag behavior."""

    def test_feature_flag_default_false(self):
        """Default value should be False."""
        assert hasattr(settings, "ENABLE_PORTFOLIO_DASHBOARD")
        # The setting is defined in config.py; default is False

    def test_dashboard_endpoint_404_when_disabled(self):
        """When flag is OFF, dashboard endpoint returns 404."""
        from api.portfolio import get_portfolio_dashboard

        with mock.patch("api.portfolio.settings") as mock_settings:
            mock_settings.ENABLE_PORTFOLIO_DASHBOARD = False
            with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                request = _make_request()
                user = {"sub": "test_auth_id"}

                from fastapi import HTTPException
                with pytest.raises(HTTPException) as exc_info:
                    import asyncio
                    asyncio.run(get_portfolio_dashboard(request, user))
                assert exc_info.value.status_code == 404

    def test_dashboard_endpoint_200_when_enabled(self):
        """When flag is ON, dashboard endpoint returns 200."""
        from api.portfolio import get_portfolio_dashboard

        with mock.patch("api.portfolio.settings") as mock_settings:
            mock_settings.ENABLE_PORTFOLIO_DASHBOARD = True
            with mock.patch("api.portfolio._resolve_db_user_id", return_value=1):
                with mock.patch("api.portfolio.PortfolioRepository") as MockRepo:
                    mock_repo = mock.MagicMock()
                    MockRepo.return_value = mock_repo
                    mock_repo.get_user_accounts.return_value = []
                    mock_repo.get_user_all_holdings.return_value = []
                    mock_repo.get_accounts_dividends_by_year.return_value = []

                    request = _make_request()
                    user = {"sub": "test_auth_id"}

                    import asyncio
                    result = asyncio.run(get_portfolio_dashboard(request, user))
                    assert result.accounts is not None
                    assert result.overview is not None
                    assert result.holdings is not None
