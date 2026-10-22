"""
Tests for the Layer 3 fingerprint-keyed response cache.

Two layers are covered:
  1. The cache module itself (key/fingerprint semantics, deep-copy isolation,
     LRU bound, failure guards).
  2. The service integration: a repeat performance request with unchanged
     snapshots and an unchanged resolved window is served from cache; any
     change to the snapshots or the window recomputes.

The service integration runs the REAL compute path (merge, LOCF, returns) over
mocked repository rows — only the DB boundary and the date window are patched.
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.portfolio_response_cache import (
    PortfolioResponseCache,
    compute_cache_key,
    compute_snapshot_fingerprint,
    get_response_cache,
)
from config import settings


# ── helpers ──────────────────────────────────────────────────────────────

def _row(account_id=1, snapshot_date="2026-01-05", total_value=100_000.0,
         cost_basis=80_000.0, cash_balance=1_000.0, net_deposits=50_000.0,
         data_quality_flag="OK", fx_unconverted_count=0):
    return {
        "account_id": account_id,
        "snapshot_date": snapshot_date,
        "total_value": total_value,
        "holdings_market_value": total_value - cash_balance,
        "cost_basis": cost_basis,
        "cash_balance": cash_balance,
        "net_deposits": net_deposits,
        "data_quality_flag": data_quality_flag,
        "fx_unconverted_count": fx_unconverted_count,
    }


KEY_KW = dict(
    account_key="1,2", period="1Y",
    start_date="2025-01-05", end_date="2026-01-05",
    snapshot_fingerprint="fp",
)


@pytest.fixture(autouse=True)
def _isolated_cache():
    """The response cache is a process-wide singleton; isolate every test."""
    cache = get_response_cache()
    cache.clear()
    cache.hits = 0
    cache.misses = 0
    yield
    cache.clear()


# ── 1. module unit tests ─────────────────────────────────────────────────

class TestCacheBasics:

    def test_round_trip(self):
        cache = PortfolioResponseCache()
        payload = {"period": "1Y", "snapshots": [{"date": "2026-01-05", "value": 1.0}]}
        cache.put("k", payload)
        assert cache.get("k") == payload

    def test_miss_returns_none(self):
        assert PortfolioResponseCache().get("absent") is None

    def test_get_returns_deep_copy(self):
        """A caller mutating its copy must not corrupt the stored entry."""
        cache = PortfolioResponseCache()
        cache.put("k", {"snapshots": [{"value": 1.0}]})
        got = cache.get("k")
        got["snapshots"][0]["value"] = 999.0
        got["served_from_cache"] = True
        assert cache.get("k")["snapshots"][0]["value"] == 1.0
        assert "served_from_cache" not in cache.get("k")

    def test_put_does_not_alias_caller_payload(self):
        """The stored entry must not change if the caller mutates after put."""
        cache = PortfolioResponseCache()
        payload = {"value": 1.0}
        cache.put("k", payload)
        payload["value"] = 999.0
        assert cache.get("k")["value"] == 1.0

    def test_lru_evicts_oldest(self):
        cache = PortfolioResponseCache(max_entries=2)
        cache.put("a", {"n": 1})
        cache.put("b", {"n": 2})
        cache.get("a")          # refresh "a" → "b" becomes the oldest
        cache.put("c", {"n": 3})
        assert cache.get("b") is None
        assert cache.get("a") == {"n": 1}
        assert cache.get("c") == {"n": 3}

    def test_size_and_stats(self):
        cache = PortfolioResponseCache()
        cache.put("a", {})
        cache.get("a")
        cache.get("missing")
        assert cache.size == 1
        assert cache.stats() == {"size": 1, "hits": 1, "misses": 1}

    def test_broken_payload_put_never_raises(self):
        cache = PortfolioResponseCache()

        class Explodes:
            def __deepcopy__(self, memo):
                raise RuntimeError("boom")

        cache.put("k", {"bad": Explodes()})       # guarded
        assert cache.get("k") is None             # nothing poisoned stored

    def test_get_failure_never_raises(self):
        cache = PortfolioResponseCache()
        cache.put("k", {"v": 1})
        with patch("application.services.portfolio_response_cache.deepcopy",
                   side_effect=RuntimeError("boom")):
            assert cache.get("k") is None         # degrades, never surfaces


# ── 2. fingerprint semantics ─────────────────────────────────────────────

class TestSnapshotFingerprint:

    def test_row_order_is_irrelevant(self):
        """The same rows must not miss their own entry over read order."""
        a = [_row(account_id=1), _row(account_id=2, snapshot_date="2026-01-06")]
        b = list(reversed(a))
        assert compute_snapshot_fingerprint(a) == compute_snapshot_fingerprint(b)

    def test_no_rows_is_stable(self):
        assert compute_snapshot_fingerprint([]) == compute_snapshot_fingerprint([])

    @pytest.mark.parametrize("field,value", [
        ("total_value", 100_001.0),
        ("cost_basis", 80_001.0),
        ("cash_balance", 1_001.0),
        ("net_deposits", 50_001.0),
        ("data_quality_flag", "WARN"),
        ("fx_unconverted_count", 2),
    ])
    def test_every_fingerprinted_column_changes_the_key(self, field, value):
        base = compute_snapshot_fingerprint([_row()])
        changed = compute_snapshot_fingerprint([_row(**{field: value})])
        assert base != changed

    def test_appended_snapshot_changes_fingerprint(self):
        before = compute_snapshot_fingerprint([_row()])
        after = compute_snapshot_fingerprint(
            [_row(), _row(snapshot_date="2026-01-06", total_value=101_000.0)]
        )
        assert before != after

    def test_corrected_snapshot_changes_fingerprint(self):
        before = compute_snapshot_fingerprint([_row()])
        after = compute_snapshot_fingerprint([_row(total_value=1.0)])
        assert before != after


# ── 3. cache key semantics ───────────────────────────────────────────────

class TestCacheKey:

    def test_same_inputs_same_key(self):
        assert compute_cache_key(**KEY_KW) == compute_cache_key(**KEY_KW)

    def test_window_identity(self):
        """Same period string, later resolved window → different key.

        The response depends on now_utc().date(); the key must carry the
        resolved dates so a cached response cannot outlive its window.
        """
        later = dict(KEY_KW, end_date="2026-01-06", start_date="2025-01-06")
        assert compute_cache_key(**KEY_KW) != compute_cache_key(**later)

    def test_account_set_changes_key(self):
        assert compute_cache_key(**KEY_KW) != compute_cache_key(
            **dict(KEY_KW, account_key="1"))

    def test_fingerprint_changes_key(self):
        assert compute_cache_key(**KEY_KW) != compute_cache_key(
            **dict(KEY_KW, snapshot_fingerprint="other"))

    def test_period_changes_key(self):
        assert compute_cache_key(**KEY_KW) != compute_cache_key(
            **dict(KEY_KW, period="ALL"))

    def test_period_case_insensitive(self):
        """'1y' and '1Y' are the same period and must share an entry."""
        assert compute_cache_key(**KEY_KW) == compute_cache_key(
            **dict(KEY_KW, period="1y"))


# ── 4. service integration (real compute path) ───────────────────────────

@pytest.fixture
def mock_portfolio_repo():
    repo = MagicMock()
    repo.get_user_accounts.return_value = [
        {"account_id": 1, "account_name": "TFSA", "is_active": True},
        {"account_id": 2, "account_name": "RRSP", "is_active": True},
    ]
    repo.get_earliest_transaction_date.return_value = None
    return repo


@pytest.fixture
def service(mock_portfolio_repo):
    from application.services.portfolio_service import PortfolioService
    return PortfolioService(mock_portfolio_repo, MagicMock())


ROWS = [
    _row(account_id=1, snapshot_date="2026-01-04", total_value=60_000.0, cost_basis=50_000.0),
    _row(account_id=2, snapshot_date="2026-01-04", total_value=40_000.0, cost_basis=30_000.0),
    _row(account_id=1, snapshot_date="2026-01-05", total_value=61_000.0, cost_basis=50_000.0),
    _row(account_id=2, snapshot_date="2026-01-05", total_value=41_000.0, cost_basis=30_000.0),
]


def _run(service, rows, window=(date(2025, 1, 5), date(2026, 1, 5))):
    with patch.object(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True), \
         patch.object(settings, "ENABLE_PORTFOLIO_RESPONSE_CACHE", True), \
         patch.object(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", False), \
         patch.object(settings, "ENABLE_PERFORMANCE_LOCF", True), \
         patch("application.services.portfolio_service.PortfolioSnapshotsRepository") as repo_cls, \
         patch.object(service, "_period_to_date_range", return_value=window):
        repo_cls.return_value.get_first_snapshot_date.return_value = date(2026, 1, 4)
        repo_cls.return_value.get_portfolio_snapshots_series.return_value = rows
        import asyncio
        result = asyncio.run(service.get_portfolio_performance(1, "1Y"))
        calls = repo_cls.return_value.get_portfolio_snapshots_series.call_count
    return result, calls


class TestPerformanceResponseCacheIntegration:
    """Drive the async service from sync tests via asyncio.run (see _run)."""

    def test_second_identical_request_serves_from_cache(
            self, service, mock_portfolio_repo):
        first, first_calls = _run(service, ROWS)
        # The second request still READS the snapshot rows: under the chosen
        # validity model (Option A) the cache key carries their fingerprint,
        # and re-reading them is what makes a corrected snapshot miss instead
        # of serving stale. What the cache saves is the merge, not the read.
        with patch("application.services.portfolio_service.check_snapshot_spike",
                   side_effect=AssertionError("the merge must not re-run")):
            second, second_calls = _run(service, ROWS)

        assert first["served_from_cache"] is False
        assert second["served_from_cache"] is True
        assert (first_calls, second_calls) == (1, 1)
        assert get_response_cache().stats()["hits"] == 1
        # And must be byte-identical in content to the computed response.
        assert second["snapshots"] == first["snapshots"]
        assert second["period"] == first["period"]

    def test_appended_snapshot_invalidates(self, service, mock_portfolio_repo):
        _run(service, ROWS)
        extended = ROWS + [
            _row(account_id=1, snapshot_date="2026-01-06", total_value=62_000.0,
                 cost_basis=50_000.0),
            _row(account_id=2, snapshot_date="2026-01-06", total_value=42_000.0,
                 cost_basis=30_000.0),
        ]
        second, second_calls = _run(service, extended)
        assert second["served_from_cache"] is False
        assert second_calls == 1

    def test_corrected_snapshot_invalidates(self, service, mock_portfolio_repo):
        _run(service, ROWS)
        corrected = [dict(r) for r in ROWS]
        corrected[0]["total_value"] = 59_500.0      # a restated value
        second, second_calls = _run(service, corrected)
        assert second["served_from_cache"] is False
        assert second_calls == 1

    def test_later_resolved_window_invalidates(self, service, mock_portfolio_repo):
        """Same rows and period string; only 'today' moved → must recompute."""
        _run(service, ROWS, window=(date(2025, 1, 5), date(2026, 1, 5)))
        second, second_calls = _run(
            service, ROWS, window=(date(2025, 1, 6), date(2026, 1, 6)))
        assert second["served_from_cache"] is False
        assert second_calls == 1

    def test_different_account_set_not_shared(self, service, mock_portfolio_repo):
        _run(service, ROWS)
        # Restrict to account 1 only: different key, must recompute.
        with patch.object(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True), \
             patch.object(settings, "ENABLE_PORTFOLIO_RESPONSE_CACHE", True), \
             patch.object(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", False), \
             patch("application.services.portfolio_service.PortfolioSnapshotsRepository") as repo_cls, \
             patch.object(service, "_period_to_date_range",
                          return_value=(date(2025, 1, 5), date(2026, 1, 5))):
            repo_cls.return_value.get_first_snapshot_date.return_value = date(2026, 1, 4)
            repo_cls.return_value.get_portfolio_snapshots_series.return_value = [
                r for r in ROWS if r["account_id"] == 1]
            import asyncio
            result = asyncio.run(
                service.get_portfolio_performance(1, "1Y", account_ids=[1]))
        assert result["served_from_cache"] is False

    def test_disabled_by_setting_always_computes(self, service, mock_portfolio_repo):
        import asyncio
        with patch.object(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True), \
             patch.object(settings, "ENABLE_PORTFOLIO_RESPONSE_CACHE", False), \
             patch.object(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", False), \
             patch("application.services.portfolio_service.PortfolioSnapshotsRepository") as repo_cls:
            repo_cls.return_value.get_first_snapshot_date.return_value = date(2026, 1, 4)
            repo_cls.return_value.get_portfolio_snapshots_series.return_value = ROWS
            first = asyncio.run(service.get_portfolio_performance(1, "1Y"))
            second = asyncio.run(service.get_portfolio_performance(1, "1Y"))
        assert "served_from_cache" not in first
        assert "served_from_cache" not in second

    def test_cached_payload_is_isolated_across_requests(
            self, service, mock_portfolio_repo):
        """Annotating one response must not leak into the next hit."""
        first, _ = _run(service, ROWS)
        first["snapshots"].append({"date": "injected", "value": -1})
        second, _ = _run(service, ROWS)
        assert second["served_from_cache"] is True
        assert all(s.get("date") != "injected" for s in second["snapshots"])
