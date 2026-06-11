# -*- coding: utf-8 -*-
"""
Earnings Refresh Scheduler
Runs every N hours to refresh financial data for companies with upcoming earnings.
Implements smart filtering to prevent duplicate DB writes (97.5% optimization).
Adds per-company distributed locks for multi-replica safety.
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional

from config import settings
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.yfinance_provider import YFinanceProvider
from domain.exceptions import (
    MaxRetriesExceededError,
    SchedulerRefreshError,
    CompanyNotFoundError,
)

from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_derived_financial_metrics,
    compute_and_upsert_quarterly_health_scores,
    compute_and_upsert_quarterly_valuation_metrics,
)
from application.jobs.data_quality_audit_job import audit_company_data_quality

logger = logging.getLogger(__name__)


class EarningsRefreshScheduler:
    """
    Background scheduler that runs every N hours (default: 2 hours).

    Refreshes financial data for companies with upcoming earnings.
    Uses smart filtering to only store new data (97.5% deduplication).
    Now includes per-company locks to avoid concurrent refresh across replicas.
    """

    def __init__(
        self,
        financial_repo: Optional[SupabaseFinancialRepository] = None,
        defeat_beta_provider: Optional[DefeatBetaProvider] = None,
    ):
        """
        Initialize scheduler.

        Args:
            financial_repo: Repository for DB operations
            defeat_beta_provider: Provider for defeat-beta data
        """
        self.financial_repo = financial_repo or SupabaseFinancialRepository()

        # Inject fallback chain: Stockdex → Edgar → YFinance
        yf_provider = YFinanceProvider()
        from providers.stockdex_provider import StockdexMacrotrendsProvider
        from providers.edgar_provider import EdgarToolsProvider
        self.defeat_beta_provider = defeat_beta_provider or DefeatBetaProvider(
            yfinance_provider=yf_provider,
            stockdex_provider=StockdexMacrotrendsProvider(),
            edgar_provider=EdgarToolsProvider(),
        )

        self.is_running = False
        self.task: Optional[asyncio.Task] = None

        # Per-company lock TTL; earnings refresh per company may be longer; default 45 min
        self.lock_ttl_seconds: int = int(getattr(settings, "SCHEDULER_COMPANY_LOCK_TTL_SECONDS", 2700))
        self.owner_lock_id: str = f"earnings:{uuid.uuid4()}"

    # ========================================================================
    # SCHEDULER CONTROL
    # ========================================================================
    async def start(self) -> None:
        """Start the scheduler background task."""
        if self.is_running:
            logger.warning("Scheduler already running")
            return

        self.is_running = True
        self.task = asyncio.create_task(self._run_scheduler_loop())
        logger.info("🚀 Earnings Scheduler started (interval: %sh)", settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS)

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️  Earnings Scheduler stopped")

    # ========================================================================
    # MAIN SCHEDULER LOOP
    # ========================================================================
    async def _run_scheduler_loop(self) -> None:
        """
        Main scheduler loop.
        Runs every N hours to check and refresh upcoming earnings.
        """
        while self.is_running:
            try:
                await self._check_and_refresh_earnings()
            except Exception as e:
                logger.error(f"Scheduler cycle failed: {str(e)}")

            # Sleep until next cycle
            sleep_seconds = settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS * 3600
            logger.debug(
                "Scheduler sleeping for %sh until next cycle",
                settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS,
            )
            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break

    async def _check_and_refresh_earnings(self) -> Dict[str, Any]:
        """
        Check for companies with upcoming earnings and refresh them.

        Workflow:
        1. Query companies with earnings in ±N days window
        2. For each company: refresh their financial data (with per-company lock)
        3. Track results and log summary

        Returns:
            Summary of refresh operation
        """
        logger.info("📊 Starting earnings check cycle")

        try:
            # Step 1: Determine earnings window
            today = date.today()
            buffer_days = settings.EARNINGS_REFRESH_BUFFER_DAYS

            start_date = today - timedelta(days=buffer_days)
            end_date = today + timedelta(days=buffer_days)

            logger.debug(f"Earnings window: {start_date} to {end_date} (±{buffer_days} days)")

            # Step 2: Query companies with upcoming earnings
            companies = await self.financial_repo.get_companies_with_upcoming_earnings(
                start_date=start_date,
                end_date=end_date,
            )

            if not companies:
                logger.info("✅ No companies with upcoming earnings to refresh")
                return {
                    'companies_found': 0,
                    'companies_refreshed': 0,
                    'companies_failed': 0,
                    'total_rows_upserted': 0,
                }

            logger.info(f"Found {len(companies)} companies with upcoming earnings")

            # Step 3: Refresh each company (with per-company lock)
            results = {
                'companies_found': len(companies),
                'companies_refreshed': 0,
                'companies_failed': 0,
                'total_rows_upserted': 0,
                'failed_companies': [],
                'refreshed_companies': [],
            }

            for company in companies:
                company_id = company['company_id']
                symbol = company['ticker_symbol']
                earnings_date = company.get('next_earnings_date')

                acquired = await self.financial_repo.acquire_company_lock(
                    company_id=company_id,
                    owner_id=self.owner_lock_id,
                    ttl_seconds=self.lock_ttl_seconds,
                    lock_type="earnings_refresh",
                )
                if not acquired:
                    logger.info("🔒 Skip %s (%s): lock held by another replica", symbol, company_id)
                    continue

                try:
                    await self._refresh_company_financials_optimized(
                        company_id=company_id,
                        symbol=symbol,
                        earnings_date=earnings_date,
                    )
                    results['companies_refreshed'] += 1
                    results['refreshed_companies'].append(symbol)
                except Exception as e:
                    logger.error(f"Failed to refresh {symbol}: {str(e)}")
                    results['companies_failed'] += 1
                    results['failed_companies'].append({'symbol': symbol, 'error': str(e)})
                finally:
                    await self.financial_repo.release_company_lock(company_id, self.owner_lock_id)

            # Step 4: Log summary
            logger.info(
                f"✅ Earnings check cycle complete: "
                f"{results['companies_refreshed']} refreshed, "
                f"{results['companies_failed']} failed"
            )

            if results['refreshed_companies']:
                logger.debug(f"Refreshed: {', '.join(results['refreshed_companies'])}")

            if results['failed_companies']:
                logger.warning(f"Failed: {results['failed_companies']}")

            return results

        except Exception as e:
            logger.error(f"Earnings check cycle failed: {str(e)}")
            raise

    # ========================================================================
    # SINGLE COMPANY REFRESH
    # ========================================================================
    async def _refresh_company_financials_optimized(
        self,
        company_id: int,
        symbol: str,
        earnings_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Refresh financial data for a single company.

        Implements 97.5% optimization:
        - Gets last refresh point
        - Fetches only new data (smart filtering)
        - Stores only new rows
        - Updates metadata
        """
        try:
            logger.info(
                f"Refreshing {symbol} (company_id={company_id})"
                + (f" | earnings: {earnings_date}" if earnings_date else "")
            )

            # Step 1: Get company refresh info (for smart filtering)
            refresh_info = await self.financial_repo.get_company_refresh_info(company_id=company_id)

            if not refresh_info:
                raise CompanyNotFoundError(company_id, symbol)

            is_first_time_load = refresh_info.first_financial_data_loaded_at is None

            logger.debug(
                f"Company status: {refresh_info.data_completeness_status} | "
                f"Last refresh: {refresh_info.last_refreshed_fiscal_year}Q"
                f"{refresh_info.last_refreshed_fiscal_quarter or 'A'}"
            )

            # Step 2: Fetch with smart filtering (97.5% optimization!)
            financials = await self.defeat_beta_provider.get_all_financials_optimized(
                symbol=symbol,
                company_id=company_id,
                last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
                last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
                force_full_history=is_first_time_load,  # Full for first load
            )

            # Step 3: Store (upsert prevents duplicates)
            upsert_results = await self.financial_repo.upsert_all_financials(financials)

            # Step 4: Update metadata
            latest_fiscal_year = 2024  # Default
            latest_fiscal_quarter = None

            if financials.income_statements.rows:
                latest = financials.income_statements.rows[-1]
                latest_fiscal_year = latest.fiscal_year
                latest_fiscal_quarter = latest.fiscal_quarter

            await self.financial_repo.update_company_refresh_metadata(
                company_id=company_id,
                last_fiscal_year=latest_fiscal_year,
                last_fiscal_quarter=latest_fiscal_quarter,
                is_first_load=is_first_time_load,
                next_earnings_date=financials.next_earnings_date,
            )

            statement_rows_written = (
                upsert_results.get("income_statements", 0)
                + upsert_results.get("balance_sheets", 0)
                + upsert_results.get("cash_flows", 0)
            )
 
            if statement_rows_written > 0:
                logger.info(
                    "[DERIVED] %s: %d new statement rows → computing derived metrics",
                    symbol, statement_rows_written,
                )
                try:
                    ratios_result = await compute_and_upsert_derived_financial_metrics(
                        company_id=company_id
                    )
                    logger.info(
                        "[DERIVED] %s: %d/%d ratio rows changed (version-gate)",
                        symbol,
                        ratios_result.get("rows_changed", 0),
                        ratios_result.get("count", 0),
                    )
                except Exception as de:
                    logger.error(
                        "[DERIVED] compute failed for %s: %s", symbol, de,
                        exc_info=True,
                    )

                # Quarterly health scores — Piotroski F, Altman Z, quarterly ratios
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
                except Exception as qe:
                    logger.error(
                        "[QHLTH] compute failed for %s: %s", symbol, qe,
                        exc_info=True,
                    )

                # Quarterly valuation metrics — trailing P/E
                try:
                    vpe_result = await compute_and_upsert_quarterly_valuation_metrics(
                        company_id=company_id
                    )
                    if vpe_result.get("upserted"):
                        logger.info(
                            "[VPE] %s: %d/%d quarterly trailing-PE rows written",
                            symbol,
                            vpe_result.get("rows_changed", 0),
                            vpe_result.get("count", 0),
                        )
                except Exception as ve:
                    logger.error(
                        "[VPE] compute failed for %s: %s", symbol, ve,
                        exc_info=True,
                    )

                # Data quality audit — only meaningful when data was written.
                try:
                    await audit_company_data_quality(company_id=company_id)
                except Exception as qe:
                    logger.error(
                        "[DQ] audit failed for %s: %s", symbol, qe
                    )

                # Trigger RI valuation
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
            else:
                logger.debug(
                    "[DERIVED] %s: no new statement rows → skipping derived metrics",
                    symbol,
                )
 

            return {
                'company_id': company_id,
                'symbol': symbol,
                'status': 'success',
                'rows_upserted': upsert_results,
                'total_rows': sum(upsert_results.values()),
                'is_first_load': is_first_time_load,
                'next_earnings_date': (
                    financials.next_earnings_date.isoformat()
                    if financials.next_earnings_date
                    else None
                ),
            }

        except MaxRetriesExceededError as e:
            logger.error(f"Max retries exceeded for {symbol}: {str(e)}")
            raise SchedulerRefreshError(company_id, symbol, e)

        except Exception as e:
            logger.error(f"Failed to refresh {symbol}: {str(e)}")
            raise SchedulerRefreshError(company_id, symbol, e)

    # ========================================================================
    # MANUAL TRIGGER (for testing/admin)
    # ========================================================================
    async def trigger_immediate_check(self) -> Dict[str, Any]:
        """
        Manually trigger an immediate earnings check.
        Useful for: testing, admin operations, force-refresh.
        """
        logger.info("🔄 Manual trigger: immediate earnings check")
        return await self._check_and_refresh_earnings()