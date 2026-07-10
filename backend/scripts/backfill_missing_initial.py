"""Create initial_holding_set events for accounts 10 and 11 only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from infrastructure.repositories.event_store import EventStore

event_store = EventStore()

for aid in [10, 11]:
    holdings_r = supabase.table("portfolio_holdings").select("*").eq("account_id", aid).execute()
    holdings = holdings_r.data or []

    snap_r = supabase.table("portfolio_snapshots").select("*").eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
    snapshot = snap_r.data[0] if snap_r.data else {}
    cash_balance = float(snapshot.get("cash_balance", 0)) if snapshot else 0.0
    net_deposits = float(snapshot.get("net_deposits", 0)) if snapshot else 0.0

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

    try:
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
        print(f"Account {aid}: written ({len(holdings_data)} holdings, cash=${cash_balance:.2f})")
    except Exception as ex:
        print(f"Account {aid}: FAILED - {ex}")
