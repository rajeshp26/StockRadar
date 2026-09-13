"""
Super Investors Refresh Scheduler
Runs every N hours to refresh 13F filings for tracked super investors.
Smart fetching: 20 quarters on first run, then only new filings when due.
"""

import asyncio
import logging
import uuid
from datetime import date, timedelta
from typing import Any

from application.services.super_investors_service import SUPER_INVESTORS, SuperInvestorsService
from config import settings
from shared.time_utils import now_utc, parse_db_timestamp

logger = logging.getLogger(__name__)


class SuperInvestorsRefreshScheduler:
    """
    Background scheduler that runs every N hours (default: 24 hours).

    Smart fetching logic:
    - First run: fetch last 20 quarters of history (configurable)
    - Subsequent runs: only fetch new filings if past due date
    - Continue on individual errors, alert if ALL fail (potential bug)
    """

    def __init__(self, service: SuperInvestorsService | None = None):
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository

        self.service = service or SuperInvestorsService()
        self.financial_repo = SupabaseFinancialRepository()
        self.is_running = False
        self.task: asyncio.Task | None = None
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

    @staticmethod
    def _ensure_edgar_identity() -> None:
        """
        Defensively ensure EDGAR identity/User-Agent is set before any fetch.

        Mirrors SuperInvestorsService._ensure_edgar_identity so standalone
        scheduler runs (outside the service) never hit an IdentityNotSet
        rejection from the SEC endpoint.
        """
        try:
            from edgar import set_identity
        except ImportError:
            logger.warning("edgar package unavailable; skipping EDGAR identity setup")
            return
        identity = getattr(settings, "EDGAR_IDENTITY", "stockerpro@example.com")
        try:
            set_identity(identity)
        except Exception as exc:  # pragma: no cover - environment dependent
            logger.warning("Could not set EDGAR identity: %s", exc)

    # ========================================================================
    # SCHEDULER CONTROL
    # ========================================================================
    async def plan(self) -> list:
        """
        v3 planner integration — returns job dicts for each investor due.
        Only enqueues investors whose last filing is past the due date,
        or who have never been filed (new investors).
        """
        jobs = []
        today = now_utc().date()

        # Fetch all existing investor records
        try:
            existing_resp = self.financial_repo.client.table("institutional_investors").select(
                "cik, last_filed_period"
            ).eq("is_super_investor", True).execute()
            existing = {r["cik"]: r for r in (existing_resp.data or [])}
        except Exception:
            existing = {}

        for cik, info in SUPER_INVESTORS.items():
            record = existing.get(cik)
            if record and record.get("last_filed_period"):
                try:
                    lfp = record["last_filed_period"]
                    if isinstance(lfp, str):
                        lfp = parse_db_timestamp(lfp).date()
                    next_due = self._calculate_next_due_date(lfp)
                    if today < next_due:
                        continue
                except Exception:
                    pass

            jobs.append({
                "job_type": "investor_refresh",
                "dedupe_key": f"investor_refresh:{cik}",
                "resource_type": "investor",
                "resource_id": cik,
                "payload": {"cik": cik, "name": info.get("name"), "firm": info.get("firm"), "tag": info.get("tag")},
                "priority": 50,
                "max_attempts": 3,
            })
        return jobs

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
    async def _refresh_all_investors(self) -> dict[str, Any]:
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

        if results["refreshed"] > 0:
            from application.services.super_investors_cache import invalidate_super_investors_cache
            invalidate_super_investors_cache()

        logger.info(f"Cycle complete: {results}")
        return results

    async def _refresh_single_investor(self, cik: str, info: dict) -> bool:
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
            if now_utc().date() < next_due:
                logger.debug(
                    f"Skipping {investor_name}: not due until {next_due}"
                )
                return False

        # Fetch new filing
        fetched = await self._fetch_new_filing(cik, info, last_period)
        return fetched

    async def _create_investor_record(self, cik: str, info: dict) -> None:
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
        self, cik: str, info: dict, quarters: int
    ) -> bool:
        """Fetch historical data (20 quarters on first run)."""
        self._ensure_edgar_identity()
        from edgar import get_filings

        investor_name = info["name"]
        logger.info(f"First run for {investor_name}: fetching {quarters} quarters")

        try:
            # Fetch filings by year (SEC API requires year filter for historical data)
            all_filings = []
            current_year = now_utc().year
            years_to_fetch = list(range(current_year - 5, current_year + 1))

            for year in years_to_fetch:
                try:
                    filings = get_filings(year=year, form="13F-HR").filter(cik=cik)
                    if filings:
                        all_filings.extend(list(filings))
                except Exception:
                    continue

            if not all_filings:
                logger.warning(f"No filings found for {investor_name}")
                return False

            # Sort by filing date descending and take required number
            all_filings.sort(key=lambda x: x.filing_date, reverse=True)
            num_to_fetch = min(quarters, len(all_filings))

            logger.info(
                f"Found {len(all_filings)} total filings, fetching {num_to_fetch} for {investor_name}"
            )

            latest_period = None
            latest_date = None
            any_saved = False

            for i in range(num_to_fetch):
                try:
                    filing = all_filings[i]
                    thirteenf = filing.obj()

                    if not thirteenf:
                        continue

                    period = self._normalize_period(thirteenf.report_period)
                    filing_date = str(filing.filing_date)

                    # Save holdings to DB
                    holdings_df = thirteenf.holdings
                    if holdings_df is not None and not holdings_df.empty:
                        total_val = float(thirteenf.total_value) if thirteenf.total_value else None
                        saved_count = await self._save_holdings_to_db(
                            cik, info, holdings_df, period, filing_date, total_value_dollars=total_val
                        )
                        # Only advance tracking to periods that actually persisted rows
                        if saved_count > 0:
                            any_saved = True
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

            # Update last_filed_period/date only to the latest period with
            # persisted rows; never advance tracking on an empty save.
            if latest_period:
                await self._update_investor_tracking(cik, latest_period, latest_date)

            if not any_saved:
                logger.warning(f"No holdings saved for {investor_name} historical fetch")
                return False

            return True

        except Exception as e:
            logger.error(f"Error fetching historical data for {investor_name}: {e}")
            return False

    async def _fetch_new_filing(
        self, cik: str, info: dict, last_period: date | None
    ) -> bool:
        """Fetch single new filing (only if newer than last_period)."""
        self._ensure_edgar_identity()
        from edgar import get_filings

        investor_name = info["name"]

        try:
            # SEC requires a year filter; query the current year first, then
            # fall back to the previous year (e.g. before the first Q1 filing
            # of a year has been submitted).
            filings = None
            current_year = now_utc().year
            for year in (current_year, current_year - 1):
                try:
                    filings = get_filings(year=year, form="13F-HR").filter(cik=cik)
                except Exception:
                    filings = None
                if filings and len(filings) > 0:
                    break

            if not filings or len(filings) == 0:
                logger.warning(f"No filings found for {investor_name}")
                return False

            # Get latest filing
            filing = filings[0]
            thirteenf = filing.obj()

            if not thirteenf:
                return False

            period = self._normalize_period(thirteenf.report_period)
            filing_date = str(filing.filing_date)
            last_period_norm = self._normalize_period(last_period)

            # Validate new period > last_period. If the tracked period itself
            # has no holdings rows (tracking was advanced without persisting,
            # a historical bug), self-heal by re-processing that period.
            if last_period_norm and period and period <= last_period_norm:
                if period == last_period_norm and not await self._holdings_exist_for_period(
                    cik, period
                ):
                    logger.warning(
                        f"Self-healing {investor_name}: tracked period {last_period_norm} "
                        f"has no holdings rows; re-processing {period}"
                    )
                else:
                    logger.debug(
                        f"No new filing for {investor_name}: period {period} <= last {last_period_norm}"
                    )
                    return False

            logger.info(f"New filing for {investor_name}: {period}")

            # Save holdings to DB
            saved_count = 0
            holdings_df = thirteenf.holdings
            if holdings_df is not None and not holdings_df.empty:
                total_val = float(thirteenf.total_value) if thirteenf.total_value else None
                saved_count = await self._save_holdings_to_db(
                    cik, info, holdings_df, period, filing_date, total_value_dollars=total_val
                )

            # Only advance tracking when rows were actually persisted
            if saved_count == 0:
                logger.warning(
                    f"No holdings saved for {investor_name} filing {period}; not advancing tracking"
                )
                return False

            # Update tracking
            await self._update_investor_tracking(cik, period, filing_date)

            return True

        except Exception as e:
            logger.error(f"Error fetching new filing for {investor_name}: {e}")
            return False

    async def _holdings_exist_for_period(self, cik: str, period: str) -> bool:
        """Return True if any institutional_holdings row exists for investor+period."""
        from database import supabase

        inv_result = (
            supabase.table("institutional_investors")
            .select("investor_id")
            .eq("cik", cik)
            .limit(1)
            .execute()
        )
        if not inv_result.data:
            return False

        investor_id = inv_result.data[0]["investor_id"]

        h_result = (
            supabase.table("institutional_holdings")
            .select("holding_id")
            .eq("investor_id", investor_id)
            .eq("quarter_end_date", period)
            .limit(1)
            .execute()
        )
        return bool(h_result.data)

    @staticmethod
    def _normalize_period(value) -> str | None:
        """Normalize a report period to an ISO 'YYYY-MM-DD' string (or None)."""
        if value is None:
            return None
        if hasattr(value, "date") and hasattr(value, "hour"):
            value = value.date()  # datetime / Timestamp -> date
        text = str(value).strip()
        if not text:
            return None
        return text.split(" ")[0][:10]

    async def _save_holdings_to_db(
        self,
        cik: str,
        info: dict,
        holdings_df,
        period: str,
        filing_date: str,
        total_value_dollars: float = None,
    ) -> int:
        """Save holdings to institutional_holdings table; returns rows saved."""
        from database import supabase

        # Get investor_id
        inv_result = supabase.table("institutional_investors").select(
            "investor_id"
        ).eq("cik", cik).execute()

        if not inv_result.data:
            logger.warning(f"No investor_id found for CIK {cik}")
            return 0

        investor_id = inv_result.data[0]["investor_id"]

        # edgar library returns Value in ACTUAL DOLLARS (not thousands)
        # Use provided total_value or sum holdings
        if total_value_dollars is not None:
            total_value = total_value_dollars
        else:
            total_value = float(holdings_df["Value"].sum())

        saved_count = 0

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

            shares = int(row.get("SharesPrnAmount", 0) or 0)
            value_dollars = float(row.get("Value", 0) or 0)  # edgar returns in actual dollars
            weight = (value_dollars / total_value) if total_value > 0 else 0

            # Look up the most recent prior quarter row for this
            # (investor_id, company_id) pair so we can store the delta.
            prev_result = (
                supabase.table("institutional_holdings")
                .select("shares_held, quarter_end_date")
                .eq("investor_id", investor_id)
                .eq("company_id", company_id)
                .lt("quarter_end_date", str(period))   # strictly before current
                .order("quarter_end_date", desc=True)
                .limit(1)
                .execute()
            )
            prev_row = prev_result.data[0] if prev_result.data else None
            prev_shares = int(prev_row["shares_held"]) if prev_row else None

            if prev_shares is None:
                shares_change = 0
                shares_change_pct = 0.0
                change_type = "new"
            else:
                shares_change = shares - prev_shares
                shares_change_pct = (
                    round((shares_change / prev_shares) * 100, 4)
                    if prev_shares != 0 else 0.0
                )
                abs_pct = abs(shares_change_pct)
                if abs_pct < 1.0:
                    change_type = "held"
                elif shares_change > 0:
                    change_type = "increased"
                else:
                    change_type = "decreased"

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
                "position_value": (value_dollars),  # Fixed: now in dollars
                "portfolio_weight": float(weight),
                "shares_change": shares_change,
                "shares_change_pct": shares_change_pct,
                "change_type": change_type,
                "data_source": "edgar",
            }

            if existing.data and len(existing.data) > 0:
                supabase.table("institutional_holdings").update(insert_data).eq(
                    "holding_id", existing.data[0]["holding_id"]
                ).execute()
                saved_count += 1
            else:
                supabase.table("institutional_holdings").insert(insert_data).execute()
                saved_count += 1

        logger.info(f"Saved {saved_count} holdings for {info['name']} period {period}")
        return saved_count

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
            last_period = parse_db_timestamp(last_period).date()

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
