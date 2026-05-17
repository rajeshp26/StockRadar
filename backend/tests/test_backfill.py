from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestBackfillCompany:
    """Verify derived metrics + valuation calls in backfill_company."""

    @pytest.fixture(autouse=True)
    def _patch_supabase(self):
        patch_db = patch("database.supabase")
        mock_supabase = patch_db.start()
        mock_supabase.table.return_value = MagicMock()
        yield
        patch_db.stop()

    async def test_dry_run_returns_noop(self):
        from scripts.phase7_backfill import backfill_company

        mock_repo = AsyncMock()
        mock_provider = AsyncMock()
        mock_valuation = AsyncMock()

        result = await backfill_company(
            repo=mock_repo, provider=mock_provider,
            valuation_service=mock_valuation,
            company={"company_id": 1, "ticker_symbol": "AAPL"},
            dry_run=True,
        )

        assert result["status"] == "dry_run"
        mock_provider.get_all_financials_optimized.assert_not_called()
        mock_valuation.compute_residual_income_if_stale.assert_not_called()

    async def test_triggers_derived_metrics_after_upsert(self):
        from scripts.phase7_backfill import backfill_company
        import scripts.phase7_backfill as bp

        mock_repo = AsyncMock()
        mock_provider = AsyncMock()
        mock_valuation = AsyncMock()

        mock_provider.get_all_financials_optimized.return_value = MagicMock(
            income_statements=MagicMock(
                rows=[MagicMock(fiscal_year=2024, fiscal_quarter=None)]
            ),
        )
        mock_repo.upsert_all_financials.return_value = {
            "income_statements": 10, "balance_sheets": 5, "cash_flows": 4,
        }

        with patch.object(bp, "supabase", MagicMock()):
            with patch("scripts.phase7_backfill.compute_and_upsert_derived_financial_metrics") as mock_derived:
                result = await backfill_company(
                    repo=mock_repo, provider=mock_provider,
                    valuation_service=mock_valuation,
                    company={"company_id": 1, "ticker_symbol": "AAPL"},
                    dry_run=False,
                )

        mock_derived.assert_called_once_with(company_id=1)
        assert result["status"] == "ok"

    async def test_triggers_valuation_with_force(self):
        from scripts.phase7_backfill import backfill_company
        import scripts.phase7_backfill as bp

        mock_repo = AsyncMock()
        mock_provider = AsyncMock()
        mock_valuation = AsyncMock()

        mock_provider.get_all_financials_optimized.return_value = MagicMock(
            income_statements=MagicMock(
                rows=[MagicMock(fiscal_year=2024, fiscal_quarter=None)]
            ),
        )
        mock_repo.upsert_all_financials.return_value = {
            "income_statements": 10, "balance_sheets": 5, "cash_flows": 4,
        }

        with patch.object(bp, "supabase", MagicMock()):
            with patch("scripts.phase7_backfill.compute_and_upsert_derived_financial_metrics"):
                result = await backfill_company(
                    repo=mock_repo, provider=mock_provider,
                    valuation_service=mock_valuation,
                    company={"company_id": 1, "ticker_symbol": "AAPL"},
                    dry_run=False,
                )

        mock_valuation.compute_residual_income_if_stale.assert_called_once_with(
            symbol="AAPL", user_id=None, force=True
        )
        assert result["status"] == "ok"

    async def test_handles_provider_failure_gracefully(self):
        from scripts.phase7_backfill import backfill_company
        import scripts.phase7_backfill as bp

        mock_repo = AsyncMock()
        mock_provider = AsyncMock()
        mock_valuation = AsyncMock()

        mock_provider.get_all_financials_optimized.side_effect = Exception("API timeout")

        with patch.object(bp, "supabase", MagicMock()):
            with patch("scripts.phase7_backfill.compute_and_upsert_derived_financial_metrics"):
                result = await backfill_company(
                    repo=mock_repo, provider=mock_provider,
                    valuation_service=mock_valuation,
                    company={"company_id": 1, "ticker_symbol": "AAPL"},
                    dry_run=False,
                )

        assert result["status"] == "error"
        assert "API timeout" in result["error"]
