"""Complete period data: replay engine output for all dates + all accounts + grand total."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from datetime import date

event_store = EventStore()
engine = ReplayEngine(event_store)

# Load current_market_data prices with correct "price" key
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices = {}
for row in cmr.data or []:
    cid, px = row.get("company_id"), row.get("current_price")
    if cid and px:
        prices[int(cid)] = {"price": float(px), "price_date": date(2026, 7, 7)}

accounts = [7, 8, 9, 10, 11, 12]
target_dates = [
    date(2025, 7, 24), date(2025, 8, 14), date(2025, 9, 4), date(2025, 9, 25),
    date(2025, 10, 16), date(2025, 11, 6), date(2025, 11, 27), date(2025, 12, 18),
    date(2026, 1, 8), date(2026, 1, 29), date(2026, 2, 19), date(2026, 3, 12),
    date(2026, 4, 7), date(2026, 4, 29), date(2026, 6, 22), date(2026, 7, 7),
]

# Check what stored snapshots exist for these dates
all_date_strs = [d.isoformat() for d in target_dates]
r = supabase.table("portfolio_snapshots").select("account_id, snapshot_date, total_value").in_("snapshot_date", all_date_strs).execute()
stored = {}
for row in r.data or []:
    stored[(row["account_id"], row["snapshot_date"])] = row["total_value"]

print()
print(" REPLAY ENGINE OUTPUT -- All Accounts, All Dates")
print("=" * 130)
header = f"{'Acct':>5} {'Date':<12} {'Net Deposits':>14} {'Cash':>12} {'Market':>12} {'Cost':>12} {'Total':>12}  {'DB_Total':>10}  {'Delta':>10}"
print(header)
print("-" * len(header))

grand_net = {d: 0.0 for d in target_dates}
grand_cash = {d: 0.0 for d in target_dates}
grand_market = {d: 0.0 for d in target_dates}
grand_cost = {d: 0.0 for d in target_dates}
grand_total = {d: 0.0 for d in target_dates}

for aid in accounts:
    for dt in target_dates:
        state = engine.replay_to_date(aid, dt)
        snap = engine.build_snapshot_from_replay(aid, dt, prices)
        db_val = stored.get((aid, dt.isoformat()))
        db_str = f"${db_val:>8,.2f}" if db_val is not None else "  --  "
        delta = float(snap["total_value"]) - (float(db_val) if db_val else 0)
        delta_str = f"${delta:>+7,.2f}" if db_val is not None else "  --  "
        print(f"{aid:>5} {dt.isoformat():<12} {state.net_deposits:>14,.2f} {snap['cash_balance']:>12,.2f} "
              f"{snap['holdings_market_value']:>12,.2f} {snap['cost_basis']:>12,.2f} "
              f"{snap['total_value']:>12,.2f}  {db_str:>10}  {delta_str:>10}")
        grand_net[dt] += float(state.net_deposits)
        grand_cash[dt] += float(snap["cash_balance"])
        grand_market[dt] += float(snap["holdings_market_value"])
        grand_cost[dt] += float(snap["cost_basis"])
        grand_total[dt] += float(snap["total_value"])
    print()

print("=" * 130)
print(" GRAND TOTAL (All 6 Accounts Combined)")
print("=" * 130)
print(f"{'Date':<12} {'Net Deposits':>14} {'Cash':>12} {'Market':>12} {'Cost':>12} {'Net Assets':>12}")
print("-" * 74)
for dt in target_dates:
    net_assets = grand_total[dt]  # total_value = market + cash
    print(f"{dt.isoformat():<12} {grand_net[dt]:>14,.2f} {grand_cash[dt]:>12,.2f} "
          f"{grand_market[dt]:>12,.2f} {grand_cost[dt]:>12,.2f} "
          f"{grand_total[dt]:>12,.2f}")
