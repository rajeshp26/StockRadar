import logging
import time
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from config import settings
from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from shared.fx_service import FXService
from shared.replay_engine import ReplayEngine
from shared.snapshot_builder import build_snapshot_row, check_snapshot_spike, convert_holding_fx
from shared.time_utils import now_utc

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
    prices_by_company: dict[int, dict],
    price_history: dict[int, list[tuple]],
    account_currency: str = "CAD",
    exchange_overrides: dict[int, str | None] | None = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
) -> dict | None:
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
            company_currencies=company_currencies,
            companies_map=companies_map,
        )
    except Exception as e:
        logger.error(f"Event-replay snapshot failed for account {account_id}: {e}")
        return None


async def _fill_snapshot_gaps(
    account_id: int,
    today: date,
    account_currency: str,
    prices_by_company: dict[int, dict],
    price_history: dict[int, list[tuple]],
    exchange_overrides: dict[int, str | None],
    snapshots_repo: PortfolioSnapshotsRepository,
    job_id_prefix: str,
    spike_threshold: float,
    financial_repo: SupabaseFinancialRepository = None,
    all_company_ids: list[int] = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
) -> int:
    """Fill missing snapshot dates between last known snapshot and today.

    Uses event-replay with forward-filled historical prices for consistency.
    For cold-start (no existing snapshots), uses incremental replay for efficiency.
    Returns the number of gap snapshots written.
    """
    if financial_repo is None:
        financial_repo = SupabaseFinancialRepository()
    if all_company_ids is None:
        all_company_ids = []

    last_date = snapshots_repo.get_last_snapshot_date(account_id)
    cold_start = False
    if last_date is None:
        event_store = EventStore()
        earliest_event_date = event_store.get_earliest_event_date(account_id)
        if earliest_event_date:
            start_date = date.fromisoformat(earliest_event_date)
            cold_start = True
            logger.info(
                f"Account {account_id}: cold-start rebuild from {start_date}"
            )
        else:
            return 0
    else:
        start_date = last_date + timedelta(days=1)
    if start_date > today:
        return 0

    missing = snapshots_repo.get_missing_dates(account_id, start_date, today)
    if not missing:
        return 0

    logger.info(
        f"Account {account_id}: filling {len(missing)} gap dates "
        f"({missing[0]} to {missing[-1]})"
    )

    if len(missing) > 10:
        return await _fill_snapshot_gaps_incremental(
            account_id=account_id,
            missing=missing,
            account_currency=account_currency,
            prices_by_company=prices_by_company,
            price_history=price_history,
            exchange_overrides=exchange_overrides,
            snapshots_repo=snapshots_repo,
            job_id_prefix=job_id_prefix,
            spike_threshold=spike_threshold,
            financial_repo=financial_repo,
            all_company_ids=all_company_ids,
            company_currencies=company_currencies,
            companies_map=companies_map,
        )

    event_store = EventStore()
    engine = ReplayEngine(event_store)
    written = 0

    for gap_date in missing:
        # Fetch prices as-of the gap date for accurate historical snapshots
        if financial_repo and all_company_ids:
            as_of_prices = await financial_repo.get_latest_prices(all_company_ids, gap_date)
            _portfolio_repo = PortfolioRepository()
            as_of_history = _portfolio_repo.get_all_prices_historical(all_company_ids, gap_date)
        else:
            as_of_prices = prices_by_company
            as_of_history = price_history

        snapshot = _build_snapshot_via_replay(
            account_id=account_id,
            snapshot_date=gap_date,
            prices_by_company=as_of_prices,
            price_history=as_of_history,
            account_currency=account_currency,
            exchange_overrides=exchange_overrides,
            company_currencies=company_currencies,
            companies_map=companies_map,
        )
        if snapshot is None or snapshot.get("total_value", 0) == 0:
            continue

        snapshot["job_id"] = f"{job_id_prefix}_gap_{gap_date.isoformat()}"

        prev = snapshots_repo.get_previous_snapshot(account_id, gap_date)
        if prev:
            spike = check_snapshot_spike(prev, snapshot, threshold=spike_threshold)
            if spike:
                logger.warning(
                    f"Account {account_id} gap {gap_date}: {spike['message']} — carrying forward previous value"
                )
                snapshot["total_value"] = prev["total_value"]
                snapshot["holdings_market_value"] = prev.get("holdings_market_value", prev["total_value"])
                snapshot["cash_balance"] = prev.get("cash_balance", 0)
                snapshot["holdings_json"] = prev.get("holdings_json")
                snapshot["data_quality_flag"] = "LOCF_CARRIED"

        snapshots_repo.upsert_snapshot(snapshot)
        written += 1

    return written


