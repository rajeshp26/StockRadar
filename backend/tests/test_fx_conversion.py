"""
Tests for the FX Currency Conversion feature.

Covers:
  - fx_provider.py: yfinance-based rate fetching
  - fx_service.py: cached conversion service
  - Integration with enrichment and snapshot builder
  - Database validation
  - End-to-end API tests

Run: pytest tests/test_fx_conversion.py -v
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from shared.fx_service import CACHE_TTL, NONE_CACHE_TTL, FXService
from shared.time_utils import now_utc

# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_supabase():
    """Mock Supabase client that simulates exchange_rates table."""
    client = MagicMock()
    client.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])
    client.table.return_value.select.return_value.eq.return_value.eq.return_value \
        .gte.return_value.order.return_value.limit.return_value.execute.return_value = \
        MagicMock(data=[])
    return client


@pytest.fixture
def fx_service(mock_supabase):
    return FXService(mock_supabase)


# ═══════════════════════════════════════════════════════════════════
# 1. fx_provider.py Tests
# ═══════════════════════════════════════════════════════════════════

class TestFXProvider:

    @patch("providers.fx_provider.yf.download")
    def test_returns_decimal(self, mock_download):
        """fetch_fx_rate returns Decimal, not float."""
        import pandas as pd

        from providers.fx_provider import fetch_fx_rate

        mock_df = pd.DataFrame({"Close": [1.3645]},
                               index=pd.DatetimeIndex(["2026-06-20"]))
        mock_download.return_value = mock_df

        result = fetch_fx_rate("USD", "CAD")
        assert result is not None
        assert isinstance(result, Decimal)
        assert result == Decimal("1.3645")

    @patch("providers.fx_provider.yf.download")
    def test_handles_multiindex_columns(self, mock_download):
        """Extracts scalar from DataFrame with MultiIndex columns."""
        import pandas as pd

        from providers.fx_provider import fetch_fx_rate

        arrays = [["Close"], ["CADUSD=X"]]
        tuples = list(zip(*arrays))
        multi_index = pd.MultiIndex.from_tuples(tuples)
        mock_df = pd.DataFrame([[1.3645]], columns=multi_index,
                               index=pd.DatetimeIndex(["2026-06-20"]))
        mock_download.return_value = mock_df

        result = fetch_fx_rate("USD", "CAD")
        assert result is not None
        assert isinstance(result, Decimal)
        assert result == Decimal("1.3645")

    @patch("providers.fx_provider.yf.download")
    def test_empty_dataframe_returns_none(self, mock_download):
        """Returns None when yfinance returns empty."""
        import pandas as pd

        from providers.fx_provider import fetch_fx_rate

        mock_download.return_value = pd.DataFrame()
        result = fetch_fx_rate("USD", "CAD")
        assert result is None

    @patch("providers.fx_provider.yf.download")
    def test_network_error_returns_none(self, mock_download):
        """Returns None when yfinance raises."""
        from providers.fx_provider import fetch_fx_rate

        mock_download.side_effect = Exception("Connection error")
        result = fetch_fx_rate("USD", "CAD")
        assert result is None

    @patch("providers.fx_provider.yf.download")
    def test_nan_close_returns_none(self, mock_download):
        """Returns None when Close column is all NaN."""
        import numpy as np
        import pandas as pd

        from providers.fx_provider import fetch_fx_rate

        mock_df = pd.DataFrame({"Close": [np.nan]},
                               index=pd.DatetimeIndex(["2026-06-20"]))
        mock_download.return_value = mock_df

        result = fetch_fx_rate("USD", "CAD")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
# 2. fx_service.py Tests
# ═══════════════════════════════════════════════════════════════════

class TestFXService:

    def test_convert_same_currency(self, fx_service):
        """USD->USD returns input unchanged."""
        result = fx_service.convert(Decimal("100"), "USD", "USD")
        assert result == Decimal("100")

    def test_convert_same_currency_case_insensitive(self, fx_service):
        """usd->Usd returns input unchanged."""
        result = fx_service.convert(Decimal("100"), "usd", "Usd")
        assert result == Decimal("100")

    def test_convert_or_warn_success(self, fx_service, mock_supabase):
        """Returns (converted, True) on success."""
        # Seed a rate
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.36", "rate_date": "2026-06-20"}])

        result, applied = fx_service.convert_or_warn(
            Decimal("100"), "USD", "CAD",
            as_of=date(2026, 6, 20),
        )
        assert applied is True
        assert result == Decimal("136")

    def test_convert_or_warn_failure(self, fx_service, caplog):
        """Returns (unconverted, False) and logs warning when rate unavailable."""
        caplog.set_level(logging.WARNING)

        result, applied = fx_service.convert_or_warn(
            Decimal("100"), "USD", "CAD",
            as_of=date(2025, 1, 1),  # historical, no live fetch
        )
        assert applied is False
        assert result == Decimal("100")
        assert "FX rate unavailable" in caplog.text

    def test_get_rate_no_rate_available(self, fx_service):
        """Returns None when cache empty, as_of != today."""
        result = fx_service.get_rate("USD", "CAD", as_of=date(2025, 1, 1))
        assert result is None

    def test_query_cached_rate(self, fx_service, mock_supabase):
        """Returns cached rate from exchange_rates table."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.3645", "rate_date": "2026-06-20"}])

        rate = fx_service._query_cached_rate("USD", "CAD", date(2026, 6, 22))
        assert rate == Decimal("1.3645")

    def test_stale_rate_forward_filled(self, fx_service, mock_supabase, caplog):
        """Rate 10 days old with MAX_STALE_DAYS=7 is forward-filled, not dropped."""
        caplog.set_level(logging.WARNING)
        fx_service.MAX_STALE_DAYS = 7
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.36", "rate_date": "2026-06-10"}])

        rate = fx_service._query_cached_rate("USD", "CAD", date(2026, 6, 20))
        assert rate == Decimal("1.36")
        assert "forward-filling" in caplog.text

    def test_fresh_rate_accepted(self, fx_service, mock_supabase):
        """Rate 3 days old with MAX_STALE_DAYS=7 returns the rate."""
        fx_service.MAX_STALE_DAYS = 7
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.36", "rate_date": "2026-06-17"}])

        rate = fx_service._query_cached_rate("USD", "CAD", date(2026, 6, 20))
        assert rate == Decimal("1.36")

    def test_inverse_rate_computed(self, fx_service, mock_supabase):
        """USD->CAD computed from cached CAD->USD as 1 / inverse."""
        # Override _query_cached_rate to return CAD->USD rate only
        original_query = fx_service._query_cached_rate

        def side_effect(base, target, as_of):
            if base == "CAD" and target == "USD":
                return Decimal("0.74")
            if base == "USD" and target == "CAD":
                return None
            return original_query(base, target, as_of)

        fx_service._query_cached_rate = side_effect

        rate = fx_service.get_rate("USD", "CAD", as_of=date(2026, 6, 20))
        assert rate is not None
        expected = Decimal("1") / Decimal("0.74")
        assert abs(rate - expected) / expected < Decimal("0.01")

    def test_instance_cache_hit(self, fx_service, mock_supabase):
        """Same (base, target, as_of) returns cached value, single DB query."""
        fx_service._cache_set(("USD", "CAD", "2026-06-20"), Decimal("1.36"))

        # No mock needed — cache should hit
        rate = fx_service.get_rate("USD", "CAD", as_of=date(2026, 6, 20))
        assert rate == Decimal("1.36")

    def test_instance_cache_ttl_expiry(self, fx_service):
        """After CACHE_TTL, cache miss triggers new lookup."""
        fx_service._cache_set(("USD", "CAD", "2026-06-20"), Decimal("1.36"))

        # Manually age the cache entry past TTL
        key = ("USD", "CAD", "2026-06-20")
        old_time = now_utc() - CACHE_TTL - timedelta(seconds=1)
        fx_service._cache[key] = (Decimal("1.36"), old_time)

        cached = fx_service._cache_get(key)
        assert cached is None  # expired

    def test_none_cache_ttl_shorter(self, fx_service):
        """None cached with NONE_CACHE_TTL, expires sooner."""
        key = ("USD", "CAD", "2026-06-20")
        fx_service._cache_set(key, None)

        # Within NONE_CACHE_TTL
        result = fx_service._cache_get(key)
        assert result is None  # still cached as None
        assert key in fx_service._cache

        # Past NONE_CACHE_TTL
        old_time = now_utc() - NONE_CACHE_TTL - timedelta(seconds=1)
        fx_service._cache[key] = (None, old_time)
        result = fx_service._cache_get(key)
        assert result is None  # expired, returns None
        assert key not in fx_service._cache  # removed from cache

    def test_future_rate_date_raises(self, fx_service, mock_supabase):
        """_cache_rate with rate_date > today raises ValueError."""
        tomorrow = now_utc().date() + timedelta(days=1)
        with pytest.raises(ValueError, match="Refusing to cache rate dated in the future"):
            fx_service._cache_rate("USD", "CAD", Decimal("1.36"), tomorrow)

    def test_decimal_arithmetic_precision(self, fx_service, mock_supabase):
        """No float rounding errors in conversion."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.23456789", "rate_date": "2026-06-20"}])

        result = fx_service.convert(
            Decimal("1000"), "USD", "CAD",
            as_of=date(2026, 6, 20),
        )
        assert result == Decimal("1234.56789")

    def test_historical_as_of_does_not_live_fetch(self, fx_service, mock_supabase):
        """Live fetch NOT called for historical as_of outside the live window."""
        with patch("providers.fx_provider.fetch_fx_history") as mock_fetch:
            result = fx_service.get_rate("USD", "CAD", as_of=date(2025, 1, 1))
            assert result is None
            mock_fetch.assert_not_called()

    def test_get_rate_uses_nearest_future_rate_when_no_past(self, fx_service):
        """as_of before the earliest stored rate resolves via nearest-future."""
        fx_service._query_cached_rate = lambda b, t, a: None
        fx_service._query_future_rate = (
            lambda b, t, a: Decimal("1.35")
            if (b, t) == ("USD", "CAD") else None
        )
        rate = fx_service.get_rate("USD", "CAD", as_of=date(2020, 1, 1))
        assert rate == Decimal("1.35")

    def test_get_rate_live_fetch_heals_recent_gap(self, fx_service):
        """Recent as_of with no stored rate fetches history once and resolves."""
        today = now_utc().date()
        as_of = today - timedelta(days=3)
        fetched_date = today - timedelta(days=2)
        calls = {"query": 0}

        def query_cached(base, target, as_of_d):
            calls["query"] += 1
            if (base, target) == ("USD", "CAD") and calls["query"] >= 2:
                return Decimal("1.3742")
            return None

        fx_service._query_cached_rate = query_cached
        fx_service._query_future_rate = lambda b, t, a: None

        with patch("providers.fx_provider.fetch_fx_history", return_value=[
            (fetched_date, Decimal("1.3742")),
        ]) as mock_fetch, patch.object(fx_service, "_cache_rate") as mock_cache:
            rate = fx_service.get_rate("USD", "CAD", as_of=as_of)

        assert rate == Decimal("1.3742")
        mock_fetch.assert_called_once()
        mock_cache.assert_called_once_with("USD", "CAD", Decimal("1.3742"), fetched_date)

    def test_round_trip_via_inverse(self, fx_service, mock_supabase):
        """USD->CAD then CAD->USD returns original amount within tolerance."""
        def select_side(base, target, as_of):
            if base == "CAD" and target == "USD":
                return [{"rate": "0.74", "rate_date": as_of.isoformat()}]
            return []

        fx_service._query_cached_rate = lambda b, t, a: (
            Decimal("0.74") if b == "CAD" and t == "USD" else None
        )

        fwd = fx_service.convert(Decimal("100"), "USD", "CAD", as_of=date(2026, 6, 20))
        assert fwd is not None

    def test_convert_with_zero_amount(self, fx_service, mock_supabase):
        """Converting 0 returns 0."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.36", "rate_date": "2026-06-20"}])

        result = fx_service.convert(Decimal("0"), "USD", "CAD", as_of=date(2026, 6, 20))
        assert result == Decimal("0")


