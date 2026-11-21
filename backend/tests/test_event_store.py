"""Tests for EventStore: idempotency, dual-write, and orphan detection."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from infrastructure.repositories.event_store import EventStore


class TestEventAppend:
    def test_append_event_creates_row(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt-1", "event_type": "test_event"}]
        )
        result = store.append_event(
            event_type="test_event",
            aggregate_id="account_1",
            aggregate_type="account",
            data={"key": "value"},
        )
        assert result["event_type"] == "test_event"
        assert result["id"] == "evt-1"

    def test_append_event_with_idempotency_key(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        key = f"import_{uuid4()}_0"

        # First call succeeds
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt-1", "idempotency_key": key}]
        )
        first = store.append_event(
            event_type="tx_imported",
            aggregate_id="account_1",
            aggregate_type="account",
            data={},
            idempotency_key=key,
        )
        assert first["id"] == "evt-1"

        # Second call with same key: insert fails with duplicate; _get_by_idempotency_key returns existing
        from postgrest.exceptions import APIError
        dup_error = APIError({"code": "23505", "message": "duplicate key value violates unique constraint", "details": ""})
        # Reset the mock chain: insert fails, select path succeeds
        mock_supabase_client.reset_mock()
        mock_table = MagicMock()
        mock_supabase_client.table.return_value = mock_table

        def insert_side_effect(*a, **kw):
            raise dup_error

        mock_table.insert.return_value.execute.side_effect = insert_side_effect
        mock_table.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt-1", "idempotency_key": key}]
        )
        second = store.append_event(
            event_type="tx_imported",
            aggregate_id="account_1",
            aggregate_type="account",
            data={},
            idempotency_key=key,
        )
        assert second["id"] == "evt-1"

    def test_append_events_batch_empty(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        result = store.append_events_batch([])
        assert result == []

    def test_append_events_batch_all_succeed(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        events = [
            {"event_type": "tx_imported", "aggregate_id": "account_1",
             "aggregate_type": "account", "data": {"tx": 1},
             "idempotency_key": f"k_{i}"}
            for i in range(3)
        ]
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=events
        )
        result = store.append_events_batch(events)
        assert len(result) == 3
    def test_append_events_batch_all_keys_existing_returns_existing(self, mock_supabase_client):
        from postgrest.exceptions import APIError

        store = EventStore(client=mock_supabase_client)
        events = [
            {"event_type": "split", "aggregate_id": "account_9",
             "aggregate_type": "account", "data": {},
             "idempotency_key": f"split_133_1996-08-09_{i}"}
            for i in range(2)
        ]
        dup_error = APIError({"code": "23505", "message": "duplicate key value violates unique constraint", "details": ""})

        mock_supabase_client.reset_mock()
        mock_table = MagicMock()
        mock_supabase_client.table.return_value = mock_table

        key_to_row = {
            e["idempotency_key"]: {"id": f"evt-{i}", "idempotency_key": e["idempotency_key"]}
            for i, e in enumerate(events)
        }

        def eq_side_effect(col, val):
            lim = MagicMock()
            lim.limit.return_value.execute.return_value = MagicMock(
                data=[key_to_row[val]] if val in key_to_row else []
            )
            return lim

        mock_table.select.return_value.eq.side_effect = eq_side_effect

        insert_payloads = []
        def insert_side_effect(rows):
            insert_payloads.append(rows)
            builder = MagicMock()

            def execute_side_effect():
                raise dup_error

            builder.execute.side_effect = execute_side_effect
            return builder

        mock_table.insert.side_effect = insert_side_effect

        result = store.append_events_batch(events)

        # All keys already existed: existing rows returned, nothing re-inserted.
        assert len(result) == 2
        assert {r["idempotency_key"] for r in result} == {e["idempotency_key"] for e in events}
        assert len(insert_payloads) == 1  # only the original (failed) full-batch insert

    def test_append_events_batch_mixed_existing_and_new(self, mock_supabase_client):
        from postgrest.exceptions import APIError

        store = EventStore(client=mock_supabase_client)
        existing = {"event_type": "split", "aggregate_id": "account_9",
                    "aggregate_type": "account", "data": {},
                    "idempotency_key": "split_133_1996-08-09_9"}
        new_event = {"event_type": "split", "aggregate_id": "account_10",
                     "aggregate_type": "account", "data": {},
                     "idempotency_key": "split_133_1996-08-09_10"}
        events = [existing, new_event]
        dup_error = APIError({"code": "23505", "message": "duplicate key value violates unique constraint", "details": ""})

        mock_supabase_client.reset_mock()
        mock_table = MagicMock()
        mock_supabase_client.table.return_value = mock_table

        key_to_row = {
            "split_133_1996-08-09_9": {"id": "evt-existing", "idempotency_key": "split_133_1996-08-09_9"},
        }

        def eq_side_effect(col, val):
            lim = MagicMock()
            lim.limit.return_value.execute.return_value = MagicMock(
                data=[key_to_row[val]] if val in key_to_row else []
            )
            return lim

        mock_table.select.return_value.eq.side_effect = eq_side_effect

        insert_payloads = []
        def insert_side_effect(rows):
            insert_payloads.append(rows)
            builder = MagicMock()

            def execute_side_effect():
                if len(insert_payloads) == 1:
                    raise dup_error
                return MagicMock(data=rows)

            builder.execute.side_effect = execute_side_effect
            return builder

        mock_table.insert.side_effect = insert_side_effect

        result = store.append_events_batch(events)

        # Existing row returned as-is; only the genuinely new row was re-inserted.
        assert len(result) == 2
        assert {r["idempotency_key"] for r in result} == {"split_133_1996-08-09_9", "split_133_1996-08-09_10"}
        assert len(insert_payloads) == 2
        assert insert_payloads[0] == events
        assert insert_payloads[1] == [new_event]


class TestDualWriteRollback:
    """Dual-write atomicity and orphan detection."""

    def test_orphan_detection_zero_when_no_events(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.select.return_value.is_.return_value.neq.return_value.not_.is_.return_value.execute.return_value = MagicMock(data=[])
        count = store.count_orphan_events()
        assert count == 0

    def test_orphan_detection_finds_missing_transaction(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        batch_id = uuid4()

        # Event exists with idempotency_key
        mock_supabase_client.table.return_value.select.return_value.is_.return_value.neq.return_value.not_.is_.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "evt-orphan",
                "idempotency_key": f"import_{batch_id}_0",
                "created_at": datetime.now(UTC).isoformat(),
            }]
        )

        # Transaction lookup returns nothing → orphan
        mock_supabase_client.table.return_value.select.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[])

        count = store.count_orphan_events()
        assert count == 1

    def test_orphan_detection_skips_when_transaction_exists(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        batch_id = uuid4()

        mock_supabase_client.table.return_value.select.return_value.is_.return_value.neq.return_value.not_.is_.return_value.execute.return_value = MagicMock(
            data=[{
                "id": "evt-ok",
                "idempotency_key": f"import_{batch_id}_0",
                "created_at": datetime.now(UTC).isoformat(),
            }]
        )

        # Transaction lookup finds a row → not orphan
        mock_supabase_client.table.return_value.select.return_value.ilike.return_value.limit.return_value.execute.return_value = MagicMock(data=[{"id": 1}])

        count = store.count_orphan_events()
        assert count == 0


class TestEventQuery:
    def test_get_events_by_aggregate(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_result = MagicMock(data=[
            {"id": "1", "aggregate_id": "account_1"},
            {"id": "2", "aggregate_id": "account_1"},
        ])
        mock_supabase_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = mock_result
        events = store.get_events(aggregate_id="account_1")
        assert len(events) == 2

    def test_get_events_empty(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
        events = store.get_events(aggregate_id="nonexistent")
        assert events == []

    def test_get_recent_events(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[{"id": "recent"}]
        )
        recent = store.get_recent_events(limit=1)
        assert len(recent) == 1
        assert recent[0]["id"] == "recent"


class TestGetAllEventsDeterministicOrdering:
    """Deterministic pagination: (created_at, id) — regression for the replay seam-drop.

    Root cause of the account_9 daily-snapshot corruption (09-13/15/18): ordering
    by created_at ONLY lets a ~500-row same-timestamp tie group re-resolve between
    adjacent page queries, dropping/duplicating straddling rows at the PAGE_SIZE
    boundary (probes #13/#14). The deterministic 'id' tiebreak must be present in
    every pagination loop and single-row ordering query.
    """

    def _table(self, mock_supabase_client):
        return mock_supabase_client.table.return_value

    def test_get_all_events_orders_by_created_at_then_id_every_page(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        # Page 1 full (1000 rows), page 2 short (1 row) -> loop terminates after 2 pages.
        table.execute.side_effect = [
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000)]),
            MagicMock(data=[{"id": "tail"}]),
        ]
        events = store.get_all_events(aggregate_type="account")
        assert len(events) == 1001

        order_args = [c.args[0] for c in table.order.call_args_list]
        # Both pages must request created_at followed by the id tiebreak.
        assert order_args == ["created_at", "id", "created_at", "id"]

    def test_get_all_events_pagination_advances_offsets(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.side_effect = [
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000)]),
            MagicMock(data=[]),
        ]
        events = store.get_all_events(aggregate_type="account")
        assert len(events) == 1000
        assert [c.args for c in table.range.call_args_list] == [(0, 999), (1000, 1999)]

    def test_get_events_orders_by_created_at_then_id(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.return_value = MagicMock(data=[{"id": "e1"}, {"id": "e2"}])
        events = store.get_events(aggregate_type="account")
        assert len(events) == 2
        assert [c.args[0] for c in table.order.call_args_list] == ["created_at", "id"]

    def test_get_recent_events_orders_by_created_at_desc_then_id_desc(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.return_value = MagicMock(data=[{"id": "recent"}])
        events = store.get_recent_events(limit=1)
        assert len(events) == 1
        assert [
            (c.args[0], c.kwargs.get("desc", False)) for c in table.order.call_args_list
        ] == [("created_at", True), ("id", True)]

    def test_get_earliest_event_date_orders_by_created_at_then_id(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.return_value = MagicMock(
            data=[{"data": {"transaction_date": "2021-02-08"}}]
        )
        earliest = store.get_earliest_event_date(9)
        assert earliest == "2021-02-08"
        assert [c.args[0] for c in table.order.call_args_list] == ["created_at", "id"]


class TestGetEventsHonoursItsLimit:
    """`get_events` accepted a `limit` and never applied it.

    The second, hand-written query returned whatever PostgREST allowed
    (`db-max-rows`, 1000 by default), so `get_events(limit=10000)` returned 1000
    of 2724 rows. `backfill_events_from_transactions` built its dedupe set from
    that call, which meant every account outside the returned prefix looked
    event-less and got a second copy of its history on the next run.
    """

    def _table(self, mock_supabase_client):
        return mock_supabase_client.table.return_value

    def test_limit_is_applied(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.side_effect = [
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000)]),
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000, 2000)]),
        ]
        events = store.get_events(event_type="transaction_imported", limit=1500)
        assert len(events) == 1500
        assert [c.args for c in table.range.call_args_list] == [(0, 999), (1000, 1999)]

    def test_default_limit_is_applied(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.return_value = MagicMock(data=[{"id": f"e{i}"} for i in range(1000)])
        events = store.get_events(aggregate_type="account")
        assert len(events) == 100

    def test_limit_none_pages_the_whole_log(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.side_effect = [
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000)]),
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000, 2000)]),
            MagicMock(data=[{"id": f"e{i}"} for i in range(2000, 2724)]),
        ]
        events = store.get_events(event_type="transaction_imported", limit=None)
        assert len(events) == 2724
        assert [c.args for c in table.range.call_args_list] == [
            (0, 999),
            (1000, 1999),
            (2000, 2999),
        ]

    def test_pages_until_the_matching_set_is_exhausted(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        table = self._table(mock_supabase_client)
        table.execute.side_effect = [
            MagicMock(data=[{"id": f"e{i}"} for i in range(1000)]),
            MagicMock(data=[]),
        ]
        events = store.get_events(aggregate_id="account_10", limit=10000)
        assert len(events) == 1000
        assert [c.args for c in table.range.call_args_list] == [(0, 999), (1000, 1999)]


class TestStateImportBackdatingGuard:
    def test_rejects_projection_import_dated_before_capture(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        with pytest.raises(ValueError, match="predates its capture date"):
            store.append_event(
                event_type="initial_holding_set",
                aggregate_id="account_10",
                aggregate_type="account",
                data={"effective_date": "2020-01-01"},
                metadata={"source": "portfolio_holdings", "backfill": True},
            )
        mock_supabase_client.table.assert_not_called()

    def test_accepts_projection_import_dated_today(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt-1"}]
        )
        captured = datetime.now(UTC).date().isoformat()
        result = store.append_event(
            event_type="initial_holding_set",
            aggregate_id="account_10",
            aggregate_type="account",
            data={"effective_date": captured},
            metadata={"source": "portfolio_holdings", "backfill": True},
        )
        assert result["id"] == "evt-1"

    def test_accepts_transaction_backfill_with_historical_date(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt-2"}]
        )
        result = store.append_event(
            event_type="transaction_imported",
            aggregate_id="account_1",
            aggregate_type="account",
            data={"transaction_date": "2021-02-08"},
            metadata={"backfill": True, "entry_source": "csv_import"},
        )
        assert result["id"] == "evt-2"

    def test_batch_rejects_backdated_projection_import(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        stale = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        with pytest.raises(ValueError, match="predates its capture date"):
            store.append_events_batch([
                {
                    "event_type": "initial_holding_set",
                    "aggregate_id": "account_11",
                    "aggregate_type": "account",
                    "data": {"effective_date": stale},
                    "metadata": {"source": "portfolio_holdings", "backfill": True},
                }
            ])
        mock_supabase_client.table.assert_not_called()

    def test_rejects_backdated_checkpoint_without_provenance_metadata(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        with pytest.raises(ValueError, match="position_state_checkpoint"):
            store.append_event(
                event_type="position_state_checkpoint",
                aggregate_id="account_12",
                aggregate_type="account",
                data={"effective_date": "2020-01-01", "holdings": []},
            )
        mock_supabase_client.table.assert_not_called()

    def test_accepts_checkpoint_dated_today(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
            data=[{"id": "evt-3"}]
        )
        captured = datetime.now(UTC).date().isoformat()
        result = store.append_event(
            event_type="position_state_checkpoint",
            aggregate_id="account_12",
            aggregate_type="account",
            data={"effective_date": captured, "holdings": []},
        )
        assert result["id"] == "evt-3"
