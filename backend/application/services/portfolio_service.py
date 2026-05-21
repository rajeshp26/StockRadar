# backend/application/services/portfolio_service.py
"""
Portfolio Service

Business logic for portfolio management:
- Import transactions from CSV
- Calculate current holdings from transactions (FIFO cost basis)
- Compute portfolio performance metrics
- Link stocks to companies table (auto-create if needed)
- Extract and track dividend payments
"""

from application.services import owner_earnings_suitability
import asyncio
import logging
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from application.parsers.portfolio_parser import (
    ParsedTransaction,
    ParseResult,
    get_parser,
)
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from providers.yfinance_provider import YFinanceProvider
from providers.base import StockDataProvider
from database import supabase

logger = logging.getLogger(__name__)


class PortfolioService:
    """Service for portfolio operations following existing service patterns."""
    
    def __init__(
        self,
        portfolio_repo: Optional[PortfolioRepository] = None,
        financial_repo: Optional[SupabaseFinancialRepository] = None,
        stock_provider: Optional[StockDataProvider] = None,
    ):
        self.portfolio_repo = portfolio_repo or PortfolioRepository()
        self.financial_repo = financial_repo or SupabaseFinancialRepository()
        self.stock_provider = stock_provider or YFinanceProvider()
    

    # ========================================================================
    # DUPLICATE DETECTION
    # ========================================================================
    
    def _calculate_csv_hash(self, csv_content: str) -> str:
        """Calculate SHA-256 hash of CSV content for duplicate detection."""
        return hashlib.sha256(csv_content.encode('utf-8')).hexdigest()
    
    async def check_duplicate_import(
        self, user_id: int, csv_hash: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check if this CSV has been imported before.
        
        Returns:
            Previous import record if found, None otherwise
        """
        try:
            res = (
                supabase.table("portfolio_import_history")
                .select("*")
                .eq("user_id", user_id)
                .eq("csv_hash", csv_hash)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Failed to check duplicate import: {e}")
            return None
    
    # ========================================================================
    # IMPORT OPERATIONS
    # ========================================================================

    async def queue_import(
        self,
        user_id: int,
        brokerage_code: str,
        csv_content: str,
        account_filter: Optional[List[str]] = None,
        csv_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Queue a CSV import for background processing.
        
        Validates input, creates a pending job record, and kicks off
        async background processing. Returns immediately.
        """
        csv_hash = self._calculate_csv_hash(csv_content)
        csv_size = len(csv_content.encode('utf-8'))
        import_batch_id = uuid.uuid4()

        # 1. Check for duplicate CSV
        previous_import = await self.check_duplicate_import(user_id, csv_hash)
        if previous_import:
            return {
                "success": False,
                "error": "This CSV file has already been imported",
                "duplicate_import": True,
                "previous_import_date": previous_import["started_at"],
                "previous_import_id": previous_import["import_id"],
                "warning": (
                    f"Previously imported on {previous_import['started_at']}: "
                    f"{previous_import['imported_rows']} transactions"
                ),
            }

        # 2. Validate brokerage
        brokerage = self.portfolio_repo.get_brokerage_by_code(brokerage_code)
        if not brokerage:
            return {"success": False, "error": f"Unsupported brokerage: {brokerage_code}"}

        brokerage_id = brokerage["brokerage_id"]

        # 3. Parse CSV (quick validation parse)
        parser = get_parser(brokerage_code)
        parse_result: ParseResult = parser.parse_csv(csv_content, account_filter)

        if not parse_result.success:
            return {
                "success": False,
                "error": "CSV parsing failed",
                "errors": parse_result.errors,
                "warnings": parse_result.warnings,
            }

        if not parse_result.transactions:
            return {
                "success": False,
                "error": "No transactions found in CSV",
                "warnings": parse_result.warnings,
            }

        total_rows = parse_result.total_rows

        # 4. Create pending import job
        import_id = self.portfolio_repo.create_import_job(
            import_batch_id=import_batch_id,
            user_id=user_id,
            brokerage_id=brokerage_id,
            csv_hash=csv_hash,
            csv_filename=csv_filename,
            csv_size_bytes=csv_size,
            total_rows=total_rows,
        )
        if import_id is None:
            return {"success": False, "error": "Failed to create import job"}

        logger.info(
            f"Queued import job {import_id} (batch {import_batch_id}) "
            f"for user {user_id}, brokerage: {brokerage_code}, "
            f"{len(parse_result.transactions)} transactions, hash: {csv_hash[:16]}..."
        )

        # 5. Start background processing
        asyncio.create_task(
            self._process_import_background(
                import_batch_id=import_batch_id,
                csv_hash=csv_hash,
                csv_size=csv_size,
                account_filter=account_filter,
                parse_result=parse_result,
                brokerage_id=brokerage_id,
                user_id=user_id,
            )
        )

        return {
            "success": True,
            "import_batch_id": str(import_batch_id),
            "status": "pending",
            "total_rows": total_rows,
            "account_types": parse_result.account_type_summary,
            "warnings": parse_result.warnings,
        }

    async def _process_import_background(
        self,
        import_batch_id: uuid.UUID,
        csv_hash: str,
        csv_size: int,
        account_filter: Optional[List[str]],
        parse_result: ParseResult,
        brokerage_id: int,
        user_id: int,
    ) -> None:
        """
        Process a queued CSV import in the background.
        Updates progress in portfolio_import_history throughout.
        """
        repo = self.portfolio_repo

        try:
            repo.update_import_progress(import_batch_id, status="processing", rows_parsed=0)

            # --- Create accounts ---
            accounts_map: Dict[str, int] = {}
            accounts_created = 0

            for tx in parse_result.transactions:
                ext_id = tx.account_external_id
                if ext_id not in accounts_map:
                    account = repo.get_or_create_account(
                        user_id=user_id,
                        brokerage_id=brokerage_id,
                        account_external_id=ext_id,
                        account_name=f"{tx.account_type} ({ext_id[-8:]})",
                        account_type=tx.account_type,
                        currency=tx.currency,
                    )
                    accounts_map[ext_id] = account["account_id"]
                    if account.get("created_at") == account.get("updated_at"):
                        accounts_created += 1

            repo.update_import_progress(import_batch_id, rows_parsed=len(parse_result.transactions))

            # --- Company lookup ---
            symbols_to_process = {tx.symbol for tx in parse_result.transactions if tx.symbol}
            companies_map, symbols_created = await self._ensure_companies_exist_with_tracking(
                symbols_to_process
            )

            # --- Convert to DB records ---
            db_transactions = []
            symbols_missing = set()

            for tx in parse_result.transactions:
                account_id = accounts_map[tx.account_external_id]
                company_id = None

                if tx.symbol:
                    company_id = companies_map.get(tx.symbol)
                    if not company_id:
                        symbols_missing.add(tx.symbol)

                db_transactions.append({
                    "account_id": account_id,
                    "company_id": company_id,
                    "transaction_date": tx.transaction_date.isoformat(),
                    "settlement_date": tx.settlement_date.isoformat() if tx.settlement_date else None,
                    "activity_type": tx.activity_type,
                    "activity_sub_type": tx.activity_sub_type,
                    "direction": tx.direction,
                    "symbol": tx.symbol,
                    "security_name": tx.security_name,
                    "currency": tx.currency,
                    "quantity": float(tx.quantity) if tx.quantity else None,
                    "unit_price": float(tx.unit_price) if tx.unit_price else None,
                    "commission": float(tx.commission),
                    "net_cash_amount": float(tx.net_cash_amount),
                    "raw_data": tx.raw_data,
                    "entry_source": "csv_import",
                    "created_by_user_id": None,
                })

            # --- Insert transactions ---
            inserted_count, duplicate_count = repo.insert_transactions_with_duplicates(
                db_transactions, import_batch_id, skip_duplicates=True
            )

            repo.update_import_progress(import_batch_id, rows_inserted=inserted_count)

            # --- Update account timestamps ---
            for account_id in accounts_map.values():
                repo.update_account_import_timestamp(account_id)

            # --- Recalculate holdings ---
            holdings_updated = 0
            for account_id in accounts_map.values():
                try:
                    await self._recalculate_account_holdings(account_id)
                    holdings_updated += 1
                except Exception as e:
                    logger.error(f"Failed to recalculate holdings for account {account_id}: {e}")

            # --- Extract dividends ---
            dividends_extracted = await self._extract_dividends(list(accounts_map.values()))

            # --- Finalize ---
            result = {
                "success": True,
                "import_batch_id": str(import_batch_id),
                "accounts_created": accounts_created,
                "accounts_updated": len(accounts_map),
                "transactions_imported": inserted_count,
                "transactions_duplicate": duplicate_count,
                "holdings_updated": holdings_updated,
                "dividends_extracted": dividends_extracted,
                "symbols_missing": list(symbols_missing),
                "symbols_created": symbols_created,
                "companies_created_count": len(symbols_created),
                "account_types": parse_result.account_type_summary,
                "warnings": list(parse_result.warnings),
            }

            warnings = list(parse_result.warnings)
            if symbols_created:
                warnings.append(
                    f"{len(symbols_created)} new compan{'y' if len(symbols_created) == 1 else 'ies'} "
                    f"created: {', '.join(symbols_created[:5])}"
                    + (f" and {len(symbols_created) - 5} more" if len(symbols_created) > 5 else "")
                )
            if duplicate_count > 0:
                warnings.append(f"{duplicate_count} duplicate transaction(s) were skipped")
            result["warnings"] = warnings

            repo.update_import_progress(
                import_batch_id,
                status="completed",
                rows_parsed=len(parse_result.transactions),
                rows_inserted=inserted_count,
            )

            logger.info(
                f"Background import {import_batch_id} complete: "
                f"{inserted_count} inserted, {duplicate_count} duplicates, "
                f"{holdings_updated} accounts updated"
            )

        except Exception as e:
            logger.error(f"Background import {import_batch_id} failed: {e}", exc_info=True)
            repo.update_import_progress(
                import_batch_id,
                status="failed",
                error_message=f"Import failed: {str(e)}",
            )
    
    async def _ensure_companies_exist_with_tracking(
        self, symbols: set[str]
    ) -> Tuple[Dict[str, int], List[str]]:
        """
        Ensure companies exist and track which were created.
        
        Returns:
            (companies_map, created_symbols)
        """
        if not symbols:
            return {}, []
        
        companies_map: Dict[str, int] = {}
        created_symbols: List[str] = []
        
        # Check existing
        try:
            res = (
                supabase.table("companies")
                .select("ticker_symbol, company_id")
                .in_("ticker_symbol", list(symbols))
                .execute()
            )
            for row in res.data or []:
                companies_map[row["ticker_symbol"]] = row["company_id"]
        except Exception as e:
            logger.error(f"Failed to check existing companies: {e}")
        
        # Create missing
        missing = symbols - companies_map.keys()
        if missing:
            logger.info(f"Creating {len(missing)} missing companies")
            for idx, symbol in enumerate(missing):
                try:
                    # Rate-limit: insert a small delay between provider calls to
                    # avoid triggering Yahoo Finance rate limiting (especially
                    # during CSV imports with many unique tickers).
                    if idx > 0:
                        await asyncio.sleep(0.5)
                    company_id = await self._create_company_from_symbol(symbol)
                    if company_id:
                        companies_map[symbol] = company_id
                        created_symbols.append(symbol)
                except Exception as e:
                    logger.error(f"Failed to create company for {symbol}: {e}")
        
        return companies_map, created_symbols
    
    # ========================================================================
    # HOLDINGS CALCULATION (FIFO Cost Basis)
    # ========================================================================
    
    async def _recalculate_account_holdings(self, account_id: int) -> None:
        """
        Recalculate holdings for an account using FIFO cost basis.
        
        Algorithm:
        1. Get all trade transactions (BUY/SELL) ordered by date
        2. Track lots (purchases) and apply FIFO matching on sells
        3. Calculate average cost, total cost, realized/unrealized gains
        4. Upsert holdings into portfolio_holdings table
        """
        logger.info(f"Recalculating holdings for account {account_id}")
        
        # Get all trade transactions
        transactions = self.portfolio_repo.get_account_transactions(
            account_id, activity_types=["Trade"]
        )
        
        if not transactions:
            logger.info(f"No trade transactions for account {account_id}")
            return
        
        # Group by symbol and calculate holdings
        holdings_by_symbol: Dict[str, Dict[str, Any]] = {}
        
        for symbol_group in self._group_by_symbol(transactions):
            symbol = symbol_group["symbol"]
            company_id = symbol_group["company_id"]
            tx_list = symbol_group["transactions"]
            
            # Look up missing company_id from companies table
            if company_id is None:
                company = await self.financial_repo.get_company_by_symbol(symbol)
                if company:
                    company_id = company["company_id"]
            
            if company_id is None:
                logger.warning(f"Skipping holding for {symbol}: no company found")
                continue
            
            holding = self._calculate_symbol_holding_fifo(
                symbol, company_id, tx_list
            )
            
            if holding and holding["quantity"] > 0:
                holdings_by_symbol[symbol] = holding
        
        # Delete old holdings for this account
        self.portfolio_repo.delete_account_holdings(account_id)
        
        # Insert new holdings
        for holding in holdings_by_symbol.values():
            holding["account_id"] = account_id
            holding["computed_at"] = datetime.now().isoformat()
            
            # Get current price for unrealized gain calculation
            try:
                price_data = await self._get_current_price(holding["symbol"])
                if price_data:
                    holding["current_price"] = price_data["price"]
                    holding["current_value"] = (
                        price_data["price"] * holding["quantity"]
                    )
                    holding["unrealized_gain_loss"] = (
                        holding["current_value"] - holding["total_cost"]
                    )
                    if holding["total_cost"] > 0:
                        holding["unrealized_gain_loss_pct"] = (
                            (holding["unrealized_gain_loss"] / holding["total_cost"]) * 100
                        )
            except Exception as e:
                logger.warning(f"Failed to get current price for {holding['symbol']}: {e}")
            
            self.portfolio_repo.upsert_holding(holding)
        
        logger.info(f"Holdings recalculated for account {account_id}: {len(holdings_by_symbol)} positions")
    
    def _group_by_symbol(
        self, transactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Group transactions by symbol."""
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        for tx in transactions:
            symbol = tx.get("symbol")
            if symbol:
                groups[symbol].append(tx)
        
        result = []
        for symbol, tx_list in groups.items():
            # Sort by date
            tx_list.sort(key=lambda x: (x["transaction_date"], x["transaction_id"]))
            
            # Get company_id from first transaction
            company_id = tx_list[0].get("company_id")
            
            result.append({
                "symbol": symbol,
                "company_id": company_id,
                "transactions": tx_list,
            })
        
        return result
    
    def _calculate_symbol_holding_fifo(
        self,
        symbol: str,
        company_id: Optional[int],
        transactions: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate current holding for a symbol using FIFO cost basis.
        
        Returns holding dict or None if position is closed.
        """
        lots: List[Dict[str, Any]] = []  # Purchase lots (FIFO queue)
        total_quantity = Decimal("0")
        total_cost = Decimal("0")
        realized_gain_loss = Decimal("0")
        first_purchase_date = None
        last_transaction_date = None
        
        for tx in transactions:
            tx_date = tx["transaction_date"]
            activity_sub = (tx.get("activity_sub_type") or "").upper()
            quantity = Decimal(str(tx.get("quantity") or 0))
            price = Decimal(str(tx.get("unit_price") or 0))
            commission = Decimal(str(tx.get("commission") or 0))
            
            if not quantity or not price:
                continue
            
            last_transaction_date = tx_date
            
            if activity_sub == "BUY":
                # Add new lot
                cost_per_share = price + (commission / quantity if quantity else 0)
                lots.append({
                    "quantity": quantity,
                    "cost_per_share": cost_per_share,
                    "date": tx_date,
                })
                total_quantity += quantity
                total_cost += quantity * cost_per_share
                
                if first_purchase_date is None:
                    first_purchase_date = tx_date
            
            elif activity_sub == "SELL":
                # Match against lots (FIFO)
                sell_qty = abs(quantity)
                remaining_to_sell = sell_qty
                sale_proceeds = sell_qty * price - commission
                cost_of_sold = Decimal("0")
                
                while remaining_to_sell > 0 and lots:
                    lot = lots[0]
                    
                    if lot["quantity"] <= remaining_to_sell:
                        # Sell entire lot
                        cost_of_sold += lot["quantity"] * lot["cost_per_share"]
                        remaining_to_sell -= lot["quantity"]
                        lots.pop(0)
                    else:
                        # Partial lot sale
                        cost_of_sold += remaining_to_sell * lot["cost_per_share"]
                        lot["quantity"] -= remaining_to_sell
                        remaining_to_sell = Decimal("0")
                
                realized_gain_loss += sale_proceeds - cost_of_sold
                total_quantity -= sell_qty
                total_cost -= cost_of_sold
        
        # No position left
        if total_quantity <= 0:
            return None
        
        # Calculate average cost
        average_cost = total_cost / total_quantity if total_quantity else Decimal("0")
        
        return {
            "symbol": symbol,
            "company_id": company_id,
            "quantity": float(total_quantity),
            "average_cost": float(average_cost),
            "total_cost": float(total_cost),
            "realized_gain_loss": float(realized_gain_loss),
            "first_purchase_date": first_purchase_date,
            "last_transaction_date": last_transaction_date,
            "currency": transactions[0].get("currency", "CAD"),
        }
    
    async def _get_current_price(self, symbol: str) -> Optional[Dict[str, float]]:
        """Get current price from current_market_data table."""
        try:
            # Get company_id
            company = await self.financial_repo.get_company_by_symbol(symbol)
            if not company:
                return None
            
            # Get price
            res = (
                supabase.table("current_market_data")
                .select("current_price")
                .eq("company_id", company["company_id"])
                .limit(1)
                .execute()
            )
            
            if res.data and res.data[0].get("current_price"):
                return {"price": float(res.data[0]["current_price"])}
        
        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")
        
        return None
    
    # ========================================================================
    # DIVIDEND EXTRACTION
    # ========================================================================
    
    async def _extract_dividends(self, account_ids: List[int]) -> int:
        """
        Extract dividend transactions and insert into portfolio_dividends table.
        
        Returns number of dividend records created.
        """
        dividend_records = []
        
        for account_id in account_ids:
            transactions = self.portfolio_repo.get_account_transactions(account_id)
            
            for tx in transactions:
                activity_type = tx.get("activity_type", "").upper()
                activity_sub = (tx.get("activity_sub_type") or "").upper()
                
                # Identify dividend transactions
                if activity_type == "DIVIDEND" or activity_sub in ["DIV", "DIST", "DIVIDEND"]:
                    payment_date = tx["transaction_date"]
                    amount = Decimal(str(tx.get("net_cash_amount") or 0))
                    
                    if amount > 0:  # Dividends are positive cash flow
                        dividend_records.append({
                            "account_id": account_id,
                            "company_id": tx.get("company_id"),
                            "transaction_id": tx["transaction_id"],
                            "symbol": tx.get("symbol"),
                            "payment_date": payment_date,
                            "amount": float(amount),
                            "currency": tx.get("currency", "CAD"),
                            "fiscal_year": payment_date.year if isinstance(payment_date, date) else datetime.fromisoformat(payment_date).year,
                            "fiscal_month": payment_date.month if isinstance(payment_date, date) else datetime.fromisoformat(payment_date).month,
                        })
        
        if dividend_records:
            return self.portfolio_repo.insert_dividends(dividend_records)
        
        return 0
    
    # ========================================================================
    # PORTFOLIO SUMMARY
    # ========================================================================
    
    async def get_user_portfolio_overview(self, user_id: int) -> Dict[str, Any]:
        """
        Get comprehensive portfolio overview for user.
        
        Returns:
            - Total net worth
            - YTD performance
            - Total gain/loss
            - Dividends (yearly)
            - Top holdings
            - Account breakdown
        """
        # Get all accounts
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        if not accounts:
            return {
                "success": False,
                "error": "No portfolio accounts found",
            }
        
        # Get all holdings
        holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        
        # Calculate totals
        total_value = sum(h.get("current_value") or 0 for h in holdings)
        total_cost = sum(h.get("total_cost") or 0 for h in holdings)
        total_gain_loss = total_value - total_cost
        total_gain_loss_pct = (
            (total_gain_loss / total_cost * 100) if total_cost > 0 else 0
        )
        
        # Get dividend summary for current year
        current_year = datetime.now().year
        ytd_dividends = Decimal("0")
        
        for account in accounts:
            account_divs = self.portfolio_repo.get_account_dividends_by_year(
                account["account_id"], current_year
            )
            ytd_dividends += sum(
                Decimal(str(d.get("amount") or 0)) for d in account_divs
            )
        
        # Top 10 holdings by value
        top_holdings = sorted(
            holdings, key=lambda h: h.get("current_value") or 0, reverse=True
        )[:10]
        
        # Account breakdown
        account_breakdown = []
        for account in accounts:
            acc_holdings = [
                h for h in holdings if h.get("account_id") == account["account_id"]
            ]
            acc_value = sum(h.get("current_value") or 0 for h in acc_holdings)
            acc_cost = sum(h.get("total_cost") or 0 for h in acc_holdings)
            
            account_breakdown.append({
                "account_id": account["account_id"],
                "account_name": account["account_name"],
                "account_type": account["account_type"],
                "brokerage_name": account.get("portfolio_brokerages", {}).get("brokerage_name"),
                "holdings_count": len(acc_holdings),
                "total_value": float(acc_value),
                "total_cost": float(acc_cost),
                "gain_loss": float(acc_value - acc_cost),
                "gain_loss_pct": (
                    float((acc_value - acc_cost) / acc_cost * 100) if acc_cost > 0 else 0
                ),
            })
        
        return {
            "success": True,
            "net_worth": float(total_value),
            "total_cost_basis": float(total_cost),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_pct": float(total_gain_loss_pct),
            "ytd_dividends": float(ytd_dividends),
            "total_holdings_count": len(holdings),
            "accounts_count": len(accounts),
            "top_holdings": top_holdings,
            "account_breakdown": account_breakdown,
        }
    # ========================================================================
    # MANUAL TRADE ENTRY
    # ========================================================================
    
    async def add_manual_transaction(
        self,
        user_id: int,
        account_id: int,
        transaction_date: date,
        activity_type: str,
        symbol: Optional[str],
        quantity: Optional[Decimal],
        unit_price: Optional[Decimal],
        commission: Decimal = Decimal("0"),
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a single transaction manually (no CSV).
        
        NOW RETURNS:
        - success: bool
        - transaction_id: int
        - transaction: dict
        - company_created: bool  # NEW
        - company_name: str      # NEW
        """
        try:
            # ... existing validation code ...
            
            # 3. Get/create company (TRACK IF CREATED)
            company_id = None
            company_created = False
            company_name = None
            
            if symbol:
                # Check if exists first
                existing_check = (
                    supabase.table("companies")
                    .select("company_id, company_name")
                    .eq("ticker_symbol", symbol)
                    .limit(1)
                    .execute()
                )
                
                if existing_check.data and len(existing_check.data) > 0:
                    # Company exists
                    company_id = existing_check.data[0]["company_id"]
                    company_name = existing_check.data[0]["company_name"]
                    company_created = False
                    logger.info(f"Using existing company: {symbol} (ID={company_id})")
                else:
                    # Need to create
                    logger.info(f"Creating new company for symbol: {symbol}")
                    company_id = await self._create_company_from_symbol(symbol)
                    
                    if company_id:
                        company_created = True
                        # Fetch the created company name
                        created_company = (
                            supabase.table("companies")
                            .select("company_name")
                            .eq("company_id", company_id)
                            .single()
                            .execute()
                        )
                        company_name = created_company.data.get("company_name", symbol) if created_company.data else symbol
                        logger.info(f"✅ Created new company: {company_name} (ID={company_id})")
            
            # ... rest of existing code to create transaction ...
            
            logger.info(
                f"Manual transaction created: {activity_type} {symbol} "
                f"for account {account_id} by user {user_id}"
                + (f" (NEW COMPANY: {company_name})" if company_created else "")
            )
            
            return {
                "success": True,
                "transaction_id": created_tx["transaction_id"],
                "transaction": created_tx,
                "company_created": company_created,      # NEW
                "company_name": company_name,            # NEW
            }
        
        except Exception as e:
            logger.error(f"Failed to add manual transaction: {e}", exc_info=True)
            return {"success": False, "error": f"Failed to create transaction: {str(e)}"}

    async def _create_company_from_symbol(self, symbol: str) -> Optional[int]:
        """
        Fetch company details from YFinance and create database record.
        
        Resilience features:
        1. Retry with .TO / .V suffix for Canadian-listed symbols when initial lookup fails
        2. Create a minimal company record when all provider lookups fail (so holdings
           calculations can proceed with a valid company_id)
        3. No crash on optional StockDetails fields (market_cap and full_time_employees
           are not part of the StockDetails model)
        
        Returns:
            company_id if successful, None if failed
        """
        try:
            # 1. Fetch from provider (YFinance / DefeatBeta)
            sd = self.stock_provider.get_stock_details(symbol)

            # 2. Retry with Canadian exchange suffixes if initial lookup fails
            if not sd:
                for suffix in [".TO", ".V"]:
                    sd = self.stock_provider.get_stock_details(symbol + suffix)
                    if sd:
                        logger.info(f"Resolved {symbol} → {symbol + suffix}")
                        break

            if not sd:
                # 3. Minimal record — no provider data available, but we still
                #    need a company_id so holdings calculation does not skip the symbol.
                logger.info(f"No stock details for {symbol}, creating minimal company record")
                payload = {
                    "ticker_symbol": symbol,
                    "company_name": symbol,
                    "exchange": "UNKNOWN",
                    "sector": None,
                    "industry": None,
                    "currency": "USD",
                    "description": None,
                    "website": None,
                }
            else:
                # Full company record from provider data
                # NOTE: StockDetails does not have market_cap / full_time_employees;
                #       those fields caused silent AttributeError crashes — intentionally omitted.
                payload = {
                    "ticker_symbol": symbol,
                    "company_name": sd.long_name or symbol,
                    "exchange": sd.exchange or "UNKNOWN",
                    "sector": sd.sector,
                    "industry": sd.industry,
                    "currency": sd.currency or "USD",
                    "description": sd.description,
                    "website": sd.website,
                }

            res = supabase.table("companies").insert(payload).execute()
            if not res.data:
                logger.error(f"Failed to insert company {symbol}")
                return None

            company_id = res.data[0]["company_id"]
            logger.info(f"Created company {symbol} (ID={company_id})")
            return company_id

        except Exception as e:
            logger.error(f"Failed to create company for {symbol}: {e}")
            return None

    # ========================================================================
    # PORTFOLIO PERFORMANCE
    # ========================================================================

    def _period_to_date_range(
        self, period: str, account_ids: Optional[List[int]] = None
    ) -> tuple[date, date]:
        """Convert period string to (start_date, end_date).

        For 'ALL' period, dynamically determines start from the earliest
        transaction date across the given accounts, falling back to a safe
        default if no account_ids or transactions exist.
        """
        end = datetime.now().date()
        p = period.upper()
        if p == "1D":
            start = end
        elif p == "1W":
            start = end - timedelta(days=7)
        elif p == "1M":
            start = end - timedelta(days=30)
        elif p == "3M":
            start = end - timedelta(days=90)
        elif p == "1Y":
            start = end - timedelta(days=365)
        elif p == "5Y":
            start = end - timedelta(days=1825)
        elif p == "YTD":
            start = date(end.year, 1, 1)
        else:  # ALL
            if account_ids:
                earliest = self.portfolio_repo.get_earliest_transaction_date(account_ids)
                if earliest is not None:
                    start = earliest
                    return start, end
            start = date(2000, 1, 1)
        return start, end

    def _get_cashflow_deltas(self, account_ids: List[int]) -> List[Dict]:
        """Fetch MoneyMovement & BonusPayment transactions as sorted cash flow deltas.

        Returns list of {date: date, amount: float} sorted chronologically.
        Positive amount = deposit (money in), negative = withdrawal (money out).
        """
        raw: List[Dict] = []
        for aid in account_ids:
            cft = self.portfolio_repo.get_account_transactions(
                aid, activity_types=["MoneyMovement", "BonusPayment"]
            )
            for t in cft:
                d = t.get("transaction_date")
                if isinstance(d, str):
                    t["transaction_date"] = date.fromisoformat(d)
                elif isinstance(d, datetime):
                    t["transaction_date"] = d.date()
            raw.extend(cft)
        raw.sort(key=lambda x: x["transaction_date"])

        return [
            {"date": t["transaction_date"], "amount": float(t.get("net_cash_amount") or 0)}
            for t in raw
        ]

    async def get_portfolio_performance(
        self, user_id: int, period: str = "1Y"
    ) -> Dict[str, Any]:
        """
        Calculate portfolio value over time by walking through transactions
        and applying FIFO lot tracking with historical prices.
        """
        # Get all accounts for user (needed first for dynamic ALL start date)
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
        if not account_ids:
            return {
                "success": True,
                "period": period,
                "snapshots": [],
                "total_return": 0,
                "total_return_pct": 0,
            }

        start_date, end_date = self._period_to_date_range(period, account_ids)

        # Get all trade transactions across accounts
        all_txns: List[Dict] = []
        for aid in account_ids:
            txns = self.portfolio_repo.get_account_transactions(aid, activity_types=["Trade"])
            # Normalize string dates to date objects
            for t in txns:
                d = t.get("transaction_date")
                if isinstance(d, str):
                    t["transaction_date"] = date.fromisoformat(d)
                elif isinstance(d, datetime):
                    t["transaction_date"] = d.date()
            all_txns.extend(txns)

        # Sort all transactions ascending, then split into pre-period (for opening lots) and in-period
        all_txns.sort(key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))
        pre_txns = [t for t in all_txns if t["transaction_date"] < start_date]
        in_txns = [t for t in all_txns if start_date <= t["transaction_date"] <= end_date]

        # Get cash flow deltas for cumulative net deposits lookup (ALL TIME)
        cashflow_deltas = self._get_cashflow_deltas(account_ids)
        net_deposits_at_date: Dict[date, float] = {}
        running_nd = 0.0
        for cf in cashflow_deltas:
            running_nd += cf["amount"]
            net_deposits_at_date[cf["date"]] = running_nd

        # Get unique symbols and their company_ids (from ALL transactions for price data)
        symbols_seen: Dict[str, int] = {}
        for t in all_txns:
            sym = t.get("symbol")
            cid = t.get("company_id")
            if sym and cid:
                symbols_seen[sym] = cid

        # Fetch price_history for all symbols in the date range (batched, with slight extension)
        price_map: Dict[str, Dict[str, float]] = {}  # symbol -> {date_str: close_price}
        company_ids = list(set(symbols_seen.values()))
        if company_ids:
            try:
                resp = (
                    supabase.table("price_history")
                    .select("company_id, price_date, close_price")
                    .in_("company_id", company_ids)
                    .gte("price_date", (start_date - timedelta(days=7)).isoformat())
                    .lte("price_date", end_date.isoformat())
                    .order("price_date", desc=False)
                    .execute()
                )
                if resp.data:
                    sym_by_cid = {cid: sym for sym, cid in symbols_seen.items()}
                    for row in resp.data:
                        cid = row["company_id"]
                        sym = sym_by_cid.get(cid)
                        if sym:
                            price_map.setdefault(sym, {})[row["price_date"]] = float(row["close_price"])
            except Exception as e:
                logger.warning(f"Failed to batch fetch price_history: {e}")

        # ── Process pre-period transactions to establish opening FIFO lots ──
        # lots: (account_id, symbol) -> [{quantity, cost_per_share, date}]
        lots: Dict[tuple, list] = defaultdict(list)
        for t in pre_txns:
            sym = t.get("symbol")
            if not sym:
                continue
            key = (t.get("account_id"), sym)
            qty = Decimal(str(t.get("quantity") or 0))
            price = Decimal(str(t.get("unit_price") or 0))
            commission = Decimal(str(t.get("commission") or 0))
            sub = (t.get("activity_sub_type") or "").upper()

            if sub == "BUY" or (sub == "" and qty > 0):
                cost_per_share = price + (commission / qty) if qty else price
                lots[key].append({
                    "quantity": float(qty),
                    "cost_per_share": float(cost_per_share),
                    "date": t["transaction_date"].isoformat(),
                })
            elif sub == "SELL" or (sub == "" and qty < 0):
                sell_qty = abs(float(qty))
                remaining = sell_qty
                while remaining > 0 and lots[key]:
                    lot = lots[key][0]
                    if lot["quantity"] <= remaining:
                        remaining -= lot["quantity"]
                        lots[key].pop(0)
                    else:
                        lot["quantity"] -= remaining
                        remaining = 0

        # Sort in-period transactions by date for sequential processing
        in_txns_sorted = sorted(in_txns, key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))

        # ── Generate snapshot dates at regular intervals ──
        p = period.upper()
        if p == "1D":
            step = timedelta(days=1)
        elif p == "1W":
            step = timedelta(days=1)
        elif p == "1M":
            step = timedelta(days=2)
        elif p == "3M":
            step = timedelta(days=3)
        elif p == "1Y":
            step = timedelta(days=7)
        elif p == "5Y":
            step = timedelta(days=14)
        else:  # ALL
            step = timedelta(days=30)

        sorted_dates: List[str] = []
        current_d = start_date
        while current_d <= end_date:
            sorted_dates.append(current_d.isoformat())
            current_d += step
        end_str = end_date.isoformat()
        if sorted_dates[-1] != end_str:
            sorted_dates.append(end_str)

        # Sort net deposits dates once for efficient lookup
        sorted_nd_dates = sorted(net_deposits_at_date.keys())

        def _cumulative_net_deposits(as_of: date) -> float:
            nd = 0.0
            for nd_date in sorted_nd_dates:
                if nd_date <= as_of:
                    nd = net_deposits_at_date[nd_date]
                else:
                    break
            return nd

        snapshots: List[Dict] = []
        txn_index = 0  # pointer into in_txns_sorted

        for d in sorted_dates:
            current_date = date.fromisoformat(d)

            # Process ALL transactions with date <= current snapshot date
            while txn_index < len(in_txns_sorted) and in_txns_sorted[txn_index]["transaction_date"].isoformat() <= d:
                t = in_txns_sorted[txn_index]
                sym = t.get("symbol")
                if sym:
                    key = (t.get("account_id"), sym)
                    qty = Decimal(str(t.get("quantity") or 0))
                    price = Decimal(str(t.get("unit_price") or 0))
                    commission = Decimal(str(t.get("commission") or 0))
                    sub = (t.get("activity_sub_type") or "").upper()

                    if sub == "BUY" or (sub == "" and qty > 0):
                        cost_per_share = price + (commission / qty) if qty else price
                        lots[key].append({
                            "quantity": float(qty),
                            "cost_per_share": float(cost_per_share),
                            "date": d,
                        })
                    elif sub == "SELL" or (sub == "" and qty < 0):
                        sell_qty = abs(float(qty))
                        remaining = sell_qty
                        while remaining > 0 and lots[key]:
                            lot = lots[key][0]
                            if lot["quantity"] <= remaining:
                                remaining -= lot["quantity"]
                                lots[key].pop(0)
                            else:
                                lot["quantity"] -= remaining
                                remaining = 0
                txn_index += 1

            # Compute snapshot at this date
            total_value = 0.0
            total_cost = 0.0
            for (_, sym), lot_list in lots.items():
                qty_held = sum(l["quantity"] for l in lot_list)
                if qty_held <= 0:
                    continue
                avg_cost = sum(l["quantity"] * l["cost_per_share"] for l in lot_list) / qty_held
                total_cost += qty_held * avg_cost

                # Look up historical price (nearest on or before snapshot date)
                price_map_for_sym = price_map.get(sym, {})
                historical_price = None
                if d in price_map_for_sym:
                    historical_price = price_map_for_sym[d]
                else:
                    nearest = None
                    for pd_str in sorted(price_map_for_sym.keys()):
                        if pd_str <= d:
                            nearest = pd_str
                        else:
                            break
                    if nearest:
                        historical_price = price_map_for_sym[nearest]

                if historical_price is not None:
                    total_value += qty_held * historical_price
                else:
                    total_value += qty_held * avg_cost

            snapshots.append({
                "date": d,
                "value": round(total_value, 2),
                "cost_basis": round(total_cost, 2),
                "net_deposits": round(_cumulative_net_deposits(current_date), 2),
            })

        if not snapshots:
            return {
                "success": True,
                "period": period,
                "snapshots": [],
                "total_return": 0,
                "total_return_pct": 0,
            }

        # Calculate summary stats
        first_value = snapshots[0]["value"]
        last_value = snapshots[-1]["value"]
        total_return = last_value - snapshots[0]["cost_basis"]
        total_return_pct = ((last_value - snapshots[0]["cost_basis"]) / snapshots[0]["cost_basis"] * 100) if snapshots[0]["cost_basis"] > 0 else 0

        # Find best/worst day
        best_day = None
        worst_day = None
        for i in range(1, len(snapshots)):
            prev = snapshots[i - 1]["value"]
            curr = snapshots[i]["value"]
            if prev > 0:
                change_pct = (curr - prev) / prev * 100
                entry = {"date": snapshots[i]["date"], "return_pct": round(change_pct, 2)}
                if best_day is None or change_pct > best_day["return_pct"]:
                    best_day = entry
                if worst_day is None or change_pct < worst_day["return_pct"]:
                    worst_day = entry

        return {
            "success": True,
            "period": period,
            "snapshots": snapshots,
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "best_day": best_day,
            "worst_day": worst_day,
        }

    # ------------------------------------------------------------------
    # Benchmark simulation (same-cash-flows approach)
    # ------------------------------------------------------------------

    def _nearest_price(self, price_map: Dict[str, float], target: str) -> Optional[float]:
        """Find the nearest price on or before target date in price_map.

        If no price exists on or before target, falls forward to the
        earliest available price (handles start dates before first EOM).
        """
        nearest = None
        for d in sorted(price_map):
            if d <= target:
                nearest = d
            else:
                break
        if nearest is None and price_map:
            nearest = sorted(price_map)[0]
        return price_map.get(nearest)

    def _simulate_benchmark_value(
        self,
        benchmark_company_id: int,
        start_date: date,
        end_date: date,
        initial_value: float,
        cashflow_deltas: List[Dict],
        snapshot_dates: List[str],
    ) -> Optional[List[Dict]]:
        """
        Simulate what a benchmark (e.g. SPY) would be worth if the same
        deposits/withdrawals had been invested in it instead of the portfolio.

        Returns list of {date, value} in dollar terms at each snapshot date,
        or None if no price data is available for the benchmark.
        """
        try:
            resp = (
                supabase.table("price_history")
                .select("price_date, close_price")
                .eq("company_id", benchmark_company_id)
                .gte("price_date", (start_date - timedelta(days=7)).isoformat())
                .lte("price_date", end_date.isoformat())
                .order("price_date", desc=False)
                .execute()
            )
        except Exception as e:
            logger.warning("Failed to fetch benchmark price data for company_id=%s: %s", benchmark_company_id, e)
            return None

        if not resp.data:
            logger.info("No price history for benchmark company_id=%s", benchmark_company_id)
            return None

        price_map: Dict[str, float] = {}
        for row in resp.data:
            pd_val = row["price_date"]
            if isinstance(pd_val, str):
                pd_str = pd_val
            elif isinstance(pd_val, date):
                pd_str = pd_val.isoformat()
            else:
                continue
            price_map[pd_str] = float(row["close_price"])

        if not price_map:
            return None

        start_str = start_date.isoformat()
        start_price = self._nearest_price(price_map, start_str)
        if not start_price or start_price <= 0:
            logger.info("No valid start price for benchmark company_id=%s", benchmark_company_id)
            return None

        # If portfolio had no value at start, benchmark is always zero
        if initial_value <= 0:
            return [{"date": d, "value": 0.0} for d in snapshot_dates]

        shares = initial_value / start_price

        # Filter cash flows to the period and normalize dates to ISO strings
        period_cashflows = [
            {
                "date": cf["date"].isoformat() if isinstance(cf["date"], date) else str(cf["date"]),
                "amount": cf["amount"],
            }
            for cf in cashflow_deltas
            if start_date <= cf["date"] <= end_date
        ]

        series: List[Dict] = []
        cf_index = 0

        for sd in snapshot_dates:
            # Process any cash flows on or before this snapshot date
            while cf_index < len(period_cashflows):
                cf = period_cashflows[cf_index]
                if cf["date"] <= sd:
                    cf_price = self._nearest_price(price_map, cf["date"])
                    if cf_price and cf_price > 0:
                        if cf["amount"] > 0:
                            shares += cf["amount"] / cf_price
                        elif cf["amount"] < 0:
                            sell_qty = min(abs(cf["amount"]) / cf_price, shares)
                            shares -= sell_qty
                    cf_index += 1
                else:
                    break

            snap_price = self._nearest_price(price_map, sd)
            if snap_price:
                series.append({
                    "date": sd,
                    "value": round(shares * snap_price, 2),
                })
            else:
                series.append({"date": sd, "value": 0.0})

        return series

    # ------------------------------------------------------------------
    # Benchmark list & comparison
    # ------------------------------------------------------------------

    async def get_benchmarks(self) -> List[Dict[str, Any]]:
        """List all active benchmarks from benchmark_config."""
        try:
            resp = (
                supabase.table("benchmark_config")
                .select("*")
                .eq("is_active", True)
                .execute()
            )
            return [
                {
                    "role": r.get("role"),
                    "symbol": r.get("symbol"),
                    "name": r.get("name", r.get("symbol")),
                    "market": r.get("market", "US"),
                    "description": r.get("description"),
                }
                for r in (resp.data or [])
            ]
        except Exception as e:
            logger.error(f"Failed to list benchmarks: {e}")
            return []

    async def get_performance_compare(
        self, user_id: int, period: str, benchmark_symbols: List[str]
    ) -> Dict[str, Any]:
        """
        Compare portfolio performance against benchmark indices.

        Uses the "same cash flows" approach: simulates what each benchmark
        would be worth if the same deposits/withdrawals were invested in it
        instead of the portfolio. Both portfolio and benchmark series are
        in dollar terms, allowing a direct side-by-side comparison.
        """
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]
        start_date, end_date = self._period_to_date_range(period, account_ids)

        perf = await self.get_portfolio_performance(user_id, period)
        if not perf.get("success") or not perf.get("snapshots"):
            return {
                "success": True,
                "period": period,
                "portfolio": [],
                "benchmarks": [],
            }

        snapshots = perf["snapshots"]

        # Find first snapshot with non-zero value as the benchmark starting point
        first_nonzero = 0
        for i, s in enumerate(snapshots):
            if s["value"] > 0:
                first_nonzero = i
                break

        snapshots_subset = snapshots[first_nonzero:]
        if not snapshots_subset:
            return {
                "success": True,
                "period": period,
                "portfolio": snapshots,
                "benchmarks": [],
            }

        initial_value = snapshots_subset[0]["value"]
        snapshot_dates = [s["date"] for s in snapshots_subset]
        cashflow_deltas = self._get_cashflow_deltas(account_ids)

        benchmark_series_list = []
        if benchmark_symbols:
            for sym in benchmark_symbols:
                company = await self.financial_repo.get_company_by_symbol(sym)
                if not company:
                    logger.info("Benchmark symbol %s not found in companies table — skipping", sym)
                    continue

                series = self._simulate_benchmark_value(
                    benchmark_company_id=company["company_id"],
                    start_date=start_date,
                    end_date=end_date,
                    initial_value=initial_value,
                    cashflow_deltas=cashflow_deltas,
                    snapshot_dates=snapshot_dates,
                )
                if series:
                    benchmark_series_list.append({
                        "symbol": sym,
                        "name": sym,
                        "data": series,
                    })

        return {
            "success": True,
            "period": period,
            "portfolio": snapshots,
            "benchmarks": benchmark_series_list,
        }
