from datetime import datetime
from typing import Any

from database import supabase
from supabase import Client


class EventStore:
    """Immutable event log for the portfolio domain.

    Events are append-only. Idempotency is enforced via a unique constraint
    on idempotency_key (NULL keys are ignored, allowing non-idempotent events).
    """

    TABLE = "portfolio_events"

    def __init__(self, client: Client = supabase):
        self.client = client

    def append_event(
        self,
        event_type: str,
        aggregate_id: str,
        aggregate_type: str,
        data: dict,
        metadata: dict | None = None,
        idempotency_key: str | None = None,
        event_version: int = 1,
    ) -> dict:
        row = {
            "event_type": event_type,
            "event_version": event_version,
            "aggregate_id": aggregate_id,
            "aggregate_type": aggregate_type,
            "data": data,
            "metadata": metadata or {},
            "idempotency_key": idempotency_key,
        }
        try:
            res = self.client.table(self.TABLE).insert(row).execute()
            return res.data[0]
        except Exception as e:
            err_str = str(e).lower()
            if "duplicate key" in err_str and idempotency_key:
                existing = self._get_by_idempotency_key(idempotency_key)
                if existing:
                    return existing
            raise

    def append_events_batch(
        self,
        events: list[dict[str, Any]],
    ) -> list[dict]:
        if not events:
            return []
        try:
            res = self.client.table(self.TABLE).insert(events).execute()
            return res.data or []
        except Exception as e:
            err_str = str(e).lower()
            if "duplicate key" in err_str:
                deduped = []
                seen_keys = set()
                for ev in events:
                    key = ev.get("idempotency_key")
                    if key:
                        if key in seen_keys:
                            continue
                        existing = self._get_by_idempotency_key(key)
                        if existing:
                            deduped.append(existing)
                            seen_keys.add(key)
                            continue
                        seen_keys.add(key)
                    deduped.append(ev)
                if deduped:
                    return self.client.table(self.TABLE).insert(deduped).execute().data or []
            raise

    def get_all_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 10000,
    ) -> list[dict]:
        """Fetch all matching events with pagination handling for large datasets."""
        PAGE_SIZE = 1000
        all_events = []
        offset = 0

        while True:
            query = (
                self.client.table(self.TABLE)
                .select("*")
                .order("created_at")
                .range(offset, offset + PAGE_SIZE - 1)
            )

            if aggregate_type:
                query = query.eq("aggregate_type", aggregate_type)
            if aggregate_id:
                query = query.eq("aggregate_id", aggregate_id)
            if event_type:
                query = query.eq("event_type", event_type)
            if since:
                query = query.gte("created_at", since.isoformat())

            res = query.execute()
            batch = res.data or []
            all_events.extend(batch)
            if len(batch) < PAGE_SIZE or (limit and len(all_events) >= limit):
                break
            offset += PAGE_SIZE

        if limit and len(all_events) > limit:
            all_events = all_events[:limit]

        return all_events

    def get_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        query = self.client.table(self.TABLE).select("*").order("created_at")

        if aggregate_type:
            query = query.eq("aggregate_type", aggregate_type)
        if aggregate_id:
            query = query.eq("aggregate_id", aggregate_id)
        if event_type:
            query = query.eq("event_type", event_type)
        if since:
            query = query.gte("created_at", since.isoformat())

        res = query.execute()
        return res.data or []

    def count_orphan_events(
        self,
        reference_table: str = "portfolio_transactions",
        join_column: str = "import_batch_id",
        since: datetime | None = None,
    ) -> int:
        """Count events whose idempotency_key references a non-existent transaction.
        
        Used by reconciliation to detect dual-write failures.
        """
        query = (
            self.client.table(self.TABLE)
            .select("id, idempotency_key, created_at")
            .is_("metadata->>rollback_reason", "null")
            .neq("idempotency_key", "")
            .not_.is_("idempotency_key", "null")
        )
        if since:
            query = query.gte("created_at", since.isoformat())

        res = query.execute()
        orphans = 0
        for ev in (res.data or []):
            key = ev.get("idempotency_key", "")
            if not key or "_" not in key:
                continue
            parts = key.rsplit("_", 1)
            lookup_key = f"%{parts[0]}%"
            txn_query = (
                self.client.table(reference_table)
                .select("id")
                .ilike(join_column, lookup_key)
                .limit(1)
                .execute()
            )
            if not txn_query.data:
                orphans += 1
        return orphans

    def get_recent_events(self, limit: int = 20) -> list[dict]:
        res = (
            self.client.table(self.TABLE)
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []

    def get_earliest_event_date(self, account_id: int) -> str | None:
        """Get the earliest event date for an account.

        Events use aggregate_id format 'account_{id}' and store dates in
        data->>'transaction_date' or data->>'date'.
        """
        aggregate_id = f"account_{account_id}"
        res = (
            self.client.table(self.TABLE)
            .select("data")
            .eq("aggregate_id", aggregate_id)
            .order("created_at")
            .limit(1)
            .execute()
        )
        if res.data:
            data = res.data[0].get("data", {})
            return (
                data.get("transaction_date")
                or data.get("date")
                or data.get("effective_date")
            )
        return None

    def _get_by_idempotency_key(self, key: str) -> dict | None:
        res = (
            self.client.table(self.TABLE)
            .select("*")
            .eq("idempotency_key", key)
            .limit(1)
            .execute()
        )
        if res.data:
            return res.data[0]
        return None
