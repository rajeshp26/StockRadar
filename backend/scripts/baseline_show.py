#!/usr/bin/env python3
"""Show what the UI would display with correct pricing."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

from database import supabase
from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import ReplayEngine

engine = ReplayEngine(EventStore())

cmd = supabase.table("current_market_data").select("company_id,current_price").execute()
prices = {}
if cmd.data:
    for c in cmd.data:
        prices[c["company_id"]] = {"price": c["current_price"]}

print("=== CORRECT VALUES (replay + current_market_data pricing) ===")
print()

for aid in [7, 8, 9, 10, 11, 12]:
    snap = engine.build_snapshot_from_replay(aid, date.today(), prices)
    print(f"Account {aid}:")
    print(f"  Total Value: ${snap['total_value']:,.2f}")
    print(f"  Market Value: ${snap['holdings_market_value']:,.2f}")
    print(f"  Cost Basis: ${snap['cost_basis']:,.2f}")
    print(f"  Cash: ${snap['cash_balance']:,.2f}")
    print(f"  Holdings: {len(snap['holdings_json'])}")
    print()

print("=== CURRENT DB VALUES (portfolio_holdings) ===")
print()
for aid in [7, 8, 9, 10, 11, 12]:
    ph = supabase.table("portfolio_holdings").select("*").eq("account_id", aid).execute()
    data = ph.data or []
    total_cost = sum(float(h.get("total_cost", 0)) for h in data)
    print(f"Account {aid}: {len(data)} holdings, cost_basis=${total_cost:,.2f}")
print()

print("=== LATEST SNAPSHOT VALUES (what UI currently shows) ===")
for aid in [7, 8, 9, 10, 11, 12]:
    s = supabase.table("portfolio_snapshots").select("total_value, snapshot_date").eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
    if s.data:
        print(f"Account {aid} ({s.data[0]['snapshot_date']}): ${s.data[0]['total_value']:,.2f}")
print()

# Show the 5 missing price companies in detail
print("=== MISSING PRICES DETAIL ===")
for cid, sym in [(3139, "NYCB"), (3140, "CMA"), (3144, "YTSL"), (3155, "WBA"), (3159, "RSLS")]:
    for aid in [7, 8, 9]:
        h = supabase.table("portfolio_holdings").select("quantity, total_cost").eq("account_id", aid).eq("company_id", cid).execute()
        if h.data:
            print(f"  Acct {aid} {sym} (cid={cid}): qty={h.data[0]['quantity']}, cost=${h.data[0]['total_cost']:,.2f} -- NO PRICE")
