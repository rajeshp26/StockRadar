"""
StockerPro — Backfill daily price history for benchmark/index ETFs.

Fetches daily price data via DefeatBeta (primary) / YFinance (fallback),
normalizes to daily trading-day rows, and upserts into price_history.

Follows the same row semantics as MarketDataRefreshScheduler._upsert_daily_price_history
(shared sanitize_daily_price_rows) to keep both code paths aligned.

Usage:
  cd backend
  python scripts/backfill_benchmark_prices.py
  python scripts/backfill_benchmark_prices.py --symbol SPY QQQ
  python scripts/backfill_benchmark_prices.py --symbol SPY --dry-run
  python scripts/backfill_benchmark_prices.py --retention-years 5 --concurrency 2
  python scripts/backfill_benchmark_prices.py --symbol NYCB CMA WBA --force-bootstrap

--force-bootstrap re-fetches the full retained history even when price_history
already has rows (the incremental path would only look back ~45 days and would
never densify a company whose stored rows are month-end closes).

Default symbols: SPY QQQ IWM VTI DIA
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from config import settings
from database import supabase
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider
from shared.price_rows import sanitize_daily_price_rows

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
# Static helpers
# ---------------------------------------------------------------------------

def _years_ago(from_date: date, years: int) -> date:
    """Return a date `years` years before `from_date`, handling Feb 29 safely."""
    try:
        return from_date.replace(year=from_date.year - years)
    except ValueError:
        target_year = from_date.year - years
        return date(target_year, 3, 1) - timedelta(days=1)


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
    force_bootstrap: bool = False,
) -> dict:
    """
    Backfill daily price history for a single symbol.

    Mirrors MarketDataRefreshScheduler._upsert_daily_price_history exactly:
      1. Check if any price_history exists (bootstrap vs incremental)
      2. Apply rolling retention window filter
      3. Normalize daily rows (sanitize_daily_price_rows)
      4. Upsert + update price refresh marker

    force_bootstrap: take the full-history path even when rows already exist.
    Without it, a company whose stored rows are month-end closes is treated as
    "has history" and only gets the ~lookback_days incremental window, so its
    month-level compression is never densified.
    """
    result = {"symbol": symbol, "company_id": company_id, "status": "pending"}

    try:
        has_any = await _has_any_price_history(repo, company_id)
        retention_cutoff = _years_ago(date.today(), retention_years)

        if force_bootstrap or not has_any:
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
            daily_out = sanitize_daily_price_rows(daily_rows, default_source="defeatbeta")
            if daily_out:
                split_rows = await provider.get_splits_optimized(symbol, company_id)
                if split_rows:
                    await repo.upsert_splits(split_rows)
                await repo.upsert_price_history(daily_out)
                await repo.update_price_refresh_marker(company_id)
                logger.info(
                    "[Bootstrap] %s: %d daily rows (>= %s)",
                    symbol, len(daily_out), retention_cutoff,
                )
            else:
                logger.warning("[Bootstrap] %s: no daily rows generated", symbol)

            result["status"] = "ok" if daily_out else "no_data"
            result["mode"] = "bootstrap"
            result["rows"] = len(daily_out or [])
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
        daily_recent_out = sanitize_daily_price_rows(daily_rows_recent, default_source="defeatbeta")
        if daily_recent_out:
            split_rows = await provider.get_splits_optimized(symbol, company_id)
            if split_rows:
                await repo.upsert_splits(split_rows)
            await repo.upsert_price_history(daily_recent_out)
            await repo.update_price_refresh_marker(company_id)
            logger.info(
                "[Incremental] %s: %d daily rows (>= %s)",
                symbol, len(daily_recent_out), effective_cutoff,
            )
        else:
            logger.info(
                "[Incremental] %s: no new daily rows in window (>= %s)",
                symbol, effective_cutoff,
            )

        result["status"] = "ok" if daily_recent_out else "no_data"
        result["mode"] = "incremental"
        result["rows"] = len(daily_recent_out or [])
        return result

    except Exception as e:
        logger.error("%s (cid=%s): %s", symbol, company_id, e, exc_info=True)
        result["status"] = "error"
        result["error"] = str(e)
        return result


def _companies_without_price_history(limit: int | None = None) -> list[dict[str, Any]]:
    """Companies holding zero price_history rows.

    Enumerated by paging the whole companies table and paging price_history to
    collect the covered ids, because PostgREST caps a single select at 1000 rows
    and an earlier capped read made this set look like 3 companies instead of
    ~2926. Correctness here decides the scope of a large write, so it pages.
    """
    covered: set[int] = set()
    page = 0
    while True:
        chunk = (
            supabase.table("price_history").select("company_id")
            .range(page * 1000, page * 1000 + 999).execute()
        ).data or []
        if not chunk:
            break
        covered.update(r["company_id"] for r in chunk)
        page += 1
        if page > 600:  # safety: 600k rows
            break

    out: list[dict[str, Any]] = []
    page = 0
    while True:
        chunk = (
            supabase.table("companies")
            .select("company_id, ticker_symbol, security_type")
            .range(page * 1000, page * 1000 + 999).execute()
        ).data or []
        if not chunk:
            break
        for c in chunk:
            if c["company_id"] not in covered:
                out.append(c)
                if limit and len(out) >= limit:
                    return out
        page += 1
        if page > 20:  # safety: 20k companies
            break
    return out


async def run_backfill(
    symbols: list[str],
    retention_years: int,
    lookback_days: int,
    concurrency: int,
    dry_run: bool,
    force_bootstrap: bool = False,
    all_missing: bool = False,
    limit: int | None = None,
) -> None:
    """Resolve symbols to company_ids, then backfill concurrently.

    all_missing: ignore `symbols` and select every company that has no
    price_history at all. This is the fleet-repair mode: the writer defects meant
    ~2926 companies were never populated, so the symbol list is not the useful
    unit of work. Companies are still processed through the identical per-symbol
    path, so this changes SELECTION only, never the write semantics.
    """
    repo = SupabaseFinancialRepository(supabase)
    yf = YFinanceProvider()
    from providers.edgar_provider import EdgarToolsProvider
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    sd = StockdexMacrotrendsProvider()
    ed = EdgarToolsProvider()
    provider = DefeatBetaProvider(
        yfinance_provider=yf, stockdex_provider=sd, edgar_provider=ed,
    )

    # ── Resolve symbols → company records ──
    companies: list[dict[str, Any]] = []
    if all_missing:
        companies = _companies_without_price_history(limit=limit)
        logger.info(
            "Fleet mode: selected %d companies with no price_history%s",
            len(companies),
            f" (limit={limit})" if limit else "",
        )
    else:
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
        "Backfill targets: %s | retention=%sy | lookback=%sd | concurrency=%d | dry_run=%s | force_bootstrap=%s",
        [c["ticker_symbol"] for c in companies],
        retention_years, lookback_days, concurrency, dry_run, force_bootstrap,
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
                force_bootstrap=force_bootstrap,
            )

    results = await asyncio.gather(*[bounded(c) for c in companies])

    # ── Summary ──
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "dry_run")
    # A zero-row fetch is not a success: the company still has no prices. Counted
    # separately so a human reading the summary cannot mistake "ran without error"
    # for "data written", which is how the original outage stayed hidden.
    no_data = sum(1 for r in results if r["status"] == "no_data")
    elapsed = (datetime.utcnow() - started_at).total_seconds()

    logger.info("")
    logger.info("=" * 60)
    logger.info(
        "SUMMARY: %d ok, %d no-data, %d errors, %d dry-run | %.1fs",
        ok, no_data, err, skipped, elapsed,
    )
    if no_data:
        logger.info(
            "  (%d companies: provider served no rows -- unservable/delisted "
            "symbols, not a write failure)", no_data,
        )
    for r in results:
        if r["status"] == "ok":
            logger.info(
                "  [OK] %s (cid=%s): [%s] %d daily rows",
                r["symbol"], r["company_id"], r.get("mode", "?"), r.get("rows", 0),
            )
        elif r["status"] == "no_data":
            logger.warning(
                "  [NONE] %s (cid=%s): provider returned no rows -- no data written",
                r["symbol"], r["company_id"],
            )
        elif r["status"] == "error":
            logger.warning("  [ERR] %s (cid=%s): %s", r["symbol"], r["company_id"], r.get("error"))
        elif r["status"] == "dry_run":
            logger.info("  [DRY] %s (cid=%s): dry-run (no changes)", r["symbol"], r["company_id"])

    if err:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill daily price history for benchmark/index ETFs.",
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
    parser.add_argument(
        "--force-bootstrap", action="store_true",
        help="Re-fetch full retained history even when rows already exist "
             "(densifies monthly-compressed companies; incremental path alone "
             "would only look back ~45 days)",
    )
    parser.add_argument(
        "--all-missing", action="store_true",
        help="Fleet repair: select every company with zero price_history instead "
             "of --symbol. Combines with --limit for a pilot run.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="With --all-missing, cap the number of companies processed.",
    )
    args = parser.parse_args()

    symbols = args.symbol or DEFAULT_SYMBOLS

    asyncio.run(run_backfill(
        symbols=symbols,
        retention_years=args.retention_years,
        lookback_days=args.lookback_days,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
        force_bootstrap=args.force_bootstrap,
        all_missing=args.all_missing,
        limit=args.limit,
    ))


if __name__ == "__main__":
    main()
