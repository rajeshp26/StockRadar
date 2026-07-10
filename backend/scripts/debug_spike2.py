"""Check price_history vs current_market_data coverage and July 7 snapshot details."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase

# Check price_history stats
r = supabase.table("price_history").select("company_id", count="exact").execute()
print(f"price_history total rows: {r.count}")

r2 = supabase.table("price_history").select("company_id").execute()
companies = set(int(x["company_id"]) for x in (r2.data or []))
print(f"price_history distinct companies: {len(companies)}")
print(f"Companies: {sorted(companies)}")

# Check current_market_data
r3 = supabase.table("current_market_data").select("company_id", count="exact").execute()
print(f"current_market_data total rows: {r3.count}")

# Check what July 7 snapshot has
r4 = supabase.table("portfolio_snapshots").select("account_id, snapshot_date, total_value, holdings_market_value, cost_basis").eq("snapshot_date", "2026-07-07").order("account_id").execute()
print("\nJuly 7 snapshots:")
for row in r4.data or []:
    print(f"  Acct {row['account_id']}: total=${row['total_value']:>8,.2f}  market=${row['holdings_market_value']:>8,.2f}  cost=${row['cost_basis']:>8,.2f}")

# Check June 23 snapshot
r5 = supabase.table("portfolio_snapshots").select("account_id, snapshot_date, total_value, holdings_market_value, cost_basis").eq("snapshot_date", "2026-06-23").order("account_id").execute()
print("\nJune 23 snapshots:")
for row in r5.data or []:
    print(f"  Acct {row['account_id']}: total=${row['total_value']:>8,.2f}  market=${row['holdings_market_value']:>8,.2f}  cost=${row['cost_basis']:>8,.2f}")

# Check what company IDs account 7 holds (from portfolio_holdings)
r6 = supabase.table("portfolio_holdings").select("company_id, total_quantity, total_cost_basis, market_value").eq("account_id", 7).execute()
print(f"\nAccount 7 holdings ({len(r6.data or [])} positions from portfolio_holdings):")
for h in (r6.data or []):
    print(f"  Company {h['company_id']}: qty={h['total_quantity']}, cost={h['total_cost_basis']:.2f}, market={h.get('market_value', 0):.2f}")

# Check price_history for account 7's companies
company_ids = list(set(int(h["company_id"]) for h in (r6.data or [])))
r7 = supabase.table("price_history").select("company_id, price_date, close_price").in_("company_id", company_ids).execute()
priced = set(int(x["company_id"]) for x in (r7.data or []))
unpriced = [c for c in company_ids if c not in priced]
print(f"\nAccount 7 companies in price_history: {len(priced)}/34")
print(f"Unpriced in price_history: {sorted(unpriced)}")
