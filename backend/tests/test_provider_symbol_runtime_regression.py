"""The doubled-suffix defect at the runtime boundary, not just in the SQL text.

The real catalog still served ``T.TO.TO`` to the live price monitor after the
migration text was written. These tests drive the exact boundaries that emit the
provider symbol, using the seven rows captured by the rollback-only DB probe as
an independent hand-derived oracle (the catalog's correct symbol is the ``symbol``
column itself).
"""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main
from domain.listing_identity import (
    ListingIdentityError,
    normalize_provider_symbol,
)
from domain.provider_resilience import ListingRateLimitBreaker, refresh_listing
from main import _YFinanceQuoteAdapter

# Oracle: (security_id, symbol, exchange, bad provider_symbol) from the live probe.
KNOWN_BAD_ROWS = [
    (9, "YTSL.NE", "NEO", "YTSL.NE.NE"),
    (123, "ENB.TO", "TSX", "ENB.TO.TO"),
    (634, "PZA.TO", "TSX", "PZA.TO.TO"),
    (2605, "T.TO", "TSX", "T.TO.TO"),
    (3006, "BCE.TO", "TSX", "BCE.TO.TO"),
    (3010, "CU.TO", "TSX", "CU.TO.TO"),
    (3115, "GSY.TO", "TSX", "GSY.TO.TO"),
]


class _RecordingProvider:
    def __init__(self):
        self.calls: list[str] = []

    def get_quote(self, provider_symbol: str) -> dict:
        self.calls.append(provider_symbol)
        return {"price": 1.0, "previous_close": 1.0}


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("T.TO.TO", "T.TO"),
        ("YTSL.NE.NE", "YTSL.NE"),
        ("ABC.V.V.V", "ABC.V"),
        ("ENB.TO", "ENB.TO"),
        ("META.NE", "META.NE"),
        ("BRK.B", "BRK.B"),
        ("ABC.TO.V", "ABC.TO.V"),
        ("aapl", "AAPL"),
        (" bce.tO ", "BCE.TO"),
    ],
)
def test_normalize_provider_symbol_only_collapses_repeated_suffix(raw, expected):
    """Genuine dotted tickers survive; only an identical repeated suffix folds."""
    assert normalize_provider_symbol(raw) == expected
    assert normalize_provider_symbol(expected) == expected


def test_normalize_provider_symbol_rejects_invalid_ticker():
    with pytest.raises(ListingIdentityError):
        normalize_provider_symbol("T$T.O")


@pytest.mark.parametrize(
    "security_id,symbol,exchange,bad",
    KNOWN_BAD_ROWS,
    ids=[f"security-{row[0]}" for row in KNOWN_BAD_ROWS],
)
def test_quote_adapter_never_sends_doubled_suffix_to_yahoo(
    security_id, symbol, exchange, bad
):
    """A stale catalog row must not reach Yahoo as an invalid ticker."""
    fake_ticker = MagicMock()
    fake_ticker.info = {
        "currentPrice": 1.0,
        "regularMarketPreviousClose": 1.0,
    }
    with patch("main.yf.Ticker", return_value=fake_ticker) as ticker:
        _YFinanceQuoteAdapter().get_quote(bad)

    ticker.assert_called_once_with(symbol)


@pytest.mark.parametrize(
    "security_id,symbol,exchange,bad",
    KNOWN_BAD_ROWS,
    ids=[f"security-{row[0]}" for row in KNOWN_BAD_ROWS],
)
def test_refresh_listing_uses_canonical_symbol_from_stale_catalog_row(
    security_id, symbol, exchange, bad
):
    """The refresh result identity must be canonical, not the stale DB value."""
    provider = _RecordingProvider()
    security = {
        "security_id": security_id,
        "symbol": symbol,
        "exchange": exchange,
        "kind": "COMMON",
        "currency": "CAD",
        "provider_symbol": bad,
    }

    result = refresh_listing(provider, security, ListingRateLimitBreaker())

    assert provider.calls == [symbol]
    assert result.provider_symbol == symbol


async def _run_one_monitor_cycle(
    stale_security: dict, provider: _RecordingProvider, writes: list,
    *, disable_guard: bool = False,
):
    """Run exactly one price-monitor cycle against a stale catalog row."""
    class _Catalog:
        def list_securities_for_symbol(self, sym):
            return [dict(stale_security)] if sym == stale_security["symbol"] else []

        def upsert_quote(self, security_id, payload):
            writes.append((security_id, payload))

    broadcast = AsyncMock()

    async def _stop_after_one_cycle(_seconds):
        raise asyncio.CancelledError

    with ExitStack() as stack:
        stack.enter_context(
            patch("api.watchlists.symbol_subscribers",
                  {stale_security["symbol"]: {"user-1"}})
        )
        stack.enter_context(
            patch("api.watchlists.broadcast_stock_update", broadcast)
        )
        stack.enter_context(
            patch(
                "infrastructure.repositories.security_repository.SecurityRepository",
                _Catalog,
            )
        )
        stack.enter_context(
            patch("main._YFinanceQuoteAdapter", return_value=provider)
        )
        stack.enter_context(
            patch(
                "domain.valuation.price_for_listing",
                side_effect=lambda _security, price: (price, "CAD"),
            )
        )
        stack.enter_context(patch("main.asyncio.sleep", new=_stop_after_one_cycle))
        stack.enter_context(patch.object(main, "_price_monitor_breaker", None))
        stack.enter_context(
            patch.object(main, "_price_monitor_provider_breaker", None)
        )
        if disable_guard:
            # Durable mutation proof: remove only the guard, keep everything
            # else, and confirm the defect signature reappears.
            def identity(value):
                return value

            stack.enter_context(
                patch("main.normalize_provider_symbol", side_effect=identity)
            )
            stack.enter_context(
                patch("domain.provider_resilience.normalize_provider_symbol",
                      side_effect=identity)
            )
        await main.background_price_monitor()

    return broadcast


_STALE_T = {
    "security_id": 2605,
    "symbol": "T.TO",
    "exchange": "TSX",
    "kind": "COMMON",
    "currency": "CAD",
    "provider_symbol": "T.TO.TO",
}


async def test_price_monitor_loop_never_emits_doubled_symbol():
    """Drive the real monitor loop with a stale catalog row (the logged failure).

    The single request, the quote write and the SSE identity must all carry the
    canonical ticker; a doubled value escaping via any one of them is the defect
    the user reported.
    """
    provider = _RecordingProvider()
    writes: list[tuple] = []

    broadcast = await _run_one_monitor_cycle(_STALE_T, provider, writes)

    assert provider.calls == ["T.TO"]
    assert writes and all(sid == 2605 for sid, _ in writes)
    broadcast.assert_awaited_once()
    assert broadcast.await_args.args[0] == "T.TO"
    assert broadcast.await_args.kwargs["identity"]["provider_symbol"] == "T.TO"


async def test_monitor_loop_test_detects_defect_when_guard_is_removed():
    """Permanent red evidence: without the guard, T.TO.TO reaches the provider.

    This test passes only while the regression test above is capable of failing
    on the original defect. It is the in-repo replacement for a temp diagnostic.
    """
    provider = _RecordingProvider()
    writes: list[tuple] = []

    await _run_one_monitor_cycle(_STALE_T, provider, writes, disable_guard=True)

    assert provider.calls == ["T.TO.TO"]
