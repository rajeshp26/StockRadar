"""Tests for shared.split_sync — the latch-agnostic split-event reconciler.

The reconciler replaces the old price_ingestion_job._emit_split_events behavior
(project current portfolio_holdings + mark splits.processed). These tests pin
the new contract:
  - detection is independent of the splits.processed latch (fetches ALL rows)
  - split-event presence is decided by business fields, never key text
  - affected accounts come from the event stream (holding evidence), so an
    account that sold the split security before the job ran is still covered
  - emission is idempotent and the latch flips only after a successful append
"""
from datetime import date
from unittest.mock import MagicMock

import pytest
from postgrest.exceptions import APIError

from shared.split_sync import (
    POSITION_ANCHOR_EVENT_TYPES,
    accounts_with_holding_evidence,
    build_split_event,
    explains_spike,
    find_missing_split_events,
    holding_window_from_events,
    reconcile_split_events,
    split_event_present,
    split_events_present,
)

# ---------------------------------------------------------------------------
# Mock client helpers
# ---------------------------------------------------------------------------


def _client_with(tables: dict[str, list[list[dict]]]) -> MagicMock:
    """FIFO client: each table serves its pages in order on every .execute().

    tables: {table_name: [page1, page2, ...]}. Requests past the supplied pages
    return an empty page (len < 1000 → pagination stops). update(payload) calls
    are recorded on client.updates as (table_name, payload).
    """
    client = MagicMock()
    client.updates = []
    built = {}

    def _table(name: str):
        if name not in built:
            pages = list(tables.get(name) or [])
            t = MagicMock()
            t.select.return_value = t
            t.eq.return_value = t
            t.neq.return_value = t
            t.in_.return_value = t
            t.order.return_value = t
            t.range.return_value = t
            t.limit.return_value = t
            t.update.side_effect = (
                lambda payload, _t=t, _n=name: (client.updates.append((_n, payload)), _t)[1]
            )
            t.execute.side_effect = (
                lambda _pages=pages: MagicMock(data=_pages.pop(0) if _pages else [])
            )
            built[name] = t
        return built[name]

    client.table.side_effect = _table
    return client


def _trade_event(account_id: int, cid: int, tdate: str) -> dict:
    return {
        "event_type": "transaction_imported",
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": {
            "account_id": account_id,
            "company_id": cid,
            "activity_type": "Trade",
            "quantity": 10,
            "unit_price": 100.0,
            "net_cash_amount": -1000.0,
            "transaction_date": tdate,
        },
        "created_at": f"{tdate}T00:00:00+00:00",
    }


def _ihs_event(account_id: int, cids: list[int], created: str) -> dict:
    return {
        "event_type": "initial_holding_set",
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": {
            "cash_balance": 0,
            "net_deposits": 0,
            "holdings": [
                {"company_id": cid, "quantity": 10, "average_cost": 100.0, "total_cost": 1000.0}
                for cid in cids
            ],
        },
        "created_at": created,
    }


def _checkpoint_event(account_id: int, cids: list[int], created: str) -> dict:
    return {
        "event_type": "position_state_checkpoint",
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": {
            "cash_balance": 0,
            "net_deposits": 0,
            "holdings": [
                {"company_id": cid, "quantity": 10, "average_cost": 100.0, "total_cost": 1000.0}
                for cid in cids
            ],
        },
        "created_at": created,
    }


def _split_row(cid: int, rd: str, factor: str = "10:1") -> dict:
    return {"company_id": cid, "report_date": rd, "split_factor": factor}


# ---------------------------------------------------------------------------
# Gap detection
# ---------------------------------------------------------------------------

