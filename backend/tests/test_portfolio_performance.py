"""
Tests for portfolio performance account filtering.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from application.services.portfolio_service import PortfolioService


@pytest.fixture
def mock_portfolio_repo():
    repo = MagicMock()
    repo.get_user_accounts.return_value = [
        {"account_id": 1, "account_name": "TFSA", "account_type": "TFSA", "brokerage_name": "Test", "is_active": True},
        {"account_id": 2, "account_name": "RRSP", "account_type": "RRSP", "brokerage_name": "Test", "is_active": True},
    ]
    repo.get_account_transactions.return_value = []
    repo.get_earliest_transaction_date.return_value = None
    return repo


@pytest.fixture
def mock_financial_repo():
    repo = MagicMock()
    repo.get_company_by_symbol = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def service(mock_portfolio_repo, mock_financial_repo):
    return PortfolioService(mock_portfolio_repo, mock_financial_repo)


@pytest.mark.anyio
class TestGetPortfolioPerformanceAccountFiltering:

    async def test_no_filter_uses_all_accounts(self, service, mock_portfolio_repo):
        with patch.object(service, '_period_to_date_range', return_value=(date(2025, 1, 1), date(2026, 1, 1))):
            result = await service.get_portfolio_performance(1, "1Y")
        mock_portfolio_repo.get_user_accounts.assert_called_with(1)
        assert result["success"]

    async def test_filter_single_account(self, service, mock_portfolio_repo):
        with patch.object(service, '_period_to_date_range', return_value=(date(2025, 1, 1), date(2026, 1, 1))):
            result = await service.get_portfolio_performance(1, "1Y", account_ids=[1])
        assert result["success"]
        calls = [c for c in mock_portfolio_repo.get_account_transactions.call_args_list]
        ids = {c[0][0] for c in calls}
        assert ids == {1}

    async def test_filter_multiple_accounts(self, service, mock_portfolio_repo):
        with patch.object(service, '_period_to_date_range', return_value=(date(2025, 1, 1), date(2026, 1, 1))):
            result = await service.get_portfolio_performance(1, "1Y", account_ids=[1, 2])
        assert result["success"]
        calls = [c for c in mock_portfolio_repo.get_account_transactions.call_args_list]
        ids = {c[0][0] for c in calls}
        assert ids == {1, 2}

    async def test_filter_invalid_ids_returns_empty(self, service, mock_portfolio_repo):
        result = await service.get_portfolio_performance(1, "1Y", account_ids=[999])
        assert len(result["snapshots"]) == 0

    async def test_filter_mixed_valid_and_invalid(self, service, mock_portfolio_repo):
        with patch.object(service, '_period_to_date_range', return_value=(date(2025, 1, 1), date(2026, 1, 1))):
            result = await service.get_portfolio_performance(1, "1Y", account_ids=[1, 999])
        assert result["success"]
        calls = [c for c in mock_portfolio_repo.get_account_transactions.call_args_list]
        ids = {c[0][0] for c in calls}
        assert ids == {1}

    async def test_security_other_user_ids_filtered(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_user_accounts.return_value = [
            {"account_id": 1, "account_name": "TFSA", "is_active": True},
        ]
        with patch.object(service, '_period_to_date_range', return_value=(date(2025, 1, 1), date(2026, 1, 1))):
            result = await service.get_portfolio_performance(1, "1Y", account_ids=[1, 2, 3])
        assert result["success"]
        calls = [c for c in mock_portfolio_repo.get_account_transactions.call_args_list]
        ids = {c[0][0] for c in calls}
        assert ids == {1}


@pytest.mark.anyio
class TestGetPerformanceCompareAccountFiltering:

    async def test_compare_no_filter(self, service, mock_portfolio_repo):
        with patch.object(service, 'get_portfolio_performance', new=AsyncMock(return_value={
            "success": True, "period": "1Y", "snapshots": [
                {"date": "2025-01-01", "value": 50000, "cost_basis": 40000, "net_deposits": 30000},
            ]
        })):
            result = await service.get_performance_compare(1, "1Y", ["SPY"])
        assert result["success"]

    async def test_compare_with_filter(self, service, mock_portfolio_repo):
        perf = AsyncMock(return_value={
            "success": True, "period": "1Y", "snapshots": [
                {"date": "2025-01-01", "value": 25000, "cost_basis": 20000, "net_deposits": 15000},
            ]
        })
        with patch.object(service, 'get_portfolio_performance', perf):
            result = await service.get_performance_compare(1, "1Y", ["SPY"], account_ids=[1])
        assert result["success"]

    async def test_compare_invalid_ids_empty(self, service, mock_portfolio_repo):
        result = await service.get_performance_compare(1, "1Y", ["SPY"], account_ids=[999])
        assert len(result.get("portfolio", [])) == 0
