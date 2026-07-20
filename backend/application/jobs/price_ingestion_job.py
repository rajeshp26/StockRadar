import asyncio
import logging
import time
from datetime import date
from typing import Any, Dict, List, Optional

from config import settings
from infrastructure.repositories.price_repository import PriceRepository
from providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger("stockerpro.price.ingestion")

stock_provider = YFinanceProvider()
repo = PriceRepository()


def timed(logger=logger):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            elapsed = time.time() - start
            logger.info("%s took %.2fs", func.__name__, elapsed)
            return result
        return wrapper
    return decorator


@timed()
async def refresh_all_prices():
    holdings = repo.get_all_active_holdings()
    company_ids = {h["company_id"] for h in holdings if h.get("company_id")}
    if not company_ids:
        logger.info("[PRICE-INGEST] no active holdings, skipping")
        return

    prefs = repo.get_price_source_preferences(list(company_ids))

    yfinance_items = []
    supabase_items = set()

    for h in holdings:
        cid = h.get("company_id")
        exchange = h.get("exchange_override") or "UNKNOWN"
        pref = prefs.get((cid, exchange))
        if pref is None:
            logger.warning(
                "[PRICE-INGEST] no preference for (company=%s, exchange=%s) — skipped",
                cid, exchange,
            )
            continue
        if pref == "yfinance_tor":
            yfinance_items.append((cid, h["symbol"], exchange))
        elif pref == "supabase_market_data":
            supabase_items.add(cid)

    prices = {}

    if yfinance_items:
        symbols = list(set(item[1] for item in yfinance_items))
        exchange = yfinance_items[0][2]

        yf_results = await _fetch_yfinance_batch(
            symbols, exchange,
            per_symbol_timeout=getattr(settings, "YFINANCE_SINGLE_TIMEOUT_SECONDS", 10),
            max_concurrent=5,
        )

        symbol_to_cid = {item[1]: item[0] for item in yfinance_items}
        for sym, result in yf_results.items():
            cid = symbol_to_cid.get(sym)
            if result["error"]:
                logger.warning(
                    "[PRICE-INGEST] symbol=%s exchange=%s error=%s",
                    sym, exchange, result["error"],
                )
                continue
            if cid and result["price"] is not None:
                prices[(cid, exchange)] = {
                    "price": result["price"],
                    "source": "yfinance_tor",
                    "currency": "CAD",
                    "ttl_seconds": 300,
                }

    company_exchanges: Dict[int, str] = {}
    if supabase_items:
        company_exchanges = repo.get_company_exchanges(list(supabase_items))
        supabase_prices = await _fetch_supabase_prices(list(supabase_items))
        for cid, price in supabase_prices.items():
            if price is not None:
                exchange = company_exchanges.get(cid, "UNKNOWN")
                prices[(cid, exchange)] = {
                    "price": price,
                    "source": "supabase_market_data",
                    "currency": "USD",
                    "ttl_seconds": 30,
                }

    for (cid, exchange), data in prices.items():
        repo.upsert_price_source(
            company_id=cid,
            exchange=exchange,
            price=data["price"],
            source=data["source"],
            currency=data["currency"],
            ttl_seconds=data["ttl_seconds"],
        )

    logger.info(
        "[PRICE-INGEST] refreshed %d/%d prices (yfinance=%d, supabase=%d)",
        len(prices), len(company_ids), len(yfinance_items), len(supabase_items),
    )

    # Auto-update CDR ratios after price refresh
    await _update_cdr_ratios()

    # Emit split events for unprocessed splits
    _emit_split_events()


async def _update_cdr_ratios():
    """Auto-update CDR ratios for all CDR holdings after price refresh.

    Computes cdr_ratio = TSX_share_price / CDR_average_cost and stores in companies table.
    Called automatically after daily price refresh.
    """
    try:
        # Find all CDR companies (those with exchange_override="TOR" in holdings)
        hold_result = (
            repo.client.table("portfolio_holdings")
            .select("company_id")
            .eq("exchange_override", "TOR")
            .execute()
        )
        cdr_cids = list(set(row["company_id"] for row in (hold_result.data or [])))
        if not cdr_cids:
            return

        # Get current TSX share prices
        cmr_result = (
            repo.client.table("current_market_data")
            .select("company_id, current_price")
            .in_("company_id", cdr_cids)
            .execute()
        )
        tsx_prices = {row["company_id"]: float(row["current_price"])
                      for row in (cmr_result.data or [])
                      if row.get("current_price")}

        # Get weighted average CDR cost per company
        hold_detail = (
            repo.client.table("portfolio_holdings")
            .select("company_id, average_cost, quantity")
            .in_("company_id", cdr_cids)
            .eq("exchange_override", "TOR")
            .execute()
        )
        cost_data: Dict[int, Dict] = {}
        for row in (hold_detail.data or []):
            cid = row["company_id"]
            avg = float(row.get("average_cost") or 0)
            qty = float(row.get("quantity") or 0)
            if qty > 0 and avg > 0:
                if cid not in cost_data:
                    cost_data[cid] = {"total_cost": 0.0, "total_qty": 0.0}
                cost_data[cid]["total_cost"] += avg * qty
                cost_data[cid]["total_qty"] += qty

        updated = 0
        for cid in cdr_cids:
            tsx_price = tsx_prices.get(cid)
            if not tsx_price or cid not in cost_data:
                continue
            cd = cost_data[cid]
            if cd["total_qty"] <= 0:
                continue
            cdr_avg_cost = cd["total_cost"] / cd["total_qty"]
            if cdr_avg_cost <= 0:
                continue

            ratio = tsx_price / cdr_avg_cost
            # Sanity check: ratio should be between 1 and 100
            if ratio < 1 or ratio > 100:
                logger.warning(
                    "[CDR-RATIO] company=%d ratio=%.2f out of range, skipping",
                    cid, ratio,
                )
                continue

            try:
                repo.client.table("companies").update({
                    "cdr_ratio": round(ratio, 2),
                    "cdr_ratio_date": date.today().isoformat(),
                }).eq("company_id", cid).execute()
                updated += 1
            except Exception as e:
                logger.warning("[CDR-RATIO] failed to update company %d: %s", cid, e)

        if updated:
            logger.info("[CDR-RATIO] updated %d/%d CDR ratios", updated, len(cdr_cids))

    except Exception as e:
        logger.error("[CDR-RATIO] update failed: %s", e)


