"""Query portfolio values — backend (snapshots) and live (holdings*prices) for all periods."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'backend')
import json
from datetime import date
from database import supabase

user_email = 'rajeshp01@gmail.com'
u = supabase.table('users').select('user_id,auth_id,email,preferred_currency').eq('email', user_email).single().execute()
uid = u.data['user_id']
ccy = u.data.get('preferred_currency', 'CAD')
print(f'user_id={uid} currency={ccy}')
print()

accts = supabase.table('portfolio_accounts').select('account_id,account_name').eq('user_id', uid).execute()
aids = sorted([a['account_id'] for a in accts.data])
print(f'accounts: {aids}')
print()

# ──────────────────────────────────────────────────────────────────
# ALL-PERIOD DATES (12 dates specified)
# ──────────────────────────────────────────────────────────────────
all_dates = ['2026-01-01','2026-01-15','2026-01-29','2026-02-12','2026-02-26',
             '2026-03-12','2026-03-26','2026-04-14','2026-04-29','2026-05-30',
             '2026-06-29','2026-07-07']

# Period boundaries for dashboard performance periods
period_map = {
    'ALL': '2020-01-01',
    'YTD': '2026-01-01',
    '1Y':  '2025-07-07',
    '3M':  '2026-04-07',
    '1M':  '2026-06-07',
    '1W':  '2026-06-30',
}

# ──────────────────────────────────────────────────────────────────
# 1) SNAPSHOT data (backend stored snapshots)
# ──────────────────────────────────────────────────────────────────
print('=' * 100)
print('SECTION 1: BACKEND SNAPSHOTS (portfolio_snapshots table)')
print('=' * 100)

# First gather ALL snapshots (not just the 12 dates)
all_snapdates_by_acct = {}
for aid in aids:
    snap = supabase.table('portfolio_snapshots').select(
        'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
    ).eq('account_id', aid).order('snapshot_date').execute()
    all_snapdates_by_acct[aid] = snap.data or []

# For each period, find latest snapshot at or after period start
print()
print('--- PERIOD VALUES FROM SNAPSHOTS ---')
print(f'{"Period":<6} {"Start Date":<14} {"Total Value":<16} {"Cost Basis":<16} {"Gain/Loss":<16} {"G/L%":<12} {"Net Deposits":<16} {"Accounts":<10}')
print(f'{"":-<6} {"":-<14} {"":-<16} {"":-<16} {"":-<16} {"":-<12} {"":-<16} {"":-<10}')
for pname, start_str in period_map.items():
    total_val = 0.0; total_cost = 0.0; total_nd = 0.0; total_cash = 0.0; count = 0
    for aid in aids:
        snaps = all_snapdates_by_acct[aid]
        # Find latest snapshot >= period start
        best = None
        for s in reversed(snaps):
            if s['snapshot_date'] >= start_str:
                best = s
            elif s['snapshot_date'] < start_str:
                break
        if best:
            total_val += float(best['total_value'] or 0)
            total_cost += float(best['cost_basis'] or 0)
            total_nd += float(best['net_deposits'] or 0)
            total_cash += float(best['cash_balance'] or 0)
            count += 1
    gl = total_val - total_cost
    gl_pct = (gl / total_cost * 100) if total_cost else 0.0
    print(f'{pname:<6} {start_str:<14} {total_val:<16.2f} {total_cost:<16.2f} {gl:<+16.2f} {gl_pct:<+11.2f}% {total_nd:<16.2f} {count}/{len(aids)}')

# Override ALL period with the specific 12 dates
print()
print('--- ALL PERIOD — Specific Date Snapshots ---')
print(f'{"Date":<14} {"Acct 7 Value":<16} {"Acct 7 Cost":<14} {"Acct 7 NetDep":<14} {"Acct 8 Value":<16} {"Acct 8 Cost":<14} {"Acct 8 NetDep":<14} {"Acct 9 Value":<16} {"Acct 9 Cost":<14} {"Acct 9 NetDep":<14} {"Total Value":<16} {"Total Cost":<16} {"Total Gain/Loss":<16} {"Total NetDep":<16}')
print(f'{"":-<14} {"":-<16} {"":-<14} {"":-<14} {"":-<16} {"":-<14} {"":-<14} {"":-<16} {"":-<14} {"":-<14} {"":-<16} {"":-<16} {"":-<16} {"":-<16}')
for d in all_dates:
    row = {}
    for aid in aids:
        best = None
        snaps = all_snapdates_by_acct[aid]
        for s in snaps:
            if s['snapshot_date'] == d:
                best = s
                break
        if best:
            row[aid] = best
        else:
            row[aid] = None
    tv7 = float(row[7]['total_value']) if row[7] else 0
    tc7 = float(row[7]['cost_basis']) if row[7] else 0
    nd7 = float(row[7]['net_deposits']) if row[7] else 0
    tv8 = float(row[8]['total_value']) if row[8] else 0
    tc8 = float(row[8]['cost_basis']) if row[8] else 0
    nd8 = float(row[8]['net_deposits']) if row[8] else 0
    tv9 = float(row[9]['total_value']) if row[9] else 0
    tc9 = float(row[9]['cost_basis']) if row[9] else 0
    nd9 = float(row[9]['net_deposits']) if row[9] else 0
    tv = tv7 + tv8 + tv9; tc = tc7 + tc8 + tc9; tnd = nd7 + nd8 + nd9
    gl = tv - tc
    v7 = f'{tv7:.2f}' if row[7] else 'N/A'
    c7 = f'{tc7:.2f}' if row[7] else 'N/A'
    n7 = f'{nd7:.2f}' if row[7] else 'N/A'
    v8 = f'{tv8:.2f}' if row[8] else 'N/A'
    c8 = f'{tc8:.2f}' if row[8] else 'N/A'
    n8 = f'{nd8:.2f}' if row[8] else 'N/A'
    v9 = f'{tv9:.2f}' if row[9] else 'N/A'
    c9 = f'{tc9:.2f}' if row[9] else 'N/A'
    n9 = f'{nd9:.2f}' if row[9] else 'N/A'
    print(f'{d:<14} {v7:<16} {c7:<14} {n7:<14} {v8:<16} {c8:<14} {n8:<14} {v9:<16} {c9:<14} {n9:<14} {tv:<16.2f} {tc:<16.2f} {gl:<+16.2f} {tnd:<16.2f}')

# ──────────────────────────────────────────────────────────────────
# 2) LIVE portfolio_holdings * current_price (what UI shows today)
# ──────────────────────────────────────────────────────────────────
print()
print('=' * 100)
print('SECTION 2: LIVE HOLDINGS (portfolio_holdings * current_market_data) — UI PRESENTED VALUES')
print('=' * 100)

cids = set()
for aid in aids:
    rows = supabase.table('portfolio_holdings').select('company_id').eq('account_id', aid).execute()
    for h in rows.data or []:
        if h.get('company_id'): cids.add(h['company_id'])

prices = {}
if cids:
    cmr = supabase.table('current_market_data').select('company_id,current_price').in_('company_id', list(cids)).execute()
    for row in cmr.data or []:
        prices[row['company_id']] = float(row.get('current_price', 0))

print(f'Prices found: {len(prices)}/{len(cids)} companies')

print()
print('--- PER-ACCOUNT LIVE VALUES ---')
print(f'{"Account":<12} {"Holdings":<10} {"Market Value":<16} {"Cost Basis":<16} {"Unrealized GL":<16} {"Realized GL":<16} {"Net Deposits":<16}')
print(f'{"":-<12} {"":-<10} {"":-<16} {"":-<16} {"":-<16} {"":-<16} {"":-<16}')
total_mv = 0.0; total_tc = 0.0; total_rgl = 0.0; total_nd = 0.0
for aid in aids:
    rows = supabase.table('portfolio_holdings').select('company_id,symbol,quantity,total_cost,average_cost,realized_gain_loss').eq('account_id', aid).execute()
    mv = 0.0; tc = 0.0; rgl = 0.0
    for h in rows.data or []:
        qty = float(h.get('quantity', 0) or 0)
        tcc = float(h.get('total_cost', 0) or 0)
        r = float(h.get('realized_gain_loss', 0) or 0)
        cid = h.get('company_id')
        avgc = float(h.get('average_cost', 0) or 0)
        px = prices.get(cid)
        if px:
            mv += qty * px
        else:
            mv += tcc
        tc += tcc; rgl += r
    nd = 0.0
    snap = supabase.table('portfolio_snapshots').select('net_deposits').eq('account_id', aid).order('snapshot_date', desc=True).limit(1).execute()
    if snap.data:
        nd = float(snap.data[0]['net_deposits'])
    total_mv += mv; total_tc += tc; total_rgl += rgl; total_nd += nd
    print(f'{aid:<12} {len(rows.data or []):<10} {mv:<16.2f} {tc:<16.2f} {mv-tc:<+16.2f} {rgl:<+16.2f} {nd:<16.2f}')

print(f'{"TOTAL":<12} {"":<10} {total_mv:<16.2f} {total_tc:<16.2f} {total_mv-total_tc:<+16.2f} {total_rgl:<+16.2f} {total_nd:<16.2f}')

# ──────────────────────────────────────────────────────────────────
# 3) UI Performance tab values: for each period, the value curve
# ──────────────────────────────────────────────────────────────────
print()
print('=' * 100)
print('SECTION 3: PERFORMANCE PERIOD VALUES (what UI Performance chart shows)')
print('=' * 100)

# The performance chart shows value per snapshot date within each period
# For each period, find all available snapshot dates within that window
for pname, start_str in period_map.items():
    print()
    print(f'--- {pname} (>= {start_str}) ---')
    print(f'{"Date":<14} {"Acct7 Val":<14} {"Acct8 Val":<14} {"Acct9 Val":<14} {"Total Val":<14} {"Total Cost":<14} {"Net Dep":<14}')
    print(f'{"":-<14} {"":-<14} {"":-<14} {"":-<14} {"":-<14} {"":-<14} {"":-<14}')
    # Collect snapshot dates that fall within this period
    snap_dates_set = set()
    snap_by_acct_date = {}
    for aid in aids:
        for s in all_snapdates_by_acct[aid]:
            if s['snapshot_date'] >= start_str and s['snapshot_date'] <= '2026-07-07':
                snap_dates_set.add(s['snapshot_date'])
                if aid not in snap_by_acct_date:
                    snap_by_acct_date[aid] = {}
                snap_by_acct_date[aid][s['snapshot_date']] = s
    for d in sorted(snap_dates_set):
        vals = [snap_by_acct_date.get(aid, {}).get(d) for aid in aids]
        v7 = float(vals[0]['total_value']) if vals[0] else 0
        v8 = float(vals[1]['total_value']) if vals[1] else 0
        v9 = float(vals[2]['total_value']) if vals[2] else 0
        c7 = float(vals[0]['cost_basis']) if vals[0] else 0
        c8 = float(vals[1]['cost_basis']) if vals[1] else 0
        c9 = float(vals[2]['cost_basis']) if vals[2] else 0
        n7 = float(vals[0]['net_deposits']) if vals[0] else 0
        n8 = float(vals[1]['net_deposits']) if vals[1] else 0
        n9 = float(vals[2]['net_deposits']) if vals[2] else 0
        tv = v7+v8+v9; tc = c7+c8+c9; tn = n7+n8+n9
        t7 = f'{v7:.2f}' if vals[0] else 'N/A'
        t8 = f'{v8:.2f}' if vals[1] else 'N/A'
        t9 = f'{v9:.2f}' if vals[2] else 'N/A'
        print(f'{d:<14} {t7:<14} {t8:<14} {t9:<14} {tv:<14.2f} {tc:<14.2f} {tn:<14.2f}')