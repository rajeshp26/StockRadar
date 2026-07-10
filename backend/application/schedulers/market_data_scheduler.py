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
NEW
---
- After company processing, evaluate Rule #1 ONLY if dependencies changed (freshness gate).
- Derived financial ratios computed unconditionally each cycle (version-gated internally).
- Dividend metrics computed unconditionally each cycle (exits early if no dividend history).
"""
import asyncio
import logging
import uuid

from datetime import date, datetime, timedelta
from shared.time_utils import now_utc
from typing import Any, Dict, List, Optional

import pandas as pd

from config import settings
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from database import supabase

# Derived metrics jobs
from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_derived_financial_metrics,
    compute_and_upsert_dividend_metrics,
    compute_and_upsert_quarterly_health_scores,
    compute_and_upsert_quarterly_valuation_metrics,
)

logger = logging.getLogger(__name__)


# ── Global semaphore to rate-limit Stockdex/Finviz across parallel workers ──
stockdex_semaphore = asyncio.Semaphore(1)


def _as_date(value: Any) -> Optional[date]:
    """Parse a date value from Supabase (ISO string or date object)."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except Exception:
            return None
    if isinstance(value, datetime):
        return value.date()
    return None


def estimate_next_ex_date(
    company_id: int,
    financial_repo: SupabaseFinancialRepository,
) -> Optional[date]:
    """Estimate next ex-dividend date from historical payment pattern.

    Reads actuals only (dividend_amount IS NOT NULL, ex_date <= today)
    from dividend_history. Never reads upcoming_dividend_events.

    Logic from design doc §7.3 Step 3:
      1. Fetch up to 8 recent actual payments
      2. Filter special dividends in Python (graceful degradation)
      3. Use average gap (not most common) to determine frequency
      4. Map to frequency bands via relativedelta
      5. Suppress predictions for deep-past dates (suspended payers)
    """
    try:
        today = now_utc().date()
        resp = (
            supabase.table("dividend_history")
            .select("ex_dividend_date, dividend_amount, dividend_type")
            .eq("company_id", company_id)
            .not_.is_("dividend_amount", "null")
            .lte("ex_dividend_date", today.isoformat())
            .order("ex_dividend_date", desc=True)
            .limit(8)
            .execute()
        )
        rows = resp.data or []
        if not rows or len(rows) < 4:
            logger.debug(
                "[PREDICT] company_id=%s: %d rows (< 4), cannot predict",
                company_id, len(rows),
            )
            return None

        # Filter out special dividends (not representative of regular cadence)
        regular = [r for r in rows if r.get("dividend_type", "regular") != "special"]
        if len(regular) < 4:
            regular = rows[:4]

        # Parse dates (Supabase returns ISO strings, not date objects)
        sorted_dates = sorted(_as_date(r["ex_dividend_date"]) for r in regular)
        sorted_dates = [d for d in sorted_dates if d is not None]
        if len(sorted_dates) < 4:
            return None

        gaps = [(b - a).days for a, b in zip(sorted_dates, sorted_dates[1:]) if (b - a).days > 0]
        if not gaps:
            return None

        avg_gap = sum(gaps) / len(gaps)
        last_ex = sorted_dates[-1]

        from dateutil.relativedelta import relativedelta

        # Map avg gap to frequency
        if avg_gap <= 35:
            next_date = last_ex + timedelta(days=round(avg_gap))
        elif avg_gap <= 100:
            months = round(avg_gap / 30.44)
            next_date = last_ex + relativedelta(months=months)
        elif avg_gap <= 200:
            next_date = last_ex + relativedelta(months=6)
        else:
            next_date = last_ex + relativedelta(years=1)

        # Suppress predictions for deep-past dates (suspended payers)
        if next_date >= today:
            logger.debug(
                "[PREDICT] company_id=%s: last=%s avg_gap=%dd predicted=%s",
                company_id, last_ex, round(avg_gap), next_date,
            )
            return next_date
        return None

    except Exception as e:
        logger.error("[PREDICT] Failed for company_id=%s: %s", company_id, e)
        return None


