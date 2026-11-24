from collections import Counter
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

from database import supabase
from shared import debug_trace
from supabase import Client

# A state import copied from a materialised projection reflects the portfolio as of the
# moment it was captured, so its effective date IS the capture date. Event types carrying a
# genuine historical fact (transaction_imported) are deliberately excluded: their dates are
# real, and are legitimately older than the import that replays them.
PROJECTION_IMPORT_SOURCE = "portfolio_holdings"

# Captured state, as opposed to recorded history. Checkpoints reset the account on replay
# instead of adding to it, and are structurally incapable of being backdated.
CHECKPOINT_EVENT_TYPE = "position_state_checkpoint"

# PostgREST puts `in.(...)` filters in the GET query string. With real CSV keys
# (51 chars) a 200-key chunk builds a ~10 KB URL and Supabase returns 414
# "URI too long" — reproduced against the local stack (150 keys OK, 200 fail).
# Pack by encoded length instead of a fixed count so longer keys cannot
# silently push a chunk over the proxy limit.
MAX_IDEMPOTENCY_FILTER_CHARS = 4000


def _pack_idempotency_key_chunks(keys: list[str]) -> Iterator[list[str]]:
    """Yield chunks whose estimated `in.(...)` filter stays under the URI budget."""
    chunk: list[str] = []
    size = 0
    for key in keys:
        # Separators and parens are percent-encoded as %2C/%28/%29; allow
        # generous headroom plus the select/filter/table-path overhead.
        cost = len(key) + 4
        if chunk and size + cost > MAX_IDEMPOTENCY_FILTER_CHARS:
            yield chunk
            chunk, size = [], 0
        chunk.append(key)
        size += cost
    if chunk:
        yield chunk