def _emit_split_events() -> None:
    """For each unprocessed split, emit a split event per affected account."""
    from infrastructure.repositories.event_store import EventStore
    from shared.split_utils import parse_split_factor

    event_store = EventStore()

    try:
        splits_res = (
            repo.client.table("splits")
            .select("company_id, report_date, split_factor")
            .eq("processed", False)
            .execute()
        )
    except Exception as e:
        logger.error("[SPLIT-EVENT] failed to fetch unprocessed splits: %s", e)
        return

    if not splits_res.data:
        return

    for split in splits_res.data:
        cid = split["company_id"]
        report_date = split["report_date"]
        split_factor_str = split.get("split_factor") or ""

        factor = parse_split_factor(split_factor_str)
        if factor <= 0 or factor == 1:
            continue

        try:
            holdings_res = (
                repo.client.table("portfolio_holdings")
                .select("account_id")
                .eq("company_id", cid)
                .execute()
            )
        except Exception as e:
            logger.error("[SPLIT-EVENT] failed to fetch holdings for company %d: %s", cid, e)
            continue

        account_ids = list({h["account_id"] for h in (holdings_res.data or [])})
        if not account_ids:
            continue

        events = []
        for aid in account_ids:
            idempotency_key = f"split_{cid}_{report_date}_{aid}"
            events.append({
                "event_type": "split",
                "event_version": 1,
                "aggregate_id": f"account_{aid}",
                "aggregate_type": "account",
                "data": {
                    "company_id": cid,
                    "split_factor": str(factor),
                    "report_date": report_date,
                },
                "metadata": {},
                "idempotency_key": idempotency_key,
            })

        if events:
            try:
                event_store.append_events_batch(events)
                logger.info(
                    "[SPLIT-EVENT] emitted %d split events for company %d (factor=%s)",
                    len(events), cid, factor,
                )
            except Exception as e:
                logger.error("[SPLIT-EVENT] failed to emit events for company %d: %s", cid, e)
                continue

        try:
            repo.client.table("splits").update({"processed": True}) \
                .eq("company_id", cid) \
                .eq("report_date", report_date) \
                .execute()
        except Exception as e:
            logger.error("[SPLIT-EVENT] failed to mark split processed for company %d: %s", cid, e)


async def _fetch_supabase_prices(company_ids: List[int]) -> Dict[int, Optional[float]]:
    if not company_ids:
        return {}
    try:
        result = (
            repo.client.table("current_market_data")
            .select("company_id, current_price")
            .in_("company_id", company_ids)
            .execute()
        )
        return {row["company_id"]: row.get("current_price") for row in (result.data or [])}
    except Exception as e:
        logger.error("[PRICE-INGEST] supabase bulk query failed: %s", e)
        return {}


async def _fetch_yfinance_batch(
    symbols: List[str], exchange: str,
    per_symbol_timeout: int = 10, max_concurrent: int = 5,
    max_retries: int = 2,
) -> Dict[str, Dict]:
    sem = asyncio.Semaphore(max_concurrent)

    async def fetch_one(sym: str) -> tuple:
        for attempt in range(1, max_retries + 2):
            async with sem:
                try:
                    sd = await asyncio.wait_for(
                        asyncio.to_thread(
                            stock_provider.get_stock_details, sym, exchange=exchange,
                        ),
                        timeout=per_symbol_timeout,
                    )
                    return sym, {"price": sd.price if sd else None, "error": None}
                except asyncio.TimeoutError:
                    if attempt <= max_retries:
                        await asyncio.sleep(1)
                    else:
                        return sym, {"price": None, "error": "timeout"}
                except Exception as e:
                    if attempt <= max_retries:
                        await asyncio.sleep(1)
                    else:
                        return sym, {"price": None, "error": str(e)}
        return sym, {"price": None, "error": "max retries exceeded"}

    results = await asyncio.gather(
        *[fetch_one(s) for s in symbols], return_exceptions=True
    )
    return {sym: data for sym, data in results if not isinstance(data, Exception)}


async def handle_price_ingestion(job: Dict[str, Any]) -> Dict[str, Any]:
    """Handler registered with JobEngine."""
    await refresh_all_prices()
    return {"status": "completed"}
