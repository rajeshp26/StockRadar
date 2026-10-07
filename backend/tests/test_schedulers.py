from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


class TestEarningsSchedulerInit:
    async def test_init_stores_repos_and_providers(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
        scheduler = EarningsRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
        )
        assert scheduler.financial_repo is mock_financial_repo
        assert scheduler.defeat_beta_provider is mock_defeat_beta_provider
        assert scheduler.is_running is False

    async def test_start_sets_is_running(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
        scheduler = EarningsRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
        )
        await scheduler.start()
        assert scheduler.is_running is True
        assert scheduler.task is not None
        await scheduler.stop()

    async def test_stop_works_when_not_running(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
        scheduler = EarningsRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
        )
        await scheduler.stop()
        assert scheduler.is_running is False


class TestEarningsSchedulerCheckAndRefresh:
    @pytest.fixture(autouse=True)
    def _setup_scheduler(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
        self.scheduler = EarningsRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
        )
        self.mock_repo = mock_financial_repo
        self.mock_provider = mock_defeat_beta_provider

    async def test_no_companies_returns_early(self):
        self.mock_repo.get_companies_with_upcoming_earnings.return_value = []

        result = await self.scheduler._check_and_refresh_earnings()

        assert result["companies_found"] == 0
        assert result["companies_refreshed"] == 0

    async def test_refresh_triggers_derived_metrics_when_rows_written(self):
        self.mock_repo.get_company_refresh_info.return_value = SimpleNamespace(
            company_id=1, ticker_symbol="AAPL",
            exchange=None,
            first_financial_data_loaded_at=datetime(2024, 1, 1),
            last_refreshed_fiscal_year=2024,
            last_refreshed_fiscal_quarter=None,
            data_completeness_status="COMPLETE",
        )
        self.mock_provider.get_all_financials_optimized.return_value = SimpleNamespace(
            income_statements=SimpleNamespace(rows=[SimpleNamespace(fiscal_year=2024, fiscal_quarter=None)]),
            balance_sheets=SimpleNamespace(),
            cash_flows=SimpleNamespace(),
            earnings=SimpleNamespace(),
            dividends=SimpleNamespace(),
            next_earnings_date=date(2025, 1, 30),
        )
        self.mock_repo.upsert_all_financials.return_value = {
            "income_statements": 5, "balance_sheets": 3, "cash_flows": 2,
            "earnings": 0, "dividends": 0,
        }

        with patch("application.schedulers.earnings_scheduler.compute_and_upsert_derived_financial_metrics") as mock_derived:
            with patch("application.schedulers.earnings_scheduler.audit_company_data_quality"):
                with patch("application.services.valuation_service.ValuationService") as mock_vs:
                    mock_vs.return_value = AsyncMock()
                    await self.scheduler._refresh_company_financials_optimized(
                        company_id=1, symbol="AAPL",
                    )

        mock_derived.assert_called_once_with(company_id=1)

    async def test_refresh_triggers_ri_valuation(self):
        self.mock_repo.get_company_refresh_info.return_value = SimpleNamespace(
            company_id=1, ticker_symbol="AAPL",
            exchange=None,
            first_financial_data_loaded_at=datetime(2024, 1, 1),
            last_refreshed_fiscal_year=2024,
            last_refreshed_fiscal_quarter=None,
            data_completeness_status="COMPLETE",
        )
        self.mock_provider.get_all_financials_optimized.return_value = SimpleNamespace(
            income_statements=SimpleNamespace(rows=[SimpleNamespace(fiscal_year=2024, fiscal_quarter=None)]),
            balance_sheets=SimpleNamespace(),
            cash_flows=SimpleNamespace(),
            earnings=SimpleNamespace(),
            dividends=SimpleNamespace(),
            next_earnings_date=date(2025, 1, 30),
        )
        self.mock_repo.upsert_all_financials.return_value = {
            "income_statements": 5, "balance_sheets": 3, "cash_flows": 2,
            "earnings": 0, "dividends": 0,
        }

        with patch("application.schedulers.earnings_scheduler.compute_and_upsert_derived_financial_metrics"):
            with patch("application.schedulers.earnings_scheduler.audit_company_data_quality"):
                with patch("application.services.valuation_service.ValuationService") as mock_vs:
                    mock_instance = AsyncMock()
                    mock_vs.return_value = mock_instance
                    await self.scheduler._refresh_company_financials_optimized(
                        company_id=1, symbol="AAPL",
                    )

        mock_instance.compute_residual_income_if_stale.assert_called_once_with(
            symbol="AAPL", user_id=None, force=True
        )

    async def test_refresh_skips_derived_when_no_rows_written(self):
        self.mock_repo.get_company_refresh_info.return_value = SimpleNamespace(
            company_id=1, ticker_symbol="AAPL",
            exchange=None,
            first_financial_data_loaded_at=datetime(2024, 1, 1),
            last_refreshed_fiscal_year=2024,
            last_refreshed_fiscal_quarter=None,
            data_completeness_status="COMPLETE",
        )
        self.mock_provider.get_all_financials_optimized.return_value = SimpleNamespace(
            income_statements=SimpleNamespace(rows=[]),
            balance_sheets=SimpleNamespace(),
            cash_flows=SimpleNamespace(),
            earnings=SimpleNamespace(),
            dividends=SimpleNamespace(),
            next_earnings_date=None,
        )
        self.mock_repo.upsert_all_financials.return_value = {
            "income_statements": 0, "balance_sheets": 0, "cash_flows": 0,
            "earnings": 0, "dividends": 0,
        }

        with patch("application.schedulers.earnings_scheduler.compute_and_upsert_derived_financial_metrics") as mock_derived:
            await self.scheduler._refresh_company_financials_optimized(
                company_id=1, symbol="AAPL",
            )

        mock_derived.assert_not_called()

    async def test_check_refresh_merges_stale_companies(self):
        self.mock_repo.get_companies_with_upcoming_earnings.return_value = [
            {"company_id": 1, "ticker_symbol": "WIN1", "next_earnings_date": "2026-09-10"},
        ]
        self.mock_repo.get_stale_financial_companies.return_value = [
            {"company_id": 2, "ticker_symbol": "STALE1"},
        ]
        with patch.object(
            self.scheduler, "_refresh_company_financials_optimized", AsyncMock()
        ) as mock_refresh:
            result = await self.scheduler._check_and_refresh_earnings()

        assert result["companies_found"] == 2
        assert result["companies_refreshed"] == 2
        assert result["companies_failed"] == 0
        assert mock_refresh.await_count == 2
        calls = {c.kwargs["symbol"]: c.kwargs.get("earnings_date") for c in mock_refresh.await_args_list}
        assert calls["WIN1"] == "2026-09-10"
        assert calls["STALE1"] is None