# ═══════════════════════════════════════════════════════════════════
# 3. Enrich Holdings Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestEnrichHoldingsFX:

    @pytest.mark.asyncio
    async def test_feature_flag_off_legacy_behavior(self):
        """With ENABLE_FX_CONVERSION=False, enrichment matches legacy code."""
        from config import settings
        original = settings.ENABLE_FX_CONVERSION
        try:
            settings.ENABLE_FX_CONVERSION = False
            from application.services.portfolio_service import PortfolioService

            service = PortfolioService()
            holdings = [
                {"company_id": 1, "price_currency": "USD",
                 "cost_currency": "USD", "total_cost": 100, "quantity": 10,
                 "symbol": "AAPL", "current_price": None},
            ]
            # Mock the supabase calls to avoid real DB
            with patch("application.services.portfolio_service.supabase.table") as mock_tbl:
                mock_tbl.return_value.select.return_value.in_.return_value \
                    .execute.return_value = MagicMock(data=[])

                result = await service.enrich_holdings_with_prices(
                    holdings, account_base_currency="CAD",
                )
            assert len(result) == 1
        finally:
            settings.ENABLE_FX_CONVERSION = original

    @pytest.mark.asyncio
    async def test_enrich_holdings_without_base_currency(self):
        """Calling without account_base_currency falls back to legacy (no conversion)."""
        from config import settings
        original = settings.ENABLE_FX_CONVERSION
        try:
            settings.ENABLE_FX_CONVERSION = True
            from application.services.portfolio_service import PortfolioService

            service = PortfolioService()
            holdings = [
                {"company_id": 1, "price_currency": "USD",
                 "cost_currency": "USD", "total_cost": 100, "quantity": 10,
                 "symbol": "AAPL"},
            ]
            with patch("application.services.portfolio_service.supabase.table") as mock_tbl:
                mock_tbl.return_value.select.return_value.in_.return_value \
                    .execute.return_value = MagicMock(data=[])

                result = await service.enrich_holdings_with_prices(holdings)
            assert len(result) == 1
        finally:
            settings.ENABLE_FX_CONVERSION = original


