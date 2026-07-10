"""Compare price_history close_price vs current_market_data current_price for companies 31-39."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase

# Check price_history for companies 31-39
r = supabase.table("price_history").select("company_id, price_date, close_price").in_("company_id", [31,32,33,34,35,36,37,38,39]).execute()
print("price_history latest prices:")
latest = {}
for row in r.data or []:
    cid = row["company_id"]
    pd = row["price_date"]
    if isinstance(pd, str):
        from datetime import date as dt_date
        pd = dt_date.fromisoformat(pd)
    existing = latest.get(cid)
    if existing is None or pd > existing["date"]:
        latest[cid] = {"price": float(row["close_price"]), "date": pd}

for cid in sorted(latest.keys()):
    print(f"  Company {cid}: ${latest[cid]['price']:.2f} on {latest[cid]['date']}")

# Check current_market_data for same companies
r2 = supabase.table("current_market_data").select("company_id, current_price").in_("company_id", [31,32,33,34,35,36,37,38,39]).execute()
print("\ncurrent_market_data prices:")
cmd_prices = {}
for row in r2.data or []:
    cmd_prices[int(row["company_id"])] = float(row["current_price"])

for cid in sorted(cmd_prices.keys()):
    ph = latest.get(cid, {})
    ph_price = ph.get("price", "N/A")
    print(f"  Company {cid}: cmd=${cmd_prices[cid]:.2f} vs ph=${ph_price}")

# Now check what account 7 holds and how many shares
r3 = supabase.table("portfolio_holdings").select("company_id, quantity, total_cost_basis").eq("account_id", 7).in_("company_id", [31,32,33,34,35,36,37,38,39]).execute()
print(f"\nAccount 7 positions in companies 31-39:")
total_cmd_value = 0
total_ph_value = 0
for h in r3.data or []:
    cid = int(h["company_id"])
    qty = float(h.get("quantity", 0))
    cmd_px = cmd_prices.get(cid, 0)
    ph_px = latest.get(cid, {}).get("price", 0)
    cmd_val = qty * cmd_px
    ph_val = qty * ph_px
    total_cmd_value += cmd_val
    total_ph_value += ph_val
    print(f"  Company {cid}: qty={qty:.2f} cmd_px=${cmd_px:.2f} ph_px=${ph_px:.2f} cmd_val=${cmd_val:.2f} ph_val=${ph_val:.2f}")

print(f"\nTotal market value from companies 31-39:")
print(f"  current_market_data: ${total_cmd_value:.2f}")
print(f"  price_history (latest): ${total_ph_value:.2f}")

# Check account 7 total holdings count
r4 = supabase.table("portfolio_holdings").select("company_id, quantity, total_cost_basis").eq("account_id", 7).execute()
print(f"\nAccount 7 has {len(r4.data or [])} total holdings")
