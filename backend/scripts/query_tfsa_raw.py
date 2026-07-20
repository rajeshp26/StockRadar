"""Query TFSA (5ZHK5CAD) - raw snapshots + net deposits, no simulation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))
from supabase import create_client
from decimal import Decimal
import json

client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

# Find TFSA account 5ZHK5CAD
result = client.table("portfolio_accounts").select("account_id,account_name,account_external_id").eq("account_external_id", "HQ035ZHK5CAD").execute()
if not result.data:
    result = client.table("portfolio_accounts").select("account_id,account_name,account_external_id").eq("account_type", "TFSA").execute()

acct = result.data[0]
aid = acct["account_id"]
print(f"ACCOUNT: {acct['account_name']} (id={aid}, external={acct['account_external_id']})")

# All snapshots ordered by date
snaps = client.table("portfolio_snapshots").select("snapshot_date,total_value,cost_basis,cash_balance,net_deposits,data_quality_flag").eq("account_id", aid).order("snapshot_date", desc=False).execute()

print(f"\nTOTAL SNAPSHOTS: {len(snaps.data)}")
print(f"\n{'date':<14}{'value':>14}{'cost_basis':>14}{'cash':>14}{'net_deposits':>14}{'quality':>12}")
print("-" * 82)
for s in snaps.data:
    tv = s.get('total_value') or 0
    cb = s.get('cost_basis') or 0
    ca = s.get('cash_balance') or 0
    nd = s.get('net_deposits') or 0
    qf = s.get('data_quality_flag') or 'OK'
    print(f"{s['snapshot_date']:<14}{tv:>14.2f}{cb:>14.2f}{ca:>14.2f}{nd:>14.2f}{qf:>12}")

# Money movement transactions (net deposits source)
print("\n\nMONEY MOVEMENTS (MoneyMovement + BonusPayment):")
money = client.table("portfolio_transactions").select("transaction_date,activity_type,activity_sub_type,net_cash_amount").eq("account_id", aid).in_("activity_type", ["MoneyMovement","BonusPayment"]).order("transaction_date", desc=False).execute()

cumulative = Decimal("0.00")
print(f"{'date':<14}{'type':<18}{'sub':<12}{'cash_amount':>14}{'cumulative':>14}")
print("-" * 72)
for t in money.data:
    amt = Decimal(str(t.get('net_cash_amount') or 0))
    cumulative += amt
    print(f"{t['transaction_date']:<14}{t.get('activity_type',''):<18}{t.get('activity_sub_type',''):<12}{float(amt):>14.2f}{float(cumulative):>14.2f}")

print(f"\nFINAL CUMULATIVE NET DEPOSITS: ${cumulative:,.2f}")

# Current holdings
print("\n\nCURRENT HOLDINGS:")
holdings = client.table("portfolio_holdings").select("symbol,quantity,average_cost,total_cost,current_value").eq("account_id", aid).execute()
for h in holdings.data:
    print(f"  {h.get('symbol','?'):<10} qty={h.get('quantity','?'):<10} avg_cost={h.get('average_cost','?'):<10} total_cost={h.get('total_cost','?'):<12} value={h.get('current_value','?')}")
