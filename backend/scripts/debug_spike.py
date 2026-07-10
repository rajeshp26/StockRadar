"""Debug why replay state differs between June 23 and July 7 for account 7."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from datetime import date

event_store = EventStore()
engine = ReplayEngine(event_store)

# Get ALL events for account 7
events = event_store.get_all_events(aggregate_id="account_7")
print(f"Account 7: {len(events)} events total")

# Check date range of events
min_date = None
max_date = None
null_date_count = 0
for ev in events:
    ed = engine._get_event_date(ev)
    if ed is None:
        null_date_count += 1
    else:
        if min_date is None or ed < min_date:
            min_date = ed
        if max_date is None or ed > max_date:
            max_date = ed

print(f"Event date range: {min_date} to {max_date} ({null_date_count} null dates)")

# Compare state for June 23 vs July 7
state_jun23 = engine.replay_to_date(7, date(2026, 6, 23))
state_jul7 = engine.replay_to_date(7, date(2026, 7, 7))

print(f"\nJune 23 state: cash={state_jun23.cash_balance}, deposits={state_jun23.net_deposits}, holdings={len(state_jun23.holdings)}")
print(f"July 7 state:  cash={state_jul7.cash_balance}, deposits={state_jul7.net_deposits}, holdings={len(state_jul7.holdings)}")

# Check if holdings differ
for cid in set(list(state_jun23.holdings.keys()) + list(state_jul7.holdings.keys())):
    hj23 = state_jun23.holdings.get(cid)
    hj7 = state_jul7.holdings.get(cid)
    if hj23 != hj7:
        print(f"  Holding {cid}: June={hj23} July={hj7}")

# Count events filtered out by date
events_before_jun23 = sum(1 for ev in events if engine._get_event_date(ev) is not None and engine._get_event_date(ev) <= date(2026, 6, 23))
events_before_jul7 = sum(1 for ev in events if engine._get_event_date(ev) is not None and engine._get_event_date(ev) <= date(2026, 7, 7))
print(f"\nEvents up to June 23: {events_before_jun23}")
print(f"Events up to July 7:  {events_before_jul7}")
