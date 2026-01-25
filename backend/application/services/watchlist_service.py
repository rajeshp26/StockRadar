"""
Updated Watchlist Service with Financial Data Integration
Includes methods for adding stocks with financial data loading.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import date

from domain.interfaces.stock_provider import StockProvider
from domain.interfaces.repository import WatchlistRepository, UserRepository
from domain.entities.watchlist import WatchlistWithStocks, StockPriceInfo
from shared.exceptions.base import NotFoundError, ExternalServiceError
from database import supabase
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.defeat_beta_provider import DefeatBetaProvider

logger = logging.getLogger(__name__)


class WatchlistService:
    """
    Manages watchlist operations including stock addition with financial data loading.
    """
    
    def __init__(
        self,
        stock_provider: StockProvider,
        watchlist_repo: WatchlistRepository,
        user_repo: UserRepository,
        financial_repo: Optional[SupabaseFinancialRepository] = None,
        defeat_beta_provider: Optional[DefeatBetaProvider] = None,
    ):
        """
        Initialize watchlist service.
        
        Args:
            stock_provider: Provider for real-time stock prices (yfinance)
            watchlist_repo: Repository for watchlist operations
            user_repo: Repository for user operations
            financial_repo: Repository for financial data (optional but recommended)
            defeat_beta_provider: Provider for defeat-beta financials (optional)
        """
        self.stock_provider = stock_provider
        self.watchlist_repo = watchlist_repo
        self.user_repo = user_repo
        self.financial_repo = financial_repo or SupabaseFinancialRepository()
        self.defeat_beta_provider = defeat_beta_provider or DefeatBetaProvider(
            yfinance_provider=stock_provider
        )
    
    # ========================================================================
    # EXISTING METHODS (unchanged)
    # ========================================================================
    
    def get_db_user_id(self, firebase_uid: str) -> int:
        user = self.user_repo.find_by_firebase_uid(firebase_uid)
        if not user:
            raise NotFoundError("User not found.")
        return user['user_id']
    
    def get_default_watchlist_with_items(self, firebase_uid: str) -> WatchlistWithStocks:
        db_user_id = self.get_db_user_id(firebase_uid)
        
        # 1. Find or Create Default Watchlist
        watchlist = self.watchlist_repo.find_default_by_user_id(db_user_id)
        
        if watchlist:
            watchlist_id = watchlist['id']
            watchlist_name = watchlist['watchlist_name']
            is_default = watchlist['is_default']
        else:
            new_watchlist = self.watchlist_repo.create_default(db_user_id, "My Watchlist")
            watchlist_id = new_watchlist['id']
            watchlist_name = new_watchlist['watchlist_name']
            is_default = new_watchlist['is_default']
        
        # 2. Fetch Watchlist Items
        raw_watchlist_items = self.watchlist_repo.get_items_by_watchlist_id(watchlist_id)
        if not raw_watchlist_items:
            return WatchlistWithStocks(
                watchlist_id=watchlist_id,
                name=watchlist_name,
                is_default=is_default,
                stocks=[]
            )
        
        symbols = [item['companies']['ticker_symbol'] for item in raw_watchlist_items if item.get('companies')]
        company_ids = [item['companies']['company_id'] for item in raw_watchlist_items if item.get('companies')]
        
        # 3. Fetch Market Data
        all_tickers_data = {}
        if symbols:
            all_tickers_data = self.stock_provider.get_tickers_data(symbols)
        
        market_data_map = {}
        if company_ids:
            market_data_res = supabase.table('current_market_data').select('*').in_('company_id', company_ids).execute()
            if market_data_res.data:
                market_data_map = {item['company_id']: item for item in market_data_res.data}
        
        # 4. Combine data
        stocks_list = []
        for item in raw_watchlist_items:
            company = item.get('companies')
            if not company:
                continue
            
            ticker_symbol = company['ticker_symbol']
            ticker_data = all_tickers_data.get(ticker_symbol)
            
            current_price = None
            previous_close = None
            last_updated = None
            
            if ticker_data:
                current_price = ticker_data.info.get('currentPrice') or ticker_data.info.get('regularMarketPrice')
                previous_close = ticker_data.info.get('previousClose') or ticker_data.info.get('regularMarketPreviousClose')
            
            db_market_data = market_data_map.get(company['company_id'])
            if db_market_data:
                last_updated = db_market_data.get('last_updated')
                if current_price is None or previous_close is None:
                    current_price = float(db_market_data.get('current_price', 0))
                    previous_close = float(db_market_data.get('close_price')) if db_market_data.get('close_price') else current_price
            
            if current_price is None or previous_close is None:
                continue
            
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else 0
            
            stocks_list.append(StockPriceInfo(
                id=item['watchlist_item_id'],
                symbol=ticker_symbol,
                name=company['company_name'],
                price=current_price,
                change=change,
                changePercent=change_percent,
                targetBuy=item.get('target_buy'),
                targetSell=item.get('target_sell'),
                lastUpdated=last_updated
            ))
        
        return WatchlistWithStocks(
            watchlist_id=watchlist_id,
            name=watchlist_name,
            is_default=is_default,
            stocks=stocks_list
        )
    
    # ========================================================================
    # NEW METHODS - Financial Data Integration
    # ========================================================================
    
    async def add_stock_to_watchlist(
        self,
        user_id: int,
        symbol: str,
        watchlist_id: int,
    ) -> Dict[str, Any]:
        """
        Add a stock to watchlist with financial data loading.
        
        Two-phase operation:
        1. FAST PATH (synchronous) - < 2 seconds
           - Get/create company
           - Fetch current price from yfinance
           - Store in current_market_data
           - Add to watchlist
           - Return to client immediately
        
        2. SLOW PATH (asynchronous) - background task
           - Load full/incremental financial history from defeat-beta
           - Store to all financial tables
           - Update company metadata
        
        Args:
            user_id: User adding stock
            symbol: Stock ticker symbol (e.g., 'TSLA')
            watchlist_id: Watchlist to add to
        
        Returns:
            Response with stock data and loading status
        """
        logger.info(f"Adding {symbol} to watchlist {watchlist_id} for user {user_id}")
        
        try:
            # ================================================================
            # PHASE 1: FAST PATH (Synchronous)
            # ================================================================
            
            # Step 1: Get or create company
            company = await self._get_or_create_company(symbol)
            company_id = company['company_id']
            
            logger.debug(f"Company {symbol}: ID={company_id} (new={not company.get('created_at')})")
            
            # Step 2: Fetch current price from yfinance
            try:
                stock_details = self.stock_provider.get_stock_details(symbol)
                current_price = stock_details.price if stock_details else None
            except Exception as e:
                logger.warning(f"Failed to fetch current price for {symbol}: {str(e)}")
                current_price = None
            
            # Step 3: Store in current_market_data
            if current_price:
                await self._update_market_data(company_id, symbol, current_price)
            
            # Step 4: Add to watchlist
            watchlist_item = await self._add_watchlist_item(watchlist_id, company_id)
            
            # Step 5: Determine if this is a new company (no financial data yet)
            refresh_info = await self.financial_repo.get_company_refresh_info(company_id)
            is_new_company = refresh_info.first_financial_data_loaded_at is None
            
            logger.info(
                f"✅ Added {symbol} to watchlist (fast path complete). "
                f"New company: {is_new_company}"
            )
            
            # Step 6: Start background task for financial data loading
            if is_new_company:
                asyncio.create_task(
                    self._fetch_and_store_financials_optimized(
                        symbol=symbol,
                        company_id=company_id,
                        is_new_company=True,  # Load full history
                    )
                )
                logger.debug(f"Started background task to load full history for {symbol}")
            
            # Return immediate response
            return {
                'watchlist_item_id': watchlist_item['watchlist_item_id'],
                'company_id': company_id,
                'symbol': symbol,
                'current_price': current_price,
                'financials_loading': is_new_company,
                'is_new_stock': is_new_company,
                'message': 'Stock added. Loading financial data...' if is_new_company else 'Stock added.',
            }
        
        except Exception as e:
            logger.error(f"Failed to add {symbol} to watchlist: {str(e)}")
            raise
    
    async def refresh_company_financials(
        self,
        symbol: str,
        company_id: int,
    ) -> Dict[str, Any]:
        """
        On-demand refresh of company financial data.
        
        Called by: POST /stocks/{symbol}/refresh-financials
        Used for: When user wants fresh data immediately
        
        Args:
            symbol: Stock ticker
            company_id: Company ID
        
        Returns:
            Summary of refresh operation
        """
        logger.info(f"On-demand refresh for {symbol} (company_id={company_id})")
        
        try:
            # Get refresh info to determine filtering
            refresh_info = await self.financial_repo.get_company_refresh_info(company_id)
            
            # Fetch with smart filtering
            financials = await self.defeat_beta_provider.get_all_financials_optimized(
                symbol=symbol,
                company_id=company_id,
                last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
                last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
                force_full_history=False,  # Always incremental for on-demand
            )
            
            # Store everything
            upsert_results = await self.financial_repo.upsert_all_financials(financials)
            
            # Update metadata
            await self.financial_repo.update_company_refresh_metadata(
                company_id=company_id,
                last_fiscal_year=financials.income_statements.rows[-1].fiscal_year
                if financials.income_statements.rows
                else refresh_info.last_refreshed_fiscal_year,
                last_fiscal_quarter=financials.income_statements.rows[-1].fiscal_quarter
                if financials.income_statements.rows
                else refresh_info.last_refreshed_fiscal_quarter,
                is_first_load=False,
                next_earnings_date=financials.next_earnings_date,
            )
            
            total_rows = sum(upsert_results.values())
            logger.info(
                f"✅ On-demand refresh complete for {symbol}: "
                f"{total_rows} rows across all tables"
            )
            
            return {
                'symbol': symbol,
                'company_id': company_id,
                'fetched_at': financials.fetched_at.isoformat(),
                'rows_upserted': upsert_results,
                'total_rows': total_rows,
                'next_earnings_date': financials.next_earnings_date.isoformat()
                if financials.next_earnings_date
                else None,
            }
        
        except Exception as e:
            logger.error(f"On-demand refresh failed for {symbol}: {str(e)}")
            raise
    
    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================
    
    async def _get_or_create_company(self, symbol: str) -> Dict[str, Any]:
        """Get existing company or create new one."""
        try:
            # Try to find existing
            existing = await self.financial_repo.get_company_by_symbol(symbol)
            if existing:
                logger.debug(f"Company {symbol} already exists: ID={existing['company_id']}")
                return existing
            
            # Create new
            logger.debug(f"Creating new company for {symbol}")
            stock_details = self.stock_provider.get_stock_details(symbol)
            
            if not stock_details:
                raise ExternalServiceError(f"Unable to fetch details for {symbol}")
            
            new_company = {
                'ticker_symbol': symbol,
                'company_name': stock_details.long_name or symbol,
                'exchange': stock_details.exchange or 'UNKNOWN',
                'sector': stock_details.sector,
                'industry': stock_details.industry,
                'currency': stock_details.currency or 'USD',
                'next_earnings_date': stock_details.next_earnings_date.isoformat()
                if stock_details.next_earnings_date
                else None,
            }
            
            response = supabase.table('companies').insert(new_company).execute()
            created = response.data[0] if response.data else None
            
            if not created:
                raise ExternalServiceError(f"Failed to create company for {symbol}")
            
            logger.info(f"✅ Created company {symbol}: ID={created['company_id']}")
            return created
        
        except Exception as e:
            logger.error(f"Failed to get/create company {symbol}: {str(e)}")
            raise
    
    async def _update_market_data(
        self, company_id: int, symbol: str, current_price: float
    ) -> None:
        """Update or insert current market data."""
        try:
            stock_details = self.stock_provider.get_stock_details(symbol)
            
            market_data = {
                'company_id': company_id,
                'current_price': current_price,
                'open_price': stock_details.open_price if stock_details else None,
                'high_price': stock_details.high_price if stock_details else None,
                'low_price': stock_details.low_price if stock_details else None,
                'close_price': stock_details.close_price if stock_details else None,
                'volume': stock_details.volume if stock_details else None,
                'market_state': stock_details.market_state if stock_details else None,
            }
            
            supabase.table('current_market_data').upsert(
                market_data,
                on_conflict='company_id'
            ).execute()
            
            logger.debug(f"Updated market data for {symbol}: ${current_price}")
        
        except Exception as e:
            logger.warning(f"Failed to update market data for {symbol}: {str(e)}")
    
    async def _add_watchlist_item(
        self, watchlist_id: int, company_id: int
    ) -> Dict[str, Any]:
        """Add item to watchlist."""
        try:
            response = supabase.table('watchlist_items').insert({
                'watchlist_id': watchlist_id,
                'company_id': company_id,
                'position': 0,
            }).execute()
            
            if not response.data:
                raise ExternalServiceError("Failed to add item to watchlist")
            
            return response.data[0]
        
        except Exception as e:
            logger.error(f"Failed to add watchlist item: {str(e)}")
            raise
    
    async def _fetch_and_store_financials_optimized(
        self,
        symbol: str,
        company_id: int,
        is_new_company: bool = False,
    ) -> None:
        """
        Background task: Fetch and store financial data.
        
        This runs asynchronously after the fast path completes.
        """
        try:
            logger.info(
                f"Starting background financial load for {symbol} "
                f"(new_company={is_new_company})"
            )
            
            # Get refresh info
            refresh_info = await self.financial_repo.get_company_refresh_info(company_id)
            
            # Fetch with optimization
            financials = await self.defeat_beta_provider.get_all_financials_optimized(
                symbol=symbol,
                company_id=company_id,
                last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
                last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
                force_full_history=is_new_company,  # Load all for new stocks
            )
            
            # Store all financials
            upsert_results = await self.financial_repo.upsert_all_financials(financials)
            
            # Update metadata
            latest_fiscal_year = 2024  # Default, update from data
            latest_fiscal_quarter = None
            
            if financials.income_statements.rows:
                latest = financials.income_statements.rows[-1]
                latest_fiscal_year = latest.fiscal_year
                latest_fiscal_quarter = latest.fiscal_quarter
            
            await self.financial_repo.update_company_refresh_metadata(
                company_id=company_id,
                last_fiscal_year=latest_fiscal_year,
                last_fiscal_quarter=latest_fiscal_quarter,
                is_first_load=is_new_company,
                next_earnings_date=financials.next_earnings_date,
            )
            
            total_rows = sum(upsert_results.values())
            logger.info(
                f"✅ Background load complete for {symbol}: "
                f"{total_rows} total rows upserted"
            )
        
        except Exception as e:
            logger.error(
                f"Background financial load failed for {symbol}: {str(e)}"
            )