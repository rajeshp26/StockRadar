"""Unit tests for PriceDataProvider symbol resolution."""

from shared.price_data_provider import PriceDataProvider


def test_resolve_symbol_appends_suffix():
    assert PriceDataProvider._resolve_symbol("BCE", "TOR") == "BCE.TO"


def test_resolve_symbol_no_double_suffix():
    """Regression: "BCE.TO" + TOR exchange must not produce "BCE.TO.TO"."""
    assert PriceDataProvider._resolve_symbol("BCE.TO", "TOR") == "BCE.TO"
    assert PriceDataProvider._resolve_symbol("ABC.V", "TSXV") == "ABC.V"


def test_resolve_symbol_without_exchange():
    assert PriceDataProvider._resolve_symbol("aapl") == "AAPL"
