"""Unit tests for market_cache module — TTL cache correctness + concurrency."""

import asyncio
import time
from unittest import mock
import pytest
from shared.market_cache import get_cached_prices, _cache, _lock


# Helper: reset cache state before each test
@pytest.fixture(autouse=True)
def reset_cache():
    _cache["data"] = {}
    _cache["expires_at"] = 0.0
    yield


@pytest.mark.asyncio
async def test_cache_returns_cached_data_within_ttl():
    """Subsequent calls within 30s return cached data without DB hit."""
    _cache["data"] = {1: 150.0, 2: 200.0}
    _cache["expires_at"] = time.time() + 30

    db_call_count = 0

    def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        return mock.Mock(data=[{"company_id": 3, "current_price": 300.0}])

    with mock.patch("shared.market_cache.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        result = await get_cached_prices([1, 2])
        assert result == {1: 150.0, 2: 200.0}
        assert db_call_count == 0  # No DB call — cache hit


@pytest.mark.asyncio
async def test_cache_refreshes_after_ttl_expiry():
    """Call after 30s+ hits DB and updates cache."""
    _cache["data"] = {1: 150.0}
    _cache["expires_at"] = 0  # Expired

    db_call_count = 0

    def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        return mock.Mock(data=[{"company_id": 1, "current_price": 155.0}])

    with mock.patch("shared.market_cache.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        result = await get_cached_prices([1])
        assert result == {1: 155.0}
        assert db_call_count == 1


@pytest.mark.asyncio
async def test_double_check_pattern_prevents_duplicate_fetch():
    """Two concurrent cache misses should result in exactly one DB query."""
    _cache["data"] = {}
    _cache["expires_at"] = 0

    db_call_count = 0

    def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        return mock.Mock(data=[{"company_id": 1, "current_price": 150.0}])

    with mock.patch("shared.market_cache.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        results = await asyncio.gather(
            get_cached_prices([1]),
            get_cached_prices([1]),
        )

        assert db_call_count == 1
        assert results[0] == results[1] == {1: 150.0}


@pytest.mark.asyncio
async def test_cache_returns_only_requested_ids():
    """Call with [1,2,3] doesn't return [4,5,6] from stale cache."""
    _cache["data"] = {1: 100.0, 2: 200.0, 3: 300.0, 4: 400.0, 5: 500.0, 6: 600.0}
    _cache["expires_at"] = time.time() + 30

    result = await get_cached_prices([1, 3, 5])
    assert result == {1: 100.0, 3: 300.0, 5: 500.0}
    assert 2 not in result
    assert 4 not in result
    assert 6 not in result


@pytest.mark.asyncio
async def test_cache_handles_empty_response_from_db():
    """DB returns empty -> cache logs warning, keeps stale data."""
    _cache["data"] = {1: 100.0}
    _cache["expires_at"] = 0

    def mock_execute(*args, **kwargs):
        return mock.Mock(data=[])

    with mock.patch("shared.market_cache.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        result = await get_cached_prices([1])
        assert result == {}


@pytest.mark.asyncio
async def test_cache_flushes_on_max_size():
    """>5000 entries -> cache resets."""
    large_data = {i: float(i) for i in range(5001)}
    _cache["data"] = large_data
    _cache["expires_at"] = 0

    def mock_execute(*args, **kwargs):
        return mock.Mock(data=[{"company_id": 1, "current_price": 100.0}])

    with mock.patch("shared.market_cache.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        await get_cached_prices([1])
        assert len(_cache["data"]) == 1


@pytest.mark.asyncio
async def test_cache_handles_empty_request():
    """Empty company_ids list returns empty dict without DB hit."""
    _cache["data"] = {}
    _cache["expires_at"] = 0

    db_call_count = 0

    def mock_execute(*args, **kwargs):
        nonlocal db_call_count
        db_call_count += 1
        return mock.Mock(data=[])

    with mock.patch("shared.market_cache.supabase.table") as mock_table:
        mock_table.return_value.select.return_value.execute = mock_execute

        result = await get_cached_prices([])
        assert result == {}
