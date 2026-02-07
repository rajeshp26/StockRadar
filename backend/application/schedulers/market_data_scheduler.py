# -*- coding: utf-8 -*-
"""
Market Data Refresh Scheduler

Responsibilities
---------------
- Runs every N hours (default: 24) to refresh market-derived datasets:
  * Monthly price history (EOM close = last trading day's close)
  * Stock splits
  * Revenue forecasts
  * Earnings forecasts
  * Company summary snapshot

- One-time bootstrap per company:
  * If no price_history exists -> fetch FULL daily series (limited by rolling retention),
    compress to monthly, upsert

- Incremental thereafter:
  * Fetch last ~lookback_days daily bars, recompute EOM for months in that window, upsert

Resilience & Ops
----------------
- Per-company distributed locks (Supabase `scheduler_locks`) → safe for multi-replica
- DefeatBeta primary with YFinance fallback
- Concurrency-limited workers
- Rolling 10-year retention window for price history fetch (configurable)
- Optional pruning hook present but disabled by default (commented out)
- Manual trigger, status fields for diagnostics
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from config import settings
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider  # YF fallback injection
from database import supabase  # used for lightweight existence checks

logger = logging.getLogger(__name__)


class MarketDataRefreshScheduler:
    """
    Periodic market data scheduler (separate from Earnings scheduler).

    Public API:
      - start(), stop()
      - trigger_immediate_run()

    Introspection for /status:
      - is_running (property)
      - last_run_at, next_run_at, last_result
    """

    def __init__(
        self,
        financial_repo: Optional[SupabaseFinancialRepository] = None,
        defeat_beta_provider: Optional[DefeatBetaProvider] = None,
    ):
        # Repos & Providers
        self.financial_repo = financial_repo or SupabaseFinancialRepository()

        # Always inject yfinance fallback provider
        yf_provider = YFinanceProvider()
        self.defeat_beta_provider = defeat_beta_provider or DefeatBetaProvider(
            yfinance_provider=yf_provider
        )

        # Config (with safe defaults)
        self.interval_hours: int = int(getattr(settings, "MARKET_DATA_REFRESH_INTERVAL_HOURS", 24))
        self.lookback_days: int = int(getattr(settings, "MARKET_DATA_PRICE_LOOKBACK_DAYS", 45))  # incremental fetch window
        self.max_concurrency: int = int(getattr(settings, "MARKET_DATA_MAX_CONCURRENCY", 5))
        self.company_statuses: List[str] = getattr(
            settings,
            "MARKET_DATA_COMPANY_STATUSES",
            ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"],
        )
        # Rolling retention window for price history fetches (years)
        self.retention_years: int = int(getattr(settings, "PRICE_HISTORY_RETENTION_YEARS", 10))

        # Per-company lock TTL (seconds); market-data cycle work is typically shorter than earnings
        self.lock_ttl_seconds: int = int(getattr(settings, "SCHEDULER_COMPANY_LOCK_TTL_SECONDS", 1800))  # 30 min

        # Runtime
        self._is_running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Status (surfaced by /status endpoints)
        self.last_run_at: Optional[datetime] = None
        self.next_run_at: Optional[datetime] = None
        self.last_result: Optional[Dict[str, Any]] = None

        # This scheduler instance's unique owner ID (stored in scheduler_locks.lock_id)
        self.owner_lock_id: str = f"market_data:{uuid.uuid4()}"

    # ----------------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------------
    @property
    def is_running(self) -> bool:
        return self._is_running

    async def start(self) -> None:
        if self._is_running:
            logger.warning("MarketDataRefreshScheduler already running")
            return
        self._is_running = True
        self._task = asyncio.create_task(self._run_loop(), name="market_data_scheduler")
        logger.info("🚀 Market Data Scheduler started (interval: %sh)", self.interval_hours)

    async def stop(self) -> None:
        self._is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️  Market Data Scheduler stopped")

    # ----------------------------------------------------------------------
    # Public manual trigger
    # ----------------------------------------------------------------------
    async def trigger_immediate_run(self) -> Dict[str, Any]:
        """
        Public manual trigger for one full refresh cycle (dev/admin/testing).
        """
        logger.info("🔄 Manual trigger: Market Data refresh cycle")
        # Run a single cycle without disturbing the main loop scheduling
        result = await self._refresh_cycle()
        # Do not adjust next_run_at here (keep loop schedule intact)
        return result

    # ----------------------------------------------------------------------
    # Main Loop
    # ----------------------------------------------------------------------
    async def _run_loop(self) -> None:
        while self._is_running:
            cycle_started_at = datetime.utcnow()
            try:
                self.last_run_at = cycle_started_at
                self.last_result = await self._refresh_cycle()
            except Exception as e:
                logger.error("Market data cycle failed: %s", e, exc_info=True)
                # Keep last_result as-is on failure
            finally:
                # Compute next_run_at only after cycle ends
                sleep_seconds = max(1, int(self.interval_hours * 3600))
                self.next_run_at = datetime.utcnow() + timedelta(seconds=sleep_seconds)
                logger.debug(
                    "MarketData scheduler sleeping for %sh (next_run_at=%s)",
                    self.interval_hours,
                    self.next_run_at.isoformat(),
                )
                try:
                    await asyncio.sleep(sleep_seconds)
                except asyncio.CancelledError:
                    # shutdown
                    break

    # ----------------------------------------------------------------------
    # Single Cycle
    # ----------------------------------------------------------------------
    async def _refresh_cycle(self) -> Dict[str, Any]:
        logger.info("📊 Market data refresh cycle started")

        # Pull target companies (active statuses by default)
        companies = await self.financial_repo.get_companies_for_market_data(self.company_statuses)
        total = len(companies or [])
        if total == 0:
            logger.info("✅ No companies eligible for market-data refresh")
            return {"companies_found": 0, "companies_succeeded": 0, "companies_failed": 0, "detail": []}

        logger.info("Found %d companies for market-data refresh", total)

        # Concurrency control
        sem = asyncio.Semaphore(self.max_concurrency)
        results = {
            "companies_found": total,
            "companies_succeeded": 0,
            "companies_failed": 0,
            "detail": [],
        }

        async def _worker(company: Dict[str, Any]):
            async with sem:
                cid = company["company_id"]
                sym = company["ticker_symbol"]

                # Per-company distributed lock (multi-replica safety)
                acquired = await self.financial_repo.acquire_company_lock(
                    company_id=cid,
                    owner_id=self.owner_lock_id,
                    ttl_seconds=self.lock_ttl_seconds,
                    lock_type="market_data_refresh",
                )
                if not acquired:
                    logger.info("🔒 Skip %s (company_id=%s): lock held by another replica", sym, cid)
                    results["detail"].append({"symbol": sym, "ok": True, "skipped": True, "reason": "lock_held"})
                    return

                try:
                    detail = await self._process_company(sym, cid)
                    results["companies_succeeded"] += 1
                    results["detail"].append({"symbol": sym, "ok": True, **detail})
                except Exception as e:
                    logger.error("Company %s failed: %s", sym, e, exc_info=True)
                    results["companies_failed"] += 1
                    results["detail"].append({"symbol": sym, "ok": False, "error": str(e)})
                finally:
                    # Release lock regardless of outcome
                    await self.financial_repo.release_company_lock(cid, self.owner_lock_id)

        await asyncio.gather(*[_worker(c) for c in companies])

        # ------------------------------------------------------------------
        # Optional: pruning (disabled by default)
        # Uncomment after you add SupabaseFinancialRepository.prune_price_history()
        # await self.financial_repo.prune_price_history(
        #     retention_years=self.retention_years
        # )
        # ------------------------------------------------------------------

        logger.info(
            "✅ Market data cycle complete: %s ok, %s failed",
            results["companies_succeeded"],
            results["companies_failed"],
        )
        return results

    # ----------------------------------------------------------------------
    # Per-Company Process
    # ----------------------------------------------------------------------
    async def _process_company(self, symbol: str, company_id: int) -> Dict[str, Any]:
        """
        Steps:
          1) Price history (monthly EOM compression; bootstrap or incremental) respecting rolling retention
          2) Splits
          3) Revenue forecast
          4) Earnings forecast
          5) Company summary snapshot
        """
        # 1) PRICE HISTORY (monthly EOM)
        price_rows_written = await self._upsert_monthly_price_history(symbol, company_id)

        # 2) SPLITS (DefeatBeta -> fallback YF inside provider)
        split_rows = await self.defeat_beta_provider.get_splits_optimized(symbol, company_id)
        if split_rows:
            await self.financial_repo.upsert_splits(split_rows)

        # 3) REVENUE FORECAST (DefeatBeta only currently)
        rev_fcst_rows = await self.defeat_beta_provider.fetch_revenue_forecast(symbol, company_id)
        if rev_fcst_rows:
            await self.financial_repo.upsert_revenue_forecast(rev_fcst_rows)

        # 4) EARNINGS FORECAST (DefeatBeta only currently)
        eps_fcst_rows = await self.defeat_beta_provider.fetch_earnings_forecast(symbol, company_id)
        if eps_fcst_rows:
            await self.financial_repo.upsert_earnings_forecast(eps_fcst_rows)

        # 5) COMPANY SUMMARY (DBeta -> fallback YF inside provider)
        summary = await self.defeat_beta_provider.get_company_summary_optimized(symbol, company_id)
        if summary:
            await self.financial_repo.upsert_company_summary(summary)

        return {
            "price_history_monthly": price_rows_written,
            "splits": len(split_rows or []),
            "revenue_forecast": len(rev_fcst_rows or []),
            "earnings_forecast": len(eps_fcst_rows or []),
            "company_summary": 1 if summary else 0,
        }

    # ----------------------------------------------------------------------
    # Price History helpers (with rolling retention)
    # ----------------------------------------------------------------------
    async def _upsert_monthly_price_history(self, symbol: str, company_id: int) -> int:
        """
        - If company has NO price_history rows: FULL fetch (limited by rolling retention window)
          -> monthly EOM compress -> upsert all
        - Else: incremental fetch (last ~lookback_days), monthly EOM compress, upsert newest month(s)
        Returns the number of monthly rows attempted for upsert (dedupe happens in repo).
        """
        has_any = await self._has_any_price_history(company_id)
        retention_cutoff = self._years_ago(date.today(), self.retention_years)

        if not has_any:
            # One-time bootstrap: full daily -> monthly compress (respect retention)
            daily_rows = await self.defeat_beta_provider.get_price_history_optimized(symbol, company_id)
            # Client-side filter to rolling retention window
            daily_rows = [
                r for r in (daily_rows or [])
                if r.get("price_date") and r["price_date"] >= retention_cutoff
            ]
            monthly_rows = self._compress_daily_to_monthly_eom(daily_rows)
            if monthly_rows:
                await self.financial_repo.upsert_price_history(monthly_rows)
                logger.info("[PH][%s] Bootstrap monthly rows (>= %s): %d", symbol, retention_cutoff, len(monthly_rows))
            return len(monthly_rows or [])

        # Incremental: pull recent daily, recompute EOM for any months in window
        lookback = max(self.lookback_days, 40)  # safety floor
        window_cutoff = date.today() - timedelta(days=lookback)

        daily_rows_recent = await self.defeat_beta_provider.get_price_history_optimized(symbol, company_id)
        # Client-side filter to max(retention_cutoff, window_cutoff)
        effective_cutoff = max(retention_cutoff, window_cutoff)
        daily_rows_recent = [
            r for r in (daily_rows_recent or [])
            if r.get("price_date") and r["price_date"] >= effective_cutoff
        ]

        # Recompute monthly bars for any months present in the window
        monthly_recent = self._compress_daily_to_monthly_eom(daily_rows_recent)
        if monthly_recent:
            await self.financial_repo.upsert_price_history(monthly_recent)
            logger.debug("[PH][%s] Incremental monthly rows (>= %s): %d", symbol, effective_cutoff, len(monthly_recent))
        return len(monthly_recent or [])

    async def _has_any_price_history(self, company_id: int) -> bool:
        """
        Returns True if any price_history row exists for the company.
        (Small targeted query to avoid additional repo plumbing.)
        """
        try:
            resp = (
                supabase.table("price_history")
                .select("price_date", count="exact")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            # Prefer Supabase exact count when available
            if hasattr(resp, "count") and resp.count is not None:
                return resp.count > 0
            return bool(resp.data)
        except Exception:
            # If the check fails, be conservative and return False (bootstrap path)
            logger.debug("price_history existence check failed for company_id=%s", company_id)
            return False

    @staticmethod
    def _compress_daily_to_monthly_eom(daily_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert daily rows (dicts with 'price_date' and 'close_price') to monthly EOM rows:
         - Group by (year, month)
         - Pick the row with the latest price_date (last trading day of that month)
         - Preserve OHLCV when available (close is most important)
         - Keep 'data_source' if present, default 'defeatbeta'

        Output rows keep the original 'price_date' (the last trading day date) as the monthly bar date.
        """
        if not daily_rows:
            return []

        df = pd.DataFrame(daily_rows)
        if df.empty or "price_date" not in df.columns:
            return []

        # Ensure datetime for price_date
        df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
        df = df.dropna(subset=["price_date"])
        if df.empty:
            return []

        # Extract (year, month)
        df["year"] = df["price_date"].dt.year
        df["month"] = df["price_date"].dt.month

        # For each (year, month), pick the row with max(price_date) -> last trading day
        idx = df.groupby(["year", "month"])["price_date"].idxmax()
        last_trading_rows = df.loc[idx].copy()

        out: List[Dict[str, Any]] = []
        for _, r in last_trading_rows.iterrows():
            out.append({
                "company_id": int(r.get("company_id")),
                "price_date": r["price_date"].date(),
                "open_price": MarketDataRefreshScheduler._safe_num(r.get("open_price")),
                "close_price": MarketDataRefreshScheduler._safe_num(r.get("close_price")),
                "high_price": MarketDataRefreshScheduler._safe_num(r.get("high_price")),
                "low_price": MarketDataRefreshScheduler._safe_num(r.get("low_price")),
                "volume": int(r.get("volume")) if pd.notna(r.get("volume")) else None,
                "data_source": str(r.get("data_source") or "defeatbeta"),
            })

        # Sort by date for consistency
        out.sort(key=lambda x: x["price_date"])
        return out

    @staticmethod
    def _safe_num(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            f = float(v)
            # NaN check: NaN != NaN in Python
            return f if f == f else None
        except (ValueError, TypeError):
            return None
            
    @staticmethod
    def _years_ago(from_date: date, years: int) -> date:
        """
        Compute a date 'years' years before 'from_date', handling leap years safely.
        Example: Feb 29 -> Feb 28 in non-leap target year.
        """
        try:
            return from_date.replace(year=from_date.year - years)
        except ValueError:
            # Handle Feb 29 -> Feb 28 (or similar end-of-month anomalies)
            # Move to the last valid day of February in the target year
            # Simplest approach: subtract (365*years + safety) days then normalize forward if needed
            # But for predictability, fallback to March 1 - 1 day in target year path:
            target_year = from_date.year - years
            # Use March 1 of target year, subtract one day -> last day of Feb target year
            march_first = date(target_year, 3, 1)
            return march_first - timedelta(days=1)