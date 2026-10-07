"""Price-quality regression tests for _get_dashboard_from_prices.

Two defects are locked here:

1. ``STALE_PRICE`` was unreachable. The price row's fetch time was stamped
   ``now_utc()`` at read time, so the computed age was always ~0 and the
   staleness comparison could never fire.
2. A holding with no price row was marked ``MISSING`` at the holding level but
   nothing propagated it to the dashboard-level ``data_quality_flag``, which
   reported ``OK`` — silently presenting a cost-basis mark as a real valuation.

The missing-price flag is ``COST_FALLBACK``, matching ``PriceTier.COST_BASIS``
in ``shared.snapshot_builder`` and the same flag the snapshot job and replay
engine already emit.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from shared.time_utils import now_utc

DAY = 86400


def _make_table_mock(data=None):
    t = MagicMock()
    t.select.return_value = t
    t.eq.return_value = t
    t.in_.return_value = t
    t.execute.return_value = MagicMock(data=data or [])
    return t


def _make_client(tables):
    mocks = {name: _make_table_mock(data) for name, data in tables.items()}
    client = MagicMock()
    client.table.side_effect = lambda name: mocks.get(name, _make_table_mock([]))
    return client


def _holding(company_id, symbol, **overrides):
    h = {
        "company_id": company_id,
        "symbol": symbol,
        "company_name": symbol,
        "account_id": 1,
        "quantity": 10.0,
        "total_cost": 1000.0,
        "average_cost": 100.0,
    }
    h.update(overrides)
    return h


def _account():
    return {
        "account_id": 1,
        "account_name": "TFSA",
        "account_type": "tfsa",
        "currency": "CAD",
        "portfolio_brokerages": {"brokerage_name": "Wealthsimple"},
    }


def _run(holdings, price_rows):
    """Drive _get_dashboard_from_prices against a fake Supabase client."""
    from api import portfolio as portfolio_api

    repo = MagicMock()
    repo.get_user_all_holdings.return_value = holdings
    repo.get_user_accounts.return_value = [_account()]
    repo.get_accounts_dividends_by_year.return_value = []

    client = _make_client({"current_market_data": price_rows})
    settings = MagicMock()
    settings.ENABLE_FX_CONVERSION = False

    with (
        patch.object(portfolio_api, "PortfolioRepository", return_value=repo),
        patch.object(portfolio_api, "supabase", client),
        patch.object(portfolio_api, "settings", settings),
        patch.object(portfolio_api, "_get_company_cdr_ratios", return_value={}),
        patch.object(portfolio_api, "_convert_holding_values"),
        patch.object(portfolio_api, "_compute_overview_from_holdings", return_value={}),
    ):
        import asyncio

        return asyncio.run(portfolio_api._get_dashboard_from_prices(db_user_id=7))


class TestAggregateQuality:
    def test_stale_outranks_cost_fallback(self):
        from api.portfolio import _aggregate_quality

        assert _aggregate_quality(any_stale=True, any_cost_fallback=True) == "STALE_PRICE"

    def test_cost_fallback_surfaces_when_no_stale(self):
        from api.portfolio import _aggregate_quality

        assert _aggregate_quality(any_stale=False, any_cost_fallback=True) == "COST_FALLBACK"

    def test_clean_portfolio_is_ok(self):
        from api.portfolio import _aggregate_quality

        assert _aggregate_quality(any_stale=False, any_cost_fallback=False) == "OK"


class TestPriceAgeIsDerivedFromObservation:
    def test_old_observation_is_flagged_stale(self):
        """The core regression: age must come from the row, not from read time."""
        stale = (now_utc() - timedelta(days=10)).isoformat()
        result = _run(
            [_holding(1, "AAA")],
            [{"company_id": 1, "current_price": 120.0, "last_updated": stale}],
        )
        assert result["data_quality_flag"] == "STALE_PRICE"

    def test_recent_observation_is_ok(self):
        fresh = (now_utc() - timedelta(hours=1)).isoformat()
        result = _run(
            [_holding(1, "AAA")],
            [{"company_id": 1, "current_price": 120.0, "last_updated": fresh}],
        )
        assert result["data_quality_flag"] == "OK"

    def test_naive_timestamp_without_offset_is_accepted(self):
        fresh = (now_utc() - timedelta(hours=1)).replace(tzinfo=None).isoformat()
        result = _run(
            [_holding(1, "AAA")],
            [{"company_id": 1, "current_price": 120.0, "last_updated": fresh}],
        )
        assert result["data_quality_flag"] == "OK"

    def test_missing_observation_fails_safe_to_stale(self):
        result = _run(
            [_holding(1, "AAA")],
            [{"company_id": 1, "current_price": 120.0, "last_updated": None}],
        )
        assert result["data_quality_flag"] == "STALE_PRICE"

    def test_malformed_observation_fails_safe_to_stale(self):
        result = _run(
            [_holding(1, "AAA")],
            [{"company_id": 1, "current_price": 120.0, "last_updated": "not-a-timestamp"}],
        )
        assert result["data_quality_flag"] == "STALE_PRICE"


class TestCostFallbackPropagates:
    def test_priced_holding_without_price_row_is_cost_fallback(self):
        result = _run([_holding(1, "AAA")], [])
        assert result["data_quality_flag"] == "COST_FALLBACK"

    def test_cost_fallback_uses_cost_basis_not_zero(self):
        result = _run([_holding(1, "AAA")], [])
        holding = result["holdings"][0]
        assert holding["current_price"] == 100.0
        assert holding["current_value"] == 1000.0

    def test_stale_outranks_cost_fallback_in_dashboard(self):
        stale = (now_utc() - timedelta(days=10)).isoformat()
        result = _run(
            [_holding(1, "AAA"), _holding(2, "BBB")],
            [{"company_id": 1, "current_price": 120.0, "last_updated": stale}],
        )
        assert result["data_quality_flag"] == "STALE_PRICE"

    def test_no_price_rows_anywhere_is_cost_fallback(self):
        result = _run([_holding(1, "AAA"), _holding(2, "BBB")], [])
        assert result["data_quality_flag"] == "COST_FALLBACK"
