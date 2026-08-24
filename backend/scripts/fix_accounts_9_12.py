"""Replace partial transaction_imported events with initial_holding_set for accounts 9-12."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from infrastructure.repositories.event_store import EventStore

event_store = EventStore()

# Accounts with partial/no transaction history: 9, 10, 11, 12
target_accounts = [9, 10, 11, 12]

for aid in target_accounts:
    # 1. Delete existing transaction_imported events for this account
    events = event_store.get_events(aggregate_id=f"account_{aid}", limit=5000)
    for ev in events:
        kid = ev.get("id")
        if kid:
            supabase.table("portfolio_events").delete().eq("id", kid).execute()
    print(f"Account {aid}: deleted {len(events)} existing events")

    # 2. Get current holdings
    r = supabase.table("portfolio_holdings").select("*").eq("account_id", aid).execute()
    holdings = r.data or []

    # 3. Get cash_balance from latest snapshot (or compute from transactions)
    r = supabase.table("portfolio_snapshots").select("*").eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
    snapshot = r.data[0] if r.data else {}
    cash_balance = float(snapshot.get("cash_balance", 0)) if snapshot else 0.0
    net_deposits = float(snapshot.get("net_deposits", 0)) if snapshot else 0.0

    # If no snapshot, compute cash from transactions
    if not snapshot and holdings:
        r = supabase.table("portfolio_transactions").select("net_cash_amount").eq("account_id", aid).execute()
        cash_balance = sum(float(t.get("net_cash_amount", 0)) for t in (r.data or []))

    holdings_data = [
        {
            "company_id": h["company_id"],
            "symbol": h["symbol"],
            "quantity": float(h["quantity"]),
            "average_cost": float(h["average_cost"]),
            "total_cost": float(h["total_cost"]),
        }
        for h in holdings
    ]

    # 4. Create initial_holding_set event
    event_store.append_event(
        event_type="initial_holding_set",
        aggregate_id=f"account_{aid}",
        aggregate_type="account",
        data={
            "effective_date": "2020-01-01",
            "account_id": aid,
            "cash_balance": cash_balance,
            "net_deposits": net_deposits,
            "holdings": holdings_data,
        },
        metadata={"backfill": True, "source": "portfolio_holdings"},
        idempotency_key=f"initial_holding_set_{aid}",
    )
    print(f"Account {aid}: created initial_holding_set ({len(holdings_data)} holdings, cash=${cash_balance:.2f})")

print("Done")
