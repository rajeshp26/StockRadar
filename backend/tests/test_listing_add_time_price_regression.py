"""AC-5 secondary regression — add-time price must use the one valuation kernel.

The browser spec exposed a 10x price flip for META/NEO/CDR: immediately after
adding, the card showed the raw provider quote ($29.64); after reload it showed
the effective price ($2.96). Every READ path (structure, /prices, SSE from the
background monitor) applies ``domain.valuation.price_for_listing`` to the raw
quote stored in ``quotes``. The add-time response and the SSE event it broadcasts
were the only path that skipped the kernel.

This test drives the real ``WatchlistService.add_stock_to_watchlist`` method with
a stubbed provider/repository so the defect is caught at the source, not by a
"logic test" that re-implements the division in the test body.
"""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.services.watchlist_service import WatchlistService

META_CDR = {
    "security_id": 3128,
    "company_id": 145,
    "symbol": "META",
    "exchange": "NEO",
    "kind": "CDR",
    "currency": "CAD",
    "provider_symbol": "META.NE",
    "cdr_ratio": 10.0,
    "underlying_security_id": 2833,
}

RAW_PRICE = 29.64
RAW_PREV = 31.54


def _build_service():
    provider = MagicMock()
    provider.get_stock_details.return_value = SimpleNamespace(
        price=RAW_PRICE,
        previous_close=RAW_PREV,
        open_price=None,
        high_price=None,
        low_price=None,
        close_price=RAW_PREV,
        volume=None,
        market_state=None,
    )
    svc = WatchlistService(provider, MagicMock(), MagicMock(), MagicMock())
    svc.financial_repo = MagicMock()
    svc.financial_repo.get_company_refresh_info = AsyncMock(
        return_value=SimpleNamespace(first_financial_data_loaded_at=None)
    )
    return svc


async def test_add_time_cdr_price_is_normalised_by_the_valuation_kernel():
    """The add response (and the SSE event built from it) must show effective price."""
    svc = _build_service()

    with patch.object(
        svc, "_get_or_create_company",
        AsyncMock(return_value={"company_id": 145, "company_name": "Meta Platforms, Inc."}),
    ), patch.object(
        svc, "_update_market_data", new_callable=AsyncMock
    ) as update_market, patch.object(
        svc, "_add_watchlist_item",
        AsyncMock(return_value={"watchlist_item_id": 999}),
    ), patch(
        "application.services.watchlist_service.asyncio.create_task",
        lambda coro: coro.close(),
    ):
        result = await svc.add_stock_to_watchlist(
            user_id=1, symbol="META", watchlist_id=6, security=META_CDR,
        )

    # 1 raw CDR quote / 10 = effective per-underlying price. This is exactly
    # what GET /watchlists/6/structure returns for the same security.
    assert result["current_price"] == pytest.approx(RAW_PRICE / 10)
    assert result["previous_close"] == pytest.approx(RAW_PREV / 10)
    # 2) Change is computed on effective prices, like the structure endpoint.
    assert result["change"] == pytest.approx((RAW_PRICE - RAW_PREV) / 10)

    # 3) The quotes row must keep the RAW provider price. Structure/prices/SSE
    #    apply the ratio on read; dividing here too would double-adjust.
    update_market.assert_awaited_once()
    assert update_market.await_args.args[2] == RAW_PRICE


async def test_add_time_common_price_is_unchanged():
    """A COMMON listing has no ratio, so the kernel must be a no-op."""
    svc = _build_service()
    common = {**META_CDR, "security_id": 2833, "kind": "COMMON",
              "cdr_ratio": None, "provider_symbol": "META"}

    with patch.object(
        svc, "_get_or_create_company",
        AsyncMock(return_value={"company_id": 145, "company_name": "Meta Platforms, Inc."}),
    ), patch.object(svc, "_update_market_data", new_callable=AsyncMock), patch.object(
        svc, "_add_watchlist_item",
        AsyncMock(return_value={"watchlist_item_id": 998}),
    ), patch(
        "application.services.watchlist_service.asyncio.create_task",
        lambda coro: coro.close(),
    ):
        result = await svc.add_stock_to_watchlist(
            user_id=1, symbol="META", watchlist_id=6, security=common,
        )

    assert result["current_price"] == pytest.approx(RAW_PRICE)
    assert result["previous_close"] == pytest.approx(RAW_PREV)
    assert result["change"] == pytest.approx(RAW_PRICE - RAW_PREV)
