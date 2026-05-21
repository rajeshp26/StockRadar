"""
StockerPro — Backfill monthly EOM price history for benchmark/index ETFs.

Fetches daily price data via DefeatBeta (primary) / YFinance (fallback),
compresses to monthly end-of-month bars, and upserts into price_history.

Follows the exact same logic as MarketDataRefreshScheduler._upsert_monthly_price_history
to keep both code paths aligned.

Usage:
  cd backend
  python scripts/backfill_benchmark_prices.py
  python scripts/backfill_benchmark_prices.py --symbol SPY QQQ
  python scripts/backfill_benchmark_prices.py --symbol SPY --dry-run
  python scripts/backfill_benchmark_prices.py --retention-years 5 --concurrency 2

Default symbols: SPY QQQ IWM VTI DIA
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from database import supabase
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_backend / "logs" / "backfill_benchmarks.log", mode="a"),
    ],
)
logger = logging.getLogger("backfill_benchmarks")

DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM", "VTI", "DIA"]
DEFAULT_RETENTION_YEARS = int(getattr(settings, "PRICE_HISTORY_RETENTION_YEARS", 10))
DEFAULT_LOOKBACK_DAYS = int(getattr(settings, "MARKET_DATA_PRICE_LOOKBACK_DAYS", 45))


# ---------------------------------------------------------------------------
# Static helpers — identical to MarketDataRefreshScheduler
# ---------------------------------------------------------------------------

def _safe_num(v: Any) -> Optional[float]:
    """Safely convert a value to float, handling None / NaN / bad types."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f else None  # NaN guard
    except (ValueError, TypeError):
        return None


def _years_ago(from_date: date, years: int) -> date:
    """Return a date `years` years before `from_date`, handling Feb 29 safely."""
    try:
        return from_date.replace(year=from_date.year - years)
    except ValueError:
        target_year = from_date.year - years
        return date(target_year, 3, 1) - timedelta(days=1)


