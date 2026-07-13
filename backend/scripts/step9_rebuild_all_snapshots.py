"""Regenerate ALL historical snapshots using event replay for consistent net_deposits.

Optimized: single incremental pass per account, batched writes.

WARNING: This script deletes ALL existing snapshots and rebuilds from scratch.
It should ONLY be run in development/staging environments.
"""
import os, sys; sys.path.insert(0, '.'); sys.path.insert(0, 'backend')

_env = os.environ.get("ENVIRONMENT", "development").lower()
if _env == "production":
    print("ERROR: step9_rebuild_all_snapshots.py must NOT be run in production.")
    print("Use the daily snapshot job (compute_daily_snapshots) instead.")
    sys.exit(1)

import json, logging, time
from datetime import date, datetime, timedelta
from decimal import Decimal
from collections import defaultdict
from typing import Dict, Optional
from database import supabase

logger = logging.getLogger("rebuild")
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.replay_engine import ReplayEngine, AccountState
from shared.snapshot_builder import build_snapshot_row

event_store = EventStore()
replay_engine = ReplayEngine(event_store)

AIDS = [7, 8, 9, 10, 11, 12]
ACCOUNT_CURRENCY = "USD"

# ── Load all events once per account ──
print("Loading events...")
all_events_by_acct = {}
for aid in AIDS:
    events = event_store.get_all_events(aggregate_type="account")
    account_events = []
    for ev in events:
        ev_aid = None
        agg_id = ev.get("aggregate_id", "")
        if agg_id.startswith("account_"):
            try: ev_aid = int(agg_id.split("_")[1])
            except: pass
        if ev_aid == aid:
            account_events.append(ev)
    account_events.sort(key=lambda e: replay_engine._get_event_date(e) or date.min)
    all_events_by_acct[aid] = account_events
    print(f"  Account {aid}: {len(account_events)} events")

# ── Build all unique dates from existing snapshots and events ──
all_dates_set = set()
for aid in AIDS:
    rows = supabase.table('portfolio_snapshots').select('snapshot_date').eq('account_id', aid).execute()
    for r in rows.data or []:
        all_dates_set.add(r['snapshot_date'])
    for ev in all_events_by_acct[aid]:
        data = ev.get("data", {}) or {}
        for key in ["transaction_date", "effective_date"]:
            val = data.get(key)
            if val: all_dates_set.add(str(val)[:10])
        created = ev.get("created_at", "")
        if created: all_dates_set.add(str(created)[:10])

# Add month-end anchors
import calendar
for d_str in list(all_dates_set):
    dt = date.fromisoformat(d_str)
    all_dates_set.add(dt.replace(day=1).isoformat())
    ld = calendar.monthrange(dt.year, dt.month)[1]
    all_dates_set.add(dt.replace(day=ld).isoformat())

all_dates = sorted(all_dates_set)
print(f"Total unique dates: {len(all_dates)}")
print(f"Range: {all_dates[0]} to {all_dates[-1]}")

# ── Load prices once ──
cids = set()
for aid in AIDS:
    for ev in all_events_by_acct[aid]:
        cid = ev.get("data", {}).get("company_id")
        if cid: cids.add(int(cid))

company_names = {}
if cids:
    comps = supabase.table('companies').select('company_id,company_name,ticker_symbol').in_('company_id', list(cids)).execute()
    for row in comps.data or []:
        company_names[int(row['company_id'])] = row['company_name'] or row['ticker_symbol']

# ── Load historical prices (price_history) with split adjustment ──
# Query per-company via the repo method to get split adjustment + anomaly
# normalization, while avoiding Supabase's 1000-row default limit.
price_history_map = {}
if cids:
    max_date = date.fromisoformat(all_dates[-1])
    repo = PortfolioRepository(supabase)
    for cid in cids:
        try:
            single_map = repo.get_all_prices_historical([cid], max_date)
            if single_map:
                price_history_map[cid] = single_map[cid]
        except Exception as e:
            logger.error(f"Failed to load price_history for cid={cid}: {e}")
    ph_total = sum(len(v) for v in price_history_map.values())
    print(f"Price history: {ph_total} rows for {len(price_history_map)} companies (split-adjusted)")

