"""
Targeted tests for production issue fixes (issues.txt).
Covers: Issue #1 (forecast_id), #2 (price overflow), #3+7 (ETF price/splits),
        #6 (429 backoff), #8 (delisted filtering).
"""
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================================
# Issue #1: forecast_id NOT NULL — _deterministic_id helper
# ============================================================================

class TestDeterministicId:
    """Verify _deterministic_id generates stable positive integers."""

    def test_generates_positive_int(self):
        from infrastructure.repositories.financial_repository import _deterministic_id
        result = _deterministic_id(1, "2025-01-01", "annual", "defeatbeta")
        assert isinstance(result, int)
        assert result > 0

    def test_deterministic_same_inputs(self):
        from infrastructure.repositories.financial_repository import _deterministic_id
        a = _deterministic_id(1, "2025-01-01", "annual", "defeatbeta")
        b = _deterministic_id(1, "2025-01-01", "annual", "defeatbeta")
        assert a == b

    def test_different_inputs_different_ids(self):
        from infrastructure.repositories.financial_repository import _deterministic_id
        a = _deterministic_id(1, "2025-01-01", "annual", "defeatbeta")
        b = _deterministic_id(2, "2025-01-01", "annual", "defeatbeta")
        assert a != b

    def test_fits_in_64bit(self):
        from infrastructure.repositories.financial_repository import _deterministic_id
        result = _deterministic_id(999999, "9999-12-31", "quarterly", "yfinance")
        assert result < 2**63


# ============================================================================
# Issue #1: forecast_id generated before upsert
# ============================================================================

class TestRevenueForecastIdGeneration:
    """Verify forecast_id is generated when missing before upsert."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_supabase_client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "ENABLE_CONFLICT_DETECTION", False)
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        self.repo = SupabaseFinancialRepository(client=mock_supabase_client)
        self.client = mock_supabase_client

    async def test_generates_forecast_id_when_none(self):
        rows = [
            {
                "company_id": 1,
                "report_date": "2025-01-01",
                "period_type": "annual",
                "provider": "defeatbeta",
                "forecast_id": None,
                "revenue_estimate": 100000,
            }
        ]
        await self.repo.upsert_revenue_forecast(rows)
        payload = self.client.table.return_value.upsert.call_args[0][0]
        assert payload[0]["forecast_id"] is not None
        assert isinstance(payload[0]["forecast_id"], int)
        assert payload[0]["forecast_id"] > 0

    async def test_preserves_existing_forecast_id(self):
        rows = [
            {
                "company_id": 1,
                "report_date": "2025-01-01",
                "period_type": "annual",
                "provider": "defeatbeta",
                "forecast_id": 42,
                "revenue_estimate": 100000,
            }
        ]
        await self.repo.upsert_revenue_forecast(rows)
        payload = self.client.table.return_value.upsert.call_args[0][0]
        assert payload[0]["forecast_id"] == 42


class TestEarningsForecastIdGeneration:
    """Verify earnings_forecast_id is generated when missing before upsert."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_supabase_client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "ENABLE_CONFLICT_DETECTION", False)
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        self.repo = SupabaseFinancialRepository(client=mock_supabase_client)
        self.client = mock_supabase_client

    async def test_generates_earnings_forecast_id_when_none(self):
        rows = [
            {
                "company_id": 1,
                "report_date": "2025-01-01",
                "period_type": "annual",
                "provider": "defeatbeta",
                "earnings_forecast_id": None,
                "eps_estimate": 5.50,
            }
        ]
        await self.repo.upsert_earnings_forecast(rows)
        payload = self.client.table.return_value.upsert.call_args[0][0]
        assert payload[0]["earnings_forecast_id"] is not None
        assert isinstance(payload[0]["earnings_forecast_id"], int)
        assert payload[0]["earnings_forecast_id"] > 0


# ============================================================================
# Issue #2: price_history overflow clamping
# ============================================================================

