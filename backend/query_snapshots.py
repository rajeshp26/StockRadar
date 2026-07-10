import sys; sys.path.insert(0, '.')
from datetime import date, datetime
from database import supabase

res = supabase.table("portfolio_snapshots").select(
    "snapshot_date,total_value,holdings_market_value,cost_basis,cash_balance,net_deposits,data_quality_flag"
).eq("account_id", 9).order("snapshot_date").execute()

rows = res.data or []
print(f"Total snapshots for account 9: {len(rows)}")
print(f"Date range: {rows[0]['snapshot_date']} to {rows[-1]['snapshot_date']}")
print()

today = date.today().isoformat()
periods = {
    'ALL': '2020-01-01',
    'YTD': '2026-01-01',
    '1Y':  '2025-07-09',
    '3M':  '2026-04-09',
    '1M':  '2026-06-09',
    '1W':  '2026-07-02',
}

for pname, start_date in sorted(periods.items(), key=lambda x: x[1], reverse=True):
    matching = [r for r in rows if r['snapshot_date'] >= start_date and r['snapshot_date'] <= today]
    if not matching:
        print(f"\n=== {pname}: No data ===")
        continue

    first = matching[0]
    last = matching[-1]
    fv = float(first['total_value'])
    lv = float(last['total_value'])
    fnd = float(first['net_deposits'])
    lnd = float(last['net_deposits'])

    print(f"\n=== {pname} ({start_date} to {today}) ===")
    print(f"  Snapshots: {len(matching)}")
    print(f"  First: {first['snapshot_date']}  Value={fv:.2f}  NetDep={fnd:.2f}")
    print(f"  Last:  {last['snapshot_date']}  Value={lv:.2f}  NetDep={lnd:.2f}")
    print(f"  Value Change: {lv-fv:+.2f} ({(lv-fv)/fv*100 if fv else 0:+.2f}%)")
    print(f"  NetDep Change: {lnd-fnd:+.2f}")

    print(f"\n  All dates ({min(10, len(matching))} shown):")
    for i, r in enumerate(matching):
        if i < 10 or i >= len(matching) - 3:
            print(f"    {r['snapshot_date']}  Value={float(r['total_value']):10.2f}  Cost={float(r['cost_basis']):10.2f}  NetDep={float(r['net_deposits']):10.2f}")
        elif i == 10:
            print(f"    ... ({len(matching)-13} more dates) ...")