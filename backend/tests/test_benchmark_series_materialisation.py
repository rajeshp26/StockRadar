"""Behavioural tests for the materialised benchmark series (migration 015).

The requirement these protect:

    The benchmark series must be computed once and stored, only the tail may be
    recomputed, and a reused series must return EXACTLY the dollars the live
    simulation would return. A store that can serve a stale dollar is worse
    than no store at all.

Two layers are covered separately:

* ``BenchmarkSeriesGuard`` - the reuse/rebuild/tail decision, tested as a pure
  function (no database), so every branch has a named, executable case.
* The integration path in ``PortfolioService._benchmark_series_with_reuse`` -
  tested with a fake store and the REAL simulator, asserting that a hit, a
  miss and a fingerprint mismatch all produce identical dollars.
"""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.benchmark_series_guard import (
    FINGERPRINT_MATCH,
    FINGERPRINT_MISMATCH,
    NO_PRIOR_SERIES,
    SERIES_ENDS_BEFORE,
    SERIES_INCEPTION_LATER,
    BenchmarkSeriesGuard,
    compute_series_fingerprint,
    price_signature,
)
from application.services.portfolio_service import PortfolioService


BENCHMARK_COMPANY_ID = 999


def _price_rows(start: date, end: date, daily_growth: float = 0.0004) -> list[dict]:
    rows: list[dict] = []
    price = 100.0
    d = start
    while d <= end:
        rows.append(
            {"price_date": d.isoformat(), "adj_close": price, "close_price": price}
        )
        price *= 1 + daily_growth
        d += timedelta(days=1)
    return rows


class FakeSeriesStore:
    """In-memory stand-in for BenchmarkSeriesRepository."""

    def __init__(self):
        self.points: list[dict] = []
        self.fingerprint: str | None = None
        self.inception_date: date | None = None
        self.initial_value: float | None = None
        self.last_mark_date: date | None = None
        self.upsert_calls = 0

    def get_series(self, account_key, symbol, start_date=None, end_date=None):
        if self.fingerprint is None:
            return MagicMock(
                fingerprint=None, inception_date=None, initial_value=None,
                last_mark_date=None, computed_at=None, points=[],
                is_empty=True,
            )
        pts = [
            p for p in self.points
            if (start_date is None or p["date"] >= start_date.isoformat())
            and (end_date is None or p["date"] <= end_date.isoformat())
        ]
        return MagicMock(
            fingerprint=self.fingerprint,
            inception_date=self.inception_date,
            initial_value=self.initial_value,
            last_mark_date=self.last_mark_date,
            computed_at=None,
            points=pts,
            is_empty=not pts,
        )

    def upsert_points(self, account_key, symbol, points, inception_date,
                      initial_value, fingerprint, last_mark_date):
        self.points = list(points)
        self.fingerprint = fingerprint
        self.inception_date = inception_date
        self.initial_value = initial_value
        self.last_mark_date = last_mark_date
        self.upsert_calls += 1
        return len(points)


# ── Guard: pure decision cases ───────────────────────────────────────────────

