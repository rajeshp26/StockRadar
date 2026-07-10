"""Check spike across all dates for all accounts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase

r = supabase.table("portfolio_snapshots").select(
    "account_id, snapshot_date, total_value, holdings_market_value, cost_basis, cash_balance"
).gte("snapshot_date", "2026-06-01").order("snapshot_date").execute()

rows = r.data or []
if not rows:
    print("No snapshots found")
    sys.exit(0)

# Group by account
from collections import defaultdict
by_account = defaultdict(list)
for row in rows:
    by_account[row["account_id"]].append(row)

for aid in sorted(by_account.keys()):
    snaps = by_account[aid]
    print(f"\nAccount {aid}:")
    for s in snaps:
        total = s["total_value"]
        market = s["holdings_market_value"]
        cash = s["cash_balance"]
        cost = s["cost_basis"]
        print(f"  {s['snapshot_date']}: total=${total:>8,.2f}  market=${market:>8,.2f}  cash=${cash:>8,.2f}  cost=${cost:>8,.2f}")