class TestMarketDataSchedulerInit:
    async def test_init_stores_repos_and_providers(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        mock_yf = SimpleNamespace(
            fetch_revenue_forecast=AsyncMock(return_value=[]),
            fetch_earnings_forecast=AsyncMock(return_value=[]),
        )
        scheduler = MarketDataRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
            yfinance_provider=mock_yf,
        )
        assert scheduler.financial_repo is mock_financial_repo
        assert scheduler.defeat_beta_provider is mock_defeat_beta_provider
        assert scheduler.yfinance_provider is mock_yf
        assert scheduler.is_running is False

    async def test_start_stop_lifecycle(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        scheduler = MarketDataRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
        )
        assert not scheduler.is_running
        await scheduler.start()
        assert scheduler.is_running
        assert scheduler._task is not None
        await scheduler.stop()
        assert not scheduler.is_running


class TestMarketDataProcessCompany:
    @pytest.fixture(autouse=True)
    def _setup_scheduler(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        mock_yfinance = SimpleNamespace(
            fetch_revenue_forecast=AsyncMock(return_value=[]),
            fetch_earnings_forecast=AsyncMock(return_value=[]),
        )
        self.scheduler = MarketDataRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
            yfinance_provider=mock_yfinance,
        )
        self.mock_repo = mock_financial_repo
        self.mock_provider = mock_defeat_beta_provider
        self.mock_yfinance = mock_yfinance
        patch_obj = patch.object(self.scheduler, "_upsert_daily_price_history", return_value=0)
        self._internal_patch = patch_obj
        self._internal_patch.start()

    @pytest.fixture(autouse=True)
    def _teardown(self):
        yield
        if getattr(self, "_internal_patch", None) is not None:
            self._internal_patch.stop()

    async def test_bootstrap_uses_min_fiscal_year_2021(self):
        with patch.object(self.scheduler, "_has_any_financials", return_value=False):
            self.mock_repo.get_company_refresh_info.return_value = SimpleNamespace(
                company_id=1, ticker_symbol="AAPL",
                exchange=None,
                first_financial_data_loaded_at=None,
                last_refreshed_fiscal_year=None,
                last_refreshed_fiscal_quarter=None,
                data_completeness_status="INITIAL",
            )
            self.mock_provider.get_all_financials_optimized.return_value = SimpleNamespace(
                income_statements=SimpleNamespace(rows=[SimpleNamespace(fiscal_year=2024)]),
                balance_sheets=SimpleNamespace(),
                cash_flows=SimpleNamespace(),
            )

            with patch("application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics"):
                with patch("application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics"):
                    with patch("application.services.valuation_service.ValuationService") as mock_vs:
                        mock_vs.return_value = AsyncMock()
                        await self.scheduler._process_company("AAPL", 1)

        self.mock_provider.get_all_financials_optimized.assert_called_once()
        kwargs = self.mock_provider.get_all_financials_optimized.call_args[1]
        assert kwargs.get("min_fiscal_year") == 2021
        assert kwargs.get("force_full_history") is True

    async def test_skips_bootstrap_when_financials_exist(self):
        with patch.object(self.scheduler, "_has_any_financials", return_value=True):
            self.mock_provider.get_all_financials_optimized.reset_mock()

            with patch("application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics"):
                with patch("application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics"):
                    with patch("application.services.valuation_service.ValuationService") as mock_vs:
                        mock_vs.return_value = AsyncMock()
                        await self.scheduler._process_company("AAPL", 1)

        self.mock_provider.get_all_financials_optimized.assert_not_called()

    async def test_stock_calls_derived_metrics(self):
        with patch("application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics") as mock_derived:
            with patch("application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics"):
                with patch("application.services.valuation_service.ValuationService") as mock_vs:
                    mock_vs.return_value = AsyncMock()
                    await self.scheduler._process_company("AAPL", 1)

        mock_derived.assert_called_once()

    async def test_stock_calls_ri_valuation_with_force(self):
        with patch("application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics"):
            with patch("application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics"):
                with patch("application.services.valuation_service.ValuationService") as mock_vs:
                    mock_instance = AsyncMock()
                    mock_vs.return_value = mock_instance
                    await self.scheduler._process_company("AAPL", 1)

        mock_instance.compute_residual_income_if_stale.assert_called_once_with(
            symbol="AAPL", user_id=None, force=True
        )

    async def test_non_stock_skips_stock_only_operations(self):
        with patch("application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics") as mock_derived:
            with patch("application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics"):
                with patch("application.services.valuation_service.ValuationService") as mock_vs:
                    mock_instance = AsyncMock()
                    mock_vs.return_value = mock_instance
                    await self.scheduler._process_company("SPY", 1, security_type="etf")

        mock_derived.assert_not_called()
        mock_instance.compute_residual_income_if_stale.assert_not_called()
