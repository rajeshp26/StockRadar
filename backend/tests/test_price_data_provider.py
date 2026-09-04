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


def test_resolve_symbol_neo_suffix():
    """NEO Exchange uses .NE suffix in yfinance (e.g. YTSL.NE)."""
    assert PriceDataProvider._resolve_symbol("YTSL", "NEO") == "YTSL.NE"
    assert PriceDataProvider._resolve_symbol("YTSL.NE", "NEO") == "YTSL.NE"


def test_resolve_symbol_all_canadian_suffixes():
    """The six Canadian exchanges must map to yfinance-compatible suffixes."""
    assert PriceDataProvider._resolve_symbol("BEP-UN", "TOR") == "BEP-UN.TO"
    assert PriceDataProvider._resolve_symbol("ETHY", "TSX") == "ETHY.TO"
    assert PriceDataProvider._resolve_symbol("XXXX", "VAN") == "XXXX.V"
    assert PriceDataProvider._resolve_symbol("XXXX", "CNQ") == "XXXX.V"
