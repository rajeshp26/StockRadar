"""Tests for snapshot-run observability under the configuration we actually ship.

The failure these guard against is the one the user reported: "did you add logs
in the entire stack flow ... did you test it end to end?" The tracing machinery
existed and was correct, but it shipped with ``DEBUG_TRACE_ENABLED`` and
``DEBUG_LOG_ENABLED`` both defaulting to False. So every emitter was compiled
into the job, every emitter returned immediately, and a scheduled run produced
zero durable records. The tests that existed all enabled tracing explicitly,
which is why the gap was invisible.

Two things are therefore pinned here, and both are about configuration and
wiring rather than about the tracing code itself:

* the allowlist mechanism -- one named scope (``snapshot``) traces while the
  global flag is off, and nothing else does;
* the shipped defaults -- with a plain ``setup_debug_logging()`` and no test
  scaffolding, the snapshot scope is allowlisted and the JSONL sink is attached.

The second group is the one that would have caught the original defect. A test
that calls ``debug_trace.configure(enabled=True)`` proves the emitter works; it
cannot prove anything is emitted in production.
"""

import logging
from datetime import date

import pytest

from application.jobs import portfolio_snapshot_job as job_mod
from shared import debug_trace, logging_setup

FIXED_DATE = "2026-07-06"


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
        return date.fromisoformat(FIXED_DATE)

    def get_missing_dates(self, _account_id, _start, _end):
        return []

    def upsert_snapshot(self, row):
        self.upserted.append(dict(row))


def _snapshot_row(total):
    return {
        "account_id": 1,
        "snapshot_date": FIXED_DATE,
        "total_value": total,
        "holdings_market_value": total,
        "cash_balance": 0.0,
        "holdings_json": [{"company_id": 10, "quantity": 5.0}],
        "data_quality_flag": "OK",
    }


class _PayloadCapture(logging.Handler):
    def __init__(self, sink):
        super().__init__()
        self._sink = sink

    def emit(self, record):
        payload = debug_trace.payload_of(record)
        if payload is not None:
            self._sink.append(payload)


def _capture(enabled: bool, always_on_prefixes):
    """Attach capture handlers and configure exactly as the caller asks.

    Logger levels are set to DEBUG *after* ``configure`` because configure
    derives the level from ``enabled``; a capture handler on a WARNING-level
    logger silently collects nothing, which is the same class of invisible
    failure this module exists to catch.
    """
    trace_records: list[dict] = []
    integrity_records: list[dict] = []
    pairs = [
        (_PayloadCapture(trace_records), debug_trace.trace_logger),
        (_PayloadCapture(integrity_records), debug_trace.integrity_logger),
    ]
    saved = [(logger, logger.level) for _, logger in pairs]
    debug_trace.configure(
        enabled=enabled, always_on_prefixes=always_on_prefixes
    )
    for handler, logger in pairs:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
    try:
        yield {"trace": trace_records, "integrity": integrity_records}
    finally:
        debug_trace.configure(enabled=False, always_on_prefixes=())
        for handler, logger in pairs:
            logger.removeHandler(handler)
        for logger, level in saved:
            logger.setLevel(level)


@pytest.fixture
def shipped(monkeypatch):
    """Global tracing off; only the snapshot scope is allowlisted.

    This is the production configuration. Anything that asserts a record appears
    here is asserting it appears for a real user, not just under a test harness.
    """
    yield from _capture(enabled=False, always_on_prefixes=("snapshot",))


@pytest.fixture
def global_on():
    """The pre-existing behaviour: the global flag alone turns tracing on."""
    yield from _capture(enabled=True, always_on_prefixes=())


