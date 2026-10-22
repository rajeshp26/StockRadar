# application/services/portfolio_response_cache.py
"""
Fingerprint-keyed response cache for /portfolio/performance.

WHY
  A period switch re-issues the whole read and re-derives the series. The period
  selector only changes the visible slice: a 1Y response and an ALL response are
  pure functions of the same stored snapshots plus the resolved date window. So a
  repeat visit to a period can be served from memory at zero DB cost.

CORRECTNESS, NOT JUST SPEED
  A cache that can silently serve stale values is worse than no cache. Two facts
  must hold, and both are enforced by the key rather than by trust:

  1. INPUT IDENTITY — the key carries a fingerprint of the exact snapshot scalars
     the series is derived from (per account, per date, every value column). A
     corrected, backdated or appended snapshot changes the fingerprint, so the
     entry misses. There is no TTL-based staleness window: an entry is valid for
     the inputs it was built from and for no others.

  2. WINDOW IDENTITY — the response depends on today's date, because the period
     window ends at ``now_utc().date()`` (portfolio_service.py:1434). The key
     therefore carries the RESOLVED (start, end) dates, not the period string.
     A request on a later day resolves a later window and misses, so a cached
     response can never outlive the window it was computed for.

WHAT IT DOES NOT CACHE
  Nothing that is not a pure function of the key. If a caller cannot supply a
  fingerprint it does not get a cache, rather than getting a cache keyed on
  something weaker.

The cache is process-local and bounded. It is an optimisation only: every read
and write is exception-guarded, so a failure degrades to the uncached path and
never surfaces as a request error.
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any

from shared.finance_math import build_fingerprint

logger = logging.getLogger(__name__)

# Snapshot scalar columns the performance series is derived from. A change to
# any of these changes the served values, so all of them are fingerprinted.
# This list matches the scalar-only read path
# (PortfolioSnapshotsRepository.get_portfolio_snapshots_series).
_FINGERPRINT_COLUMNS = (
    "account_id",
    "snapshot_date",
    "total_value",
    "holdings_market_value",
    "cost_basis",
    "cash_balance",
    "net_deposits",
    "data_quality_flag",
    "fx_unconverted_count",
)


def compute_snapshot_fingerprint(raw_snapshots: list[dict]) -> str:
    """Fingerprint the snapshot rows a series is derived from.

    Rows are sorted by (account_id, snapshot_date) before hashing so the
    fingerprint is independent of the order the reader returned them in — the
    same rows must not produce two different keys and miss their own entry.
    """
    rows = [{c: s.get(c) for c in _FINGERPRINT_COLUMNS} for s in raw_snapshots]
    rows.sort(key=lambda r: (r["account_id"], r["snapshot_date"]))
    return build_fingerprint({"snapshots": rows})


def compute_cache_key(
    *, account_key: str, period: str, start_date: str, end_date: str,
    snapshot_fingerprint: str,
) -> str:
    """Key a response by account set, resolved window, and input fingerprint."""
    return build_fingerprint({
        "account_key": account_key,
        "period": period.upper(),
        "start_date": start_date,
        "end_date": end_date,
        "snapshot_fingerprint": snapshot_fingerprint,
    })


@dataclass
class _Entry:
    payload: dict[str, Any]
    hits: int = 0


class PortfolioResponseCache:
    """Bounded process-local LRU keyed on input fingerprint + resolved window."""

    def __init__(self, max_entries: int = 256) -> None:
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._lock = Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a deep copy of a cached payload, or None.

        A copy is returned because callers may annotate the dict (the service
        sets ``served_from_cache``); handing out the stored object would let one
        request corrupt another's cached response.
        """
        try:
            with self._lock:
                entry = self._entries.get(key)
                if entry is None:
                    self.misses += 1
                    return None
                self._entries.move_to_end(key)
                entry.hits += 1
                self.hits += 1
                return deepcopy(entry.payload)
        except Exception as e:  # a cache must never fail a request
            logger.info("response cache read failed (%s) — computing live", e)
            return None

    def put(self, key: str, payload: dict[str, Any]) -> None:
        try:
            with self._lock:
                self._entries[key] = _Entry(payload=deepcopy(payload))
                self._entries.move_to_end(key)
                while len(self._entries) > self._max_entries:
                    self._entries.popitem(last=False)
        except Exception as e:
            logger.info("response cache write failed (%s) — value still served", e)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"size": len(self._entries), "hits": self.hits, "misses": self.misses}


# One process-wide cache. Module-level rather than per-service because the
# service is constructed per request, so an instance attribute would be a cache
# with a single-request lifetime.
_portfolio_response_cache = PortfolioResponseCache()


def get_response_cache() -> PortfolioResponseCache:
    return _portfolio_response_cache
