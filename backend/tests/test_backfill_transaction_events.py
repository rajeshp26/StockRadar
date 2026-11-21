"""Dedupe in the one-time event backfill must be complete, scoped and stable.

Two independent defects lived in `backfill_events`'s dedupe, and both produce the
same failure: a second copy of an account's share history.

1. **The dedupe query was truncated.** It asked
   ``get_events(event_type="transaction_imported", limit=10000)``, a method that
   accepted a limit and never applied it, so PostgREST's own row cap (1000 by
   default) decided the answer. Measured: 1000 rows returned out of 2724. Every
   account outside that prefix looked event-less.

2. **The key embedded a positional index.** ``backfill_{aid}_{tx_id}_{idx}`` changes
   for every row after an inserted historical transaction, so even a complete scan
   stops recognising the events it already wrote.

Doubled history is not cosmetic. Replay then totals 200 shares against a 100-share
position, which is the exact disagreement that logged "Replay lot split declined"
on every snapshot run.

These tests pin all four properties: the query is scoped per account, legacy keys
are still recognised, a re-run writes nothing, and the reported counts describe
this run.
"""
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest

from scripts import backfill_events_from_transactions as backfill
from shared.portfolio_event_payload import (
    normalise_backfill_key,
    transaction_event_key,
)


def _tx(tx_id, account_id, symbol, day=1):
    return {
        "transaction_id": tx_id,
        "account_id": account_id,
        "company_id": 100 + account_id,
        "transaction_date": date(2026, 1, day),
        "activity_type": "Trade",
        "activity_sub_type": "Buy",
        "direction": "Buy",
        "symbol": symbol,
        "quantity": Decimal("10"),
        "unit_price": Decimal("5.00"),
        "net_cash_amount": Decimal("-50.00"),
        "currency": "CAD",
    }


class _FakeEventStore:
    """Records what the backfill asked for and what it wrote."""

    def __init__(self, existing_by_aggregate):
        self.existing_by_aggregate = existing_by_aggregate
        self.queries = []
        self.written = []

    def get_all_events(self, **kwargs):
        self.queries.append(kwargs)
        return list(self.existing_by_aggregate.get(kwargs.get("aggregate_id"), []))

    def append_events_batch(self, events):
        self.written.extend(events)


def _event(key, backfill_meta=True):
    return {
        "event_type": "transaction_imported",
        "aggregate_id": "account_10",
        "idempotency_key": key,
        "metadata": {"backfill": backfill_meta},
    }


def _run(transactions, existing, **kwargs):
    store = _FakeEventStore(existing)
    with (
        patch.object(backfill, "EventStore", return_value=store),
        patch.object(
            backfill, "get_transactions_for_backfill", return_value=transactions
        ),
    ):
        result = backfill.backfill_events(**kwargs)
    return result, store


class TestBackfillDedupe:
    def test_dedupe_query_is_scoped_to_the_backfilled_accounts(self):
        transactions = [_tx(1, 10, "RY"), _tx(2, 11, "TD")]

        _, store = _run(transactions, {})

        assert [q["aggregate_id"] for q in store.queries] == ["account_10", "account_11"]
        assert all(q["event_type"] == "transaction_imported" for q in store.queries)

    def test_an_account_with_events_elsewhere_does_not_stop_this_one(self):
        """A truncated global scan is exactly what let account 12 be re-written."""
        transactions = [_tx(2, 11, "TD"), _tx(3, 12, "ENB")]
        existing = {"account_11": [_event(transaction_event_key(11, 2))], "account_12": []}

        result, store = _run(transactions, existing)

        assert result["skipped_duplicates"] == 1
        assert result["events_written"] == 1
        assert [e["aggregate_id"] for e in store.written] == ["account_12"]

    def test_a_second_run_writes_nothing(self):
        transactions = [_tx(2, 11, "TD"), _tx(3, 12, "ENB")]

        first, first_store = _run(transactions, {})
        assert first["events_written"] == 2

        written_by_aggregate = {}
        for event in first_store.written:
            written_by_aggregate.setdefault(event["aggregate_id"], []).append(event)

        second, second_store = _run(transactions, written_by_aggregate)

        assert second["events_written"] == 0
        assert second["skipped_duplicates"] == 2
        assert second_store.written == []

    def test_an_account_backfilled_by_the_old_key_format_is_recognised(self):
        """Existing rows keep ``..._{idx}``; stripping it must prevent a duplicate."""
        transactions = [_tx(1, 10, "RY"), _tx(2, 10, "TD")]
        legacy = [_event("backfill_10_1_0"), _event("backfill_10_2_1")]

        result, store = _run(transactions, {"account_10": legacy})

        assert result["skipped_duplicates"] == 2
        assert result["events_written"] == 0
        assert store.written == []

    def test_events_written_counts_this_runs_writes(self):
        """`existing_events` is a global count, not a subset of `transactions`.

        Subtracting it under-reported writes and went negative whenever an account
        already had more events than it had transactions.
        """
        transactions = [_tx(1, 10, "RY"), _tx(2, 11, "TD"), _tx(3, 12, "ENB")]
        existing = {
            "account_10": [_event(transaction_event_key(10, 1))],
            "account_11": [_event(transaction_event_key(11, 2))],
        }

        result, store = _run(transactions, existing)

        assert result["existing_events"] == 2
        assert result["events_written"] == 1
        assert result["events_written"] >= 0
        assert [e["aggregate_id"] for e in store.written] == ["account_12"]

    def test_events_without_backfill_metadata_are_not_treated_as_dedupe_hits(self):
        """A CSV import that happens to collide must not suppress a backfill row."""
        transactions = [_tx(1, 10, "RY")]
        existing = {"account_10": [_event(transaction_event_key(10, 1), backfill_meta=False)]}

        result, store = _run(transactions, existing)

        assert result["skipped_duplicates"] == 0
        assert len(store.written) == 1


class TestIdempotencyKeyIsStable:
    def test_key_does_not_depend_on_row_position(self):
        """The defect: inserting one transaction shifted every later index."""
        before = [
            _tx(1, 10, "RY"),
            _tx(2, 10, "TD"),
        ]
        after = [
            _tx(9, 10, "ENB", day=5),
            _tx(1, 10, "RY"),
            _tx(2, 10, "TD"),
        ]

        def keys(transactions):
            _, store = _run(transactions, {})
            return {e["data"]["symbol"]: e["idempotency_key"] for e in store.written}

        before_keys = keys(before)
        after_keys = keys(after)

        for symbol in before_keys:
            assert before_keys[symbol] == after_keys[symbol]

    def test_legacy_key_suffix_is_stripped(self):
        assert normalise_backfill_key("backfill_10_1_0") == "backfill_10_1"
        assert normalise_backfill_key("backfill_10_1") == "backfill_10_1"
        assert normalise_backfill_key(None) == ""
        assert normalise_backfill_key("") == ""
        # Not a backfill key: left untouched.
        assert normalise_backfill_key("import_fc49eec2_15") == "import_fc49eec2_15"

    def test_a_row_without_a_transaction_id_cannot_be_keyed(self):
        with pytest.raises(ValueError, match="no transaction_id"):
            transaction_event_key(10, None)
