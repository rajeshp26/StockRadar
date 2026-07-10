"""Test the UI endpoint values vs replay engine values."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from infrastructure.repositories.price_repository import PriceRepository
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from datetime import date

# Get account IDs for user rajeshp01@gmail.com
repo = PortfolioRepository()
users = supabase.table("users").select("user_id").eq("email", "rajeshp01@gmail.com").execute()
db_user_id = users.data[0]["user_id"]
accounts = repo.get_user_accounts(db_user_id, active_only=True)
account_ids = [a["account_id"] for a in accounts]
print(f"User accounts: {account_ids}")

# Get holdings with prices via PriceRepository (same as UI)
all_holdings = repo.get_user_all_holdings(db_user_id)
company_exchange_pairs = []
for h in all_holdings:
    cid = h.get("company_id")
    if cid:
        exchange = h.get("exchange_override") or "UNKNOWN"
        company_exchange_pairs.append((cid, exchange))

price_repo = PriceRepository()
prices = price_repo.get_prices_for_holdings(company_exchange_pairs)
price_details = price_repo.get_price_details_for_holdings(company_exchange_pairs)

print(f"\nPriceRepository results:")
print(f"  get_prices_for_holdings: {len(prices)} prices")
print(f"  get_price_details_for_holdings: {len(price_details)} details")

# Compute values per account (same as list_accounts endpoint)
for acc in accounts:
    aid = acc["account_id"]
    acc_holdings = [h for h in all_holdings if h["account_id"] == aid]
    total_value = 0
    total_cost = 0
    priced_count = 0
    for h in acc_holdings:
        cid = h.get("company_id")
        exchange = h.get("exchange_override") or "UNKNOWN"
        price = prices.get((cid, exchange))
        if price is not None:
            total_value += price * (h.get("quantity", 0) or 0)
            priced_count += 1
        else:
            total_value += float(h.get("total_cost", 0))
        total_cost += float(h.get("total_cost", 0))

    print(f"\n  Account {aid} ({acc['account_type']}):")
    print(f"    Holdings: {len(acc_holdings)}, Priced: {priced_count}, Unpriced: {len(acc_holdings)-priced_count}")
    print(f"    UI total_value: ${total_value:,.2f}")
    print(f"    UI total_cost:  ${total_cost:,.2f}")

# Compare with replay engine
event_store = EventStore()
engine = ReplayEngine(event_store)
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
replay_prices = {}
for row in cmr.data or []:
    cid, px = row.get("company_id"), row.get("current_price")
    if cid and px:
        replay_prices[int(cid)] = {"price": float(px), "price_date": date(2026, 7, 7)}

print(f"\n  Replay Engine comparison (Jul 7):")
for acc in accounts:
    aid = acc["account_id"]
    snap = engine.build_snapshot_from_replay(aid, date(2026, 7, 7), replay_prices)
    print(f"  Account {aid} ({acc['account_type']}): Replay=${snap['total_value']:,.2f}  Cost=${snap['cost_basis']:,.2f}")
