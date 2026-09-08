"""Tests for EventStore: idempotency, dual-write, and orphan detection."""

from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

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