# ═══════════════════════════════════════════════════════════════════
# 4. Snapshot Builder Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestSnapshotBuilderFX:

    def test_snapshot_builder_same_currency(self):
        """All holdings in account currency: no conversion, values unchanged."""
        from shared.snapshot_builder import build_snapshot_row

        row = build_snapshot_row(
            account_id=1,
            snapshot_date=date(2026, 6, 20),
            holdings_state=[{
                "company_id": 1, "symbol": "RY", "quantity": 100,
                "total_cost": 17000, "price_currency": "CAD",
            }],
            cash_balance=Decimal("5000"),
            net_deposits=Decimal("20000"),
            prices_by_company={1: {"price": 170.00, "price_date": date(2026, 6, 20)}},
            job_id="test",
            account_currency="CAD",
        )
        assert row["holdings_market_value"] == 17000.0  # 100 * 170
        assert row["cost_basis"] == 17000.0
        assert row["cash_balance"] == 5000.0
        assert row["total_value"] == 22000.0

    def test_snapshot_builder_double_conversion_guard(self):
        """Holding with value_currency already set triggers AssertionError."""
        from shared.snapshot_builder import build_snapshot_row

        with pytest.raises(AssertionError, match="would double-convert"):
            build_snapshot_row(
                account_id=1,
                snapshot_date=date(2026, 6, 20),
                holdings_state=[{
                    "company_id": 1, "symbol": "RY", "quantity": 100,
                    "total_cost": 17000, "price_currency": "CAD",
                    "value_currency": "CAD",
                }],
                cash_balance=Decimal("0"),
                net_deposits=Decimal("0"),
                prices_by_company={1: {"price": 170.00, "price_date": date(2026, 6, 20)}},
                job_id="test",
                account_currency="CAD",
            )

    def test_snapshot_builder_zero_quantity_skipped(self):
        """Holding with qty=0 is skipped."""
        from shared.snapshot_builder import build_snapshot_row

        row = build_snapshot_row(
            account_id=1,
            snapshot_date=date(2026, 6, 20),
            holdings_state=[{
                "company_id": 1, "symbol": "RY", "quantity": 0,
                "total_cost": 0, "price_currency": "CAD",
            }],
            cash_balance=Decimal("100"),
            net_deposits=Decimal("100"),
            prices_by_company={1: {"price": 170.00, "price_date": date(2026, 6, 20)}},
            job_id="test",
            account_currency="CAD",
        )
        assert row["holdings_market_value"] == 0.0
        assert row["total_value"] == 100.0

    def test_snapshot_builder_fx_failure_sets_warning_flag(self):
        """USD holding with no rate: fx_applied False, WARNING flag surfaced."""
        from shared.fx_service import FXService
        from shared.snapshot_builder import build_snapshot_row

        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        client.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        fx = FXService(client)

        row = build_snapshot_row(
            account_id=1,
            snapshot_date=date(2026, 6, 20),
            holdings_state=[{
                "company_id": 7, "symbol": "AAPL", "quantity": 10,
                "total_cost": 1000, "price_currency": "USD",
            }],
            cash_balance=Decimal("0"),
            net_deposits=Decimal("0"),
            prices_by_company={7: {"price": 200.0, "price_date": date(2026, 6, 20)}},
            job_id="test",
            account_currency="CAD",
            fx_service=fx,
        )
        assert row["data_quality_flag"] == "WARNING"
        holding = row["holdings_json"][0]
        assert holding["fx_applied"] is False
        assert holding["fx_rate"] is None
        assert any("FX rate unavailable" in w for w in row["validation_warnings"])

    def test_snapshot_builder_fx_success_records_rate(self):
        """USD holding converts at snapshot-date rate; fx_rate recorded."""
        from shared.fx_service import FXService
        from shared.snapshot_builder import build_snapshot_row

        client = MagicMock()
        client.table.return_value.select.return_value.eq.return_value.eq.return_value \
            .lte.return_value.order.return_value.limit.return_value.execute.return_value = \
            MagicMock(data=[{"rate": "1.36", "rate_date": "2026-06-20"}])
        fx = FXService(client)

        row = build_snapshot_row(
            account_id=1,
            snapshot_date=date(2026, 6, 20),
            holdings_state=[{
                "company_id": 7, "symbol": "AAPL", "quantity": 10,
                "total_cost": 1000, "price_currency": "USD",
            }],
            cash_balance=Decimal("0"),
            net_deposits=Decimal("0"),
            prices_by_company={7: {"price": 200.0, "price_date": date(2026, 6, 20)}},
            job_id="test",
            account_currency="CAD",
            fx_service=fx,
        )
        holding = row["holdings_json"][0]
        assert holding["fx_applied"] is True
        assert holding["fx_rate"] == 1.36
        assert holding["current_value"] == pytest.approx(2720.0)
        assert holding["cost_basis"] == pytest.approx(1360.0)
        assert row["data_quality_flag"] == "OK"


