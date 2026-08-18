"""
Updated Watchlist Service with Financial Data Integration
- YFinance is used exclusively for public.current_market_data (fast path).
- All fundamentals (IS/BS/CF/Earnings/Dividends) enter via DefeatBetaProvider, with YF fallback.
- Unifies orchestration so routes stay thin and consistent (no YF-only deep sync paths).
- Auto-compute Rule #1 intrinsic value after fundamentals ingestion and on-demand refresh.
- NEW: Price history loading (monthly bars for CANSLIM N/L analysis).
"""

from __future__ import annotations
import asyncio
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import date, timedelta

import pandas as pd

from domain.interfaces.stock_provider import StockProvider
from domain.interfaces.repository import WatchlistRepository, UserRepository
from domain.entities.watchlist import WatchlistWithStocks, StockPriceInfo
from shared.exceptions.base import NotFoundError, ExternalServiceError
from database import supabase

from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from shared.price_utils import build_price_snapshot
if TYPE_CHECKING:
    from providers.defeat_beta_provider import DefeatBetaProvider

# NEW: Valuation imports
from infrastructure.repositories.valuation_repository import ValuationRepository
from application.services.recompute_guard import RecomputeGuard
from application.services.valuation_service import ValuationService
from application.jobs.derived_financial_metrics_job import (
    compute_and_upsert_derived_financial_metrics,
    compute_and_upsert_quarterly_health_scores,
)
from application.jobs.data_quality_audit_job import audit_company_data_quality

logger = logging.getLogger(__name__)


def _map_quote_type(quote_type: Optional[str]) -> str:
    """Map yfinance quoteType to the companies.security_type enum."""
    if not quote_type:
        return "stock"
    mapping = {
        "EQUITY": "stock",
        "ETF": "etf",
        "MUTUALFUND": "fund",
        "INDEX": "index",
        "CRYPTOCURRENCY": "crypto",
        "CURRENCY": "currency",
        "FUTURE": "stock",
    }
    return mapping.get(quote_type.upper(), "stock")


