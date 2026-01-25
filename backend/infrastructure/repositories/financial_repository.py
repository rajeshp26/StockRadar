"""
Financial Data Repository - Refactored
Handles all database operations with improved error handling and type safety.
"""
import logging
from datetime import date, datetime
from typing import List, Dict, Any, Optional
from decimal import Decimal
from supabase import Client
from database import supabase
from domain.models import (
    IncomeStatementRow,
    BalanceSheetRow,
    CashFlowRow,
    EarningsRow,
    DividendRow,
    CompanyRefreshInfo,
    CompleteFundamentals,
)

logger = logging.getLogger(__name__)


# ============================================================================
# SERIALIZATION UTILITY
# ============================================================================
class DatabaseSerializer:
    """Handles conversion of Python types to database-compatible formats."""
    
    @staticmethod
    def serialize(data: dict) -> dict:
        """
        Convert non-JSON-serializable types to database-compatible formats.
        
        Handles:
        - date → ISO format string
        - datetime → ISO format string  
        - Decimal → float
        - None → None (preserved)
        """
        result = {}
        for key, value in data.items():
            if value is None:
                result[key] = None
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, date):
                result[key] = value.isoformat()
            elif isinstance(value, Decimal):
                result[key] = float(value)
            else:
                result[key] = value
        return result


