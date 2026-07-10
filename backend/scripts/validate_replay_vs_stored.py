"""Validate replay engine vs stored snapshots across all accounts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from datetime import date
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

repo = PortfolioRepository()
accounts = [a["account_id"] for a in repo.get_user_accounts_all()]
event_store = EventStore()
engine = ReplayEngine(event_store)

# Build prices_by_company from current_market_data
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices_by_company = {}
for row in cmr.data or []:
    cid = row.get("company_id")
    price = row.get("current_price")
    if cid and price:
        prices_by_company[int(cid)] = {"price": float(price), "price_date": date(2026, 7, 7)}

print(f"Loaded {len(prices_by_company)} company prices")

total_match = 0
total_diff = 0
total_snapshots = 0
total_compared = 0

for aid in sorted(accounts):
    snapshots = (
        supabase.table("portfolio_snapshots")
        .select("*")
        .eq("account_id", aid)
        .order("snapshot_date")
        .execute()
    )
    if not snapshots.data:
        print(f"Account {aid}: no snapshots")
        continue

    total_snapshots += len(snapshots.data)

    # Compare latest 3 snapshots per account
    for snap in snapshots.data[-3:]:
        raw_date = snap["snapshot_date"]
        snap_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date

        result = engine.compare_with_snapshot(
            account_id=aid,
            snapshot_date=snap_date,
            stored_snapshot=snap,
            prices_by_company=prices_by_company,
        )

        total_compared += 1
        replay_total = result.replay.get("total_value", 0)
        stored_total = result.stored.get("total_value", 0)
        delta = float(result.delta_total_value)

        if result.match:
            label = "MATCH"
            total_match += 1
        else:
            label = f"DIFFERS (delta=${delta:.2f})"
            total_diff += 1

        print(
            f"Account {aid} {snap_date}: "
            f"replay=${replay_total:,.2f} stored=${stored_total:,.2f} "
            f"-> {label}"
        )
        for d in result.differences[:5]:
            print(f"   {d}")

print(f"\nSummary: {total_match} match, {total_diff} differ, {total_compared} compared, {total_snapshots} total snapshots")