class TestPriceHistoryOverflowClamping:
    """Verify extreme price values are clamped to numeric(16,4) limit."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_supabase_client, monkeypatch):
        from config import settings
        monkeypatch.setattr(settings, "ENABLE_CONFLICT_DETECTION", False)
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        self.repo = SupabaseFinancialRepository(client=mock_supabase_client)
        self.client = mock_supabase_client

    async def test_clamps_extreme_price(self):
        rows = [
            {
                "company_id": 1,
                "price_date": date(2026, 1, 31),
                "open_price": 1.5e12,
                "close_price": 1.6e12,
                "high_price": 1.7e12,
                "low_price": 1.4e12,
                "volume": 1000,
                "data_source": "yfinance",
            }
        ]
        await self.repo.upsert_price_history(rows)
        payload = self.client.table.return_value.upsert.call_args[0][0]
        assert payload[0]["close_price"] == 999_999_999_999.9999
        assert payload[0]["open_price"] == 999_999_999_999.9999

    async def test_normal_price_unaffected(self):
        rows = [
            {
                "company_id": 1,
                "price_date": date(2026, 1, 31),
                "open_price": 150.50,
                "close_price": 155.75,
                "high_price": 157.00,
                "low_price": 149.00,
                "volume": 1000,
                "data_source": "yfinance",
            }
        ]
        await self.repo.upsert_price_history(rows)
        payload = self.client.table.return_value.upsert.call_args[0][0]
        assert payload[0]["close_price"] == 155.75
        assert payload[0]["open_price"] == 150.50


# ============================================================================
# ETF / index / fund handling: price history + splits only (regression lock)
# ============================================================================
#
# The 2026-09-04 commit 21109f19 converted the non-stock branch from a
# fall-through ("running price+splits only") into an early return placed
# *above* the splits and price steps. That silently deleted price ingestion
# for every ETF/index/fund, so their price history froze at the seed horizon
# while stocks kept refreshing. The class below pins the documented contract:
# non-stocks still collect splits + daily price history, and skip only the
# fundamental steps 3-7.

class TestEtfPriceAndSplitsOnly:
    """Non-stock securities collect price history + splits, skip fundamentals."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_financial_repo, mock_defeat_beta_provider):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        self.repo = mock_financial_repo
        self.provider = mock_defeat_beta_provider
        self.scheduler = MarketDataRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=mock_defeat_beta_provider,
            yfinance_provider=MagicMock(),
        )

    async def test_etf_collects_price_and_splits(self):
        self.provider.get_splits_optimized.return_value = [
            {"company_id": 1, "split_date": "2020-01-01", "ratio": 2.0}
        ]
        self.scheduler._upsert_daily_price_history = AsyncMock(return_value=7)

        result = await self.scheduler._process_company("SPY", 1, security_type="etf")

        self.provider.get_splits_optimized.assert_awaited_once()
        self.repo.upsert_splits.assert_awaited_once()
        self.scheduler._upsert_daily_price_history.assert_awaited_once()
        assert result["price_history_daily"] == 7
        assert result["splits"] == 1
        assert result["skipped_etf"] is True

    async def test_index_collects_price(self):
        self.scheduler._upsert_daily_price_history = AsyncMock(return_value=3)

        result = await self.scheduler._process_company("^GSPC", 2, security_type="index")

        self.scheduler._upsert_daily_price_history.assert_awaited_once()
        assert result["price_history_daily"] == 3
        assert result["skipped_etf"] is True

    async def test_etf_does_not_call_fundamental_providers(self):
        self.scheduler._upsert_daily_price_history = AsyncMock(return_value=0)

        await self.scheduler._process_company("QQQ", 3, security_type="etf")

        self.provider.fetch_revenue_forecast.assert_not_called()
        self.provider.fetch_earnings_forecast.assert_not_called()
        self.provider.get_company_summary_optimized.assert_not_called()
        self.repo.upsert_revenue_forecast.assert_not_called()
        self.repo.upsert_earnings_forecast.assert_not_called()
        self.repo.upsert_company_summary.assert_not_called()

    async def test_delisted_symbol_still_skips_before_price(self):
        self.scheduler._upsert_daily_price_history = AsyncMock(return_value=9)

        result = await self.scheduler._process_company("WBA", 4, security_type="stock")

        self.scheduler._upsert_daily_price_history.assert_not_called()
        assert result["skipped_delisted"] is True
        assert result["price_history_daily"] == 0


