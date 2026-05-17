#!/usr/bin/env python3
"""Verify data accuracy - check position_values and portfolio_weights."""
import sys
sys.path.insert(0, ".")

from database import supabase

print("=" * 80)
print("SUPER INVESTOR DATA ACCURACY VERIFICATION")
print("=" * 80)

# 1. Check total holdings
result = supabase.table('institutional_holdings').select('holding_id', count='exact').execute()
print(f"\nTotal holdings: {result.count}")

# 2. Check value ranges (should be in millions/billions of dollars)
print("\n--- POSITION VALUE VERIFICATION ---")
print("(Position values should be in DOLLARS, not thousands)")
result = supabase.table('institutional_holdings').select(
    'position_value'
).order('position_value', desc=True).limit(5).execute()

print("Top 5 largest positions:")
for r in result.data:
    val = r['position_value']
    print(f"  ${val:,.2f} ({'BILLIONS' if val > 1e9 else 'MILLIONS'})")

# Check for suspicious values (too small = still in thousands)
result = supabase.table('institutional_holdings').select(
    'holding_id, position_value'
).lt('position_value', 1000000).execute()  # Less than $1M might indicate wrong units

if result.data:
    print(f"\n⚠️ POTENTIAL ISSUE: {len(result.data)} holdings with value < $1M")
    print("These might be stored in thousands instead of dollars")
    for r in result.data[:5]:
        print(f"  Holding {r['holding_id']}: ${r['position_value']:,.2f}")
else:
    print("\n✅ All holdings are > $1M (correct unit: dollars)")

# 3. Check portfolio weights (should be 0.001 - 0.50 = 0.1% to 50%)
print("\n--- PORTFOLIO WEIGHT VERIFICATION ---")
print("(Weights should be 0.001-0.50 = 0.1% to 50%)")
result = supabase.table('institutional_holdings').select(
    'portfolio_weight'
).order('portfolio_weight', desc=True).limit(5).execute()

print("Top 5 weights:")
for r in result.data:
    w = r['portfolio_weight']
    print(f"  {w:.6f} ({w*100:.2f}%)")

# Check for impossible weights (>50% or <0.0001%)
result = supabase.table('institutional_holdings').select(
    'holding_id, portfolio_weight'
).or_('portfolio_weight.gt.0.50,portfolio_weight.lt.0.0001').execute()

if result.data:
    print(f"\n⚠️ POTENTIAL ISSUE: {len(result.data)} holdings with impossible weights")
    for r in result.data[:5]:
        print(f"  Holding {r['holding_id']}: {r['portfolio_weight']:.6f} ({r['portfolio_weight']*100:.4f}%)")
else:
    print("\n✅ All weights are in realistic range (0.01% - 50%)")

# 4. Sample check: Warren Buffett's AAPL holding
print("\n--- SAMPLE CHECK: Warren Buffett (BUFFETT) ---")
result = supabase.table('institutional_holdings').select(
    'quarter_end_date, position_value, portfolio_weight, shares_held'
).eq('investor_id', 12).eq('company_id', 1).order('quarter_end_date', desc=True).limit(3).execute()

if result.data:
    print("AAPL holdings by Buffett:")
    for r in result.data:
        print(f"  {r['quarter_end_date']}: ${r['position_value']:,.0f} ({r['portfolio_weight']*100:.2f}%) - {r['shares_held']:,} shares")
else:
    print("No AAPL data found (company_id=1 might be wrong)")

# 5. Verify weight calculation for a sample
print("\n--- WEIGHT CALCULATION CHECK ---")
result = supabase.table('institutional_holdings').select(
    'holding_id, investor_id, quarter_end_date, position_value, portfolio_weight'
).eq('investor_id', 12).eq('quarter_end_date', '2023-09-30').execute()

if result.data:
    total = sum(r['position_value'] for r in result.data)
    print(f"Buffett Q3 2023: {len(result.data)} holdings, total portfolio = ${total:,.0f}")
    print("Checking weight calculations:")
    for r in result.data[:3]:
        expected_weight = r['position_value'] / total if total > 0 else 0
        actual_weight = r['portfolio_weight']
        diff = abs(expected_weight - actual_weight)
        status = "✅" if diff < 0.0001 else "❌"
        print(f"  Holding {r['holding_id']}: expected={expected_weight:.6f}, actual={actual_weight:.6f} {status}")

print("\n=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
