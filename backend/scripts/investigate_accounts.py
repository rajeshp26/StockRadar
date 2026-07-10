"""Investigate what accounts 9-12 have (holdings, transactions, activity)."""
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

print("\n=== Transactions ===")
r = supabase.table("portfolio_transactions").select("account_id").execute()
t = Counter(e["account_id"] for e in r.data)
for k in sorted(t):
    print(f"  Account {k}: {t[k]} transactions")

print("\n=== Account Details ===")
for aid in [7, 8, 9, 10, 11, 12]:
    r = supabase.table("portfolio_accounts").select("*").eq("account_id", aid).execute()
    if r.data:
        a = r.data[0]
        print(f"  Account {aid}: name={a.get('account_name')}, type={a.get('account_type')}, currency={a.get('currency')}")

print("\n=== Snapshots per account ===")
r = supabase.table("portfolio_snapshots").select("account_id, snapshot_date, total_value").order("snapshot_date.desc").limit(5).execute()
by_acct = {}
for s in r.data or []:
    aid = s["account_id"]
    if aid not in by_acct:
        by_acct[aid] = []
    by_acct[aid].append(s)
for aid in sorted(by_acct):
    snaps = by_acct[aid]
    print(f"  Account {aid}: {snaps[0]['snapshot_date']} total=${snaps[0]['total_value']}")
    print(f"    latest: {snaps[0]['snapshot_date']} total=${snaps[0]['total_value']}")
