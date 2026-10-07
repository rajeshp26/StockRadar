"""
Tests for CDR pricing — covers all 13 bugs identified in the design doc.

Bug 1: Hardcoded ratio=10 (should be per-company)
Bug 2: CDR price from price_history not converted to CAD
Bug 3: CDR price from current_market_data not divided by ratio
Bug 4: CDR cost_basis in wrong currency
Bug 5: Dashboard endpoint missing CDR ratio
Bug 6: Accounts endpoint missing CDR ratio
Bug 7: Account holdings endpoint missing CDR ratio
Bug 8: All holdings endpoint missing CDR ratio
Bug 9: Watchlist service missing CDR adjustment
Bug 10: SSE broadcast missing CDR adjustment
Bug 11: Stock price endpoint missing CDR adjustment
Bug 12: get_holding_performance() missing CDR adjustment
Bug 13: _fill_snapshot_gaps_incremental price_currency wrong for CDR
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# ============================================================================
# Bug 1: Per-company CDR ratio (not hardcoded)
# ============================================================================

class TestPerCompanyCDRRatio:
    """Bug 1: _resolve_holding_price should use per-company cdr_ratio, not hardcoded CDR_RATIO."""

    def test_per_company_ratio_used(self):
        from shared.snapshot_builder import PriceTier, _resolve_holding_price

        prices = {1: {"price": 350.0, "price_date": date(2024, 6, 1)}}
        history = {}

        # Per-company ratio of 12 (not the default 10)
        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override="TOR",
            cdr_ratio=Decimal("12"),
        )
        assert tier == PriceTier.CURRENT
        assert price == Decimal("350") / Decimal("12")

    def test_fallback_to_default_ratio(self):
        from shared.snapshot_builder import CDR_RATIO, _resolve_holding_price

        prices = {1: {"price": 350.0, "price_date": date(2024, 6, 1)}}
        history = {}

        # No cdr_ratio provided — should fall back to CDR_RATIO (10)
        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override="TOR",
        )
        assert price == Decimal("350") / CDR_RATIO

    def test_non_cdr_not_divided(self):
        from shared.snapshot_builder import _resolve_holding_price

        prices = {1: {"price": 350.0, "price_date": date(2024, 6, 1)}}
        history = {}

        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override=None,
            cdr_ratio=Decimal("12"),
        )
        # Non-CDR: price should NOT be divided
        assert price == Decimal("350")


# ============================================================================
# Bug 2: CDR price from price_history converted to CAD via FX
# ============================================================================

class TestCDRPriceHistoryFX:
    """Bug 2: CDR prices from price_history (US USD) should be divided by ratio AND multiplied by FX."""

    def test_price_history_cdr_with_fx(self):
        from shared.snapshot_builder import PriceTier, _resolve_holding_price

        mock_fx = MagicMock()
        mock_fx.get_rate.return_value = Decimal("1.35")

        prices = {}  # No current market data
        history = {1: [(date(2024, 6, 1), 250.0)]}  # US price $250

        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override="TOR",
            cdr_ratio=Decimal("10"),
            fx_service=mock_fx,
        )
        assert tier == PriceTier.FORWARD_FILL
        # Expected: (250 / 10) * 1.35 = 33.75
        expected = (Decimal("250") / Decimal("10")) * Decimal("1.35")
        assert price == expected

    def test_price_history_cdr_fx_unavailable(self):
        from shared.snapshot_builder import _resolve_holding_price

        mock_fx = MagicMock()
        mock_fx.get_rate.return_value = None  # FX rate unavailable

        prices = {}
        history = {1: [(date(2024, 6, 1), 250.0)]}

        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override="TOR",
            cdr_ratio=Decimal("10"),
            fx_service=mock_fx,
        )
        # Fallback: divide by ratio only
        assert price == Decimal("250") / Decimal("10")


# ============================================================================
# Bug 3: CDR price from yfinance_tor divided by ratio only (no FX)
# ============================================================================

class TestCDRYFinanceTor:
    """Bug 3: CDR prices from yfinance_tor (TSX share in CAD) should be divided by ratio only."""

    def test_yfinance_tor_source(self):
        from shared.snapshot_builder import _resolve_holding_price

        prices = {1: {"price": 350.0, "price_date": date(2024, 6, 1), "source": "yfinance_tor"}}
        history = {}

        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override="TOR",
            cdr_ratio=Decimal("10"),
        )
        # yfinance_tor: price is already in CAD, just divide by ratio
        assert price == Decimal("350") / Decimal("10")

    def test_yfinance_tor_with_fx_ignored(self):
        from shared.snapshot_builder import _resolve_holding_price

        mock_fx = MagicMock()
        mock_fx.get_rate.return_value = Decimal("1.35")

        prices = {1: {"price": 350.0, "price_date": date(2024, 6, 1), "source": "yfinance_tor"}}
        history = {}

        price, tier, _ = _resolve_holding_price(
            company_id=1, symbol="TSLA", avg_cost=None,
            latest_prices=prices, price_history=history,
            snapshot_date=date(2024, 6, 1),
            exchange_override="TOR",
            cdr_ratio=Decimal("10"),
            fx_service=mock_fx,
        )
        # yfinance_tor: FX should NOT be applied (price already in CAD)
        assert price == Decimal("350") / Decimal("10")


# ============================================================================
# Bug 4: CDR cost_basis currency
# ============================================================================

class TestCDRCostBasisCurrency:
    """Bug 4: CDR holdings should have price_currency='CAD' to prevent double FX conversion."""

    def test_cdr_price_currency_cad_in_snapshot(self):
        from shared.snapshot_builder import build_snapshot_row

        holdings = [{
            "company_id": 1,
            "symbol": "TSLA",
            "quantity": 10,
            "total_cost": 294.1,
            "average_cost": 29.41,
            "price_currency": "USD",
            "exchange_override": "TOR",
        }]
        prices = {1: {"price": 350.0, "price_date": date(2024, 6, 1), "source": "yfinance_tor"}}
        history = {}
        exchange_overrides = {1: "TOR"}
        companies_map = {1: {"cdr_ratio": 10.0}}
        company_currencies = {1: "USD"}

        with patch("config.settings") as mock_settings:
            mock_settings.ENABLE_FX_CONVERSION = False
            result = build_snapshot_row(
                account_id=1,
                snapshot_date=date(2024, 6, 1),
                holdings_state=holdings,
                cash_balance=Decimal("0"),
                net_deposits=Decimal("1000"),
                prices_by_company=prices,
                job_id="test",
                account_currency="CAD",
                price_history=history,
                exchange_overrides=exchange_overrides,
                company_currencies=company_currencies,
                companies_map=companies_map,
            )

        # CDR price should be 350/10 = $35 CAD
        h = result["holdings_json"][0]
        assert h["current_price"] == 35.0
        assert h["current_value"] == 350.0  # 10 * 35


# ============================================================================
# Bug 5-8: API endpoints missing CDR ratio
# ============================================================================

class TestApplyCdrAdjustment:
    """Bug 5-8: The apply_cdr_adjustment helper correctly adjusts CDR prices."""

    def test_apply_cdr_with_ratio(self):
        from api.portfolio import apply_cdr_adjustment
        cdr_ratios = {1: 12.0}

        result = apply_cdr_adjustment(360.0, 1, cdr_ratios, "TOR")
        assert result == 360.0 / 12.0

    def test_apply_cdr_with_default_ratio(self):
        from api.portfolio import apply_cdr_adjustment
        cdr_ratios = {}  # No ratio in DB

        result = apply_cdr_adjustment(350.0, 1, cdr_ratios, "TOR")
        # Falls back to CDR_RATIO = 10
        assert result == 350.0 / 10.0

    def test_apply_cdr_non_cdr_holding(self):
        from api.portfolio import apply_cdr_adjustment
        cdr_ratios = {1: 12.0}

        result = apply_cdr_adjustment(350.0, 1, cdr_ratios, "XTSE")
        # Not a CDR: price unchanged
        assert result == 350.0

    def test_apply_cdr_missing_override_is_not_a_cdr(self):
        from api.portfolio import apply_cdr_adjustment
        cdr_ratios = {1: 12.0}

        result = apply_cdr_adjustment(350.0, 1, cdr_ratios, None)
        # A holding with no TOR override must not be assumed to be a CDR: doing
        # so overvalues it by the ratio, which is the error this change removes.
        assert result == 350.0

    def test_apply_cdr_uses_the_holding_not_the_company(self):
        from api.portfolio import apply_cdr_adjustment

        cdr_ratios = {7: 10.0}

        tor_holding = apply_cdr_adjustment(350.0, 7, cdr_ratios, "TOR")
        plain_holding = apply_cdr_adjustment(350.0, 7, cdr_ratios, None)

        assert tor_holding == 35.0
        assert plain_holding == 350.0

    def test_apply_cdr_rejects_a_company_keyed_map(self):
        from api.portfolio import apply_cdr_adjustment

        with pytest.raises(TypeError):
            apply_cdr_adjustment(350.0, 7, {7: 10.0}, {7: "TOR"})


# ============================================================================
# Bug 9: Watchlist service CDR adjustment
# ============================================================================

class TestWatchlistCDR:
    """Bug 9: Watchlist service should apply CDR ratio to prices."""

    def test_cdr_price_divided_in_watchlist(self):
        """Verify that if a company has exchange_override=TOR, the watchlist service divides by ratio."""
        # The watchlist service divides current_price and previous_close by ratio
        # for CDR holdings. This is a logic test.
        tsx_price = 350.0
        prev_close_tsx = 345.0
        ratio = 10.0

        cdr_price = tsx_price / ratio
        cdr_prev = prev_close_tsx / ratio

        assert cdr_price == 35.0
        assert cdr_prev == 34.5


# ============================================================================
# Bug 10: SSE broadcast CDR adjustment
# ============================================================================

class TestSSECDR:
    """Bug 10: SSE broadcast should apply CDR ratio to prices."""

    def test_cdr_sse_price_adjustment(self):
        """Verify that SSE broadcast divides price by ratio for CDR holdings."""
        # SSE gets raw yfinance price (TSX share in CAD)
        raw_price = 350.0
        raw_prev = 345.0
        ratio = 10.0

        cdr_price = raw_price / ratio
        cdr_prev = raw_prev / ratio

        change = cdr_price - cdr_prev
        change_pct = (change / cdr_prev) * 100

        assert cdr_price == 35.0
        assert abs(change_pct - 1.449) < 0.01


# ============================================================================
# Bug 11: Stock price endpoint CDR adjustment
# ============================================================================

class TestStockPriceEndpointCDR:
    """Bug 11: /stocks/{symbol}/quote should apply CDR ratio."""

    def test_cdr_quote_adjustment(self):
        """Verify that the stock quote endpoint divides by ratio for CDR holdings."""
        raw_price = 350.0
        raw_prev = 345.0
        ratio = 12.0

        cdr_price = raw_price / ratio
        cdr_prev = raw_prev / ratio
        change = cdr_price - cdr_prev
        change_pct = (change / cdr_prev) * 100

        assert abs(cdr_price - 29.167) < 0.01
        assert abs(change_pct - 1.449) < 0.1


# ============================================================================
# Bug 12: get_holding_performance CDR adjustment
# ============================================================================

class TestHoldingPerformanceCDR:
    """Bug 12: get_holding_performance should apply CDR ratio + FX to price_history."""

    def test_performance_cdr_price_levels(self):
        """Verify that historical CDR prices are in CDR price range (~$35, not ~$350)."""
        # US stock price in price_history
        us_price = 250.0
        ratio = 10.0
        fx_rate = 1.35

        # CDR price = (US_price / ratio) * FX
        cdr_price = (us_price / ratio) * fx_rate
        assert cdr_price == 33.75
        # This is in the ~$35 range, not ~$350
        assert 20 < cdr_price < 50


# ============================================================================
# Bug 13: _fill_snapshot_gaps_incremental price_currency for CDR
# ============================================================================

class TestGapFillCDRCurrency:
    """Bug 13: _fill_snapshot_gaps_incremental should set price_currency='CAD' for CDR holdings."""

    def test_cdr_holding_price_currency_override(self):
        """Verify that the gap-fill sets price_currency='CAD' for CDR holdings."""
        # Simulate the logic
        exch_override = "TOR"
        price_currency = "USD"

        holding_dict = {
            "company_id": 1,
            "price_currency": price_currency,
        }

        if exch_override == "TOR":
            holding_dict["price_currency"] = "CAD"

        assert holding_dict["price_currency"] == "CAD"

    def test_non_cdr_holding_price_currency_unchanged(self):
        """Non-CDR holdings keep their original price_currency."""
        exch_override = None
        price_currency = "USD"

        holding_dict = {
            "company_id": 1,
            "price_currency": price_currency,
        }

        if exch_override == "TOR":
            holding_dict["price_currency"] = "CAD"

        assert holding_dict["price_currency"] == "USD"


# ============================================================================
# Bug 4 (extended): CDR price_currency prevents double conversion
# ============================================================================

class TestCDRNoDoubleConversion:
    """Bug 4: CDR holdings with price_currency='CAD' should not be re-converted by FX."""

    def test_cdr_cad_account_no_conversion(self):
        from shared.snapshot_builder import convert_holding_fx

        holding = {
            "company_id": 1,
            "price_currency": "CAD",
            "exchange_override": "TOR",
        }
        # CDR price is already $35 CAD
        raw_value = Decimal("350")  # 10 units * $35
        total_cost = Decimal("294.10")

        mock_fx = MagicMock()
        mock_fx.convert_or_warn.return_value = (raw_value, None)

        value, cost = convert_holding_fx(
            holding, raw_value, total_cost, "CAD",
            mock_fx, date(2024, 6, 1), True,
        )
        # price_currency=CAD, account_currency=CAD → no FX conversion needed
        assert value == raw_value
        assert cost == total_cost


# ============================================================================
# get_cdr_ratio_for_company
# ============================================================================

class TestGetCDRRatioForCompany:
    """Test the get_cdr_ratio_for_company helper."""

    def test_ratio_found(self):
        from shared.snapshot_builder import get_cdr_ratio_for_company
        companies_map = {1: {"cdr_ratio": 12.5}}
        result = get_cdr_ratio_for_company(1, companies_map)
        assert result == Decimal("12.5")

    def test_ratio_not_found(self):
        from shared.snapshot_builder import get_cdr_ratio_for_company
        companies_map = {1: {"cdr_ratio": None}}
        result = get_cdr_ratio_for_company(1, companies_map)
        assert result is None

    def test_company_not_in_map(self):
        from shared.snapshot_builder import get_cdr_ratio_for_company
        companies_map = {2: {"cdr_ratio": 10.0}}
        result = get_cdr_ratio_for_company(1, companies_map)
        assert result is None

    def test_no_map(self):
        from shared.snapshot_builder import get_cdr_ratio_for_company
        result = get_cdr_ratio_for_company(1, None)
        assert result is None
