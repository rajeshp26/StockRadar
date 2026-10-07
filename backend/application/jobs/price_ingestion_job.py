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
    """Maintain the structural CDR ratio for CDR companies after price refresh.

    The CDR ratio is a fixed structural property of the instrument (1 CDR =
    1/CDR_RATIO of an underlying US share), fixed by the depositary at issuance.
    It is NOT a market measurement and is NEVER derived from TSX price, CDR
    average cost, or any other price/cost data. This function writes ONLY the
    structural constant ``shared.cdr_utils.CDR_RATIO``. A market-derived value
    written here is a bug.

    A company is CDR when EVERY one of its holdings rows carries
    exchange_override="TOR" (unanimous, company-global rule). Per-account CDR
    classification is owned by shared.cdr_utils.derive_cdr_companies_by_account;
    this function only maintains the company-level reference value, which
    per-account pricing (snapshot_builder) applies via each holding's
    exchange_override.
    """
    from shared.cdr_utils import CDR_RATIO, EXCHANGE_OVERRIDE_TOR

    hold_result = repo.client.table("portfolio_holdings").select(
        "company_id, exchange_override"
    ).execute()
    total_by_cid: dict[int, int] = {}
    tor_by_cid: dict[int, int] = {}
    for row in (hold_result.data or []):
        cid = int(row["company_id"])
        total_by_cid[cid] = total_by_cid.get(cid, 0) + 1
        if row.get("exchange_override") == EXCHANGE_OVERRIDE_TOR:
            tor_by_cid[cid] = tor_by_cid.get(cid, 0) + 1

    cdr_cids = {
        cid for cid, total in total_by_cid.items()
        if tor_by_cid.get(cid, 0) == total
    }
    if not cdr_cids:
        return

    today = date.today().isoformat()
    updated = 0
    for cid in cdr_cids:
        try:
            repo.client.table("companies").update(
                {
                    "cdr_ratio": float(CDR_RATIO),
                    "cdr_ratio_date": today,
                    # Required by the companies_cdr_ratio_range CHECK; not read back here
                    "cdr_ratio_source": "structural_constant",
                }
            ).eq("company_id", cid).execute()
            updated += 1
        except Exception as e:
            logger.warning("[CDR-RATIO] failed to update company %d: %s", cid, e)

    logger.info(
        "[CDR-RATIO] wrote structural ratio %s for %d/%d CDR companies",
        CDR_RATIO, updated, len(cdr_cids),
    )


def _emit_split_events() -> None:
    """Emit split events for every (split, account) pair that lacks one.

    Delegates to shared.split_sync.reconcile_split_events: the account set is
    derived from the immutable event stream (holding evidence), never from
    current portfolio_holdings, so accounts that sold the split security before
    the job ran are still covered. The splits.processed latch is updated by the
    reconciler only after a successful emission and is a hint, not a gate —
    reconciliation re-scans ALL splits regardless of latch state.
    """
    from shared.split_sync import reconcile_split_events

    try:
        report = reconcile_split_events(client=repo.client, dry_run=False)
    except Exception as e:
        logger.error("[SPLIT-EVENT] reconciliation failed: %s", e)
        return

    if report.error:
        logger.error("[SPLIT-EVENT] reconciliation error: %s", report.error)
        return

    if report.emitted_events:
        logger.info(
            "[SPLIT-EVENT] emitted %d split events for %d companies",
            report.emitted_events,
            len(report.companies_with_gaps),
        )
    else:
        logger.info(
            "[SPLIT-EVENT] no missing split events (checked %d account-company pairs)",
            report.checked_splits,
        )


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
