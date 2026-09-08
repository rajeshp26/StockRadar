import asyncio
import logging
import random
import time
from datetime import date
from typing import Any

from config import settings
from infrastructure.repositories.price_repository import PriceRepository
from providers.yfinance_provider import YFinanceProvider
from shared.constants import get_effective_skipped_symbols

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
    symbols = repo.get_all_active_symbols()

    # Drop delisted/renamed symbols (WBA, CMA, NYCB, CS, ...) before hitting
    # the provider — they 404 on yfinance every cycle and only add retry noise.
    skipped = get_effective_skipped_symbols()
    symbols = [
        s for s in symbols
        if (s.get("symbol") or "").upper() not in skipped
    ]

    company_ids = {s["company_id"] for s in symbols if s.get("company_id")}
    if not company_ids:
        logger.info("[PRICE-INGEST] no active symbols, skipping")
        return

    yfinance_items_by_exchange: dict[str, list] = {}

    for s in symbols:
        cid = s.get("company_id")
        exchange = s.get("exchange_override") or "UNKNOWN"
        if exchange not in yfinance_items_by_exchange:
            yfinance_items_by_exchange[exchange] = []
        yfinance_items_by_exchange[exchange].append((cid, s["symbol"], exchange))

    prices = {}

    if yfinance_items_by_exchange:
        for exchange, items in yfinance_items_by_exchange.items():
            syms = list(set(item[1] for item in items))

            yf_results = await _fetch_yfinance_batch(
                syms, exchange,
                per_symbol_timeout=getattr(settings, "YFINANCE_SINGLE_TIMEOUT_SECONDS", 10),
                max_concurrent=2,
            )

            symbol_to_cid = {item[1]: item[0] for item in items}
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
                        "source": "yfinance",
                        "currency": "CAD" if exchange in ("TOR", "TSX", "TO", "VAN", "TSXV", "V", "CNQ", "NEO") else "USD",
                        "ttl_seconds": 300,
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
        "[PRICE-INGEST] refreshed %d/%d prices across %d exchanges",
        len(prices), len(company_ids), len(yfinance_items_by_exchange),
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
        cost_data: dict[int, dict] = {}
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
                # Duplicate-key means a previous cycle already emitted these events
                # (e.g. a crash between append and mark-processed). Not fatal: fall
                # through and mark the split processed so the cycle self-heals instead
                # of retrying the same batch on every run.
                if "duplicate key" in str(e).lower():
                    logger.warning(
                        "[SPLIT-EVENT] events for company %d already exist (factor=%s) - marking processed",
                        cid, factor,
                    )
                else:
                    logger.error(
                        "[SPLIT-EVENT] failed to emit events for company %d: %s", cid, e,
                    )
                    continue

        try:
            repo.client.table("splits").update({"processed": True}) \
                .eq("company_id", cid) \
                .eq("report_date", report_date) \
                .execute()
        except Exception as e:
            logger.error("[SPLIT-EVENT] failed to mark split processed for company %d: %s", cid, e)


async def _fetch_yfinance_batch(
    symbols: list[str], exchange: str,
    per_symbol_timeout: int = 10, max_concurrent: int = 2,
    max_retries: int = 2,
) -> dict[str, dict]:
    sem = asyncio.Semaphore(max_concurrent)

    def _backoff_delay(attempt: int) -> float:
        """Jittered exponential backoff: base 2.5s * 2^(attempt-1), jitter x0.75-1.25.

        Slows the instantaneous request rate to keep yfinance under its 429
        threshold; jitter prevents synchronized thundering-herd retries."""
        delay = 2.5 * (2 ** (attempt - 1))
        return delay * random.uniform(0.75, 1.25)

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
                except TimeoutError:
                    if attempt <= max_retries:
                        await asyncio.sleep(_backoff_delay(attempt))
                    else:
                        return sym, {"price": None, "error": "timeout"}
                except Exception as e:
                    if attempt <= max_retries:
                        await asyncio.sleep(_backoff_delay(attempt))
                    else:
                        return sym, {"price": None, "error": str(e)}
        return sym, {"price": None, "error": "max retries exceeded"}

    results = await asyncio.gather(
        *[fetch_one(s) for s in symbols], return_exceptions=True
    )
    return {sym: data for sym, data in results if not isinstance(data, Exception)}


async def handle_price_ingestion(job: dict[str, Any]) -> dict[str, Any]:
    """Handler registered with JobEngine."""
    await refresh_all_prices()
    return {"status": "completed"}