class TestGuardDecisions:
    def test_no_stored_series_rebuilds(self):
        d = BenchmarkSeriesGuard().decide(
            stored_fingerprint=None, stored_inception=None, stored_last_mark=None,
            expected_fingerprint="abc", required_inception=date(2022, 1, 3),
            required_end=date(2026, 10, 19),
        )
        assert d.rebuild and not d.can_reuse
        assert d.reason == NO_PRIOR_SERIES and d.gate == 1

    def test_inception_moved_earlier_rebuilds_whole_series(self):
        """A backdated import before stored inception invalidates every date."""
        d = BenchmarkSeriesGuard().decide(
            stored_fingerprint="abc", stored_inception=date(2023, 1, 1),
            stored_last_mark=date(2026, 10, 19), expected_fingerprint="abc",
            required_inception=date(2022, 1, 3), required_end=date(2026, 10, 19),
        )
        assert d.rebuild and not d.can_reuse
        assert d.reason == SERIES_INCEPTION_LATER and d.gate == 1

    def test_fingerprint_mismatch_rebuilds(self):
        """Same coverage, different inputs => stored dollars are wrong."""
        d = BenchmarkSeriesGuard().decide(
            stored_fingerprint="old", stored_inception=date(2022, 1, 3),
            stored_last_mark=date(2026, 10, 19), expected_fingerprint="new",
            required_inception=date(2022, 1, 3), required_end=date(2026, 10, 19),
        )
        assert d.rebuild and not d.can_reuse
        assert d.reason == FINGERPRINT_MISMATCH and d.gate == 2

    def test_covered_and_matching_reuses_with_nothing_to_compute(self):
        d = BenchmarkSeriesGuard().decide(
            stored_fingerprint="same", stored_inception=date(2022, 1, 3),
            stored_last_mark=date(2026, 10, 19), expected_fingerprint="same",
            required_inception=date(2022, 1, 3), required_end=date(2026, 10, 19),
        )
        assert d.can_reuse and not d.rebuild and not d.must_compute
        assert d.reason == FINGERPRINT_MATCH

    def test_tail_missing_reuses_prefix_and_computes_from_mark(self):
        """One new day must compute one day, not five years."""
        d = BenchmarkSeriesGuard().decide(
            stored_fingerprint="same", stored_inception=date(2022, 1, 3),
            stored_last_mark=date(2026, 10, 18), expected_fingerprint="same",
            required_inception=date(2022, 1, 3), required_end=date(2026, 10, 19),
        )
        assert d.can_reuse and not d.rebuild
        assert d.compute_from == date(2026, 10, 18)
        assert d.reason == SERIES_ENDS_BEFORE

    def test_earlier_stored_inception_than_required_is_reusable(self):
        """Stored inception before what is needed covers it - not a rebuild."""
        d = BenchmarkSeriesGuard().decide(
            stored_fingerprint="same", stored_inception=date(2021, 1, 1),
            stored_last_mark=date(2026, 10, 19), expected_fingerprint="same",
            required_inception=date(2022, 1, 3), required_end=date(2026, 10, 19),
        )
        assert d.can_reuse and not d.must_compute


# ── Fingerprint: sensitivity to the changes that move a dollar ───────────────

class TestFingerprint:
    BASE = dict(
        account_key="7,8,9", symbol="SPY", inception_date=date(2022, 1, 3),
        initial_value=50_000.0,
        cashflows=[{"date": date(2022, 1, 3), "amount": 1_000.0}],
        price_signature={"row_count": 100, "first": ["2022-01-03", 100.0],
                         "last": ["2026-10-19", 300.0]},
    )

    def test_identical_inputs_give_identical_fingerprint(self):
        assert compute_series_fingerprint(**self.BASE) == compute_series_fingerprint(**self.BASE)

    def test_amount_change_changes_fingerprint(self):
        other = dict(self.BASE)
        other["cashflows"] = [{"date": date(2022, 1, 3), "amount": 1_001.0}]
        assert compute_series_fingerprint(**self.BASE) != compute_series_fingerprint(**other)

    def test_price_backfill_changes_fingerprint(self):
        other = dict(self.BASE)
        other["price_signature"] = {"row_count": 101, "first": ["2022-01-03", 100.0],
                                    "last": ["2026-10-19", 300.0]}
        assert compute_series_fingerprint(**self.BASE) != compute_series_fingerprint(**other)

    def test_inception_change_changes_fingerprint(self):
        other = dict(self.BASE)
        other["inception_date"] = date(2021, 12, 1)
        assert compute_series_fingerprint(**self.BASE) != compute_series_fingerprint(**other)

    def test_signature_detects_count_and_both_ends(self):
        rows = _price_rows(date(2022, 1, 1), date(2022, 1, 10))
        base = price_signature(rows)
        assert base["row_count"] == 10
        assert price_signature(rows[:-1])["row_count"] == 9
        assert price_signature(rows[:-1]) != base
        assert price_signature([]) == {"row_count": 0, "first": None, "last": None}

    def test_signature_is_order_independent(self):
        rows = _price_rows(date(2022, 1, 1), date(2022, 1, 10))
        assert price_signature(rows) == price_signature(list(reversed(rows)))


