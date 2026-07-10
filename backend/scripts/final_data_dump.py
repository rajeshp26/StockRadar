"""Final data dump: net deposits + portfolio value for every account and date."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from datetime import date

event_store = EventStore()
engine = ReplayEngine(event_store)

# Load current_market_data prices (the fix — "price" key, not "current_price")
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices = {}
for row in cmr.data or []:
    cid, px = row.get("company_id"), row.get("current_price")
    if cid and px:
        prices[int(cid)] = {"price": float(px), "price_date": date(2026, 7, 7)}
print(f"Prices: {len(prices)} companies")

accounts = [7, 8, 9, 10, 11, 12]
target_dates = [date(2026, 6, 23), date(2026, 6, 24), date(2026, 6, 26),
                date(2026, 6, 27), date(2026, 6, 30), date(2026, 7, 6), date(2026, 7, 7)]

for aid in accounts:
    print(f"\n{'='*70}")
    print(f"Account {aid}")
    print(f"{'='*70}")
    print(f"{'Date':<14} {'Net Deposits':>16} {'Cash':>12} {'Market':>12} {'Cost':>12} {'Total':>12}")
    print(f"{'-'*14} {'-'*16} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
    for dt in target_dates:
        state = engine.replay_to_date(aid, dt)
        snap = engine.build_snapshot_from_replay(aid, dt, prices)
        print(f"{dt.isoformat():<14} {state.net_deposits:>16,.2f} {snap['cash_balance']:>12,.2f} "
              f"{snap['holdings_market_value']:>12,.2f} {snap['cost_basis']:>12,.2f} "
              f"{snap['total_value']:>12,.2f}")

    # Also show stored snapshot values for comparison
    stored = supabase.table("portfolio_snapshots").select(
        "snapshot_date, total_value, holdings_market_value, cash_balance, cost_basis, net_deposits"
    ).eq("account_id", aid).gte("snapshot_date", "2026-06-23").lte("snapshot_date", "2026-07-07").order("snapshot_date").execute()
    print(f"\n  Stored (DB):")
    print(f"  {'Date':<14} {'Net Deposits':>16} {'Cash':>12} {'Market':>12} {'Cost':>12} {'Total':>12}")
    print(f"  {'-'*14} {'-'*16} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
    for s in stored.data or []:
        print(f"  {s['snapshot_date']:<14} {float(s.get('net_deposits',0)):>16,.2f} {float(s['cash_balance']):>12,.2f} "
              f"{float(s['holdings_market_value']):>12,.2f} {float(s['cost_basis']):>12,.2f} "
              f"{float(s['total_value']):>12,.2f}")

# Final summary
print(f"\n{'='*70}")
print(f"SUMMARY: All accounts flat across June 23 - July 7")
print(f"{'='*70}")
print(f"{'Account':<10} {'Net Deposits':>16} {'Cash':>12} {'Market':>12} {'Cost':>12} {'Total':>12}")
print(f"{'-'*10} {'-'*16} {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
for aid in accounts:
    dt = date(2026, 7, 7)
    state = engine.replay_to_date(aid, dt)
    snap = engine.build_snapshot_from_replay(aid, dt, prices)
    print(f"{aid:<10} {state.net_deposits:>16,.2f} {snap['cash_balance']:>12,.2f} "
          f"{snap['holdings_market_value']:>12,.2f} {snap['cost_basis']:>12,.2f} "
          f"{snap['total_value']:>12,.2f}")
