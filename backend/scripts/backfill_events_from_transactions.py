"""Phase 3: One-time migration — create portfolio_events from existing portfolio_transactions.

Usage:
    python -m scripts.backfill_events_from_transactions [--account-id N] [--dry-run] [--batch-size 500]
"""

import argparse
import logging
import sys
from datetime import date
from typing import Any

from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.portfolio_event_payload import (
    build_transaction_event_data,
    normalise_backfill_key,
    transaction_event_key,
)

logger = logging.getLogger("stockerpro.scripts.backfill_events")


def get_transactions_for_backfill(
    account_id: int | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict[str, Any]]:
    repo = PortfolioRepository()
    accounts = [account_id] if account_id else [a["account_id"] for a in repo.get_user_accounts_all()]

    all_txns = []
    for aid in accounts:
        txns = repo.get_accounts_transactions([aid], activity_types=None)
        for t in txns:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            all_txns.append(t)

    all_txns.sort(key=lambda t: (t.get("account_id", 0), t.get("transaction_date", date.min), t.get("transaction_id", 0)))
    return all_txns


def build_event_from_transaction(tx: dict) -> dict[str, Any]:
    """Convert a portfolio_transaction row to a portfolio_event."""
    account_id = tx.get("account_id")
    return {
        "event_type": "transaction_imported",
        "event_version": 1,
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": build_transaction_event_data(
            account_id=account_id,
            company_id=tx.get("company_id"),
            transaction_date=tx.get("transaction_date").isoformat() if hasattr(tx.get("transaction_date"), "isoformat") else tx.get("transaction_date"),
            settlement_date=tx.get("settlement_date").isoformat() if hasattr(tx.get("settlement_date"), "isoformat") else tx.get("settlement_date"),
            activity_type=tx.get("activity_type"),
            activity_sub_type=tx.get("activity_sub_type"),
            direction=tx.get("direction"),
            symbol=tx.get("symbol"),
            security_name=tx.get("security_name"),
            exchange_override=tx.get("exchange_override"),
            quantity=tx.get("quantity"),
            unit_price=tx.get("unit_price"),
            net_cash_amount=tx.get("net_cash_amount"),
            currency=tx.get("currency", "CAD"),
        ),
        "metadata": {
            "entry_source": tx.get("entry_source", "csv_import"),
            "import_batch_id": tx.get("import_batch_id"),
            "backfill": True,
            "original_transaction_id": tx.get("transaction_id"),
        },
        "idempotency_key": transaction_event_key(account_id, tx.get("transaction_id")),
    }


def backfill_events(
    account_id: int | None = None,
    dry_run: bool = False,
    batch_size: int = 500,
) -> dict[str, Any]:
    event_store = EventStore()
    transactions = get_transactions_for_backfill(account_id)
    logger.info(f"Found {len(transactions)} transactions to backfill")

    # Check for existing backfill events to skip.
    #
    # Scoped per account, not a global scan. The global scan asked for
    # `get_events(event_type="transaction_imported", limit=10000)`, which returned
    # a 1000-row prefix of a 2724-row log, so accounts outside that prefix looked
    # event-less and a re-run appended a second copy of their history. An account's
    # own events are a bounded set and paginate completely.
    account_ids = sorted(
        {t.get("account_id") for t in transactions if t.get("account_id") is not None}
    )
    existing_keys: set[str] = set()
    for aid in account_ids:
        for ev in event_store.get_all_events(
            aggregate_id=f"account_{aid}", event_type="transaction_imported"
        ):
            meta = ev.get("metadata", {}) or {}
            if not meta.get("backfill"):
                continue
            key = normalise_backfill_key(ev.get("idempotency_key"))
            if key:
                existing_keys.add(key)

    logger.info(
        f"Found {len(existing_keys)} existing backfill events across "
        f"{len(account_ids)} account(s), will skip duplicates"
    )

    events_to_write = []
    skipped = 0
    for tx in transactions:
        key = transaction_event_key(tx.get("account_id"), tx.get("transaction_id"))

        if key in existing_keys:
            skipped += 1
            continue

        events_to_write.append(build_event_from_transaction(tx))

        if len(events_to_write) >= batch_size:
            if not dry_run:
                event_store.append_events_batch(events_to_write)
                logger.info(f"Wrote batch of {len(events_to_write)} events")
            else:
                logger.info(f"[DRY RUN] Would write batch of {len(events_to_write)} events")
            events_to_write = []

    # Final batch
    if events_to_write:
        if not dry_run:
            event_store.append_events_batch(events_to_write)
            logger.info(f"Wrote final batch of {len(events_to_write)} events")
        else:
            logger.info(f"[DRY RUN] Would write final batch of {len(events_to_write)} events")

    return {
        "total_transactions": len(transactions),
        "existing_events": len(existing_keys),
        # `skipped` is a subset of `total_transactions`, so subtracting the whole
        # existing-key set (which includes other accounts' events) under-reported
        # writes and could go negative.
        "skipped_duplicates": skipped,
        "events_written": len(transactions) - skipped,
        "dry_run": dry_run,
    }


def main():
    parser = argparse.ArgumentParser(description="Backfill portfolio_events from portfolio_transactions")
    parser.add_argument("--account-id", type=int, help="Specific account to backfill")
    parser.add_argument("--dry-run", action="store_true", help="Scan without writing")
    parser.add_argument("--batch-size", type=int, default=500, help="Events per batch insert")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s", stream=sys.stderr)

    result = backfill_events(
        account_id=args.account_id,
        dry_run=args.dry_run,
        batch_size=args.batch_size,
    )

    logger.info(
        f"Backfill complete: {result['total_transactions']} transactions, "
        f"{result['existing_events']} existing events, "
        f"{result['skipped_duplicates']} duplicates skipped, "
        f"{result['events_written']} events written"
        + (" (dry run)" if result["dry_run"] else "")
    )


if __name__ == "__main__":
    main()
