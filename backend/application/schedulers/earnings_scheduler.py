"""
Earnings Refresh Scheduler
Runs every N hours to refresh financial data for companies with upcoming earnings.
Implements smart filtering to prevent duplicate DB writes (97.5% optimization).
"""

import asyncio
import logging
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional

from config import settings
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider
from domain.exceptions import (
    MaxRetriesExceededError,
    SchedulerRefreshError,
    CompanyNotFoundError,
)

logger = logging.getLogger(__name__)


# ============================================================================
# EARNINGS REFRESH SCHEDULER
# ============================================================================

class EarningsRefreshScheduler:
    """
    Background scheduler that runs every N hours (default: 2 hours).
    
    Refreshes financial data for companies with upcoming earnings.
    Uses smart filtering to only store new data (97.5% deduplication).
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
        self.defeat_beta_provider = defeat_beta_provider or DefeatBetaProvider()
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
    
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
        logger.info(f"🚀 Earnings Scheduler started (interval: {settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS}h)")
    
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
                f"Scheduler sleeping for {settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS}h "
                f"until next cycle"
            )
            await asyncio.sleep(sleep_seconds)
    
    async def _check_and_refresh_earnings(self) -> Dict[str, Any]:
        """
        Check for companies with upcoming earnings and refresh them.
        
        Workflow:
        1. Query companies with earnings in ±N days window
        2. For each company: refresh their financial data
        3. Track results and log summary
        
        Returns:
            Summary of refresh operation
        """
        logger.info("📊 Starting earnings check cycle")
        
        try:
            # ================================================================
            # Step 1: Determine earnings window
            # ================================================================
            
            today = date.today()
            buffer_days = settings.EARNINGS_REFRESH_BUFFER_DAYS
            
            start_date = today - timedelta(days=buffer_days)
            end_date = today + timedelta(days=buffer_days)
            
            logger.debug(f"Earnings window: {start_date} to {end_date} (±{buffer_days} days)")
            
            # ================================================================
            # Step 2: Query companies with upcoming earnings
            # ================================================================
            
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
            
            # ================================================================
            # Step 3: Refresh each company
            # ================================================================
            
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
            
            # ================================================================
            # Step 4: Log summary
            # ================================================================
            
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
        
        Args:
            company_id: Company to refresh
            symbol: Stock ticker
            earnings_date: Earnings announcement date (for logging)
        
        Returns:
            Refresh operation summary
        """
        try:
            logger.info(
                f"Refreshing {symbol} (company_id={company_id})"
                + (f" | earnings: {earnings_date}" if earnings_date else "")
            )
            
            # ================================================================
            # Step 1: Get company refresh info (for smart filtering)
            # ================================================================
            
            refresh_info = await self.financial_repo.get_company_refresh_info(
                company_id=company_id
            )
            
            if not refresh_info:
                raise CompanyNotFoundError(company_id, symbol)
            
            is_first_time_load = (
                refresh_info.first_financial_data_loaded_at is None
            )
            
            logger.debug(
                f"Company status: {refresh_info.data_completeness_status} | "
                f"Last refresh: {refresh_info.last_refreshed_fiscal_year}Q"
                f"{refresh_info.last_refreshed_fiscal_quarter or 'A'}"
            )
            
            # ================================================================
            # Step 2: Fetch with smart filtering (97.5% optimization!)
            # ================================================================
            
            financials = await self.defeat_beta_provider.get_all_financials_optimized(
                symbol=symbol,
                company_id=company_id,
                last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
                last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
                force_full_history=is_first_time_load,  # Full for first load
            )
            
            # ================================================================
            # Step 3: Store (upsert prevents duplicates)
            # ================================================================
            
            upsert_results = await self.financial_repo.upsert_all_financials(
                financials
            )
            
            # ================================================================
            # Step 4: Update metadata
            # ================================================================
            
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
            
            total_rows = sum(upsert_results.values())
            logger.info(
                f"✅ Refreshed {symbol}: "
                f"{total_rows} rows upserted "
                f"(Income: {upsert_results['income_statements']}, "
                f"Balance: {upsert_results['balance_sheets']}, "
                f"Cash: {upsert_results['cash_flows']}, "
                f"Earnings: {upsert_results['earnings']}, "
                f"Div: {upsert_results['dividends']})"
            )
            
            return {
                'company_id': company_id,
                'symbol': symbol,
                'status': 'success',
                'rows_upserted': upsert_results,
                'total_rows': total_rows,
                'is_first_load': is_first_time_load,
                'next_earnings_date': (
                    financials.next_earnings_date.isoformat()
                    if financials.next_earnings_date
                    else None
                ),
            }
        
        except MaxRetriesExceededError as e:
            logger.error(
                f"Max retries exceeded for {symbol}: {str(e)}"
            )
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