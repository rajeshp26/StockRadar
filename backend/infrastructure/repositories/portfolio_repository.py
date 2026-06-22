# backend/infrastructure/repositories/portfolio_repository.py
"""
Portfolio Repository

Handles all portfolio database operations following the existing repository pattern.
No business logic — pure data access layer that delegates to Supabase.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import date, datetime

from shared.time_utils import now_utc, now_iso, parse_db_timestamp

# Exchange code → market group mapping for holdings enrichment
EXCHANGE_MARKET_MAP: Dict[str, str] = {
    "NMS": "US", "NASDAQ": "US", "NYSE": "US", "NYSEARCA": "US",
    "NASDAQCM": "US", "BATS": "US", "IEX": "US", "AMEX": "US",
    "NYSEAMERICAN": "US", "NASDAQNM": "US", "NASDAQSC": "US",
    "TSX": "CA", "TSXV": "CA", "TOR": "CA", "TO": "CA", "VAN": "CA",
    "V": "CA", "CNQ": "CA", "NEO": "CA",
    "LSE": "INTL", "FRA": "INTL", "ETR": "INTL", "TSE": "INTL",
    "HKEX": "INTL", "MIL": "INTL", "SWX": "INTL", "ASX": "INTL",
    "SGX": "INTL", "STO": "INTL", "CPH": "INTL", "HEL": "INTL",
    "OSL": "INTL", "BCBA": "INTL", "MCX": "INTL", "BSE": "INTL",
    "NSE": "INTL", "KRX": "INTL", "SSE": "INTL", "SZSE": "INTL",
    "TWSE": "INTL", "SET": "INTL", "IDX": "INTL", "PSE": "INTL",
    "HNX": "INTL", "HOSE": "INTL", "BMV": "INTL", "BOVESPA": "INTL",
    "JSE": "INTL", "TADAWUL": "INTL", "DFM": "INTL", "ADX": "INTL",
    "QSE": "INTL", "ISE": "INTL",
}


def _exchange_to_market_group(exchange: Optional[str]) -> str:
    """Normalize exchange code to a broad market group."""
    if not exchange:
        return "OTHER"
    return EXCHANGE_MARKET_MAP.get(exchange.upper(), "OTHER")
from decimal import Decimal
import logging
import uuid
from datetime import timedelta

from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)


class PortfolioRepository:
    """Repository for portfolio-related database operations."""
    
    def __init__(self, client: Client = supabase):
        self.client = client
    
    # ========================================================================
    # BROKERAGE OPERATIONS
    # ========================================================================
    
    def get_brokerage_by_code(self, brokerage_code: str) -> Optional[Dict[str, Any]]:
        """Get brokerage by code (e.g., 'wealthsimple')."""
        try:
            res = (
                self.client.table("portfolio_brokerages")
                .select("*")
                .eq("brokerage_code", brokerage_code.lower())
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Failed to get brokerage {brokerage_code}: {e}")
            return None
    
    def list_active_brokerages(self) -> List[Dict[str, Any]]:
        """List all active brokerage types."""
        try:
            res = (
                self.client.table("portfolio_brokerages")
                .select("*")
                .eq("is_active", True)
                .order("brokerage_name")
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to list brokerages: {e}")
            return []
    
    # ========================================================================
    # ACCOUNT OPERATIONS
    # ========================================================================
    
    def get_user_accounts(self, user_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get all accounts for a user."""
        try:
            query = (
                self.client.table("portfolio_accounts")
                .select("""
                    *,
                    portfolio_brokerages!fk_portfolio_accounts_brokerage(brokerage_id, brokerage_code, brokerage_name, country_code)
                """)
                .eq("user_id", user_id)
            )
            if active_only:
                query = query.eq("is_active", True)
            
            res = query.order("created_at", desc=True).execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get user accounts for user_id={user_id}: {e}")
            return []
    
    def get_account_by_id(self, account_id: int) -> Optional[Dict[str, Any]]:
        """Get account by ID."""
        try:
            res = (
                self.client.table("portfolio_accounts")
                .select("""
                    *,
                    portfolio_brokerages!fk_portfolio_accounts_brokerage(brokerage_id, brokerage_code, brokerage_name)
                """)
                .eq("account_id", account_id)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Failed to get account {account_id}: {e}")
            return None
    
    def get_or_create_account(
        self,
        user_id: int,
        brokerage_id: int,
        account_external_id: str,
        account_name: str,
        account_type: str,
        currency: str = "CAD",
    ) -> Dict[str, Any]:
        """
        Get existing account or create new one.
        Uses unique constraint on (user_id, brokerage_id, account_external_id).
        """
        try:
            # Try to find existing
            res = (
                self.client.table("portfolio_accounts")
                .select("*")
                .eq("user_id", user_id)
                .eq("brokerage_id", brokerage_id)
                .eq("account_external_id", account_external_id)
                .limit(1)
                .execute()
            )
            
            if res.data:
                logger.debug(f"Found existing account: {account_external_id}")
                return res.data[0]
            
            # Create new
            payload = {
                "user_id": user_id,
                "brokerage_id": brokerage_id,
                "account_external_id": account_external_id,
                "account_name": account_name,
                "account_type": account_type,
                "currency": currency,
                "is_active": True,
            }
            
            create_res = self.client.table("portfolio_accounts").insert(payload).execute()
            if not create_res.data:
                raise Exception("Account creation returned no data")
            
            logger.info(f"Created new account: {account_external_id} (type: {account_type})")
            return create_res.data[0]
        
        except Exception as e:
            logger.error(f"Failed to get/create account {account_external_id}: {e}")
            raise
    
    def update_account_import_timestamp(self, account_id: int) -> None:
        """Update last_import_at timestamp for an account."""
        try:
            self.client.table("portfolio_accounts").update(
                {"last_import_at": now_iso()}
            ).eq("account_id", account_id).execute()
        except Exception as e:
            logger.error(f"Failed to update import timestamp for account {account_id}: {e}")
    
    # ========================================================================
    # TRANSACTION OPERATIONS
    # ========================================================================
    
    def insert_transactions(
        self, transactions: List[Dict[str, Any]], import_batch_id: uuid.UUID
    ) -> int:
        """
        Bulk insert transactions.
        
        Args:
            transactions: List of transaction dicts ready for DB insertion
            import_batch_id: UUID grouping this import batch
        
        Returns:
            Number of transactions inserted
        """
        if not transactions:
            return 0
        
        try:
            # Add import_batch_id to all transactions
            for tx in transactions:
                tx["import_batch_id"] = str(import_batch_id)
            
            res = self.client.table("portfolio_transactions").insert(transactions).execute()
            inserted = len(res.data) if res.data else 0
            logger.info(f"Inserted {inserted} transactions (batch {import_batch_id})")
            return inserted
        
        except Exception as e:
            logger.error(f"Failed to insert transactions: {e}")
            raise
    
    def get_account_transactions(
        self,
        account_id: int,
        limit: Optional[int] = None,
        activity_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get transactions for an account.
        
        Args:
            account_id: Account ID
            limit: Max transactions to return (None = all)
            activity_types: Filter by activity types (e.g., ['Trade'])
        
        Returns:
            List of transaction dicts
        """
        try:
            query = (
                self.client.table("portfolio_transactions")
                .select("*")
                .eq("account_id", account_id)
            )
            
            if activity_types:
                query = query.in_("activity_type", activity_types)
            
            query = query.order("transaction_date", desc=True)
            
            if limit:
                query = query.limit(limit)
            
            res = query.execute()
            return res.data or []
        
        except Exception as e:
            logger.error(f"Failed to get transactions for account {account_id}: {e}")
            return []
    
    def delete_account_transactions(self, account_id: int) -> int:
        """Delete all transactions for an account. Returns count deleted."""
        try:
            res = (
                self.client.table("portfolio_transactions")
                .delete()
                .eq("account_id", account_id)
                .execute()
            )
            deleted = len(res.data) if res.data else 0
            logger.info(f"Deleted {deleted} transactions for account {account_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete transactions for account {account_id}: {e}")
            return 0
    
    # ========================================================================
    # HOLDINGS OPERATIONS
    # ========================================================================
    
    def get_account_holdings(self, account_id: int) -> List[Dict[str, Any]]:
        """Get all current holdings for an account, enriched with company data."""
        return self._get_holdings(account_id=account_id)

    def get_user_all_holdings(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all holdings across all user accounts (aggregated view)."""
        try:
            accounts = self.get_user_accounts(user_id, active_only=True)
            account_ids = [acc["account_id"] for acc in accounts]
            if not account_ids:
                return []
            return self._get_holdings(account_ids=account_ids)
        except Exception as e:
            logger.error(f"Failed to get all holdings for user {user_id}: {e}")
            return []

    def _get_holdings(
        self,
        *,
        account_ids: Optional[List[int]] = None,
        account_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Base method: fetch holdings with account_name/account_type via join.

        Call with either ``account_ids`` (multi-account) or ``account_id`` (single).
        Both are keyword-only for clarity.
        """
        try:
            query = (
                self.client.table("portfolio_holdings")
                .select("""
                    *,
                    portfolio_accounts!fk_portfolio_holdings_account(account_name, account_type)
                """)
            )
            if account_ids is not None:
                query = query.in_("account_id", account_ids)
            elif account_id is not None:
                query = query.eq("account_id", account_id)

            res = query.order("total_cost", desc=True).execute()
            holdings = res.data or []
            holdings = self._flatten_joins(holdings)
            return self._enrich_holdings(holdings)
        except Exception as e:
            logger.error(f"Failed to fetch holdings: {e}")
            return []
    
    def _flatten_joins(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Promote nested Supabase join objects to top-level fields.

        PostgREST returns joined columns as nested dicts keyed by the
        related table name, e.g.:
          {"portfolio_accounts": {"account_name": "RRSP", "account_type": "RRSP"}}

        This flattens those sub-keys to the top level so callers can
        read ``h["account_name"]`` instead of ``h["portfolio_accounts"]["account_name"]``.
        """
        result = []
        for row in rows:
            flat = dict(row)
            for value in row.values():
                if isinstance(value, dict):
                    for sub_key, sub_value in value.items():
                        if sub_key not in flat:
                            flat[sub_key] = sub_value
            result.append(flat)
        return result

    def _enrich_holdings(self, holdings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add company info (name, sector, industry, exchange, market_group) to each holding."""
        company_ids = list(set(h.get("company_id") for h in holdings if h.get("company_id")))
        companies: Dict[int, Dict[str, Any]] = {}
        if company_ids:
            try:
                res = (
                    self.client.table("companies")
                    .select("company_id, company_name, sector, industry, exchange, security_type")
                    .in_("company_id", company_ids)
                    .execute()
                )
                for c in res.data or []:
                    companies[c["company_id"]] = c
            except Exception as e:
                logger.error(f"Failed to enrich holdings with company data: {e}")

        for h in holdings:
            cid = h.get("company_id")
            if cid in companies:
                c = companies[cid]
                h["company_name"] = c.get("company_name", h.get("symbol", "Unknown"))
                h["sector"] = c.get("sector")
                h["industry"] = c.get("industry")
                h["exchange"] = c.get("exchange")
                h["market_group"] = _exchange_to_market_group(c.get("exchange"))
                h["security_type"] = c.get("security_type", "stock")
            else:
                h["company_name"] = h.get("symbol", "Unknown")
                h["sector"] = None
                h["industry"] = None
                h["exchange"] = None
                h["market_group"] = "OTHER"
                h["security_type"] = "stock"

        return holdings
    
    def upsert_holding(self, holding: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update a holding. Uses unique constraint on (account_id, company_id)."""
        try:
            res = (
                self.client.table("portfolio_holdings")
                .upsert(holding, on_conflict="account_id,company_id")
                .execute()
            )
            if not res.data:
                raise Exception("Holding upsert returned no data")
            return res.data[0]
        except Exception as e:
            logger.error(f"Failed to upsert holding: {e}")
            raise
    
    def delete_account_holdings(self, account_id: int) -> int:
        """Delete all holdings for an account. Returns count deleted."""
        try:
            res = (
                self.client.table("portfolio_holdings")
                .delete()
                .eq("account_id", account_id)
                .execute()
            )
            deleted = len(res.data) if res.data else 0
            logger.info(f"Deleted {deleted} holdings for account {account_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete holdings for account {account_id}: {e}")
            return 0
    
    # ========================================================================
    # PERFORMANCE OPERATIONS
    # ========================================================================
    
    def get_earliest_transaction_date(
        self, account_ids: List[int]
    ) -> Optional[date]:
        """Get the earliest transaction date across the given accounts."""
        if not account_ids:
            return None
        try:
            res = (
                self.client.table("portfolio_transactions")
                .select("transaction_date")
                .in_("account_id", account_ids)
                .order("transaction_date", desc=False)
                .limit(1)
                .execute()
            )
            if res.data:
                d = res.data[0]["transaction_date"]
                if isinstance(d, str):
                    return date.fromisoformat(d)
                elif isinstance(d, datetime):
                    return d.date()
                return d
            return None
        except Exception as e:
            logger.error(f"Failed to get earliest transaction date: {e}")
            return None

    def get_account_performance_history(
        self, account_id: int, days: int = 90
    ) -> List[Dict[str, Any]]:
        """Get performance snapshots for last N days."""
        try:
            res = (
                self.client.table("portfolio_performance")
                .select("*")
                .eq("account_id", account_id)
                .order("snapshot_date", desc=True)
                .limit(days)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get performance for account {account_id}: {e}")
            return []
    
    def upsert_performance_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """Insert or update daily performance snapshot."""
        try:
            res = (
                self.client.table("portfolio_performance")
                .upsert(snapshot, on_conflict="account_id,snapshot_date")
                .execute()
            )
            if not res.data:
                raise Exception("Performance snapshot upsert returned no data")
            return res.data[0]
        except Exception as e:
            logger.error(f"Failed to upsert performance snapshot: {e}")
            raise
    
    # ========================================================================
    # DIVIDEND OPERATIONS
    # ========================================================================
    
    def insert_dividends(self, dividends: List[Dict[str, Any]]) -> int:
        """Bulk insert dividend records."""
        if not dividends:
            return 0
        
        try:
            res = self.client.table("portfolio_dividends").insert(dividends).execute()
            inserted = len(res.data) if res.data else 0
            logger.info(f"Inserted {inserted} dividend records")
            return inserted
        except Exception as e:
            logger.error(f"Failed to insert dividends: {e}")
            raise
    
    def get_account_dividends_by_year(
        self, account_id: int, fiscal_year: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Get all dividend payments for an account in a specific year.

        When fiscal_year is None, returns ALL dividend records for the account.
        """
        try:
            query = (
                self.client.table("portfolio_dividends")
                .select("*")
                .eq("account_id", account_id)
                .order("payment_date", desc=False)
            )
            if fiscal_year is not None:
                query = query.eq("fiscal_year", fiscal_year)
            res = query.execute()
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get dividends for account {account_id}: {e}")
            return []
    
    def get_monthly_dividends(
        self, account_id: int, months: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Get monthly dividend summaries (last N months).
        Uses the portfolio_monthly_dividends view.
        """
        try:
            res = (
                self.client.table("portfolio_monthly_dividends")
                .select("*")
                .eq("account_id", account_id)
                .limit(months)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get monthly dividends for account {account_id}: {e}")
            return []
    
    # ========================================================================
    # DIVIDEND DASHBOARD OPERATIONS
    # ========================================================================

    def get_holdings_with_companies(self, account_ids: List[int]) -> List[Dict[str, Any]]:
        """Get holdings enriched with company name/sector for the given accounts."""
        return self._get_holdings(account_ids=account_ids)

    def get_trailing_twelve_month_dividends(
        self, account_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Get dividend payments within the last 365 days."""
        if not account_ids:
            return []
        cutoff = (now_utc() - timedelta(days=365)).strftime("%Y-%m-%d")
        try:
            res = (
                self.client.table("portfolio_dividends")
                .select("symbol, amount, currency, payment_date")
                .in_("account_id", account_ids)
                .gte("payment_date", cutoff)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get trailing 12M dividends: {e}")
            return []

    def get_latest_regular_dps(
        self, company_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Get the latest regular dividend per share per company."""
        if not company_ids:
            return []
        try:
            res = (
                self.client.table("dividend_history")
                .select("company_id, dividend_amount, ex_dividend_date, currency")
                .in_("company_id", company_ids)
                .eq("dividend_type", "regular")
                .order("ex_dividend_date", desc=True)
                .execute()
            )
            rows = res.data or []
            seen = set()
            latest = []
            for r in rows:
                cid = r["company_id"]
                if cid not in seen:
                    seen.add(cid)
                    latest.append(r)
            return latest
        except Exception as e:
            logger.error(f"Failed to get latest regular dps: {e}")
            return []

    def get_dividend_metrics_for_companies(
        self, company_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Get dividend metrics rows for the given companies."""
        if not company_ids:
            return []
        try:
            res = (
                self.client.table("dividend_metrics")
                .select("company_id, dividend_growth_rate_5yr, cash_dividend_payout_ratio, consecutive_years_paid, annual_dps")
                .in_("company_id", company_ids)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get dividend metrics: {e}")
            return []

    def get_upcoming_ex_dates(
        self, company_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Get upcoming ex-dividend dates for the given companies."""
        if not company_ids:
            return []
        today = now_utc().strftime("%Y-%m-%d")
        try:
            res = (
                self.client.table("dividend_history")
                .select("*")
                .in_("company_id", company_ids)
                .eq("dividend_type", "regular")
                .gte("ex_dividend_date", today)
                .order("ex_dividend_date", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get upcoming ex-dates: {e}")
            return []

    def get_next_upcoming_event(
        self, company_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the best available upcoming event for a single company."""
        events = self.get_next_upcoming_events([company_id])
        return events[0] if events else None

    def get_next_upcoming_events(
        self, company_ids: List[int]
    ) -> List[Dict[str, Any]]:
        """Batch-fetch best upcoming event per company.

        Single query using ``company_id=in.(…)``, deduplicated in Python
        to keep the highest‑trust row per company (ORDER BY trust_score
        DESC, source_observed_at DESC).
        """
        if not company_ids:
            return []
        today = now_utc().date().isoformat()
        try:
            res = (
                self.client.table("upcoming_dividend_events")
                .select("*")
                .in_("company_id", company_ids)
                .gte("ex_dividend_date", today)
                .order("trust_score", desc=True)
                .order("source_observed_at", desc=True)
                .execute()
            )
            seen: set = set()
            result: List[Dict[str, Any]] = []
            for row in (res.data or []):
                cid = row.get("company_id")
                if cid is not None and cid not in seen:
                    seen.add(cid)
                    result.append(row)
            return result
        except Exception as e:
            logger.error(
                "Failed to get next upcoming events for %d companies: %s",
                len(company_ids), e,
            )
            return []

    def get_portfolio_dividends_for_symbol(
        self, account_ids: List[int], symbol: str
    ) -> List[Dict[str, Any]]:
        """Get dividend payments for a symbol across the given accounts."""
        if not account_ids:
            return []
        try:
            res = (
                self.client.table("portfolio_dividends")
                .select("*")
                .in_("account_id", account_ids)
                .eq("symbol", symbol.upper())
                .order("payment_date", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get dividends for {symbol}: {e}")
            return []

    # ========================================================================
    # HOLDING-LEVEL OPERATIONS (for single-stock performance)
    # ========================================================================

    def get_transactions_for_symbol(
        self, user_id: int, symbol: str
    ) -> List[Dict[str, Any]]:
        """Get all Trade transactions for a symbol across user's accounts."""
        accounts = self.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
        if not account_ids:
            return []
        try:
            res = (
                self.client.table("portfolio_transactions")
                .select("*")
                .in_("account_id", account_ids)
                .eq("symbol", symbol.upper())
                .in_("activity_type", ["Trade"])
                .order("transaction_date", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get transactions for {symbol}: {e}")
            return []

    def get_dividends_for_symbol(
        self, user_id: int, symbol: str
    ) -> List[Dict[str, Any]]:
        """Get ALL dividend payments for a symbol across user's accounts."""
        accounts = self.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
        if not account_ids:
            return []
        try:
            res = (
                self.client.table("portfolio_dividends")
                .select("*")
                .in_("account_id", account_ids)
                .eq("symbol", symbol.upper())
                .order("payment_date", desc=False)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get dividends for {symbol}: {e}")
            return []

    # ========================================================================
    # IMPORT JOB OPERATIONS
    # ========================================================================

    def create_import_job(
        self,
        import_batch_id: uuid.UUID,
        user_id: int,
        brokerage_id: int,
        csv_hash: str,
        csv_filename: Optional[str] = None,
        csv_size_bytes: Optional[int] = None,
        total_rows: int = 0,
    ) -> Optional[int]:
        """Create a pending import job record. Returns import_id."""
        try:
            payload = {
                "import_batch_id": str(import_batch_id),
                "user_id": user_id,
                "brokerage_id": brokerage_id,
                "csv_hash": csv_hash,
                "csv_filename": csv_filename,
                "csv_size_bytes": csv_size_bytes,
                "total_rows": total_rows,
                "imported_rows": 0,
                "status": "pending",
            }
            res = self.client.table("portfolio_import_history").insert(payload).execute()
            if res.data:
                import_id = res.data[0].get("import_id")
                logger.info(f"Created import job {import_id} (batch {import_batch_id})")
                return import_id
            return None
        except Exception as e:
            logger.error(f"Failed to create import job: {e}")
            return None

    def update_import_progress(
        self,
        import_batch_id: uuid.UUID,
        status: Optional[str] = None,
        rows_parsed: Optional[int] = None,
        rows_inserted: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """Update import job status and progress. Returns True on success."""
        try:
            payload: Dict[str, Any] = {}
            if status is not None:
                payload["status"] = status
            if rows_parsed is not None:
                payload["rows_parsed"] = rows_parsed
            if rows_inserted is not None:
                payload["imported_rows"] = rows_inserted
            if error_message is not None:
                payload["error_message"] = error_message
                payload["status"] = "failed"
            if status == "processing":
                payload["started_at"] = now_iso()
            if status in ("completed", "failed"):
                payload["completed_at"] = now_iso()

            if not payload:
                return False

            self.client.table("portfolio_import_history").update(payload).eq(
                "import_batch_id", str(import_batch_id)
            ).execute()
            return True
        except Exception as e:
            logger.error(f"Failed to update import progress for {import_batch_id}: {e}")
            return False

    def get_import_job(self, import_batch_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        """Get current import job status and progress."""
        try:
            res = (
                self.client.table("portfolio_import_history")
                .select("*")
                .eq("import_batch_id", str(import_batch_id))
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Failed to get import job {import_batch_id}: {e}")
            return None

    # ========================================================================
    # DUPLICATE HANDLING
    # ========================================================================

    UNIQUE_FINGERPRINT_COLS = "account_id,transaction_date,activity_type,symbol,quantity,net_cash_amount"

    def insert_transactions_with_duplicates(
        self,
        transactions: List[Dict[str, Any]],
        import_batch_id: uuid.UUID,
        skip_duplicates: bool = True,
    ) -> Tuple[int, int]:
        """
        Bulk insert transactions with duplicate detection.
        
        Uses ON CONFLICT DO NOTHING via the upsert() API with ignore_duplicates=True.
        
        Args:
            transactions: List of transaction dicts
            import_batch_id: UUID for this import batch
            skip_duplicates: Skip duplicates (True) or fail (False)
        
        Returns:
            (inserted_count, duplicate_count)
        """
        if not transactions:
            return 0, 0

        # Add import_batch_id to all transactions
        for tx in transactions:
            tx["import_batch_id"] = str(import_batch_id)

        try:
            if skip_duplicates:
                res = self.client.table("portfolio_transactions").upsert(
                    transactions,
                    ignore_duplicates=True,
                    on_conflict=self.UNIQUE_FINGERPRINT_COLS,
                ).execute()
                inserted_count = len(res.data) if res.data else 0
                duplicate_count = len(transactions) - inserted_count
                logger.info(
                    f"Batch upsert complete: {inserted_count} inserted, "
                    f"{duplicate_count} duplicates skipped"
                )
                return inserted_count, duplicate_count
            else:
                res = self.client.table("portfolio_transactions").insert(transactions).execute()
                inserted_count = len(res.data) if res.data else 0
                logger.info(f"Bulk inserted {inserted_count} transactions")
                return inserted_count, 0
        except Exception as e:
            error_str = str(e).lower()
            if "unique" in error_str or "duplicate" in error_str:
                if not skip_duplicates:
                    logger.error("Duplicate transaction detected - import failed")
                    raise ValueError(
                        "Duplicate transactions detected. This CSV may have been imported before."
                    )
                logger.warning(f"Unexpected constraint error during upsert: {e}")
                return 0, len(transactions)
            logger.error(f"Failed to insert transactions: {e}")
            raise

    def get_import_history(
        self, user_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get import history for a user."""
        try:
            res = (
                self.client.table("portfolio_user_import_history")
                .select("*")
                .eq("user_id", user_id)
                .order("started_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"Failed to get import history for user {user_id}: {e}")
            return []