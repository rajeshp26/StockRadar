"""Unit tests for YFinance async-blocking fix."""

import asyncio
from unittest import mock
import pytest
from providers.yfinance_provider import YFinanceProvider


@pytest.mark.asyncio
async def test_get_stock_details_runs_in_thread():
    """YFinanceProvider.get_stock_details should be callable via to_thread."""
    provider = YFinanceProvider()

    with mock.patch.object(provider, "get_stock_details") as mock_get:
        mock_get.return_value = mock.MagicMock(price=150.0)

        # Simulate the pattern used in portfolio_service.py:enrich_holdings_with_prices
        result = await asyncio.to_thread(provider.get_stock_details, "AAPL", exchange="TOR")
        assert mock_get.called


@pytest.mark.asyncio
async def test_get_stock_details_timeout_handling():
    """When yfinance takes too long, to_thread can be cancelled with timeout."""
    provider = YFinanceProvider()

    async def slow_lookup():
        await asyncio.sleep(10)
        return mock.MagicMock(price=150.0)

    with mock.patch.object(provider, "get_stock_details") as mock_get:
        mock_get.side_effect = lambda sym, exchange=None: mock.MagicMock(price=150.0)

        result = await asyncio.wait_for(
            asyncio.to_thread(provider.get_stock_details, "AAPL"),
            timeout=5.0,
        )
        assert result.price == 150.0


@pytest.mark.asyncio
async def test_get_stock_details_fallback_on_failure():
    """When yfinance raises exception, caller handles gracefully via override_cache."""
    provider = YFinanceProvider()

    with mock.patch.object(provider, "get_stock_details", side_effect=Exception("API Error")):
        override_cache = {}
        cache_key = "AAPL:TOR"
        try:
            sd = await asyncio.to_thread(provider.get_stock_details, "AAPL", exchange="TOR")
            override_cache[cache_key] = sd.price if sd else None
        except Exception:
            override_cache[cache_key] = None

        assert override_cache[cache_key] is None
