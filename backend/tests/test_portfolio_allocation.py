"""
Tests for portfolio allocation endpoint and service.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from application.services.portfolio_service import PortfolioService


@pytest.fixture
def mock_alloc_repo():
    repo = MagicMock()
    repo.get_user_accounts.return_value = [
        {"account_id": 1, "account_name": "TFSA", "account_type": "TFSA", "brokerage_name": "Test", "is_active": True},
        {"account_id": 2, "account_name": "RRSP", "account_type": "RRSP", "brokerage_name": "Test", "is_active": True},
        {"account_id": 3, "account_name": "Non-reg", "account_type": "Non-registered", "brokerage_name": "Test", "is_active": True},
    ]
    repo.get_user_all_holdings.return_value = [
        {"company_id": 1, "symbol": "AAPL", "sector": "Technology", "security_type": "stock", "total_cost": 8000, "account_id": 1, "account_name": "TFSA", "shares": 10, "currency": "USD", "quantity": 10},
        {"company_id": 2, "symbol": "GOOGL", "sector": "Technology", "security_type": "stock", "total_cost": 6500, "account_id": 1, "account_name": "TFSA", "shares": 5, "currency": "USD", "quantity": 5},
        {"company_id": 3, "symbol": "XOM", "sector": "Energy", "security_type": "stock", "total_cost": 5500, "account_id": 1, "account_name": "TFSA", "shares": 20, "currency": "USD", "quantity": 20},
    ]
    return repo


@pytest.fixture
def mock_financial_repo():
    repo = MagicMock()
    repo.get_company_by_symbol = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def service(mock_alloc_repo, mock_financial_repo):
    return PortfolioService(mock_alloc_repo, mock_financial_repo)


def _make_holding(
    symbol: str, sector: str, value: float, cost: float,
    account_id: int = 1, account_name: str = "TFSA",
    security_type: str = "stock",
):
    return {
        "symbol": symbol,
        "company_id": 1,
        "sector": sector,
        "security_type": security_type,
        "current_value": value,
        "total_cost": cost,
        "account_id": account_id,
        "account_name": account_name,
        "shares": 10,
        "currency": "USD",
    }


MOCK_HOLDINGS = [
    _make_holding("AAPL", "Technology", 10000, 8000),
    _make_holding("GOOGL", "Technology", 8000, 6500),
    _make_holding("XOM", "Energy", 5000, 5500),
]


@pytest.mark.anyio
class TestGetPortfolioAllocation:

    async def test_allocation_by_sector_returns_types(self, service, mock_alloc_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_portfolio_allocation(1, group_by="sector")
        assert result["success"]
        assert "types" in result
        assert len(result["types"]) == 1
        assert result["types"][0]["type"] == "stock"
        assert result["types"][0]["type_label"] == "Stocks"

    async def test_allocation_by_sector_sectors_inside_type(self, service, mock_alloc_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_portfolio_allocation(1, group_by="sector")
        stock_type = result["types"][0]
        sector_names = {s["segment"] for s in stock_type["sectors"]}
        assert "Technology" in sector_names
        assert "Energy" in sector_names

    async def test_allocation_total_value(self, service, mock_alloc_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_portfolio_allocation(1, group_by="sector")
        assert result["success"]
        assert result["total_value"] == 23000

    async def test_allocation_by_account_flat(self, service, mock_alloc_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_portfolio_allocation(1, group_by="account")
        assert result["success"]
        assert len(result["segments"]) > 0
        assert "types" not in result or result["types"] == []

    async def test_allocation_filter_account_ids(self, service, mock_alloc_repo):
        filtered = [_make_holding("AAPL", "Technology", 10000, 8000)]
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=filtered)):
            result = await service.get_portfolio_allocation(1, group_by="sector", account_ids=[1])
        assert result["success"]
        total = sum(s["value"] for s in result["segments"])
        assert total == 10000

    async def test_allocation_no_holdings(self, service, mock_alloc_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=[])):
            result = await service.get_portfolio_allocation(1, group_by="sector")
        assert result["success"]
        assert len(result["segments"]) == 0
        assert result["total_value"] == 0


@pytest.mark.anyio
class TestGetPortfolioAllocationEdgeCases:

    async def test_allocation_security_other_user_accounts(self, service, mock_alloc_repo):
        mock_alloc_repo.get_user_accounts.return_value = [
            {"account_id": 1, "account_name": "TFSA", "is_active": True},
        ]
        filtered = [_make_holding("AAPL", "Technology", 5000, 4000)]
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=filtered)):
            result = await service.get_portfolio_allocation(1, account_ids=[1, 999])
        assert result["success"]
        assert result["total_value"] == 5000

    async def test_allocation_unknown_accounts_empty(self, service, mock_alloc_repo):
        mock_alloc_repo.get_user_accounts.return_value = []
        result = await service.get_portfolio_allocation(1, account_ids=[999])
        assert result["success"]
        assert len(result["segments"]) == 0

    async def test_allocation_handles_empty_holdings(self, service, mock_alloc_repo):
        mock_alloc_repo.get_user_accounts.return_value = []
        result = await service.get_portfolio_allocation(1, group_by="sector")
        assert result["success"]
        assert result["total_value"] == 0

    async def test_allocation_with_missing_sector(self, service, mock_alloc_repo):
        no_sector = [
            _make_holding("ETHY", None, 1000, 900, security_type="etf"),
        ]
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=no_sector)):
            result = await service.get_portfolio_allocation(1, group_by="sector")
        assert result["success"]
        assert len(result["types"]) == 1
        assert result["types"][0]["type"] == "etf"
        assert result["types"][0]["type_label"] == "ETFs"
        # The missing sector should appear as "Unknown" inside the ETF type
        assert result["types"][0]["sectors"][0]["segment"] == "Unknown"
        assert result["types"][0]["sectors"][0]["value"] == 1000

    async def test_allocation_mixed_types(self, service, mock_alloc_repo):
        mixed = [
            _make_holding("AAPL", "Technology", 10000, 8000, security_type="stock"),
            _make_holding("QQQ", None, 5000, 4500, security_type="etf"),
            _make_holding("SPY", None, 3000, 2800, security_type="etf"),
        ]
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=mixed)):
            result = await service.get_portfolio_allocation(1, group_by="sector")
        assert result["success"]
        assert len(result["types"]) == 2
        type_map = {t["type"]: t for t in result["types"]}
        assert "stock" in type_map
        assert "etf" in type_map
        assert type_map["stock"]["value"] == 10000
        assert type_map["etf"]["value"] == 8000
        assert type_map["etf"]["count"] == 2

    async def test_allocation_geography_still_flat(self, service, mock_alloc_repo):
        with patch.object(service, 'enrich_holdings_with_prices', new=AsyncMock(return_value=MOCK_HOLDINGS)):
            result = await service.get_portfolio_allocation(1, group_by="geography")
        assert result["success"]
        assert "types" not in result or result["types"] == []
        assert len(result["segments"]) > 0
