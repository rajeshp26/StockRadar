import sys, os
sys.path.insert(0, r'C:\Project\StockerPro\StockerPro\backend')
os.environ['PYTHONIOENCODING'] = 'utf-8'
from database import supabase

# Successful scheduler runs
for sched in ['market_data', 'earnings', 'aggregation']:
    r = supabase.table('scheduler_run_history').select('*').eq('scheduler_name', sched).eq('status', 'succeeded').order('planned_at', desc=True).limit(5).execute()
    print(sched, '- last 5 successful:')
    if r.data:
        for row in r.data:
            print(' ', row)
    else:
        print('  NONE')
    print()

# Check also if earnings has a more recent successful run
r = supabase.table('scheduler_run_history').select('*').eq('scheduler_name', 'earnings').order('planned_at', desc=True).limit(5).execute()
print('Earnings - last 5 runs (any status):')
for row in r.data:
    print(' ', row)

# Also check price history - how many companies have it
r = supabase.table('price_history').select('company_id').execute()
companies = set(d['company_id'] for d in r.data if d.get('company_id'))
print('\nDistinct companies with price_history:', len(companies))

# Check CURRENT companies
r = supabase.table('companies').select('company_id,ticker_symbol,data_completeness_status,last_financial_refresh_at,last_price_refresh_at').eq('data_completeness_status', 'CURRENT').execute()
print('\nCURRENT companies:', len(r.data))
for row in r.data:
    print(' ', row)

# Most recent dividend date
r = supabase.table('dividend_history').select('ex_dividend_date').order('ex_dividend_date', desc=True).limit(1).execute()
if r.data:
    print('\nLatest ex_dividend_date:', r.data[0]['ex_dividend_date'])
