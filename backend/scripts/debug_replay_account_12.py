"""Debug why account 12 replay returns $0."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import ReplayEngine
from datetime import date

event_store = EventStore()
engine = ReplayEngine(event_store)

# Check what events account 12 has
events = event_store.get_events(aggregate_id="account_12")
print(f"Account 12 events: {len(events)}")
for ev in events:
    edate = engine._get_event_date(ev)
    data = ev.get("data", {})
    print(f"  {ev['event_type']} date={edate} txn_date={data.get('transaction_date')} act={data.get('activity_type')} net_cash={data.get('net_cash_amount')}")

# Try replay up to today
state = engine.replay_to_date(12, date(2026, 7, 7))
print(f"\nReplay state: cash={state.cash_balance}, net_deposits={state.net_deposits}")
print(f"Holdings: {len(state.holdings)}")
for cid, h in state.holdings.items():
    print(f"  company={cid} symbol={h.symbol} qty={h.quantity} cost={h.total_cost} avg={h.average_cost}")
