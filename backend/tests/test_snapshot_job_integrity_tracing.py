"""Tests for the snapshot job's integrity instrumentation.

The failure this guards against is silent: the job computes one total, decides it
is a spike, and persists a *different* total (the previous verified value). The
substitution is deliberate and correct -- it prevents a garbage number entering
the ledger -- but it means the computed value is discarded without a trace.

``REPLAY_DRIFT`` is the only record that the two diverged. Without it, a snapshot
that was silently replaced looks identical to one that was computed normally, and
"why does account 7's value differ from what the replay said?" is unanswerable
after the fact.

These tests pin the two fields that make the finding useful: the value that was
computed (``replayed_total``) and the value that was actually stored
(``persisted_total``).
"""

import logging
from datetime import UTC, datetime

import pytest

from application.jobs import portfolio_snapshot_job as job_mod
from shared import debug_trace

FIXED_DATE = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)


class _PayloadCapture(logging.Handler):
    def __init__(self, sink):
        super().__init__()
        self._sink = sink

    def emit(self, record):
        payload = debug_trace.payload_of(record)
        if payload is not None:
            self._sink.append(payload)


@pytest.fixture
def captured():
    """Capture payloads from both the trace and integrity loggers."""
    trace_records: list[dict] = []
    integrity_records: list[dict] = []
    handlers = [
        (_PayloadCapture(trace_records), debug_trace.trace_logger),
        (_PayloadCapture(integrity_records), debug_trace.integrity_logger),
    ]
    saved = [(logger, logger.level) for _, logger in handlers]
    for handler, logger in handlers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    debug_trace.configure(enabled=True)
    try:
        yield {"trace": trace_records, "integrity": integrity_records}
    finally:
        debug_trace.configure(enabled=False)
        for handler, logger in handlers:
            logger.removeHandler(handler)
        for logger, level in saved:
            logger.setLevel(level)


class _FakePortfolioRepo:
    def get_user_accounts_all(self):
        return [{"account_id": 1, "currency": "CAD"}]

    def get_holdings_for_accounts(self, _batch):
        return [
            {
                "account_id": 1,
                "company_id": 10,
                "symbol": "AAPL",
                "quantity": 5,
                "first_purchase_date": "2026-01-02",
            }
        ]

    def get_company_names(self, _ids):
        return [{"company_id": 10, "company_name": "Apple Inc."}]

    def get_company_currencies(self, _ids):
        return [{"company_id": 10, "currency": "USD"}]

    def get_companies_info(self, _ids):
        return [{"company_id": 10, "cdr_ratio": 1.0}]

    def get_all_prices_historical(self, _ids, _today):
        return {}

    def get_cash_balance(self, *_args):
        return 0.0

    def get_net_deposits(self, *_args):
        return 0.0

    def get_cdr_company_ids_by_account(self):
        return {}

    def get_cdr_lots_by_account_as_of(self, _as_of):
        return {}


class _FakeFinancialRepo:
    async def get_latest_prices(self, _ids, _today):
        return {}


class _FakeSnapshotsRepo:
    def __init__(self, previous):
        self._previous = previous
        self.upserted: list[dict] = []

    def get_previous_snapshot(self, _account_id, _today):
        return self._previous

    def get_last_snapshot_date(self, _account_id):
        # History is complete through FIXED_DATE, so the daily job's gap-fill
        # pre-pass is a no-op and these tests stay focused on the spike policy.
        return FIXED_DATE.date()

    def get_missing_dates(self, _account_id, _start, _end):
        return []

    def upsert_snapshot(self, row):
        self.upserted.append(dict(row))


def _snapshot_row(total):
    return {
        "account_id": 1,
        "snapshot_date": FIXED_DATE.date().isoformat(),
        "total_value": total,
        "holdings_market_value": total,
        "cash_balance": 0.0,
        "holdings_json": [{"company_id": 10, "quantity": 5.0}],
        "data_quality_flag": "OK",
    }


@pytest.fixture
def job_env(monkeypatch, captured):
    """Wire ``compute_daily_snapshots`` against fakes.

    Returns a dict the test mutates to steer the outcome, plus the repo that
    records what was actually persisted.
    """
    state = {
        "computed_total": 1000.0,
        "previous": {"total_value": 900.0, "holdings_market_value": 900.0,
                     "cash_balance": 0.0, "holdings_json": []},
        "spike": {"message": "value moved 90%"},
    }
    repo_holder = {}

    def _build_row(**_kwargs):
        return _snapshot_row(state["computed_total"])

    def _check_spike(_prev, _row, threshold=0.20):
        return state["spike"] if state["spike"] else None

    def _make_snapshots_repo():
        repo = _FakeSnapshotsRepo(state["previous"])
        repo_holder["repo"] = repo
        return repo

    fake_settings = type("S", (), {
        "ENABLE_FX_CONVERSION": False,
        "ENABLE_EVENT_REPLAY_SNAPSHOTS": False,
        "SNAPSHOT_SPIKE_THRESHOLD": 0.20,
    })()

    monkeypatch.setattr(job_mod, "PortfolioRepository", _FakePortfolioRepo)
    monkeypatch.setattr(job_mod, "SupabaseFinancialRepository", _FakeFinancialRepo)
    monkeypatch.setattr(job_mod, "PortfolioSnapshotsRepository", _make_snapshots_repo)
    monkeypatch.setattr(job_mod, "build_snapshot_row", _build_row)
    monkeypatch.setattr(job_mod, "check_snapshot_spike", _check_spike)
    monkeypatch.setattr(job_mod, "settings", fake_settings)
    monkeypatch.setattr(job_mod, "now_utc", lambda: FIXED_DATE)
    monkeypatch.setattr(job_mod, "BATCH_SIZE", 100)

    state["captured"] = captured
    state["upserts"] = repo_holder
    return state


