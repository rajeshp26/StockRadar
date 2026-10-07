"""Update July 7 snapshots with current_market_data prices (matching June 23-July 6)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

from database import supabase
from infrastructure.repositories.event_store import EventStore
from shared.cdr_utils import derive_account_cdr_companies, derive_account_cdr_lots_as_of
from shared.replay_engine import ReplayEngine

TARGET_DATE = date(2026, 7, 7)

# Same price source as regenerate_historical_snapshots.py
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices_by_company = {}
for row in cmr.data or []:
    cid = row.get("company_id")
    price = row.get("current_price")
    if cid and price:
        prices_by_company[int(cid)] = {"price": float(price), "price_date": TARGET_DATE}

print(f"Loaded {len(prices_by_company)} prices from current_market_data")

event_store = EventStore()
engine = ReplayEngine(event_store)

for aid in [7, 8, 9, 10, 11, 12]:
    snap = engine.build_snapshot_from_replay(
        account_id=aid,
        target_date=TARGET_DATE,
        prices_by_company=prices_by_company,
        account_currency="CAD",
        derived_cdr_companies=derive_account_cdr_companies(supabase, aid),
        cdr_lots=derive_account_cdr_lots_as_of(supabase, aid, TARGET_DATE.isoformat()),
    )

    print(f"Account {aid}: total=${snap['total_value']:>8,.2f}  market=${snap['holdings_market_value']:>8,.2f}  cash=${snap['cash_balance']:.2f}")

    supabase.table("portfolio_snapshots").update({
        "total_value": snap["total_value"],
        "holdings_market_value": snap["holdings_market_value"],
        "cash_balance": snap["cash_balance"],
        "cost_basis": snap["cost_basis"],
        "holdings_json": snap["holdings_json"],
        "data_quality_flag": snap["data_quality_flag"],
    }).eq("account_id", aid).eq("snapshot_date", TARGET_DATE.isoformat()).execute()

    print(f"  -> Updated July 7 snapshot for account {aid}")
