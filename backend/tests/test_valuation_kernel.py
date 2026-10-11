"""Unit tests for the single CDR/FX valuation kernel (shared.valuation).

These lock the extraction that ended the "Overview card vs chart" CDR divergence:
before it, six copies of the CDR rule existed and only the snapshot copy applied
the USD->CAD FX step, so the live/overview copies understated every US-sourced
CDR holding by the FX factor. The kernel is the one rule; the cross-path test
proves the snapshot, API and price_utils call sites now agree numerically.

No database, no fixtures — the kernel is pure (trace_division is observational).
"""
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from shared.valuation import (
    DEFAULT_ACCOUNT_CURRENCY,
    AdjustedPrice,
    adjust_cdr_price,
    is_cad_native_source,
    is_cdr_override,
    resolve_cdr_ratio,
)

# ============================================================================
# The core rule
# ============================================================================


class TestAdjustCdrPrice:
    """One rule: non-CDR unchanged; CDR CAD-native -> /ratio; CDR US -> (/ratio)*fx."""

    def test_non_cdr_returned_unchanged(self):
        result = adjust_cdr_price(350.0, is_cdr=False, cdr_ratio=Decimal("10"))
        assert result == AdjustedPrice(price=Decimal("350"), is_cdr=False)
        assert result.cdr_ratio_applied is None
        assert result.fx_rate_applied is None

    def test_non_cdr_ignores_fx_and_ratio(self):
        result = adjust_cdr_price(
            350.0, is_cdr=False, cdr_ratio=Decimal("7"), fx_rate=Decimal("1.4"),
        )
        assert result.price == Decimal("350")
        assert result.fx_rate_applied is None

    def test_cdr_cad_native_source_divides_only(self):
        """yfinance_tor quotes are already CAD — dividing is the whole adjustment."""
        result = adjust_cdr_price(
            350.0, is_cdr=True, cdr_ratio=Decimal("10"),
            price_source="yfinance_tor", fx_rate=Decimal("1.40"),
        )
        assert result.price == Decimal("35")
        assert result.cdr_ratio_applied == Decimal("10")
        assert result.fx_rate_applied is None

    def test_cdr_cad_native_via_price_currency_divides_only(self):
        result = adjust_cdr_price(
            250.0, is_cdr=True, cdr_ratio=Decimal("10"),
            price_currency="CAD", account_currency="CAD", fx_rate=Decimal("1.4"),
        )
        assert result.price == Decimal("25")
        assert result.fx_rate_applied is None

    def test_cdr_us_source_divides_and_fx_converts(self):
        result = adjust_cdr_price(
            250.0, is_cdr=True, cdr_ratio=Decimal("10"),
            price_source="price_history", fx_rate=Decimal("1.35"),
        )
        assert result.price == (Decimal("250") / Decimal("10")) * Decimal("1.35")

    def test_cdr_us_source_without_fx_falls_back_to_ratio_only(self):
        """A missing rate must degrade to /ratio, never to a wrong full-price value."""
        result = adjust_cdr_price(
            250.0, is_cdr=True, cdr_ratio=Decimal("10"),
            price_source="price_history", fx_rate=None,
        )
        assert result.price == Decimal("25")
        assert result.fx_rate_applied is None

    def test_cdr_us_source_rejects_zero_or_negative_rate(self):
        for bad_rate in (Decimal("0"), Decimal("-1.2")):
            result = adjust_cdr_price(
                250.0, is_cdr=True, cdr_ratio=Decimal("10"),
                price_source="price_history", fx_rate=bad_rate,
            )
            assert result.price == Decimal("25")
            assert result.fx_rate_applied is None

    def test_none_ratio_falls_back_to_constant_not_no_division(self):
        """The original defect: a None ratio must still divide by the structural 10."""
        result = adjust_cdr_price(250.0, is_cdr=True, cdr_ratio=None)
        assert result.price == Decimal("25")
        assert result.cdr_ratio_applied == Decimal("10")

    def test_none_price_returns_zero(self):
        result = adjust_cdr_price(None, is_cdr=True)
        assert result.price == Decimal("0")

    def test_msft_snapshot_anchor(self):
        """Real anchor: MSFT cid45 snapshot price 529.76 / 10 * 1.403 CAD."""
        result = adjust_cdr_price(
            529.76, is_cdr=True, cdr_ratio=None,
            price_source="price_history", fx_rate=Decimal("1.403"),
        )
        expected = (Decimal("529.76") / Decimal("10")) * Decimal("1.403")
        assert result.price == pytest.approx(expected, abs=Decimal("0.0001"))

    def test_audit_fields_reconstruct_the_price_offline(self):
        result = adjust_cdr_price(
            529.76, is_cdr=True, cdr_ratio=Decimal("10"),
            price_source="price_history", fx_rate=Decimal("1.403"),
        )
        reconstructed = (
            Decimal("529.76") / result.cdr_ratio_applied * result.fx_rate_applied
        )
        assert reconstructed == result.price


