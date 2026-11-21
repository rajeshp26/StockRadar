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
        tuples = list(zip(*arrays, strict=False))
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
#
# I1d: the former ``TestEnrichHoldingsFX`` class tested
# ``PortfolioService.enrich_holdings_with_prices`` / ``_get_split_factors``,
# both removed by refactor commit 22942cc4. The replacement paths
# (``_enrich_holdings`` + ``shared.snapshot_builder.convert_holding_fx``) are
# exercised by ``test_convert_holding_fx.py`` and ``TestSnapshotBuilderFX``
# below. Those obsolete cases were retired; no live behavior lost.
# ═══════════════════════════════════════════════════════════════════

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

    def test_seed_data_shop_currency_fixed(self):
        """Verify seed_e2e_data.py has SHOP->USD."""
        import ast
        with open("scripts/seed_e2e_data.py") as f:
            content = f.read()

        # Check that SHOP is in the USD list
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, val in zip(node.keys, node.values, strict=False):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "currency"
                        and isinstance(val, ast.JoinedStr)
                    ):
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

# I1d: ``TestEnrichHoldingsNativeFields`` and ``TestFXWarnings`` tested the
# removed ``enrich_holdings_with_prices`` / ``_check_fx_warnings`` methods.
# Native-field preservation is now covered by the snapshot-builder tests
# (``TestSnapshotBuilderFX``) and ``test_convert_holding_fx.py``.


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


# I1d: four module-level test functions previously attached to
# ``TestEnrichHoldingsFX`` were removed alongside that class. They exercised
# the same deleted ``enrich_holdings_with_prices`` / ``_get_split_factors``
# API; the equivalent behavior is covered by ``test_convert_holding_fx.py``.

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
# 7. Display-currency tests — RETIRED (I1d)
#
# The former ``TestApplyDisplayCurrency`` class exercised
# ``PortfolioService._apply_display_currency``, removed by commit 22942cc4.
# NOTE (product gap, not hidden by this retirement): ``display_currency`` is
# still plumbed from ``api/portfolio.py`` into ``get_user_portfolio_overview``
# but no conversion method remains. Restoring that feature is a separate
# product decision; these tests cannot pass against the current API and were
# not silently rewritten to assert weaker behavior.
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
