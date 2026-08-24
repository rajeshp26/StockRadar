"""Query TFSA (5ZHK5CAD) portfolio data for ALL period analysis."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from decimal import Decimal

from supabase import create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 1. Find TFSA account
print("=" * 80)
print("1. FINDING TFSA ACCOUNT (5ZHK5CAD)")
print("=" * 80)

result = client.table("portfolio_accounts").select("*").eq("account_external_id", "5ZHK5CAD").execute()
if not result.data:
    # Try by account_type
    result = client.table("portfolio_accounts").select("*").eq("account_type", "TFSA").execute()

if result.data:
    for acct in result.data:
        print(f"  account_id: {acct['account_id']}")
        print(f"  account_name: {acct['account_name']}")
        print(f"  account_type: {acct['account_type']}")
        print(f"  account_external_id: {acct.get('account_external_id', 'N/A')}")
        print(f"  currency: {acct.get('currency', 'N/A')}")
        print(f"  is_active: {acct.get('is_active', 'N/A')}")
        print()
    tfsa_account_id = result.data[0]['account_id']
else:
    print("  No TFSA account found!")
    sys.exit(1)

# 2. Get earliest transaction
print("=" * 80)
print("2. EARLIEST TRANSACTION")
print("=" * 80)

txns = client.table("portfolio_transactions").select("*").eq("account_id", tfsa_account_id).order("transaction_date", desc=False).limit(5).execute()
if txns.data:
    for t in txns.data:
        print(f"  date={t['transaction_date']} type={t.get('activity_type','?')} sub={t.get('activity_sub_type','?')} symbol={t.get('symbol','?')} qty={t.get('quantity','?')} price={t.get('unit_price','?')} cash={t.get('net_cash_amount','?')}")
    earliest_date = txns.data[0]['transaction_date']
    print(f"\n  Earliest transaction date: {earliest_date}")
else:
    print("  No transactions found!")
    earliest_date = None

# 3. Get ALL snapshots
print("\n" + "=" * 80)
print("3. ALL PORTFOLIO SNAPSHOTS")
print("=" * 80)

snapshots = client.table("portfolio_snapshots").select("*").eq("account_id", tfsa_account_id).order("snapshot_date", desc=False).execute()
if snapshots.data:
    print(f"  Total snapshots: {len(snapshots.data)}")
    print()
    print(f"  {'Date':<14} {'Total Value':>14} {'Cost Basis':>14} {'Cash Balance':>14} {'Net Deposits':>14} {'Quality':>12}")
    print(f"  {'-'*14} {'-'*14} {'-'*14} {'-'*14} {'-'*14} {'-'*12}")
    for s in snapshots.data:
        tv = s.get('total_value', 0) or 0
        cb = s.get('cost_basis', 0) or 0
        cash = s.get('cash_balance', 0) or 0
        nd = s.get('net_deposits', 0) or 0
        qf = s.get('data_quality_flag', 'OK')
        print(f"  {s['snapshot_date']:<14} ${tv:>12,.2f} ${cb:>12,.2f} ${cash:>12,.2f} ${nd:>12,.2f} {qf:>12}")
else:
    print("  No snapshots found!")

# 4. Get ALL transactions
print("\n" + "=" * 80)
print("4. ALL TRANSACTIONS")
print("=" * 80)

all_txns = client.table("portfolio_transactions").select("*").eq("account_id", tfsa_account_id).order("transaction_date", desc=False).execute()
if all_txns.data:
    print(f"  Total transactions: {len(all_txns.data)}")
    print()
    for t in all_txns.data:
        print(f"  {t['transaction_date']} | type={t.get('activity_type','?'):<15} sub={t.get('activity_sub_type','?'):<15} symbol={t.get('symbol','N/A')!s:<10} qty={t.get('quantity','N/A')!s:<10} price={t.get('unit_price','N/A')!s:<10} cash={t.get('net_cash_amount',0)}")

    # Calculate cumulative net deposits
    print("\n" + "=" * 80)
    print("5. CUMULATIVE NET DEPOSITS (MoneyMovement + BonusPayment)")
    print("=" * 80)

    money_txns = [t for t in all_txns.data if t.get('activity_type') in ('MoneyMovement', 'BonusPayment')]
    if money_txns:
        cumulative = Decimal("0.00")
        print(f"  {'Date':<14} {'Cash Amount':>14} {'Cumulative':>14}")
        print(f"  {'-'*14} {'-'*14} {'-'*14}")
        for t in money_txns:
            amt = Decimal(str(t.get('net_cash_amount') or 0))
            cumulative += amt
            print(f"  {t['transaction_date']:<14} ${amt:>12,.2f} ${cumulative:>12,.2f}")
        print(f"\n  Final cumulative net deposits: ${cumulative:,.2f}")
    else:
        print("  No MoneyMovement or BonusPayment transactions found!")
else:
    print("  No transactions found!")

# 6. Get holdings
print("\n" + "=" * 80)
print("6. CURRENT HOLDINGS")
print("=" * 80)

holdings = client.table("portfolio_holdings").select("*").eq("account_id", tfsa_account_id).execute()
if holdings.data:
    for h in holdings.data:
        print(f"  {h.get('symbol','?'):<10} qty={h.get('quantity','?'):<10} avg_cost={h.get('average_cost','?'):<10} total_cost={h.get('total_cost','?')}")
else:
    print("  No holdings found!")

print("\nDone!")
