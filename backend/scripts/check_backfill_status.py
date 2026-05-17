#!/usr/bin/env python3
"""Check backfill status - how many holdings saved per investor."""
import sys
sys.path.insert(0, ".")

from database import supabase

# Check total holdings
result = supabase.table('institutional_holdings').select('holding_id', count='exact').execute()
print(f"Total holdings saved: {result.count}")

# Check holdings per investor
result2 = supabase.table('institutional_holdings').select(
    'investor_id'
).execute()

from collections import Counter
investor_counts = Counter(r['investor_id'] for r in result2.data)
print(f"\nInvestors with holdings: {len(investor_counts)}")

# Get investor names
inv_result = supabase.table('institutional_investors').select(
    'investor_id, investor_name, investor_tag, last_filed_period'
).execute()
inv_map = {inv['investor_id']: inv for inv in inv_result.data}

print("\nHoldings per investor:")
for inv_id, count in sorted(investor_counts.items()):
    inv = inv_map.get(inv_id, {})
    tag = inv.get('investor_tag', 'Unknown')
    name = inv.get('investor_name', 'Unknown')
    last = inv.get('last_filed_period', 'None')
    print(f"  {tag:15s}: {count:4d} holdings (last_filed: {last})")

# Check quarters per investor
print("\nQuarters per investor:")
for inv_id in sorted(investor_counts.keys()):
    q_result = supabase.table('institutional_holdings').select(
        'quarter_end_date'
    ).eq('investor_id', inv_id).execute()
    quarters = set(r['quarter_end_date'] for r in q_result.data)
    inv = inv_map.get(inv_id, {})
    tag = inv.get('investor_tag', 'Unknown')
    print(f"  {tag:15s}: {len(quarters)} quarters - {sorted(quarters)}")
