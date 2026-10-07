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
from shared import debug_trace
from shared.cdr_utils import split_holdings_by_cdr_lot
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


class _GapLotMapCache:
    """As-of lot maps for gap repair: one paginated scan per distinct date set.

    Gap dates are discovered inside _fill_snapshot_gaps(), after the call site has
    already committed to an account, so the date set cannot be hoisted to the caller.
    Scanning per account would multiply one daily run by the account count -- and the
    batched scan exists precisely to stop that happening for the daily path. Results
    are therefore memoised per distinct date set, so accounts with the same gap reuse
    one scan and the cache is per-run so it cannot serve stale rows after new imports.
    """

    def __init__(self, portfolio_repo: PortfolioRepository) -> None:
        self._repo = portfolio_repo
        self._by_dates: dict[tuple[str, ...], dict] = {}

    def for_account(
        self, account_id: int, dates: list[date]
    ) -> dict[str, dict[int, dict[str, Decimal]]]:
        """date string -> company_id -> lot kind -> signed qty, for one account."""
        key = tuple(sorted({d.isoformat() for d in dates}))
        if not key:
            return {}
        if key not in self._by_dates:
            self._by_dates[key] = self._repo.get_cdr_lots_by_account_at_dates(list(key))
        batch = self._by_dates[key]
        return {d: batch.get(d, {}).get(account_id, {}) for d in key}


