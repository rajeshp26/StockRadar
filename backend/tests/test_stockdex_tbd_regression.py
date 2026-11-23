"""REG-006-STOCKDEX: a Macrotrends `/TBD/` 403 must block that symbol at once.

Observed symptom: repeated
`403 ... https://www.macrotrends.net/stocks/charts/{SYM}/TBD/income-statement`.
`/TBD/` is stockdex's unresolved-slug placeholder: retrying the identical URL
three times (the old generic-403 policy) only generates three guaranteed
failures before blocking. Once seen, the symbol must be blocked immediately.
"""
from __future__ import annotations

from providers.stockdex_provider import StockdexMacrotrendsProvider


def _tbd_error(symbol: str) -> Exception:
    return Exception(
        "HTTP 403 Client Error: Forbidden for url: "
        f"https://www.macrotrends.net/stocks/charts/{symbol}/TBD/income-statement"
    )


def test_tbd_403_blocks_symbol_on_first_occurrence():
    provider = StockdexMacrotrendsProvider()
    assert provider.is_symbol_blocked("AAPL") is False

    provider._handle_fetch_error("AAPL", _tbd_error("AAPL"))

    assert provider.is_symbol_blocked("AAPL") is True


def test_tbd_403_does_not_block_unrelated_symbols():
    provider = StockdexMacrotrendsProvider()
    provider._handle_fetch_error("AAPL", _tbd_error("AAPL"))
    assert provider.is_symbol_blocked("MSFT") is False


def test_generic_403_still_requires_three_failures():
    provider = StockdexMacrotrendsProvider()
    provider._handle_fetch_error("AAPL", Exception("HTTP 403 Forbidden"))
    assert provider.is_symbol_blocked("AAPL") is False
    provider._handle_fetch_error("AAPL", Exception("HTTP 403 Forbidden"))
    provider._handle_fetch_error("AAPL", Exception("HTTP 403 Forbidden"))
    assert provider.is_symbol_blocked("AAPL") is True