# Also load current prices for reference (used for data_quality age checks, not for valuation)
prices_by_company = {}
if cids:
    cmr = supabase.table('current_market_data').select('company_id,current_price,last_updated').in_('company_id', list(cids)).execute()
    for row in cmr.data or []:
        updated = row.get('last_updated')
        price_date = str(updated)[:10] if updated else all_dates[-1]
        prices_by_company[int(row['company_id'])] = {'price': float(row.get('current_price', 0) or 0), 'price_date': price_date}
    print(f"Current prices: {len(prices_by_company)} companies")

print()

# ── Load exchange_override for CDR holdings (from portfolio_holdings) ──
exchange_overrides: Dict[int, Dict[int, Optional[str]]] = {}
for aid in AIDS:
    try:
        rows = supabase.table('portfolio_holdings').select('company_id, exchange_override').eq('account_id', aid).execute()
        exchange_overrides[aid] = {}
        for row in rows.data or []:
            if row.get('exchange_override'):
                exchange_overrides[aid][row['company_id']] = row['exchange_override']
    except Exception as e:
        print(f"  WARNING: could not load exchange_overrides for account {aid}: {e}")
        exchange_overrides[aid] = {}

# ── Single-pass incremental replay ──
MAX_BATCH = 50
total_written = 0
total_acct_rows = {aid: 0 for aid in AIDS}

print("Deleting old snapshots...")
for aid in AIDS:
    supabase.table('portfolio_snapshots').delete().eq('account_id', aid).execute()
print("Old snapshots deleted.\n")

for aid in AIDS:
    t0 = time.time()
    print(f"Processing account {aid}...")
    
    state = AccountState(account_id=aid)
    snap_batch = []
    
    # Group events by their effective date
    events_by_date = defaultdict(list)
    for ev in all_events_by_acct[aid]:
        ev_date = replay_engine._get_event_date(ev)
        if ev_date:
            events_by_date[ev_date.isoformat()].append(ev)
        else:
            created = ev.get("created_at", "")
            events_by_date[str(created)[:10] if created else "2000-01-01"].append(ev)
    
    for sd in all_dates:
        target_date = date.fromisoformat(sd)
        
        # Apply all events with this date
        for ev in events_by_date.get(sd, []):
            handler_name = f"_handle_{ev.get('event_type', '')}"
            handler = getattr(replay_engine, handler_name, None)
            if handler:
                handler(state, ev)
        
        # Skip if no activity
        if not state.holdings and float(state.cash_balance) == 0 and float(state.net_deposits) == 0:
            continue
        
        # Build holdings list (include exchange_override for CDR pricing)
        acct_overrides = exchange_overrides.get(aid, {})
        holdings_state = []
        for cid, h in state.holdings.items():
            holdings_state.append({
                'company_id': cid, 'symbol': h.symbol,
                'company_name': company_names.get(cid, h.symbol),
                'quantity': float(h.quantity),
                'total_cost': float(h.total_cost),
                'average_cost': float(h.average_cost),
                'realized_gain_loss': float(h.realized_gain_loss),
                'currency': ACCOUNT_CURRENCY,
                'exchange_override': acct_overrides.get(cid),
            })
        
        try:
            # Pass empty prices_by_company so Tier 1 (current prices) never fires.
            # All snapshots use Tier 2 forward-fill from price_history, falling to
            # Tier 3 cost_basis — consistent pricing across ALL dates, no spike.
            snapshot = build_snapshot_row(
                account_id=aid, snapshot_date=target_date,
                holdings_state=holdings_state,
                cash_balance=state.cash_balance,
                net_deposits=state.net_deposits,
                prices_by_company={},
                job_id=f"rebuild_{aid}_{sd}",
                stale_threshold_days=0,
                account_currency=ACCOUNT_CURRENCY,
                price_history=price_history_map,
            )
        except Exception as e:
            print(f"  ERROR building snapshot {aid} {sd}: {e}")
            continue
        
        db_row = {
            'account_id': aid,
            'snapshot_date': sd,
            'total_value': snapshot.get('total_value', 0),
            'holdings_market_value': snapshot.get('holdings_market_value', 0),
            'cost_basis': snapshot.get('cost_basis', 0),
            'cash_balance': snapshot.get('cash_balance', 0),
            'net_deposits': snapshot.get('net_deposits', 0),
            'holdings_json': snapshot.get('holdings_json') or [],
            'computed_at': datetime.now().isoformat(),
            'data_quality_flag': snapshot.get('data_quality_flag', 'OK'),
        }
        snap_batch.append(db_row)
        total_acct_rows[aid] += 1
        
        if len(snap_batch) >= MAX_BATCH:
            try:
                supabase.table('portfolio_snapshots').insert(snap_batch).execute()
            except Exception as e:
                print(f"  ERROR writing batch: {e}")
                for br in snap_batch:
                    try: supabase.table('portfolio_snapshots').insert(br).execute()
                    except: pass
            total_written += len(snap_batch)
            snap_batch = []
    
    # Flush remaining
    if snap_batch:
        try:
            supabase.table('portfolio_snapshots').insert(snap_batch).execute()
        except Exception as e:
            print(f"  ERROR writing final batch: {e}")
        total_written += len(snap_batch)
    
    elapsed = time.time() - t0
    print(f"  Account {aid}: {total_acct_rows[aid]} snapshots in {elapsed:.1f}s")