async def _fill_snapshot_gaps_incremental(
    account_id: int,
    missing: list[date],
    account_currency: str,
    prices_by_company: dict[int, dict],
    price_history: dict[int, list[tuple]],
    exchange_overrides: dict[int, str | None],
    snapshots_repo: PortfolioSnapshotsRepository,
    job_id_prefix: str,
    spike_threshold: float,
    financial_repo: SupabaseFinancialRepository = None,
    all_company_ids: list[int] = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
) -> int:
    """Cold-start: rebuild snapshots using incremental event replay.

    Fetches all events once, sorts by date, then processes gap dates in order,
    accumulating state incrementally instead of replaying from scratch each time.
    """
    from shared.replay_engine import (
        AccountState,
        ReplayEngine,
        _decimal,
        _parse_account_id,
    )

    event_store = EventStore()
    all_events = event_store.get_all_events(aggregate_type="account")

    account_events = []
    for ev in all_events:
        ev_account_id = _parse_account_id(ev.get("aggregate_id", ""))
        if ev_account_id != account_id:
            continue
        account_events.append(ev)

    engine = ReplayEngine(event_store)

    def _get_event_date(ev):
        return engine._get_event_date(ev)

    account_events.sort(key=lambda e: _get_event_date(e) or date.min)

    event_idx = 0
    state = AccountState(account_id=account_id)
    written = 0
    snapshots_to_write = []

    # Pre-fetch ALL prices once for the entire date range (O(1) HTTP calls)
    last_gap_date = missing[-1]
    logger.info(
        f"Account {account_id}: pre-fetching prices for {len(all_company_ids)} companies "
        f"(range: {missing[0]} to {last_gap_date})"
    )
    _portfolio_repo = PortfolioRepository()
    all_price_history_raw = _portfolio_repo.get_all_prices_historical(
        list(all_company_ids), last_gap_date
    )
    all_latest_raw = await financial_repo.get_latest_prices(
        list(all_company_ids), last_gap_date, include_current_fallback=False
    )
    logger.info(
        f"Account {account_id}: pre-fetch complete — "
        f"{sum(len(v) for v in all_price_history_raw.values())} price rows, "
        f"{len(all_latest_raw)} companies with latest prices"
    )

    def _prices_as_of(target_date: date) -> dict[int, dict]:
        """Filter pre-fetched latest prices to only include those <= target_date."""
        result: dict[int, dict] = {}
        for cid, info in all_latest_raw.items():
            if info["price_date"] <= target_date:
                result[cid] = info
        return result

    def _history_as_of(target_date: date) -> dict[int, list[tuple]]:
        """Filter pre-fetched history to only include rows <= target_date."""
        result: dict[int, list[tuple]] = {}
        for cid, prices in all_price_history_raw.items():
            filtered = [(pd, px) for pd, px in prices if pd <= target_date]
            if filtered:
                result[cid] = filtered
        return result

    for gap_date in missing:
        as_of_prices = _prices_as_of(gap_date)
        as_of_history = _history_as_of(gap_date)

        while event_idx < len(account_events):
            ev_date = _get_event_date(account_events[event_idx])
            if ev_date is not None and ev_date <= gap_date:
                ev = account_events[event_idx]
                event_type = ev.get("event_type", "")
                handler = getattr(engine, f"_handle_{event_type}", None)
                if handler:
                    handler(state, ev)
                event_idx += 1
            else:
                break

        holdings_list = []
        total_market_value = _decimal("0")
        total_cost = _decimal("0")
        from shared.replay_engine import TIER_QUALITY_MAP, PriceTier, _resolve_holding_price

        for cid, holding in state.holdings.items():
            qty = holding.quantity

            exch_override = exchange_overrides.get(cid) if exchange_overrides else None
            comp_ccy = (company_currencies.get(cid) if company_currencies else None) or "USD"
            # Look up per-company CDR ratio
            comp_ratio = None
            if companies_map and cid in companies_map:
                r = companies_map[cid].get("cdr_ratio")
                if r is not None:
                    from decimal import Decimal as _D
                    comp_ratio = _D(str(r))

            price, tier, resolved_price_date = _resolve_holding_price(
                company_id=cid,
                symbol=holding.symbol,
                avg_cost=holding.average_cost if holding.average_cost > 0 else None,
                latest_prices=as_of_prices,
                price_history=as_of_history or {},
                snapshot_date=gap_date,
                exchange_override=exch_override,
                cdr_ratio=comp_ratio,
                company_currency=comp_ccy,
                price_source=as_of_prices.get(cid, {}).get("source"),
            )

            if tier == PriceTier.UNAVAILABLE:
                current_value = _decimal("0")
                current_price = _decimal("0")
                pos_quality = "UNAVAILABLE"
                cost = holding.total_cost
            else:
                current_price = price
                raw_value = qty * current_price

                # FX conversion for inline snapshot building
                price_currency = "USD"
                if company_currencies and cid in company_currencies:
                    price_currency = company_currencies[cid]
                holding_dict = {
                    "company_id": cid,
                    "price_currency": price_currency,
                    "trade_date": holding.trade_date,
                    "lots": [
                        {
                            "quantity": lot["quantity"],
                            "cost_per_share": lot["cost_per_share"],
                            "date": lot.get("date"),
                        }
                        for lot in holding.lots
                    ] if holding.lots else [],
                }
                # For CDR holdings: CDR-adjusted price is already in CAD.
                # Override price_currency to prevent convert_holding_fx from re-converting.
                if exch_override == "TOR":
                    holding_dict["price_currency"] = "CAD"
                try:
                    from database import supabase as _sb
                    from shared.fx_service import FXService
                    _fx_svc = FXService(_sb) if settings.ENABLE_FX_CONVERSION else None
                    current_value, cost = convert_holding_fx(
                        holding_dict, raw_value, holding.total_cost,
                        account_currency, _fx_svc, gap_date,
                        settings.ENABLE_FX_CONVERSION,
                    )
                except Exception:
                    current_value = raw_value
                    cost = holding.total_cost

                total_market_value += current_value
                total_cost += cost
                # Context-aware quality
                if tier == PriceTier.COST_BASIS:
                    pos_quality = "COST_FALLBACK"
                elif tier == PriceTier.FORWARD_FILL:
                    price_age = (gap_date - resolved_price_date).days if resolved_price_date else None
                    pos_quality = "STALE_PRICE" if (price_age is not None and price_age > 30) else "OK"
                else:
                    pos_quality = TIER_QUALITY_MAP.get(tier, "OK")

            holdings_list.append({
                "company_id": cid,
                "symbol": holding.symbol,
                "quantity": float(qty),
                "current_price": float(current_price),
                "current_value": float(current_value),
                "cost_basis": float(cost),
                "unrealized_gain_loss": float(current_value - cost),
                "unrealized_gain_loss_pct": float(
                    (current_value - cost) / cost * 100
                ) if cost > 0 else 0.0,
                "price_age_days": None,
                "price_data_quality": pos_quality,
            })

        total_value = total_market_value + state.cash_balance

        any_stale = any(h["price_data_quality"] == "STALE_PRICE" for h in holdings_list)
        any_fallback = any(h["price_data_quality"] == "COST_FALLBACK" for h in holdings_list)
        any_unavailable = any(h["price_data_quality"] == "UNAVAILABLE" for h in holdings_list)
        if any_unavailable:
            data_quality = "INCOMPLETE"
        elif any_stale:
            data_quality = "STALE_PRICE"
        elif any_fallback:
            data_quality = "COST_FALLBACK"
        else:
            data_quality = "OK"

        snapshot_row = {
            "account_id": account_id,
            "snapshot_date": gap_date.isoformat(),
            "total_value": round(float(total_value), 2),
            "holdings_market_value": round(float(total_market_value), 2),
            "cost_basis": round(float(total_cost), 2),
            "cash_balance": round(float(state.cash_balance), 2),
            "net_deposits": round(float(state.net_deposits), 2),
            "holdings_json": holdings_list if holdings_list else None,
            "data_quality_flag": data_quality,
            "job_id": f"{job_id_prefix}_gap_{gap_date.isoformat()}",
        }

        snapshots_to_write.append(snapshot_row)
        last_computed_snapshot = {k: snapshot_row[k] for k in ("total_value", "holdings_market_value", "cash_balance", "holdings_json")}
        written += 1

        if written % 100 == 0:
            logger.info(f"Account {account_id}: {written}/{len(missing)} gap snapshots written")
            snapshots_repo.upsert_snapshots_batch(snapshots_to_write)
            snapshots_to_write = []

    if snapshots_to_write:
        snapshots_repo.upsert_snapshots_batch(snapshots_to_write)

    logger.info(f"Account {account_id}: cold-start rebuild complete, {written} snapshots written")
    return written


