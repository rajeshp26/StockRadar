"""Full-period verification: key period values per account from event replay.
Shows only snapshot dates (what the UI would display) plus key event dates."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, datetime, timezone
from database import supabase
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore

engine = ReplayEngine(EventStore())

# Build price map from current_market_data
cids = set()
for aid in [7, 8, 9, 10, 11, 12]:
    ph = supabase.table("portfolio_holdings").select("company_id").eq("account_id", aid).execute()
    for h in (ph.data or []):
        if h.get("company_id"):
            cids.add(h["company_id"])

prices_by_company = {}
if cids:
    cmr = supabase.table("current_market_data").select("company_id, current_price").in_("company_id", list(cids)).execute()
    for row in (cmr.data or []):
        cid = row["company_id"]
        px = row.get("current_price")
        if px is not None:
            prices_by_company[cid] = {"price": float(px)}

ACCOUNT_NAMES = {7: "Non-registered", 8: "RRSP", 9: "TFSA", 10: "TFSA-2", 11: "RRSP-2", 12: "Margin"}

print("=" * 120)
print("FINAL VERIFICATION: PORTFOLIO VALUES AT SNAPSHOT DATES")
print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
print(f"Prices from current_market_data: {len(prices_by_company)} of {len(cids)} companies")
print("=" * 120)

for aid in [7, 8, 9, 10, 11, 12]:
    label = ACCOUNT_NAMES[aid]
    
    # Get snapshot dates from DB
    s = supabase.table("portfolio_snapshots").select("snapshot_date, total_value").eq("account_id", aid).order("snapshot_date").execute()
    snap_dates = sorted(set(d["snapshot_date"][:10] for d in (s.data or [])))
    snap_by_date = {d["snapshot_date"][:10]: float(d["total_value"]) for d in (s.data or [])}
    
    print(f"\n{'=' * 120}")
    print(f"Account {aid} ({label}) — {len(snap_dates)} snapshot dates")
    print(f"{'=' * 120}")
    print(f"  {'Date':<14} {'Replay Total':>14} {'Replay Market':>14} {'Replay Cost':>14} {'Replay Cash':>12} {'Snap Total':>14} {'Diff':>10} {'Quality':<20}")
    print(f"  {'-'*13:>14} {'-'*13:>14} {'-'*13:>14} {'-'*13:>14} {'-'*11:>12} {'-'*13:>14} {'-'*7:>8} {'-'*19:>20}")
    
    for dt_str in snap_dates:
        try:
            dt = date.fromisoformat(dt_str)
        except (ValueError, TypeError):
            continue
        
        snap_val = snap_by_date[dt_str]
        r = engine.build_snapshot_from_replay(aid, dt, prices_by_company)
        rv = float(r["total_value"])
        mv = float(r["holdings_market_value"])
        cb = float(r["cost_basis"])
        ca = float(r["cash_balance"])
        qf = r["data_quality_flag"]
        diff = rv - snap_val
        
        status = "OK" if abs(diff) < 0.01 else "MISMATCH"
        
        print(f"  {dt_str:<14} ${rv:>11,.2f} ${mv:>11,.2f} ${cb:>11,.2f} ${ca:>9,.2f} ${snap_val:>11,.2f} {diff:>+7,.2f} {qf:<20} {status:<8}")
    
    # Today's latest
    today = date.today()
    r = engine.build_snapshot_from_replay(aid, today, prices_by_company)
    print(f"  {'[TODAY]':<14} ${float(r['total_value']):>11,.2f} ${float(r['holdings_market_value']):>11,.2f} ${float(r['cost_basis']):>11,.2f} ${float(r['cash_balance']):>9,.2f} {'':>14} {'':>8} {r['data_quality_flag']:<20}")

print()
print("=" * 120)
print("END-TO-END CONSISTENCY: HOLDING QUANTITIES")
print("=" * 120)
all_ok = True
for aid in [7, 8, 9, 10, 11, 12]:
    snap = engine.build_snapshot_from_replay(aid, date.today(), prices_by_company)
    ph = supabase.table("portfolio_holdings").select("company_id, quantity, total_cost").eq("account_id", aid).execute()
    ph_map = {}
    for h in (ph.data or []):
        cid = h.get("company_id")
        if cid:
            ph_map[cid] = {"qty": float(h["quantity"]), "cost": float(h["total_cost"])}
    
    replay_cids = set(cid for cid in snap["holdings"].keys())
    ph_cids = set(ph_map.keys())
    
    if replay_cids != ph_cids:
        print(f"  ACCOUNT {aid}: HOLDING SET MISMATCH — extra in replay: {replay_cids - ph_cids}, extra in db: {ph_cids - replay_cids}")
        all_ok = False
        continue
    
    mismatches = 0
    for cid in replay_cids:
        rq = float(snap["holdings"][cid].quantity)
        pq = ph_map[cid]["qty"]
        if abs(rq - pq) > 0.001:
            print(f"  ACCOUNT {aid} CID {cid}: replay qty={rq} ph qty={pq} MISMATCH")
            mismatches += 1
            all_ok = False
    
    if mismatches == 0:
        print(f"  Account {aid}: {len(replay_cids)} holdings — ALL QUANTITIES MATCH ✓")

print()
if all_ok:
    print("=== ALL 6 ACCOUNTS: QUANTITIES MATCH 100% ===")
else:
    print("=== DISCREPANCIES FOUND ===")

print()
print("=" * 120)
print("PRICE COVERAGE")
print("=" * 120)
print(f"  Companies in current_market_data: {len(prices_by_company)}")
print(f"  Companies in portfolio_holdings: {len(cids)}")
missing = cids - set(prices_by_company.keys())
if missing:
    print(f"  Missing prices for {len(missing)} companies: {sorted(missing)}")

print()
print("=" * 120)
print("VERIFICATION COMPLETE")
print("=" * 120)