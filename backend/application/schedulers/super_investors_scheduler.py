# -*- coding: utf-8 -*-
"""
Super Investors Refresh Scheduler
Runs every N hours to refresh 13F filings for tracked super investors.
Smart fetching: 20 quarters on first run, then only new filings when due.
"""

import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Dict, Any, Optional, List

from config import settings
from application.services.super_investors_service import SuperInvestorsService, SUPER_INVESTORS

logger = logging.getLogger(__name__)


class SuperInvestorsRefreshScheduler:
    """
    Background scheduler that runs every N hours (default: 24 hours).

    Smart fetching logic:
    - First run: fetch last 20 quarters of history (configurable)
    - Subsequent runs: only fetch new filings if past due date
    - Continue on individual errors, alert if ALL fail (potential bug)
    """

    def __init__(self, service: Optional[SuperInvestorsService] = None):
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository

        self.service = service or SuperInvestorsService()
        self.financial_repo = SupabaseFinancialRepository()
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.owner_lock_id = f"super_investors:{uuid.uuid4()}"
        self.lock_ttl_seconds = 3600  # 1 hour lock

    @property
    def interval_hours(self) -> int:
        return getattr(settings, "SUPER_INVESTORS_REFRESH_INTERVAL_HOURS", 24)

    @property
    def initial_quarters(self) -> int:
        return getattr(settings, "SUPER_INVESTORS_INITIAL_QUARTERS", 20)

    @property
    def grace_days(self) -> int:
        return getattr(settings, "SUPER_INVESTORS_GRACE_DAYS", 49)

    # ========================================================================
    # SCHEDULER CONTROL
    # ========================================================================
    async def start(self) -> None:
        if self.is_running:
            logger.warning("SuperInvestorsScheduler already running")
            return
        self.is_running = True
        self.task = asyncio.create_task(self._run_loop())
        logger.info("🚀 Super Investors Scheduler started (interval: %sh)", self.interval_hours)

    async def stop(self) -> None:
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️  Super Investors Scheduler stopped")

    # ========================================================================
    # MAIN LOOP
    # ========================================================================
    async def _run_loop(self) -> None:
        while self.is_running:
            try:
                await self._refresh_all_investors()
            except Exception as e:
                logger.error(f"Scheduler cycle failed: {e}")

            sleep_seconds = self.interval_hours * 3600
            logger.debug("Scheduler sleeping for %sh", self.interval_hours)
            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break

    # ========================================================================
    # CORE LOGIC
    # ========================================================================
    async def _refresh_all_investors(self) -> Dict[str, Any]:
        """Main refresh logic for all super investors."""
        logger.info("📊 Starting Super Investors refresh cycle")

        results = {
            "investors_found": len(SUPER_INVESTORS),
            "refreshed": 0,
            "skipped": 0,
            "errors": 0,
            "all_failed": False,
        }

        for cik, info in SUPER_INVESTORS.items():
            try:
                refreshed = await self._refresh_single_investor(cik, info)
                if refreshed:
                    results["refreshed"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                logger.error(f"Error refreshing {info['name']}: {e}")
                results["errors"] += 1

        # Check if ALL failed - potential bug
        if results["errors"] == results["investors_found"] and results["investors_found"] > 0:
            results["all_failed"] = True
            logger.error(
                "⚠️  ALL super investors failed to refresh - possible bug, needs investigation"
            )

        logger.info(f"Cycle complete: {results}")
        return results

    async def _refresh_single_investor(self, cik: str, info: Dict) -> bool:
        """
        Refresh single investor's holdings.

        Returns True if new data was fetched, False if skipped (not due yet).
        """
        investor_name = info["name"]

        # Get last filed period from DB
        result = self.financial_repo.client.table("institutional_investors").select(
            "investor_id, last_filed_period, last_filed_date"
        ).eq("cik", cik).execute()

        if not result.data or not result.data[0].get("investor_id"):
            # First run - create investor record and fetch historical data
            await self._create_investor_record(cik, info)
            fetched = await self._fetch_historical_data(cik, info, self.initial_quarters)
            return fetched

        last_period = result.data[0].get("last_filed_period")
        last_date = result.data[0].get("last_filed_date")

        # Check if new filing is due
        if last_period:
            next_due = self._calculate_next_due_date(last_period)
            if datetime.now().date() < next_due:
                logger.debug(
                    f"Skipping {investor_name}: not due until {next_due}"
                )
                return False

        # Fetch new filing
        fetched = await self._fetch_new_filing(cik, info, last_period)
        return fetched

    async def _create_investor_record(self, cik: str, info: Dict) -> None:
        """Create new investor record in DB."""
        insert_data = {
            "cik": cik,
            "investor_name": info["name"],
            "firm_name": info["firm"],
            "investor_tag": info["tag"],
            "investment_style": info.get("style", ""),
            "is_super_investor": True,
            "is_active": True,
        }
        self.financial_repo.client.table("institutional_investors").insert(
            insert_data
        ).execute()
        logger.info(f"Created investor record: {info['name']}")

    async def _fetch_historical_data(
        self, cik: str, info: Dict, quarters: int
    ) -> bool:
        """Fetch historical data (20 quarters on first run)."""
        from edgar import get_filings

        investor_name = info["name"]
        logger.info(f"First run for {investor_name}: fetching {quarters} quarters")

        try:
            filings = get_filings(form="13F-HR").filter(cik=cik)
            if not filings or len(filings) == 0:
                logger.warning(f"No filings found for {investor_name}")
                return False

            # Get all available filings (up to quarters limit)
            filing_list = list(filings)
            num_to_fetch = min(quarters, len(filing_list))

            logger.info(
                f"Fetching {num_to_fetch} historical filings for {investor_name}"
            )

            latest_period = None
            latest_date = None

            for i in range(num_to_fetch):
                try:
                    filing = filing_list[i]
                    thirteenf = filing.obj()

                    if not thirteenf:
                        continue

                    period = str(thirteenf.report_period)
                    filing_date = str(filing.filing_date)

                    # Save holdings to DB
                    holdings_df = thirteenf.holdings
                    if holdings_df is not None and not holdings_df.empty:
                        await self._save_holdings_to_db(
                            cik, info, holdings_df, period, filing_date
                        )

                    # Track latest
                    if not latest_period or (
                        period and period > latest_period
                    ):
                        latest_period = period
                        latest_date = filing_date

                except Exception as e:
                    logger.error(
                        f"Error processing filing {i} for {investor_name}: {e}"
                    )
                    continue

            # Update last_filed_period/date
            if latest_period:
                await self._update_investor_tracking(cik, latest_period, latest_date)

            return True

        except Exception as e:
            logger.error(f"Error fetching historical data for {investor_name}: {e}")
            return False

    async def _fetch_new_filing(
        self, cik: str, info: Dict, last_period: Optional[date]
    ) -> bool:
        """Fetch single new filing (only if newer than last_period)."""
        from edgar import get_filings

        investor_name = info["name"]

        try:
            filings = get_filings(form="13F-HR").filter(cik=cik)
            if not filings or len(filings) == 0:
                logger.warning(f"No filings found for {investor_name}")
                return False

            # Get latest filing
            filing = filings[0]
            thirteenf = filing.obj()

            if not thirteenf:
                return False

            period = str(thirteenf.report_period)
            filing_date = str(filing.filing_date)

            # Validate new period > last_period
            if last_period and period and period <= last_period:
                logger.debug(
                    f"No new filing for {investor_name}: period {period} <= last {last_period}"
                )
                return False

            logger.info(f"New filing for {investor_name}: {period}")

            # Save holdings to DB
            holdings_df = thirteenf.holdings
            if holdings_df is not None and not holdings_df.empty:
                await self._save_holdings_to_db(
                    cik, info, holdings_df, period, filing_date
                )

            # Update tracking
            await self._update_investor_tracking(cik, period, filing_date)

            return True

        except Exception as e:
            logger.error(f"Error fetching new filing for {investor_name}: {e}")
            return False

    async def _save_holdings_to_db(
        self,
        cik: str,
        info: Dict,
        holdings_df,
        period: date,
        filing_date: str,
    ) -> None:
        """Save holdings to institutional_holdings table."""
        from database import supabase

        # Get investor_id
        inv_result = supabase.table("institutional_investors").select(
            "investor_id"
        ).eq("cik", cik).execute()

        if not inv_result.data:
            logger.warning(f"No investor_id found for CIK {cik}")
            return

        investor_id = inv_result.data[0]["investor_id"]

        # Calculate total portfolio value for weight
        total_value = holdings_df["Value"].sum() * 1000  # Values in thousands

        # Process each holding (store all, not just specific ticker)
        for _, row in holdings_df.iterrows():
            ticker = row.get("Ticker")
            if not ticker:
                continue

            # Get company_id from ticker
            company_result = supabase.table("companies").select(
                "company_id"
            ).eq("ticker_symbol", ticker).execute()

            if not company_result.data:
                continue

            company_id = company_result.data[0]["company_id"]

            shares = row.get("SharesPrnAmount", 0) or 0
            value = row.get("Value", 0) or 0  # Already in thousands per 13F
            weight = (value / total_value) if total_value > 0 else 0

            # Check if holding exists
            existing = supabase.table("institutional_holdings").select(
                "holding_id"
            ).eq("investor_id", investor_id).eq(
                "company_id", company_id
            ).eq("quarter_end_date", str(period)).execute()

            insert_data = {
                "investor_id": investor_id,
                "company_id": company_id,
                "quarter_end_date": str(period),
                "filing_date": filing_date,
                "shares_held": int(shares),
                "position_value": float(value),
                "portfolio_weight": float(weight),
                "data_source": "edgar",
            }

            if existing.data and len(existing.data) > 0:
                supabase.table("institutional_holdings").update(insert_data).eq(
                    "holding_id", existing.data[0]["holding_id"]
                ).execute()
            else:
                supabase.table("institutional_holdings").insert(insert_data).execute()

    async def _update_investor_tracking(
        self, cik: str, period: date, filing_date: str
    ) -> None:
        """Update last_filed_period and last_filed_date."""
        update_data = {
            "last_filed_date": filing_date,
        }

        # last_filed_period needs to be stored as date
        if period:
            if isinstance(period, str):
                update_data["last_filed_period"] = period
            else:
                update_data["last_filed_period"] = str(period)

        self.financial_repo.client.table("institutional_investors").update(
            update_data
        ).eq("cik", cik).execute()

    def _calculate_next_due_date(self, last_period: date) -> date:
        """Calculate next filing due date (quarter end + 49 days grace)."""
        if isinstance(last_period, str):
            last_period = datetime.strptime(last_period, "%Y-%m-%d").date()

        # Next quarter is 6 months after last
        month = last_period.month
        year = last_period.year

        if month <= 3:
            next_month = 6
            next_year = year
        elif month <= 6:
            next_month = 9
            next_year = year
        elif month <= 9:
            next_month = 12
            next_year = year
        else:
            next_month = 3
            next_year = year + 1

        # Due date = quarter end + grace days
        quarter_end = date(next_year, next_month, 30)
        next_due = quarter_end + timedelta(days=self.grace_days)

        return next_due