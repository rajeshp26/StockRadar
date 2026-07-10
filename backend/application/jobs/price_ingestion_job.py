import asyncio
import logging
import time
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