print(f"\nTotal written: {total_written}")

# ── Verify ──
print("\n=== VERIFICATION ===")
for aid in AIDS:
    rows = supabase.table('portfolio_snapshots').select(
        'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
    ).eq('account_id', aid).order('snapshot_date').execute()
    data = rows.data or []
    print(f"\nAccount {aid}: {len(data)} rows")
    prev_nd = None
    nd_drops = 0
    for r in data:
        nd = float(r.get('net_deposits', 0))
        if prev_nd is not None and nd < prev_nd - 0.01:
            nd_drops += 1
            print(f"  ❌ ND DROP: {r['snapshot_date']}: {prev_nd:.2f} -> {nd:.2f}")
        prev_nd = nd
    print(f"  Net deposit decreases: {nd_drops}")
    if data:
        print(f"  First: {data[0]['snapshot_date']} val={data[0]['total_value']} nd={data[0]['net_deposits']}")
        print(f"  Last:  {data[-1]['snapshot_date']} val={data[-1]['total_value']} nd={data[-1]['net_deposits']}")

# Print the specific dates the user asked about
print("\n\n=== UI PRESENTED VALUES FOR ALL PERIODS ===")
# Aggregate by date
by_date = defaultdict(lambda: {'val': 0.0, 'cost': 0.0, 'cash': 0.0, 'nd': 0.0})
for aid in AIDS:
    rows = supabase.table('portfolio_snapshots').select(
        'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
    ).eq('account_id', aid).order('snapshot_date').execute()
    for r in rows.data or []:
        d = r['snapshot_date']; by_date[d]['val'] += float(r['total_value'])
        by_date[d]['cost'] += float(r['cost_basis']); by_date[d]['cash'] += float(r['cash_balance'])
        by_date[d]['nd'] += float(r['net_deposits'])

# Period definitions
from datetime import datetime as dt_mod
periods = {
    'ALL': dt_mod(2020,1,1), 'YTD': dt_mod(2026,1,1), '1Y': dt_mod(2025,7,7),
    '3M': dt_mod(2026,4,7), '1M': dt_mod(2026,6,7), '1W': dt_mod(2026,6,30),
}
today = '2026-07-08'

for pname, start_dt in periods.items():
    print(f"\n{'='*80}")
    print(f"PERIOD: {pname}")
    print(f"{'='*80}")
    matching = sorted([d for d in by_date.keys() if d >= start_dt.strftime('%Y-%m-%d') and d <= today])
    if not matching:
        print("  No data")
        continue
    # Show first and last 5
    show = matching[:5] + (['...'] if len(matching) > 10 else []) + matching[-5:]
    for d in show:
        if d == '...':
            print("  ...")
            continue
        v = by_date[d]
        gl = v['val'] - v['cost']
        gl_pct = (gl / v['cost'] * 100) if v['cost'] else 0
        print(f"  {d}: Value={v['val']:.2f} Cost={v['cost']:.2f} G/L={gl:+.2f} ({gl_pct:+.2f}%) NetDep={v['nd']:.2f}")
    first_d = matching[0]; last_d = matching[-1]
    fv = by_date[first_d]; lv = by_date[last_d]
    ret = lv['val'] - fv['val']; ret_pct = (ret / fv['val'] * 100) if fv['val'] else 0
    nd_change = lv['nd'] - fv['nd']
    print(f"\n  SUMMARY: {first_d} -> {last_d}")
    print(f"    Start: Value={fv['val']:.2f} NetDep={fv['nd']:.2f}")
    print(f"    End:   Value={lv['val']:.2f} NetDep={lv['nd']:.2f}")
    print(f"    Return: {ret:+.2f} ({ret_pct:+.2f}%)")
    print(f"    Net Deposits Change: {nd_change:+.2f}")