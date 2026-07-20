"""
Tests for the shared convert_holding_fx function.

Verifies that FX conversion is consistent across all code paths:
  - Per-lot FX (when lots are present)
  - Single-date FX fallback (when lots are absent)
  - Same-currency (no conversion)
  - FX disabled
  - Missing FX rate fallback

Run: pytest tests/test_convert_holding_fx.py -v
"""

import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from shared.snapshot_builder import convert_holding_fx


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _make_fx_service(rate_map):
    """Create a mock FXService that returns rates from rate_map.

    rate_map: dict of (base, target, date_str) -> Decimal rate
    """
    svc = MagicMock()
    svc._rate_map = rate_map

    def _get_rate(base, target, as_of):
        key = (base.upper(), target.upper(), as_of.isoformat())
        return rate_map.get(key)

    svc.get_rate = _get_rate

    def _convert_or_warn(amount, from_curr, to_curr, as_of=None, holding_id=None):
        rate = _get_rate(from_curr, to_curr, as_of or date.today())
        if rate is not None:
            return (amount * rate, True)
        return (amount, False)

    svc.convert_or_warn = _convert_or_warn
    return svc


# ═══════════════════════════════════════════════════════════════════
# 1. Same-currency (no conversion)
# ═══════════════════════════════════════════════════════════════════

class TestSameCurrency:

    def test_usd_account_holding_usd_stock(self):
        holding = {"company_id": 1, "price_currency": "USD"}
        val, cost = convert_holding_fx(
            holding, Decimal("10000"), Decimal("8000"),
            "USD", MagicMock(), date(2026, 1, 15), True,
        )
        assert val == Decimal("10000")
        assert cost == Decimal("8000")

    def test_cad_account_holding_cad_stock(self):
        holding = {"company_id": 1, "price_currency": "CAD"}
        val, cost = convert_holding_fx(
            holding, Decimal("15000"), Decimal("12000"),
            "CAD", MagicMock(), date(2026, 1, 15), True,
        )
        assert val == Decimal("15000")
        assert cost == Decimal("12000")


# ═══════════════════════════════════════════════════════════════════
# 2. FX disabled
# ═══════════════════════════════════════════════════════════════════

class TestFXDisabled:

    def test_returns_unconverted_when_disabled(self):
        holding = {"company_id": 1, "price_currency": "USD"}
        val, cost = convert_holding_fx(
            holding, Decimal("10000"), Decimal("8000"),
            "CAD", MagicMock(), date(2026, 1, 15), False,
        )
        assert val == Decimal("10000")
        assert cost == Decimal("8000")


# ═══════════════════════════════════════════════════════════════════
# 3. Per-lot FX conversion
# ═══════════════════════════════════════════════════════════════════