# ============================================================================
# resolve_cdr_ratio
# ============================================================================


class TestResolveCdrRatio:
    def test_per_company_ratio_wins(self):
        assert resolve_cdr_ratio(Decimal("12")) == Decimal("12")

    def test_none_falls_back_to_structural_constant(self):
        assert resolve_cdr_ratio(None) == Decimal("10")

    def test_non_positive_falls_back(self):
        assert resolve_cdr_ratio(Decimal("0")) == Decimal("10")
        assert resolve_cdr_ratio(Decimal("-3")) == Decimal("10")

    def test_explicit_fallback_used_before_constant(self):
        assert resolve_cdr_ratio(None, fallback=Decimal("8")) == Decimal("8")

    def test_non_numeric_falls_back(self):
        assert resolve_cdr_ratio("not-a-number") == Decimal("10")


# ============================================================================
# is_cad_native_source / is_cdr_override
# ============================================================================


class TestCadNativeAndOverride:
    @pytest.mark.parametrize("source", ["yfinance_tor", "cdr_feed"])
    def test_cad_native_sources(self, source):
        assert is_cad_native_source(source, None) is True

    def test_us_source_is_not_native(self):
        assert is_cad_native_source("price_history", None) is False
        assert is_cad_native_source("current_market_data", None) is False

    def test_currency_match_is_native(self):
        assert is_cad_native_source(None, "CAD") is True
        assert is_cad_native_source(None, "cad") is True
        assert is_cad_native_source(None, "USD") is False

    def test_default_account_currency_is_cad(self):
        assert DEFAULT_ACCOUNT_CURRENCY == "CAD"

    def test_override_true_only_for_tor(self):
        assert is_cdr_override("TOR") is True
        assert is_cdr_override("NYSE") is False
        assert is_cdr_override("tor") is False
        assert is_cdr_override(None) is False


# ============================================================================
# Cross-path equivalence — the invariant the redesign exists to enforce
# ============================================================================


class TestCrossPathEquivalence:
    """Snapshot, API and price_utils call sites must produce the same CDR price.

    This is the regression that caused the defect: the same holding valued two
    ways. The FX-bearing sites (snapshot with a rate, API with fx_rate) must match
    each other; price_utils is the documented no-FX surface (native-currency
    display) and must match the ratio-only fallback.
    """

    RAW = Decimal("529.76")
    RATIO = Decimal("12")
    FX = Decimal("1.403")

    def test_snapshot_and_api_agree_with_fx(self):
        from api.portfolio import apply_cdr_adjustment as api_apply

        mock_fx = MagicMock()
        mock_fx.get_rate.return_value = self.FX
        from shared.snapshot_builder import _resolve_holding_price

        snapshot_price, _, _ = _resolve_holding_price(
            company_id=45, symbol="MSFT", avg_cost=None,
            latest_prices={}, price_history={45: [(date(2024, 6, 1), self.RAW)]},
            snapshot_date=date(2024, 6, 1), exchange_override="TOR",
            cdr_ratio=self.RATIO, fx_service=mock_fx,
        )
        api_price = api_apply(
            float(self.RAW), 45, {45: float(self.RATIO)},
            exchange_override="TOR", fx_rate=float(self.FX),
        )
        assert snapshot_price == pytest.approx(Decimal(str(api_price)), abs=Decimal("0.0001"))
        assert snapshot_price == (self.RAW / self.RATIO) * self.FX

    def test_price_utils_matches_ratio_only_fallback(self):
        from shared.price_utils import apply_cdr_adjustment as pu_apply

        price, prev = pu_apply(
            float(self.RAW), float(self.RAW) - 5, 45, {45: float(self.RATIO)}, {45},
        )
        assert price == pytest.approx(float(self.RAW / self.RATIO))
        assert prev == pytest.approx(float((self.RAW - 5) / self.RATIO))

    def test_price_utils_leaves_non_tor_untouched(self):
        from shared.price_utils import apply_cdr_adjustment as pu_apply

        price, prev = pu_apply(100.0, 99.0, 7, {7: 12.0}, set())
        assert (price, prev) == (100.0, 99.0)

    def test_api_rejects_company_keyed_override_map(self):
        from api.portfolio import apply_cdr_adjustment as api_apply

        with pytest.raises(TypeError):
            api_apply(100.0, 45, {45: 10.0}, exchange_override={"45": "TOR"})