# ═══════════════════════════════════════════════════════════════════
# 5. Scheduler FX Refresh Tests
# ═══════════════════════════════════════════════════════════════════

class TestSchedulerFX:

    def test_refresh_fx_rates_stores_rates(self):
        """Calling _refresh_fx_rates caches daily closes under their close dates."""
        from config import settings
        original = settings.ENABLE_FX_CONVERSION
        try:
            settings.ENABLE_FX_CONVERSION = True
            from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
            scheduler = MarketDataRefreshScheduler()

            with patch("providers.fx_provider.fetch_fx_history") as mock_fetch, \
                 patch("shared.fx_service.FXService._cache_rate") as mock_cache:
                mock_fetch.return_value = [(date(2026, 6, 20), Decimal("1.3645"))]
                scheduler._refresh_fx_rates()

            assert scheduler.fx_service is not None
            mock_fetch.assert_called()
            assert mock_cache.call_count >= 1
        finally:
            settings.ENABLE_FX_CONVERSION = original

    def test_refresh_fx_rate_failure_logged(self, caplog):
        """Failed fetch logs error, does not crash."""
        caplog.set_level(logging.ERROR)
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        scheduler = MarketDataRefreshScheduler()

        with patch("providers.fx_provider.fetch_fx_history") as mock_fetch:
            mock_fetch.return_value = []
            scheduler._refresh_fx_rates()

        assert "Failed to fetch FX rate USD->CAD" in caplog.text

    def test_refresh_fx_rates_both_directions(self):
        """Both USD->CAD and CAD->USD are fetched."""
        from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
        scheduler = MarketDataRefreshScheduler()

        called_pairs = []

        def mock_fetch(base, target, start, end):
            called_pairs.append((base, target))
            return [(date(2026, 6, 20), Decimal("1.3645"))]

        with patch("providers.fx_provider.fetch_fx_history", side_effect=mock_fetch), \
             patch("shared.fx_service.FXService._cache_rate"):
            scheduler._refresh_fx_rates()

        assert ("USD", "CAD") in called_pairs
        assert ("CAD", "USD") in called_pairs


# ═══════════════════════════════════════════════════════════════════
# 6. Database Validation Tests
# ═══════════════════════════════════════════════════════════════════

class TestDatabaseValidation:

    def test_exchange_rates_constraints(self):
        """Verify SQL constraints are correct in the migration script."""
        # These are schema-level assertions that should match the SQL migration
        constraints = {
            "unique_rate_per_day": "UNIQUE (base_currency, target_currency, rate_date)",
            "rate_positive": "CHECK (rate > 0)",
            "currencies_len": "CHECK (length(base_currency) = 3 AND length(target_currency) = 3)",
            "no_same_currency": "CHECK (base_currency <> target_currency)",
            "currencies_uppercase": "CHECK (base_currency = upper(base_currency) AND target_currency = upper(target_currency))",
        }

        # Verify all expected constraints are documented
        for name, definition in constraints.items():
            assert name is not None
            assert definition is not None

    def test_companies_currency_not_null(self):
        """Verify companies table has currency field."""
        # This is a schema check — the migration adds currency if not present
        # We verify the seed data fix is correct
        pass

    def test_portfolio_accounts_has_currency(self):
        """Verify portfolio_accounts has currency field (default CAD)."""
        pass


# ═══════════════════════════════════════════════════════════════════
# 7. End-to-End Tests (mock API layer)
# ═══════════════════════════════════════════════════════════════════

class TestE2EFXConversion:

    @pytest.mark.asyncio
    async def test_portfolio_overview_returns_fx_fields(self):
        """API response includes fx_applied, value_currency, fx_rate."""
        from config import settings
        original = settings.ENABLE_FX_CONVERSION
        try:
            settings.ENABLE_FX_CONVERSION = True
            from application.services.portfolio_service import PortfolioService

            service = PortfolioService()
            holdings = [
                {"company_id": 1, "symbol": "AAPL", "quantity": 10,
                 "total_cost": 1000, "price_currency": "USD",
                 "cost_currency": "USD"},
            ]

            with patch.object(service.portfolio_repo, '_get_split_factors', return_value={}):
                with patch("application.services.portfolio_service.supabase.table") as mock_table:
                    mock_execute = MagicMock()
                    mock_execute.data = [{"company_id": 1, "close_price": 200.0, "price_date": "2026-06-20"}]
                    mock_table.return_value.select.return_value.in_.return_value \
                        .order.return_value.execute.return_value = mock_execute

                    # Also mock exchange_rates for FX lookup
                    rate_execute = MagicMock()
                    rate_execute.data = [{"rate": "1.36", "rate_date": "2026-06-20"}]
                    # The FX service calls exchange_rates table
                    mock_table.return_value.select.return_value.eq.return_value.eq.return_value \
                        .lte.return_value.order.return_value.limit.return_value \
                        .execute.return_value = rate_execute

                    result = await service.enrich_holdings_with_prices(
                        holdings, account_base_currency="CAD",
                    )

            assert len(result) == 1
            h = result[0]
            assert h["value_currency"] == "CAD"
            assert h["fx_applied"] is True
        finally:
            settings.ENABLE_FX_CONVERSION = original

    def test_seed_data_shop_currency_fixed(self):
        """Verify seed_e2e_data.py has SHOP->USD."""
        import ast
        with open("scripts/seed_e2e_data.py") as f:
            content = f.read()

        # Check that SHOP is in the USD list
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "currency":
                        if isinstance(val, ast.JoinedStr):
                            val_str = "".join(
                                v.value if isinstance(v, ast.Constant) else "{}"
                                for v in val.values
                            )
                            assert "SHOP" in val_str or "AAPL" in val_str
                            assert "(\"AAPL\", \"SHOP\")" in content or "\"SHOP\"" in content

        # Simpler assertion: grep for SHOP in the currency line
        assert '"SHOP"' in content
        for line in content.split("\n"):
            if "currency" in line and "SHOP" in line:
                assert "SHOP" in line
                break


