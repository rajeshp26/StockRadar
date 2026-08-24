import os
import sys

sys.path.insert(0, '.')
from dotenv import load_dotenv

load_dotenv('.env')
from datetime import date

from supabase import create_client

client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

snaps = client.table('portfolio_snapshots').select('snapshot_date,total_value,cost_basis,cash_balance,net_deposits,data_quality_flag').eq('account_id', 9).order('snapshot_date', desc=False).execute()

start = date(2021, 2, 8)
end = date(2026, 7, 14)

filtered = [s for s in snaps.data if start <= date.fromisoformat(s['snapshot_date']) <= end]

# 30-day compression for ALL period
compressed = [filtered[0]]
last_sel = date.fromisoformat(filtered[0]['snapshot_date'])
for s in filtered[1:]:
    cur = date.fromisoformat(s['snapshot_date'])
    if (cur - last_sel).days >= 30:
        compressed.append(s)
        last_sel = cur
if compressed[-1]['snapshot_date'] != filtered[-1]['snapshot_date']:
    compressed.append(filtered[-1])

print("Period: ALL")
print("Raw:", len(filtered), "Compressed:", len(compressed))
print()
hdr = "{:<14} {:>14} {:>14} {:>14} {:>14} {:>12}".format("date", "value", "net_deposits", "cost_basis", "cash", "quality")
print(hdr)
print("-" * len(hdr))
for s in compressed:
    tv = s.get('total_value') or 0
    nd = s.get('net_deposits') or 0
    cb = s.get('cost_basis') or 0
    ca = s.get('cash_balance') or 0
    qf = s.get('data_quality_flag') or 'OK'
    row = "{:<14} {:>14.2f} {:>14.2f} {:>14.2f} {:>14.2f} {:>12}".format(s['snapshot_date'], tv, nd, cb, ca, qf)
    print(row)