class TestFindMissingSplitEvents:
    def test_gap_detected_despite_processed_latch(self):
        """Regression: a split row already marked processed (the legacy latch)
        must still be re-checked — the latch is not a gate. Account 7 / 1117 was
        skipped forever by that latch."""
        client = _client_with({
            # existing split events: none for cid 1117
            "portfolio_events": [
                [],                                  # fetch_existing_split_events
                [],                                  # evidence query 1 (top-level)
                [],                                  # evidence query 2 (initial_holding_set)
            ],
        })
        splits = [_split_row(1117, "2022-06-29")]  # latch state is not in the row
        gaps, checked = find_missing_split_events(client, splits)

        assert checked == 0  # no holding evidence -> nothing owed
        assert gaps == []

    def test_gap_detected_from_event_stream_evidence(self):
        """Account 7 bought cid 1117 before the split, sold after -> still owed
        the split event even though portfolio_holdings no longer has it."""
        client = _client_with({
            "portfolio_events": [
                [],                          # existing split events for 1117
                [_trade_event(7, 1117, "2020-01-10")],  # evidence q1
                [],                          # evidence q2 (initial_holding_set)
            ],
        })
        gaps, checked = find_missing_split_events(client, [_split_row(1117, "2022-06-29")])

        assert checked == 1
        assert len(gaps) == 1
        g = gaps[0]
        assert g == {
            "company_id": 1117,
            "report_date": date(2022, 6, 29),
            "split_factor": "10:1",
            "account_id": 7,
            "evidence_date": date(2020, 1, 10),
        }

    def test_existing_event_matched_by_fields_not_key_text(self):
        """A stored split event for account 7/cid 1117 must be recognized even
        when its idempotency_key is non-standard (account 7's production repair
        used 'split_1117_2022-06-29_10_acct7')."""
        existing = [{
            "event_type": "split",
            "aggregate_id": "account_7",
            "data": {
                "company_id": 1117,
                "split_factor": "10.0",
                "report_date": "2022-06-29",
            },
            "idempotency_key": "split_1117_2022-06-29_10_acct7",
        }]
        client = _client_with({
            "portfolio_events": [
                existing,
                [_trade_event(7, 1117, "2020-01-10")],
                [],
            ],
        })
        gaps, checked = find_missing_split_events(client, [_split_row(1117, "2022-06-29")])

        assert checked == 1
        assert gaps == []  # present -> no gap

    def test_standard_key_but_wrong_fields_does_not_match(self):
        """A standard-looking key with the WRONG business fields must not mask
        the gap (key text is never authoritative)."""
        existing = [{
            "event_type": "split",
            "aggregate_id": "account_8",          # different account
            "data": {
                "company_id": 1117,
                "split_factor": "10.0",
                "report_date": "2022-06-29",
            },
            "idempotency_key": "split_1117_2022-06-29_8",
        }]
        client = _client_with({
            "portfolio_events": [
                existing,
                [_trade_event(7, 1117, "2020-01-10")],
                [],
            ],
        })
        gaps, _ = find_missing_split_events(client, [_split_row(1117, "2022-06-29")])

        assert len(gaps) == 1
        assert gaps[0]["account_id"] == 7

    def test_post_split_acquirer_excluded(self):
        """Earliest evidence AFTER the split date -> not a holder at split time
        -> no event owed."""
        client = _client_with({
            "portfolio_events": [
                [],
                [_trade_event(7, 1117, "2023-05-01")],  # bought after the split
                [],
            ],
        })
        gaps, checked = find_missing_split_events(client, [_split_row(1117, "2022-06-29")])

        assert checked == 0
        assert gaps == []

    def test_no_op_factor_skipped(self):
        client = _client_with({"portfolio_events": [[], [], []]})
        splits = [_split_row(1117, "2022-06-29", factor="1:1")]
        gaps, checked = find_missing_split_events(client, splits)

        assert checked == 0
        assert gaps == []

    def test_zero_factor_skipped(self):
        client = _client_with({"portfolio_events": [[], [], []]})
        splits = [_split_row(1117, "2022-06-29", factor="0:1")]
        gaps, checked = find_missing_split_events(client, splits)

        assert checked == 0
        assert gaps == []

    def test_max_date_filters_future_splits(self):
        client = _client_with({"portfolio_events": [[], [], []]})
        splits = [_split_row(1117, "2023-01-01", factor="2:1")]
        gaps, checked = find_missing_split_events(
            client, splits, max_date=date(2022, 12, 31))

        assert checked == 0
        assert gaps == []

    def test_account_ids_filter(self):
        client = _client_with({
            "portfolio_events": [
                [],
                [_trade_event(7, 1117, "2020-01-10"), _trade_event(8, 1117, "2020-02-01")],
                [],
            ],
        })
        gaps, checked = find_missing_split_events(
            client, [_split_row(1117, "2022-06-29")], account_ids=[8])

        assert checked == 1
        assert len(gaps) == 1
        assert gaps[0]["account_id"] == 8

    def test_company_ids_filter(self):
        client = _client_with({"portfolio_events": [[], [], []]})
        splits = [_split_row(1117, "2022-06-29"), _split_row(3117, "2023-05-01", "1:5")]
        gaps, checked = find_missing_split_events(client, splits, company_ids=[3117])

        assert checked == 0  # 1117 filtered out; 3117 has no evidence
        assert gaps == []

    def test_initial_holding_set_evidence(self):
        """An account whose only reference is inside an initial_holding_set
        holdings[] list (nested company_id) must still qualify."""
        client = _client_with({
            "portfolio_events": [
                [],                       # existing split events
                [],                       # evidence q1 (top-level company_id)
                [_ihs_event(9, [1117, 3110], "2020-03-01T00:00:00+00:00")],
            ],
        })
        gaps, checked = find_missing_split_events(client, [_split_row(1117, "2022-06-29")])

        assert checked == 1
        assert len(gaps) == 1
        assert gaps[0]["account_id"] == 9

    def test_position_state_checkpoint_evidence(self):
        client = _client_with({
            "portfolio_events": [
                [],
                [],
                [_checkpoint_event(9, [1117, 3110], "2020-03-01T00:00:00+00:00")],
            ],
        })
        gaps, checked = find_missing_split_events(client, [_split_row(1117, "2022-06-29")])

        assert checked == 1
        assert len(gaps) == 1
        assert gaps[0]["account_id"] == 9

    def test_anchor_evidence_query_pins_both_event_types(self):
        client = _client_with({"portfolio_events": [[], [], []]})
        accounts_with_holding_evidence(client, 1117)
        in_filters = [c.args for c in client.table("portfolio_events").in_.call_args_list]
        assert ("event_type", list(POSITION_ANCHOR_EVENT_TYPES)) in in_filters

    def test_multi_split_same_company(self):
        client = _client_with({
            "portfolio_events": [
                [],
                [_trade_event(7, 3131, "2015-06-01")],
                [],
                # second call: existing events still absent
                [],
                [_trade_event(7, 3131, "2015-06-01")],
                [],
            ],
        })
        splits = [
            _split_row(3131, "2016-08-19", "2:1"),
            _split_row(3131, "2023-01-20", "5:1"),
        ]
        gaps, checked = find_missing_split_events(client, splits)

        assert checked == 2
        assert len(gaps) == 2
        assert [g["report_date"] for g in gaps] == [date(2016, 8, 19), date(2023, 1, 20)]