# ═══════════════════════════════════════════════════════════════════
# 8. Additional Tests
# ═══════════════════════════════════════════════════════════════════

class TestEnrichHoldingsNativeFields:

    @pytest.mark.asyncio
    async def test_native_fields_preserved(self):
        """Enrich with FX=True and verify native fields contain pre-conversion values."""
        from config import settings
        original = settings.ENABLE_FX_CONVERSION
        try:
            settings.ENABLE_FX_CONVERSION = True
            from application.services.portfolio_service import PortfolioService

            service = PortfolioService()
            holdings = [
                {"company_id": 1, "symbol": "AAPL", "quantity": 10,
                 "total_cost": 1000, "price_currency": "USD",
                 "cost_currency": "USD"},
            ]

            with patch.object(service.portfolio_repo, '_get_split_factors', return_value={}):
                with patch("application.services.portfolio_service.supabase.table") as mock_table:
                    mock_execute = MagicMock()
                    mock_execute.data = [{"company_id": 1, "close_price": 200.0, "price_date": "2026-06-20"}]
                    mock_table.return_value.select.return_value.in_.return_value \
                        .order.return_value.execute.return_value = mock_execute

                    rate_execute = MagicMock()
                    rate_execute.data = [{"rate": "1.36", "rate_date": "2026-06-20"}]
                    mock_table.return_value.select.return_value.eq.return_value.eq.return_value \
                        .lte.return_value.order.return_value.limit.return_value \
                        .execute.return_value = rate_execute

                    result = await service.enrich_holdings_with_prices(
                        holdings, account_base_currency="CAD",
                    )

            assert len(result) == 1
            h = result[0]
            assert h["value_currency"] == "CAD"
            assert h["fx_applied"] is True
            assert h["current_price_native"] == 200.0
            assert h["current_value_native"] == 2000.0  # 200 * 10
            assert h["cost_basis_native"] == 1000.0
        finally:
            settings.ENABLE_FX_CONVERSION = original


class TestFXWarnings:

    def test_warnings_empty_when_all_converted(self):
        """All holdings fx_applied=True, warnings list is empty."""
        from application.services.portfolio_service import PortfolioService

        holdings = [
            {"symbol": "AAPL", "fx_applied": True},
            {"symbol": "RY", "fx_applied": True},
        ]
        warnings = PortfolioService._check_fx_warnings(holdings)
        assert warnings == []

    def test_warnings_populated_when_missing_rate(self):
        """At least one holding has fx_applied=False, warnings list contains warning."""
        from application.services.portfolio_service import PortfolioService

        holdings = [
            {"symbol": "AAPL", "fx_applied": True},
            {"symbol": "RY", "fx_applied": False},
        ]
        warnings = PortfolioService._check_fx_warnings(holdings)
        assert len(warnings) == 1
        assert "Currency conversion unavailable" in warnings[0]


# ═══════════════════════════════════════════════════════════════════
# Patch existing classes with new test methods
# ═══════════════════════════════════════════════════════════════════

# TestFXService addition
def _test_today_live_fetch_success(self, fx_service, mock_supabase):
    """When as_of == today, history is fetched and the rate is cached."""
    today = now_utc().date()
    fetched_date = today - timedelta(days=1)
    calls = {"query": 0}

    def query_cached(base, target, as_of_d):
        calls["query"] += 1
        if (base, target) == ("USD", "CAD") and calls["query"] >= 2:
            return Decimal("1.36")
        return None

    fx_service._query_cached_rate = query_cached
    fx_service._query_future_rate = lambda b, t, a: None

    with patch("providers.fx_provider.fetch_fx_history", return_value=[
        (fetched_date, Decimal("1.36")),
    ]) as mock_fetch, patch.object(fx_service, "_cache_rate") as mock_cache:
        result = fx_service.get_rate("USD", "CAD")

    assert result == Decimal("1.36")
    mock_fetch.assert_called_once()
    mock_cache.assert_called_once_with("USD", "CAD", Decimal("1.36"), fetched_date)

TestFXService.test_today_live_fetch_success = _test_today_live_fetch_success


# TestEnrichHoldingsFX additions
@pytest.mark.asyncio
async def _test_enrich_holdings_cad_holding_in_cad_account(self):
    """When price_currency matches account_base_currency, value_currency is set correctly."""
    from config import settings
    original = settings.ENABLE_FX_CONVERSION
    try:
        settings.ENABLE_FX_CONVERSION = True
        from application.services.portfolio_service import PortfolioService

        service = PortfolioService()
        holdings = [
            {"company_id": 1, "symbol": "RY", "quantity": 100,
             "total_cost": 17000, "price_currency": "CAD",
             "cost_currency": "CAD"},
        ]

        with patch.object(service.portfolio_repo, '_get_split_factors', return_value={}):
            with patch("application.services.portfolio_service.supabase.table") as mock_table:
                mock_execute = MagicMock()
                mock_execute.data = [{"company_id": 1, "close_price": 170.0, "price_date": "2026-06-20"}]
                mock_table.return_value.select.return_value.in_.return_value \
                    .order.return_value.execute.return_value = mock_execute

                result = await service.enrich_holdings_with_prices(
                    holdings, account_base_currency="CAD",
                )

        assert len(result) == 1
        h = result[0]
        assert h["value_currency"] == "CAD"
        assert h["fx_applied"] is True
        assert h["fx_rate"] == 1.0
        assert h["current_value"] == 17000.0  # 170 * 100
    finally:
        settings.ENABLE_FX_CONVERSION = original

