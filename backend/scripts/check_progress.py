import sys
sys.path.insert(0, ".")
from database import supabase

result = supabase.table('institutional_investors').select(
    'investor_name, last_filed_period, is_super_investor'
).eq('is_super_investor', True).execute()

print("\n=== Backfill Progress ===")
done = 0
pending = 0
for r in result.data:
    if r.get('last_filed_period'):
        print(f"[DONE] {r['investor_name']}: {r['last_filed_period']}")
        done += 1
    else:
        print(f"[PENDING] {r['investor_name']}")
        pending += 1

print(f"\nTotal: {done} done, {pending} pending, {done+pending} total")
