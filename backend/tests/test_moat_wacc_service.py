import pytest
from unittest.mock import AsyncMock, MagicMock

from application.services.moat_wacc_service import MoatWaccService


class TestMoatWaccService:
    @pytest.mark.asyncio
    async def test_compute_wacc_happy_path(self, mock_moat_repo):
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None
        assert 0.0 < wacc < 0.20

    @pytest.mark.asyncio
    async def test_compute_wacc_no_beta(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": 500_000, "beta": None}
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None

    @pytest.mark.asyncio
    async def test_compute_wacc_no_debt(self, mock_moat_repo):
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(
            return_value={
                "fiscal_year": 2024,
                "total_assets": 200_000,
                "shareholders_equity": 100_000,
                "total_debt": None,
                "cash_and_cash_equivalents": 20_000,
            }
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None

    @pytest.mark.asyncio
    async def test_compute_wacc_no_equity_value(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": None, "beta": 1.0}
        )
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(
            return_value={
                "fiscal_year": 2024,
                "total_assets": 200_000,
                "shareholders_equity": None,
            }
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is None

    @pytest.mark.asyncio
    async def test_compute_wacc_falls_back_to_equity(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": None, "beta": 1.2}
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None

    @pytest.mark.asyncio
    async def test_compute_wacc_negative_beta(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": 500_000, "beta": -0.5}
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None
        assert wacc >= 0.01

    @pytest.mark.asyncio
    async def test_compute_wacc_missing_tax_rate(self, mock_moat_repo):
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None
        assert 0.0 < wacc < 0.20

    # ── NEG-11: Both balance sheet and company summary return None ──

    @pytest.mark.asyncio
    async def test_compute_wacc_no_data_at_all(self, mock_moat_repo):
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(return_value=None)
        mock_moat_repo.get_company_summary_latest = AsyncMock(return_value=None)
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is None

    # ── NEG-12: Both market_cap and shareholders_equity are None ────

    @pytest.mark.asyncio
    async def test_compute_wacc_no_equity_source(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": None, "beta": 1.2}
        )
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(
            return_value={
                "fiscal_year": 2024, "total_assets": 200_000,
                "shareholders_equity": None, "total_debt": 40_000,
                "cash_and_cash_equivalents": 20_000,
            }
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is None

    # ── NEG-13: Zero market cap ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_compute_wacc_zero_market_cap(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": 0, "beta": 1.0}
        )
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(
            return_value={
                "fiscal_year": 2024, "total_assets": 200_000,
                "shareholders_equity": 80_000, "total_debt": 40_000,
                "cash_and_cash_equivalents": 20_000,
            }
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is None

    # ── NEG-14: Very large beta ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_compute_wacc_extreme_beta(self, mock_moat_repo):
        mock_moat_repo.get_company_summary_latest = AsyncMock(
            return_value={"market_cap": 500_000, "beta": 5.0}
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None
        assert wacc > 0.10

    # ── NEG-15: Zero total_debt is handled ──────────────────────────

    @pytest.mark.asyncio
    async def test_compute_wacc_zero_debt(self, mock_moat_repo):
        mock_moat_repo.get_balance_sheet_latest = AsyncMock(
            return_value={
                "fiscal_year": 2024, "total_assets": 200_000,
                "shareholders_equity": 80_000, "total_debt": 0,
                "cash_and_cash_equivalents": 20_000,
            }
        )
        svc = MoatWaccService(mock_moat_repo)
        wacc = await svc.compute_wacc(1)
        assert wacc is not None
        assert 0.0 < wacc < 0.20