# ── Integration: reuse returns the same dollars as a live simulation ─────────

class TestMaterialisedPathEquivalence:
    def _service(self) -> PortfolioService:
        return PortfolioService(MagicMock(), MagicMock())

    @pytest.mark.anyio
    async def test_cold_miss_then_hit_returns_identical_values(self):
        """The unit of the change: a stored series is worth storing.

        Cold call simulates and writes; the next call must be served from the
        store with byte-identical dollars on every date.
        """
        end = date(2026, 10, 19)
        inception = date(2022, 1, 3)
        rows = _price_rows(date(2022, 1, 1), end)
        cashflows = [
            {"date": date(2022, 1, 3), "amount": 50_000.0},
            {"date": date(2023, 6, 1), "amount": 25_000.0},
            {"date": date(2025, 3, 1), "amount": 10_000.0},
        ]
        grid: list[str] = []
        d = inception
        while d <= end:
            grid.append(d.isoformat())
            d += timedelta(days=30)
        if grid[-1] != end.isoformat():
            grid.append(end.isoformat())

        svc = self._service()
        store = FakeSeriesStore()

        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
        ):
            cold = await svc._benchmark_series_with_reuse(
                account_key="7,8,9", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end,
                initial_value=50_000.0, cashflows=cashflows, window_dates=grid,
            )
            assert store.upsert_calls == 1, "a cold miss must write the series"

            warm = await svc._benchmark_series_with_reuse(
                account_key="7,8,9", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end,
                initial_value=50_000.0, cashflows=cashflows, window_dates=grid,
            )
            assert store.upsert_calls == 1, "a hit must not rewrite the series"

        assert warm == cold, "a served series must equal the simulated one"
        assert [p["value"] for p in warm] == [p["value"] for p in cold]

    @pytest.mark.anyio
    async def test_warm_hit_is_served_without_simulating(self):
        """A valid stored series must not call the simulator at all."""
        end = date(2026, 10, 19)
        inception = date(2022, 1, 3)
        rows = _price_rows(date(2022, 1, 1), end)
        cashflows = [{"date": date(2022, 1, 3), "amount": 50_000.0}]
        grid = [inception.isoformat(), "2025-01-01", end.isoformat()]

        svc = self._service()
        store = FakeSeriesStore()
        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
        ):
            await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=cashflows, window_dates=grid,
            )
            with patch.object(
                svc, "_simulate_benchmark_value",
                side_effect=AssertionError("simulator must not run on a hit"),
            ):
                served = await svc._benchmark_series_with_reuse(
                    account_key="k", symbol="SPY",
                    benchmark_company_id=BENCHMARK_COMPANY_ID,
                    inception_date=inception, end_date=end, initial_value=50_000.0,
                    cashflows=cashflows, window_dates=grid,
                )
        assert served == [
            {"date": inception.isoformat(), "value": served[0]["value"]},
            {"date": "2025-01-01", "value": served[1]["value"]},
            {"date": end.isoformat(), "value": served[2]["value"]},
        ]

    @pytest.mark.anyio
    async def test_price_change_invalidates_and_rebuilds(self):
        """A corrected price must produce new dollars, not the stored ones."""
        end = date(2026, 10, 19)
        inception = date(2022, 1, 3)
        rows = _price_rows(date(2022, 1, 1), end)
        cashflows = [{"date": date(2022, 1, 3), "amount": 50_000.0}]
        grid = [inception.isoformat(), end.isoformat()]

        svc = self._service()
        store = FakeSeriesStore()
        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
        ):
            first = await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=cashflows, window_dates=grid,
            )
            assert store.upsert_calls == 1

        # A corrected price INSIDE the fetched window changes the signature.
        # (Appending an earlier date alone does not: `_nearest_price` would
        # resolve to the same first price, so the dollars legitimately match —
        # that case is covered by the fingerprint unit test.)
        corrected = list(rows)
        corrected[-1] = {
            "price_date": corrected[-1]["price_date"],
            "adj_close": corrected[-1]["adj_close"] * 2,
            "close_price": corrected[-1]["close_price"] * 2,
        }
        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=corrected),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
        ):
            second = await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=cashflows, window_dates=grid,
            )
            assert store.upsert_calls == 2, "a changed input must rebuild"

        assert second != first, "a corrected price must change the served dollars"

    @pytest.mark.anyio
    async def test_period_change_computes_only_missing_dates(self):
        """The defect the live probe found: a different grid over the same
        history must NOT re-simulate the dates already stored.

        A monthly-stored build asked for a weekly grid must compute only the
        weekly dates it does not have, and serve the rest from the store.
        """
        end = date(2026, 10, 19)
        inception = date(2022, 1, 3)
        rows = _price_rows(date(2022, 1, 1), end)
        cashflows = [{"date": inception, "amount": 50_000.0}]

        monthly = ["2022-01-03", "2026-10-19"]
        weekly = ["2022-01-03", "2023-01-03", "2024-01-03", "2026-10-19"]

        svc = self._service()
        store = FakeSeriesStore()
        simulated_grids: list[list[str]] = []
        real_sim = svc._simulate_benchmark_value

        def recording_sim(**kwargs):
            simulated_grids.append(list(kwargs["snapshot_dates"]))
            return real_sim(**kwargs)

        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
            patch.object(svc, "_simulate_benchmark_value", side_effect=recording_sim),
        ):
            first = await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=cashflows, window_dates=monthly,
            )
            simulated_grids.clear()

            second = await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=cashflows, window_dates=weekly,
            )

        # Only the two weekly dates the store lacked were computed.
        assert simulated_grids == [["2023-01-03", "2024-01-03"]], (
            f"expected only the missing weekly dates, got {simulated_grids}"
        )
        # The served result covers every requested date, in order.
        assert [p["date"] for p in second] == weekly
        # And the dates shared with the first build carry identical dollars.
        first_map = {p["date"]: p["value"] for p in first}
        for p in second:
            if p["date"] in first_map:
                assert p["value"] == first_map[p["date"]]

    @pytest.mark.anyio
    async def test_rebuild_simulates_the_full_requested_grid(self):
        """A rebuild (changed inputs) must compute every requested date."""
        end = date(2026, 10, 19)
        inception = date(2022, 1, 3)
        rows = _price_rows(date(2022, 1, 1), end)
        svc = self._service()
        store = FakeSeriesStore()

        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
        ):
            await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=[{"date": inception, "amount": 50_000.0}],
                window_dates=[inception.isoformat(), end.isoformat()],
            )

        # Different cash flows => different fingerprint => full rebuild.
        grids: list[list[str]] = []
        real_sim = svc._simulate_benchmark_value

        def recording_sim(**kwargs):
            grids.append(list(kwargs["snapshot_dates"]))
            return real_sim(**kwargs)

        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=store,
            ),
            patch.object(svc, "_simulate_benchmark_value", side_effect=recording_sim),
        ):
            await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=[{"date": inception, "amount": 60_000.0}],
                window_dates=[inception.isoformat(), end.isoformat()],
            )

        assert grids == [[inception.isoformat(), end.isoformat()]]

    @pytest.mark.anyio
    async def test_store_failure_degrades_to_live_simulation(self):
        """A missing table must not break the request."""
        end = date(2026, 10, 19)
        inception = date(2022, 1, 3)
        rows = _price_rows(date(2022, 1, 1), end)
        svc = self._service()

        broken = MagicMock()
        broken.get_series.side_effect = Exception("relation does not exist")
        broken.upsert_points.side_effect = Exception("relation does not exist")

        with (
            patch.object(svc, "_fetch_benchmark_price_rows", return_value=rows),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository",
                return_value=broken,
            ),
        ):
            series = await svc._benchmark_series_with_reuse(
                account_key="k", symbol="SPY",
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                inception_date=inception, end_date=end, initial_value=50_000.0,
                cashflows=[{"date": inception, "amount": 50_000.0}],
                window_dates=[inception.isoformat(), end.isoformat()],
            )

        # Real repository swallows store errors; the fake raises, so the call
        # must still have produced a series for the request to succeed.
        assert series and len(series) == 2
