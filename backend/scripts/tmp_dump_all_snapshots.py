"""Dump ALL snapshot data and API performance response for all periods."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'backend')
from database import supabase
from datetime import date, datetime
import json

user_email = 'rajeshp01@gmail.com'
u = supabase.table('users').select('user_id,email').eq('email', user_email).single().execute()
uid = u.data['user_id']
accts = supabase.table('portfolio_accounts').select('account_id,account_name').eq('user_id', uid).execute()
aids = sorted([a['account_id'] for a in accts.data])

# ============================================
# TABLE A: ALL snapshots every row
# ============================================
print("=" * 140)
print("TABLE A: ALL portfolio_snapshots rows")
print("=" * 140)
print(f"{'date':<14} {'acct':<6} {'total_value':<16} {'cost_basis':<16} {'cash_balance':<14} {'net_deposits':<16} {'notes'}")
print("-" * 140)

prev_nd = {7: None, 8: None, 9: None}
for aid in aids:
    rows = supabase.table('portfolio_snapshots').select(
        'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
    ).eq('account_id', aid).order('snapshot_date').execute()
    for r in rows.data or []:
        nd = float(r.get('net_deposits', 0))
        nd_change = ""
        if prev_nd[aid] is not None and abs(nd - prev_nd[aid]) > 0.001:
            nd_change = f" ND_CHANGE:+{nd - prev_nd[aid]:.2f}"
        prev_nd[aid] = nd
        note = nd_change
        print(f"{r['snapshot_date']:<14} {aid:<6} {float(r['total_value']):<16.2f} {float(r['cost_basis']):<16.2f} {float(r['cash_balance']):<14.2f} {float(nd):<16.2f}{note}")

# ============
# TABLE B: Aggregate per date
# ============
print()
print("=" * 120)
print("TABLE B: AGGREGATE per unique date (sum across accounts)")
print("=" * 120)
print(f"{'date':<14} {'total_val':<16} {'cost':<16} {'cash':<14} {'net_dep':<16} {'gain_loss':<16} {'gl%':<12} {'accts'}")
print("-" * 120)

from collections import defaultdict
by_date = defaultdict(lambda: {'val': 0.0, 'cost': 0.0, 'cash': 0.0, 'nd': 0.0, 'count': 0})
for aid in aids:
    rows = supabase.table('portfolio_snapshots').select(
        'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
    ).eq('account_id', aid).order('snapshot_date').execute()
    for r in rows.data or []:
        d = r['snapshot_date']
        by_date[d]['val'] += float(r['total_value'])
        by_date[d]['cost'] += float(r['cost_basis'])
        by_date[d]['cash'] += float(r['cash_balance'])
        by_date[d]['nd'] += float(r['net_deposits'])
        by_date[d]['count'] += 1

for d in sorted(by_date.keys()):
    v = by_date[d]
    gl = v['val'] - v['cost']
    gl_pct = (gl / v['cost'] * 100) if v['cost'] else 0.0
    print(f"{d:<14} {v['val']:<16.2f} {v['cost']:<14.2f} {v['cash']:<14.2f} {v['nd']:<16.2f} {gl:<+16.2f} {gl_pct:<+11.2f}% {v['count']}")

# ============
# TABLE C: Period boundaries — FIRST and LAST snapshot per account
# ============
print()
print("=" * 100)
print("TABLE C: PERIOD BOUNDARIES")
print("=" * 100)
periods = {
    'ALL': datetime(2020,1,1),
    'YTD': datetime(2026,1,1),
    '1Y': datetime(2025,7,7),
    '3M': datetime(2026,4,7),
    '1M': datetime(2026,6,7),
    '1W': datetime(2026,6,30),
}
now_date = datetime(2026,7,7)

for pname, start_dt in periods.items():
    print(f"\n--- {pname} (>= {start_dt.date()}) ---")
    agg_start = {'val': 0.0, 'cost': 0.0, 'cash': 0.0, 'nd': 0.0}
    agg_end = {'val': 0.0, 'cost': 0.0, 'cash': 0.0, 'nd': 0.0}
    count_start = 0
    count_end = 0
    for aid in aids:
        rows = supabase.table('portfolio_snapshots').select(
            'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
        ).eq('account_id', aid).gte('snapshot_date', start_dt.isoformat()).order('snapshot_date').execute()
        if rows.data:
            first = rows.data[0]
            last = rows.data[-1]
            fv = float(first['total_value']); fc = float(first['cost_basis']); fnd = float(first['net_deposits'])
            lv = float(last['total_value']); lc = float(last['cost_basis']); lnd = float(last['net_deposits'])
            agg_start['val'] += fv; agg_start['cost'] += fc; agg_start['nd'] += fnd
            agg_end['val'] += lv; agg_end['cost'] += lc; agg_end['nd'] += lnd
            count_start += 1; count_end += 1
            print(f"  acct={aid}: first={first['snapshot_date']} val={fv:.2f} cost={fc:.2f} nd={fnd:.2f} | last={last['snapshot_date']} val={lv:.2f} cost={lc:.2f} nd={lnd:.2f}")
    start_gl = agg_start['val'] - agg_start['cost']
    end_gl = agg_end['val'] - agg_end['cost']
    print(f"  AGG START: val={agg_start['val']:.2f} cost={agg_start['cost']:.2f} gl={start_gl:.2f} nd={agg_start['nd']:.2f}")
    print(f"  AGG END:   val={agg_end['val']:.2f} cost={agg_end['cost']:.2f} gl={end_gl:.2f} nd={agg_end['nd']:.2f}")