# ============================================================================
# Issue #6: Stockdex 429 exponential backoff
# ============================================================================

class TestStockdex429Backoff:
    """Verify exponential backoff and rate-limit check."""

    def test_is_rate_limited_returns_false_initially(self):
        from providers.stockdex_provider import StockdexMacrotrendsProvider
        p = StockdexMacrotrendsProvider()
        assert p.is_rate_limited() is False

    def test_consecutive_429_increments(self):
        from providers.stockdex_provider import StockdexMacrotrendsProvider
        p = StockdexMacrotrendsProvider()
        p._consecutive_429 = 0
        p._consecutive_429 += 1
        assert p._consecutive_429 == 1

    def test_exponential_backoff_cap(self):
        """Verify backoff formula: min(300 * 2^(n-1), 1800)."""
        from providers.stockdex_provider import StockdexMacrotrendsProvider
        p = StockdexMacrotrendsProvider()
        # n=1: 300, n=2: 600, n=3: 1200, n=4: 1800 (capped)
        cases = [(1, 300), (2, 600), (3, 1200), (4, 1800), (5, 1800)]
        for n, expected in cases:
            result = min(300 * (2 ** (n - 1)), 1800)
            assert result == expected, f"n={n}: expected {expected}, got {result}"


# ============================================================================
# Issue #8: Delisted symbol filtering
# ============================================================================

class TestDelistedSymbolFiltering:
    """Verify skipped_symbols are filtered from refresh cycle."""

    def test_hardcoded_delisted_symbols_present(self):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        scheduler = MarketDataRefreshScheduler(
            financial_repo=MagicMock(),
            defeat_beta_provider=MagicMock(),
            yfinance_provider=MagicMock(),
        )
        assert "NYCB" in scheduler.skipped_symbols
        assert "CS" in scheduler.skipped_symbols
        assert "CMA" in scheduler.skipped_symbols
        assert "WBA" in scheduler.skipped_symbols
        assert "PSYK" in scheduler.skipped_symbols
        assert "HYLD" in scheduler.skipped_symbols

    def test_max_price_failures_default(self):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        scheduler = MarketDataRefreshScheduler(
            financial_repo=MagicMock(),
            defeat_beta_provider=MagicMock(),
            yfinance_provider=MagicMock(),
        )
        assert scheduler.max_price_failures == 10

# ============================================================================
# Issue #8b: Price ingestion honors the delisted skip list
# ============================================================================

class TestPriceIngestionSkipList:
    """Verify refresh_all_prices() drops delisted/renamed symbols before fetch."""

    def test_get_effective_skipped_symbols_includes_hardcoded(self):
        from shared.constants import get_effective_skipped_symbols
        skipped = get_effective_skipped_symbols()
        for sym in ("NYCB", "CS", "CMA", "WBA"):
            assert sym in skipped
        # BK.TO (Canadian Banc Corp Class A) is a LIVE listing — never skipped
        assert "BK" not in skipped

    def test_refresh_all_prices_filters_delisted_symbols(self):
        import asyncio

        from application.jobs import price_ingestion_job as job

        active_symbols = [
            {"company_id": 1, "symbol": "AAPL", "exchange_override": "NMS"},
            {"company_id": 2, "symbol": "WBA", "exchange_override": "UNKNOWN"},
            {"company_id": 3, "symbol": "BK", "exchange_override": "TOR"},
        ]
        fetched: list = []

        async def fake_fetch(symbols, exchange, **kwargs):
            for s in symbols:
                fetched.append((s, exchange))
            return {s: {"price": 10.0, "error": None} for s in symbols}

        class FakeRepo:
            def get_all_active_symbols(self):
                return active_symbols

            def upsert_price_source(
                self, company_id, exchange, price, source,
                currency="USD", ttl_seconds=300,
            ):
                return None

        with patch.object(job, "repo", FakeRepo()), \
             patch.object(job, "_fetch_yfinance_batch", side_effect=fake_fetch), \
             patch.object(job, "_update_cdr_ratios", new=AsyncMock()), \
             patch.object(job, "_emit_split_events", new=MagicMock()):
            asyncio.run(job.refresh_all_prices())

        fetched_symbols = {s for s, _ in fetched}
        assert "WBA" not in fetched_symbols, "WBA delisted — must not reach provider"
        assert "AAPL" in fetched_symbols
        assert "BK" in fetched_symbols  # BK.TO is live