class TestScopeAllowlist:
    def test_allowlisted_scope_is_traced_with_global_flag_off(self, shipped):
        assert debug_trace.is_enabled() is False
        with debug_trace.trace_scope("snapshot"):
            assert debug_trace.is_enabled() is True

    def test_unlisted_scope_stays_silent_with_global_flag_off(self, shipped):
        with debug_trace.trace_scope("something-else"):
            assert debug_trace.is_enabled() is False

    def test_scope_prefix_is_cleared_after_the_scope_exits(self, shipped):
        with debug_trace.trace_scope("snapshot"):
            pass
        assert debug_trace.is_enabled() is False

    def test_trace_event_emits_inside_the_allowlisted_scope(self, shipped):
        with debug_trace.trace_scope("snapshot"):
            debug_trace.trace_event("unit", "emitted")
        assert [r["event"] for r in shipped["trace"]] == ["emitted"]

    def test_trace_event_is_silent_outside_the_allowlisted_scope(self, shipped):
        with debug_trace.trace_scope("not-allowlisted"):
            debug_trace.trace_event("unit", "dropped")
        assert shipped["trace"] == []

    def test_predicate_and_emitter_cannot_disagree(self, shipped):
        """``is_enabled()`` True must imply a record is actually emitted.

        Two copies of the enablement check drift, and a caller that sees True
        while the emitter drops the record is the worst failure a debugging tool
        can have: it reports that it is logging, and it is not.
        """
        with debug_trace.trace_scope("snapshot"):
            assert debug_trace.is_enabled() is True
            debug_trace.trace_event("unit", "agreement-check")
        assert len(shipped["trace"]) == 1

    def test_integrity_finding_emits_inside_the_allowlisted_scope(self, shipped):
        with debug_trace.trace_scope("snapshot"):
            debug_trace.integrity_finding("REPLAY_DRIFT", account_id=1)
        assert [r["event"] for r in shipped["integrity"]] == ["REPLAY_DRIFT"]

    def test_global_flag_on_overrides_an_empty_allowlist(self, global_on):
        """The allowlist is additive, not a replacement.

        Turning the global flag on must keep working exactly as it did before
        the allowlist existed, or this change would have broken every existing
        deployment that relies on ``DEBUG_TRACE_ENABLED``.
        """
        assert debug_trace.is_enabled() is True
        debug_trace.trace_event("unit", "emitted")
        assert [r["event"] for r in global_on["trace"]] == ["emitted"]

    def test_restore_carries_the_allowlist(self, monkeypatch):
        """A caller that snapshots and restores must not lose the allowlist.

        The scheduler and the job both reconfigure tracing. If restore dropped
        the allowlist, the first reconfigure in the process would silently
        disable snapshot tracing for the rest of the run.
        """
        debug_trace.configure(enabled=False, always_on_prefixes=("snapshot",))
        try:
            saved = debug_trace.snapshot()
            debug_trace.configure(enabled=True, always_on_prefixes=())
            debug_trace.restore(saved)
            with debug_trace.trace_scope("snapshot"):
                assert debug_trace.is_enabled() is True
        finally:
            debug_trace.configure(enabled=False, always_on_prefixes=())

    def test_restore_accepts_a_legacy_two_tuple(self, monkeypatch):
        """Older callers captured a 2-tuple; restoring one must not raise."""
        try:
            debug_trace.restore(("legacy", False))
        except Exception as exc:  # pragma: no cover - failure path
            pytest.fail(f"restore() rejected a 2-tuple: {exc!r}")
        assert debug_trace.is_enabled() is False


class TestShippedDefaults:
    """The tests that would have caught the reported defect."""

    def test_snapshot_scope_is_allowlisted_by_default(self):
        from config import settings

        assert "snapshot" in settings.DEBUG_TRACE_ALWAYS_ON_SCOPES

    def test_debug_file_sink_is_on_by_default(self):
        from config import settings

        assert settings.DEBUG_LOG_ENABLED is True

    def test_setup_debug_logging_actually_installs_the_allowlist(self):
        """End of the wiring chain: settings -> setup_debug_logging -> module.

        Asserting the setting exists and asserting the module honours it are
        different claims. This is the second one, and it is the one that was
        never true before.
        """
        logging_setup.setup_debug_logging()
        try:
            with debug_trace.trace_scope("snapshot"):
                assert debug_trace.is_enabled() is True
            with debug_trace.trace_scope("other"):
                assert debug_trace.is_enabled() is False
        finally:
            debug_trace.configure(enabled=False, always_on_prefixes=())


@pytest.fixture
def job_env(monkeypatch, shipped):
    """``handle_portfolio_snapshot`` against fakes, with shipped tracing config.

    Returns a dict the test mutates to steer the outcome.
    """
    state = {
        "computed_total": 1000.0,
        "previous": {
            "total_value": 900.0,
            "holdings_market_value": 900.0,
            "cash_balance": 0.0,
            "holdings_json": [],
        },
        "spike": {"message": "value moved 90%"},
        "gap_days": 0,
    }

    def _build_row(**_kwargs):
        return _snapshot_row(state["computed_total"])

    def _check_spike(_prev, _row, threshold=0.20):
        return state["spike"] if state["spike"] else None

    def _make_snapshots_repo():
        return _FakeSnapshotsRepo(state["previous"])

    async def _fill_gaps(**_kwargs):
        return state["gap_days"]

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
    monkeypatch.setattr(job_mod, "_fill_snapshot_gaps", _fill_gaps)
    monkeypatch.setattr(job_mod, "settings", fake_settings)
    monkeypatch.setattr(job_mod, "BATCH_SIZE", 100)
    return state