class TestSplitEventPresent:
    def test_field_match(self):
        evs = [{
            "aggregate_id": "account_7",
            "data": {"company_id": 1117, "report_date": "2022-06-29"},
        }]
        assert split_event_present(evs, 7, 1117, date(2022, 6, 29))
        assert not split_event_present(evs, 8, 1117, date(2022, 6, 29))
        assert not split_event_present(evs, 7, 3117, date(2022, 6, 29))
        assert not split_event_present(evs, 7, 1117, date(2022, 6, 30))


# ---------------------------------------------------------------------------
# Event construction
# ---------------------------------------------------------------------------

class TestBuildSplitEvent:
    def test_shape_matches_legacy_emitter(self):
        gap = {
            "company_id": 1117,
            "report_date": date(2022, 6, 29),
            "split_factor": "10:1",
            "account_id": 7,
        }
        ev = build_split_event(gap)

        assert ev["event_type"] == "split"
        assert ev["event_version"] == 1
        assert ev["aggregate_id"] == "account_7"
        assert ev["aggregate_type"] == "account"
        assert ev["data"] == {
            "company_id": 1117,
            "split_factor": "10.0",
            "report_date": "2022-06-29",
        }
        assert ev["metadata"] == {}
        assert ev["idempotency_key"] == "split_1117_2022-06-29_7"

    def test_reverse_split_factor_as_string_number(self):
        gap = {
            "company_id": 3117,
            "report_date": date(2023, 5, 1),
            "split_factor": "1:5",
            "account_id": 9,
        }
        ev = build_split_event(gap)
        assert ev["data"]["split_factor"] == "0.2"  # replay's _decimal() parses this


