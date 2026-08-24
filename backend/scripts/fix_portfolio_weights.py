#!/usr/bin/env python3
"""Fix portfolio weights and position values in institutional_holdings.
Recalculates weights based on actual position_values and total portfolio value per investor/quarter.
Also fixes any position_values that are still in thousands (too small).
"""
import sys

sys.path.insert(0, ".")

from collections import defaultdict

from database import supabase

print("=" * 80)
print("FIXING PORTFOLIO WEIGHTS AND POSITION VALUES")
print("=" * 80)

# Step 1: Find holdings where position_value is too small (< $1M) - likely still in thousands
print("\n--- Step 1: Finding holdings with position_value < $1M ---")
result = supabase.table('institutional_holdings').select(
    'holding_id, investor_id, company_id, quarter_end_date, position_value'
).lt('position_value', 1000000).execute()

if result.data:
    print(f"Found {len(result.data)} holdings with value < $1M")
    print("These are likely still in THOUSANDS - fixing by multiplying by 1000...")

    # Fix: multiply by 1000 to convert thousands to dollars
    fixed_count = 0
    for r in result.data:
        new_value = float(r['position_value']) * 1000
        supabase.table('institutional_holdings').update({
            'position_value': new_value
        }).eq('holding_id', r['holding_id']).execute()
        fixed_count += 1

    print(f"✅ Fixed {fixed_count} holdings (multiplied by 1000)")
else:
    print("✅ No holdings with value < $1M found")

# Step 2: Recalculate portfolio weights for ALL holdings
print("\n--- Step 2: Recalculating all portfolio weights ---")

# Get all unique investor_id + quarter_end_date combinations
result = supabase.table('institutional_holdings').select(
    'investor_id, quarter_end_date, holding_id'
).execute()

portfolios = defaultdict(list)
for r in result.data:
    key = (r['investor_id'], r['quarter_end_date'])
    portfolios[key].append(r['holding_id'])

print(f"Found {len(portfolios)} unique investor/quarter combinations")

# For each portfolio, calculate total value and update weights
fixed_weights = 0
for idx, ((investor_id, quarter), _) in enumerate(portfolios.items(), 1):
    # Get all holdings for this investor + quarter
    holdings_result = supabase.table('institutional_holdings').select(
        'holding_id, position_value'
    ).eq('investor_id', investor_id).eq('quarter_end_date', quarter).execute()

    if not holdings_result.data:
        continue

    # Calculate total portfolio value
    total_value = sum(float(h['position_value']) for h in holdings_result.data)

    if total_value == 0:
        continue

    # Update each holding's portfolio_weight
    for h in holdings_result.data:
        holding_id = h['holding_id']
        position_value = float(h['position_value'])
        new_weight = position_value / total_value

        supabase.table('institutional_holdings').update({
            'portfolio_weight': float(new_weight)
        }).eq('holding_id', holding_id).execute()
        fixed_weights += 1

    if idx % 100 == 0:
        print(f"  Processed {idx}/{len(portfolios)} portfolios...")

print(f"✅ Fixed {fixed_weights} portfolio weights")

# Step 3: Verify the fix
print("\n--- Step 3: Verification ---")

# Check for weights > 50% (should be none or very few)
result = supabase.table('institutional_holdings').select(
    'holding_id, portfolio_weight, position_value'
).gt('portfolio_weight', 0.50).execute()

if result.data:
    print(f"⚠️ Still {len(result.data)} holdings with weight > 50%")
    for r in result.data[:5]:
        print(f"  Holding {r['holding_id']}: {r['portfolio_weight']:.6f} ({r['portfolio_weight']*100:.2f}%)")
else:
    print("✅ No holdings with weight > 50%")

# Check for values < $1M (should be none)
result = supabase.table('institutional_holdings').select(
    'holding_id, position_value'
).lt('position_value', 1000000).execute()

if result.data:
    print(f"⚠️ Still {len(result.data)} holdings with value < $1M")
else:
    print("✅ All holdings have position_value >= $1M")

# Sample check
print("\n--- Sample: Warren Buffett's AAPL holdings (if exist) ---")
result = supabase.table('institutional_holdings').select(
    'quarter_end_date, position_value, portfolio_weight'
).eq('investor_id', 12).order('quarter_end_date', desc=True).limit(3).execute()

if result.data:
    print("Buffett sample holdings:")
    for r in result.data:
        print(f"  {r['quarter_end_date']}: ${r['position_value']:,.0f} ({r['portfolio_weight']*100:.2f}%)")
else:
    print("No data found for investor_id=12 (Buffett)")

print("\n" + "=" * 80)
print("FIX COMPLETE")
print("=" * 80)
