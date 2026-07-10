"""Check which accounts have holdings, events, and snapshots."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from collections import Counter

print("=== Holdings ===")
r = supabase.table("portfolio_holdings").select("account_id").execute()
h = Counter(e["account_id"] for e in r.data)
for k in sorted(h):
    print(f"  Account {k}: {h[k]} holdings")

print("\n=== Events ===")
r = supabase.table("portfolio_events").select("aggregate_id,event_type").execute()
e = Counter()
for ev in r.data or []:
    aid = ev["aggregate_id"]
    etype = ev["event_type"]
    e[(aid, etype)] += 1
for (aid, etype), cnt in sorted(e.items()):
    print(f"  {aid} ({etype}): {cnt}")

print("\n=== Snapshots ===")
r = supabase.table("portfolio_snapshots").select("account_id").execute()
s = Counter(e["account_id"] for e in r.data)
for k in sorted(s):
    print(f"  Account {k}: {s[k]} snapshots")

print("\n=== Missing coverage ===")
accounts_with_holdings = set(h.keys())
accounts_with_events = set()
for (aid, _), _ in e.items():
    parts = aid.split("_")
    if len(parts) == 2 and parts[0] == "account":
        accounts_with_events.add(int(parts[1]))

missing = accounts_with_holdings - accounts_with_events
print(f"  Holdings but no events: {sorted(missing)}")