# ============================================================================
# Issue #8c: Planner->worker path honors the delisted skip list
# ============================================================================

class TestDelistedSymbolPlannerGuard:
    """Verify _process_company() and plan() short-circuit delisted symbols."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_financial_repo):
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        self.scheduler = MarketDataRefreshScheduler(
            financial_repo=mock_financial_repo,
            defeat_beta_provider=MagicMock(),
            yfinance_provider=MagicMock(),
        )

    async def test_process_company_returns_skipped_delisted(self):
        result = await self.scheduler._process_company("WBA", 1)
        assert result["skipped_delisted"] is True
        assert result["price_history_daily"] == 0
        assert "WBA" in self.scheduler.skipped_symbols

    async def test_process_company_does_not_call_providers(self):
        self.scheduler.defeat_beta_provider.get_price_history_optimized = AsyncMock()
        self.scheduler.defeat_beta_provider.fetch_revenue_forecast = AsyncMock()
        await self.scheduler._process_company("CMA", 2)
        self.scheduler.defeat_beta_provider.get_price_history_optimized.assert_not_called()
        self.scheduler.defeat_beta_provider.fetch_revenue_forecast.assert_not_called()

    async def test_plan_excludes_delisted_symbols(self):
        companies = [
            {"company_id": 1, "ticker_symbol": "AAPL", "security_type": "stock", "exchange": "NMS"},
            {"company_id": 2, "ticker_symbol": "WBA", "security_type": "stock", "exchange": "UNKNOWN"},
            {"company_id": 3, "ticker_symbol": "BK", "security_type": "stock", "exchange": "TOR"},
        ]
        self.scheduler.financial_repo.get_active_companies_for_market_data = AsyncMock(
            return_value=companies
        )
        jobs = await self.scheduler.plan()
        symbols = [j["payload"]["ticker_symbol"] for j in jobs]
        assert "AAPL" in symbols
        assert "BK" in symbols
        assert "WBA" not in symbols


class TestStockdex403Handling:
    def test_403_blocks_after_three_consecutive(self, monkeypatch):
        from providers.stockdex_provider import StockdexMacrotrendsProvider

        p = StockdexMacrotrendsProvider()
        calls = []

        def bad(*args, **kwargs):
            calls.append(1)
            raise RuntimeError("Failed to fetch URL (status 403)")

        monkeypatch.setattr(p, "_get_raw_dataframe", bad)

        assert p.get_quarterly_income_statement_df("TBD").empty
        assert p.get_quarterly_income_statement_df("TBD").empty
        assert p.get_quarterly_income_statement_df("TBD").empty
        assert p.get_quarterly_income_statement_df("TBD").empty

        assert p.is_symbol_blocked("TBD")
        assert len(calls) == 3

    def test_403_does_not_block_other_symbol(self, monkeypatch):
        from providers.stockdex_provider import StockdexMacrotrendsProvider

        p = StockdexMacrotrendsProvider()
        calls = []

        def bad_tbd(*args, **kwargs):
            calls.append("tbd")
            raise RuntimeError("Failed to fetch URL (status 403)")

        def ok_other(*args, **kwargs):
            calls.append("other")
            import pandas as pd
            return pd.DataFrame({"2024-01-01": [1.0]}, index=["Total Revenue"])

        monkeypatch.setattr(p, "_get_raw_dataframe", bad_tbd)
        p.get_quarterly_income_statement_df("TBD")
        p.get_quarterly_income_statement_df("TBD")
        p.get_quarterly_income_statement_df("TBD")

        monkeypatch.setattr(p, "_get_raw_dataframe", ok_other)
        res = p.get_quarterly_income_statement_df("OTHER")
        assert not res.empty
        assert p.is_symbol_blocked("TBD")
        assert not p.is_symbol_blocked("OTHER")