def _build_snapshot_via_replay(
    account_id: int,
    snapshot_date: date,
    prices_by_company: dict[int, dict],
    price_history: dict[int, list[tuple]],
    account_currency: str = "CAD",
    exchange_overrides: dict[int, str | None] | None = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
    derived_cdr_companies: set[int] | None = None,
    cdr_lots: dict[int, dict[str, Decimal]] | None = None,
) -> dict | None:
    """Build snapshot using event-replay engine. Returns None if replay fails.

    derived_cdr_companies and cdr_lots are the transaction-derived CDR truth for the
    account AS OF snapshot_date. Both are required for a historical date to be priced
    correctly:

    - derived_cdr_companies is the company-level fallback. Replay kept a company whose
      exchange_overrides entry was NULL out of its override set entirely, which stripped
      "TOR" from a 1/10-scale CDR and priced it as a full US share -- a 10x error.
    - cdr_lots is the per-lot truth (BLK-027) for a company held as both CDR and direct.

    Without them replay stays company-keyed, which is the pre-fix behaviour.
    """
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
            derived_cdr_companies=derived_cdr_companies,
            cdr_lots=cdr_lots,
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
    all_company_ids: list[int] | None = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
    derived_cdr_companies: set[int] | None = None,
    lot_map_cache: "_GapLotMapCache | None" = None,
) -> int:
    """Fill missing snapshot dates between last known snapshot and today.

    Uses event-replay with forward-filled historical prices for consistency.
    For cold-start (no existing snapshots), uses incremental replay for efficiency.
    Returns the number of gap snapshots written.

    derived_cdr_companies and lot_map_cache carry the transaction-derived CDR truth.
    Gap dates are rebuilt through the same replay path as today, so without them they
    would be rebuilt company-keyed -- which means a repaired date could disagree with
    the day after it about the very same shares, making the repaired history worse than
    the hole it replaced. Each gap date gets its OWN as-of lot map, because lot truth is
    date-dependent by construction.
    """
    if financial_repo is None:
        financial_repo = SupabaseFinancialRepository()
    if all_company_ids is None:
        all_company_ids = []

    last_date = snapshots_repo.get_last_snapshot_date(account_id)
    if last_date is None:
        event_store = EventStore()
        earliest_event_date = event_store.get_earliest_event_date(account_id)
        if earliest_event_date:
            start_date = date.fromisoformat(earliest_event_date)
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

    # One scan for the whole gap, not one per date -- see _GapLotMapCache.
    gap_lots = (
        lot_map_cache.for_account(account_id, missing)
        if lot_map_cache is not None
        else {}
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
            derived_cdr_companies=derived_cdr_companies,
            gap_lots=gap_lots,
        )

    event_store = EventStore()
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
            derived_cdr_companies=derived_cdr_companies,
            cdr_lots=gap_lots.get(gap_date.isoformat()),
        )
        if snapshot is None or snapshot.get("total_value", 0) == 0:
            continue

        snapshot["job_id"] = f"{job_id_prefix}_gap_{gap_date.isoformat()}"

        prev = snapshots_repo.get_previous_snapshot(account_id, gap_date)
        if prev:
            spike = check_snapshot_spike(prev, snapshot, threshold=spike_threshold)
            if spike:
                # A gap date is recomputed from events + as-of prices, so unlike the
                # same-day path this value is already the source of truth: if it still
                # spikes, the move is real and must be recorded. Substituting the
                # previous day's numbers here (the old LOCF_CARRIED behaviour) would
                # discard a genuine finding. Flag it and keep the recomputed value.
                logger.warning(
                    f"Account {account_id} gap {gap_date}: {spike['message']} — "
                    f"recomputed value confirmed against events, recording as-is"
                )
                snapshot["data_quality_flag"] = "SPIKE_CONFIRMED"

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
    all_company_ids: list[int] | None = None,
    company_currencies: dict[int, str] | None = None,
    companies_map: dict[int, dict] | None = None,
    derived_cdr_companies: set[int] | None = None,
    gap_lots: dict[str, dict[int, dict[str, Decimal]]] | None = None,
) -> int:
    """Cold-start: rebuild snapshots using incremental event replay.

    Fetches all events once, sorts by date, then processes gap dates in order,
    accumulating state incrementally instead of replaying from scratch each time.

    derived_cdr_companies and gap_lots carry the transaction-derived CDR truth, and
    the legs come from replay_engine._cdr_lot_legs() -- the same helper
    build_snapshot_from_replay() uses -- rather than a second local expansion, so the
    cold-start path cannot drift from the daily path on how a mixed position is split.
    """
    from shared.replay_engine import (
        AccountState,
        ReplayEngine,
        _cdr_lot_legs,
        _decimal,
        _parse_account_id,
    )
    from shared.cdr_utils import EXCHANGE_OVERRIDE_TOR

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

        for cid, holding, leg_kind in _cdr_lot_legs(
            state.holdings,
            (gap_lots or {}).get(gap_date.isoformat()),
            derived_cdr_companies,
        ):
            qty = holding.quantity

            # Canonical precedence, shared with build_snapshot_from_replay(): a leg
            # verdict wins outright; with no lot evidence, transaction-derived company
            # truth overrides the cached holdings flag.
            if leg_kind is not None:
                exch_override = EXCHANGE_OVERRIDE_TOR if leg_kind == "cdr" else None
            else:
                exch_override = exchange_overrides.get(cid) if exchange_overrides else None
                if derived_cdr_companies and cid in derived_cdr_companies:
                    exch_override = EXCHANGE_OVERRIDE_TOR
            comp_ccy = (company_currencies.get(cid) if company_currencies else None) or "USD"
            # Look up per-company CDR ratio
            comp_ratio = None
            if companies_map and cid in companies_map:
                r = companies_map[cid].get("cdr_ratio")
                if r is not None:
                    comp_ratio = Decimal(str(r))

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

            # Provenance for every tier, not just FORWARD_FILL: a stale price must
            # never be labelled OK. Canonical form: snapshot_builder.build_snapshot_row.
            price_age = (
                (gap_date - resolved_price_date).days if resolved_price_date else None
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
                "price_age_days": price_age,
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
async def compute_daily_snapshots(target_date: date | None = None) -> int:
    """Build the snapshot for `target_date` (default: today) for all accounts.

    Historical gaps are filled before the target date is written, so the spike
    baseline is the genuinely preceding day rather than whatever the last successful
    run happened to be.
    """
    today = target_date or now_utc().date()
    portfolio_repo = PortfolioRepository()
    financial_repo = SupabaseFinancialRepository()
    snapshots_repo = PortfolioSnapshotsRepository()

    use_replay = getattr(settings, "ENABLE_EVENT_REPLAY_SNAPSHOTS", False)
    spike_threshold = getattr(settings, "SNAPSHOT_SPIKE_THRESHOLD", 0.20)

    all_accounts = portfolio_repo.get_user_accounts_all()
    if not all_accounts:
        logger.info("No accounts found, skipping")
        return 0

    account_ids = [a["account_id"] for a in all_accounts]
    account_currency_map = {a["account_id"]: a.get("currency", "CAD") for a in all_accounts}
    logger.info(f"Building today's snapshots for {len(account_ids)} accounts on {today}")
    written = 0
    withheld = 0
    debug_trace.trace_event(
        "snapshot_job",
        "run_start",
        snapshot_date=today.isoformat(),
        accounts=len(account_ids),
        use_replay=use_replay,
        spike_threshold=spike_threshold,
    )

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

        # Union the transaction-derived CDR truth; cdr_utils is canonical and the
        # holdings column is only a cache of it. When that cache was NULL the daily
        # job priced a 1/10-scale CDR as a full US share -- a 10x error.
        # Derived once for the batch, not per account: this is a paginated scan of
        # every transaction, so a per-account call re-read the whole table N times.
        derived_cdr_by_account = portfolio_repo.get_cdr_company_ids_by_account()

        # Lot-level truth for the same batching reason, and for BLK-027: a company
        # held as BOTH a CDR lot and a direct lot cannot be priced from one
        # per-company ratio, because the ratio lands on the price
        # (raw_value = qty * current_price) and one price cannot serve two scales.
        cdr_lots_by_account = portfolio_repo.get_cdr_lots_by_account_as_of(
            today.isoformat()
        )
        gap_lot_map_cache = _GapLotMapCache(portfolio_repo)

        for aid in batch:
            account_currency = account_currency_map.get(aid, "CAD")
            exchange_overrides = {
                h["company_id"]: h["exchange_override"]
                for h in holdings_by_account.get(aid, [])
                if h.get("exchange_override")
            }
            derived_cdr = derived_cdr_by_account.get(aid) or set()
            for cid in derived_cdr:
                exchange_overrides[cid] = "TOR"
            lots_for_account = cdr_lots_by_account.get(aid) or {}

            # Repair history BEFORE writing the target date. A missed run leaves a hole,
            # and the spike check below compares against get_previous_snapshot() — i.e.
            # the last row that happens to exist. With a hole, that baseline is not the
            # previous day but the last successful run, possibly weeks back, so the check
            # fires on ordinary movement and the old carry-forward then stamped stale
            # values onto today. Filling first makes the baseline correct by construction.
            # The call is a cheap no-op when there is nothing missing.
            repaired = await _fill_snapshot_gaps(
                account_id=aid,
                today=today - timedelta(days=1),
                account_currency=account_currency,
                prices_by_company=prices_by_company,
                price_history=price_history,
                exchange_overrides=exchange_overrides,
                snapshots_repo=snapshots_repo,
                job_id_prefix="daily",
                spike_threshold=spike_threshold,
                financial_repo=financial_repo,
                all_company_ids=list(all_company_ids),
                company_currencies=company_currencies,
                companies_map=companies_map,
                derived_cdr_companies=derived_cdr,
                lot_map_cache=gap_lot_map_cache,
            )
            if repaired:
                debug_trace.trace_event(
                    "snapshot_job",
                    "gap_repair",
                    account_id=aid,
                    repaired_through=(today - timedelta(days=1)).isoformat(),
                    days_written=repaired,
                )

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
                    derived_cdr_companies=derived_cdr,
                    cdr_lots=lots_for_account,
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

                lot_legs, lot_notes = split_holdings_by_cdr_lot(
                    clean_holdings, lots_for_account, derived_cdr
                )
                for note in lot_notes:
                    logger.warning(f"Account {aid}: {note}")

                snapshot_row = build_snapshot_row(
                    account_id=aid,
                    snapshot_date=today,
                    holdings_state=lot_legs,
                    cash_balance=cash_balance,
                    net_deposits=net_deposits,
                    prices_by_company=prices_by_company,
                    job_id=f"daily_{today.isoformat()}",
                    account_currency=account_currency,
                    exchange_overrides=exchange_overrides,
                    derived_cdr_companies=derived_cdr,
                    lot_cdr_authoritative=True,
                )

            snapshot_row["job_id"] = f"daily_{today.isoformat()}"
            replayed_total = snapshot_row.get("total_value")

            # Spike detection: quarantine the write, never mutate the value.
            #
            # This used to copy the previous snapshot's total_value, holdings_market_value,
            # cash_balance and holdings_json onto this row and persist it under today's
            # date. That wrote a row dated today holding an older day's numbers — a
            # fabricated record, indistinguishable from a real one once the flag is
            # filtered out. It also destroyed the property that makes this system
            # auditable: that any day can be recomputed from events.
            #
            # Skipping the write keeps the day absent instead. The gap-fill above repairs
            # it on the next run from events + as-of prices, which is the source of truth,
            # so the question resolves itself: a real move gets written (and flagged) by
            # the recomputation, and a transient fault gets written corrected. Either way
            # the persisted number is one that was actually derived, never a stand-in.
            prev = snapshots_repo.get_previous_snapshot(aid, today)
            spike = (
                check_snapshot_spike(prev, snapshot_row, threshold=spike_threshold)
                if prev
                else None
            )
            if spike:
                logger.error(
                    f"Account {aid}: {spike['message']} — withholding {today} write for "
                    f"recomputation from events on the next run"
                )
                if debug_trace.is_enabled():
                    debug_trace.integrity_finding(
                        "REPLAY_DRIFT",
                        account_id=aid,
                        snapshot_date=today.isoformat(),
                        replayed_total=replayed_total,
                        persisted_total=None,
                        message=spike.get("message"),
                        reason="spike_write_withheld",
                        used_replay=use_replay,
                    )
                withheld += 1
                continue

            if debug_trace.is_enabled():
                debug_trace.trace_event(
                    "snapshot_job",
                    "persist_snapshot",
                    account_id=aid,
                    snapshot_date=today.isoformat(),
                    used_replay=use_replay,
                    replayed_total=replayed_total,
                    persisted_total=snapshot_row.get("total_value"),
                    data_quality_flag=snapshot_row.get("data_quality_flag"),
                    holdings=len(snapshot_row.get("holdings_json") or []),
                )

            snapshots_repo.upsert_snapshot(snapshot_row)
            written += 1

        logger.info(f"Processed accounts batch {i}-{i + len(batch)}")

    logger.info(
        f"Daily snapshot computation complete for {today}: {written} written"
    )
    debug_trace.trace_event(
        "snapshot_job",
        "run_end",
        snapshot_date=today.isoformat(),
        written=written,
        withheld=withheld,
        accounts=len(account_ids),
    )
    return written


async def handle_portfolio_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    """Handler registered with JobEngine."""
    payload = job.get("payload") or {}
    requested = payload.get("date")
    target = date.fromisoformat(requested) if requested else None
    with debug_trace.trace_scope("snapshot") as trace_id:
        debug_trace.trace_event(
            "snapshot_job",
            "job_received",
            trace_id=trace_id,
            requested_date=requested,
            resolved_date=target.isoformat() if target else None,
            payload_date_present=requested is not None,
        )
        written = await compute_daily_snapshots(target)
    return {
        "status": "completed",
        "snapshot_date": (target or now_utc().date()).isoformat(),
        "accounts_processed": written,
    }
