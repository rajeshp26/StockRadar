"""Check current scheduler state and run history."""
import sys
sys.path.insert(0, '.')
from database import get_supabase
supabase = get_supabase()

# Get latest planner runs
resp = supabase.table('planner_run_history').select('*').order('created_at', desc=True).limit(10).execute()
print('=== Planner Run History (last 10) ===')
for row in resp.data:
    created = (row.get('created_at') or '')[:19]
    sched = row.get('scheduler_name', '')
    status = row.get('status', '')
    next_due = str(row.get('next_due_at') or '')[:19] if row.get('next_due_at') else 'None'
    err = str(row.get('error_message') or '')[:60] if row.get('error_message') else 'None'
    print(f'  [{created}] scheduler={sched} status={status} next_due_at={next_due} error={err}')

print()
# Get latest scheduler_run_history
resp2 = supabase.table('scheduler_run_history').select('*').order('created_at', desc=True).limit(10).execute()
print('=== Scheduler Run History (last 10) ===')
for row in resp2.data:
    created = (row.get('created_at') or '')[:19]
    sched = row.get('scheduler_name', '')
    status = row.get('status', '')
    jobs = row.get('jobs_enqueued', 0)
    err = str(row.get('error_details') or '')[:60] if row.get('error_details') else 'None'
    print(f'  [{created}] scheduler={sched} status={status} jobs_enqueued={jobs} error={err}')