# ---------------------------------------------------------------------------
# reconcile_split_events orchestration
# ---------------------------------------------------------------------------

class TestReconcileSplitEvents:
    def test_dry_run_discovers_without_writing(self):
        client = _client_with({
            "splits": [[_split_row(1117, "2022-06-29")]],
            "portfolio_events": [
                [],
                [_trade_event(7, 1117, "2020-01-10")],
                [],
            ],
        })
        report = reconcile_split_events(client, dry_run=True)

        assert report.error is None
        assert report.missing_events == 1
        assert report.emitted_events == 0
        assert report.companies_with_gaps == {1117}
        # no latch flip, no event append on dry-run
        assert client.updates == []

    def test_apply_emits_and_marks_processed(self):
        from shared import split_sync

        client = _client_with({
            "splits": [[_split_row(1117, "2022-06-29")]],
            "portfolio_events": [
                [],
                [_trade_event(7, 1117, "2020-01-10")],
                [],
            ],
        })
        appended = []
        original_append = split_sync.EventStore

        class FakeEventStore:
            def __init__(self, client=None):
                self.client = client

            def append_events_batch(self, events):
                appended.extend(events)
                return events

        split_sync.EventStore = FakeEventStore
        try:
            report = reconcile_split_events(client, dry_run=False)
        finally:
            split_sync.EventStore = original_append

        assert report.error is None
        assert report.emitted_events == 1
        assert len(appended) == 1
        assert appended[0]["aggregate_id"] == "account_7"
        # latch flipped per company AFTER a successful append
        assert ("splits", {"processed": True}) in client.updates

    def test_duplicate_key_failure_sets_error_no_latch(self):
        from shared import split_sync

        client = _client_with({
            "splits": [[_split_row(1117, "2022-06-29")]],
            "portfolio_events": [
                [],
                [_trade_event(7, 1117, "2020-01-10")],
                [],
            ],
        })
        original_append = split_sync.EventStore

        class DupStore:
            def __init__(self, client=None):
                self.client = client

            def append_events_batch(self, events):
                raise APIError({
                    "code": "23505",
                    "message": "duplicate key value violates unique constraint",
                    "details": "",
                })

        split_sync.EventStore = DupStore
        try:
            report = reconcile_split_events(client, dry_run=False)
        finally:
            split_sync.EventStore = original_append

        assert report.error is not None
        assert "duplicate-key" in report.error
        assert report.emitted_events == 0
        assert client.updates == []  # latch untouched -> gap re-detected next run

    def test_non_duplicate_failure_keeps_unprocessed(self):
        from shared import split_sync

        client = _client_with({
            "splits": [[_split_row(1117, "2022-06-29")]],
            "portfolio_events": [
                [],
                [_trade_event(7, 1117, "2020-01-10")],
                [],
            ],
        })
        original_append = split_sync.EventStore

        class BrokenStore:
            def __init__(self, client=None):
                self.client = client

            def append_events_batch(self, events):
                raise RuntimeError("provider down")

        split_sync.EventStore = BrokenStore
        try:
            report = reconcile_split_events(client, dry_run=False)
        finally:
            split_sync.EventStore = original_append

        assert report.error is not None
        assert "failed to append split events" in report.error
        assert report.emitted_events == 0
        assert client.updates == []

    def test_fetch_splits_failure_sets_error(self):
        client = MagicMock()
        client.table.side_effect = RuntimeError("db down")
        report = reconcile_split_events(client, dry_run=True)
        assert report.error is not None
        assert "failed to fetch splits" in report.error


