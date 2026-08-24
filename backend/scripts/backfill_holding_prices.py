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
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.yfinance_provider import YFinanceProvider

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


def _compress_daily_to_monthly_eom(daily_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not daily_rows:
        return []
    df = pd.DataFrame(daily_rows)
    if df.empty or "price_date" not in df.columns:
        return []
    df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
    df = df.dropna(subset=["price_date"])
    if df.empty:
        return []
    df["year"] = df["price_date"].dt.year
    df["month"] = df["price_date"].dt.month
    idx = df.groupby(["year", "month"])["price_date"].idxmax()
    last_trading_rows = df.loc[idx].copy()
    out: list[dict[str, Any]] = []
    for _, r in last_trading_rows.iterrows():
        out.append({
            "company_id":  int(r.get("company_id")),
            "price_date":  r["price_date"].date(),
            "open_price":  _safe_num(r.get("open_price")),
            "close_price": _safe_num(r.get("close_price")),
            "high_price":  _safe_num(r.get("high_price")),
            "low_price":   _safe_num(r.get("low_price")),
            "volume":      int(r.get("volume")) if pd.notna(r.get("volume")) else None,
            "data_source": "yfinance",
        })
    out.sort(key=lambda x: x["price_date"])
    return out


# ---------------------------------------------------------------------------
# Core backfill logic
# ---------------------------------------------------------------------------

def _get_all_holding_symbols() -> list[str]:
    """Return all distinct ticker symbols across all portfolio_holdings."""
    resp = (
        supabase.table("portfolio_holdings")
        .select("symbol")
        .not_.is_("symbol", "null")
        .execute()
    )
    symbols = sorted({r["symbol"] for r in (resp.data or [])})
    logger.info("Found %d unique symbols in portfolio_holdings", len(symbols))
    return symbols


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
    """Check whether price_history has any rows for this company."""
    try:
        resp = (
            supabase.table("price_history")
            .select("price_date", count="exact")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        if hasattr(resp, "count") and resp.count is not None:
            return resp.count > 0
        return bool(resp.data)
    except Exception:
        return False


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


def _strip_split_artifacts(rows: list[dict[str, Any]], symbol: str) -> list[dict[str, Any]]:
    """Strip reverse-split price artifacts where old prices dwarf recent ones.

    Stocks with multiple reverse splits (e.g. XELA) produce raw price_history
    where pre-split prices compound into absurdly high numbers ($120K for a
    penny stock).  This removes entries whose close_price exceeds 100x the
    median close_price of the most recent 20 trading days.
    """
    if len(rows) < 30:
        return rows

    # Sort by date ascending
    sorted_rows = sorted(rows, key=lambda r: r["price_date"])
    recent = [r for r in reversed(sorted_rows) if r.get("close_price") is not None]

    # Get median of 20 most recent closes
    recent_closes = sorted([r["close_price"] for r in recent[:20]])
    recent_median = recent_closes[len(recent_closes) // 2]

    if recent_median is None or recent_median <= 0:
        return rows

    ceiling = recent_median * 100
    clean = [r for r in sorted_rows if r.get("close_price") is None or r["close_price"] <= ceiling]
    removed = len(sorted_rows) - len(clean)
    if removed:
        logger.info("%s: stripped %d of %d rows with close_price > %.2f (100x recent median %.4f)",
                     symbol, removed, len(sorted_rows), ceiling, recent_median)
    return clean


async def backfill_symbol(
    repo: SupabaseFinancialRepository,
    yf_provider: YFinanceProvider,
    symbol: str,
    dry_run: bool,
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
        needs_history = not await _has_price_history(repo, cid)

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
                logger.info("%s: upserted current_market_data ($%.2f)", symbol, sd.price)
            else:
                logger.warning("%s: no current price from YFinance", symbol)

        # ── Fetch price history ──
        if needs_history:
            price_df = yf_provider.get_price_history_df(symbol, exchange=exchange)
            if price_df is not None and not price_df.empty:
                daily_rows = _yfinance_daily_to_rows(price_df, cid)
                daily_rows = _strip_split_artifacts(daily_rows, symbol)
                if daily_rows:
                    monthly_rows = _compress_daily_to_monthly_eom(daily_rows)
                    if monthly_rows:
                        await repo.upsert_price_history(monthly_rows)
                        await repo.update_price_refresh_marker(cid)
                        result["history_rows"] = len(monthly_rows)
                        logger.info(
                            "%s: upserted %d monthly price_history rows",
                            symbol, len(monthly_rows),
                        )
                    else:
                        logger.warning("%s: no monthly rows generated from %d daily rows",
                                       symbol, len(daily_rows))
                else:
                    logger.warning("%s: no daily rows parsed from data", symbol)
            else:
                logger.warning("%s: empty price history from YFinance", symbol)

        result["status"] = "ok"
        return result

    except Exception as e:
        logger.error("%s: %s", symbol, e, exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)
        return result


async def run_backfill(
    symbols: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Resolve symbols, then backfill price data for each."""
    repo = SupabaseFinancialRepository(supabase)
    yf_provider = YFinanceProvider()

    if symbols:
        target_symbols = sorted(set(s.upper() for s in symbols))
    else:
        target_symbols = _get_all_holding_symbols()

    if not target_symbols:
        logger.info("No symbols to process.")
        return

    logger.info(
        "Target: %d symbols | dry_run=%s",
        len(target_symbols), dry_run,
    )

    # Bounded concurrency to control YFinance API rate limits
    sem = asyncio.Semaphore(5)

    async def bounded(sym: str) -> dict:
        async with sem:
            return await backfill_symbol(repo, yf_provider, sym, dry_run=dry_run)

    started_at = datetime.utcnow()
    results = await asyncio.gather(*[bounded(sym) for sym in target_symbols])

    # ── Summary ──
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    dry = sum(1 for r in results if r["status"] == "dry_run")
    elapsed = (datetime.utcnow() - started_at).total_seconds()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY: %d ok, %d errors, %d skipped, %d dry-run | %.1fs",
                ok, err, skipped, dry, elapsed)

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
    args = parser.parse_args()

    asyncio.run(run_backfill(
        symbols=args.symbol,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
