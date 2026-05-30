"""
Tests for portfolio overview account filtering.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from application.services.portfolio_service import PortfolioService


@pytest.fixture
def mock_overview_repo():
    repo = MagicMock()
    repo.get_user_accounts.return_value = [
        {"account_id": 1, "account_name": "TFSA", "account_type": "TFSA", "brokerage_name": "Test", "is_active": True},
        {"account_id": 2, "account_name": "RRSP", "account_type": "RRSP", "brokerage_name": "Test", "is_active": True},
    ]
    repo.get_account_dividends_by_year.return_value = []
    return repo


@pytest.fixture
def mock_financial_repo():
    repo = MagicMock()
    repo.get_company_by_symbol = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def service(mock_overview_repo, mock_financial_repo):
    return PortfolioService(mock_overview_repo, mock_financial_repo)


def _make_holding(symbol: str, value: float, cost: float, account_id: int = 1):
    return {
        "symbol": symbol,
        "company_id": 1,
        "sector": "Technology",
        "current_value": value,
        "total_cost": cost,
        "account_id": account_id,
        "account_name": "TFSA",
        "shares": 10,
        "currency": "USD",
    }


MOCK_HOLDINGS = [
    _make_holding("AAPL", 50000, 40000, account_id=1),
    _make_holding("GOOGL", 30000, 25000, account_id=2),
]


@pytest.mark.anyio
class TestGetUserPortfolioOverviewFiltering:

    async def test_overview_no_filter(self, service, mock_overview_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_user_portfolio_overview(1)
        assert result["success"]
        assert len(result.get("account_breakdown", [])) == 2

    async def test_overview_filter_single_account(self, service, mock_overview_repo):
        single = [_make_holding("AAPL", 50000, 40000, account_id=1)]
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=single)):
            result = await service.get_user_portfolio_overview(1, account_ids=[1])
        assert result["success"]
        assert result["net_worth"] == 50000.0

    async def test_overview_filter_invalid_ids_returns_empty(self, service, mock_overview_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=[])):
            result = await service.get_user_portfolio_overview(1, account_ids=[999])
        assert not result["success"]
        assert "error" in result

    async def test_overview_filter_multiple_accounts(self, service, mock_overview_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_user_portfolio_overview(1, account_ids=[1, 2])
        assert result["success"]
        assert len(result.get("account_breakdown", [])) == 2

    async def test_overview_security_other_user_ids_filtered(self, service, mock_overview_repo):
        mock_overview_repo.get_user_accounts.return_value = [
            {"account_id": 1, "account_name": "TFSA", "account_type": "TFSA", "is_active": True},
        ]
        single = [_make_holding("AAPL", 50000, 40000, account_id=1)]
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=single)):
            result = await service.get_user_portfolio_overview(1, account_ids=[1, 2, 3])
        assert result["success"]
        assert result["net_worth"] == 50000.0