class TestPerLotFX:

    def test_two_lots_different_dates(self):
        """Verify per-lot FX uses each lot's own trade date."""
        rate_map = {
            ("USD", "CAD", "2021-02-08"): Decimal("1.2758"),
            ("USD", "CAD", "2022-06-01"): Decimal("1.2639"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 1,
            "price_currency": "USD",
            "lots": [
                {"quantity": Decimal("100"), "cost_per_share": Decimal("130"), "date": date(2021, 2, 8)},
                {"quantity": Decimal("50"), "cost_per_share": Decimal("150"), "date": date(2022, 6, 1)},
            ],
        }

        val, cost = convert_holding_fx(
            holding, Decimal("24750"), Decimal("24750"),  # 150 * 165 avg
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        # Market value: 24750 USD * rate at 2026-07-14 (not in rate_map, so falls back)
        # Cost basis: Lot1: 100 * 130 * 1.2758 = 16585.40
        #             Lot2:  50 * 150 * 1.2639 = 9479.25
        #             Total = 26064.65
        expected_cost = Decimal("100") * Decimal("130") * Decimal("1.2758") + \
                        Decimal("50") * Decimal("150") * Decimal("1.2639")
        assert cost == expected_cost

    def test_three_lots_same_date(self):
        """All lots on the same date — should still work."""
        rate_map = {
            ("USD", "CAD", "2024-07-05"): Decimal("1.3615"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 2,
            "price_currency": "USD",
            "lots": [
                {"quantity": Decimal("30"), "cost_per_share": Decimal("180"), "date": date(2024, 7, 5)},
                {"quantity": Decimal("20"), "cost_per_share": Decimal("190"), "date": date(2024, 7, 5)},
                {"quantity": Decimal("10"), "cost_per_share": Decimal("200"), "date": date(2024, 7, 5)},
            ],
        }

        _, cost = convert_holding_fx(
            holding, Decimal("12000"), Decimal("11100"),
            "CAD", fx_svc, date(2024, 7, 5), True,
        )

        expected_cost = (Decimal("30") * Decimal("180") +
                         Decimal("20") * Decimal("190") +
                         Decimal("10") * Decimal("200")) * Decimal("1.3615")
        assert cost == expected_cost


# ═══════════════════════════════════════════════════════════════════
# 4. Single-date FX fallback (no lots)
# ═══════════════════════════════════════════════════════════════════

class TestSingleDateFXFallback:

    def test_uses_trade_date_for_cost_basis(self):
        """Without lots, cost basis FX uses trade_date."""
        rate_map = {
            ("USD", "CAD", "2023-03-15"): Decimal("1.3500"),
            ("USD", "CAD", "2026-07-14"): Decimal("1.4149"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 3,
            "price_currency": "USD",
            "trade_date": date(2023, 3, 15),
        }

        val, cost = convert_holding_fx(
            holding, Decimal("50000"), Decimal("40000"),
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        # Market value: 50000 * 1.4149 (snapshot_date)
        assert val == Decimal("50000") * Decimal("1.4149")
        # Cost basis: 40000 * 1.3500 (trade_date)
        assert cost == Decimal("40000") * Decimal("1.3500")

    def test_falls_back_to_snapshot_date_when_no_trade_date(self):
        """Without lots and without trade_date, uses snapshot_date."""
        rate_map = {
            ("USD", "CAD", "2026-07-14"): Decimal("1.4149"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 4,
            "price_currency": "USD",
        }

        _, cost = convert_holding_fx(
            holding, Decimal("50000"), Decimal("40000"),
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        assert cost == Decimal("40000") * Decimal("1.4149")


# ═══════════════════════════════════════════════════════════════════
# 5. Missing FX rate
# ═══════════════════════════════════════════════════════════════════

class TestMissingFXRate:

    def test_returns_unconverted_when_rate_missing(self):
        """When FX rate is unavailable, returns unconverted values."""
        fx_svc = _make_fx_service({})

        holding = {
            "company_id": 5,
            "price_currency": "USD",
            "trade_date": date(2023, 1, 1),
        }

        val, cost = convert_holding_fx(
            holding, Decimal("50000"), Decimal("40000"),
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        # No rate available for USD->CAD, so values should be unconverted
        assert val == Decimal("50000")
        assert cost == Decimal("40000")

    def test_partial_lot_rates_some_missing(self):
        """When some lot rates are missing, those lots are unconverted."""
        rate_map = {
            ("USD", "CAD", "2021-02-08"): Decimal("1.2758"),
            # No rate for 2022-06-01
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 6,
            "price_currency": "USD",
            "lots": [
                {"quantity": Decimal("100"), "cost_per_share": Decimal("130"), "date": date(2021, 2, 8)},
                {"quantity": Decimal("50"), "cost_per_share": Decimal("150"), "date": date(2022, 6, 1)},
            ],
        }

        _, cost = convert_holding_fx(
            holding, Decimal("24750"), Decimal("24750"),
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        # Lot 1: 100 * 130 * 1.2758 = 16585.40 (converted)
        # Lot 2: 50 * 150 = 7500 (unconverted, rate missing)
        expected_cost = Decimal("100") * Decimal("130") * Decimal("1.2758") + \
                        Decimal("50") * Decimal("150")
        assert cost == expected_cost


# ═══════════════════════════════════════════════════════════════════
# 6. FXService is None
# ═══════════════════════════════════════════════════════════════════

class TestFXServiceNone:

    def test_returns_unconverted_when_fx_service_none(self):
        holding = {"company_id": 7, "price_currency": "USD"}
        val, cost = convert_holding_fx(
            holding, Decimal("10000"), Decimal("8000"),
            "CAD", None, date(2026, 1, 15), True,
        )
        assert val == Decimal("10000")
        assert cost == Decimal("8000")


# ═══════════════════════════════════════════════════════════════════
# 7. Currency case insensitivity
# ═══════════════════════════════════════════════════════════════════

class TestCaseInsensitivity:

    def test_lowercase_currencies(self):
        rate_map = {
            ("USD", "CAD", "2026-01-15"): Decimal("1.4000"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 8,
            "price_currency": "usd",
        }

        val, cost = convert_holding_fx(
            holding, Decimal("10000"), Decimal("8000"),
            "cad", fx_svc, date(2026, 1, 15), True,
        )

        assert val == Decimal("10000") * Decimal("1.4000")
        assert cost == Decimal("8000") * Decimal("1.4000")


# ═══════════════════════════════════════════════════════════════════
# 8. Zero values
# ═══════════════════════════════════════════════════════════════════

class TestZeroValues:

    def test_zero_value_zero_cost(self):
        holding = {"company_id": 9, "price_currency": "USD"}
        val, cost = convert_holding_fx(
            holding, Decimal("0"), Decimal("0"),
            "CAD", MagicMock(), date(2026, 1, 15), True,
        )
        assert val == Decimal("0")
        assert cost == Decimal("0")


# ═══════════════════════════════════════════════════════════════════
# 9. Currency fallback (price_currency key)
# ═══════════════════════════════════════════════════════════════════

class TestCurrencyFallback:

    def test_uses_currency_when_price_currency_absent(self):
        rate_map = {
            ("CAD", "USD", "2026-01-15"): Decimal("0.7200"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 10,
            "currency": "CAD",  # no price_currency key
        }

        val, cost = convert_holding_fx(
            holding, Decimal("15000"), Decimal("12000"),
            "USD", fx_svc, date(2026, 1, 15), True,
        )

        assert val == Decimal("15000") * Decimal("0.7200")
        assert cost == Decimal("12000") * Decimal("0.7200")

    def test_defaults_to_usd_when_neither_key_present(self):
        rate_map = {
            ("USD", "CAD", "2026-01-15"): Decimal("1.4000"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding = {
            "company_id": 11,
            # no price_currency, no currency
        }

        val, _ = convert_holding_fx(
            holding, Decimal("10000"), Decimal("8000"),
            "CAD", fx_svc, date(2026, 1, 15), True,
        )

        # Default price_currency is USD, so conversion should happen
        assert val == Decimal("10000") * Decimal("1.4000")


# ═══════════════════════════════════════════════════════════════════
# 10. Real-world scenario: CDR (Canadian Depository Receipt)
# ═══════════════════════════════════════════════════════════════════

class TestCDRScenario:

    def test_cdr_is_cad_no_conversion_needed(self):
        """CDR holdings are priced in CAD — no FX conversion needed."""
        holding = {
            "company_id": 12,
            "price_currency": "CAD",
        }

        val, cost = convert_holding_fx(
            holding, Decimal("5000"), Decimal("4500"),
            "CAD", MagicMock(), date(2026, 1, 15), True,
        )

        assert val == Decimal("5000")
        assert cost == Decimal("4500")


# ═══════════════════════════════════════════════════════════════════
# 11. Consistency: per-lot vs. single-date should produce different
#     results when dates differ (proving per-lot matters)
# ═══════════════════════════════════════════════════════════════════

class TestPerLotVsSingleDate:

    def test_per_lot_differs_from_single_date(self):
        """When lots span multiple dates, per-lot and single-date produce
        different cost basis — proving that per-lot FX is more accurate."""
        rate_map = {
            ("USD", "CAD", "2021-01-01"): Decimal("1.2700"),
            ("USD", "CAD", "2024-01-01"): Decimal("1.3500"),
            ("USD", "CAD", "2026-07-14"): Decimal("1.4149"),
        }
        fx_svc = _make_fx_service(rate_map)

        holding_with_lots = {
            "company_id": 13,
            "price_currency": "USD",
            "lots": [
                {"quantity": Decimal("100"), "cost_per_share": Decimal("100"), "date": date(2021, 1, 1)},
                {"quantity": Decimal("100"), "cost_per_share": Decimal("100"), "date": date(2024, 1, 1)},
            ],
            "trade_date": date(2021, 1, 1),  # earliest lot
        }

        _, cost_per_lot = convert_holding_fx(
            holding_with_lots, Decimal("20000"), Decimal("20000"),
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        # Single-date fallback uses trade_date (2021-01-01)
        holding_no_lots = {
            "company_id": 13,
            "price_currency": "USD",
            "trade_date": date(2021, 1, 1),
        }

        _, cost_single = convert_holding_fx(
            holding_no_lots, Decimal("20000"), Decimal("20000"),
            "CAD", fx_svc, date(2026, 7, 14), True,
        )

        # Per-lot: 10000 * 1.27 + 10000 * 1.35 = 26200
        expected_per_lot = Decimal("10000") * Decimal("1.2700") + \
                           Decimal("10000") * Decimal("1.3500")
        assert cost_per_lot == expected_per_lot

        # Single-date: 20000 * 1.27 = 25400
        expected_single = Decimal("20000") * Decimal("1.2700")
        assert cost_single == expected_single

        # They should differ — proving per-lot is more accurate
        assert cost_per_lot != cost_single
        assert cost_per_lot == Decimal("26200")
        assert cost_single == Decimal("25400")
