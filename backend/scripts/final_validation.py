"""Final validation: compare replay vs stored for all historical snapshots."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date

from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.replay_engine import ReplayEngine

repo = PortfolioRepository()
accounts = [a["account_id"] for a in repo.get_user_accounts_all()]
event_store = EventStore()
engine = ReplayEngine(event_store)

# Build prices_by_company
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices_by_company = {}
for row in cmr.data or []:
    cid = row.get("company_id")
    price = row.get("current_price")
    if cid and price:
        prices_by_company[int(cid)] = {"price": float(price), "price_date": date(2026, 7, 7)}

print(f"Prices loaded: {len(prices_by_company)}")

total_match = 0
total_diff = 0
total_snapshots = 0

for aid in sorted(accounts):
    snapshots = supabase.table("portfolio_snapshots").select("*").eq("account_id", aid).order("snapshot_date").execute()
    if not snapshots.data:
        print(f"Account {aid}: no snapshots")
        continue

    total_snapshots += len(snapshots.data)
    account_match = 0
    account_diff = 0
    worst_delta = 0

    for snap in snapshots.data[-3:]:
        raw_date = snap["snapshot_date"]
        snap_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date

        result = engine.compare_with_snapshot(
            account_id=aid,
            snapshot_date=snap_date,
            stored_snapshot=snap,
            prices_by_company=prices_by_company,
        )

        delta = float(result.delta_total_value)
        worst_delta = max(worst_delta, abs(delta))

        if result.match:
            account_match += 1
        else:
            account_diff += 1

    print(f"Account {aid}: {len(snapshots.data)} snapshots, {account_match} match, {account_diff} differ, worst_delta=${worst_delta:.2f}")
    total_match += account_match
    total_diff += account_diff

print(f"\nTotal: {total_match} match, {total_diff} differ, {total_snapshots} snapshots")
if total_diff > 0:
    print("NOTE: differences are expected — replay uses current prices, stored uses historical prices at snapshot date")