async def _run(state):
    return await job_mod.handle_portfolio_snapshot({"payload": {"date": FIXED_DATE}})


def _events(records, event):
    return [r for r in records if r.get("event") == event]


class TestRunBoundaries:
    """A run must be reconstructable end to end from the record stream alone."""

    @pytest.mark.asyncio
    async def test_run_is_recorded_with_the_global_flag_off(
        self, job_env, shipped
    ):
        """The end-to-end claim: shipped config, real job entry point, records.

        Global tracing is off in this fixture. Every other test in the repository
        that proves snapshot records exist turns it on first, which is exactly
        why the absence of records in production went unnoticed.
        """
        job_env["spike"] = None
        await _run(job_env)
        assert _events(shipped["trace"], "job_received")
        assert _events(shipped["trace"], "run_start")
        assert _events(shipped["trace"], "run_end")

    @pytest.mark.asyncio
    async def test_job_received_records_the_payload_date(self, job_env, shipped):
        job_env["spike"] = None
        await _run(job_env)
        received = _events(shipped["trace"], "job_received")[0]
        assert received["requested_date"] == FIXED_DATE
        assert received["payload_date_present"] is True
        assert received["trace_id"].startswith("snapshot-")

    @pytest.mark.asyncio
    async def test_run_start_names_the_target_date_and_account_count(
        self, job_env, shipped
    ):
        job_env["spike"] = None
        await _run(job_env)
        start = _events(shipped["trace"], "run_start")[0]
        assert start["snapshot_date"] == FIXED_DATE
        assert start["accounts"] == 1

    @pytest.mark.asyncio
    async def test_run_end_counts_written(self, job_env, shipped):
        job_env["spike"] = None
        await _run(job_env)
        end = _events(shipped["trace"], "run_end")[0]
        assert end["written"] == 1
        assert end["withheld"] == 0

    @pytest.mark.asyncio
    async def test_run_end_counts_the_withheld_write(self, job_env, shipped):
        """A run that withheld a write must not look like a clean run.

        Without ``withheld`` in the end record, a run that declined to persist
        an account is indistinguishable from one that had no such account.
        """
        job_env["spike"] = {"message": "value moved 90%"}
        await _run(job_env)
        end = _events(shipped["trace"], "run_end")[0]
        assert end["written"] == 0
        assert end["withheld"] == 1

    @pytest.mark.asyncio
    async def test_withheld_run_records_why_with_the_global_flag_off(
        self, job_env, shipped
    ):
        """The specific question the user asked: why was this write withheld?

        ``persisted_total is None`` is a positive claim that the write was
        deliberately withheld, not a missing field.
        """
        job_env["spike"] = {"message": "value moved 90%"}
        await _run(job_env)
        findings = shipped["integrity"]
        assert findings, "a withheld write must leave a finding"
        finding = findings[0]
        assert finding["event"] == "REPLAY_DRIFT"
        assert finding["reason"] == "spike_write_withheld"
        assert finding["persisted_total"] is None
        assert finding["replayed_total"] == 1000.0

    @pytest.mark.asyncio
    async def test_gap_repair_is_recorded_when_days_were_written(
        self, job_env, shipped
    ):
        job_env["spike"] = None
        job_env["gap_days"] = 3
        await _run(job_env)
        repairs = _events(shipped["trace"], "gap_repair")
        assert len(repairs) == 1
        assert repairs[0]["days_written"] == 3
        assert repairs[0]["account_id"] == 1

    @pytest.mark.asyncio
    async def test_silent_run_emits_no_gap_repair_record(self, job_env, shipped):
        """A no-op repair is not news; recording it would bury real repairs."""
        job_env["spike"] = None
        job_env["gap_days"] = 0
        await _run(job_env)
        assert _events(shipped["trace"], "gap_repair") == []

    @pytest.mark.asyncio
    async def test_every_record_shares_one_trace_id(self, job_env, shipped):
        """Correlatability is the whole point: one run, one id, every record."""
        job_env["spike"] = None
        await _run(job_env)
        ids = {r["trace_id"] for r in shipped["trace"]}
        assert len(ids) == 1
        next(iter(ids)).startswith("snapshot-")
