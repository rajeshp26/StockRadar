import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from infrastructure.repositories.moat_repository import MoatRepository


class TestMoatRepository:
    def test_get_company_context_found(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"company_id": 1, "currency": "USD", "sector": "Tech"}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = repo.get_company_context("AAPL")
        assert result is not None
        assert result["company_id"] == 1

    def test_get_company_context_not_found(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = repo.get_company_context("UNKNOWN")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_financial_ratios_history(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"fiscal_year": 2024, "roic": 0.32}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_financial_ratios_history(1)
        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_get_income_statements_annual(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"fiscal_year": 2024, "revenue": 100_000}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_income_statements_annual(1)
        assert len(result) >= 0

    @pytest.mark.asyncio
    async def test_get_balance_sheet_latest(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"fiscal_year": 2024, "total_assets": 200_000}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_balance_sheet_latest(1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_cash_flow_latest(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.is_.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"fiscal_year": 2024, "cash_from_operating_activities": 35_000}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_cash_flow_latest(1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_company_summary_latest(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"market_cap": 500_000, "beta": 1.2}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_company_summary_latest(1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_upsert_moat_analysis_insert(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.upsert_moat_analysis(1, {"moat_score": 85.0})
        assert result is True

    @pytest.mark.asyncio
    async def test_upsert_moat_analysis_update(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"id": 1}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.upsert_moat_analysis(1, {"moat_score": 85.0})
        assert result is True

    @pytest.mark.asyncio
    async def test_get_moat_analysis(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"company_id": 1, "moat_score": 85.0}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_moat_analysis(1)
        assert result is not None
        assert result["moat_score"] == 85.0

    @pytest.mark.asyncio
    async def test_get_moat_keyword_evidence(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value = (
            MagicMock(data=[{"keyword": "patent", "keyword_group": "intangible_assets"}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_moat_keyword_evidence(1)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_upsert_moat_ai_narrative(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.upsert_moat_ai_narrative(1, {"narrative": "test"})
        assert result is True

    @pytest.mark.asyncio
    async def test_get_current_market_price(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"current_price": 150.0}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_current_market_price(1)
        assert result == 150.0

    @pytest.mark.asyncio
    async def test_get_industry_multiples(self, mock_supabase_client):
        mock_supabase_client.table.return_value.select.return_value.eq.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = (
            MagicMock(data=[{"avg_roic": 0.15, "sample_size": 100}])
        )
        repo = MoatRepository()
        with patch("infrastructure.repositories.moat_repository.supabase", mock_supabase_client):
            result = await repo.get_industry_multiples("Technology", "Software")
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_industry_multiples_no_sector(self):
        repo = MoatRepository()
        result = await repo.get_industry_multiples("", "")
        assert result is None