async def refresh_upcoming_dividend(
    company_id: int,
    symbol: str,
    financial_repo: SupabaseFinancialRepository,
) -> None:
    """Refresh upcoming dividend events for a single company.

    Runs all providers in sequence (with rate limiting), then falls
    back to prediction if no provider returned data. Each source
    upserts its own opinion via UNIQUE(company_id, data_source).
    """
    from providers.yfinance_provider import YFinanceProvider
    yf = YFinanceProvider()
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    sd = StockdexMacrotrendsProvider()

    # 1. YFinance (primary) — no rate limit issue
    yf_date = yf.get_upcoming_ex_date(symbol)

    # 2. Stockdex/Finviz (secondary) — rate-limited via global semaphore
    sd_date = None
    async with stockdex_semaphore:
        await asyncio.sleep(1)  # max 1 req/sec to Finviz
        sd_date = sd.get_upcoming_ex_date(symbol)

    # 3. Upsert each source opinion
    if yf_date:
        await financial_repo.upsert_upcoming_dividend(
            company_id, yf_date, data_source="yfinance",
        )
    if sd_date:
        await financial_repo.upsert_upcoming_dividend(
            company_id, sd_date, data_source="finviz",
        )

    # 4. Prediction fallback (only if no provider data)
    if not yf_date and not sd_date:
        pred_date = estimate_next_ex_date(company_id, financial_repo)
        if pred_date:
            await financial_repo.upsert_upcoming_dividend(
                company_id, pred_date, data_source="predicted",
            )

    # 5. Cleanup stale events (14-day grace period)
    await financial_repo.cleanup_stale_events(company_id)


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
        defeat_beta_provider: Optional["DefeatBetaProvider"] = None,
    ):
        # Repos & Providers
        self.financial_repo = financial_repo or SupabaseFinancialRepository()
        self.defeat_beta_provider = defeat_beta_provider
        if self.defeat_beta_provider is None:
            try:
                from providers.yfinance_provider import YFinanceProvider
                from providers.defeat_beta_provider import DefeatBetaProvider
                yf_provider = YFinanceProvider()
                from providers.stockdex_provider import StockdexMacrotrendsProvider
                from providers.edgar_provider import EdgarToolsProvider
                self.defeat_beta_provider = DefeatBetaProvider(
                    yfinance_provider=yf_provider,
                    stockdex_provider=StockdexMacrotrendsProvider(),
                    edgar_provider=EdgarToolsProvider(),
                )
            except Exception as import_err:
                logger.warning("Failed to initialize DefeatBetaProvider: %s", import_err)

        # Config (with safe defaults)
        self.interval_hours: int = int(getattr(settings, "MARKET_DATA_REFRESH_INTERVAL_HOURS", 24))
        self.lookback_days: int = int(getattr(settings, "MARKET_DATA_PRICE_LOOKBACK_DAYS", 45))
        self.max_concurrency: int = int(getattr(settings, "MARKET_DATA_MAX_CONCURRENCY", 5))
        self.company_statuses: List[str] = getattr(
            settings,
            "MARKET_DATA_COMPANY_STATUSES",
            ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"],
        )
        self.retention_years: int = int(getattr(settings, "PRICE_HISTORY_RETENTION_YEARS", 10))
        self.lock_ttl_seconds: int = int(getattr(settings, "SCHEDULER_COMPANY_LOCK_TTL_SECONDS", 1800))

        # FX Service for currency conversion
        self.fx_service: Optional[Any] = None
        if settings.ENABLE_FX_CONVERSION:
            from shared.fx_service import FXService
            self.fx_service = FXService(supabase)

        # Runtime
        self._is_running: bool = False
        self._task: Optional[asyncio.Task] = None

        # Status (surfaced by /status endpoints)
        self.last_run_at: Optional[datetime] = None
        self.next_run_at: Optional[datetime] = None
        self.last_result: Optional[Dict[str, Any]] = None

        self.owner_lock_id: str = f"market_data:{uuid.uuid4()}"

    # -------------------------------------------------------------------------
    # v3 Planner Integration
    # -------------------------------------------------------------------------

    async def plan(self) -> list:
        """
        v3 planner integration — returns company_refresh job dicts for each
        active company needing market data refresh.

        Handlers (registered in scheduler_worker.py):
          - handler for 'company_refresh' with scope='market_data'
            runs price history, splits, revenue/earnings forecasts,
            company summary, derived ratios, dividend metrics, RI valuation.

        Returns list of dicts, each suitable for SchedulerRepository.enqueue_job:
            job_type: 'company_refresh'
            dedupe_key: 'company_refresh:{company_id}:market_data'
            resource_type: 'company'
            resource_id: company_id (as str)
            payload: { company_id, ticker_symbol, security_type, exchange, scope: 'market_data' }
            priority: 30 (lower than earnings)
        """
        try:
            companies = await self.financial_repo.get_active_companies_for_market_data()
        except Exception:
            companies = []
        jobs = []
        for c in companies or []:
            jobs.append({
                "job_type": "company_refresh",
                "dedupe_key": f"company_refresh:{c.get('company_id')}:market_data",
                "resource_type": "company",
                "resource_id": str(c.get("company_id", "")),
                "payload": {
                    "company_id": c.get("company_id"),
                    "ticker_symbol": c.get("ticker_symbol"),
                    "security_type": c.get("security_type", "stock"),
                    "exchange": c.get("exchange"),
                    "scopes": ["market_data"],
                },
                "priority": 30,
                "max_attempts": 3,
            })
        return jobs

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # Public manual trigger
    # -------------------------------------------------------------------------

    async def trigger_immediate_run(self) -> Dict[str, Any]:
        """Public manual trigger for one full refresh cycle (dev/admin/testing)."""
        logger.info("🔄 Manual trigger: Market Data refresh cycle")
        result = await self._refresh_cycle()
        return result

    # -------------------------------------------------------------------------
    # Main Loop
    # -------------------------------------------------------------------------

    async def _run_loop(self) -> None:
        while self._is_running:
            cycle_started_at = now_utc()
            try:
                self.last_run_at = cycle_started_at
                self.last_result = await self._refresh_cycle()
            except Exception as e:
                logger.error("Market data cycle failed: %s", e, exc_info=True)
            finally:
                sleep_seconds = max(1, int(self.interval_hours * 3600))
                self.next_run_at = now_utc() + timedelta(seconds=sleep_seconds)
                logger.debug(
                    "MarketData scheduler sleeping for %sh (next_run_at=%s)",
                    self.interval_hours,
                    self.next_run_at.isoformat(),
                )
                try:
                    await asyncio.sleep(sleep_seconds)
                except asyncio.CancelledError:
                    break

    # -------------------------------------------------------------------------
    # Single Cycle
    # -------------------------------------------------------------------------

    async def _refresh_cycle(self) -> Dict[str, Any]:
        logger.info("📊 Market data refresh cycle started")

        # Process only active companies (in ANY user's portfolio or watchlist)
        companies = await self.financial_repo.get_active_companies_for_market_data()
        total = len(companies or [])
        if total == 0:
            logger.info("✅ No companies eligible for market-data refresh")
            return {"companies_found": 0, "companies_succeeded": 0, "companies_failed": 0, "detail": []}

        logger.info("Found %d companies for market-data refresh", total)

        sem = asyncio.Semaphore(self.max_concurrency)
        results: Dict[str, Any] = {
            "companies_found": total,
            "companies_succeeded": 0,
            "companies_failed": 0,
            "detail": [],
        }

        async def _worker(company: Dict[str, Any]) -> None:
            async with sem:
                cid = company["company_id"]
                sym = company["ticker_symbol"]

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
                    detail = await self._process_company(
                        sym, cid, company.get("security_type", "stock"),
                        exchange=company.get("exchange"),
                    )
                    results["companies_succeeded"] += 1
                    results["detail"].append({"symbol": sym, "ok": True, **detail})
                except Exception as e:
                    logger.error("Company %s failed: %s", sym, e, exc_info=True)
                    results["companies_failed"] += 1
                    results["detail"].append({"symbol": sym, "ok": False, "error": str(e)})
                finally:
                    await self.financial_repo.release_company_lock(cid, self.owner_lock_id)

        await asyncio.gather(*[_worker(c) for c in companies])

        # ------------------------------------------------------------------
        # Optional: pruning (disabled by default)
        # await self.financial_repo.prune_price_history(retention_years=self.retention_years)
        # ------------------------------------------------------------------

        # FX rate refresh (non-company, runs once per cycle)
        if settings.ENABLE_FX_CONVERSION:
            try:
                self._refresh_fx_rates()
            except Exception as e:
                logger.error("FX rate refresh failed: %s", e)

        logger.info(
            "✅ Market data cycle complete: %s ok, %s failed",
            results["companies_succeeded"],
            results["companies_failed"],
        )
        return results

    # -------------------------------------------------------------------------
    # FX Rate Refresh
    # -------------------------------------------------------------------------

    def _refresh_fx_rates(self) -> None:
        """Fetch and cache daily FX rates."""
        from providers.fx_provider import fetch_fx_rate
        today = now_utc().date()

        usd_to_cad = fetch_fx_rate("USD", "CAD")
        if usd_to_cad is not None and self.fx_service is not None:
            self.fx_service._cache_rate("USD", "CAD", usd_to_cad, today)
            logger.info("FX rate USD->CAD cached: %s", usd_to_cad)
        else:
            logger.error("Failed to fetch FX rate USD->CAD — rate cache not updated")

        cad_to_usd = fetch_fx_rate("CAD", "USD")
        if cad_to_usd is not None and self.fx_service is not None:
            self.fx_service._cache_rate("CAD", "USD", cad_to_usd, today)

    # -------------------------------------------------------------------------
    # Per-Company Process
    # -------------------------------------------------------------------------

    async def _process_company(
        self,
        symbol: str,
        company_id: int,
        security_type: str = "stock",
        exchange: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Steps:
          1) Price history (monthly EOM compression; bootstrap or incremental)
          2) Splits
          --- stock-only below ---
          3) Revenue forecast
          4) Earnings forecast
          5) Company summary snapshot
          5c) IS/BS/CF bootstrap for companies never synced via earnings scheduler
          6) Derived financial ratios (version-gated — only writes when source data changed)
          7) Dividend metrics (exits early if no dividend history exists)

        For ETFs, indices, and funds steps 3-7 are skipped.  Price history and
        splits are the only meaningful datasets for benchmark instruments.
         """
        is_stock = (security_type == "stock")

        if not is_stock:
            logger.debug(
                "[MARKET_DATA] %s security_type=%s — running price+splits only",
                symbol, security_type,
            )

        # 1) PRICE HISTORY — all security types
        price_rows_written = await self._upsert_monthly_price_history(symbol, company_id, exchange=exchange)

        # 2) SPLITS — all security types (ETFs and funds do split)
        split_rows = await self.defeat_beta_provider.get_splits_optimized(symbol, company_id)
        if split_rows:
            await self.financial_repo.upsert_splits(split_rows)

        # 3) REVENUE FORECAST — stocks only
        rev_fcst_rows: List[Dict[str, Any]] = []
        if is_stock:
            rev_fcst_rows = await self.defeat_beta_provider.fetch_revenue_forecast(symbol, company_id)
            if rev_fcst_rows:
                await self.financial_repo.upsert_revenue_forecast(rev_fcst_rows)

        # 4) EARNINGS FORECAST — stocks only
        eps_fcst_rows: List[Dict[str, Any]] = []
        if is_stock:
            eps_fcst_rows = await self.defeat_beta_provider.fetch_earnings_forecast(symbol, company_id)
            if eps_fcst_rows:
                await self.financial_repo.upsert_earnings_forecast(eps_fcst_rows)

        # 5) COMPANY SUMMARY — stocks only
        #    ETF/index market cap and beta are not meaningful in this context and
        #    would pollute company_summary with non-fundamental data.
        summary = None
        if is_stock:
            summary = await self.defeat_beta_provider.get_company_summary_optimized(symbol, company_id)
            if summary:
                await self.financial_repo.upsert_company_summary(summary)

        # 5c) IS/BS/CF bootstrap — stocks only
        #     ETFs/indices have no income statements, balance sheets, or cash flows.
        #
        # The earnings scheduler only runs for companies in the ±N day earnings
        # window. A newly added company outside that window will have empty
        # IS/BS/CF tables. When derived metrics (step 6) runs against empty
        # tables it correctly returns count:0 — but ROIC/ROE/payout are never
        # populated and all suitability scores silently degrade to 9/100.
        #
        # Fix: check for at least one annual income_statement row. If absent,
        # trigger a full financial sync so derived metrics has data to work with.
        try:
            if is_stock and not await self._has_any_financials(company_id):
                logger.info(
                    "[BOOTSTRAP] %s (company_id=%s) has no IS/BS/CF rows — "
                    "triggering full financial sync",
                    symbol, company_id,
                )
                refresh_info = await self.financial_repo.get_company_refresh_info(
                    company_id=company_id
                )
                if refresh_info:
                    financials = await self.defeat_beta_provider.get_all_financials_optimized(
                        symbol=symbol,
                        company_id=company_id,
                        last_refreshed_fiscal_year=None,
                        last_refreshed_fiscal_quarter=None,
                        force_full_history=True,
                        min_fiscal_year=now_utc().year - 5,
                    )
                    if not financials.income_statements.rows:
                        logger.warning(
                            "[BOOTSTRAP] %s: min_fiscal_year=2021 stripped all rows — skipping upsert & metadata",
                            symbol,
                        )
                    else:
                        await self.financial_repo.upsert_all_financials(financials)
                        await self.financial_repo.update_company_refresh_metadata(
                            company_id=company_id,
                            last_fiscal_year=financials.income_statements.rows[-1].fiscal_year,
                            last_fiscal_quarter=None,
                            is_first_load=True,
                            next_earnings_date=financials.next_earnings_date,
                        )
                        logger.info(
                            "[BOOTSTRAP] %s IS/BS/CF bootstrap complete — IS:%d BS:%d CF:%d",
                            symbol,
                            len(financials.income_statements.rows),
                            len(financials.balance_sheets.rows),
                            len(financials.cash_flows.rows),
                        )
        except Exception as bootstrap_exc:
            logger.error(
                "[BOOTSTRAP] Financial bootstrap failed for %s: %s",
                symbol, bootstrap_exc,
            )
            # Non-fatal — steps 6 & 7 still run. If IS/BS/CF are empty, derived
            # metrics will return count:0 and log appropriately.

        # 6) DERIVED FINANCIAL RATIOS — stocks only
        # Version-gated internally: only writes rows whose source data changed.
        # Safe to call unconditionally every cycle.
        ratios_result: Dict[str, Any] = {"rows_changed": 0, "count": 0, "upserted": False}
        if is_stock:
            try:
                ratios_result = await compute_and_upsert_derived_financial_metrics(
                    company_id=company_id
                )
                logger.info(
                    "[RATIOS] %s: %d/%d rows written",
                    symbol,
                    ratios_result.get("rows_changed", 0),
                    ratios_result.get("count", 0),
                )
            except Exception as exc:
                logger.error("[RATIOS] %s failed: %s", symbol, exc)

        # 6b) QUARTERLY HEALTH SCORES — Piotroski F, Altman Z, quarterly ratios
        # Runs after annual ratios to reuse any prior-year annual data for
        # Piotroski YoY deltas. Writes quarterly rows to financial_ratios.
        if is_stock:
            try:
                qh_result = await compute_and_upsert_quarterly_health_scores(
                    company_id=company_id
                )
                if qh_result.get("upserted"):
                    logger.info(
                        "[QHLTH] %s: %d quarterly health rows written",
                        symbol,
                        qh_result.get("rows_changed", 0),
                    )
            except Exception as exc:
                logger.error("[QHLTH] %s failed: %s", symbol, exc)

        # 6c) QUARTERLY VALUATION METRICS — trailing P/E, EV/EBITDA, P/FCF per quarter
        # Pre-computes from income_statements + balance_sheets + cash_flow_statements + price_history.
        # Version-gated: only writes when source data changed.
        vpe_result: Dict[str, Any] = {"rows_changed": 0, "count": 0, "upserted": False}
        if is_stock:
            try:
                vpe_result = await compute_and_upsert_quarterly_valuation_metrics(
                    company_id=company_id
                )
                if vpe_result.get("upserted"):
                    logger.info(
                        "[VPE] %s: %d/%d quarterly valuation-ratio rows written",
                        symbol,
                        vpe_result.get("rows_changed", 0),
                        vpe_result.get("count", 0),
                    )
            except Exception as exc:
                logger.error("[VPE] %s failed: %s", symbol, exc)

        # 7) DIVIDEND METRICS — stocks only
        # Exits early with no DB writes if no dividend_history rows exist.
        # Safe to call unconditionally for every company.
        div_result: Dict[str, Any] = {"rows_changed": 0, "upserted": False}
        if is_stock:
            try:
                div_result = await compute_and_upsert_dividend_metrics(company_id=company_id)
                if div_result.get("upserted"):
                    logger.info(
                        "[DIV_METRICS] %s: %d rows written",
                        symbol,
                        div_result.get("rows_changed", 0),
                    )
            except Exception as exc:
                logger.error("[DIV_METRICS] %s failed: %s", symbol, exc)

        # 7b) UPCOMING DIVIDEND EVENTS — stocks only
        # Fetches forward-looking ex-dates from YFinance + Stockdex,
        # falls back to prediction.  Runs every cycle; upsert is
        # idempotent via UNIQUE(company_id, data_source).
        if is_stock:
            try:
                await refresh_upcoming_dividend(
                    company_id=company_id,
                    symbol=symbol,
                    financial_repo=self.financial_repo,
                )
            except Exception as exc:
                logger.error(
                    "[UPCOMING_DIV] %s (company_id=%s) failed: %s",
                    symbol, company_id, exc,
                )

        # 8) RI VALUATION — stocks only
        if is_stock:
            try:
                from infrastructure.repositories.valuation_repository import ValuationRepository
                from application.services.recompute_guard import RecomputeGuard
                from application.services.valuation_service import ValuationService
                valuation_repo = ValuationRepository()
                vs = ValuationService(repo=valuation_repo, guard=RecomputeGuard(valuation_repo))
                await vs.compute_residual_income_if_stale(symbol=symbol, user_id=None, force=True)
                logger.info("[VALUATION] %s RI valuation complete", symbol)
            except Exception as ve:
                logger.error("[VALUATION] %s failed: %s", symbol, ve)

        return {
            "price_history_monthly": price_rows_written,
            "security_type":         security_type,
            "splits":                len(split_rows or []),
            "revenue_forecast":      len(rev_fcst_rows or []),
            "earnings_forecast":     len(eps_fcst_rows or []),
            "company_summary":       1 if summary else 0,
            "ratios_changed":        ratios_result.get("rows_changed", 0),
            "dividend_metrics":      div_result.get("rows_changed", 0),
            "valuation_pe":          vpe_result.get("rows_changed", 0),
        }

    # -------------------------------------------------------------------------
    # Price History helpers (with rolling retention)
    # -------------------------------------------------------------------------

    async def _upsert_monthly_price_history(self, symbol: str, company_id: int, exchange: Optional[str] = None) -> int:
        """
        Bootstrap path  — no existing rows: fetch full daily history, compress to
                          monthly EOM, upsert all (respects retention window).
        Incremental path — rows exist: fetch last ~lookback_days, recompute EOM
                          for any months in that window, upsert.
        Returns the number of monthly rows attempted for upsert.
        """
        has_any = await self._has_any_price_history(company_id)
        retention_cutoff = self._years_ago(now_utc().date(), self.retention_years)

        await self.financial_repo.update_price_attempt_marker(company_id)

        if not has_any:
            daily_rows = await self.defeat_beta_provider.get_price_history_optimized(symbol, company_id, exchange=exchange)
            daily_rows = [
                r for r in (daily_rows or [])
                if r.get("price_date") and r["price_date"] >= retention_cutoff
            ]
            monthly_rows = self._compress_daily_to_monthly_eom(daily_rows)
            if monthly_rows:
                await self.financial_repo.upsert_price_history(monthly_rows)
                await self.financial_repo.update_price_success_marker(company_id)
                await self.financial_repo.update_price_refresh_marker(company_id)
                logger.info("[PH][%s] Bootstrap monthly rows (>= %s): %d", symbol, retention_cutoff, len(monthly_rows))
            else:
                await self.financial_repo.increment_price_failures(company_id)
            return len(monthly_rows or [])

        lookback = max(self.lookback_days, 40)
        window_cutoff = now_utc().date() - timedelta(days=lookback)
        daily_rows_recent = await self.defeat_beta_provider.get_price_history_optimized(symbol, company_id, exchange=exchange)
        effective_cutoff = max(retention_cutoff, window_cutoff)
        daily_rows_recent = [
            r for r in (daily_rows_recent or [])
            if r.get("price_date") and r["price_date"] >= effective_cutoff
        ]
        monthly_recent = self._compress_daily_to_monthly_eom(daily_rows_recent)
        if monthly_recent:
            await self.financial_repo.upsert_price_history(monthly_recent)
            await self.financial_repo.update_price_success_marker(company_id)
            await self.financial_repo.update_price_refresh_marker(company_id)
            logger.debug("[PH][%s] Incremental monthly rows (>= %s): %d", symbol, effective_cutoff, len(monthly_recent))
        else:
            await self.financial_repo.increment_price_failures(company_id)
        return len(monthly_recent or [])

    async def _has_any_price_history(self, company_id: int) -> bool:
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
            logger.debug("price_history existence check failed for company_id=%s", company_id)
            return False

    async def _has_any_financials(self, company_id: int) -> bool:
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .limit(1)
                .execute()
            )
            return bool(resp.data)
        except Exception:
            logger.debug(
                "income_statements existence check failed for company_id=%s", company_id
            )
            return True

    @staticmethod
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
        df["price_date"] = pd.to_datetime(df["price_date"], utc=True, errors="coerce")
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
                "open_price":  MarketDataRefreshScheduler._safe_num(r.get("open_price")),
                "close_price": MarketDataRefreshScheduler._safe_num(r.get("close_price")),
                "high_price":  MarketDataRefreshScheduler._safe_num(r.get("high_price")),
                "low_price":   MarketDataRefreshScheduler._safe_num(r.get("low_price")),
                "volume":      int(r.get("volume")) if pd.notna(r.get("volume")) else None,
                "data_source": str(r.get("data_source") or "defeatbeta"),
            })
        out.sort(key=lambda x: x["price_date"])
        return out

    @staticmethod
    def _safe_num(v: Any) -> Optional[float]:
        if v is None:
            return None
        try:
            f = float(v)
            return f if f == f else None  # NaN guard
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _years_ago(from_date: date, years: int) -> date:
        """Return a date `years` years before `from_date`, handling Feb 29 safely."""
        try:
            return from_date.replace(year=from_date.year - years)
        except ValueError:
            target_year = from_date.year - years
            return date(target_year, 3, 1) - timedelta(days=1)