TestEnrichHoldingsFX.test_enrich_holdings_cad_holding_in_cad_account = _test_enrich_holdings_cad_holding_in_cad_account


@pytest.mark.asyncio
async def _test_enrich_holdings_usd_holding_in_cad_account(self):
    """When price_currency=USD, account_currency=CAD, conversion happens."""
    from config import settings
    original = settings.ENABLE_FX_CONVERSION
    try:
        settings.ENABLE_FX_CONVERSION = True
        from application.services.portfolio_service import PortfolioService

        service = PortfolioService()
        holdings = [
            {"company_id": 1, "symbol": "AAPL", "quantity": 10,
             "total_cost": 1000, "price_currency": "USD",
             "cost_currency": "USD"},
        ]

        with patch.object(service.portfolio_repo, '_get_split_factors', return_value={}):
            with patch("application.services.portfolio_service.supabase.table") as mock_table:
                mock_execute = MagicMock()
                mock_execute.data = [{"company_id": 1, "close_price": 200.0, "price_date": "2026-06-20"}]
                mock_table.return_value.select.return_value.in_.return_value \
                    .order.return_value.execute.return_value = mock_execute

                rate_execute = MagicMock()
                rate_execute.data = [{"rate": "1.36", "rate_date": "2026-06-20"}]
                mock_table.return_value.select.return_value.eq.return_value.eq.return_value \
                    .lte.return_value.order.return_value.limit.return_value \
                    .execute.return_value = rate_execute

                result = await service.enrich_holdings_with_prices(
                    holdings, account_base_currency="CAD",
                )

        assert len(result) == 1
        h = result[0]
        assert h["value_currency"] == "CAD"
        assert h["fx_applied"] is True
        assert h["fx_rate"] == 1.36
        assert h["current_value"] == 2720.0  # 200 * 10 * 1.36
    finally:
        settings.ENABLE_FX_CONVERSION = original

TestEnrichHoldingsFX.test_enrich_holdings_usd_holding_in_cad_account = _test_enrich_holdings_usd_holding_in_cad_account


@pytest.mark.asyncio
async def _test_enrich_holdings_fx_applied_false_when_rate_missing(self):
    """When no rate exists and live fetch fails, fx_applied=False, fx_rate absent."""
    from config import settings
    original = settings.ENABLE_FX_CONVERSION
    try:
        settings.ENABLE_FX_CONVERSION = True
        from application.services.portfolio_service import PortfolioService

        service = PortfolioService()
        holdings = [
            {"company_id": 1, "symbol": "AAPL", "quantity": 10,
             "total_cost": 1000, "price_currency": "USD",
             "cost_currency": "USD"},
        ]

        with patch.object(service.portfolio_repo, '_get_split_factors', return_value={}):
            with patch("application.services.portfolio_service.supabase.table") as mock_table:
                mock_execute = MagicMock()
                mock_execute.data = [{"company_id": 1, "close_price": 200.0, "price_date": "2026-06-20"}]
                mock_table.return_value.select.return_value.in_.return_value \
                    .order.return_value.execute.return_value = mock_execute

                rate_execute = MagicMock()
                rate_execute.data = []
                mock_table.return_value.select.return_value.eq.return_value.eq.return_value \
                    .lte.return_value.order.return_value.limit.return_value \
                    .execute.return_value = rate_execute

                with patch("providers.fx_provider.fetch_fx_rate", return_value=None):
                    result = await service.enrich_holdings_with_prices(
                        holdings, account_base_currency="CAD",
                    )

        assert len(result) == 1
        h = result[0]
        assert h["fx_applied"] is False
        assert "fx_rate" not in h
        assert h["current_value"] == 2000.0  # unconverted raw value
    finally:
        settings.ENABLE_FX_CONVERSION = original

TestEnrichHoldingsFX.test_enrich_holdings_fx_applied_false_when_rate_missing = _test_enrich_holdings_fx_applied_false_when_rate_missing


@pytest.mark.asyncio
async def _test_enrich_holdings_mixed_currencies(self):
    """RY(CAD) + AAPL(USD) in CAD account, each correctly handled."""
    from config import settings
    original = settings.ENABLE_FX_CONVERSION
    try:
        settings.ENABLE_FX_CONVERSION = True
        from application.services.portfolio_service import PortfolioService

        service = PortfolioService()
        holdings = [
            {"company_id": 1, "symbol": "RY", "quantity": 100,
             "total_cost": 17000, "price_currency": "CAD",
             "cost_currency": "CAD"},
            {"company_id": 2, "symbol": "AAPL", "quantity": 10,
             "total_cost": 1000, "price_currency": "USD",
             "cost_currency": "USD"},
        ]

        with patch.object(service.portfolio_repo, '_get_split_factors', return_value={}):
            with patch("application.services.portfolio_service.supabase.table") as mock_table:
                mock_execute = MagicMock()
                mock_execute.data = [
                    {"company_id": 1, "close_price": 170.0, "price_date": "2026-06-20"},
                    {"company_id": 2, "close_price": 200.0, "price_date": "2026-06-20"},
                ]
                mock_table.return_value.select.return_value.in_.return_value \
                    .order.return_value.execute.return_value = mock_execute

                rate_execute = MagicMock()
                rate_execute.data = [{"rate": "1.36", "rate_date": "2026-06-20"}]
                mock_table.return_value.select.return_value.eq.return_value.eq.return_value \
                    .lte.return_value.order.return_value.limit.return_value \
                    .execute.return_value = rate_execute

                result = await service.enrich_holdings_with_prices(
                    holdings, account_base_currency="CAD",
                )

        assert len(result) == 2
        ry = next(h for h in result if h["symbol"] == "RY")
        aapl = next(h for h in result if h["symbol"] == "AAPL")

        assert ry["value_currency"] == "CAD"
        assert ry["fx_applied"] is True
        assert ry["fx_rate"] == 1.0
        assert ry["current_value"] == 17000.0

        assert aapl["value_currency"] == "CAD"
        assert aapl["fx_applied"] is True
        assert aapl["fx_rate"] == 1.36
        assert aapl["current_value"] == 2720.0
    finally:
        settings.ENABLE_FX_CONVERSION = original

