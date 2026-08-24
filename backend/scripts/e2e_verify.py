"""End-to-end verification: replay engine vs portfolio_holdings vs snapshots for every account & date."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from database import supabase
from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import ReplayEngine

rows = lambda r: r.data or []

# 1. Check all companies
cmd = supabase.table("current_market_data").select("company_id").execute()
cmd_ids = set(str(r["company_id"]) for r in rows(cmd))
ph = supabase.table("portfolio_holdings").select("company_id").execute()
ph_ids = set(str(r["company_id"]) for r in rows(ph) if r.get("company_id"))
missing = ph_ids - cmd_ids
print("=== PRICE COVERAGE ===")
print(f"current_market_data: {len(cmd_ids)} companies")
print(f"portfolio_holdings: {len(ph_ids)} companies")
missing_str = ", ".join(sorted(missing)) if missing else "NONE"
print(f"Missing: {missing_str}")
for cid in sorted(missing):
    h = supabase.table("portfolio_holdings").select("account_id, symbol, quantity, total_cost").eq("company_id", int(cid)).execute()
    for row in rows(h):
        print(f"  Company {cid} ({row['symbol']}): Acct {row['account_id']} qty={row['quantity']} cost={row['total_cost']}")

print()

# 2. Replay engine vs portfolio_holdings for every account
print("=== REPLAY vs PORTFOLIO_HOLDINGS (current state) ===")
event_store = EventStore()
engine = ReplayEngine(event_store)
today = date(2026, 7, 8)

users = supabase.table("users").select("user_id, email").execute()
for u in rows(users):
    accts = supabase.table("portfolio_accounts").select("account_id, account_name, account_type").eq("user_id", u["user_id"]).execute()
    for a in rows(accts):
        aid = a["account_id"]
        # Replay state
        try:
            state = engine.replay_to_date(aid, today)
        except Exception as e:
            print(f"Acct {aid} ({a['account_type']}): REPLAY FAILED: {e}")
            continue

        # portfolio_holdings
        ph_rows = rows(supabase.table("portfolio_holdings").select("*").eq("account_id", aid).execute())

        # Compare holdings count
        replay_cids = set(state.holdings.keys())
        ph_cids = set(int(h["company_id"]) for h in ph_rows if h.get("company_id"))
        only_replay = replay_cids - ph_cids
        only_ph = ph_cids - replay_cids

        print(f"\nAcct {aid} ({a['account_type']}):")
        print(f"  Replay: {len(state.holdings)} holdings, cash=${float(state.cash_balance):.2f}")
        print(f"  Portfolio_Holdings: {len(ph_rows)} rows (including CASH)")
        if only_replay:
            print(f"  ONLY IN REPLAY: {sorted(only_replay)}")
        if only_ph:
            print(f"  ONLY IN PORTFOLIO_HOLDINGS: {sorted(only_ph)}")

        # For matching companies, compare quantities
        common = replay_cids & ph_cids
        qty_diffs = []
        for cid in sorted(common):
            rqty = float(state.holdings[cid].quantity)
            ph_row = [h for h in ph_rows if h.get("company_id") == cid]
            pqty = float(ph_row[0].get("quantity", 0)) if ph_row else 0
            if abs(rqty - pqty) > 0.001:
                qty_diffs.append((cid, rqty, pqty, state.holdings[cid].symbol))
        if qty_diffs:
            print(f"  QUANTITY DIFFERENCES: {len(qty_diffs)}")
            for cid, rq, pq, sym in qty_diffs[:10]:
                print(f"    Company {cid} ({sym}): replay_qty={rq:.4f}  ph_qty={pq:.4f}")
        else:
            print(f"  All {len(common)} common holdings: QUANTITIES MATCH")

print()

# 3. Compare replay values vs latest snapshot
print("=== REPLAY vs SNAPSHOTS (latest date) ===")
for u in rows(users):
    accts = supabase.table("portfolio_accounts").select("account_id, account_name, account_type").eq("user_id", u["user_id"]).execute()
    for a in rows(accts):
        aid = a["account_id"]
        # Latest snapshot
        snap = supabase.table("portfolio_snapshots").select("snapshot_date, total_value, holdings_market_value, cash_balance, cost_basis").eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
        if not rows(snap):
            print(f"Acct {aid}: No snapshots")
            continue
        s = rows(snap)[0]
        snap_date = date.fromisoformat(s["snapshot_date"])
        snap_total = float(s["total_value"])

        # Replay for same date with same pricing
        cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
        prices = {}
        for row in rows(cmr):
            cid, px = row.get("company_id"), row.get("current_price")
            if cid and px:
                prices[int(cid)] = {"price": float(px), "price_date": snap_date}
        replay = engine.build_snapshot_from_replay(aid, snap_date, prices)
        replay_total = replay["total_value"]

        delta = replay_total - snap_total
        status = "MATCH" if abs(delta) < 0.01 else f"DELTA=${delta:+.2f}"
        print(f"Acct {aid} ({a['account_type']}) on {snap_date}: snap=${snap_total:,.2f}  replay=${replay_total:,.2f}  [{status}]")

print()

# 4. Full date-range replay for rajesh accounts
print("=== FULL PERIOD CHECK (rajeshp01) ===")
target_dates = [
    date(2025, 7, 24), date(2025, 8, 14), date(2025, 9, 4), date(2025, 9, 25),
    date(2025, 10, 16), date(2025, 11, 6), date(2025, 11, 27), date(2025, 12, 18),
    date(2026, 1, 8), date(2026, 1, 29), date(2026, 2, 19), date(2026, 3, 12),
    date(2026, 4, 7), date(2026, 4, 29), date(2026, 6, 22), date(2026, 7, 7),
    date(2026, 7, 8),
]

cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices = {}
for row in rows(cmr):
    cid, px = row.get("company_id"), row.get("current_price")
    if cid and px:
        prices[int(cid)] = {"price": float(px), "price_date": date(2026, 7, 8)}

for aid in [7, 8, 9]:
    acct = supabase.table("portfolio_accounts").select("account_type").eq("account_id", aid).execute()
    atype = rows(acct)[0]["account_type"]
    print(f"\nAcct {aid} ({atype}):")
    for dt in target_dates:
        state = engine.replay_to_date(aid, dt)
        snap = engine.build_snapshot_from_replay(aid, dt, prices)
        db_snap = supabase.table("portfolio_snapshots").select("total_value").eq("account_id", aid).eq("snapshot_date", dt.isoformat()).execute()
        db_val = float(rows(db_snap)[0]["total_value"]) if rows(db_snap) else None
        delta_str = f"db={db_val:>10,.2f}" if db_val else "no_snap"
        print(f"  {dt}: cash={snap['cash_balance']:>8,.2f}  market={snap['holdings_market_value']:>10,.2f}  "
              f"total={snap['total_value']:>10,.2f}  ({delta_str})")
