"""Verify Account 9 net_deposits across snapshots and also check the API response."""
import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'backend')
from database import supabase

# Account 9 ALL snapshots
rows = supabase.table('portfolio_snapshots').select(
    'snapshot_date,total_value,cost_basis,cash_balance,net_deposits'
).eq('account_id', 9).order('snapshot_date').execute()
print("Account 9 snapshots:")
print(f"{'date':<14} {'total_value':<16} {'cost':<16} {'cash':<14} {'net_deposits':<16} {'val-cost':<16}")
print("-" * 100)
for r in rows.data or []:
    gl = float(r['total_value']) - float(r['cost_basis'])
    print(f"{r['snapshot_date']:<14} {float(r['total_value']):<16.2f} {float(r['cost_basis']):<16.2f} {float(r['cash_balance']):<14.2f} {float(r['net_deposits']):<16.2f} {gl:<+16.2f}")

print(f"\nTotal rows: {len(rows.data)}")
print(f"First: {rows.data[0]['snapshot_date']} nd={rows.data[0]['net_deposits']}")
print(f"Last:  {rows.data[-1]['snapshot_date']} nd={rows.data[-1]['net_deposits']}")

# Also check the legacy portfolio_transactions for account 9 to see deposits
txns = supabase.table('portfolio_transactions').select('transaction_date,activity_sub_type,quantity,unit_price,net_cash_amount').eq('account_id', 9).is_('quantity', 'null').eq('activity_sub_type', 'DEPOSIT').order('transaction_date').execute()
print(f"\nDeposits for account 9: {len(txns.data)}")
total_dep = 0
for t in txns.data or []:
    val = float(t.get('net_cash_amount', 0) or 0)
    total_dep += val
    print(f"  {t['transaction_date']}: {val:.2f}")
print(f"  Total deposits: {total_dep:.2f}")

# Withdrawals
txns_w = supabase.table('portfolio_transactions').select('transaction_date,activity_sub_type,quantity,unit_price,net_cash_amount').eq('account_id', 9).is_('quantity', 'null').eq('activity_sub_type', 'WITHDRAWAL').order('transaction_date').execute()
print(f"\nWithdrawals for account 9: {len(txns_w.data)}")
total_wd = 0
for t in txns_w.data or []:
    val = float(t.get('net_cash_amount', 0) or 0)
    total_wd += val
    print(f"  {t['transaction_date']}: {val:.2f}")
print(f"  Total withdrawals: {total_wd:.2f}")
print(f"  Net deposits (deposits - withdrawals): {total_dep - total_wd:.2f}")