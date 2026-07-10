"""Debug why same state produces different snapshot values."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from database import supabase
from datetime import date
import asyncio

event_store = EventStore()
engine = ReplayEngine(event_store)

# Prices from current_market_data (same as regenerate script)
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices_cmd = {}
for row in cmr.data or []:
    cid = row.get("company_id")
    price = row.get("current_price")
    if cid and price:
        prices_cmd[int(cid)] = {"current_price": float(price)}

# Prices from financial_repo.get_latest_prices (same as snapshot job)
async def get_financial_prices():
    repo = SupabaseFinancialRepository()
    account_ids = [7]
    r = supabase.table("portfolio_holdings").select("company_id").eq("account_id", 7).execute()
    company_ids = list(set(int(h["company_id"]) for h in (r.data or []) if h.get("company_id")))
    return await repo.get_latest_prices(company_ids, date(2026, 7, 7))

prices_fin = asyncio.run(get_financial_prices())

print(f"Prices from current_market_data: {len(prices_cmd)} companies")
print(f"Prices from financial_repo: {len(prices_fin)} companies")

# Build snapshot with both price sources
snap_cmd = engine.build_snapshot_from_replay(7, date(2026, 7, 7), prices_cmd)
snap_fin = engine.build_snapshot_from_replay(7, date(2026, 7, 7), prices_fin)

print(f"\nWith current_market_data: total=${snap_cmd['total_value']:,.2f} market=${snap_cmd['holdings_market_value']:,.2f}")
print(f"With financial_repo:      total=${snap_fin['total_value']:,.2f} market=${snap_fin['holdings_market_value']:,.2f}")

# Find which prices differ
for cid in set(list(prices_cmd.keys()) + list(prices_fin.keys())):
    pc = prices_cmd.get(cid, {}).get("current_price")
    pf = prices_fin.get(cid, {}).get("current_price")
    if pc != pf:
        print(f"  Company {cid}: cmd={pc} fin={pf}")
