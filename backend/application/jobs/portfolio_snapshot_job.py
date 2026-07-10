import asyncio
import logging
import time
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from config import settings
from shared.time_utils import now_utc
from shared.snapshot_builder import build_snapshot_row
from shared.replay_engine import ReplayEngine
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository

logger = logging.getLogger("stockerpro.portfolio.snapshots")

BATCH_SIZE = 50


def timed(logger=logger):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            logger.info(f"{func.__name__} took {elapsed:.2f}s")
            return result
        return wrapper
    return decorator


def _build_snapshot_via_replay(
    account_id: int,
    snapshot_date: date,
    prices_by_company: Dict[int, Dict],
    price_history: Dict[int, List[tuple]],
    account_currency: str = "CAD",
    exchange_overrides: Optional[Dict[int, Optional[str]]] = None,
) -> Optional[dict]:
    """Build snapshot using event-replay engine. Returns None if replay fails."""
    try:
        event_store = EventStore()
        engine = ReplayEngine(event_store)
        return engine.build_snapshot_from_replay(
            account_id=account_id,
            target_date=snapshot_date,
            prices_by_company=prices_by_company,
            price_history=price_history,
            account_currency=account_currency,
            exchange_overrides=exchange_overrides,
        )
    except Exception as e:
        logger.error(f"Event-replay snapshot failed for account {account_id}: {e}")
        return None


@timed()
async def compute_daily_snapshots():
    today = now_utc().date()
    portfolio_repo = PortfolioRepository()
    financial_repo = SupabaseFinancialRepository()
    snapshots_repo = PortfolioSnapshotsRepository()

    use_replay = getattr(settings, "ENABLE_EVENT_REPLAY_SNAPSHOTS", False)
    comparison_mode = getattr(settings, "EVENT_REPLAY_COMPARISON_MODE", True)

    all_accounts = portfolio_repo.get_user_accounts_all()
    if not all_accounts:
        logger.info("No accounts found, skipping")
        return

    account_ids = [a["account_id"] for a in all_accounts]
    account_currency_map = {a["account_id"]: a.get("currency", "CAD") for a in all_accounts}
    logger.info(f"Computing snapshots for {len(account_ids)} accounts on {today} "
                f"(replay={'enabled' if use_replay else 'disabled'}, "
                f"compare={comparison_mode})")

    for i in range(0, len(account_ids), BATCH_SIZE):
        batch = account_ids[i:i + BATCH_SIZE]

        holdings_result = portfolio_repo.get_holdings_for_accounts(batch)
        holdings_by_account = defaultdict(list)
        for h in holdings_result:
            holdings_by_account[h["account_id"]].append(h)

        all_company_ids = set()
        for h_list in holdings_by_account.values():
            for h in h_list:
                if h.get("company_id"):
                    all_company_ids.add(h["company_id"])

        company_names: Dict[int, str] = {}
        if all_company_ids:
            names_result = portfolio_repo.get_company_names(list(all_company_ids))
            for row in names_result:
                company_names[row["company_id"]] = row.get("company_name")

        prices_by_company = await financial_repo.get_latest_prices(list(all_company_ids), today)

        for aid in batch:
            if use_replay:
                # Event-replay path
                price_history: Dict[int, List[tuple]] = {}
                exchange_overrides = {
                    h["company_id"]: h["exchange_override"]
                    for h in holdings_by_account.get(aid, [])
                    if h.get("exchange_override")
                }
                replay_snapshot = _build_snapshot_via_replay(
                    account_id=aid,
                    snapshot_date=today,
                    prices_by_company=prices_by_company,
                    price_history=price_history,
                    account_currency=account_currency_map.get(aid, "CAD"),
                    exchange_overrides=exchange_overrides,
                )

                if replay_snapshot is None:
                    logger.warning(f"Replay failed for account {aid}, skipping")
                    continue

                if comparison_mode:
                    # Old path as fallback for comparison
                    holdings = holdings_by_account.get(aid, [])
                    clean_holdings = []
                    for h in holdings:
                        qty = Decimal(str(h.get("quantity") or 0))
                        if qty < 0:
                            logger.error(f"Account {aid}: negative quantity: {h}")
                            continue
                        if qty == 0:
                            continue
                        h["company_name"] = company_names.get(h.get("company_id"), h.get("symbol", "?"))
                        clean_holdings.append(h)

                    cash_balance = portfolio_repo.get_cash_balance(aid, today)
                    net_deposits = portfolio_repo.get_net_deposits(aid, today)

                    old_snapshot = build_snapshot_row(
                        account_id=aid,
                        snapshot_date=today,
                        holdings_state=clean_holdings if clean_holdings else [],
                        cash_balance=cash_balance,
                        net_deposits=net_deposits,
                        prices_by_company=prices_by_company,
                        job_id=f"daily_{today.isoformat()}",
                        account_currency=account_currency_map.get(aid, "CAD"),
                    )

                    # Compare
                    replay_tv = Decimal(str(replay_snapshot.get("total_value", 0)))
                    old_tv = Decimal(str(old_snapshot.get("total_value", 0)))
                    delta = abs(replay_tv - old_tv)
                    if delta > Decimal("0.50"):
                        logger.warning(
                            f"Account {aid}: replay vs old delta=${float(delta):.2f}. "
                            f"replay_total={replay_snapshot['total_value']} "
                            f"old_total={old_snapshot['total_value']}"
                        )

                snapshots_repo.upsert_snapshot(replay_snapshot)

            else:
                # Legacy mutable-state path
                holdings = holdings_by_account.get(aid, [])

                clean_holdings = []
                for h in holdings:
                    qty = Decimal(str(h.get("quantity") or 0))
                    if qty < 0:
                        logger.error(f"Account {aid}: negative quantity: {h}")
                        raise ValueError(f"Data corruption: negative quantity in holdings")
                    if qty == 0:
                        logger.warning(f"Account {aid}: zero-qty holding {h.get('company_id')} — skipping")
                        continue
                    h["company_name"] = company_names.get(h.get("company_id"), h.get("symbol", "?"))
                    clean_holdings.append(h)

                cash_balance = portfolio_repo.get_cash_balance(aid, today)
                net_deposits = portfolio_repo.get_net_deposits(aid, today)

                snapshot_row = build_snapshot_row(
                    account_id=aid,
                    snapshot_date=today,
                    holdings_state=clean_holdings if clean_holdings else [],
                    cash_balance=cash_balance,
                    net_deposits=net_deposits,
                    prices_by_company=prices_by_company,
                    job_id=f"daily_{today.isoformat()}",
                    account_currency=account_currency_map.get(aid, "CAD"),
                )

                snapshots_repo.upsert_snapshot(snapshot_row)

        logger.info(f"Processed accounts batch {i}-{i + len(batch)}")

    logger.info("Daily snapshot job completed")


async def handle_portfolio_snapshot(job: Dict[str, Any]) -> Dict[str, Any]:
    """Handler registered with JobEngine."""
    await compute_daily_snapshots()
    return {"status": "completed", "accounts_processed": ...}
