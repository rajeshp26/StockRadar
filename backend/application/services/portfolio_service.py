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
import re

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

            # --- Company lookup (with exchange override for CDR symbols) ---
            symbols_meta: Dict[str, Optional[str]] = {}
            for tx in parse_result.transactions:
                if tx.symbol:
                    override = getattr(tx, "exchange_override", None)
                    if tx.symbol not in symbols_meta:
                        symbols_meta[tx.symbol] = override
                    elif override:
                        symbols_meta[tx.symbol] = "TOR"  # prefer TOR if any transaction is CDR
            companies_map, symbols_created = await self._ensure_companies_exist_with_tracking(
                symbols_meta
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

            # --- On-demand price fetch for new symbols (background) ---
            account_ids_list = list(accounts_map.values())
            asyncio.create_task(self._fetch_prices_on_import(account_ids_list))

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
        self, symbols: Dict[str, Optional[str]]
    ) -> Tuple[Dict[str, int], List[str]]:
        """
        Ensure companies exist and track which were created.
        
        Args:
            symbols: Dict mapping ticker_symbol → optional exchange_override
                     (e.g., {"TSLA": "TOR", "AAPL": None})
        
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
                .in_("ticker_symbol", list(symbols.keys()))
                .execute()
            )
            for row in res.data or []:
                companies_map[row["ticker_symbol"]] = row["company_id"]
        except Exception as e:
            logger.error(f"Failed to check existing companies: {e}")
        
        # Create missing
        missing = set(symbols.keys()) - companies_map.keys()
        if missing:
            logger.info(f"Creating {len(missing)} missing companies")
            for idx, symbol in enumerate(sorted(missing)):
                try:
                    # Rate-limit: insert a small delay between provider calls to
                    # avoid triggering Yahoo Finance rate limiting (especially
                    # during CSV imports with many unique tickers).
                    if idx > 0:
                        await asyncio.sleep(0.5)
                    company_id = await self._create_company_from_symbol(symbol, exchange_override=symbols.get(symbol))
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
                # Detect CDR from transaction raw_data (symbol or name field) for exchange override
                exchange_override = None
                for tx in tx_list:
                    raw = tx.get("raw_data")
                    if isinstance(raw, dict):
                        raw_symbol = raw.get("symbol", "") or ""
                        raw_name = raw.get("name", "") or ""
                        if re.search(r"\bCDR\b", raw_symbol + " " + raw_name, re.IGNORECASE):
                            exchange_override = "TOR"
                            break
                if exchange_override:
                    holding["exchange_override"] = exchange_override
                holdings_by_symbol[symbol] = holding
        
        # Delete old holdings for this account
        self.portfolio_repo.delete_account_holdings(account_id)
        
        # Insert new holdings (price-independent cost-basis fields only)
        for holding in holdings_by_symbol.values():
            holding["account_id"] = account_id
            holding["computed_at"] = datetime.now().isoformat()
            self.portfolio_repo.upsert_holding(holding)
        
        logger.info(f"Holdings recalculated for account {account_id}: {len(holdings_by_symbol)} positions")
    
    async def enrich_holdings_with_prices(
        self, holdings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Compute current_value, current_price, unrealized_gain_loss at query time.

        Batches price lookups across all holdings (2 queries total, not N+1).
        3-tier fallback: current_market_data → price_history latest close → cost basis.

        Holdings with exchange_override (e.g., "TOR" for CDRs) get live YFinance
        prices using the override exchange, bypassing the cached tables.
        """
        if not holdings:
            return holdings

        company_ids = list({h["company_id"] for h in holdings if h.get("company_id")})
        if not company_ids:
            return holdings

        # Separate holdings with exchange_override (need live lookup)
        override_holdings = [h for h in holdings if h.get("exchange_override")]
        standard_holdings = [h for h in holdings if not h.get("exchange_override")]

        # Price map: company_id → price (for standard holdings)
        price_map: Dict[int, float] = {}

        if standard_holdings:
            std_ids = list({h["company_id"] for h in standard_holdings if h.get("company_id")})

            # Tier 1: current_market_data (single batch)
            cm_res = (
                supabase.table("current_market_data")
                .select("company_id, current_price")
                .in_("company_id", std_ids)
                .execute()
            )
            for row in (cm_res.data or []):
                if row.get("current_price") is not None:
                    price_map[row["company_id"]] = float(row["current_price"])

            # Tier 2: price_history latest close for missing companies
            missing_ids = [cid for cid in std_ids if cid not in price_map]
            if missing_ids:
                ph_res = (
                    supabase.table("price_history")
                    .select("company_id, close_price, price_date")
                    .in_("company_id", missing_ids)
                    .order("price_date", desc=True)
                    .execute()
                )
                seen_company: set = set()
                for row in (ph_res.data or []):
                    cid = row["company_id"]
                    if cid not in seen_company and row.get("close_price") is not None:
                        seen_company.add(cid)
                        price_map.setdefault(cid, float(row["close_price"]))

        # Live lookup cache for exchange-override holdings
        override_cache: Dict[str, Optional[float]] = {}

        # Apply prices to each holding
        for h in holdings:
            cid = h.get("company_id")
            total_cost = h.get("total_cost", 0) or 0
            quantity = h.get("quantity", 0) or 0
            avg_cost = h.get("average_cost", 0) or 0
            exchange_override = h.get("exchange_override")

            price = None
            if exchange_override:
                # Live lookup with override exchange (bypass cached tables)
                cache_key = f"{h.get('symbol')}:{exchange_override}"
                if cache_key not in override_cache:
                    try:
                        sd = self.stock_provider.get_stock_details(h["symbol"], exchange=exchange_override)
                        override_cache[cache_key] = sd.price if sd else None
                    except Exception:
                        override_cache[cache_key] = None
                price = override_cache[cache_key]
            else:
                price = price_map.get(cid)

            if price is not None and quantity > 0:
                h["current_price"] = price
                h["current_value"] = price * quantity
            else:
                # Tier 3: cost-basis fallback
                h["current_price"] = float(avg_cost) if avg_cost else 0.0
                h["current_value"] = float(total_cost) if total_cost else 0.0

            h["unrealized_gain_loss"] = h["current_value"] - float(total_cost)
            h["unrealized_gain_loss_pct"] = (
                (h["unrealized_gain_loss"] / float(total_cost) * 100)
                if float(total_cost) > 0 else 0.0
            )

        return holdings

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

    def aggregate_holdings(
        self, holdings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Group holdings by company_id, aggregating quantities and costs.

        Returns one record per symbol with combined quantities, weighted
        average cost, and a per-account breakdown.
        """
        groups: Dict[int, Dict[str, Any]] = {}

        for h in holdings:
            cid = h.get("company_id")
            if cid is None:
                continue

            if cid not in groups:
                groups[cid] = {
                    "company_id": cid,
                    "symbol": h.get("symbol"),
                    "company_name": h.get("company_name") or h.get("symbol", "Unknown"),
                    "sector": h.get("sector"),
                    "industry": h.get("industry"),
                    "exchange": h.get("exchange"),
                    "market_group": h.get("market_group"),
                    "security_type": h.get("security_type", "stock"),
                    "currency": h.get("currency"),
                    "total_quantity": 0.0,
                    "total_cost": 0.0,
                    "current_price": h.get("current_price"),
                    "account_breakdown": [],
                }

            g = groups[cid]
            qty = float(h.get("quantity") or 0)
            cost = float(h.get("total_cost") or 0)
            g["total_quantity"] += qty
            g["total_cost"] += cost

            # Keep the most recent non-null price
            price = h.get("current_price")
            if price is not None:
                g["current_price"] = price

            g["account_breakdown"].append({
                "account_id": h.get("account_id"),
                "account_name": h.get("account_name"),
                "account_type": h.get("account_type"),
                "quantity": qty,
                "total_cost": cost,
                "current_value": float(h.get("current_value") or 0),
            })

        result = []
        for g in groups.values():
            g["average_cost"] = round(
                g["total_cost"] / g["total_quantity"], 4
            ) if g["total_quantity"] > 0 else 0.0

            price = g.get("current_price")
            if price is not None:
                g["current_value"] = round(price * g["total_quantity"], 2)
            else:
                g["current_value"] = round(
                    sum(b["current_value"] for b in g["account_breakdown"]), 2
                )

            g["unrealized_gain_loss"] = round(
                g["current_value"] - g["total_cost"], 2
            )
            g["unrealized_gain_loss_pct"] = round(
                (g["unrealized_gain_loss"] / g["total_cost"] * 100), 2
            ) if g["total_cost"] > 0 else 0.0

            g["accounts_count"] = len(g["account_breakdown"])
            result.append(g)

        # Sort by current_value descending
        result.sort(key=lambda x: x["current_value"], reverse=True)
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
        """
        Get current price for a symbol with three-tier fallback:
        1. current_market_data (live market price)
        2. price_history (latest close price)
        Returns None only if both tables are empty.
        """
        try:
            company = await self.financial_repo.get_company_by_symbol(symbol)
            if not company:
                return None
            cid = company["company_id"]

            # Tier 1: current_market_data (live)
            res = (
                supabase.table("current_market_data")
                .select("current_price")
                .eq("company_id", cid)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("current_price"):
                return {"price": float(res.data[0]["current_price"]), "source": "current_market_data"}

            # Tier 2: price_history (latest close)
            res = (
                supabase.table("price_history")
                .select("close_price")
                .eq("company_id", cid)
                .order("price_date", desc=True)
                .limit(1)
                .execute()
            )
            if res.data and res.data[0].get("close_price"):
                return {"price": float(res.data[0]["close_price"]), "source": "price_history"}

        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")

        return None

    # ========================================================================
    # ON-DEMAND PRICE FETCH (Phase 2)
    # ========================================================================

    async def _fetch_prices_on_import(self, account_ids: List[int]) -> None:
        """
        On-demand price fetch for symbols without current_market_data
        discovered during portfolio import. Runs as a background task.

        For each symbol in the imported accounts:
        1. Checks if current_market_data already exists → skip
        2. Fetches current price from YFinance → upserts current_market_data
        3. Fetches full price history → compresses to monthly EOM → upserts price_history
        """
        try:
            # Gather all unique symbols from holdings
            symbols: set = set()
            for aid in account_ids:
                holdings = self.portfolio_repo.get_account_holdings(aid)
                symbols.update(h["symbol"] for h in holdings if h.get("symbol"))

            if not symbols:
                return

            logger.info("On-demand price fetch for %d symbols: %s", len(symbols), sorted(symbols))
            fetched = 0
            for symbol in sorted(symbols):
                try:
                    await self._fetch_and_store_prices(symbol)
                    fetched += 1
                except Exception as e:
                    logger.warning("Price fetch failed for %s: %s", symbol, e)
                    continue
            logger.info("On-demand price fetch complete: %d/%d symbols", fetched, len(symbols))

        except Exception as e:
            logger.error("On-demand price fetch failed: %s", e)

    async def _fetch_and_store_prices(self, symbol: str) -> None:
        """
        Fetch current price and price_history for a symbol.
        Skips current_market_data if entry already exists.
        Skips price_history if already populated.
        """
        company = await self.financial_repo.get_company_by_symbol(symbol)
        if not company:
            logger.debug("No company record for %s — skipping price fetch", symbol)
            return
        cid = company["company_id"]

        # Check if current_market_data already exists
        existing = (
            supabase.table("current_market_data")
            .select("company_id")
            .eq("company_id", cid)
            .limit(1)
            .execute()
        )
        needs_current = not existing.data

        # Check if price_history already exists
        needs_history = not await self._has_price_history(cid)

        if not needs_current and not needs_history:
            logger.debug("Prices already exist for %s — skipping", symbol)
            return

        # Fetch from YFinance provider
        exchange = company.get("exchange")
        try:
            sd = self.stock_provider.get_stock_details(symbol, exchange=exchange)

            # Upsert current_market_data
            if sd and sd.price is not None:
                market_data = {
                    "company_id": cid,
                    "current_price": sd.price,
                    "open_price": getattr(sd, "open_price", None),
                    "high_price": getattr(sd, "high_price", None),
                    "low_price": getattr(sd, "low_price", None),
                    "close_price": getattr(sd, "close_price", None),
                    "volume": getattr(sd, "volume", None),
                    "market_state": getattr(sd, "market_state", None),
                }
                supabase.table("current_market_data").upsert(
                    market_data, on_conflict="company_id"
                ).execute()
                logger.debug("Upserted current_market_data for %s: $%.2f", symbol, sd.price)
            else:
                logger.debug("No current price from YFinance for %s", symbol)

            # Fetch and store price_history if needed
            if needs_history:
                daily_rows = await self._get_daily_price_history(symbol, cid, exchange=exchange)
                if daily_rows:
                    monthly_rows = self._compress_daily_to_monthly_eom(daily_rows)
                    if monthly_rows:
                        await self.financial_repo.upsert_price_history(monthly_rows)
                        await self.financial_repo.update_price_refresh_marker(cid)
                        logger.info("Price history loaded for %s: %d monthly rows", symbol, len(monthly_rows))

        except Exception as e:
            logger.warning("Price provider error for %s: %s", symbol, e)

    async def _has_price_history(self, company_id: int) -> bool:
        """Check if any price_history exists for a company."""
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
            logger.debug("_has_price_history failed for company_id=%s: %s", company_id, e)
            return False

    async def _get_daily_price_history(
        self, symbol: str, company_id: int, exchange: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch daily OHLCV price history from YFinance provider."""
        try:
            # YFinanceProvider has get_price_history_df returning a DataFrame
            if hasattr(self.stock_provider, "get_price_history_df"):
                df = self.stock_provider.get_price_history_df(symbol, exchange=exchange)
                if df is not None and not df.empty:
                    rows = []
                    for _, r in df.iterrows():
                        rows.append({
                            "company_id": company_id,
                            "price_date": r["price_date"].date() if hasattr(r["price_date"], "date") else r["price_date"],
                            "open_price": float(r.get("open_price", 0)),
                            "close_price": float(r.get("close_price", 0)),
                            "high_price": float(r.get("high_price", 0)),
                            "low_price": float(r.get("low_price", 0)),
                            "volume": int(r.get("volume", 0)) if r.get("volume") else None,
                            "data_source": "yfinance",
                        })
                    return rows
            return []
        except Exception as e:
            logger.debug("Failed to fetch daily price history for %s: %s", symbol, e)
            return []

    @staticmethod
    def _compress_daily_to_monthly_eom(
        daily_rows: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Convert daily OHLCV rows to monthly EOM rows:
          - Group by (year, month)
          - Pick the row with the latest price_date (last trading day of the month)
          - Preserve all OHLCV fields
        """
        if not daily_rows:
            return []
        try:
            import pandas as pd
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
                out.append({
                    "company_id": int(r.get("company_id")),
                    "price_date": r["price_date"].date(),
                    "open_price": float(r["open_price"]) if pd.notna(r.get("open_price")) else None,
                    "close_price": float(r["close_price"]) if pd.notna(r.get("close_price")) else None,
                    "high_price": float(r["high_price"]) if pd.notna(r.get("high_price")) else None,
                    "low_price": float(r["low_price"]) if pd.notna(r.get("low_price")) else None,
                    "volume": int(r["volume"]) if pd.notna(r.get("volume")) else None,
                    "data_source": str(r.get("data_source") or "yfinance"),
                })
            out.sort(key=lambda x: x["price_date"])
            return out
        except ImportError:
            logger.error("pandas required for _compress_daily_to_monthly_eom")
            return []
        except Exception as e:
            logger.error("Failed to compress daily to monthly EOM: %s", e)
            return []

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
    
    async def get_user_portfolio_overview(
        self, user_id: int,
        account_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive portfolio overview for user.

        When account_ids is provided, scope to those accounts only.
        None or empty list = all user accounts.

        Returns:
            - Total net worth
            - YTD performance
            - Total gain/loss
            - Dividends (yearly)
            - Top holdings
            - Account breakdown
        """
        # Get all accounts (for ownership verification)
        all_accounts = self.portfolio_repo.get_user_accounts(user_id)

        if account_ids:
            valid_ids = {a["account_id"] for a in all_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]
            accounts = [a for a in all_accounts if a["account_id"] in account_ids]
        else:
            accounts = all_accounts

        if not accounts:
            return {
                "success": False,
                "error": "No portfolio accounts found",
            }

        # Get all holdings
        holdings = await self.enrich_holdings_with_prices(
            self.portfolio_repo.get_user_all_holdings(user_id)
        )
        # Filter by account_ids if specified
        if account_ids:
            holdings = [h for h in holdings if h.get("account_id") in account_ids]
        
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
    # ALL-ACCOUNTS DIVIDENDS
    # ========================================================================

    async def get_user_all_dividends(
        self, user_id: int,
        account_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Aggregate dividends across all (or specified) user accounts.

        When account_ids is provided, scope to those accounts only.
        None or empty list = all user accounts.
        """
        if account_ids is None:
            accounts = self.portfolio_repo.get_user_accounts(user_id, active_only=True)
            account_ids = [a["account_id"] for a in accounts]
        else:
            user_accounts = self.portfolio_repo.get_user_accounts(user_id, active_only=True)
            valid_ids = {a["account_id"] for a in user_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]

        if not account_ids:
            return {
                "success": True,
                "current_year_total": 0,
                "monthly_summaries": [],
            }

        current_year = datetime.now().year
        current_year_total = Decimal("0")
        all_monthly_summaries = []

        for aid in account_ids:
            yearly_divs = self.portfolio_repo.get_account_dividends_by_year(aid, current_year)
            current_year_total += sum(Decimal(str(d.get("amount", 0))) for d in yearly_divs)
            monthly = self.portfolio_repo.get_monthly_dividends(aid, months=12)
            all_monthly_summaries.extend(monthly)

        aggregated = {}
        for m in all_monthly_summaries:
            key = (m["fiscal_year"], m["fiscal_month"])
            if key not in aggregated:
                aggregated[key] = {
                    "fiscal_year": m["fiscal_year"],
                    "fiscal_month": m["fiscal_month"],
                    "total_amount": 0,
                    "payment_count": 0,
                    "paying_companies": 0,
                }
            aggregated[key]["total_amount"] += m.get("total_amount", 0)
            aggregated[key]["payment_count"] += m.get("payment_count", 0)
            aggregated[key]["paying_companies"] += m.get("paying_companies", 0)

        monthly_summaries = sorted(
            aggregated.values(),
            key=lambda x: (x["fiscal_year"], x["fiscal_month"]),
            reverse=True,
        )

        return {
            "success": True,
            "current_year_total": float(current_year_total),
            "monthly_summaries": monthly_summaries,
        }

    # ========================================================================
    # ALL-ACCOUNTS TRANSACTIONS
    # ========================================================================

    async def get_user_all_transactions(
        self, user_id: int,
        account_ids: Optional[List[int]] = None,
        limit: int = 100,
        activity_type: Optional[str] = None,
        search: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get transactions across all (or specified) user accounts.

        Supports the same filters as the per-account endpoint.
        When account_ids is None/empty, returns transactions for all accounts.
        """
        if account_ids is None:
            accounts = self.portfolio_repo.get_user_accounts(user_id, active_only=True)
            account_ids = [a["account_id"] for a in accounts]
        else:
            user_accounts = self.portfolio_repo.get_user_accounts(user_id, active_only=True)
            valid_ids = {a["account_id"] for a in user_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]

        if not account_ids:
            return {
                "transactions": [],
                "total_count": 0,
            }

        activity_types = [activity_type] if activity_type else None

        all_transactions = []
        for aid in account_ids:
            txs = self.portfolio_repo.get_account_transactions(
                aid, limit=limit, activity_types=activity_types,
            )
            all_transactions.extend(txs)

        if search:
            search_lower = search.lower()
            all_transactions = [
                t for t in all_transactions
                if search_lower in (t.get("symbol") or "").lower()
                or search_lower in (t.get("security_name") or "").lower()
            ]
        if from_date:
            fd = date.fromisoformat(from_date) if isinstance(from_date, str) else from_date
            all_transactions = [
                t for t in all_transactions
                if date.fromisoformat(t["transaction_date"]) >= fd
            ]
        if to_date:
            td = date.fromisoformat(to_date) if isinstance(to_date, str) else to_date
            all_transactions = [
                t for t in all_transactions
                if date.fromisoformat(t["transaction_date"]) <= td
            ]

        all_transactions.sort(key=lambda x: x.get("transaction_date", ""), reverse=True)
        all_transactions = all_transactions[:limit]

        return {
            "transactions": all_transactions,
            "total_count": len(all_transactions),
        }

    # ========================================================================
    # DIVIDEND HISTORY (extended detail)
    # ========================================================================

    async def get_dividend_history_detail(
        self, user_id: int, account_id: int,
    ) -> Dict[str, Any]:
        """Get detailed dividend history for an account with company names."""
        repo = self.portfolio_repo
        account = repo.get_account_by_id(account_id)
        if not account:
            return {"success": False, "error": "Account not found"}
        if account["user_id"] != user_id:
            return {"success": False, "error": "Access denied"}

        dividends = repo.get_account_dividends_by_year(account_id, None)
        dividends.sort(key=lambda d: d.get("payment_date", ""), reverse=True)

        current_year = datetime.now().year
        current_year_total = sum(
            float(d.get("amount", 0)) for d in dividends
            if d.get("fiscal_year") == current_year
        )

        company_ids = list({d.get("company_id") for d in dividends if d.get("company_id")})
        company_names: Dict[int, str] = {}
        if company_ids:
            try:
                res = (
                    supabase.table("companies")
                    .select("company_id, company_name")
                    .in_("company_id", company_ids)
                    .execute()
                )
                for c in res.data or []:
                    company_names[c["company_id"]] = c["company_name"]
            except Exception as e:
                logger.error(f"Failed to fetch company names for dividends: {e}")

        details = []
        for d in dividends:
            details.append({
                "dividend_id": d["dividend_id"],
                "symbol": d.get("symbol", ""),
                "company_name": company_names.get(d.get("company_id")),
                "payment_date": d["payment_date"],
                "amount": float(d.get("amount", 0)),
                "shares_held": d.get("shares_held"),
                "amount_per_share": d.get("amount_per_share"),
                "account_name": account.get("account_name"),
                "account_type": account.get("account_type"),
            })

        return {
            "success": True,
            "dividends": details,
            "total_count": len(details),
            "current_year_total": current_year_total,
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

    async def _create_company_from_symbol(self, symbol: str, exchange_override: Optional[str] = None) -> Optional[int]:
        """
        Fetch company details from YFinance and create database record.
        
        Resilience features:
        1. Accept exchange_override (e.g., "TOR") to skip US primary-listing resolution
           and query the Canadian-listed version directly via .TO / .V suffix
        2. Retry with .TO / .V suffix for Canadian-listed symbols when initial lookup fails
        3. Create a minimal company record when all provider lookups fail (so holdings
           calculations can proceed with a valid company_id)
        4. No crash on optional StockDetails fields (market_cap and full_time_employees
           are not part of the StockDetails model)
        
        Returns:
            company_id if successful, None if failed
        """
        try:
            # 1. Determine lookup symbol based on exchange override
            lookup_symbol = symbol
            if exchange_override == "TOR":
                lookup_symbol = symbol + ".TO"
            elif exchange_override == "VAN":
                lookup_symbol = symbol + ".V"

            # Attempt lookup
            sd = self.stock_provider.get_stock_details(lookup_symbol)

            # 2. If override failed (e.g., CDR no longer trades on TSX),
            #    fall back to unsuffixed lookup
            if not sd and exchange_override:
                logger.warning(f"Exchange override {exchange_override} failed for {symbol}, falling back to normal lookup")
                sd = self.stock_provider.get_stock_details(symbol)

            # 3. Retry with Canadian exchange suffixes if still no data
            if not sd:
                for suffix in [".TO", ".V"]:
                    sd = self.stock_provider.get_stock_details(symbol + suffix)
                    if sd:
                        logger.info(f"Resolved {symbol} → {symbol + suffix}")
                        break

            if not sd:
                # 4. Minimal record — no provider data available, but we still
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
                    "security_type": "stock",
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
                    "security_type": _map_quote_type(sd.quote_type),
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

    def _step_for_period(self, period: str) -> timedelta:
        """Return the snapshot interval for a given period string."""
        p = period.upper()
        if p == "1D":
            return timedelta(days=1)
        elif p == "1W":
            return timedelta(days=1)
        elif p == "1M":
            return timedelta(days=2)
        elif p == "3M":
            return timedelta(days=3)
        elif p == "1Y":
            return timedelta(days=7)
        elif p == "5Y":
            return timedelta(days=14)
        else:
            return timedelta(days=30)

    def _generate_snapshot_dates(
        self, period: str, start_date: date, end_date: date
    ) -> List[str]:
        """Generate snapshot date strings at intervals appropriate for the period."""
        step = self._step_for_period(period)
        dates: List[str] = []
        current_d = start_date
        while current_d <= end_date:
            dates.append(current_d.isoformat())
            current_d += step
        end_str = end_date.isoformat()
        if dates[-1] != end_str:
            dates.append(end_str)
        return dates

    def _compute_fifo_snapshots(
        self,
        lots: Dict[tuple, list],
        in_txns_sorted: List[Dict],
        sorted_dates: List[str],
        price_map: Dict[str, Dict[str, float]],
        cumulative_invested_map: Optional[Dict[date, float]] = None,
    ) -> List[Dict]:
        """Core FIFO snapshot engine — used by both portfolio and single-stock.

        Args:
            lots: Opening FIFO lots per (account_id, symbol) key.
            in_txns_sorted: In-period transactions sorted by date.
            sorted_dates: Snapshot date strings in ascending order.
            price_map: symbol -> {date_str: close_price}.
            cumulative_invested_map: Optional date->cumulative_invested lookup.

        Returns list of {date, value, cost_basis, net_deposits} dicts.
        """
        snapshots: List[Dict] = []
        txn_index = 0

        for d in sorted_dates:
            current_date = date.fromisoformat(d)

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

            total_value = 0.0
            total_cost = 0.0
            total_shares = 0
            for (_, sym), lot_list in lots.items():
                qty_held = sum(l["quantity"] for l in lot_list)
                if qty_held <= 0:
                    continue
                avg_cost = sum(l["quantity"] * l["cost_per_share"] for l in lot_list) / qty_held
                total_cost += qty_held * avg_cost
                total_shares += qty_held

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

            cumulative_invested = 0.0
            if cumulative_invested_map:
                for ci_date in sorted(cumulative_invested_map.keys()):
                    if ci_date <= current_date:
                        cumulative_invested = cumulative_invested_map[ci_date]
                    else:
                        break

            snapshots.append({
                "date": d,
                "value": round(total_value, 2),
                "cost_basis": round(total_cost, 2),
                "net_deposits": round(cumulative_invested, 2),
                "shares_held": total_shares,
            })

        return snapshots

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
        self, user_id: int, period: str = "1Y",
        account_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Calculate portfolio value over time by walking through transactions
        and applying FIFO lot tracking with historical prices.

        When account_ids is provided, only transactions from those accounts
        are included. None or empty list = all user accounts.
        """
        if account_ids is None:
            accounts = self.portfolio_repo.get_user_accounts(user_id)
            account_ids = [a["account_id"] for a in accounts]
        else:
            # Security: intersect with user's actual accounts
            user_accounts = self.portfolio_repo.get_user_accounts(user_id)
            valid_ids = {a["account_id"] for a in user_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]

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

        # Fetch price_history for all symbols in the date range (paginated due to Supabase 1000-row limit)
        price_map: Dict[str, Dict[str, float]] = {}  # symbol -> {date_str: close_price}
        company_ids = list(set(symbols_seen.values()))
        if company_ids:
            try:
                sym_by_cid = {cid: sym for sym, cid in symbols_seen.items()}
                offset = 0
                batch_size = 1000
                while True:
                    batch = (
                        supabase.table("price_history")
                        .select("company_id, price_date, close_price")
                        .in_("company_id", company_ids)
                        .gte("price_date", (start_date - timedelta(days=7)).isoformat())
                        .lte("price_date", end_date.isoformat())
                        .order("price_date", desc=False)
                        .range(offset, offset + batch_size - 1)
                        .execute()
                    )
                    if not batch.data:
                        break
                    for row in batch.data:
                        cid = row["company_id"]
                        sym = sym_by_cid.get(cid)
                        if sym:
                            price_map.setdefault(sym, {})[row["price_date"]] = float(row["close_price"])
                    offset += batch_size
                    if len(batch.data) < batch_size:
                        break
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

        sorted_dates = self._generate_snapshot_dates(period, start_date, end_date)

        snapshots = self._compute_fifo_snapshots(
            lots=lots,
            in_txns_sorted=in_txns_sorted,
            sorted_dates=sorted_dates,
            price_map=price_map,
            cumulative_invested_map=net_deposits_at_date,
        )

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
        total_return = last_value - first_value
        total_return_pct = ((last_value - first_value) / first_value * 100) if first_value > 0 else 0

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

    # ========================================================================
    # SINGLE-HOLDING PERFORMANCE
    # ========================================================================

    def check_holding_exists(self, user_id: int, symbol: str) -> bool:
        """Check if user holds a position in the given symbol."""
        holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        return any(h.get("symbol", "").upper() == symbol.upper() for h in holdings)

    async def get_holding_performance(
        self, user_id: int, symbol: str, period: str = "1Y",
    ) -> Dict[str, Any]:
        """
        Compute time-series performance for a single stock in user's portfolio.

        Reuses the shared FIFO snapshot engine from _compute_fifo_snapshots()
        but filtered to a single symbol across all user accounts.
        """
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]

        if not account_ids:
            return {
                "success": True, "symbol": symbol.upper(), "period": period,
                "snapshots": [], "total_return": 0, "total_return_pct": 0,
                "total_dividends": 0, "total_dividends_pct": 0,
            }

        txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
        if not txns:
            return {
                "success": True, "symbol": symbol.upper(), "period": period,
                "snapshots": [], "total_return": 0, "total_return_pct": 0,
                "total_dividends": 0, "total_dividends_pct": 0,
            }

        # Normalize transaction dates first
        for t in txns:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            elif isinstance(d, datetime):
                t["transaction_date"] = d.date()

        # P-02: Compute start date from the symbol's own transactions
        symbol_first = min(t["transaction_date"] for t in txns)
        period_start, end_date = self._period_to_date_range(period, account_ids)
        start_date = max(period_start, symbol_first)

        txns.sort(key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))
        pre_txns = [t for t in txns if t["transaction_date"] < start_date]
        in_txns = [t for t in txns if start_date <= t["transaction_date"] <= end_date]

        price_map: Dict[str, Dict[str, float]] = {}
        try:
            sym_up = symbol.upper()
            resp = (
                supabase.table("price_history")
                .select("company_id, price_date, close_price")
                .eq("company_id", txns[0].get("company_id")) if txns else None
            )
            if resp:
                rows = (
                    supabase.table("price_history")
                    .select("price_date, close_price")
                    .gte("price_date", (start_date - timedelta(days=7)).isoformat())
                    .lte("price_date", end_date.isoformat())
                    .order("price_date", desc=False)
                    .execute()
                )
                if rows.data:
                    for row in rows.data:
                        price_map.setdefault(sym_up, {})[row["price_date"]] = float(row["close_price"])
        except Exception as e:
            logger.warning(f"Failed to fetch price_history for {symbol}: {e}")

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

        in_txns_sorted = sorted(in_txns, key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))

        sorted_dates = self._generate_snapshot_dates(period, start_date, end_date)

        # Build cumulative_invested map: total $ put in (buys - sells) to date
        cumulative_invested_map: Dict[date, float] = {}
        running_ci = Decimal("0")
        for t in txns:
            d = t["transaction_date"]
            qty = Decimal(str(t.get("quantity") or 0))
            price = Decimal(str(t.get("unit_price") or 0))
            commission = Decimal(str(t.get("commission") or 0))
            sub = (t.get("activity_sub_type") or "").upper()
            if sub == "BUY" or (sub == "" and qty > 0):
                running_ci += qty * price + commission
            elif sub == "SELL" or (sub == "" and qty < 0):
                running_ci -= abs(qty) * price - commission
            cumulative_invested_map[d] = float(running_ci)

        base_snapshots = self._compute_fifo_snapshots(
            lots=lots,
            in_txns_sorted=in_txns_sorted,
            sorted_dates=sorted_dates,
            price_map=price_map,
            cumulative_invested_map=cumulative_invested_map,
        )

        # Compute dividends
        total_dividends = 0.0
        try:
            divs = self.portfolio_repo.get_dividends_for_symbol(user_id, symbol)
            for d in divs:
                amt = float(d.get("amount") or 0)
                pd = d.get("payment_date")
                if isinstance(pd, str):
                    pd = date.fromisoformat(pd)
                elif isinstance(pd, datetime):
                    pd = pd.date()
                if start_date <= pd <= end_date:
                    total_dividends += amt
        except Exception as e:
            logger.warning(f"Failed to fetch dividends for {symbol}: {e}")

        snapshots = []
        for s in base_snapshots:
            shares_held = s.get("shares_held", 0)
            avg_cost_per_share = round(s["cost_basis"] / shares_held, 2) if shares_held > 0 else 0
            snapshots.append({
                "date": s["date"],
                "position_value": s["value"],
                "cost_basis": s["cost_basis"],
                "cumulative_invested": s["net_deposits"],
                "shares_held": shares_held,
                "avg_cost_per_share": avg_cost_per_share,
            })

        if not snapshots:
            return {
                "success": True, "symbol": symbol.upper(), "period": period,
                "snapshots": [], "total_return": 0, "total_return_pct": 0,
                "total_dividends": round(total_dividends, 2),
                "total_dividends_pct": 0,
            }

        last_value = snapshots[-1]["position_value"]
        last_cost_basis = snapshots[-1]["cost_basis"]
        last_cumulative_invested = snapshots[-1].get("cumulative_invested", 0)
        total_return = last_value - last_cost_basis
        total_return_pct = (total_return / last_cost_basis * 100) if last_cost_basis > 0 else 0
        total_dividends_pct = (total_dividends / last_cumulative_invested * 100) if last_cumulative_invested > 0 else 0

        return {
            "success": True,
            "symbol": symbol.upper(),
            "period": period,
            "snapshots": snapshots,
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_dividends": round(total_dividends, 2),
            "total_dividends_pct": round(total_dividends_pct, 2),
        }

    async def get_holding_dividends(
        self, user_id: int, symbol: str,
    ) -> List[Dict[str, Any]]:
        """Get dividend history for a single held stock, aggregated by fiscal quarter."""
        divs = self.portfolio_repo.get_dividends_for_symbol(user_id, symbol)
        if not divs:
            return []

        quarterly: Dict[tuple, dict] = {}
        for d in divs:
            fy = d.get("fiscal_year") or date.fromisoformat(str(d.get("payment_date", "2000-01-01"))).year
            fm = d.get("fiscal_month") or date.fromisoformat(str(d.get("payment_date", "2000-01-01"))).month
            fq = (fm - 1) // 3 + 1
            key = (fy, fq)
            label = f"Q{fq} {fy}"
            amt = float(d.get("amount") or 0)
            aps = amt / float(d.get("shares_held") or 1) if d.get("shares_held") else 0

            if key not in quarterly:
                quarterly[key] = {
                    "fiscal_year": fy,
                    "fiscal_quarter": fq,
                    "label": label,
                    "total_amount": 0.0,
                    "payments_count": 0,
                    "amount_per_share": 0.0,
                }
            quarterly[key]["total_amount"] += amt
            quarterly[key]["payments_count"] += 1
            # Weighted average amount per share
            if aps > 0:
                prev_total = quarterly[key]["total_amount"] - amt
                prev_count = quarterly[key]["payments_count"] - 1
                if prev_count > 0:
                    quarterly[key]["amount_per_share"] = (
                        (prev_total / prev_count * prev_count + aps) / quarterly[key]["payments_count"]
                    )
                else:
                    quarterly[key]["amount_per_share"] = aps

        result = sorted(quarterly.values(), key=lambda x: (x["fiscal_year"], x["fiscal_quarter"]))
        for r in result:
            r["total_amount"] = round(r["total_amount"], 2)
            r["amount_per_share"] = round(r["amount_per_share"], 4)

        return result

    # ------------------------------------------------------------------
    # P-04: Transaction history for a single symbol
    # ------------------------------------------------------------------

    async def get_holding_transactions(
        self, user_id: int, symbol: str,
    ) -> List[Dict[str, Any]]:
        """Return all BUY/SELL transactions for a symbol across user accounts."""
        txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_map = {a["account_id"]: a for a in accounts}

        result = []
        for t in txns:
            sub = (t.get("activity_sub_type") or "").upper()
            if sub not in ("BUY", "SELL"):
                continue
            td = t.get("transaction_date")
            if isinstance(td, datetime):
                td = td.date()
            result.append({
                "transaction_id": t["transaction_id"],
                "transaction_date": td.isoformat() if isinstance(td, date) else str(td),
                "activity_sub_type": sub,
                "quantity": float(t.get("quantity") or 0),
                "unit_price": float(t.get("unit_price") or 0),
                "commission": float(t.get("commission") or 0),
                "net_cash_amount": float(t.get("net_cash_amount") or 0),
                "account_name": account_map.get(t.get("account_id"), {}).get("account_name", "Unknown"),
                "account_type": account_map.get(t.get("account_id"), {}).get("account_type", ""),
            })

        result.sort(key=lambda x: x["transaction_date"], reverse=True)
        return result

    # ------------------------------------------------------------------
    # P-05: Per-account breakdown for a single symbol
    # ------------------------------------------------------------------

    async def get_holding_accounts(
        self, user_id: int, symbol: str,
    ) -> List[Dict[str, Any]]:
        """Return per-account breakdown of a single holding."""
        symbol_up = symbol.upper()
        holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        symbol_holdings = [h for h in holdings if h.get("symbol", "").upper() == symbol_up]

        enriched = await self.enrich_holdings_with_prices(symbol_holdings)

        divs = self.portfolio_repo.get_dividends_for_symbol(user_id, symbol)
        divs_by_account: Dict[int, float] = {}
        for d in divs:
            aid = d.get("account_id")
            if aid:
                divs_by_account[aid] = divs_by_account.get(aid, 0) + float(d.get("amount") or 0)

        result = []
        for h in enriched:
            shares = float(h.get("quantity") or 0)
            cost = float(h.get("total_cost") or 0)
            value = float(h.get("current_value") or 0)
            gl = value - cost
            gl_pct = (gl / cost * 100) if cost > 0 else 0
            result.append({
                "account_id": h["account_id"],
                "account_name": h.get("account_name", "Unknown"),
                "account_type": h.get("account_type", ""),
                "shares_held": shares,
                "total_cost": round(cost, 2),
                "current_value": round(value, 2),
                "unrealized_gain_loss": round(gl, 2),
                "unrealized_gain_loss_pct": round(gl_pct, 2),
                "dividends_received": round(divs_by_account.get(h["account_id"], 0), 2),
            })

        return result

    # ------------------------------------------------------------------
    # P-03: Holding-level benchmark comparison
    # ------------------------------------------------------------------

    async def get_holding_performance_compare(
        self, user_id: int, symbol: str, period: str, benchmark_symbols: List[str],
    ) -> Dict[str, Any]:
        """Compare single-stock performance against benchmarks using the
        symbol's own buy/sell cash flows (not portfolio-level deposits)."""
        perf = await self.get_holding_performance(user_id, symbol, period)
        if not perf.get("success") or not perf.get("snapshots"):
            return {
                "success": True, "period": period,
                "portfolio": [], "benchmarks": [],
            }

        snapshots = perf["snapshots"]
        start_date, end_date = self._period_to_date_range(period)

        first_nonzero = next(
            (i for i, s in enumerate(snapshots) if s["position_value"] > 0), 0
        )
        snapshots_subset = snapshots[first_nonzero:]
        if not snapshots_subset:
            return {
                "success": True, "period": period,
                "portfolio": snapshots, "benchmarks": [],
            }

        initial_value = snapshots_subset[0]["position_value"]
        snapshot_dates = [s["date"] for s in snapshots_subset]

        txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
        holding_cashflows = []
        for t in txns:
            qty = Decimal(str(t.get("quantity") or 0))
            price = Decimal(str(t.get("unit_price") or 0))
            commission = Decimal(str(t.get("commission") or 0))
            td = t.get("transaction_date")
            if isinstance(td, str):
                td = date.fromisoformat(td)
            elif isinstance(td, datetime):
                td = td.date()
            sub = (t.get("activity_sub_type") or "").upper()
            if sub == "BUY" or (sub == "" and qty > 0):
                amount = float(qty * price + commission)
                holding_cashflows.append({"date": td, "amount": amount})
            elif sub == "SELL" or (sub == "" and qty < 0):
                amount = -(float(abs(qty) * price - commission))
                holding_cashflows.append({"date": td, "amount": amount})
        holding_cashflows.sort(key=lambda x: x["date"])

        benchmark_series_list = []
        if benchmark_symbols:
            for sym in benchmark_symbols:
                company = await self.financial_repo.get_company_by_symbol(sym)
                if not company:
                    logger.info("Holding benchmark %s not found — skipping", sym)
                    continue
                series = self._simulate_benchmark_value(
                    benchmark_company_id=company["company_id"],
                    start_date=start_date,
                    end_date=end_date,
                    initial_value=initial_value,
                    cashflow_deltas=holding_cashflows,
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
            "portfolio": [
                {"date": s["date"], "value": s["position_value"]}
                for s in snapshots_subset
            ],
            "benchmarks": benchmark_series_list,
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

    async def get_portfolio_allocation(
        self, user_id: int, group_by: str = "sector",
        account_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Get portfolio allocation breakdown grouped by sector, geography, or account.

        When group_by='sector', returns a two-level hierarchy:
          types[].sectors[] — grouped by security_type first, then by sector.

        When group_by='geography' or 'account', returns flat segments.

        When account_ids is provided, only those accounts are included.
        None or empty list = all user accounts.
        """
        if account_ids is None:
            accounts = self.portfolio_repo.get_user_accounts(user_id)
            account_ids = [a["account_id"] for a in accounts]
        else:
            user_accounts = self.portfolio_repo.get_user_accounts(user_id)
            valid_ids = {a["account_id"] for a in user_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]

        if not account_ids:
            return {
                "success": True,
                "group_by": group_by,
                "segments": [],
                "total_value": 0,
            }

        holdings = await self.enrich_holdings_with_prices(
            self.portfolio_repo.get_user_all_holdings(user_id)
        )
        holdings = [h for h in holdings if h.get("account_id") in account_ids]

        if not holdings:
            return {
                "success": True,
                "group_by": group_by,
                "segments": [],
                "total_value": 0,
            }

        SECURITY_TYPE_LABELS = {
            "stock": "Stocks",
            "etf": "ETFs",
            "fund": "Funds",
            "index": "Indices",
            "crypto": "Cryptocurrencies",
            "currency": "Currencies",
        }

        if group_by == "sector":
            return self._group_allocation_by_type(holdings, SECURITY_TYPE_LABELS)
        else:
            return self._group_allocation_flat(holdings, group_by)

    def _group_allocation_by_type(
        self, holdings: List[Dict[str, Any]],
        type_labels: Dict[str, str],
    ) -> Dict[str, Any]:
        """Two-level grouping: security_type → sector."""
        types: Dict[str, Dict[str, Any]] = {}

        for h in holdings:
            st = h.get("security_type") or "stock"
            sector = h.get("sector") or "Unknown"

            value = h.get("current_value") or 0
            cost = h.get("total_cost") or 0

            if st not in types:
                types[st] = {"type": st, "value": 0, "cost": 0, "count": 0,
                             "sectors": {}}

            t = types[st]
            t["value"] += value
            t["cost"] += cost
            t["count"] += 1

            if sector not in t["sectors"]:
                t["sectors"][sector] = {"value": 0, "cost": 0, "count": 0}
            t["sectors"][sector]["value"] += value
            t["sectors"][sector]["cost"] += cost
            t["sectors"][sector]["count"] += 1

        total_value = sum(t["value"] for t in types.values())

        type_list = []
        flat_segments = []
        for st, t in sorted(types.items(), key=lambda x: x[1]["value"], reverse=True):
            type_total = t["value"]
            sector_list = [
                {
                    "segment": s_key,
                    "value": round(s["value"], 2),
                    "weight": round((s["value"] / type_total * 100), 2) if type_total > 0 else 0,
                    "count": s["count"],
                    "gain_loss": round(s["value"] - s["cost"], 2),
                }
                for s_key, s in sorted(t["sectors"].items(), key=lambda x: x[1]["value"], reverse=True)
            ]

            type_label = type_labels.get(st, st.capitalize())
            type_list.append({
                "type": st,
                "type_label": type_label,
                "value": round(t["value"], 2),
                "weight": round((t["value"] / total_value * 100), 2) if total_value > 0 else 0,
                "count": t["count"],
                "gain_loss": round(t["value"] - t["cost"], 2),
                "sectors": sector_list,
            })

            # Also populate flat segments for backward compat
            for seg in sector_list:
                flat_segments.append({
                    "segment": f"{type_label} / {seg['segment']}",
                    "value": seg["value"],
                    "weight": round((seg["value"] / total_value * 100), 2) if total_value > 0 else 0,
                    "count": seg["count"],
                    "gain_loss": seg["gain_loss"],
                })

        return {
            "success": True,
            "group_by": "sector",
            "segments": flat_segments,
            "types": type_list,
            "total_value": round(total_value, 2),
        }

    def _group_allocation_flat(
        self, holdings: List[Dict[str, Any]], group_by: str,
    ) -> Dict[str, Any]:
        """Flat grouping for geography or account views."""
        segments: Dict[str, Dict[str, Any]] = {}

        for h in holdings:
            if group_by == "geography":
                key = h.get("market_group") or "OTHER"
            elif group_by == "account":
                key = h.get("account_name") or "Unknown Account"
            else:
                key = "Other"

            value = h.get("current_value") or 0
            cost = h.get("total_cost") or 0

            if key not in segments:
                segments[key] = {"value": 0, "cost": 0, "count": 0}
            segments[key]["value"] += value
            segments[key]["cost"] += cost
            segments[key]["count"] += 1

        total_value = sum(s["value"] for s in segments.values())
        segment_list = [
            {
                "segment": key,
                "value": round(s["value"], 2),
                "weight": round((s["value"] / total_value * 100), 2) if total_value > 0 else 0,
                "count": s["count"],
                "gain_loss": round(s["value"] - s["cost"], 2),
            }
            for key, s in sorted(segments.items(), key=lambda x: x[1]["value"], reverse=True)
        ]

        return {
            "success": True,
            "group_by": group_by,
            "segments": segment_list,
            "total_value": round(total_value, 2),
        }

    async def get_benchmarks(self) -> List[Dict[str, Any]]:
        """List all active benchmarks from benchmark_config — delegates to shared repository logic."""
        from infrastructure.repositories.analysis_repository import AnalysisRepository
        from infrastructure.repositories.valuation_repository import ValuationRepository
        repo = AnalysisRepository(ValuationRepository())
        return await repo.list_active_benchmarks()

    async def get_performance_compare(
        self, user_id: int, period: str, benchmark_symbols: List[str],
        account_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """
        Compare portfolio performance against benchmark indices.

        Uses the "same cash flows" approach: simulates what each benchmark
        would be worth if the same deposits/withdrawals were invested in it
        instead of the portfolio. Both portfolio and benchmark series are
        in dollar terms, allowing a direct side-by-side comparison.

        When account_ids is provided, only transactions from those accounts
        are used. None or empty list = all user accounts.
        """
        if account_ids is None:
            accounts = self.portfolio_repo.get_user_accounts(user_id)
            account_ids = [a["account_id"] for a in accounts]
        else:
            user_accounts = self.portfolio_repo.get_user_accounts(user_id)
            valid_ids = {a["account_id"] for a in user_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]

        start_date, end_date = self._period_to_date_range(period, account_ids)

        perf = await self.get_portfolio_performance(user_id, period, account_ids)
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
