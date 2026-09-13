"""In-process TTL cache for super-investor read payloads.

13F data changes at most quarterly; the per-ticker read payload is a pure
function of (ticker, latest-quarter holdings). An in-process TTL cache serves
repeat reads in ~0ms and keeps the API off the database on hot paths.

Coherence: the data source (the scheduler worker) runs in a separate OS
process, so cross-process invalidation is best-effort only — the TTL is the
authoritative coherence mechanism. Redis becomes the upgrade path when the
API runs more than one replica.
"""

import threading
import time
from typing import Any

from config import settings

_DEFAULT_TTL_SECONDS = getattr(settings, "SUPER_INVESTORS_CACHE_TTL_SECONDS", 900)
_DEFAULT_MAX_ENTRIES = getattr(settings, "SUPER_INVESTORS_CACHE_MAX_ENTRIES", 512)


class SuperInvestorsCache:
    """Thread-safe TTL dict keyed by uppercase ticker symbol."""

    def __init__(self, ttl_seconds: float = _DEFAULT_TTL_SECONDS, max_entries: int = _DEFAULT_MAX_ENTRIES):
        self._ttl = ttl_seconds
        self._max = max_entries
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, ticker: str) -> Any | None:
        key = ticker.upper()
        with self._lock:
            item = self._store.get(key)
        if item is None:
            return None
        expires_at, payload = item
        if time.monotonic() > expires_at:
            with self._lock:
                self._store.pop(key, None)
            return None
        return payload

    def set(self, ticker: str, payload: Any) -> None:
        key = ticker.upper()
        with self._lock:
            if len(self._store) >= self._max and key not in self._store:
                self._evict_locked()
            self._store[key] = (time.monotonic() + self._ttl, payload)

    def invalidate(self) -> None:
        with self._lock:
            self._store.clear()

    def _evict_locked(self) -> None:
        now = time.monotonic()
        stale = [k for k, (exp, _) in self._store.items() if exp <= now]
        for k in stale:
            self._store.pop(k, None)
        if len(self._store) >= self._max:
            oldest = min(self._store.items(), key=lambda kv: kv[1][0])
            self._store.pop(oldest[0], None)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._store)


_super_investors_cache = SuperInvestorsCache()


def get_super_investors_cache() -> SuperInvestorsCache:
    return _super_investors_cache


def invalidate_super_investors_cache() -> None:
    _super_investors_cache.invalidate()