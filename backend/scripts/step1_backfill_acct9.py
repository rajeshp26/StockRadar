"""Step 1: Backfill account 9 events with proper pagination."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from infrastructure.repositories.event_store import EventStore
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stderr)
log = logging.getLogger("backfill_acct9")

ACCOUNT_ID = 9
AGG_ID = f"account_{ACCOUNT_ID}"
PAGE_SIZE = 1000

event_store = EventStore()

def get_all_transactions():
    all_txns = []
    offset = 0
    while True:
        r = (
            supabase.table("portfolio_transactions")
            .select("*")
            .eq("account_id", ACCOUNT_ID)
            .order("transaction_date")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = r.data or []
        all_txns.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    log.info(f"Fetched {len(all_txns)} transactions for account {ACCOUNT_ID}")
    return all_txns

def get_existing_backfill_keys():
    existing_keys = set()
    offset = 0
    while True:
        r = (
            supabase.table("portfolio_events")
            .select("idempotency_key")
            .eq("aggregate_id", AGG_ID)
            .eq("event_type", "transaction_imported")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        batch = r.data or []
        for e in batch:
            k = e.get("idempotency_key")
            if k:
                existing_keys.add(k)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    log.info(f"Found {len(existing_keys)} existing backfill events")
    return existing_keys

def build_events(txns):
    events = []
    for idx, tx in enumerate(txns):
        tx_id = tx.get("transaction_id", idx)
        txn_date = tx.get("transaction_date")
        if hasattr(txn_date, "isoformat"):
            txn_date = txn_date.isoformat()
        key = f"backfill_{ACCOUNT_ID}_{tx_id}_{idx}"
        events.append({
            "event_type": "transaction_imported",
            "event_version": 1,
            "aggregate_id": AGG_ID,
            "aggregate_type": "account",
            "data": {
                "account_id": ACCOUNT_ID,
                "company_id": tx.get("company_id"),
                "transaction_date": txn_date,
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
                "original_transaction_id": tx_id,
            },
            "idempotency_key": key,
        })
    return events

def main():
    txns = get_txns()
    existing = get_existing_keys()
    
    new_txns = [t for t in txns if f"backfill_{ACCOUNT_ID}_{t.get('transaction_id', txns.index(t))}_{txns.index(t)}" not in existing]
    log.info(f"{len(new_txns)} new transactions to backfill")
    
    if not new_txns:
        log.info("Nothing to backfill")
        return
    
    events = build_events(new_txns)
    BATCH = 500
    for i in range(0, len(events), BATCH):
        batch = events[i:i+BATCH]
        event_store.append_events_batch(batch)
        log.info(f"Wrote batch {i//BATCH + 1}: {len(batch)} events")
    
    log.info(f"Done: {len(events)} events created")

# Rename to avoid shadowing
def get_txns():
    return get_transactions()

def get_transactions():
    return get_txn_range()

def get_txn_range():
    all_t = []
    off = 0
    while True:
        r = supabase.table("portfolio_transactions").select("*").eq("account_id", 9).order("transaction_date").range(off, off + 999).execute()
        b = r.data or []
        all_t.extend(b)
        if len(b) < 1000:
            break
        off += 1000
    return all_t

def get_existing_keys():
    keys = set()
    off = 0
    while True:
        r = supabase.table("portfolio_events").select("idempotency_key").eq("aggregate_id", "account_9").eq("event_type", "transaction_imported").range(off, off + 999).execute()
        b = r.data or []
        for e in b:
            if e.get("idempotency_key"):
                keys.add(e["idempotency_key"])
        if len(b) < 1000:
            break
        off += 1000
    return keys

if __name__ == "__main__":
    main()