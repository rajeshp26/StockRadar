#!/usr/bin/env python3
"""Reset all holdings and tracking fields for complete fresh backfill."""
import sys

sys.path.insert(0, ".")

from database import supabase

print("=" * 60)
print("RESETTING DATABASE FOR FRESH BACKFILL")
print("=" * 60)

# 1. Delete all holdings
print("\nStep 1: Deleting all holdings...")
result = supabase.table('institutional_holdings').delete().neq('holding_id', 0).execute()
print("  Done.")

# 2. Reset tracking fields in institutional_investors
print("\nStep 2: Resetting tracking fields...")
supabase.table('institutional_investors').update({
    'last_filed_period': None,
    'last_filed_date': None
}).neq('investor_id', 0).execute()
print("  Done.")

# 3. Verify
print("\nStep 3: Verification...")
result = supabase.table('institutional_holdings').select('holding_id', count='exact').execute()
print(f"  Remaining holdings: {result.count}")

result2 = supabase.table('institutional_investors').select(
    'investor_tag, last_filed_period'
).order('investor_id').execute()
for r in result2.data:
    print(f"  {r['investor_tag']}: last_filed={r['last_filed_period']}")

print("\n" + "=" * 60)
print("RESET COMPLETE - Ready for fresh backfill")
print("=" * 60)
