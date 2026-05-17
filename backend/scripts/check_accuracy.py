#!/usr/bin/env python3
"""Check data accuracy before continuing backfill."""
import sys
sys.path.insert(0, ".")

from database import supabase

print("=== DATA ACCURACY CHECK ===")

# 1. Total holdings
result = supabase.table('institutional_holdings').select('holding_id', count='exact').execute()
print(f"\nTotal holdings saved: {result.count}")

# 2. Check for weights > 50% (impossible)
print("\n--- Checking for impossible weights (>50%) ---")
result = supabase.table('institutional_holdings').select(
    'holding_id, investor_id, quarter_end_date, portfolio_weight'
).gt('portfolio_weight', 0.50).execute()

if result.data:
    print(f"❌ FOUND {len(result.data)} holdings with weight >50% (IMPOSSIBLE!)")
    print("Sample:")
    for r in result.data[:5]:
        print(f"  ID={r['holding_id']} Inv={r['investor_id']} Q={r['quarter_end_date']} W={r['portfolio_weight']:.6f}")
else:
    print("✅ No holdings with weight >50%")

# 3. Check for position_value < $1M (might be in thousands)
print("\n--- Checking for small position values (<$1M) ---")
result = supabase.table('institutional_holdings').select(
    'holding_id, position_value'
).lt('position_value', 1000000).execute()

if result.data:
    print(f"❌ FOUND {len(result.data)} holdings with value <$1M (might be in thousands!)")
    print("Sample:")
    for r in result.data[:5]:
        print(f"  ID={r['holding_id']}: ${r['position_value']:,.2f}")
else:
    print("✅ All holdings have position_value >= $1M (correct dollars)")

# 4. Sample check: Warren Buffett's largest holdings
print("\n--- Sample: Warren Buffett's holdings (investor_id=12) ---")
result = supabase.table('institutional_holdings').select(
    'quarter_end_date, position_value, portfolio_weight'
).eq('investor_id', 12).order('position_value', desc=True).limit(3).execute()

if result.data:
    print("Top 3 positions by Buffett:")
    for r in result.data:
        print(f"  {r['quarter_end_date']}: ${r['position_value']:,.0f} ({r['portfolio_weight']*100:.2f}%)")
else:
    print("No Buffett data found")

# 5. Check weight = 1.0 (100%) - likely wrong
print("\n--- Checking for weight = 100% ---")
result = supabase.table('institutional_holdings').select(
    'holding_id, investor_id, quarter_end_date'
).eq('portfolio_weight', 1.0).execute()

if result.data:
    print(f"❌ FOUND {len(result.data)} holdings with weight = 100% (impossible!)")
    print("Sample:")
    for r in result.data[:5]:
        print(f"  ID={r['holding_id']} Inv={r['investor_id']} Q={r['quarter_end_date']}")
else:
    print("✅ No holdings with weight = 100%")

# 6. Overall data quality summary
print("\n=== SUMMARY ===")
total = supabase.table('institutional_holdings').select('holding_id', count='exact').execute().count

issue_count = 0
if supabase.table('institutional_holdings').select('holding_id').gt('portfolio_weight', 0.50).execute().data:
    issue_count += 1
if supabase.table('institutional_holdings').select('holding_id').lt('position_value', 1000000).execute().data:
    issue_count += 1
if supabase.table('institutional_holdings').select('holding_id').eq('portfolio_weight', 1.0).execute().data:
    issue_count += 1

if issue_count == 0:
    print("✅ DATA LOOKS ACCURATE - Ready to continue backfill")
else:
    print(f"❌ FOUND {issue_count} potential issues - Need to fix before continuing")

print("=== END CHECK ===")