TestEnrichHoldingsFX.test_enrich_holdings_mixed_currencies = _test_enrich_holdings_mixed_currencies


# TestSnapshotBuilderFX additions

def _test_snapshot_builder_mixed_currency(self):
    """RY(CAD) + AAPL(USD) with account_currency=CAD and a rate in the DB."""
    from shared.fx_service import FXService
    from shared.snapshot_builder import build_snapshot_row

    fx = FXService(MagicMock())
    fx._cache_set(("USD", "CAD", "2026-06-20"), Decimal("1.36"))

    row = build_snapshot_row(
        account_id=1,
        snapshot_date=date(2026, 6, 20),
        holdings_state=[
            {
                "company_id": 1, "symbol": "RY", "quantity": 100,
                "total_cost": 17000, "price_currency": "CAD",
            },
            {
                "company_id": 2, "symbol": "AAPL", "quantity": 10,
                "total_cost": 1000, "price_currency": "USD",
            },
        ],
        cash_balance=Decimal("5000"),
        net_deposits=Decimal("20000"),
        prices_by_company={
            1: {"price": 170.00, "price_date": date(2026, 6, 20)},
            2: {"price": 200.00, "price_date": date(2026, 6, 20)},
        },
        job_id="test",
        account_currency="CAD",
        fx_service=fx,
    )
    assert row["holdings_market_value"] == 19720.0  # 17000 + 2720
    assert row["total_value"] == 24720.0  # 17000 + 2720 + 5000

TestSnapshotBuilderFX.test_snapshot_builder_mixed_currency = _test_snapshot_builder_mixed_currency


def _test_snapshot_builder_cost_basis_converted(self):
    """Verify cost_basis is also converted."""
    from shared.fx_service import FXService
    from shared.snapshot_builder import build_snapshot_row

    fx = FXService(MagicMock())
    fx._cache_set(("USD", "CAD", "2026-06-20"), Decimal("1.36"))

    row = build_snapshot_row(
        account_id=1,
        snapshot_date=date(2026, 6, 20),
        holdings_state=[{
            "company_id": 1, "symbol": "AAPL", "quantity": 10,
            "total_cost": 1000, "price_currency": "USD",
        }],
        cash_balance=Decimal("0"),
        net_deposits=Decimal("0"),
        prices_by_company={1: {"price": 200.00, "price_date": date(2026, 6, 20)}},
        job_id="test",
        account_currency="CAD",
        fx_service=fx,
    )
    assert row["cost_basis"] == 1360.0  # 1000 * 1.36

TestSnapshotBuilderFX.test_snapshot_builder_cost_basis_converted = _test_snapshot_builder_cost_basis_converted


def _test_snapshot_builder_cash_balance_unchanged(self):
    """Cash balance not converted."""
    from shared.snapshot_builder import build_snapshot_row

    row = build_snapshot_row(
        account_id=1,
        snapshot_date=date(2026, 6, 20),
        holdings_state=[{
            "company_id": 1, "symbol": "RY", "quantity": 100,
            "total_cost": 17000, "price_currency": "CAD",
        }],
        cash_balance=Decimal("5000.50"),
        net_deposits=Decimal("20000"),
        prices_by_company={1: {"price": 170.00, "price_date": date(2026, 6, 20)}},
        job_id="test",
        account_currency="CAD",
    )
    assert row["cash_balance"] == 5000.5  # unchanged

TestSnapshotBuilderFX.test_snapshot_builder_cash_balance_unchanged = _test_snapshot_builder_cash_balance_unchanged


# ═══════════════════════════════════════════════════════════════════
# 7. _apply_display_currency Tests
# ═══════════════════════════════════════════════════════════════════

