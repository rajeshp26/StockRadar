"""Writer-side persistence policy for daily portfolio snapshots.

Covers the contract that replaced the old carry-forward behaviour:
- history is repaired before the target date is written, so the spike baseline is
  the genuinely preceding day rather than the last successful run;
- a spike withholds the write instead of persisting a stand-in value;
- a gap date recomputed from events keeps its real value, flagged SPIKE_CONFIRMED;
- the scheduler's payload date is honoured;
- the return value counts rows actually written.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import application.jobs.portfolio_snapshot_job as job_mod

DAY_16 = date(2026, 8, 16)
DAY_17 = date(2026, 8, 17)
DAY_18 = date(2026, 8, 18)
DAY_19 = date(2026, 8, 19)


class FakeSnapshotsRepo:
    """Date-keyed store, so assertions read like the rows that would reach the DB."""

    def __init__(self, existing=()):
        self.rows: dict[str, dict] = {r["snapshot_date"]: dict(r) for r in existing}
        self.upserted: list[dict] = []

    def get_previous_snapshot(self, _account_id, as_of):
        prior = [d for d in self.rows if d < as_of.isoformat()]
        return self.rows[max(prior)] if prior else None

    def get_last_snapshot_date(self, _account_id):
        return date.fromisoformat(max(self.rows)) if self.rows else None

    def get_missing_dates(self, _account_id, start, end):
        return [
            date.fromordinal(d)
            for d in range(start.toordinal(), end.toordinal() + 1)
            if date.fromordinal(d).isoformat() not in self.rows
        ]

    def upsert_snapshot(self, row):
        self.rows[row["snapshot_date"]] = dict(row)
        self.upserted.append(dict(row))


def _row(total, day, flag="OK"):
    return {
        "account_id": 1,
        "snapshot_date": day.isoformat(),
        "total_value": total,
        "holdings_market_value": total,
        "cash_balance": 0.0,
        "holdings_json": [{"company_id": 10, "quantity": 5.0}],
        "net_deposits": 0.0,
        "data_quality_flag": flag,
    }


def _portfolio_repo(account_ids=(1,)):
    repo = MagicMock()
    repo.get_user_accounts_all.return_value = [
        {"account_id": a, "currency": "CAD"} for a in account_ids
    ]
    repo.get_holdings_for_accounts.return_value = [
        {"account_id": a, "company_id": 10, "symbol": "ABC", "quantity": 5.0,
         "exchange_override": None, "first_purchase_date": "2021-07-19"}
        for a in account_ids
    ]
    repo.get_company_names.return_value = []
    repo.get_company_currencies.return_value = []
    repo.get_companies_info.return_value = []
    repo.get_all_prices_historical.return_value = {}
    repo.get_cash_balance.return_value = 0.0
    repo.get_net_deposits.return_value = 0.0
    return repo


def _financial_repo():
    repo = MagicMock()
    repo.get_latest_prices = AsyncMock(return_value={})
    return repo


def _settings():
    return type("S", (), {
        "ENABLE_FX_CONVERSION": False,
        "ENABLE_EVENT_REPLAY_SNAPSHOTS": False,
        "SNAPSHOT_SPIKE_THRESHOLD": 0.20,
    })()


def _patch_job(monkeypatch, portfolio_repo, snapshots_repo, build_row, replay_row=None):
    financial_repo = _financial_repo()
    monkeypatch.setattr(job_mod, "PortfolioRepository", lambda: portfolio_repo)
    monkeypatch.setattr(
        job_mod, "SupabaseFinancialRepository", lambda: financial_repo
    )
    monkeypatch.setattr(
        job_mod, "PortfolioSnapshotsRepository", lambda: snapshots_repo
    )
    monkeypatch.setattr(job_mod, "build_snapshot_row", build_row)
    monkeypatch.setattr(job_mod, "settings", _settings())
    monkeypatch.setattr(job_mod, "now_utc", lambda: datetime(2026, 8, 19))
    monkeypatch.setattr(job_mod, "BATCH_SIZE", 100)
    if replay_row is not None:
        monkeypatch.setattr(
            job_mod,
            "_build_snapshot_via_replay",
            lambda **_kwargs: dict(replay_row),
        )
    return financial_repo


class TestGapRepairPrecedesTargetWrite:
    async def test_spike_baseline_is_the_repaired_previous_day(self, monkeypatch):
        """A hole must be filled before the spike check, or the baseline is stale.

        With 2026-08-16 as the last row, the 17th and 18th are missing. If the 19th
        were compared before repair, get_previous_snapshot would return the 16th and
        a two-day-old row would decide whether today is anomalous.
        """
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_16)])
        baselines: list[dict | None] = []

        def _check_spike(prev, _row, threshold=0.20):
            baselines.append(prev)
            return None

        def _replay(**kwargs):
            day = kwargs["snapshot_date"]
            return _row(1100.0, day)

        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1200.0, kwargs["snapshot_date"]),
            replay_row=None,
        )
        monkeypatch.setattr(job_mod, "check_snapshot_spike", _check_spike)
        monkeypatch.setattr(
            job_mod, "_build_snapshot_via_replay", lambda **kwargs: _replay(**kwargs)
        )

        await job_mod.compute_daily_snapshots(DAY_19)

        assert DAY_17.isoformat() in snapshots.rows
        assert DAY_18.isoformat() in snapshots.rows
        # The gap filler runs its own spike check per gap day; the final check is the
        # target date's, and it must see the repaired previous day.
        assert baselines[-1]["snapshot_date"] == DAY_18.isoformat(), (
            "the spike check compared against a stale row, so a normal day would "
            "be measured against the last successful run rather than yesterday"
        )

    async def test_no_gap_no_extra_writes(self, monkeypatch):
        """A complete history must not produce gap rows or extra writes."""
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_18)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1200.0, kwargs["snapshot_date"]),
        )

        written = await job_mod.compute_daily_snapshots(DAY_19)

        assert written == 1
        assert [r["snapshot_date"] for r in snapshots.upserted] == [DAY_19.isoformat()]


class TestRecomputedGapSpike:
    async def test_real_move_is_kept_and_flagged(self, monkeypatch):
        """A gap value recomputed from events that still spikes is a real finding.

        It differs from the same-day case: this number was derived from the source,
        so keeping it is correct. Only the substitution of an older day's numbers
        was ever wrong.
        """
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_16)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1200.0, kwargs["snapshot_date"]),
        )
        monkeypatch.setattr(
            job_mod,
            "_build_snapshot_via_replay",
            lambda **kwargs: _row(5000.0, kwargs["snapshot_date"]),
        )

        await job_mod.compute_daily_snapshots(DAY_19)

        jumped = [r for r in snapshots.upserted if r["snapshot_date"] == DAY_17.isoformat()]
        assert jumped, "the hole was never repaired"
        assert jumped[0]["total_value"] == 5000.0, (
            "the recomputed value was replaced; that is the same fabrication the "
            "same-day path was fixed to avoid"
        )
        assert jumped[0]["data_quality_flag"] == "SPIKE_CONFIRMED"
        # The day after already holds 5000, so it is a flat continuation, not a spike.
        settled = [r for r in snapshots.upserted if r["snapshot_date"] == DAY_18.isoformat()]
        assert settled[0]["data_quality_flag"] == "OK"

    async def test_quiet_gap_is_written_unflagged(self, monkeypatch):
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_16)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1200.0, kwargs["snapshot_date"]),
        )
        monkeypatch.setattr(
            job_mod,
            "_build_snapshot_via_replay",
            lambda **kwargs: _row(1050.0, kwargs["snapshot_date"]),
        )

        await job_mod.compute_daily_snapshots(DAY_19)

        gap_rows = [r for r in snapshots.upserted if r["snapshot_date"] == DAY_18.isoformat()]
        assert gap_rows[0]["data_quality_flag"] == "OK"


class TestSpikeWithholdsWrite:
    async def test_no_row_is_written_for_the_spike_date(self, monkeypatch):
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_18)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(36_000_000.0, kwargs["snapshot_date"]),
        )

        written = await job_mod.compute_daily_snapshots(DAY_19)

        assert written == 0
        assert DAY_19.isoformat() not in snapshots.rows

    async def test_absent_day_is_repaired_on_the_next_run(self, monkeypatch):
        """The withheld day must come back as a real recomputed value, not a stand-in."""
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_18)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(36_000_000.0, kwargs["snapshot_date"]),
        )
        await job_mod.compute_daily_snapshots(DAY_19)
        assert DAY_19.isoformat() not in snapshots.rows

        monkeypatch.setattr(
            job_mod,
            "build_snapshot_row",
            lambda **kwargs: _row(1010.0, kwargs["snapshot_date"]),
        )
        written = await job_mod.compute_daily_snapshots(DAY_19)

        assert written == 1
        assert snapshots.rows[DAY_19.isoformat()]["total_value"] == 1010.0


class TestWriteCounts:
    async def test_no_accounts_is_zero(self, monkeypatch):
        snapshots = FakeSnapshotsRepo()
        _patch_job(
            monkeypatch, _portfolio_repo(account_ids=()), snapshots,
            lambda **kwargs: _row(1.0, kwargs["snapshot_date"]),
        )

        assert await job_mod.compute_daily_snapshots(DAY_19) == 0

    async def test_counts_every_account(self, monkeypatch):
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_18)])
        _patch_job(
            monkeypatch, _portfolio_repo(account_ids=(1, 2, 3)), snapshots,
            lambda **kwargs: _row(1010.0, kwargs["snapshot_date"]),
        )

        assert await job_mod.compute_daily_snapshots(DAY_19) == 3

    async def test_withheld_accounts_are_not_counted(self, monkeypatch):
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_18)])

        def _build_row(**kwargs):
            account = kwargs["account_id"]
            total = 36_000_000.0 if account == 2 else 1010.0
            row = _row(total, kwargs["snapshot_date"])
            row["account_id"] = account
            return row

        _patch_job(
            monkeypatch, _portfolio_repo(account_ids=(1, 2)), snapshots, _build_row
        )

        assert await job_mod.compute_daily_snapshots(DAY_19) == 1


class TestPayloadDateIsHonoured:
    async def test_scheduler_date_reaches_the_writer(self, monkeypatch):
        captured: list[date | None] = []

        async def _fake_compute(target_date=None):
            captured.append(target_date)
            return 5

        monkeypatch.setattr(job_mod, "compute_daily_snapshots", _fake_compute)

        result = await job_mod.handle_portfolio_snapshot(
            {"payload": {"date": "2026-08-19"}}
        )

        assert captured == [date(2026, 8, 19)]
        assert result["snapshot_date"] == "2026-08-19"

    async def test_backfill_targets_the_requested_day(self, monkeypatch):
        """A backfill must write the day it was asked for, not the day it ran."""
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_16)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1010.0, kwargs["snapshot_date"]),
        )

        await job_mod.compute_daily_snapshots(DAY_18)

        assert DAY_18.isoformat() in snapshots.rows
        assert DAY_19.isoformat() not in snapshots.rows

    async def test_missing_payload_date_defaults_to_today(self, monkeypatch):
        monkeypatch.setattr(job_mod, "now_utc", lambda: datetime(2026, 8, 19))
        seen: list[date | None] = []

        async def _fake_compute(target_date=None):
            seen.append(target_date)
            return 0

        monkeypatch.setattr(job_mod, "compute_daily_snapshots", _fake_compute)

        result = await job_mod.handle_portfolio_snapshot({})

        assert seen == [None]
        assert result["snapshot_date"] == "2026-08-19"


class TestTargetDateDefaultsToNow:
    async def test_no_argument_uses_today(self, monkeypatch):
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_18)])
        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1010.0, kwargs["snapshot_date"]),
        )

        written = await job_mod.compute_daily_snapshots()

        assert written == 1
        assert DAY_19.isoformat() in snapshots.rows

    async def test_gap_fill_never_runs_past_the_previous_day(self, monkeypatch):
        """Repair targets yesterday at the latest, so the target day stays a spike test."""
        snapshots = FakeSnapshotsRepo([_row(1000.0, DAY_16)])
        seen_bounds: list[tuple] = []
        real_gaps = job_mod._fill_snapshot_gaps

        async def _spy(**kwargs):
            seen_bounds.append((kwargs["today"], kwargs["snapshots_repo"].get_last_snapshot_date(1)))
            return await real_gaps(**kwargs)

        _patch_job(
            monkeypatch,
            _portfolio_repo(),
            snapshots,
            lambda **kwargs: _row(1010.0, kwargs["snapshot_date"]),
        )
        monkeypatch.setattr(job_mod, "_fill_snapshot_gaps", _spy)

        await job_mod.compute_daily_snapshots(DAY_19)

        assert seen_bounds[0][0] == DAY_18
        assert seen_bounds[0][0] <= DAY_19 - timedelta(days=1)