class WatchlistService:
    """
    Manages watchlist operations, including add flow with fast path (YF market price)
    and background fundamentals loading (DefeatBeta -> fallback YF).
    Also triggers Rule #1 intrinsic value computation after fundamentals ingestion.
    """

    def __init__(
        self,
        stock_provider: StockProvider,
        watchlist_repo: WatchlistRepository,
        user_repo: UserRepository,
        defeat_beta_provider: DefeatBetaProvider,
        financial_repo: Optional[SupabaseFinancialRepository] = None,
    ):
        self.stock_provider = stock_provider
        self.watchlist_repo = watchlist_repo
        self.user_repo = user_repo
        self.defeat_beta_provider = defeat_beta_provider
        self.financial_repo = financial_repo or SupabaseFinancialRepository()

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

        if not watchlist:
            # If no default is marked, do NOT create a duplicate watchlist for existing users.
            # Use the first watchlist if any exist; only create if none exist.
            existing = self.watchlist_repo.find_by_user_id(db_user_id) or []
            watchlist = existing[0] if existing else None

        if watchlist:
            watchlist_id = watchlist['id']
            watchlist_name = watchlist['watchlist_name']
            is_default = watchlist.get('is_default', False)
        else:
            new_watchlist = self.watchlist_repo.create_default(db_user_id, "My Watchlist")
            watchlist_id = new_watchlist['id']
            watchlist_name = new_watchlist['watchlist_name']
            is_default = new_watchlist.get('is_default', True)

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

        # Fetch CDR ratios and exchange overrides for CDR pricing
        cdr_ratios = {}
        exchange_overrides = {}
        if company_ids:
            try:
                comp_res = supabase.table('companies').select('company_id, cdr_ratio, exchange').in_('company_id', company_ids).execute()
                for row in (comp_res.data or []):
                    cid = row['company_id']
                    ratio = row.get('cdr_ratio')
                    if ratio is not None:
                        cdr_ratios[cid] = float(ratio)
            except Exception:
                pass
            # Check portfolio_holdings for exchange_override
            try:
                holdings_res = supabase.table('portfolio_holdings').select('company_id, exchange_override').in_('company_id', company_ids).execute()
                for row in (holdings_res.data or []):
                    cid = row['company_id']
                    exch = row.get('exchange_override')
                    if exch:
                        exchange_overrides[cid] = exch
            except Exception:
                pass

        # 4. Combine data
        stocks_list = []
        for item in raw_watchlist_items:
            company = item.get('companies')
            if not company:
                continue

            ticker_symbol = company['ticker_symbol']
            ticker_data = all_tickers_data.get(ticker_symbol)
            cid = company['company_id']

            current_price = None
            previous_close = None
            last_updated = None

            if ticker_data:
                current_price = ticker_data.info.get('currentPrice') or ticker_data.info.get('regularMarketPrice')
                previous_close = ticker_data.info.get('previousClose') or ticker_data.info.get('regularMarketPreviousClose')

            db_market_data = market_data_map.get(cid)
            if db_market_data:
                last_updated = db_market_data.get('last_updated')
                if current_price is None or previous_close is None:
                    current_price = float(db_market_data.get('current_price', 0))
                    previous_close = float(db_market_data.get('close_price')) if db_market_data.get('close_price') else current_price

            if current_price is None or previous_close is None:
                continue

            # Apply CDR adjustment if this is a CDR holding
            if exchange_overrides.get(cid) == "TOR":
                from shared.snapshot_builder import CDR_RATIO as _CDR_RATIO
                ratio = cdr_ratios.get(cid, float(_CDR_RATIO))
                current_price = current_price / ratio
                previous_close = previous_close / ratio

            change = current_price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else 0

            stocks_list.append(StockPriceInfo(
                id=item['watchlist_item_id'],
                symbol=ticker_symbol,
                name=company['company_name'],
                sector=company.get('sector'),
                industry=company.get('industry'),
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
    # Phase 2: Fast watchlist STRUCTURE (no price enrichment)
    # ========================================================================
    def get_default_watchlist_structure(self, firebase_uid: str) -> Dict[str, Any]:
        """
        Fast path for initial watchlist render:
        - Returns watchlist + items WITH prices from current_market_data
        - No YFinance calls (reads cached DB data via shared snapshot builder)
        - Prices appear at first paint (~200-300ms)
        """
        db_user_id = self.get_db_user_id(firebase_uid)

        # 1) Find or Create Default Watchlist
        watchlist = self.watchlist_repo.find_default_by_user_id(db_user_id)
        if not watchlist:
            existing = self.watchlist_repo.find_by_user_id(db_user_id) or []
            watchlist = existing[0] if existing else None

        if watchlist:
            watchlist_id = watchlist["id"]
            watchlist_name = watchlist["watchlist_name"]
            is_default = watchlist.get("is_default", False)
        else:
            new_watchlist = self.watchlist_repo.create_default(db_user_id, "My Watchlist")
            watchlist_id = new_watchlist["id"]
            watchlist_name = new_watchlist["watchlist_name"]
            is_default = new_watchlist.get("is_default", True)

        # 2) Fetch Watchlist Items (structure only)
        raw_items = self.watchlist_repo.get_items_by_watchlist_id(watchlist_id)
        stocks: List[Dict[str, Any]] = []

        for item in raw_items or []:
            company = item.get("companies")
            if not company:
                continue

            stocks.append(
                {
                    "id": item["watchlist_item_id"],
                    "companyId": company["company_id"],
                    "symbol": company["ticker_symbol"],
                    "name": company["company_name"],
                    "sector": company.get("sector"),
                    "industry": company.get("industry"),
                    "targetBuy": item.get("target_buy"),
                    "targetSell": item.get("target_sell"),
                    "price": None,
                    "change": None,
                    "changePercent": None,
                    "isStale": False,
                    "lastUpdated": None,
                }
            )

        # 3) Enrich with prices from current_market_data (batch, sub-50ms)
        if stocks:
            company_ids = [s["companyId"] for s in stocks]
            snapshots = build_price_snapshot(supabase, company_ids, source="db_cached")

            for s in stocks:
                snap = snapshots.get(s["companyId"])
                if not snap:
                    continue
                s["price"] = snap["price"]
                s["change"] = snap["change"]
                s["changePercent"] = snap["changePercent"]
                s["isStale"] = snap["isStale"]
                s["lastUpdated"] = snap["lastUpdated"]

        return {
            "watchlist_id": watchlist_id,
            "name": watchlist_name,
            "is_default": is_default,
            "stocks": stocks,
        }

    def get_watchlist_structure_by_id(self, firebase_uid: str, watchlist_id: int) -> Dict[str, Any]:
        """Get structure (symbols + targets) for a specific watchlist by ID."""
        db_user_id = self.get_db_user_id(firebase_uid)

        watchlist = (
            supabase.table("watchlists")
            .select("id, watchlist_name, is_default, user_id")
            .eq("id", watchlist_id)
            .limit(1)
            .execute()
        ).data[0] if True else None

        if not watchlist or watchlist["user_id"] != db_user_id:
            raise NotFoundError("Watchlist not found")

        raw_items = self.watchlist_repo.get_items_by_watchlist_id(watchlist_id)

        stocks = []
        for item in raw_items or []:
            company = item.get("companies")
            if not company:
                continue
            stocks.append({
                "id": item["watchlist_item_id"],
                "symbol": company["ticker_symbol"],
                "name": company["company_name"],
                "sector": company.get("sector"),
                "industry": company.get("industry"),
                "targetBuy": item.get("target_buy"),
                "targetSell": item.get("target_sell"),
                "price": None,
                "change": None,
                "changePercent": None,
                "lastUpdated": None,
            })

        return {
            "watchlist_id": watchlist_id,
            "name": watchlist["watchlist_name"],
            "is_default": watchlist.get("is_default", False),
            "stocks": stocks,
        }


    # ========================================================================
    # NEW METHODS - Financial Data Integration
    # ========================================================================

    async def add_stock_to_watchlist(
        self,
        user_id: int,
        symbol: str,
        watchlist_id: int,
        target_buy: Optional[float] = None,
        target_sell: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Add a stock to the given watchlist with fast path + background fundamentals.

        Phase 1 (Fast):
          - Get/create company
          - YF -> current price (no fundamentals)
          - Upsert public.current_market_data
          - Insert into watchlist_items
          - Return payload to client

        Phase 2 (Background):
          - DefeatBetaProvider.get_all_financials_optimized(...)
            * DefeatBeta first
            * Fallback to YF if DBeta returns empty/timeouts
          - Upsert all fundamentals tables
          - Update companies refresh metadata
          - (NEW) Auto-compute Rule #1 intrinsic value

        Args:
            user_id: User adding stock
            symbol: Stock ticker symbol (e.g., 'TSLA')
            watchlist_id: Watchlist to add to
            target_buy: Optional target buy price to persist
            target_sell: Optional target sell price to persist

        Returns:
            Response with stock data and loading status
        """
        logger.info(f"Adding {symbol} to watchlist {watchlist_id} for user {user_id}")

        try:
            # 1) Get or create the company
            company = await self._get_or_create_company(symbol)
            company_id = company["company_id"]
            logger.debug("Company %s: ID=%s", symbol, company_id)

            # 2) YF -> current price (fast)
            current_price: Optional[float] = None
            try:
                sd = self.stock_provider.get_stock_details(symbol)
                current_price = sd.price if sd and (sd.price is not None) else None
            except Exception as e:
                logger.warning("Failed to fetch current price for %s: %s", symbol, str(e))
                current_price = None

            # 3) Upsert current_market_data from YF (leave timestamp to DB default)
            if current_price is not None:
                await self._update_market_data(company_id, symbol, current_price)

            # 4) Insert into watchlist_items
            watchlist_item = await self._add_watchlist_item(
                watchlist_id, company_id, target_buy, target_sell
            )

            # 5) Check refresh info to determine "new company" (first-time fundamentals)
            refresh_info = await self.financial_repo.get_company_refresh_info(company_id)
            is_new_company = refresh_info.first_financial_data_loaded_at is None

            logger.info("✅ Added %s to watchlist (fast path). New company: %s", symbol, is_new_company)

            # 6) Schedule background fundamentals load (always)
            asyncio.create_task(
                self._fetch_and_store_financials_optimized(
                    symbol=symbol,
                    company_id=company_id,
                    is_new_company=is_new_company,  # full if new; incremental otherwise
                )
            )
            logger.debug("[WATCHLIST][%s] Background task started (is_new=%s)", symbol, is_new_company)

            # 6b) Schedule background valuation computation
            asyncio.create_task(
                self._compute_valuations_background(symbol=symbol, user_id=user_id)
            )
            logger.debug("[WATCHLIST][%s] Background valuation computation scheduled", symbol)

            # 7) Calculate change data from price info
            prev_close = getattr(sd, 'previous_close', None) if sd else None
            if current_price and prev_close:
                change = float(current_price) - float(prev_close)
                pct = (float(change) / float(prev_close)) * 100
            else:
                change = 0.0
                pct = 0.0

            # 8) Return payload with complete data for API
            return {
                "watchlist_item_id": watchlist_item["watchlist_item_id"],
                "company_id": company_id,
                "symbol": symbol,
                "company_name": company.get("company_name"),
                "current_price": current_price,
                "previous_close": prev_close,
                "change": change,
                "change_percent": pct,
                "financials_loading": True,
                "is_new_stock": is_new_company,
                "message": "Stock added. Loading financial data...",
            }

        except Exception as e:
            logger.error("Failed to add %s to watchlist: %s", symbol, str(e))
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

        Returns:
            Summary of refresh operation
        """
        logger.info(f"On-demand refresh for {symbol} (company_id={company_id})")

        try:
            # Get refresh info to determine filtering
            refresh_info = await self.financial_repo.get_company_refresh_info(company_id)

            # Fetch with smart filtering (always incremental for on-demand)
            financials = await self.defeat_beta_provider.get_all_financials_optimized(
                symbol=symbol,
                company_id=company_id,
                last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
                last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
                force_full_history=False,
            )

            # Store everything
            upsert_results = await self.financial_repo.upsert_all_financials(financials)

            # Update metadata (derive latest from IS if available)
            last_fy = refresh_info.last_refreshed_fiscal_year
            last_fq = refresh_info.last_refreshed_fiscal_quarter
            if financials.income_statements.rows:
                latest = max(
                    financials.income_statements.rows,
                    key=lambda r: (r.fiscal_year or 0, r.fiscal_quarter or 0)
                )
                last_fy = latest.fiscal_year
                last_fq = latest.fiscal_quarter

            await self.financial_repo.update_company_refresh_metadata(
                company_id=company_id,
                last_fiscal_year=last_fy or 2024,  # default safe guard
                last_fiscal_quarter=last_fq,
                is_first_load=False,
                next_earnings_date=financials.next_earnings_date,
            )

            total_rows = sum(upsert_results.values())
            logger.info("✅ On-demand refresh complete for %s: %s rows", symbol, total_rows)

            # ── Price History Load (incremental, no benchmark) ────────────
            await self._fetch_and_store_price_history(symbol, company_id, refresh_info, is_new_company=False)

            # NEW: Derived metrics compute after fundamentals refresh (non-blocking)
            try:
                await compute_and_upsert_derived_financial_metrics(company_id=company_id)
                logger.info("[DERIVED] metrics computed after on-demand refresh for %s", symbol)
            except Exception as de:
                logger.error("[DERIVED] compute failed after on-demand refresh for %s: %s", symbol, de)

            # Quarterly health scores — Piotroski F, Altman Z, quarterly ratios
            try:
                await compute_and_upsert_quarterly_health_scores(company_id=company_id)
                logger.info("[QHLTH] quarterly health scores computed after on-demand refresh for %s", symbol)
            except Exception as qe:
                logger.error("[QHLTH] compute failed after on-demand refresh for %s: %s", symbol, qe)

            # PHASE 8: Data quality audit (non-blocking)
            try:
                await audit_company_data_quality(company_id=company_id)
                logger.info("[DQ] audit complete after on-demand refresh for %s", symbol)
            except Exception as qe:
                logger.error("[DQ] audit failed after on-demand refresh for %s: %s", symbol, qe)

            # ── Auto-compute all valuation methods after on-demand refresh ─────────
            # On-demand refresh means the user explicitly requested fresh data.
            # Fundamentals have changed → force recompute all methods unconditionally.
            val_repo = ValuationRepository()
            guard    = RecomputeGuard(val_repo)
            vs       = ValuationService(val_repo, guard)
    
            try:
                await vs.compute_rule1_if_stale(
                    symbol=symbol, user_id=None, overrides=None, force=True
                )
                logger.info("[VALUATION] Rule #1 computed after on-demand refresh for %s", symbol)
            except Exception as ve:
                logger.error("[VALUATION] Rule #1 auto-compute (on-demand) failed for %s: %s", symbol, ve)
    
            try:
                await vs.compute_dcf_if_stale(
                    symbol=symbol, user_id=None, overrides=None, force=True
                )
                logger.info("[VALUATION] DCF computed after on-demand refresh for %s", symbol)
            except Exception as ve:
                logger.error("[VALUATION] DCF auto-compute (on-demand) failed for %s: %s", symbol, ve)
    
            try:
                await vs.compute_owner_earnings_if_stale(
                    symbol=symbol, user_id=None, overrides=None, force=True
                )
                logger.info("[VALUATION] OE computed after on-demand refresh for %s", symbol)
            except Exception as ve:
                logger.error("[VALUATION] OE auto-compute (on-demand) failed for %s: %s", symbol, ve)
    
            try:
                await vs.compute_ddm_if_stale(
                    symbol=symbol, user_id=None, variant="gordon", overrides=None, force=True
                )
                logger.info("[VALUATION] DDM computed after on-demand refresh for %s", symbol)
            except Exception as ve:
                logger.error("[VALUATION] DDM auto-compute (on-demand) failed for %s: %s", symbol, ve)
    
            try:
                await vs.compute_residual_income_if_stale(
                    symbol=symbol, user_id=None, overrides=None, force=True
                )
                logger.info("[VALUATION] RI computed after on-demand refresh for %s", symbol)
            except Exception as ve:
                logger.error("[VALUATION] RI auto-compute (on-demand) failed for %s: %s", symbol, ve)

            return {
                "symbol": symbol,
                "company_id": company_id,
                "fetched_at": financials.fetched_at.isoformat(),
                "rows_upserted": upsert_results,
                "total_rows": total_rows,
                "next_earnings_date": (
                    financials.next_earnings_date.isoformat() if financials.next_earnings_date else None
                ),
            }

        except Exception as e:
            logger.error("On-demand refresh failed for %s: %s", symbol, str(e))
            raise

    # ========================================================================
    # PRIVATE HELPER METHODS
    # ========================================================================

    async def _get_or_create_company(self, symbol: str) -> Dict[str, Any]:
        """Get existing company or create new one."""
        try:
            existing = await self.financial_repo.get_company_by_symbol(symbol)
            if existing:
                logger.debug("Company %s already exists: ID=%s", symbol, existing["company_id"])
                return existing

            logger.debug("Creating new company for %s", symbol)
            sd = self.stock_provider.get_stock_details(symbol)
            if not sd:
                raise ExternalServiceError(f"Unable to fetch details for {symbol}")

            # Upsert currency first to keep referential data consistent (optional, but clean)
            if sd.currency:
                try:
                    supabase.table("currencies").upsert(
                        {"code": sd.currency, "name": sd.currency}, on_conflict="code"
                    ).execute()
                except Exception as e:
                    logger.debug("Currencies upsert failed for %s: %s", sd.currency, e)

            payload = {
                "ticker_symbol": symbol,
                "company_name": sd.long_name or symbol,
                "exchange": sd.exchange or "UNKNOWN",
                "sector": sd.sector,
                "industry": sd.industry,
                "currency": sd.currency or "USD",
                "next_earnings_date": sd.next_earnings_date.isoformat() if sd.next_earnings_date else None,
                "description": sd.description,
                "website": sd.website,
                "security_type": _map_quote_type(sd.quote_type),
            }

            res = supabase.table("companies").insert(payload).execute()
            created = res.data[0] if res.data else None
            if not created:
                raise ExternalServiceError(f"Failed to create company for {symbol}")

            logger.info("✅ Created company %s: ID=%s", symbol, created["company_id"])
            return created

        except Exception as e:
            logger.error("Failed to get/create company %s: %s", symbol, str(e))
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
        self, watchlist_id: int, company_id: int, target_buy: Optional[float],
        target_sell: Optional[float],
    ) -> Dict[str, Any]:
        """
        Insert into watchlist_items with default position=0.
        """
        try:
            res = supabase.table("watchlist_items").insert(
                {
                    "watchlist_id": watchlist_id,
                    "company_id": company_id,
                    "position": 0,
                    "target_buy": target_buy,
                    "target_sell": target_sell
                }
            ).execute()
            if not res.data:
                # Second-chance: detect duplicate gracefully for better error messaging
                dup = (
                    supabase.table("watchlist_items")
                    .select("*")
                    .eq("watchlist_id", watchlist_id)
                    .eq("company_id", company_id)
                    .execute()
                )
                if dup.data:
                    raise ExternalServiceError("This stock is already in your watchlist.")
                raise ExternalServiceError("Failed to add item to watchlist.")

            return res.data[0]

        except Exception as e:
            error_msg = str(e)
            # Check for duplicate key constraint violation
            if '23505' in error_msg or 'unique_watchlist_company' in error_msg:
                raise ExternalServiceError("This stock is already in your watchlist.")
            logger.error("Failed to add watchlist item: %s", error_msg)
            raise

    async def _fetch_and_store_financials_optimized(
        self,
        symbol: str,
        company_id: int,
        is_new_company: bool = False,
    ) -> None:
        """
        Background task: Fetch & store fundamentals via unified provider.
        - Full history if new company
        - Incremental otherwise
        - NEW: Auto-compute Rule #1 intrinsic value after successful ingestion
        """
        try:
            logger.info("Starting background financial load for %s (new_company=%s)", symbol, is_new_company)

            refresh_info = await self.financial_repo.get_company_refresh_info(company_id)
            logger.debug(
                "[WATCHLIST][%s] Requesting via DefeatBetaProvider "
                "(last_fy=%s, last_fq=%s, force_full=%s)",
                symbol,
                refresh_info.last_refreshed_fiscal_year,
                refresh_info.last_refreshed_fiscal_quarter,
                is_new_company,
            )

            financials = await self.defeat_beta_provider.get_all_financials_optimized(
                symbol=symbol,
                company_id=company_id,
                last_refreshed_fiscal_year=refresh_info.last_refreshed_fiscal_year,
                last_refreshed_fiscal_quarter=refresh_info.last_refreshed_fiscal_quarter,
                force_full_history=is_new_company,
            )

            upsert_results = await self.financial_repo.upsert_all_financials(financials)

            # Compute metadata from IS last row (if present)
            last_fy = refresh_info.last_refreshed_fiscal_year
            last_fq = refresh_info.last_refreshed_fiscal_quarter
            if financials.income_statements.rows:
                latest = max(
                    financials.income_statements.rows,
                    key=lambda r: (r.fiscal_year or 0, r.fiscal_quarter or 0)
                )
                last_fy = latest.fiscal_year
                last_fq = latest.fiscal_quarter

            await self.financial_repo.update_company_refresh_metadata(
                company_id=company_id,
                last_fiscal_year=last_fy or 2024,
                last_fiscal_quarter=last_fq,
                is_first_load=is_new_company,
                next_earnings_date=financials.next_earnings_date,
            )

            total_rows = sum(upsert_results.values())
            logger.info("✅ Background load complete for %s: %s total rows upserted", symbol, total_rows)

            # ── Price History Load ─────────────────────────────────────────
            # Fetch and store price history (monthly bars for CANSLIM N/L analysis)
            await self._fetch_and_store_price_history(symbol, company_id, refresh_info, is_new_company)

            # NEW: Derived metrics compute after fundamentals ingestion (non-blocking)
            try:
                await compute_and_upsert_derived_financial_metrics(company_id=company_id)
                logger.info("[DERIVED] metrics computed after fundamentals ingestion for %s", symbol)
            except Exception as de:
                logger.error("[DERIVED] compute failed after fundamentals ingestion for %s: %s", symbol, de)

            # Quarterly health scores — Piotroski F, Altman Z, quarterly ratios
            try:
                await compute_and_upsert_quarterly_health_scores(company_id=company_id)
                logger.info("[QHLTH] quarterly health scores computed after fundamentals ingestion for %s", symbol)
            except Exception as qe:
                logger.error("[QHLTH] compute failed after fundamentals ingestion for %s: %s", symbol, qe)
                
            # PHASE 8: Data quality audit (non-blocking)
            try:
                await audit_company_data_quality(company_id=company_id)  
                logger.info("[DQ] audit complete after fundamentals ingestion for %s", symbol)
            except Exception as qe:
                logger.error("[DQ] audit failed after fundamentals ingestion for %s: %s", symbol, qe)  
            # ── Auto-compute all valuation methods (new company only) ──────────────
            # Runs only when is_new_company=True. If the stock already existed in the
            # companies table, Gate 1 will serve the cached results from a prior run —
            # no computation needed and this block is never reached for existing stocks.
            if is_new_company:
                val_repo = ValuationRepository()
                guard    = RecomputeGuard(val_repo)
                vs       = ValuationService(val_repo, guard)
                # Lazy import to avoid circular dependency with api.watchlists
                from api.watchlists import broadcast_valuation_ready
    
                # Priority 1: Rule #1 — fastest, EPS-only, user sees something first
                try:
                    await vs.compute_rule1_if_stale(
                        symbol=symbol, user_id=None, overrides=None, force=True
                    )
                    logger.info("[VALUATION] Rule #1 computed after fundamentals ingestion for %s", symbol)
                    try:
                        await broadcast_valuation_ready(symbol, "rule1", company_id)
                    except Exception as be:
                        logger.debug("[SSE] broadcast_valuation_ready(rule1) failed (non-fatal): %s", be)
                except Exception as ve:
                    logger.error("[VALUATION] Rule #1 auto-compute failed for %s: %s", symbol, ve)
    
                # Priority 2: DCF — most universally applicable
                try:
                    await vs.compute_dcf_if_stale(
                        symbol=symbol, user_id=None, overrides=None, force=True
                    )
                    logger.info("[VALUATION] DCF computed after fundamentals ingestion for %s", symbol)
                    try:
                        await broadcast_valuation_ready(symbol, "dcf", company_id)
                    except Exception as be:
                        logger.debug("[SSE] broadcast_valuation_ready(dcf) failed (non-fatal): %s", be)
                except Exception as ve:
                    logger.error("[VALUATION] DCF auto-compute failed for %s: %s", symbol, ve)
    
                # Priority 3: Owner Earnings — shares CF inputs with DCF
                try:
                    await vs.compute_owner_earnings_if_stale(
                        symbol=symbol, user_id=None, overrides=None, force=True
                    )
                    logger.info("[VALUATION] Owner Earnings computed after fundamentals ingestion for %s", symbol)
                    try:
                        await broadcast_valuation_ready(symbol, "owner_earnings", company_id)
                    except Exception as be:
                        logger.debug("[SSE] broadcast_valuation_ready(owner_earnings) failed (non-fatal): %s", be)
                except Exception as ve:
                    logger.error("[VALUATION] OE auto-compute failed for %s: %s", symbol, ve)
    
                # Priority 4: DDM — only meaningful if dividends exist, but run anyway
                # so the UI shows a proper "not applicable" result rather than NOT RUN
                try:
                    await vs.compute_ddm_if_stale(
                        symbol=symbol, user_id=None, variant="gordon", overrides=None, force=True
                    )
                    logger.info("[VALUATION] DDM computed after fundamentals ingestion for %s", symbol)
                    try:
                        await broadcast_valuation_ready(symbol, "ddm_gordon", company_id)
                    except Exception as be:
                        logger.debug("[SSE] broadcast_valuation_ready(ddm_gordon) failed (non-fatal): %s", be)
                except Exception as ve:
                    logger.error("[VALUATION] DDM auto-compute failed for %s: %s", symbol, ve)
    
                # Priority 5: Residual Income — most data-intensive, runs last
                try:
                    await vs.compute_residual_income_if_stale(
                        symbol=symbol, user_id=None, overrides=None, force=True
                    )
                    logger.info("[VALUATION] Residual Income computed after fundamentals ingestion for %s", symbol)
                    try:
                        await broadcast_valuation_ready(symbol, "residual_income", company_id)
                    except Exception as be:
                        logger.debug("[SSE] broadcast_valuation_ready(residual_income) failed (non-fatal): %s", be)
                except Exception as ve:
                    logger.error("[VALUATION] RI auto-compute failed for %s: %s", symbol, ve)
    
            else:
                # Existing company — financial data may have been refreshed incrementally.
                # Gate 1/2/3 will determine on next user request whether recompute is needed.
                # No forced recompute here to avoid unnecessary work.
                logger.debug(
                    "[VALUATION] Skipping auto-compute for %s — existing company, gates will handle staleness",
                    symbol,
                )

        except Exception as e:
            logger.error("Background financial load failed for %s: %s", symbol, str(e))
            # Swallow to avoid impacting user-facing flows

    # ========================================================================
    # PRICE HISTORY METHODS
    # ========================================================================

    async def _fetch_and_store_price_history(
        self,
        symbol: str,
        company_id: int,
        refresh_info: Any,
        is_new_company: bool,
    ) -> None:
        """
        Fetch and store price history (monthly bars for CANSLIM N/L analysis).
        - Full bootstrap if no history exists or is_new_company
        - Incremental from last_price_refresh_at otherwise
        """
        try:
            has_price = await self._has_price_history(company_id)
            is_full_load = not has_price or is_new_company

            if is_full_load:
                # Full bootstrap (first time ever for this company)
                daily_rows = await self.defeat_beta_provider.get_price_history_optimized(
                    symbol=symbol, company_id=company_id
                )
                logger.info("[PRICE_HISTORY][%s] Full bootstrap: %d daily rows", symbol, len(daily_rows or []))
            else:
                # Incremental from last refresh marker
                start_date = refresh_info.last_price_refresh_at.date() if refresh_info.last_price_refresh_at else None
                if start_date:
                    daily_rows = await self.defeat_beta_provider.get_price_history_optimized(
                        symbol=symbol, company_id=company_id, start_date=start_date
                    )
                else:
                    daily_rows = []
                logger.info("[PRICE_HISTORY][%s] Incremental from %s: %d daily rows",
                          symbol, start_date, len(daily_rows or []))

            monthly_rows = self._compress_daily_to_monthly_eom(daily_rows or [])

            if monthly_rows:
                await self.financial_repo.upsert_price_history(monthly_rows)
                await self.financial_repo.update_price_refresh_marker(company_id)
                logger.info("[PRICE_HISTORY][%s] ✅ %d monthly rows upserted (full=%s)",
                         symbol, len(monthly_rows), is_full_load)
            else:
                logger.info("[PRICE_HISTORY][%s] No monthly rows to upsert", symbol)

        except Exception as e:
            logger.warning("[PRICE_HISTORY][%s] Failed: %s", symbol, e)

    async def _has_price_history(self, company_id: int) -> bool:
        """Check if any price_history exists for company."""
        try:
            resp = (
                supabase.table("price_history")
                .select("price_date")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            return bool(resp.data)
        except Exception as e:
            logger.debug("_has_price_history failed for %s: %s", company_id, e)
            return False

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
        df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
        df = df.dropna(subset=["price_date"])
        if df.empty:
            return []
        df["year"] = df["price_date"].dt.year
        df["month"] = df["price_date"].dt.month
        idx = df.groupby(["year", "month"])["price_date"].idxmax()
        last_trading_rows = df.loc[idx].copy()
        out: List[Dict[str, Any]] = []
        for _, r in last_trading_rows.iterrows():
            def _safe_num(v: Any) -> Optional[float]:
                if v is None:
                    return None
                try:
                    f = float(v)
                    return f if f == f else None
                except (ValueError, TypeError):
                    return None
            out.append({
                "company_id": int(r.get("company_id")),
                "price_date": r["price_date"].date(),
                "open_price": _safe_num(r.get("open_price")),
                "close_price": _safe_num(r.get("close_price")),
                "high_price": _safe_num(r.get("high_price")),
                "low_price": _safe_num(r.get("low_price")),
                "volume": int(r.get("volume")) if pd.notna(r.get("volume")) else None,
                "data_source": str(r.get("data_source") or "defeatbeta"),
            })
        out.sort(key=lambda x: x["price_date"])
        return out

    async def _compute_valuations_background(self, symbol: str, user_id: int) -> None:
        try:
            from application.schedulers.valuation_computation_scheduler import ValuationComputationScheduler
            scheduler = ValuationComputationScheduler()
            await scheduler.compute_all(symbol=symbol, user_id=user_id, force=False)
            logger.info("Background valuation computation completed for %s", symbol)
        except Exception as e:
            logger.warning("Background valuation computation failed for %s: %s", symbol, e)