@timed()
async def compute_daily_snapshots():
    """Build today's snapshot for all accounts. Snapshots are immutable historical records.

    Each run creates ONE new snapshot per account (today's date). If a snapshot
    already exists for today, it is overwritten (upsert). Historical gaps are
    filled by a separate backfill process, not by this daily job.
    """
    today = now_utc().date()
    portfolio_repo = PortfolioRepository()
    financial_repo = SupabaseFinancialRepository()
    snapshots_repo = PortfolioSnapshotsRepository()

    use_replay = getattr(settings, "ENABLE_EVENT_REPLAY_SNAPSHOTS", False)
    spike_threshold = getattr(settings, "SNAPSHOT_SPIKE_THRESHOLD", 0.20)

    all_accounts = portfolio_repo.get_user_accounts_all()
    if not all_accounts:
        logger.info("No accounts found, skipping")
        return

    account_ids = [a["account_id"] for a in all_accounts]
    account_currency_map = {a["account_id"]: a.get("currency", "CAD") for a in all_accounts}
    logger.info(f"Building today's snapshots for {len(account_ids)} accounts on {today}")

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

        company_names: dict[int, str] = {}
        company_currencies: dict[int, str] = {}
        companies_map: dict[int, dict] = {}
        if all_company_ids:
            names_result = portfolio_repo.get_company_names(list(all_company_ids))
            for row in names_result:
                company_names[row["company_id"]] = row.get("company_name")
            cur_result = portfolio_repo.get_company_currencies(list(all_company_ids))
            for row in cur_result:
                company_currencies[row["company_id"]] = row.get("currency", "USD")
            # Fetch companies info including cdr_ratio for CDR pricing
            companies_info = portfolio_repo.get_companies_info(list(all_company_ids))
            for row in companies_info:
                companies_map[row["company_id"]] = row

        prices_by_company = await financial_repo.get_latest_prices(list(all_company_ids), today)

        price_history: dict[int, list[tuple]] = {}
        if all_company_ids:
            price_history = portfolio_repo.get_all_prices_historical(
                list(all_company_ids), today
            )

        for aid in batch:
            account_currency = account_currency_map.get(aid, "CAD")
            exchange_overrides = {
                h["company_id"]: h["exchange_override"]
                for h in holdings_by_account.get(aid, [])
                if h.get("exchange_override")
            }

            if use_replay:
                snapshot_row = _build_snapshot_via_replay(
                    account_id=aid,
                    snapshot_date=today,
                    prices_by_company=prices_by_company,
                    price_history=price_history,
                    account_currency=account_currency,
                    exchange_overrides=exchange_overrides,
                    company_currencies=company_currencies,
                    companies_map=companies_map,
                )
                if snapshot_row is None:
                    logger.warning(f"Replay failed for account {aid}, skipping")
                    continue
            else:
                holdings = holdings_by_account.get(aid, [])
                clean_holdings = []
                for h in holdings:
                    qty = Decimal(str(h.get("quantity") or 0))
                    if qty < 0:
                        logger.error(f"Account {aid}: negative quantity: {h}")
                        raise ValueError("Data corruption: negative quantity in holdings")
                    if qty == 0:
                        continue
                    h["company_name"] = company_names.get(h.get("company_id"), h.get("symbol", "?"))
                    h["trade_date"] = h.get("first_purchase_date")
                    clean_holdings.append(h)

                cash_balance = portfolio_repo.get_cash_balance(
                    aid, today, account_currency,
                    FXService(supabase) if settings.ENABLE_FX_CONVERSION else None,
                )
                net_deposits = portfolio_repo.get_net_deposits(aid, today)

                snapshot_row = build_snapshot_row(
                    account_id=aid,
                    snapshot_date=today,
                    holdings_state=clean_holdings if clean_holdings else [],
                    cash_balance=cash_balance,
                    net_deposits=net_deposits,
                    prices_by_company=prices_by_company,
                    job_id=f"daily_{today.isoformat()}",
                    account_currency=account_currency,
                )

            snapshot_row["job_id"] = f"daily_{today.isoformat()}"

            # Spike detection: log warning but still write (daily snapshot is authoritative)
            prev = snapshots_repo.get_previous_snapshot(aid, today)
            if prev:
                spike = check_snapshot_spike(prev, snapshot_row, threshold=spike_threshold)
                if spike:
                    logger.warning(f"Account {aid}: {spike['message']}")

            snapshots_repo.upsert_snapshot(snapshot_row)

        logger.info(f"Processed accounts batch {i}-{i + len(batch)}")

    logger.info("Daily snapshot computation complete")


async def handle_portfolio_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    """Handler registered with JobEngine."""
    await compute_daily_snapshots()
    return {"status": "completed", "accounts_processed": ...}
