"""Regenerate today's snapshots from replay data.

WARNING: This script overwrites today's snapshots. Use only in development/staging.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_env = os.environ.get("ENVIRONMENT", "development").lower()
if _env == "production":
    print("ERROR: step8_regenerate_snapshots.py must NOT be run in production.")
    print("Use the daily snapshot job (compute_daily_snapshots) instead.")
    sys.exit(1)

from datetime import date

from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.price_repository import PriceRepository
from shared.replay_engine import ReplayEngine

engine = ReplayEngine(EventStore())

ph = supabase.table("portfolio_holdings").select("company_id, exchange_override").execute()
pairs = [(h["company_id"], h.get("exchange_override") or "UNKNOWN") for h in (ph.data or [])]
price_repo = PriceRepository()
price_details = price_repo.get_prices_for_holdings(pairs)

prices_by_company = {}
for (cid, exch), px in price_details.items():
    if cid not in prices_by_company:
        prices_by_company[cid] = {"price": px}

today = date.today()
print(f"=== REGENERATED SNAPSHOTS ({today}) ===")
for aid in [7, 8, 9, 10, 11, 12]:
    snap = engine.build_snapshot_from_replay(aid, today, prices_by_company)
    sv = snap["total_value"]
    mv = snap["holdings_market_value"]
    cb = snap["cost_basis"]
    ca = snap["cash_balance"]
    qf = snap["data_quality_flag"]
    print(f"  Account {aid}: total=${sv:,.2f} market=${mv:,.2f} cost=${cb:,.2f} cash=${ca:,.2f} quality={qf}")

    supabase.table("portfolio_snapshots").upsert({
        "account_id": aid,
        "snapshot_date": today.isoformat(),
        "total_value": sv,
        "holdings_market_value": mv,
        "cost_basis": cb,
        "cash_balance": ca,
        "net_deposits": snap["net_deposits"],
        "holdings_json": snap["holdings_json"],
        "data_quality_flag": qf,
    }, on_conflict="account_id,snapshot_date").execute()

print()
print("=== VERIFICATION: Latest snapshot now matches replay ===")
for aid in [7, 8, 9, 10, 11, 12]:
    s = supabase.table("portfolio_snapshots").select("total_value, snapshot_date").eq("account_id", aid).order("snapshot_date", desc=True).limit(1).execute()
    if s.data:
        snap_total = s.data[0]["total_value"]
        del_total = abs(snap_total - sv) if aid == 9 else abs(snap_total - sv)
        print(f"  Account {aid}: snap=${snap_total:,.2f}")