def _find(records, event):
    return [r for r in records if r.get("event") == event]


class TestReplayDrift:
    @pytest.mark.asyncio
    async def test_spike_records_the_withheld_value(self, job_env, captured):
        """The finding must carry the computed value AND the fact nothing was stored.

        Recording only one makes the finding unactionable: you cannot tell a withheld
        write from a large correction. ``persisted_total is None`` is a positive claim
        that the write was deliberately withheld, not a missing field.
        """
        job_env["computed_total"] = 5000.0  # a wild jump from the previous 900

        await job_mod.compute_daily_snapshots()

        findings = _find(captured["integrity"], "REPLAY_DRIFT")
        assert len(findings) == 1
        finding = findings[0]
        assert finding["layer"] == "integrity"
        assert finding["account_id"] == 1
        assert finding["replayed_total"] == 5000.0
        assert finding["persisted_total"] is None
        assert finding["reason"] == "spike_write_withheld"
        assert finding["used_replay"] is False
        assert finding["message"] == "value moved 90%"

    @pytest.mark.asyncio
    async def test_drift_reflects_what_was_actually_persisted(self, job_env, captured):
        """``persisted_total`` must match the row written to storage.

        If these two ever disagree the finding is describing an intention rather
        than an outcome, which is the one thing a diagnostic must not do. When the
        write is withheld the two must agree that nothing was stored.
        """
        job_env["computed_total"] = 5000.0

        await job_mod.compute_daily_snapshots()

        finding = _find(captured["integrity"], "REPLAY_DRIFT")[0]
        assert job_env["upserts"]["repo"].upserted == [], (
            "a spike must not write a row; carrying the previous day forward "
            "would persist one row's values under another row's date"
        )
        assert finding["persisted_total"] is None

    @pytest.mark.asyncio
    async def test_no_drift_when_there_is_no_spike(self, job_env, captured):
        """A clean run must stay quiet; a finding that always fires is noise."""
        job_env["spike"] = None

        await job_mod.compute_daily_snapshots()

        assert _find(captured["integrity"], "REPLAY_DRIFT") == []
        assert _find(captured["trace"], "persist_snapshot")

    @pytest.mark.asyncio
    async def test_no_findings_when_tracing_disabled(self, job_env, captured):
        """A debug facility must not slow or alter the production path."""
        debug_trace.configure(enabled=False)
        try:
            await job_mod.compute_daily_snapshots()
        finally:
            debug_trace.configure(enabled=True)

        assert captured["integrity"] == []
        assert captured["trace"] == []


class TestPersistSnapshotTrace:
    @pytest.mark.asyncio
    async def test_emits_persisted_shape(self, job_env, captured):
        job_env["spike"] = None

        await job_mod.compute_daily_snapshots()

        events = _find(captured["trace"], "persist_snapshot")
        assert len(events) == 1
        event = events[0]
        assert event["layer"] == "snapshot_job"
        assert event["account_id"] == 1
        assert event["snapshot_date"] == "2026-07-06"
        assert event["holdings"] == 1
        assert event["data_quality_flag"] == "OK"
        assert event["used_replay"] is False

    @pytest.mark.asyncio
    async def test_no_persist_trace_when_the_write_is_withheld(
        self, job_env, captured
    ):
        """A withheld write must leave no persist event behind.

        The two channels are cross-referenced during triage, so they must not
        disagree: the persist channel stays silent and the integrity channel
        carries the computed value with nothing marked as stored.
        """
        job_env["computed_total"] = 5000.0

        await job_mod.compute_daily_snapshots()

        assert _find(captured["trace"], "persist_snapshot") == []
        finding = _find(captured["integrity"], "REPLAY_DRIFT")[0]
        assert finding["replayed_total"] == 5000.0
        assert finding["persisted_total"] is None

    @pytest.mark.asyncio
    async def test_trace_carries_the_job_trace_id(self, job_env, captured):
        """The record must join to the repository calls made in the same run."""
        job_env["spike"] = None

        with debug_trace.trace_scope("snapshot-test"):
            scoped = debug_trace.current_trace_id()
            await job_mod.compute_daily_snapshots()

        event = _find(captured["trace"], "persist_snapshot")[0]
        assert event["trace_id"] == scoped