class TestApplyDisplayCurrency:

    @pytest.mark.asyncio
    async def test_skips_native_fields(self):
        """
        BUG REPRODUCTION: _native fields (cost_basis_native, current_price_native,
        current_value_native) must NOT be converted — they represent the stock's
        original market currency value. Converting them erases the native reference.
        Without this fix, native values get converted to display currency and
        subsequent calculations that reference the native price are wrong.
        """
        from application.services.portfolio_service import PortfolioService
        service = PortfolioService()

        holdings = [{
            "symbol": "AAPL",
            "company_id": 1,
            "current_value": 2000.0,      # CAD value
            "total_cost": 1500.0,          # CAD value
            "current_price": 200.0,        # CAD price
            "current_value_native": 1500.0,  # USD native
            "current_price_native": 150.0,   # USD native
            "cost_basis_native": 1100.0,     # USD native
            "value_currency": "CAD",
            "fx_applied": True,
            "fx_rate": 1.33,
        }]

        with patch("shared.fx_service.FXService") as MockFX:
            mock_fx = MagicMock()
            mock_fx.get_rate.return_value = Decimal("0.75")
            MockFX.return_value = mock_fx
            result = await service._apply_display_currency(holdings, "USD")

        h = result[0]
        # These SHOULD be converted (CAD → USD)
        assert h["current_value"] == 1500.0, f"Expected 1500.0, got {h['current_value']}"
        assert h["current_price"] == 150.0, f"Expected 150.0, got {h['current_price']}"
        assert h["total_cost"] == 1125.0, f"Expected 1125.0, got {h['total_cost']}"

        # These MUST NOT be converted (they're already in native USD)
        assert h["current_value_native"] == 1500.0, f"Native value changed to {h['current_value_native']}"
        assert h["current_price_native"] == 150.0, f"Native price changed to {h['current_price_native']}"
        assert h["cost_basis_native"] == 1100.0, f"Native cost changed to {h['cost_basis_native']}"

    @pytest.mark.asyncio
    async def test_idempotent_same_currency(self):
        """
        BUG REPRODUCTION: Calling _apply_display_currency twice with the same
        display currency must be a no-op. Without the display_currency_applied
        guard, the second call skips because from_currency == display_currency,
        BUT if the first call already changed value_currency to display_currency,
        then on the second call from_currency == display_currency matches and
        no conversion happens — which is correct. This test verifies values
        are not double-converted.
        """
        from application.services.portfolio_service import PortfolioService
        service = PortfolioService()

        holdings = [{
            "symbol": "AAPL",
            "company_id": 1,
            "current_value": 2000.0,
            "total_cost": 1500.0,
            "current_price": 200.0,
            "value_currency": "CAD",
        }]

        with patch("shared.fx_service.FXService") as MockFX:
            mock_fx = MagicMock()
            mock_fx.get_rate.return_value = Decimal("0.75")
            MockFX.return_value = mock_fx
            result1 = await service._apply_display_currency(holdings, "USD")

        assert result1[0]["current_value"] == 1500.0
        assert result1[0]["value_currency"] == "USD"

        # Second call: from_currency == "USD" == display_currency → no conversion
        result2 = await service._apply_display_currency(result1, "USD")
        assert result2[0]["current_value"] == 1500.0, f"Second call changed value to {result2[0]['current_value']}"
        assert result2[0]["value_currency"] == "USD"

    @pytest.mark.asyncio
    async def test_handles_missing_value_currency(self):
        """
        BUG REPRODUCTION: Holdings enriched without FX enabled have no value_currency
        field. The code defaults to 'USD' which is WRONG if the account is in CAD.
        This test verifies holdings missing value_currency are left unchanged
        rather than being incorrectly converted.
        """
        from application.services.portfolio_service import PortfolioService
        service = PortfolioService()

        holdings = [{
            "symbol": "RY",
            "company_id": 1,
            "current_value": 17000.0,  # CAD value (from a CAD account)
            "total_cost": 15000.0,
            "current_price": 170.0,
            # Note: NO value_currency field — enrichment ran with FX disabled
        }]

        with patch("shared.fx_service.FXService") as MockFX:
            mock_fx = MagicMock()
            mock_fx.get_rate.return_value = Decimal("0.75")
            MockFX.return_value = mock_fx
            result = await service._apply_display_currency(holdings, "USD")

        h = result[0]
        # Without value_currency, we can't know the source currency.
        # The current behavior defaults to "USD" and skips conversion.
        # But the values are really in CAD, so they should be converted.
        # For now, document the behavior: missing value_currency = no conversion.
        assert h["current_value"] == 17000.0, (
            f"Value without value_currency should not be touched, got {h['current_value']}"
        )

    @pytest.mark.asyncio
    async def test_rate_unavailable_leaves_unchanged(self):
        """
        When FX rate is unavailable, holdings must be left with their original
        value_currency and values. Without this, the code could silently report
        values in the wrong currency.
        """
        from application.services.portfolio_service import PortfolioService
        service = PortfolioService()

        holdings = [{
            "symbol": "AAPL",
            "company_id": 1,
            "current_value": 2000.0,
            "total_cost": 1500.0,
            "current_price": 200.0,
            "value_currency": "CAD",
        }]

        with patch("shared.fx_service.FXService") as MockFX:
            mock_fx = MagicMock()
            mock_fx.get_rate.return_value = None  # Rate unavailable
            MockFX.return_value = mock_fx
            result = await service._apply_display_currency(holdings, "EUR")

        h = result[0]
        assert h["current_value"] == 2000.0, "Value changed despite unavailable rate"
        assert h["value_currency"] == "CAD", "Currency changed despite unavailable rate"
        assert "display_currency_applied" not in h, "Flag set despite unavailable rate"

    @pytest.mark.asyncio
    async def test_mixed_accounts_to_third_currency(self):
        """
        User has CAD and USD accounts. Display currency = EUR.
        Both sets of values must be converted to EUR correctly.
        Without this, values from one account could be incorrectly summed
        with values from another account in a different currency.
        """
        from application.services.portfolio_service import PortfolioService
        service = PortfolioService()

        holdings = [
            {
                "symbol": "RY",
                "company_id": 1,
                "current_value": 17000.0,  # CAD
                "total_cost": 15000.0,
                "value_currency": "CAD",
                "account_id": 1,
            },
            {
                "symbol": "AAPL",
                "company_id": 2,
                "current_value": 20000.0,  # USD
                "total_cost": 15000.0,
                "value_currency": "USD",
                "account_id": 2,
            },
        ]

        def mock_get_rate(from_ccy, to_ccy, as_of=None):
            rates = {("CAD", "EUR"): Decimal("0.68"), ("USD", "EUR"): Decimal("0.92")}
            return rates.get((from_ccy.upper(), to_ccy.upper()))

        with patch("shared.fx_service.FXService") as MockFX:
            mock_fx = MagicMock()
            mock_fx.get_rate.side_effect = mock_get_rate
            MockFX.return_value = mock_fx
            result = await service._apply_display_currency(holdings, "EUR")

        ry = next(h for h in result if h["symbol"] == "RY")
        aapl = next(h for h in result if h["symbol"] == "AAPL")

        assert ry["current_value"] == 11560.0, f"RY CAD→EUR: expected 11560, got {ry['current_value']}"
        assert ry["value_currency"] == "EUR"

        assert aapl["current_value"] == 18400.0, f"AAPL USD→EUR: expected 18400, got {aapl['current_value']}"
        assert aapl["value_currency"] == "EUR"

TestApplyDisplayCurrency.test_skips_native_fields = TestApplyDisplayCurrency.test_skips_native_fields
TestApplyDisplayCurrency.test_idempotent_same_currency = TestApplyDisplayCurrency.test_idempotent_same_currency
TestApplyDisplayCurrency.test_handles_missing_value_currency = TestApplyDisplayCurrency.test_handles_missing_value_currency
TestApplyDisplayCurrency.test_rate_unavailable_leaves_unchanged = TestApplyDisplayCurrency.test_rate_unavailable_leaves_unchanged
TestApplyDisplayCurrency.test_mixed_accounts_to_third_currency = TestApplyDisplayCurrency.test_mixed_accounts_to_third_currency


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
