"""Interior-hole repair for the daily portfolio snapshot job.

Forward-only gap filling starts the day after the newest stored row, so a hole a
missed run left *behind* that row (the June 2026 gap) is unreachable once a later
date exists. These tests pin the bounded look-back that rebuilds those holes and
the first-snapshot clamp that stops it fabricating pre-inception zero rows.
"""

from datetime import date, timedelta

import pytest

import application.jobs.portfolio_snapshot_job as job_mod
from application.jobs.portfolio_snapshot_job import _gap_repair_start

TODAY = date(2026, 9, 15)
THU = date(2026, 9, 10)
FRI = date(2026, 9, 11)
MON = date(2026, 9, 14)  # the interior hole
TUE = date(2026, 9, 15)  # the newest stored row


class _FakeSnapshotsRepo:
    """Date-keyed store that records the window asked of get_missing_dates."""

    def __init__(self, dates=(THU, FRI, TUE)):
        self.dates = sorted(d.isoformat() for d in dates)
        self.rows = {d: {"snapshot_date": d, "total_value": 1000.0} for d in self.dates}
        self.upserted: list[dict] = []
        self.missing_calls: list[tuple[date, date]] = []

    def get_last_snapshot_date(self, _account_id):
        return date.fromisoformat(self.dates[-1]) if self.dates else None

    def get_first_snapshot_date(self, _account_id):
        return date.fromisoformat(self.dates[0]) if self.dates else None

    def get_missing_dates(self, _account_id, start, end):
        self.missing_calls.append((start, end))
        return [
            date.fromordinal(o)
            for o in range(start.toordinal(), end.toordinal() + 1)
            if date.fromordinal(o).weekday() < 5
            and date.fromordinal(o).isoformat() not in self.rows
        ]

    def get_previous_snapshot(self, _account_id, before_date):
        prior = [d for d in self.dates if d < before_date.isoformat()]
        return self.rows[prior[-1]] if prior else None

    def upsert_snapshot(self, row):
        self.dates = sorted(set(self.dates) | {row["snapshot_date"]})
        self.rows[row["snapshot_date"]] = dict(row)
        self.upserted.append(dict(row))


def _patch_replay(monkeypatch, total=1000.0):
    monkeypatch.setattr(
        job_mod,
        "_build_snapshot_via_replay",
        lambda **kwargs: {
            "snapshot_date": kwargs["snapshot_date"].isoformat(),
            "total_value": total,
            "holdings_market_value": total,
            "cash_balance": 0.0,
            "holdings_json": [],
        },
    )
    monkeypatch.setattr(job_mod, "check_snapshot_spike", lambda *_a, **_k: None)


async def _fill(snapshots, lookback_days):
    return await job_mod._fill_snapshot_gaps(
        account_id=1,
        today=TODAY,
        account_currency="CAD",
        prices_by_company={},
        price_history={},
        exchange_overrides={},
        snapshots_repo=snapshots,
        job_id_prefix="daily",
        spike_threshold=0.20,
        financial_repo=object(),
        all_company_ids=None,
        company_currencies={},
        companies_map={},
        derived_cdr_companies=set(),
        lot_map_cache=None,
        lookback_days=lookback_days,
    )


class TestGapRepairStart:
    def test_cold_start_defers_to_the_caller(self):
        assert _gap_repair_start(None, TODAY, 730, None) is None

    def test_forward_only_without_a_lookback(self):
        assert _gap_repair_start(TUE, TODAY, None, THU) == TUE + timedelta(days=1)

    def test_zero_lookback_keeps_forward_only(self):
        """0 is the documented off switch, not a one-day window."""
        assert _gap_repair_start(TUE, TODAY, 0, THU) == TUE + timedelta(days=1)

    def test_window_reaches_back_from_today(self):
        start = _gap_repair_start(TUE, TODAY, 30, None)
        assert start == TODAY - timedelta(days=29)

    def test_window_is_clamped_to_the_first_snapshot(self):
        """Never ask for dates before the account existed -- they would write zeros."""
        start = _gap_repair_start(TUE, TODAY, 730, MON)
        assert start == MON

    def test_start_is_never_pushed_forward(self):
        """Look-back only ever widens the window; a live tail is still filled."""
        # window_start clamps to the first snapshot, which predates the tail start
        assert _gap_repair_start(THU, TODAY, 30, THU) == THU
        # and for every look-back the start is never later than the day after the
        # newest row, so the ordinary tail fill is always preserved
        newest = date(2026, 9, 14)
        for lookback in (1, 2, 30, 730):
            assert _gap_repair_start(newest, TODAY, lookback, date(2020, 1, 1)) <= (
                newest + timedelta(days=1)
            )


class TestInteriorHoleRepair:
    @pytest.mark.asyncio
    async def test_forward_only_leaves_the_hole(self, monkeypatch):
        snapshots = _FakeSnapshotsRepo()
        _patch_replay(monkeypatch)

        assert await _fill(snapshots, lookback_days=None) == 0
        assert snapshots.upserted == []

    @pytest.mark.asyncio
    async def test_lookback_rebuilds_the_hole(self, monkeypatch):
        snapshots = _FakeSnapshotsRepo()
        _patch_replay(monkeypatch)

        written = await _fill(snapshots, lookback_days=730)

        assert written == 1
        assert [r["snapshot_date"] for r in snapshots.upserted] == [MON.isoformat()]
        assert snapshots.upserted[0]["job_id"].endswith(f"_gap_{MON.isoformat()}")

    @pytest.mark.asyncio
    async def test_window_is_clamped_before_get_missing_dates(self, monkeypatch):
        snapshots = _FakeSnapshotsRepo()
        _patch_replay(monkeypatch)

        await _fill(snapshots, lookback_days=730)

        assert snapshots.missing_calls == [(THU, TODAY)], (
            "repair must start at the first stored snapshot, not 730 days back"
        )

    @pytest.mark.asyncio
    async def test_dense_history_stays_a_no_op(self, monkeypatch):
        """Look-back must not manufacture writes when nothing is missing."""
        snapshots = _FakeSnapshotsRepo([THU, FRI, MON, TUE])
        _patch_replay(monkeypatch)

        assert await _fill(snapshots, lookback_days=730) == 0
        assert snapshots.upserted == []
