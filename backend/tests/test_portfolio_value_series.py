"""
Tests for the Layer 4 materialised portfolio value series (migration 017).

The requirement these protect (same standard as the benchmark series):

    The stored curve must be computed once and stored, and a reused curve must
    return EXACTLY the dollars, metrics and quality metadata the live merge
    would. A store that can serve a stale dollar is worse than no store.

Option A validity model (the one this code implements): the stored build is
keyed on an INPUT fingerprint - a hash of the per-account snapshot scalar rows
the request path reads anyway - so every request re-verifies the store against
the live snapshot table before serving a single stored point. An appended,
corrected or BACKDATED snapshot changes the hash and forces a rebuild; there is
no staleness window and no background job in the loop.

Two layers are covered separately:

* ``PortfolioValueSeriesGuard`` - the reuse/rebuild decision, pure function.
* ``PortfolioService.get_portfolio_performance`` integration - a fake store
  plus the REAL merge, asserting hit, miss, correction and weekend behaviour.
"""
import asyncio
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from application.services.portfolio_service import PortfolioService
from application.services.portfolio_value_series_guard import (
    FINGERPRINT_MATCH,
    FINGERPRINT_MISMATCH,
    NO_PRIOR_SERIES,
    SERIES_ENDS_BEFORE,
    PortfolioValueSeriesGuard,
    compute_portfolio_series_fingerprint,
)
from config import settings
from infrastructure.repositories.portfolio_value_series_repository import (
    StoredPortfolioSeries,
)


def _row(account_id, snapshot_date, total_value, cost_basis=80_000.0,
         cash_balance=1_000.0, net_deposits=50_000.0, quality="OK", fx=0):
    return {
        "account_id": account_id,
        "snapshot_date": snapshot_date,
        "total_value": total_value,
        "holdings_market_value": total_value - cash_balance,
        "cost_basis": cost_basis,
        "cash_balance": cash_balance,
        "net_deposits": net_deposits,
        "data_quality_flag": quality,
        "fx_unconverted_count": fx,
    }


class FakeValueSeriesStore:
    """In-memory stand-in for PortfolioValueSeriesRepository."""

    def __init__(self):
        self.points: list[dict] = []
        self.fingerprint: str | None = None
        self.last_mark_date: date | None = None
        self.upsert_calls = 0
        self.get_calls = 0

    def get_series(self, account_key, start_date=None, end_date=None):
        self.get_calls += 1
        if self.fingerprint is None:
            return StoredPortfolioSeries()
        return StoredPortfolioSeries(
            fingerprint=self.fingerprint,
            last_mark_date=self.last_mark_date,
            computed_at=None,
            points=[dict(p) for p in self.points],
        )

    def upsert_points(self, account_key, points, fingerprint, last_mark_date):
        self.points = [dict(p) for p in points]
        self.fingerprint = fingerprint
        self.last_mark_date = last_mark_date
        self.upsert_calls += 1
        return len(points)


# ── Guard: pure decision cases ───────────────────────────────────────────────

class TestGuardDecisions:
    def test_no_stored_series_rebuilds(self):
        d = PortfolioValueSeriesGuard().decide(
            stored_fingerprint=None, stored_last_mark=None,
            expected_fingerprint="abc", required_end=date(2026, 10, 21),
        )
        assert d.rebuild and not d.can_reuse
        assert d.reason == NO_PRIOR_SERIES and d.gate == 1

    def test_input_change_rebuilds(self):
        """Same coverage, different snapshot inputs => stored dollars are wrong."""
        d = PortfolioValueSeriesGuard().decide(
            stored_fingerprint="old", stored_last_mark=date(2026, 10, 21),
            expected_fingerprint="new", required_end=date(2026, 10, 21),
        )
        assert d.rebuild and not d.can_reuse
        assert d.reason == FINGERPRINT_MISMATCH and d.gate == 2

    def test_covered_and_matching_reuses_with_nothing_to_compute(self):
        d = PortfolioValueSeriesGuard().decide(
            stored_fingerprint="same", stored_last_mark=date(2026, 10, 21),
            expected_fingerprint="same", required_end=date(2026, 10, 21),
        )
        assert d.can_reuse and not d.rebuild and not d.must_compute
        assert d.reason == FINGERPRINT_MATCH

    def test_window_advanced_without_new_inputs_reuses(self):
        """Weekend: window end moved, no new snapshots -> still reusable."""
        d = PortfolioValueSeriesGuard().decide(
            stored_fingerprint="same", stored_last_mark=date(2026, 10, 19),
            expected_fingerprint="same", required_end=date(2026, 10, 21),
        )
        assert d.can_reuse and not d.rebuild
        assert d.compute_from == date(2026, 10, 19)
        assert d.reason == SERIES_ENDS_BEFORE


