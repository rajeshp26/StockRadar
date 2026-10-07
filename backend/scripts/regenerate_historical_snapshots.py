"""Regenerate historical snapshots using the event-replay engine to fix the stale-price spike.

WARNING: This script overwrites historical snapshots. Use only in development/staging.
"""
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_env = os.environ.get("ENVIRONMENT", "development").lower()
if _env == "production":
    print("ERROR: regenerate_historical_snapshots.py must NOT be run in production.")
    print("Use the daily snapshot job (compute_daily_snapshots) instead.")
    sys.exit(1)

from datetime import date

from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from shared.cdr_utils import derive_account_cdr_companies, derive_account_cdr_lots_as_of
from shared.replay_engine import ReplayEngine

logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s", stream=sys.stderr)
logger = logging.getLogger("stockerpro.scripts.regenerate")

event_store = EventStore()
engine = ReplayEngine(event_store)
snapshots_repo = PortfolioSnapshotsRepository()

# Build current prices
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
prices_by_company = {}
for row in cmr.data or []:
    cid = row.get("company_id")
    price = row.get("current_price")
    if cid and price:
        prices_by_company[int(cid)] = {"price": float(price), "price_date": date(2026, 7, 7)}

logger.info(f"Loaded {len(prices_by_company)} prices")

# Dates to regenerate: June 23 through July 6
target_dates = [
    date(2026, 6, 23), date(2026, 6, 24), date(2026, 6, 26),
    date(2026, 6, 27), date(2026, 6, 30),
    date(2026, 7, 6),
]

accounts = [7, 8, 9, 10, 11, 12]
total = 0

for aid in accounts:
    derived_cdr = derive_account_cdr_companies(supabase, aid)
    for dt in target_dates:
        replay = engine.build_snapshot_from_replay(
            account_id=aid,
            target_date=dt,
            prices_by_company=prices_by_company,
            derived_cdr_companies=derived_cdr,
            cdr_lots=derive_account_cdr_lots_as_of(supabase, aid, dt.isoformat()),
        )
        if replay and replay.get("total_value", 0) != 0:
            snapshots_repo.upsert_snapshot(replay)
            logger.info(f"Account {aid} {dt}: ${replay['total_value']:,.2f}")
            total += 1
        else:
            logger.warning(f"Account {aid} {dt}: replay returned $0, skipping")

logger.info(f"Done. Regenerated {total} snapshots")
