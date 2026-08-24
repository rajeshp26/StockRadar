"""Final Verification: Show what the UI would display for each account, full period."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.price_repository import PriceRepository
from shared.replay_engine import ReplayEngine


def dates_with_snapshots(s_data):
    if not s_data:
        return set()
    return set(d["snapshot_date"] for d in s_data)

def dates_with_events(aid, engine):
    evts = engine.event_store.get_events(aggregate_type="account")
    dates = set()
    for e in evts:
        from shared.replay_engine import _parse_account_id
        if _parse_account_id(e.get("aggregate_id","")) != aid:
            continue
        d = engine._get_event_date(e)
        if d:
            dates.add(d.isoformat())
    return sorted(dates)

engine = ReplayEngine(EventStore())

# Get prices
ph = supabase.table("portfolio_holdings").select("company_id, exchange_override").execute()
pairs = [(h["company_id"], h.get("exchange_override") or "UNKNOWN") for h in (ph.data or [])]
price_repo = PriceRepository()
price_details = price_repo.get_prices_for_holdings(pairs)

prices_by_company = {}
for (cid, exch), px in price_details.items():
    if cid not in prices_by_company:
        prices_by_company[cid] = {"price": px}

today = date.today()

print("=" * 90)
print("STOCKERPRO — PORTFOLIO PERFORMANCE REPORT (Event-Sourced Read Model)")
print(f"Date: {today}")
print("=" * 90)

for aid in [7, 8, 9, 10, 11, 12]:
    snap = engine.build_snapshot_from_replay(aid, today, prices_by_company)
    holdings = snap["holdings_json"]

    print()
    print(f"--- Account {aid} ({['Non-registered','RRSP','TFSA','TFSA-2','RRSP-2','Margin'][aid-7]}) ---")
    print(f"  Total Value:     ${snap['total_value']:>10,.2f}")
    print(f"  Market Value:    ${snap['holdings_market_value']:>10,.2f}")
    print(f"  Cost Basis:      ${snap['cost_basis']:>10,.2f}")
    print(f"  Cash Balance:    ${snap['cash_balance']:>10,.2f}")
    print(f"  Unrealized P&L:  ${snap['holdings_market_value'] - snap['cost_basis']:>10,.2f}")
    print(f"  Data Quality:    {snap['data_quality_flag']}")

    # Sort holdings by value descending
    sorted_h = sorted(holdings, key=lambda h: abs(h["current_value"]), reverse=True)[:10]
    print("  Top Holdings (by value):")
    print(f"    {'Symbol':>8} {'Qty':>8} {'Price':>10} {'Value':>12} {'Cost':>10} {'P&L':>10}")
    print(f"    {'-'*8} {'-'*8} {'-'*10} {'-'*12} {'-'*10} {'-'*10}")
    for h in sorted_h:
        sym = h["symbol"] or f"CID{h['company_id']}"
        ul = h.get("unrealized_gain_loss", 0)
        print(f"    {sym:>8} {h['quantity']:>8.1f} ${h['current_price']:>7.2f} ${h['current_value']:>9,.2f} ${h['cost_basis']:>7,.2f} ${ul:>+7,.2f}")

    # Missing prices
    missing = [h for h in holdings if h.get("price_data_quality") in ("UNAVAILABLE", "COST_FALLBACK")]
    if missing:
        symbols_str = ", ".join(sorted(set(h.get("symbol", f"ID{h['company_id']}") for h in missing)))
        print(f"  PRICE DATA MISSING: {len(missing)} holdings ({symbols_str}) — showing cost basis")

print()
print("=" * 90)
print("FULL PERIOD PORTFOLIO VALUES (replay at each snapshot date)")
print("=" * 90)

# For each account, show values at all available snapshot dates
for aid in [7, 8, 9]:
    s = supabase.table("portfolio_snapshots").select("snapshot_date, total_value, cost_basis").eq("account_id", aid).order("snapshot_date").execute()
    dates_with_snapshots = set(d["snapshot_date"] for d in (s.data or []))

    label = ["Non-registered", "RRSP", "TFSA"][aid - 7]
    print(f"\n--- Account {aid} ({label}) — Full History ---")
    print(f"  {'Date':<14} {'Total Value':>14} {'Cost Basis':>14} {'Snap?':<8}")
    print(f"  {'-'*14} {'-'*14} {'-'*14} {'-'*8}")

    # Generate dates from query dates range
    if s.data:
        min_date = min(s.data, key=lambda d: d["snapshot_date"])["snapshot_date"]
        max_date = max(s.data, key=lambda d: d["snapshot_date"])["snapshot_date"]
    else:
        min_date = "2025-07-24"
        max_date = today.isoformat()

    # Generate a set of interesting dates
    snapshot_dates = sorted(dates_with_events(aid, engine))
    for dt_str in snapshot_dates:
        dt = date.fromisoformat(dt_str) if isinstance(dt_str, str) else dt_str
        if isinstance(dt_str, str):
            pass
        elif hasattr(dt_str, 'isoformat'):
            dt_str = dt_str.isoformat()

        snap = engine.build_snapshot_from_replay(aid, date.fromisoformat(dt_str[:10]), prices_by_company)
        has_snap = "YES" if dt_str[:10] in dates_with_snapshots(s.data) else "NO"
        print(f"  {dt_str[:10]:<14} ${snap['total_value']:>11,.2f} ${snap['cost_basis']:>11,.2f} {has_snap:<8}")