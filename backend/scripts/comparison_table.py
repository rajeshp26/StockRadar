"""Comparison table: UI (portfolio_holdings) vs Replay (events) vs DB (snapshots) for all dates."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import supabase
from infrastructure.repositories.price_repository import PriceRepository
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from datetime import date

# Get user's accounts
users = supabase.table("users").select("user_id").eq("email", "rajeshp01@gmail.com").execute()
db_user_id = users.data[0]["user_id"]
repo = PortfolioRepository()
accounts = repo.get_user_accounts(db_user_id, active_only=True)  # [9, 8, 7]

# Get UI holdings
all_holdings = repo.get_user_all_holdings(db_user_id)

# Get prices via PriceRepository (with the current_market_data fix)
price_repo = PriceRepository()
company_exchange_pairs = []
for h in all_holdings:
    cid = h.get("company_id")
    if cid:
        exchange = h.get("exchange_override") or "UNKNOWN"
        company_exchange_pairs.append((cid, exchange))
prices = price_repo.get_prices_for_holdings(company_exchange_pairs)

# Load prices for replay engine
cmr = supabase.table("current_market_data").select("company_id, current_price").execute()
replay_prices = {}
for row in cmr.data or []:
    cid, px = row.get("company_id"), row.get("current_price")
    if cid and px:
        replay_prices[int(cid)] = {"price": float(px), "price_date": date(2026, 7, 7)}

event_store = EventStore()
engine = ReplayEngine(event_store)

target_dates = [
    date(2025, 7, 24), date(2025, 8, 14), date(2025, 9, 4), date(2025, 9, 25),
    date(2025, 10, 16), date(2025, 11, 6), date(2025, 11, 27), date(2025, 12, 18),
    date(2026, 1, 8), date(2026, 1, 29), date(2026, 2, 19), date(2026, 3, 12),
    date(2026, 4, 7), date(2026, 4, 29), date(2026, 6, 22), date(2026, 7, 7),
]

print(f"{'='*130}")
print(f"{'COMPARISON: UI (portfolio_holdings) vs Replay (events) vs DB (snapshots)':^130}")
print(f"{'='*130}")

for acc in accounts:
    aid = acc["account_id"]
    acc_name = f"Acct {aid} ({acc['account_type']})"
    print(f"\n--- {acc_name} ---")
    print(f"{'Date':<12} {'UI_Cash':>10} {'UI_Market':>10} {'UI_Total':>10}  {'Replay_Cash':>12} {'Replay_Market':>12} {'Replay_Total':>12}  {'DB_Total':>10}")
    print(f"{'-'*12} {'-'*10} {'-'*10} {'-'*10}  {'-'*12} {'-'*12} {'-'*12}  {'-'*10}")

    for dt in target_dates:
        # UI value: price * qty from portfolio_holdings (current prices, not date-specific)
        acc_holdings = [h for h in all_holdings if h["account_id"] == aid]
        ui_total = 0.0
        ui_market = 0.0
        ui_cash = 0.0
        for h in acc_holdings:
            cid = h.get("company_id")
            exchange = h.get("exchange_override") or "UNKNOWN"
            px = prices.get((cid, exchange))
            qty = float(h.get("quantity", 0) or 0)
            if px is not None:
                val = px * qty
                ui_market += val
                ui_total += val
            else:
                ui_total += float(h.get("total_cost", 0) or 0)

        # Replay engine value for this date
        state = engine.replay_to_date(aid, dt)
        snap = engine.build_snapshot_from_replay(aid, dt, replay_prices)
        replay_total = snap["total_value"]
        replay_market = snap["holdings_market_value"]
        replay_cash = snap["cash_balance"]

        # DB snapshot value
        r = supabase.table("portfolio_snapshots").select("total_value").eq("account_id", aid).eq("snapshot_date", dt.isoformat()).execute()
        db_total = r.data[0]["total_value"] if r.data else None

        print(f"{dt.isoformat():<12} {ui_cash:>10,.2f} {ui_market:>10,.2f} {ui_total:>10,.2f}  "
              f"{replay_cash:>12,.2f} {replay_market:>12,.2f} {replay_total:>12,.2f}  "
              f"{db_total:>10,.2f}" if db_total else f"{'N/A':>10}")

print(f"\n{'='*130}")
print(f"{'NOTE: UI values use current_market_data prices applied to portfolio_holdings quantities.':^130}")
print(f"{'Replay values use the same current_market_data prices but quantities from event replay.':^130}")
print(f"{'The difference is entirely in HOLDINGS QUANTITIES, not prices.':^130}")
print(f"{'='*130}")
