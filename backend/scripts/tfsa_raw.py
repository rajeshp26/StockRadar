import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env')
from supabase import create_client

client = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))

# Get snapshots
snaps = client.table('portfolio_snapshots').select('snapshot_date,total_value,cost_basis,cash_balance,net_deposits,data_quality_flag').eq('account_id', 9).order('snapshot_date', desc=False).execute()

# Print all rows
for s in snaps.data:
    tv = s.get('total_value') or 0
    nd = s.get('net_deposits') or 0
    print(s['snapshot_date'], tv, nd)
