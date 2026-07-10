"""Tests for EventStore: idempotency, dual-write, and orphan detection."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
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
                "created_at": datetime.now(timezone.utc).isoformat(),
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
                "created_at": datetime.now(timezone.utc).isoformat(),
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