# ---------------------------------------------------------------------------
# Pure integrity helpers (shared with verify_snapshot_history.py)
# ---------------------------------------------------------------------------

class TestHoldingWindowFromEvents:
    def test_excludes_split_events(self):
        events = [
            _trade_event(7, 1117, "2020-01-10"),
            {
                "event_type": "split",
                "aggregate_id": "account_7",
                "data": {"company_id": 1117, "split_factor": "10.0", "report_date": "2022-06-29"},
            },
            _trade_event(7, 1117, "2023-05-05"),
        ]
        window = holding_window_from_events(events, 1117)
        assert window == (date(2020, 1, 10), date(2023, 5, 5))

    def test_nested_ihs_company_detected(self):
        events = [_ihs_event(9, [1117], "2020-03-01T00:00:00+00:00")]
        window = holding_window_from_events(events, 1117)
        assert window == (date(2020, 3, 1), date(2020, 3, 1))

    def test_no_evidence_returns_none(self):
        events = [_trade_event(7, 9999, "2020-01-10")]
        assert holding_window_from_events(events, 1117) is None


class TestSplitEventsPresent:
    def test_field_match(self):
        events = [{
            "event_type": "split",
            "aggregate_id": "account_7",
            "data": {"company_id": 1117, "split_factor": "10.0", "report_date": "2022-06-29"},
        }]
        assert split_events_present(events, 1117, date(2022, 6, 29))
        assert not split_events_present(events, 1117, date(2022, 6, 30))
        assert not split_events_present(events, 3117, date(2022, 6, 29))


class TestExplainsSpike:
    SPIKE = date(2024, 12, 23)

    def test_split_never_explains(self):
        events = [{
            "event_type": "split",
            "data": {"company_id": 10, "split_factor": "2.0", "report_date": "2024-12-23"},
            "created_at": "2024-12-23T00:00:00+00:00",
        }]
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is False

    def test_initial_holding_set_explains(self):
        events = [_ihs_event(9, [10], "2024-12-22T00:00:00+00:00")]
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is True

    def test_position_state_checkpoint_explains(self):
        events = [_checkpoint_event(9, [10], "2024-12-22T00:00:00+00:00")]
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is True

    def test_internal_security_transfer_above_materiality(self):
        events = [{
            "event_type": "transaction_imported",
            "data": {
                "company_id": 10,
                "activity_type": "InternalSecurityTransfer",
                "quantity": 1000,
                "unit_price": 120.0,
                "transaction_date": "2024-12-23",
            },
        }]
        # impact = 1000 * 120 = 120000 >= 0.10 * 100000
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is True

    def test_internal_security_transfer_below_materiality(self):
        events = [{
            "event_type": "transaction_imported",
            "data": {
                "company_id": 10,
                "activity_type": "InternalSecurityTransfer",
                "quantity": 10,
                "unit_price": 120.0,
                "transaction_date": "2024-12-23",
            },
        }]
        # impact = 1200 < 10000
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is False

    def test_trade_never_explains(self):
        events = [_trade_event(7, 10, "2024-12-23")]
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is False

    def test_outside_tolerance_window(self):
        events = [{
            "event_type": "transaction_imported",
            "data": {
                "company_id": 10,
                "activity_type": "InternalSecurityTransfer",
                "quantity": 1000,
                "unit_price": 120.0,
                "transaction_date": "2024-12-01",
            },
        }]
        assert explains_spike(events, self.SPIKE, delta=100_000.0) is False