def _compress_daily_to_monthly_eom(daily_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert daily OHLCV rows to monthly EOM rows:
      - Group by (year, month)
      - Pick the row with the latest price_date (last trading day of the month)
      - Preserve all OHLCV fields; default data_source to 'defeatbeta'
    """
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
    out: List[Dict[str, Any]] = []
    for _, r in last_trading_rows.iterrows():
        out.append({
            "company_id":  int(r.get("company_id")),
            "price_date":  r["price_date"].date(),
            "open_price":  _safe_num(r.get("open_price")),
            "close_price": _safe_num(r.get("close_price")),
            "high_price":  _safe_num(r.get("high_price")),
            "low_price":   _safe_num(r.get("low_price")),
            "volume":      int(r.get("volume")) if pd.notna(r.get("volume")) else None,
            "data_source": str(r.get("data_source") or "defeatbeta"),
        })
    out.sort(key=lambda x: x["price_date"])
    return out


# ---------------------------------------------------------------------------
# Core backfill logic
# ---------------------------------------------------------------------------

async def _has_any_price_history(
    repo: SupabaseFinancialRepository, company_id: int
) -> bool:
    """Check whether price_history already has rows for this company."""
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
        logger.debug(
            "price_history existence check failed for company_id=%s", company_id
        )
        return False


async def backfill_symbol(
    repo: SupabaseFinancialRepository,
    provider: DefeatBetaProvider,
    symbol: str,
    company_id: int,
    retention_years: int,
    lookback_days: int,
    dry_run: bool,
) -> dict:
    """
    Backfill monthly EOM price history for a single symbol.

    Mirrors MarketDataRefreshScheduler._upsert_monthly_price_history exactly:
      1. Check if any price_history exists (bootstrap vs incremental)
      2. Apply rolling retention window filter
      3. Compress daily → monthly EOM
      4. Upsert + update price refresh marker
    """
    result = {"symbol": symbol, "company_id": company_id, "status": "pending"}

    try:
        has_any = await _has_any_price_history(repo, company_id)
        retention_cutoff = _years_ago(date.today(), retention_years)

        if not has_any:
            # ── Bootstrap: no existing rows → full daily history ──
            if dry_run:
                logger.info(
                    "[DRY RUN] %s (cid=%s): would bootstrap from %s",
                    symbol, company_id, retention_cutoff,
                )
                result["status"] = "dry_run"
                return result

            daily_rows = await provider.get_price_history_optimized(symbol, company_id)
            daily_rows = [
                r for r in (daily_rows or [])
                if r.get("price_date") and r["price_date"] >= retention_cutoff
            ]
            monthly_rows = _compress_daily_to_monthly_eom(daily_rows)
            if monthly_rows:
                await repo.upsert_price_history(monthly_rows)
                await repo.update_price_refresh_marker(company_id)
                logger.info(
                    "[Bootstrap] %s: %d monthly rows (>= %s)",
                    symbol, len(monthly_rows), retention_cutoff,
                )
            else:
                logger.warning("[Bootstrap] %s: no monthly rows generated", symbol)

            result["status"] = "ok"
            result["mode"] = "bootstrap"
            result["rows"] = len(monthly_rows or [])
            return result

        # ── Incremental: rows exist → fetch recent window ──
        lookback = max(lookback_days, 40)
        window_cutoff = date.today() - timedelta(days=lookback)
        effective_cutoff = max(retention_cutoff, window_cutoff)

        if dry_run:
            logger.info(
                "[DRY RUN] %s (cid=%s): would fetch incremental >= %s",
                symbol, company_id, effective_cutoff,
            )
            result["status"] = "dry_run"
            return result

        daily_rows_recent = await provider.get_price_history_optimized(symbol, company_id)
        daily_rows_recent = [
            r for r in (daily_rows_recent or [])
            if r.get("price_date") and r["price_date"] >= effective_cutoff
        ]
        monthly_recent = _compress_daily_to_monthly_eom(daily_rows_recent)
        if monthly_recent:
            await repo.upsert_price_history(monthly_recent)
            await repo.update_price_refresh_marker(company_id)
            logger.info(
                "[Incremental] %s: %d monthly rows (>= %s)",
                symbol, len(monthly_recent), effective_cutoff,
            )
        else:
            logger.info(
                "[Incremental] %s: no new monthly rows in window (>= %s)",
                symbol, effective_cutoff,
            )

        result["status"] = "ok"
        result["mode"] = "incremental"
        result["rows"] = len(monthly_recent or [])
        return result

    except Exception as e:
        logger.error("%s (cid=%s): %s", symbol, company_id, e, exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)
        return result


async def run_backfill(
    symbols: List[str],
    retention_years: int,
    lookback_days: int,
    concurrency: int,
    dry_run: bool,
) -> None:
    """Resolve symbols to company_ids, then backfill concurrently."""
    repo = SupabaseFinancialRepository(supabase)
    yf = YFinanceProvider()
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    from providers.edgar_provider import EdgarToolsProvider
    sd = StockdexMacrotrendsProvider()
    ed = EdgarToolsProvider()
    provider = DefeatBetaProvider(
        yfinance_provider=yf, stockdex_provider=sd, edgar_provider=ed,
    )

    # ── Resolve symbols → company records ──
    companies: List[Dict[str, Any]] = []
    for sym in symbols:
        upper = sym.upper()
        resp = (
            supabase.table("companies")
            .select("company_id, ticker_symbol, security_type")
            .eq("ticker_symbol", upper)
            .limit(1)
            .execute()
        )
        if resp.data:
            companies.append(resp.data[0])
        else:
            logger.warning(
                "%s: not found in companies table -- skipping. "
                "Import a CSV containing this symbol first, then re-run.",
                upper,
            )

    if not companies:
        logger.error("No valid companies found for any of the requested symbols.")
        return

    logger.info(
        "Backfill targets: %s | retention=%sy | lookback=%sd | concurrency=%d | dry_run=%s",
        [c["ticker_symbol"] for c in companies],
        retention_years, lookback_days, concurrency, dry_run,
    )

    # ── Run with bounded concurrency ──
    sem = asyncio.Semaphore(concurrency)
    started_at = datetime.utcnow()

    async def bounded(company: dict) -> dict:
        async with sem:
            return await backfill_symbol(
                repo=repo,
                provider=provider,
                symbol=company["ticker_symbol"],
                company_id=company["company_id"],
                retention_years=retention_years,
                lookback_days=lookback_days,
                dry_run=dry_run,
            )

    results = await asyncio.gather(*[bounded(c) for c in companies])

    # ── Summary ──
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "dry_run")
    elapsed = (datetime.utcnow() - started_at).total_seconds()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY: %d ok, %d errors, %d dry-run | %.1fs", ok, err, skipped, elapsed)
    for r in results:
        if r["status"] == "ok":
            logger.info(
                "  [OK] %s (cid=%s): [%s] %d monthly rows",
                r["symbol"], r["company_id"], r.get("mode", "?"), r.get("rows", 0),
            )
        elif r["status"] == "error":
            logger.warning("  [ERR] %s (cid=%s): %s", r["symbol"], r["company_id"], r.get("error"))
        elif r["status"] == "dry_run":
            logger.info("  [DRY] %s (cid=%s): dry-run (no changes)", r["symbol"], r["company_id"])

    if err:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill monthly EOM price history for benchmark/index ETFs.",
    )
    parser.add_argument(
        "--symbol", type=str, nargs="*", default=None,
        help="Symbol(s) to backfill (default: SPY QQQ IWM VTI DIA)",
    )
    parser.add_argument(
        "--retention-years", type=int, default=DEFAULT_RETENTION_YEARS,
        help="Rolling retention window in years (default: %(default)s)",
    )
    parser.add_argument(
        "--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS,
        help="Lookback window for incremental refresh (default: %(default)s)",
    )
    parser.add_argument(
        "--concurrency", type=int, default=3,
        help="Max parallel fetches (default: %(default)s)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print plan; make no DB or provider calls",
    )
    args = parser.parse_args()

    symbols = args.symbol or DEFAULT_SYMBOLS

    asyncio.run(run_backfill(
        symbols=symbols,
        retention_years=args.retention_years,
        lookback_days=args.lookback_days,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