# ============================================================================
# FINANCIAL REPOSITORY
# ============================================================================
class SupabaseFinancialRepository:
    """
    Repository for all financial data operations with Supabase.
    Uses unconditional unique constraints for reliable UPSERT operations.
    """
    
    def __init__(self, client: Client = supabase):
        self.client = client
    
    # ========================================================================
    # UPSERT METHODS - Financial Statements
    # ========================================================================
    async def upsert_income_statements(
        self, rows: List[IncomeStatementRow]
    ) -> Dict[str, Any]:
        """
        Upsert income statement rows.
        
        Uses constraint: UNIQUE (company_id, fiscal_year, fiscal_quarter)
        - Annual records: (company_id, fiscal_year, NULL)
        - Quarterly records: (company_id, fiscal_year, fiscal_quarter)
        
        Deduplicates by unique key to prevent batch update conflicts.
        """
        if not rows:
            logger.debug("No income statements to upsert")
            return {"count": 0}
        
        try:
            # Deduplicate by (company_id, fiscal_year, fiscal_quarter)
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            
            deduplicated_rows = list(seen.values())
            
            if len(deduplicated_rows) < len(rows):
                logger.warning(
                    f"Deduplicated income statements: {len(rows)} → {len(deduplicated_rows)} "
                    f"(removed {len(rows) - len(deduplicated_rows)} duplicates)"
                )
            
            data = [DatabaseSerializer.serialize(row.model_dump()) for row in deduplicated_rows]
            
            response = self.client.table('income_statements').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()
            
            logger.info(f"✅ Upserted {len(deduplicated_rows)} income statement rows")
            return response.data or {"count": len(deduplicated_rows)}
        
        except Exception as e:
            logger.error(f"Failed to upsert income statements: {str(e)}")
            raise
    
    async def upsert_balance_sheets(
        self, rows: List[BalanceSheetRow]
    ) -> Dict[str, Any]:
        """
        Upsert balance sheet rows.
        
        Uses constraint: UNIQUE (company_id, fiscal_year, fiscal_quarter)
        Deduplicates by unique key to prevent batch update conflicts.
        """
        if not rows:
            logger.debug("No balance sheets to upsert")
            return {"count": 0}
        
        try:
            # Deduplicate by (company_id, fiscal_year, fiscal_quarter)
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            
            deduplicated_rows = list(seen.values())
            
            if len(deduplicated_rows) < len(rows):
                logger.warning(
                    f"Deduplicated balance sheets: {len(rows)} → {len(deduplicated_rows)} "
                    f"(removed {len(rows) - len(deduplicated_rows)} duplicates)"
                )
            
            data = [DatabaseSerializer.serialize(row.model_dump()) for row in deduplicated_rows]
            
            response = self.client.table('balance_sheets').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()
            
            logger.info(f"✅ Upserted {len(deduplicated_rows)} balance sheet rows")
            return response.data or {"count": len(deduplicated_rows)}
        
        except Exception as e:
            logger.error(f"Failed to upsert balance sheets: {str(e)}")
            raise
    
    async def upsert_cash_flows(
        self, rows: List[CashFlowRow]
    ) -> Dict[str, Any]:
        """
        Upsert cash flow statement rows.
        
        Uses constraint: UNIQUE (company_id, fiscal_year, fiscal_quarter)
        Deduplicates by unique key to prevent batch update conflicts.
        """
        if not rows:
            logger.debug("No cash flows to upsert")
            return {"count": 0}
        
        try:
            # Deduplicate by (company_id, fiscal_year, fiscal_quarter)
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            
            deduplicated_rows = list(seen.values())
            
            if len(deduplicated_rows) < len(rows):
                logger.warning(
                    f"Deduplicated cash flows: {len(rows)} → {len(deduplicated_rows)} "
                    f"(removed {len(rows) - len(deduplicated_rows)} duplicates)"
                )
            
            data = [DatabaseSerializer.serialize(row.model_dump()) for row in deduplicated_rows]
            
            response = self.client.table('cash_flow_statements').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()
            
            logger.info(f"✅ Upserted {len(deduplicated_rows)} cash flow rows")
            return response.data or {"count": len(deduplicated_rows)}
        
        except Exception as e:
            logger.error(f"Failed to upsert cash flows: {str(e)}")
            raise
    
    async def upsert_earnings(
        self, rows: List[EarningsRow]
    ) -> Dict[str, Any]:
        """
        Upsert earnings rows.
        
        Uses constraint: UNIQUE (company_id, fiscal_year, fiscal_quarter)
        Deduplicates by unique key to prevent batch update conflicts.
        """
        if not rows:
            logger.debug("No earnings to upsert")
            return {"count": 0}
        
        try:
            # Deduplicate by (company_id, fiscal_year, fiscal_quarter)
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            
            deduplicated_rows = list(seen.values())
            
            if len(deduplicated_rows) < len(rows):
                logger.warning(
                    f"Deduplicated earnings: {len(rows)} → {len(deduplicated_rows)} "
                    f"(removed {len(rows) - len(deduplicated_rows)} duplicates)"
                )
            
            data = [DatabaseSerializer.serialize(row.model_dump()) for row in deduplicated_rows]
            
            response = self.client.table('earnings').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()
            
            logger.info(f"✅ Upserted {len(deduplicated_rows)} earnings rows")
            return response.data or {"count": len(deduplicated_rows)}
        
        except Exception as e:
            logger.error(f"Failed to upsert earnings: {str(e)}")
            raise
    
    async def upsert_dividends(
        self, rows: List[DividendRow]
    ) -> Dict[str, Any]:
        """
        Upsert dividend history rows.
        
        Deduplicates rows by (company_id, ex_dividend_date) to prevent
        'ON CONFLICT DO UPDATE command cannot affect row a second time' error.
        """
        if not rows:
            logger.debug("No dividends to upsert")
            return {"count": 0}
        
        try:
            # Deduplicate by (company_id, ex_dividend_date) - keep last occurrence
            # This prevents PostgreSQL error when same dividend appears multiple times
            seen = {}
            for row in rows:
                key = (row.company_id, row.ex_dividend_date)
                seen[key] = row
            
            deduplicated_rows = list(seen.values())
            
            if len(deduplicated_rows) < len(rows):
                logger.warning(
                    f"Deduplicated dividends: {len(rows)} → {len(deduplicated_rows)} "
                    f"(removed {len(rows) - len(deduplicated_rows)} duplicates)"
                )
            
            data = [DatabaseSerializer.serialize(row.model_dump()) for row in deduplicated_rows]
            
            response = self.client.table('dividend_history').upsert(
                data,
                on_conflict='company_id,ex_dividend_date'
            ).execute()
            
            logger.info(f"✅ Upserted {len(deduplicated_rows)} dividend rows")
            return response.data or {"count": len(deduplicated_rows)}
        
        except Exception as e:
            logger.error(f"Failed to upsert dividends: {str(e)}")
            raise
    
    # ========================================================================
    # COMPANY METADATA UPDATES
    # ========================================================================
    async def update_company_refresh_metadata(
        self,
        company_id: int,
        last_fiscal_year: int,
        last_fiscal_quarter: Optional[int],
        is_first_load: bool = False,
        next_earnings_date: Optional[date] = None,
    ) -> Dict[str, Any]:
        """
        Update company's refresh tracking metadata.
        
        Args:
            company_id: Company to update
            last_fiscal_year: Latest fiscal year in our data
            last_fiscal_quarter: Latest fiscal quarter (None for annual)
            is_first_load: If True, set first_financial_data_loaded_at
            next_earnings_date: Next earnings announcement date
        
        Returns:
            Updated company record
        """
        try:
            now = datetime.utcnow()
            
            # Determine completeness status
            status = "COMPLETE" if is_first_load else "CURRENT"
            
            update_data = {
                'last_financial_refresh_at': now.isoformat(),
                'last_refreshed_fiscal_year': last_fiscal_year,
                'last_refreshed_fiscal_quarter': last_fiscal_quarter,
                'data_completeness_status': status,
            }
            
            if is_first_load:
                update_data['first_financial_data_loaded_at'] = now.isoformat()
            
            if next_earnings_date:
                update_data['next_earnings_date'] = next_earnings_date.isoformat()
            
            response = self.client.table('companies').update(update_data).eq(
                'company_id', company_id
            ).execute()
            
            logger.info(
                f"✅ Updated metadata for company {company_id}: "
                f"FY{last_fiscal_year}Q{last_fiscal_quarter or 'Annual'} | Status: {status}"
            )
            return response.data[0] if response.data else {}
        
        except Exception as e:
            logger.error(f"Failed to update metadata for company {company_id}: {str(e)}")
            raise
    
    # ========================================================================
    # COMPANY QUERY METHODS
    # ========================================================================
    async def get_companies_with_upcoming_earnings(
        self,
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        """Query companies with earnings in date range."""
        try:
            response = self.client.table('companies').select(
                'company_id, ticker_symbol, next_earnings_date, '
                'last_refreshed_fiscal_year, last_refreshed_fiscal_quarter, '
                'data_completeness_status, first_financial_data_loaded_at'
            ).gte(
                'next_earnings_date', start_date.isoformat()
            ).lte(
                'next_earnings_date', end_date.isoformat()
            ).in_(
                'data_completeness_status',
                ['INITIAL', 'PARTIAL', 'COMPLETE', 'CURRENT']
            ).execute()
            
            count = len(response.data or [])
            logger.info(
                f"Found {count} companies with earnings between {start_date} and {end_date}"
            )
            return response.data or []
        
        except Exception as e:
            logger.error(f"Failed to query companies with upcoming earnings: {str(e)}")
            raise
    
    async def get_company_refresh_info(
        self, company_id: int
    ) -> Optional[CompanyRefreshInfo]:
        """Get company's refresh metadata for smart filtering."""
        try:
            response = self.client.table('companies').select(
                'company_id, ticker_symbol, '
                'first_financial_data_loaded_at, last_financial_refresh_at, '
                'last_refreshed_fiscal_year, last_refreshed_fiscal_quarter, '
                'data_completeness_status, next_earnings_date'
            ).eq('company_id', company_id).single().execute()
            
            if not response.data:
                logger.warning(f"Company {company_id} not found")
                return None
            
            data = response.data
            return CompanyRefreshInfo(
                company_id=data['company_id'],
                ticker_symbol=data['ticker_symbol'],
                first_financial_data_loaded_at=(
                    datetime.fromisoformat(data['first_financial_data_loaded_at'])
                    if data.get('first_financial_data_loaded_at')
                    else None
                ),
                last_financial_refresh_at=(
                    datetime.fromisoformat(data['last_financial_refresh_at'])
                    if data.get('last_financial_refresh_at')
                    else None
                ),
                last_refreshed_fiscal_year=data.get('last_refreshed_fiscal_year'),
                last_refreshed_fiscal_quarter=data.get('last_refreshed_fiscal_quarter'),
                data_completeness_status=data.get('data_completeness_status', 'INITIAL'),
                next_earnings_date=(
                    datetime.fromisoformat(data['next_earnings_date']).date()
                    if data.get('next_earnings_date')
                    else None
                ),
            )
        
        except Exception as e:
            logger.error(f"Failed to get refresh info for company {company_id}: {str(e)}")
            raise
    
    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================
    async def upsert_all_financials(
        self, financials: CompleteFundamentals
    ) -> Dict[str, int]:
        """Upsert all financial data from a CompleteFundamentals object."""
        logger.info(
            f"Upserting all financials for {financials.symbol}: "
            f"{financials.total_rows_fetched} total rows"
        )
        
        results = {
            'income_statements': 0,
            'balance_sheets': 0,
            'cash_flows': 0,
            'earnings': 0,
            'dividends': 0,
        }
        
        try:
            if financials.income_statements.rows:
                await self.upsert_income_statements(
                    financials.income_statements.rows
                )
                results['income_statements'] = len(financials.income_statements.rows)
            
            if financials.balance_sheets.rows:
                await self.upsert_balance_sheets(
                    financials.balance_sheets.rows
                )
                results['balance_sheets'] = len(financials.balance_sheets.rows)
            
            if financials.cash_flows.rows:
                await self.upsert_cash_flows(
                    financials.cash_flows.rows
                )
                results['cash_flows'] = len(financials.cash_flows.rows)
            
            if financials.earnings.rows:
                await self.upsert_earnings(
                    financials.earnings.rows
                )
                results['earnings'] = len(financials.earnings.rows)
            
            if financials.dividends.rows:
                await self.upsert_dividends(
                    financials.dividends.rows
                )
                results['dividends'] = len(financials.dividends.rows)
            
            total = sum(results.values())
            logger.info(
                f"✅ Upserted all financials for {financials.symbol}: "
                f"{total} rows across all tables"
            )
            
            return results
        
        except Exception as e:
            logger.error(f"Failed to upsert all financials: {str(e)}")
            raise
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    async def company_exists(self, company_id: int) -> bool:
        """Check if company exists in database."""
        try:
            response = self.client.table('companies').select('company_id').eq(
                'company_id', company_id
            ).single().execute()
            return response.data is not None
        except Exception:
            return False
    
    async def get_company_by_id(self, company_id: int) -> Optional[Dict[str, Any]]:
        """Get full company record."""
        try:
            response = self.client.table('companies').select('*').eq(
                'company_id', company_id
            ).single().execute()
            return response.data
        except Exception:
            return None
    
    async def get_company_by_symbol(
        self, symbol: str, exchange: str = 'NASDAQ'
    ) -> Optional[Dict[str, Any]]:
        """Get company by ticker symbol."""
        try:
            response = self.client.table('companies').select('*').eq(
                'ticker_symbol', symbol
            ).eq('exchange', exchange).single().execute()
            return response.data
        except Exception:
            return None