# ── Input fingerprint: sensitive to every edit that moves a dollar ───────────

class TestSeriesFingerprint:
    ROWS = [
        _row(1, "2026-01-04", 60_000.0),
        _row(2, "2026-01-04", 40_000.0),
        _row(1, "2026-01-05", 61_000.0),
    ]

    def test_stable_for_same_inputs(self):
        a = compute_portfolio_series_fingerprint("1,2", self.ROWS)
        b = compute_portfolio_series_fingerprint("1,2", [dict(r) for r in self.ROWS])
        assert a == b

    def test_row_order_is_irrelevant(self):
        assert (compute_portfolio_series_fingerprint("1,2", self.ROWS)
                == compute_portfolio_series_fingerprint("1,2", list(reversed(self.ROWS))))

    def test_backdated_correction_changes_fingerprint(self):
        """The class of change a timestamp check cannot see: an OLD row edited."""
        corrected = [dict(r) for r in self.ROWS]
        corrected[0]["total_value"] = 59_500.0
        assert (compute_portfolio_series_fingerprint("1,2", self.ROWS)
                != compute_portfolio_series_fingerprint("1,2", corrected))

    def test_backdated_append_changes_fingerprint(self):
        appended = self.ROWS + [_row(2, "2026-01-03", 39_000.0)]
        assert (compute_portfolio_series_fingerprint("1,2", self.ROWS)
                != compute_portfolio_series_fingerprint("1,2", appended))

    def test_account_key_is_part_of_identity(self):
        assert (compute_portfolio_series_fingerprint("1,2", self.ROWS)
                != compute_portfolio_series_fingerprint("1", self.ROWS))


# ── Integration: a served curve equals the live merge, byte for byte ─────────

# A LOCF gap on 2026-01-05 (account 2 has no row that day).
GAP_ROWS = [
    _row(1, "2026-01-04", 60_000.0, cost_basis=50_000.0),
    _row(2, "2026-01-04", 40_000.0, cost_basis=30_000.0),
    _row(1, "2026-01-05", 61_000.0, cost_basis=50_000.0),
    _row(1, "2026-01-06", 62_000.0, cost_basis=50_000.0),
    _row(2, "2026-01-06", 42_000.0, cost_basis=30_000.0),
]

# A 250% step on 2026-01-05 with a LOCF gap: the merge must suppress it as an
# artifact and report spike_detected=True - and a served curve must report the
# same, which is only possible because the flag is persisted per point.
SPIKE_ROWS = [
    _row(1, "2026-01-04", 50_000.0, cost_basis=40_000.0, net_deposits=40_000.0),
    _row(2, "2026-01-04", 50_000.0, cost_basis=40_000.0, net_deposits=40_000.0),
    _row(1, "2026-01-05", 200_000.0, cost_basis=40_000.0, net_deposits=40_000.0),
    _row(1, "2026-01-06", 55_000.0, cost_basis=40_000.0, net_deposits=40_000.0),
    _row(2, "2026-01-06", 50_000.0, cost_basis=40_000.0, net_deposits=40_000.0),
]

WINDOW = (date(2026, 1, 4), date(2026, 1, 6))


def _service():
    repo = MagicMock()
    repo.get_user_accounts.return_value = [
        {"account_id": 1, "account_name": "TFSA", "is_active": True},
        {"account_id": 2, "account_name": "RRSP", "is_active": True},
    ]
    repo.get_earliest_transaction_date.return_value = None
    return PortfolioService(repo, MagicMock())


