"""Tests for the ReplayEngine tracing instrumentation.

The point of these assertions is not that ``trace_event`` was called -- that is
almost an implementation detail. It is that the emitted payload carries the
*reconciliation numbers* needed to answer the question the seam-drop defect
raised: how many rows were fetched, how many were actually replayed, and where
the difference went.

Without ``fetched``/``matched``/``filtered_out`` a dropped row is invisible: the
engine simply reports a shorter holding list and looks internally consistent.
"""

import logging
from datetime import date
from decimal import Decimal

import pytest

from shared import debug_trace
from shared.replay_engine import ReplayEngine


def _event(
    event_id: int,
    event_type: str,
    account_id: int = 1,
    effective: str | None = None,
    **data,
):
    """A single account event in the shape the engine consumes."""
    payload = {
        "account_id": account_id,
        "company_id": 10,
        "activity_type": "Trade",
        "symbol": "AAPL",
        "quantity": 10,
        "unit_price": 100.0,
        "net_cash_amount": -1000.0,
        "currency": "USD",
    }
    payload.update(data)
    return {
        "id": event_id,
        "event_type": event_type,
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": payload,
        "created_at": (effective or "2026-07-01") + "T00:00:00+00:00",
    }


class _StubEventStore:
    """Minimal store: ``replay_to_date`` only needs ``get_all_events``."""

    def __init__(self, events):
        self._events = events

    def get_all_events(self, **_kwargs):
        return list(self._events)


class _PayloadCapture(logging.Handler):
    """Collects the structured payload off each emitted trace record."""

    def __init__(self, sink: list[dict]):
        super().__init__()
        self._sink = sink

    def emit(self, record):
        payload = debug_trace.payload_of(record)
        if payload is not None:
            self._sink.append(payload)


@pytest.fixture
def capture_trace():
    """Capture emitted trace records and return the parsed payloads."""
    records: list[dict] = []
    handler = _PayloadCapture(records)
    logger = debug_trace.trace_logger
    logger.addHandler(handler)
    old_level, old_enabled = logger.level, debug_trace.is_enabled()
    logger.setLevel(logging.DEBUG)
    debug_trace.configure(enabled=True)
    try:
        yield records
    finally:
        debug_trace.configure(enabled=old_enabled)
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def _latest(records):
    """The most recent payload for a given event name."""
    return [r for r in records if r.get("event") == "replay_to_date"][-1]


class TestReplayTracingDisabled:
    def test_no_records_when_tracing_off(self):
        """Disabled tracing must not touch the logger at all (repositories import
        this on every query, so the off-path has to stay free)."""
        records: list[dict] = []
        handler = _PayloadCapture(records)
        debug_trace.trace_logger.addHandler(handler)
        old_level = debug_trace.trace_logger.level
        debug_trace.trace_logger.setLevel(logging.DEBUG)
        debug_trace.configure(enabled=False)
        try:
            engine = ReplayEngine(_StubEventStore([_event(1, "transaction_imported")]))
            engine.replay_to_date(1, date(2026, 7, 6))
        finally:
            debug_trace.trace_logger.removeHandler(handler)
            debug_trace.trace_logger.setLevel(old_level)
        assert records == []


class TestReplayTracingPayload:
    def test_emits_reconciliation_counts(self, capture_trace):
        events = [
            _event(1, "transaction_imported"),
            _event(2, "transaction_imported"),
        ]
        engine = ReplayEngine(_StubEventStore(events))
        engine.replay_to_date(1, date(2026, 7, 6))

        payload = _latest(capture_trace)
        assert payload["layer"] == "replay_engine"
        assert payload["account_id"] == 1
        assert payload["target_date"] == "2026-07-06"
        # Both events were fetched and both replayed: nothing lost at the seam.
        assert payload["fetched"] == 2
        assert payload["matched"] == 2
        assert payload["filtered_out"] == 0
        assert payload["handled_total"] == 2
        assert payload["handled_by_type"] == {"transaction_imported": 2}
        assert payload["skipped_unknown"] == []

    def test_reports_rows_dropped_by_account_filter(self, capture_trace):
        """A row belonging to another account must be accounted for, not vanish.

        This is the exact shape of the seam-drop defect: the engine sees fewer
        rows and has no record of why.
        """
        events = [
            _event(1, "transaction_imported", account_id=1),
            _event(2, "transaction_imported", account_id=2),
            _event(3, "transaction_imported", account_id=1),
        ]
        engine = ReplayEngine(_StubEventStore(events))
        engine.replay_to_date(1, date(2026, 7, 6))

        payload = _latest(capture_trace)
        assert payload["fetched"] == 3
        assert payload["matched"] == 2
        assert payload["filtered_out"] == 1

    def test_reports_rows_dropped_by_date_cutoff(self, capture_trace):
        """Events after the target date are excluded, and the count says so."""
        events = [
            _event(1, "transaction_imported", effective="2026-07-01"),
            _event(2, "transaction_imported", effective="2026-09-01"),
        ]
        engine = ReplayEngine(_StubEventStore(events))
        engine.replay_to_date(1, date(2026, 7, 6))

        payload = _latest(capture_trace)
        assert payload["fetched"] == 2
        assert payload["matched"] == 1
        assert payload["filtered_out"] == 1

    def test_records_unknown_event_types(self, capture_trace):
        """An unhandled event type is a silent state change if not reported.

        ``getattr`` returning ``None`` means the event is dropped from the
        replay entirely. That is a real loss of state, so it must be visible.
        """
        events = [
            _event(1, "transaction_imported"),
            _event(2, "some_future_event_we_do_not_handle"),
        ]
        engine = ReplayEngine(_StubEventStore(events))
        engine.replay_to_date(1, date(2026, 7, 6))

        payload = _latest(capture_trace)
        assert payload["handled_total"] == 1
        assert payload["skipped_unknown"] == ["some_future_event_we_do_not_handle"]

    def test_includes_final_state_and_id_fingerprint(self, capture_trace):
        events = [_event(7, "transaction_imported"), _event(8, "transaction_imported")]
        engine = ReplayEngine(_StubEventStore(events))
        engine.replay_to_date(1, date(2026, 7, 6))

        payload = _latest(capture_trace)
        assert payload["final_holdings"] == 1
        assert payload["cash_balance"] == Decimal("-2000.0")
        # Fingerprint lets two runs be compared even when counts coincide.
        assert payload["count"] == 2
        assert payload["first"] == ["7", "8"]
        assert payload["fingerprint"] == debug_trace.fingerprint(["7", "8"])

    def test_empty_replay_still_emits(self, capture_trace):
        """A replay that matched nothing must still leave a trace.

        Silence is indistinguishable from a dropped row, which is the whole
        reason this instrumentation exists.
        """
        engine = ReplayEngine(_StubEventStore([]))
        engine.replay_to_date(1, date(2026, 7, 6))

        payload = _latest(capture_trace)
        assert payload["fetched"] == 0
        assert payload["matched"] == 0
        assert payload["handled_total"] == 0

    def test_trace_id_is_carried_into_the_payload(self, capture_trace):
        """The payload must carry the ambient trace id, or it cannot be joined
        to the repository records that produced it."""
        with debug_trace.trace_scope("replay-test"):
            engine = ReplayEngine(_StubEventStore([_event(1, "transaction_imported")]))
            engine.replay_to_date(1, date(2026, 7, 6))
            scoped = debug_trace.current_trace_id()

        payload = _latest(capture_trace)
        assert payload["trace_id"] == scoped
        assert payload["trace_id"].startswith("replay-test-")
