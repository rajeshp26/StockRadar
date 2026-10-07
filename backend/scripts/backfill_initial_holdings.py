"""Create position_state_checkpoint events for accounts that have holdings but no transactions (9-12).

These accounts have no transaction history, so the only honest record of their state is a
capture of what they hold today. That is a checkpoint, not a historical opening position:
the captured quantities already reflect every corporate action to date.
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from database import supabase
from infrastructure.repositories.event_store import EventStore

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s", stream=sys.stderr)
logger = logging.getLogger("stockerpro.scripts.backfill_initial_holdings")

event_store = EventStore()

def get_accounts_without_events():
    """Find accounts that have holdings but no events."""
    r = supabase.table("portfolio_events").select("aggregate_id").execute()
    accounts_with_events = set()
    for ev in r.data or []:
        aid = ev.get("aggregate_id", "")
        if aid.startswith("account_"):
            try:
                accounts_with_events.add(int(aid.split("_")[1]))
            except (ValueError, IndexError):
                pass

    r = supabase.table("portfolio_accounts").select("account_id").eq("is_active", True).execute()
    all_accounts = [a["account_id"] for a in r.data or []]

    r = supabase.table("portfolio_holdings").select("account_id").execute()
    accounts_with_holdings = set()
    for h in r.data or []:
        aid = h.get("account_id")
        if aid:
            accounts_with_holdings.add(aid)

    return sorted(accounts_with_holdings - accounts_with_events)

def get_latest_snapshot(account_id: int) -> dict:
    r = supabase.table("portfolio_snapshots").select("*").eq("account_id", account_id).order("snapshot_date", desc=True).limit(1).execute()
    return r.data[0] if r.data else {}

def main():
    accounts = get_accounts_without_events()
    logger.info(f"Accounts with holdings but no events: {accounts}")

    written = 0
    for aid in accounts:
        holdings_r = supabase.table("portfolio_holdings").select("*").eq("account_id", aid).execute()
        holdings = holdings_r.data or []

        snapshot = get_latest_snapshot(aid)
        cash_balance = float(snapshot.get("cash_balance", 0)) if snapshot else 0.0
        net_deposits = float(snapshot.get("net_deposits", 0)) if snapshot else 0.0

        holdings_data = []
        for h in holdings:
            holdings_data.append({
                "company_id": h["company_id"],
                "symbol": h["symbol"],
                "quantity": float(h["quantity"]),
                "average_cost": float(h["average_cost"]),
                "total_cost": float(h["total_cost"]),
            })

        event_store.append_event(
            event_type="position_state_checkpoint",
            aggregate_id=f"account_{aid}",
            aggregate_type="account",
            data={
                "effective_date": datetime.now(timezone.utc).date().isoformat(),
                "account_id": aid,
                "cash_balance": cash_balance,
                "net_deposits": net_deposits,
                "holdings": holdings_data,
            },
            metadata={"backfill": True, "source": "portfolio_holdings"},
            idempotency_key=f"position_state_checkpoint_{aid}",
        )
        logger.info(f"Account {aid}: wrote position_state_checkpoint with {len(holdings_data)} holdings, cash=${cash_balance:.2f}")
        written += 1

    logger.info(f"Done. Wrote {written} position_state_checkpoint events")

if __name__ == "__main__":
    main()
