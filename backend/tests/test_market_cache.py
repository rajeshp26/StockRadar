"""Unit tests for market_cache.py — TTL cache for current_market_data."""
import pytest
from unittest.mock import MagicMock, patch
import asyncio


def _mock_data(data):
    """Return a mock response with the given data list."""
    m = MagicMock()
    m.data = data
    return m


@pytest.mark.asyncio
async def test_cache_returns_cached_data_within_ttl():
    """Subsequent calls within 30s return cached data without DB hit."""
    from shared.market_cache import get_cached_prices, invalidate_cache

    invalidate_cache()
    db_call_count = 0

    def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        return _mock_data([{"company_id": 1, "current_price": 150.0}])

    with patch("shared.market_cache.supabase") as mock_supa:
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.execute = mock_execute
        mock_supa.table.return_value = mock_table

        # First call — cache miss, hits DB
        result1 = await get_cached_prices([1])
        assert result1 == {1: 150.0}
        assert db_call_count == 1

        # Second call — cache hit, no DB query
        result2 = await get_cached_prices([1])
        assert result2 == {1: 150.0}
        assert db_call_count == 1


@pytest.mark.asyncio
async def test_double_check_pattern_prevents_duplicate_fetch():
    """Two concurrent cache misses result in exactly one DB query."""
    from shared.market_cache import get_cached_prices, invalidate_cache

    invalidate_cache()
    db_call_count = 0

    def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        return _mock_data([{"company_id": 1, "current_price": 150.0}])

    with patch("shared.market_cache.supabase") as mock_supa:
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.execute = mock_execute
        mock_supa.table.return_value = mock_table

        results = await asyncio.gather(
            get_cached_prices([1]),
            get_cached_prices([1]),
        )

        assert db_call_count == 1
        assert results[0] == results[1] == {1: 150.0}


@pytest.mark.asyncio
async def test_cache_returns_only_requested_ids():
    """Cache returns only the IDs requested, not the full cached set."""
    from shared.market_cache import get_cached_prices, invalidate_cache

    invalidate_cache()

    def mock_execute(*args, **kwargs):
        return _mock_data([
            {"company_id": 1, "current_price": 100.0},
            {"company_id": 2, "current_price": 200.0},
            {"company_id": 3, "current_price": 300.0},
        ])

    with patch("shared.market_cache.supabase") as mock_supa:
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.execute = mock_execute
        mock_supa.table.return_value = mock_table

        result = await get_cached_prices([1, 3])
        assert result == {1: 100.0, 3: 300.0}
        assert 2 not in result


@pytest.mark.asyncio
async def test_cache_handles_empty_response():
    """DB returns empty — cache keeps stale data."""
    from shared.market_cache import get_cached_prices, invalidate_cache

    invalidate_cache()

    def mock_execute_ok(*args, **kwargs):
        return _mock_data([{"company_id": 1, "current_price": 150.0}])

    with patch("shared.market_cache.supabase") as mock_supa:
        mock_table = MagicMock()
        mock_table.select.return_value = mock_table
        mock_table.execute = mock_execute_ok
        mock_supa.table.return_value = mock_table

        result = await get_cached_prices([1])
        assert result == {1: 150.0}

    # Fast-forward past TTL by patching market_cache's time.time
    import shared.market_cache as mc

    orig_time = mc.time.time
    try:
        mc.time.time = lambda: orig_time() + 31

        def mock_execute_empty(*args, **kwargs):
            return _mock_data([])

        with patch("shared.market_cache.supabase") as mock_supa2:
            mock_table2 = MagicMock()
            mock_table2.select.return_value = mock_table2
            mock_table2.execute = mock_execute_empty
            mock_supa2.table.return_value = mock_table2

            result = await get_cached_prices([1])
            assert result == {}
    finally:
        mc.time.time = orig_time


@pytest.mark.asyncio
async def test_cache_empty_company_ids():
    """Empty company_ids returns empty dict, no DB query."""
    from shared.market_cache import get_cached_prices

    with patch("shared.market_cache.supabase") as mock_supa:
        result = await get_cached_prices([])
        assert result == {}
        mock_supa.table.assert_not_called()
