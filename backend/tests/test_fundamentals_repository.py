from unittest.mock import MagicMock, patch

import pytest

from infrastructure.repositories.fundamentals_repository import FundamentalsRepository


class TestFundamentalsRepository:

    # ─── is_held_in_portfolio ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_is_held_in_portfolio_held(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        # First call: accounts query → 1 account
        # Second call: holdings query → found
        table.execute.side_effect = [
            MagicMock(data=[{"account_id": 1}]),
            MagicMock(data=[{"holding_id": 42}]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.is_held_in_portfolio(company_id=1, user_id="99")

        assert result is True

        # Verify correct tables were queried
        calls = [c.args[0] for c in mock_supabase_client.table.call_args_list]
        assert calls == ["portfolio_accounts", "portfolio_holdings"]

    @pytest.mark.asyncio
    async def test_is_held_in_portfolio_not_held(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.side_effect = [
            MagicMock(data=[{"account_id": 1}]),
            MagicMock(data=[]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.is_held_in_portfolio(company_id=1, user_id="99")

        assert result is False

    @pytest.mark.asyncio
    async def test_is_held_in_portfolio_no_accounts(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.side_effect = [
            MagicMock(data=[]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.is_held_in_portfolio(company_id=1, user_id="99")

        assert result is False
        # Should not have queried holdings at all
        assert mock_supabase_client.table.call_args_list[0].args[0] == "portfolio_accounts"
        assert len(mock_supabase_client.table.call_args_list) == 1

    # ─── get_buy_anchor ──────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_buy_anchor_found(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.side_effect = [
            MagicMock(data=[{"account_id": 1}]),
            MagicMock(data=[{"first_purchase_date": "2020-06-15", "average_cost": 25.50}]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.get_buy_anchor(company_id=1, user_id="99")

        assert result is not None
        assert result["transaction_date"] == "2020-06-15"
        assert result["unit_price"] == 25.50

    @pytest.mark.asyncio
    async def test_get_buy_anchor_not_found(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.side_effect = [
            MagicMock(data=[{"account_id": 1}]),
            MagicMock(data=[]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.get_buy_anchor(company_id=1, user_id="99")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_buy_anchor_no_accounts(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.side_effect = [
            MagicMock(data=[]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.get_buy_anchor(company_id=1, user_id="99")

        assert result is None
        assert len(mock_supabase_client.table.call_args_list) == 1

    @pytest.mark.asyncio
    async def test_get_buy_anchor_earliest_across_accounts(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.side_effect = [
            MagicMock(data=[{"account_id": 1}, {"account_id": 2}]),
            MagicMock(data=[{"first_purchase_date": "2019-03-01", "average_cost": 18.00}]),
        ]

        repo = FundamentalsRepository()
        with patch("infrastructure.repositories.fundamentals_repository.supabase", mock_supabase_client):
            result = await repo.get_buy_anchor(company_id=1, user_id="99")

        assert result is not None
        assert result["transaction_date"] == "2019-03-01"

        # Verify all account IDs were included
        table.in_.assert_called_once_with("account_id", [1, 2])