def _run(svc, rows, store, period="1Y", window=WINDOW, enabled=True,
         cache_enabled=False):
    with patch.object(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True), \
         patch.object(settings, "ENABLE_PORTFOLIO_RESPONSE_CACHE", cache_enabled), \
         patch.object(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", enabled), \
         patch.object(settings, "ENABLE_PERFORMANCE_LOCF", True), \
         patch("application.services.portfolio_service.PortfolioSnapshotsRepository") as repo_cls, \
         patch("application.services.portfolio_service.PortfolioValueSeriesRepository",
               return_value=store), \
         patch.object(svc, "_period_to_date_range", return_value=window):
        repo_cls.return_value.get_first_snapshot_date.return_value = date(2026, 1, 4)
        repo_cls.return_value.get_portfolio_snapshots_series.return_value = rows
        return asyncio.run(svc.get_portfolio_performance(1, period))


def _live_only(svc, rows, period="1Y", window=WINDOW):
    """Run the same request with the series layer fully disabled."""
    return _run(svc, rows, FakeValueSeriesStore(), period, window, enabled=False)


class TestValueSeriesPathEquivalence:

    def test_cold_then_warm_returns_identical_payload(self):
        """The unit of the change: a stored curve is worth storing."""
        svc = _service()
        store = FakeValueSeriesStore()

        cold = _run(svc, GAP_ROWS, store)
        assert store.upsert_calls == 1, "a cold miss must write the series"

        warm = _run(svc, GAP_ROWS, store)
        assert store.upsert_calls == 1, "a hit must not rewrite the series"

        assert warm == cold, "a served response must equal the computed one"
        assert warm["locf_count"] == cold["locf_count"] == 1
        assert warm["snapshots"] == cold["snapshots"]
        for key in ("total_return", "twr_pct", "mwr_pct", "cagr_pct",
                    "best_day", "worst_day"):
            assert warm[key] == cold[key], key

    def test_warm_hit_does_not_run_the_merge(self):
        """A valid stored curve must not re-enter the merge at all."""
        svc = _service()
        store = FakeValueSeriesStore()
        _run(svc, GAP_ROWS, store)

        with patch("application.services.portfolio_service.check_snapshot_spike",
                   side_effect=AssertionError("merge must not run on a hit")):
            warm = _run(svc, GAP_ROWS, store)
        assert warm["success"]

    def test_spike_metadata_survives_the_store(self):
        """The merge's suppression decision must be reported identically served."""
        svc = _service()
        store = FakeValueSeriesStore()

        cold = _run(svc, SPIKE_ROWS, store)
        warm = _run(svc, SPIKE_ROWS, store)

        assert cold["spike_detected"] is True, "test data must actually spike"
        assert warm["spike_detected"] is True
        assert warm["locf_count"] == cold["locf_count"]
        assert warm["snapshots"] == cold["snapshots"]

    def test_corrected_snapshot_rebuilds_and_serves_new_dollars(self):
        """Option A's headline: a backdated correction is never served stale."""
        svc = _service()
        store = FakeValueSeriesStore()
        first = _run(svc, GAP_ROWS, store)

        corrected = [dict(r) for r in GAP_ROWS]
        corrected[0]["total_value"] = 55_000.0     # restated an OLD date
        second = _run(svc, corrected, store)

        assert store.upsert_calls == 2, "a corrected input must rebuild"
        assert second["snapshots"] != first["snapshots"]
        assert second["total_return"] != first["total_return"]

    def test_appended_backdated_snapshot_rebuilds(self):
        svc = _service()
        store = FakeValueSeriesStore()
        _run(svc, GAP_ROWS, store)

        earlier = [_row(1, "2026-01-03", 58_000.0, cost_basis=50_000.0)] + GAP_ROWS
        second = _run(svc, earlier, store)
        assert store.upsert_calls == 2, "an older row must invalidate the build"
        # The backdated row predates the response window, so it must not appear
        # in the served slice - but it MUST be part of the rebuilt curve.
        assert second["snapshots"][0]["date"] == "2026-01-04"
        assert store.points[0]["date"] == "2026-01-03"

    def test_new_day_extends_the_curve(self):
        svc = _service()
        store = FakeValueSeriesStore()
        _run(svc, GAP_ROWS, store)

        extended = GAP_ROWS + [
            _row(1, "2026-01-07", 63_000.0, cost_basis=50_000.0),
            _row(2, "2026-01-07", 43_000.0, cost_basis=30_000.0),
        ]
        later = _run(svc, extended, store,
                     window=(date(2026, 1, 4), date(2026, 1, 7)))
        assert store.upsert_calls == 2
        assert store.last_mark_date == date(2026, 1, 7)
        assert later["snapshots"][-1]["date"] == "2026-01-07"

    def test_weekend_window_move_serves_from_store(self):
        """Window end moved, inputs unchanged: slice the store, no rewrite."""
        svc = _service()
        store = FakeValueSeriesStore()
        first = _run(svc, GAP_ROWS, store)

        weekend = _run(svc, GAP_ROWS, store, window=(date(2026, 1, 4), date(2026, 1, 8)))
        assert store.upsert_calls == 1, "no new inputs must mean no rewrite"
        assert weekend["snapshots"] == first["snapshots"]

    def test_period_switch_is_a_slice_of_the_same_build(self):
        """Different period, same inputs: identical dollars on shared dates."""
        svc = _service()
        store = FakeValueSeriesStore()
        one_year = _run(svc, GAP_ROWS, store, period="1Y")
        five_year = _run(svc, GAP_ROWS, store, period="5Y")
        assert store.upsert_calls == 1

        # And each served period equals what the live path would compute.
        live_5y = _live_only(svc, GAP_ROWS, period="5Y")
        assert five_year["snapshots"] == live_5y["snapshots"]
        assert five_year["twr_pct"] == live_5y["twr_pct"]
        assert one_year["twr_pct"] == live_5y["twr_pct"], (
            "same window and daily series => same TWR regardless of label"
        )

    def test_store_failure_degrades_to_live_compute(self):
        """A missing or broken store must not break the request."""
        svc = _service()
        broken = MagicMock()
        broken.get_series.side_effect = Exception("relation does not exist")
        broken.upsert_points.side_effect = Exception("relation does not exist")

        with patch.object(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True), \
             patch.object(settings, "ENABLE_PORTFOLIO_RESPONSE_CACHE", False), \
             patch.object(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", True), \
             patch("application.services.portfolio_service.PortfolioSnapshotsRepository") as repo_cls, \
             patch("application.services.portfolio_service.PortfolioValueSeriesRepository",
                   return_value=broken), \
             patch.object(svc, "_period_to_date_range", return_value=WINDOW):
            repo_cls.return_value.get_first_snapshot_date.return_value = date(2026, 1, 4)
            repo_cls.return_value.get_portfolio_snapshots_series.return_value = GAP_ROWS
            result = asyncio.run(svc.get_portfolio_performance(1, "1Y"))

        assert result["success"]
        assert result["snapshots"], "the request must still be served"

    def test_disabled_flag_never_touches_the_store(self):
        svc = _service()
        store = FakeValueSeriesStore()
        result = _run(svc, GAP_ROWS, store, enabled=False)
        assert result["success"]
        assert store.get_calls == 0 and store.upsert_calls == 0

    def test_first_hit_warms_the_response_cache_for_repeats(self):
        """A Layer 4 hit must also warm Layer 3, so repeats skip both."""
        from application.services.portfolio_response_cache import get_response_cache
        get_response_cache().clear()

        svc = _service()
        store = FakeValueSeriesStore()
        cold = _run(svc, GAP_ROWS, store, cache_enabled=True)
        assert cold["served_from_cache"] is False

        gets_after_cold = store.get_calls
        warm = _run(svc, GAP_ROWS, store, cache_enabled=True)
        assert warm["served_from_cache"] is True, "the repeat must be a L3 hit"
        assert store.get_calls == gets_after_cold, "L3 hit must not reach the store"

    def test_empty_window_still_falls_back(self):
        """A 1D request before today's snapshot lands keeps its fallback path."""
        svc = _service()
        store = FakeValueSeriesStore()
        with patch.object(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True), \
             patch.object(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", True), \
             patch("application.services.portfolio_service.PortfolioSnapshotsRepository") as repo_cls, \
             patch("application.services.portfolio_service.PortfolioValueSeriesRepository",
                   return_value=store), \
             patch.object(svc, "_period_to_date_range",
                          return_value=(date(2026, 1, 7), date(2026, 1, 7))), \
             patch.object(svc, "_compute_performance_fallback",
                          return_value={"success": True, "snapshots": []}):
            repo_cls.return_value.get_first_snapshot_date.return_value = date(2026, 1, 4)
            repo_cls.return_value.get_portfolio_snapshots_series.return_value = GAP_ROWS
            result = asyncio.run(svc.get_portfolio_performance(1, "1D"))
        assert result["data_source"] == "computed_fallback"
        assert store.upsert_calls == 0, "a fallback response is not a curve build"
