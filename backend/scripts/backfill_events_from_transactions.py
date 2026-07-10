"""Phase 3: One-time migration — create portfolio_events from existing portfolio_transactions.

Usage:
    python -m scripts.backfill_events_from_transactions [--account-id N] [--dry-run] [--batch-size 500]
"""

import argparse
import logging
import sys
from datetime import date
from typing import Any, Dict, List, Optional

from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger("stockerpro.scripts.backfill_events")


def get_transactions_for_backfill(
    account_id: Optional[int] = None,
    limit: Optional[int] = None,
    offset: int = 0,
) -> List[Dict[str, Any]]:
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


def build_event_from_transaction(tx: dict, idx: int) -> Dict[str, Any]:
    """Convert a portfolio_transaction row to a portfolio_event."""
    account_id = tx.get("account_id")
    return {
        "event_type": "transaction_imported",
        "event_version": 1,
        "aggregate_id": f"account_{account_id}",
        "aggregate_type": "account",
        "data": {
            "account_id": account_id,
            "company_id": tx.get("company_id"),
            "transaction_date": tx.get("transaction_date").isoformat() if hasattr(tx.get("transaction_date"), "isoformat") else tx.get("transaction_date"),
            "activity_type": tx.get("activity_type"),
            "symbol": tx.get("symbol"),
            "quantity": tx.get("quantity"),
            "unit_price": tx.get("unit_price"),
            "net_cash_amount": tx.get("net_cash_amount"),
            "currency": tx.get("currency", "CAD"),
        },
        "metadata": {
            "entry_source": tx.get("entry_source", "csv_import"),
            "import_batch_id": tx.get("import_batch_id"),
            "backfill": True,
            "original_transaction_id": tx.get("transaction_id"),
        },
        "idempotency_key": f"backfill_{account_id}_{tx.get('transaction_id', idx)}_{idx}",
    }


def backfill_events(
    account_id: Optional[int] = None,
    dry_run: bool = False,
    batch_size: int = 500,
) -> Dict[str, Any]:
    event_store = EventStore()
    transactions = get_transactions_for_backfill(account_id)
    logger.info(f"Found {len(transactions)} transactions to backfill")

    # Check for existing backfill events to skip
    existing_events = event_store.get_events(event_type="transaction_imported", limit=10000)
    existing_keys = set()
    for ev in existing_events:
        meta = ev.get("metadata", {}) or {}
        if meta.get("backfill"):
            key = ev.get("idempotency_key", "")
            if key:
                existing_keys.add(key)

    logger.info(f"Found {len(existing_keys)} existing backfill events, will skip duplicates")

    events_to_write = []
    skipped = 0
    for tx in transactions:
        aid = tx.get("account_id")
        tx_id = tx.get("transaction_id")
        idx = transactions.index(tx)
        key = f"backfill_{aid}_{tx_id}_{idx}" if tx_id else f"backfill_{aid}_{idx}"

        if key in existing_keys:
            skipped += 1
            continue

        events_to_write.append(build_event_from_transaction(tx, idx))

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
        "skipped_duplicates": skipped,
        "events_written": len(transactions) - skipped - (len(existing_keys) if not dry_run else 0),
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