def _assert_state_import_not_backdated(event: dict[str, Any], captured_on: date) -> None:
    """Reject a projection-sourced state import dated before it was captured.

    Backdating invents history. Replay orders events by effective date, so a snapshot of
    current holdings stamped with a past date gets re-executed against every corporate
    action in between: quantities that already include those actions are multiplied a
    second time. On 2026-09-25 that inflated the seeded AAPL position 4x and SHOP 10x on
    accounts 10-12, which is what desynchronised the Overview from the Snapshot chart.
    """
    metadata = event.get("metadata") or {}
    event_type = event.get("event_type", "")
    is_checkpoint = event_type == CHECKPOINT_EVENT_TYPE
    if not is_checkpoint and metadata.get("source") != PROJECTION_IMPORT_SOURCE:
        return

    data = event.get("data") or {}
    raw = data.get("effective_date")
    if raw is None:
        return

    effective = raw if isinstance(raw, date) else date.fromisoformat(str(raw)[:10])
    if effective < captured_on:
        kind = (
            f"event_type={CHECKPOINT_EVENT_TYPE}"
            if is_checkpoint
            else f"metadata.source={PROJECTION_IMPORT_SOURCE}"
        )
        raise ValueError(
            f"State import dated {effective.isoformat()} predates its capture date "
            f"{captured_on.isoformat()} ({kind}). A snapshot of current holdings is only "
            "true as of the moment it was captured. Backdating it re-applies corporate "
            "actions to quantities that already include them. Use the capture date as "
            f"effective_date, or record real transactions as {CHECKPOINT_EVENT_TYPE}'s "
            "predecessor history instead of a checkpoint."
        )


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
        _assert_state_import_not_backdated(
            {"event_type": event_type, "data": data, "metadata": metadata or {}},
            datetime.now(UTC).date(),
        )
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
        captured_on = datetime.now(UTC).date()
        for event in events:
            _assert_state_import_not_backdated(event, captured_on)
        try:
            res = self.client.table(self.TABLE).insert(events).execute()
            return res.data or []
        except Exception as e:
            err_str = str(e).lower()
            if "duplicate key" in err_str:
                # Idempotent retry: rows whose idempotency_key already exists are
                # returned as-is and NEVER re-inserted - re-inserting an existing row
                # re-triggers the same 23505. Only genuinely new rows are inserted;
                # this also covers a partially-applied batch (rows applied before the
                # failure are picked up by the existence lookup, not re-inserted).
                existing_rows: list[dict] = []
                pending: list[dict] = []
                seen_keys: set[str] = set()
                for ev in events:
                    key = ev.get("idempotency_key")
                    if key:
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                        existing = self._get_by_idempotency_key(key)
                        if existing:
                            existing_rows.append(existing)
                            continue
                    pending.append(ev)
                inserted: list[dict] = []
                if pending:
                    inserted = self.client.table(self.TABLE).insert(pending).execute().data or []
                return existing_rows + inserted
            raise

    def get_existing_idempotency_keys(self, keys: list[str]) -> set[str]:
        """Return the subset of ``keys`` already present in the event log.

        Used by resumable CSV imports to append only rows that are genuinely
        new. A failed lookup must raise: treating it as "nothing imported yet"
        would duplicate the entire event history.
        """
        if not keys:
            return set()
        existing: set[str] = set()
        for chunk in _pack_idempotency_key_chunks(keys):
            res = (
                self.client.table(self.TABLE)
                .select("idempotency_key")
                .in_("idempotency_key", chunk)
                .execute()
            )
            chunk_keys = set(chunk)
            for row in res.data or []:
                key = row.get("idempotency_key")
                if key in chunk_keys:
                    existing.add(key)
        return existing

    def get_all_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int | None = 10000,
    ) -> list[dict]:
        """Fetch all matching events with pagination handling for large datasets.

        ``limit=None`` pages until the result set is exhausted.
        """
        page_size = 1000
        all_events = []
        offset = 0

        tracing = debug_trace.is_enabled()
        page = 0
        seen_ids: set[str] = set()
        prev_key: tuple[str, str] | None = None
        expected_total = (
            self._count_matching(aggregate_type, aggregate_id, event_type, since)
            if tracing
            else None
        )

        while True:
            query = (
                self.client.table(self.TABLE)
                .select("*")
                .order("created_at")
                .order("id")
                .range(offset, offset + page_size - 1)
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
            if tracing and batch:
                prev_key = self._trace_page(
                    page=page, batch=batch, seen_ids=seen_ids, prev_key=prev_key
                )
            page += 1
            if len(batch) < page_size or (limit and len(all_events) >= limit):
                break
            offset += page_size

        truncated = bool(limit) and len(all_events) > limit
        if truncated:
            all_events = all_events[:limit]

        if tracing:
            self._trace_result(
                all_events=all_events,
                expected_total=expected_total,
                truncated=truncated,
                limit=limit,
                pages=page,
            )

        return all_events

    def get_transfer_legs(self, account_ids: list[int]) -> list[dict[str, Any]]:
        """Return ``InternalSecurityTransfer`` payloads for the given accounts.

        I5: read-path spike attribution needs to know which dates carried a
        transfer round-trip. Transfers are recorded as ``transaction_imported``
        events whose ``data.activity_type`` is ``InternalSecurityTransfer``
        (there is no separate event_type). Aggregates are named ``account_<id>``.

        Advisory only: a failure here degrades to no attribution, never a failed
        performance response.
        """
        if not account_ids:
            return []
        aggregate_ids = [f"account_{aid}" for aid in account_ids]
        res = (
            self.client.table(self.TABLE)
            .select("data")
            .eq("event_type", "transaction_imported")
            .in_("aggregate_id", aggregate_ids)
            .execute()
        )
        legs: list[dict[str, Any]] = []
        for row in res.data or []:
            payload = row.get("data")
            if isinstance(payload, dict) and payload.get("activity_type") == "InternalSecurityTransfer":
                legs.append(payload)
        return legs

    def _count_matching(
        self,
        aggregate_type: str | None,
        aggregate_id: str | None,
        event_type: str | None,
        since: datetime | None,
    ) -> int | None:
        """Exact row count under the same filters.

        Supplies the "expected vs actual" half of every integrity check. A
        diagnostic must never break the read it is describing, so any failure
        here degrades to None, which suppresses those checks rather than
        reporting a false defect.
        """
        query = self.client.table(self.TABLE).select("id", count="exact")
        if aggregate_type:
            query = query.eq("aggregate_type", aggregate_type)
        if aggregate_id:
            query = query.eq("aggregate_id", aggregate_id)
        if event_type:
            query = query.eq("event_type", event_type)
        if since:
            query = query.gte("created_at", since.isoformat())
        try:
            res = query.execute()
        except Exception:
            return None
        count = getattr(res, "count", None)
        return count if isinstance(count, int) else None

    def _trace_page(
        self,
        page: int,
        batch: list[dict],
        seen_ids: set[str],
        prev_key: tuple[str, str] | None,
    ) -> tuple[str, str]:
        """Check one page against the total order (created_at, id) and report defects.

        The pair (created_at, id) is a strict total order because id is unique,
        so a correct pagination cannot repeat or reverse. Any violation means the
        database returned rows outside the requested window -- exactly the
        failure recorded in EVENT_REPLAY_SEAM_DROP_ROOT_CAUSE_ANALYSIS.md.

        Returns the page's last sort key for the next page's boundary check.
        """
        keys = [(str(r.get("created_at") or ""), str(r.get("id"))) for r in batch]
        ids = [k[1] for k in keys]

        out_of_order = [i for i in range(len(keys) - 1) if keys[i] >= keys[i + 1]]
        if out_of_order:
            debug_trace.integrity_finding(
                "ORDER_VIOLATION",
                page=page,
                occurrences=len(out_of_order),
                ids=debug_trace.summarize_ids([ids[i] for i in out_of_order[:3]]),
            )

        repeated = sorted(i for i, n in Counter(ids).items() if n > 1)
        carried_over = sorted({i for i in ids if i in seen_ids} - set(repeated))
        duplicates = repeated + carried_over
        if duplicates:
            debug_trace.integrity_finding(
                "DUPLICATE_ID",
                page=page,
                within_page=len(repeated),
                carried_from_previous_page=len(carried_over),
                ids=debug_trace.summarize_ids(duplicates),
            )

        if prev_key is not None and keys[0] <= prev_key:
            debug_trace.integrity_finding(
                "PAGE_OVERLAP",
                page=page,
                previous_last={"created_at": prev_key[0], "id": prev_key[1]},
                this_page_first={"created_at": keys[0][0], "id": keys[0][1]},
            )

        seen_ids.update(ids)
        return keys[-1]

    def _trace_result(
        self,
        all_events: list[dict],
        expected_total: int | None,
        truncated: bool,
        limit: int,
        pages: int,
    ) -> None:
        ids = [str(r.get("id")) for r in all_events]

        if expected_total is not None and limit and expected_total > limit:
            # Checked first on purpose: a shortfall the limit already explains
            # is not missing data, and reordering these would report a false
            # PAGE_GAP on every account whose table exceeds its limit.
            debug_trace.integrity_finding(
                "TRUNCATED_AT_LIMIT",
                returned=len(ids),
                limit=limit,
                expected_total=expected_total,
            )
        elif expected_total is not None and len(ids) < expected_total:
            debug_trace.integrity_finding(
                "PAGE_GAP",
                returned=len(ids),
                expected_total=expected_total,
                missing=expected_total - len(ids),
                pages=pages,
            )

        debug_trace.trace_event(
            "event_store",
            "get_all_events",
            pages=pages,
            returned=len(ids),
            distinct_ids=len(set(ids)),
            expected_total=expected_total,
            truncated=truncated,
            limit=limit,
            **debug_trace.summarize_ids(ids),
        )

    def get_events(
        self,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        event_type: str | None = None,
        since: datetime | None = None,
        limit: int | None = 100,
    ) -> list[dict]:
        """Fetch matching events, honouring ``limit``.

        Delegates to :meth:`get_all_events` so there is exactly one paginated
        implementation. It used to be a second, hand-written query that accepted a
        ``limit`` and never applied it: PostgREST capped the response at its own
        ``db-max-rows`` (1000 by default), so ``get_events(limit=10000)`` silently
        returned 1000 of 2724 rows. ``backfill_events_from_transactions`` used that
        call to build its dedupe set, so every account outside the returned prefix
        was considered event-less and got a second copy of its history on re-run.

        Pass ``limit=None`` for every matching event.
        """
        return self.get_all_events(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            since=since,
            limit=limit,
        )

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
            .order("id", desc=True)
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
            .order("id")
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
