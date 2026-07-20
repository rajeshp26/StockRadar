"""
100% accurate expected portfolio value calculation.

Uses the EXACT backend code:
- ReplayEngine.replay_to_date() for holdings/cash/net_deposits reconstruction
- ReplayEngine.build_snapshot_from_replay() for snapshot computation
- PortfolioRepository.get_all_prices_historical() for split-adjusted price_history
- FinancialRepository.get_latest_prices() for latest prices
- Same exchange_overrides, same CDR logic, same price resolution

No reimplementation. No approximation. Direct code reuse.
"""
import sys
import os
import asyncio
from datetime import date, datetime
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from database import get_supabase
from config import settings


def main():
    from infrastructure.repositories.portfolio_repository import PortfolioRepository
    from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
    from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
    from infrastructure.repositories.event_store import EventStore
    from shared.replay_engine import ReplayEngine

    supabase = get_supabase()
    portfolio_repo = PortfolioRepository()
    financial_repo = SupabaseFinancialRepository()
    snapshots_repo = PortfolioSnapshotsRepository()
    event_store = EventStore()

    account_id = 9  # TFSA

    # 1. Get exchange_overrides from portfolio_holdings
    holdings_resp = supabase.table('portfolio_holdings') \
        .select('company_id, exchange_override') \
        .eq('account_id', account_id) \
        .execute()
    exchange_overrides = {}
    for h in holdings_resp.data or []:
        cid = h['company_id']
        exch = h.get('exchange_override')
        if exch:
            exchange_overrides[cid] = exch
    print(f"Exchange overrides: {exchange_overrides}")

    # 2. Get all company_ids from holdings
    all_company_ids = list(set(h['company_id'] for h in (holdings_resp.data or [])))
    print(f"Total holdings: {len(all_company_ids)} companies")

    # 3. Get stored snapshots
    stored = snapshots_repo.get_account_snapshots(account_id)
    snapshot_dates = sorted(set(s['snapshot_date'] for s in stored))
    print(f"Stored snapshots: {len(snapshot_dates)} dates")

    # 4. Create replay engine with the event store
    engine = ReplayEngine(event_store)

    # 5. For each snapshot date, compute expected snapshot using actual backend code
    results = []
    for i, snap_str in enumerate(snapshot_dates):
        snap_date = date.fromisoformat(snap_str) if isinstance(snap_str, str) else snap_str

        print(f"  [{i+1}/{len(snapshot_dates)}] Computing {snap_str}...", end=" ", flush=True)

        # Get prices as-of this date (same as _fill_snapshot_gaps does)
        loop = asyncio.new_event_loop()
        prices_by_company = loop.run_until_complete(
            financial_repo.get_latest_prices(all_company_ids, snap_date, include_current_fallback=False)
        )
        price_history = portfolio_repo.get_all_prices_historical(all_company_ids, snap_date)
        loop.close()

        # Build snapshot using EXACT backend code
        replay = engine.build_snapshot_from_replay(
            account_id=account_id,
            target_date=snap_date,
            prices_by_company=prices_by_company,
            price_history=price_history,
            account_currency="CAD",
            exchange_overrides=exchange_overrides,
        )

        # Get stored snapshot
        stored_snap = None
        for s in stored:
            if s['snapshot_date'] == snap_str:
                stored_snap = s
                break

        match = "YES" if abs(replay.get('total_value', 0) - (stored_snap.get('total_value', 0) if stored_snap else 0)) < 0.02 else "NO"
        print(f"Exp=${replay.get('total_value', 0):,.2f} Obs=${stored_snap.get('total_value', 0) if stored_snap else 0:,.2f} {match}")

        results.append({
            'date': snap_str,
            'replay': replay,
            'stored': stored_snap,
        })

    # 6. Print comparison table
    print("\n" + "=" * 130)
    print(f"{'Date':<12} | {'Exp PV':>12} {'Obs PV':>12} {'Delta':>10} | {'Exp CB':>12} {'Obs CB':>12} | {'Exp ND':>12} {'Obs ND':>12} | {'Exp Cost':>12} {'Obs Cost':>12} | Match")
    print("-" * 130)

    for r in results:
        replay = r['replay']
        stored = r['stored']
        exp_pv = replay.get('total_value', 0)
        obs_pv = stored.get('total_value', 0) if stored else 0
        delta = exp_pv - obs_pv
        exp_cb = replay.get('cash_balance', 0)
        obs_cb = stored.get('cash_balance', 0) if stored else 0
        exp_nd = replay.get('net_deposits', 0)
        obs_nd = stored.get('net_deposits', 0) if stored else 0
        exp_cost = replay.get('cost_basis', 0)
        obs_cost = stored.get('cost_basis', 0) if stored else 0

        match = "YES" if abs(delta) < 0.02 else "NO"

        print(f"{r['date']:<12} | ${exp_pv:>10,.2f} ${obs_pv:>10,.2f} ${delta:>+9,.2f} | ${exp_cb:>10,.2f} ${obs_cb:>10,.2f} | ${exp_nd:>10,.2f} ${obs_nd:>10,.2f} | ${exp_cost:>10,.2f} ${obs_cost:>10,.2f} | {match}")

    # 7. Print discrepancies
    mismatches = [r for r in results if abs(r['replay'].get('total_value', 0) - (r['stored'].get('total_value', 0) if r['stored'] else 0)) >= 0.02]
    print(f"\n\nTotal matches: {len(results) - len(mismatches)}/{len(results)}")
    if mismatches:
        print(f"\nMismatches ({len(mismatches)}):")
        for r in mismatches:
            replay = r['replay']
            stored = r['stored']
            delta = replay.get('total_value', 0) - (stored.get('total_value', 0) if stored else 0)
            print(f"  {r['date']}: replay=${replay.get('total_value', 0):,.2f} stored=${stored.get('total_value', 0) if stored else 0:,.2f} delta=${delta:+,.2f}")


if __name__ == '__main__':
    main()
