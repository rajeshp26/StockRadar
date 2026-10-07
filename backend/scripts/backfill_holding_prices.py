"""
StockerPro — Backfill price data for existing portfolio holdings.

Fetches current prices (-> current_market_data) and monthly EOM price history
(-> price_history) for any symbols in portfolio_holdings that lack them.

This is a one-time backfill for holdings imported before the on-demand
price fetch (Phase 2) was implemented.

Usage:
  cd backend
  python scripts/backfill_holding_prices.py
  python scripts/backfill_holding_prices.py --symbol AAPL MSFT
  python scripts/backfill_holding_prices.py --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from infrastructure.repositories.event_store import EventStore
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider
from shared.constants import get_effective_skipped_symbols
from shared.price_rows import sanitize_daily_price_rows

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_backend / "logs" / "backfill_holdings.log", mode="a"),
    ],
)
logger = logging.getLogger("backfill_holdings")


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------

def _safe_num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Core backfill logic
# ---------------------------------------------------------------------------

def _get_all_holding_symbols() -> list[str]:
    """Symbols behind both portfolio_holdings and the account event stream.

    The two sources disagree: a holding whose events were never collapsed into
    portfolio_holdings is absent from that table, and reading either one alone
    under-backfills silently. Events carry company_id rather than a symbol, so
    they resolve through companies.ticker_symbol.
    """
    symbols: set[str] = set()

    resp = (
        supabase.table("portfolio_holdings")
        .select("symbol")
        .not_.is_("symbol", "null")
        .execute()
    )
    from_holdings = {str(r["symbol"]).upper() for r in (resp.data or []) if r.get("symbol")}
    symbols |= from_holdings
    logger.info("Found %d unique symbols in portfolio_holdings", len(from_holdings))

    event_cids: set[int] = set()
    try:
        for ev in EventStore().get_all_events(aggregate_type="account"):
            cid = (ev.get("data") or {}).get("company_id")
            if cid is None:
                continue
            try:
                event_cids.add(int(cid))
            except (TypeError, ValueError):
                continue
    except Exception as e:
        logger.warning("Could not read account event stream: %s", e)

    from_events: set[str] = set()
    if event_cids:
        ordered = sorted(event_cids)
        for i in range(0, len(ordered), 200):
            chunk = ordered[i:i + 200]
            try:
                cresp = (
                    supabase.table("companies")
                    .select("company_id,ticker_symbol")
                    .in_("company_id", chunk)
                    .execute()
                )
            except Exception as e:
                logger.warning("company_id lookup failed for a chunk of %d ids: %s", len(chunk), e)
                continue
            from_events |= {
                str(r["ticker_symbol"]).upper()
                for r in (cresp.data or [])
                if r.get("ticker_symbol")
            }

    only_events = from_events - from_holdings
    symbols |= from_events
    logger.info(
        "Found %d unique symbols in account events (%d absent from portfolio_holdings)",
        len(from_events), len(only_events),
    )
    if only_events:
        logger.info("Event-only holdings portfolio_holdings is missing: %s", sorted(only_events))
    return sorted(symbols)


def _current_market_data_exists(company_id: int) -> bool:
    """Check whether current_market_data has an entry for this company."""
    try:
        resp = (
            supabase.table("current_market_data")
            .select("company_id")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        return bool(resp.data)
    except Exception:
        return False


async def _has_price_history(repo: SupabaseFinancialRepository, company_id: int) -> bool:
    """Check whether price_history already holds daily-resolution rows.

    Existence is not sufficient: a company backfilled before the
    month-end compression was removed has ~12 rows/year, so a presence
    check reports it as complete while every mid-month snapshot falls
    back to a stale quote. Density is the property that matters, so
    compare the stored span against the trading days it should cover.
    """
    try:
        resp = (
            supabase.table("price_history")
            .select("price_date", count="exact")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        count = getattr(resp, "count", None)
        if count is None:
            count = len(resp.data or [])
        if count == 0:
            return False
    except Exception:
        return False

    return await _is_daily_resolution(company_id, count)


async def _is_daily_resolution(company_id: int, count: int) -> bool:
    """True when stored rows are dense enough to price a snapshot on its own date."""
    try:
        resp = (
            supabase.table("price_history")
            .select("price_date")
            .eq("company_id", company_id)
            .order("price_date", desc=False)
            .limit(1)
            .execute()
        )
        first = (resp.data or [{}])[0].get("price_date")
    except Exception:
        return False
    if first is None:
        return False

    try:
        span_days = (date.today() - date.fromisoformat(str(first)[:10])).days
    except ValueError:
        return False
    if span_days <= 0:
        return True

    # ~252 trading days per calendar year; 45% is the monthly-compression
    # threshold, since ~12 EOM rows/year is well under it.
    return count >= 0.45 * (span_days / 365.0) * 252


def _yfinance_daily_to_rows(df: pd.DataFrame, company_id: int) -> list[dict[str, Any]]:
    """Convert a yfinance price_history_df to a list of row dicts."""
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        pdate = r.get("price_date")
        if pdate is None:
            continue
        if isinstance(pdate, pd.Timestamp):
            pdate = pdate.date()
        rows.append({
            "company_id":  company_id,
            "price_date":  pdate,
            "open_price":  _safe_num(r.get("open_price")),
            "close_price": _safe_num(r.get("close_price")),
            "high_price":  _safe_num(r.get("high_price")),
            "low_price":   _safe_num(r.get("low_price")),
            "volume":      int(r.get("volume")) if pd.notna(r.get("volume")) else None,
            "data_source": "yfinance",
        })
    return rows


async def backfill_symbol(
    repo: SupabaseFinancialRepository,
    yf_provider: YFinanceProvider,
    db_provider: DefeatBetaProvider,
    symbol: str,
    dry_run: bool,
    force: bool = False,
) -> dict:
    """
    Backfill current_market_data and price_history for a single symbol.
    Returns a dict with status details.
    """
    result: dict = {"symbol": symbol, "status": "pending"}

    try:
        company = await repo.get_company_by_symbol(symbol)
        if not company:
            result["status"] = "skipped"
            result["reason"] = "not found in companies table"
            return result

        cid = company["company_id"]
        needs_current = not _current_market_data_exists(cid)
        # force re-fetches history even when stored rows look dense, because a
        # density check cannot see rows an earlier run wrongly removed.
        needs_history = force or not await _has_price_history(repo, cid)

        if not needs_current and not needs_history:
            result["status"] = "skipped"
            result["reason"] = "both current_market_data and price_history exist"
            return result

        result["company_id"] = cid
        result["needs_current"] = needs_current
        result["needs_history"] = needs_history

        if dry_run:
            result["status"] = "dry_run"
            return result

        exchange = company.get("exchange")
        wrote_any = False

        # ── Fetch current price ──
        if needs_current:
            sd = yf_provider.get_stock_details(symbol, exchange=exchange)
            if sd and sd.price is not None:
                vol_raw = _safe_num(getattr(sd, "volume", None))
                market_data = {
                    "company_id":    cid,
                    "current_price": sd.price,
                    "open_price":    _safe_num(getattr(sd, "open_price", None)),
                    "high_price":    _safe_num(getattr(sd, "high_price", None)),
                    "low_price":     _safe_num(getattr(sd, "low_price", None)),
                    "close_price":   _safe_num(getattr(sd, "close_price", None)),
                    "volume":        int(vol_raw) if vol_raw is not None else None,
                    "market_state":  getattr(sd, "market_state", None),
                }
                supabase.table("current_market_data").upsert(
                    market_data, on_conflict="company_id"
                ).execute()
                result["current_price"] = sd.price
                wrote_any = True
                logger.info("%s: upserted current_market_data ($%.2f)", symbol, sd.price)
            else:
                logger.warning("%s: no current price from YFinance", symbol)

        # ── Fetch price history ──
        if needs_history:
            price_df = yf_provider.get_price_history_df(symbol, exchange=exchange)
            if price_df is not None and not price_df.empty:
                daily_rows = sanitize_daily_price_rows(
                    _yfinance_daily_to_rows(price_df, cid), default_source="yfinance"
                )
                if daily_rows:
                    split_rows = await db_provider.get_splits_optimized(symbol, cid)
                    if split_rows:
                        await repo.upsert_splits(split_rows)
                    # Daily granularity is required, not optional: a mid-month
                    # snapshot has no price of its own at month-end resolution,
                    # and resolving one picks a stale or future quote. Month-end
                    # rows are a subset of daily, so this upsert supersedes them.
                    upsert = await repo.upsert_price_history(daily_rows)
                    await repo.update_price_refresh_marker(cid)
                    # The plausibility gate runs inside the upsert, so the fetched
                    # count is not what landed. Reporting it as "upserted" hid
                    # TNXP's 2980 rejections behind "history=3615" this session.
                    gate = (upsert or {}).get("gate_rejected")
                    rejected = int(gate.get(cid, 0)) if isinstance(gate, dict) else int(gate or 0)
                    written = (upsert or {}).get("count")
                    if not isinstance(written, int):
                        written = len(daily_rows) - rejected
                    result["history_rows"] = written
                    result["gate_rejected"] = rejected
                    wrote_any = True
                    logger.info(
                        "%s: wrote %d daily price_history rows (%d rejected by plausibility gate)",
                        symbol, written, rejected,
                    )
                else:
                    logger.warning("%s: no daily rows parsed from data", symbol)
            else:
                logger.warning("%s: empty price history from YFinance", symbol)

        result["status"] = "ok" if wrote_any else "no_data"
        return result

    except Exception as e:
        logger.error("%s: %s", symbol, e, exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)
        return result


async def run_backfill(
    symbols: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Resolve symbols, then backfill price data for each."""
    repo = SupabaseFinancialRepository(supabase)
    yf_provider = YFinanceProvider()
    db_provider = DefeatBetaProvider()

    if symbols:
        target_symbols = sorted(set(s.upper() for s in symbols))
    else:
        target_symbols = _get_all_holding_symbols()

    delisted = sorted(s for s in target_symbols if s.upper() in get_effective_skipped_symbols())
    if delisted:
        target_symbols = [s for s in target_symbols if s.upper() not in get_effective_skipped_symbols()]
        logger.info("[FILTER] Skipped %d delisted/renamed symbol(s): %s", len(delisted), delisted)

    if not target_symbols:
        logger.info("No symbols to process.")
        return

    logger.info(
        "Target: %d symbols | dry_run=%s | force=%s",
        len(target_symbols), dry_run, force,
    )

    # Bounded concurrency to control YFinance API rate limits
    sem = asyncio.Semaphore(5)

    async def bounded(sym: str) -> dict:
        async with sem:
            return await backfill_symbol(repo, yf_provider, db_provider, sym, dry_run=dry_run, force=force)

    started_at = datetime.utcnow()
    results = await asyncio.gather(*[bounded(sym) for sym in target_symbols])

    # ── Summary ──
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    no_data = sum(1 for r in results if r["status"] == "no_data")
    dry = sum(1 for r in results if r["status"] == "dry_run")
    elapsed = (datetime.utcnow() - started_at).total_seconds()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY: %d ok, %d errors, %d skipped, %d no-data, %d dry-run | %.1fs",
                ok, err, skipped, no_data, dry, elapsed)

    if dry_run:
        for r in results:
            if r["status"] == "dry_run":
                needs = []
                if r.get("needs_current"):
                    needs.append("current_market_data")
                if r.get("needs_history"):
                    needs.append("price_history")
                logger.info("  [DRY] %s (cid=%s): would fetch %s",
                            r["symbol"], r.get("company_id"), "+".join(needs))
    else:
        for r in results:
            if r["status"] == "ok":
                parts = []
                if r.get("current_price") is not None:
                    parts.append("price=$%.2f" % r["current_price"])
                if r.get("history_rows"):
                    parts.append("history=%d rows" % r["history_rows"])
                detail = ", ".join(parts) if parts else "done"
                logger.info("  [OK] %s (cid=%s): %s", r["symbol"], r.get("company_id"), detail)
            elif r["status"] == "error":
                logger.warning("  [ERR] %s: %s", r["symbol"], r.get("error"))
            elif r["status"] == "skipped":
                logger.info("  [SKIP] %s: %s", r["symbol"], r.get("reason", "?"))
            elif r["status"] == "no_data":
                logger.warning("  [NODATA] %s: provider returned no current price or price history", r["symbol"])

    if err:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill price data for existing portfolio holdings.",
    )
    parser.add_argument(
        "--symbol", type=str, nargs="*", default=None,
        help="Symbol(s) to backfill (default: all symbols in portfolio_holdings)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print plan; make no DB or provider calls",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-fetch price_history even when stored rows already look dense",
    )
    args = parser.parse_args()

    asyncio.run(run_backfill(
        symbols=args.symbol,
        dry_run=args.dry_run,
        force=args.force,
    ))


if __name__ == "__main__":
    main()
