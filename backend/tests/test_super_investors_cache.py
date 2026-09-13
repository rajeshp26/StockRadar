"""Super-investors read cache: TTL, eviction, invalidation."""

import time

from application.services.super_investors_cache import (
    SuperInvestorsCache,
    invalidate_super_investors_cache,
)


def test_get_returns_none_for_unknown_ticker():
    cache = SuperInvestorsCache()
    assert cache.get("ZZZZ") is None


def test_set_then_get_roundtrip_is_case_insensitive():
    cache = SuperInvestorsCache()
    cache.set("msft", {"ticker": "MSFT", "overlap_count": 2})
    assert cache.get("MSFT") == {"ticker": "MSFT", "overlap_count": 2}
    assert cache.get("msft") == {"ticker": "MSFT", "overlap_count": 2}


def test_expired_entry_is_not_returned():
    cache = SuperInvestorsCache(ttl_seconds=0.05)
    cache.set("MSFT", {"ticker": "MSFT"})
    assert cache.get("MSFT") is not None
    time.sleep(0.06)
    assert cache.get("MSFT") is None


def test_invalidate_clears_store():
    cache = SuperInvestorsCache()
    cache.set("MSFT", {"ticker": "MSFT"})
    cache.set("NVDA", {"ticker": "NVDA"})
    cache.invalidate()
    assert cache.size == 0
    assert cache.get("MSFT") is None


def test_eviction_drops_oldest_when_full():
    cache = SuperInvestorsCache(ttl_seconds=60, max_entries=2)
    cache.set("MSFT", {"n": 1})
    cache.set("NVDA", {"n": 2})
    cache.set("TSLA", {"n": 3})
    assert cache.size == 2
    assert cache.get("MSFT") is None
    assert cache.get("NVDA") == {"n": 2}
    assert cache.get("TSLA") == {"n": 3}


def test_module_level_invalidation_clears_singleton():
    from application.services.super_investors_cache import get_super_investors_cache

    cache = get_super_investors_cache()
    cache.set("MSFT", {"ticker": "MSFT"})
    invalidate_super_investors_cache()
    assert cache.size == 0