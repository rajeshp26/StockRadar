# backend/application/services/portfolio_service.py
"""
Portfolio Service — Business logic for portfolio management.
"""

import asyncio
import hashlib
import itertools
import logging
import re
import time
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache
from typing import Any, ClassVar

import numpy as np

from application.parsers.portfolio_parser import (
    ParseResult,
    canonical_brokerage_code,
    get_parser,
)
from application.services.benchmark_series_guard import (
    BenchmarkSeriesGuard,
    compute_series_fingerprint,
    price_signature,
)
from application.services.portfolio_value_series_guard import (
    PortfolioValueSeriesGuard,
    compute_portfolio_series_fingerprint,
)
from config import settings
from database import supabase
from infrastructure.repositories.benchmark_series_repository import (
    BenchmarkSeriesRepository,
)
from infrastructure.repositories.financial_repository import (
    SupabaseFinancialRepository as FinancialRepository,
)
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
from infrastructure.repositories.portfolio_value_series_repository import (
    PortfolioValueSeriesRepository,
)
from providers.base import StockDataProvider
from providers.yfinance_provider import YFinanceProvider
from shared.cdr_utils import CDR_RATIO, is_cdr_transaction
from shared.fx_service import FXService
from shared.portfolio_event_payload import (
    build_transaction_event_data,
    csv_import_event_key,
)
from shared.portfolio_stats import (
    annualize_return,
    compute_annualized_volatility,
    compute_daily_returns,
    compute_max_drawdown,
    compute_portfolio_mwr,
    compute_portfolio_twr,
)
from shared.price_rows import sanitize_daily_price_rows
from shared.snapshot_builder import (
    _classify_lot_action,
    build_snapshot_row,
    check_snapshot_spike,
    convert_holding_fx,
    resolve_price_forward_filled,
)
from shared.time_utils import now_utc, parse_db_timestamp
from shared.transfer_reconciliation import (
    reconcile_transfers,
    transfer_leg_counts_by_date,
)
from shared.valuation import adjust_cdr_price

logger = logging.getLogger(__name__)

# The CSV parser converts dots to hyphens (BBD.A -> BBD-A, ENB.TO -> ENB-TO) so
# stored company tickers stay stable. Option/contract identifiers contain spaces
# and are not tickers: keep them on the event, but never send them to a provider.
_PROVIDER_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")
_PROVIDER_SUFFIX_RE = re.compile(r"-(TO|V|NE)$", re.IGNORECASE)


def _is_provider_ticker(symbol: str | None) -> bool:
    """True only for identifiers a market-data provider can resolve."""
    return bool(symbol) and bool(_PROVIDER_SYMBOL_RE.fullmatch(symbol.strip().upper()))


def _provider_lookup_symbol(symbol: str, exchange_override: str | None = None) -> str:
    """Return the yfinance form of a stored portfolio ticker.

    ``ENB-TO`` is the stored form (fingerprint-stable); ``ENB.TO`` is what Yahoo
    understands. The conversion is confined to the provider boundary so stored
    symbols and event idempotency keys never change.
    """
    provider = _PROVIDER_SUFFIX_RE.sub(lambda m: "." + m.group(1).upper(), symbol.strip().upper())
    if exchange_override == "TOR" and not provider.endswith(".TO"):
        provider += ".TO"
    elif exchange_override == "VAN" and not provider.endswith(".V"):
        provider += ".V"
    return provider


# Timing decorator
def timed(logger_: logging.Logger = logger):
    def decorator(fn):
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await fn(*args, **kwargs)
            finally:
                elapsed = (time.perf_counter() - start) * 1000
                logger_.info(f"[TIMING] {fn.__name__} took {elapsed:.1f}ms")
        return wrapper
    return decorator


def _map_quote_type(quote_type: str | None) -> str:
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
        portfolio_repo: PortfolioRepository | None = None,
        financial_repo: FinancialRepository | None = None,
        stock_provider: StockDataProvider | None = None,
        defeat_beta_provider: Any | None = None,
    ):
        self.portfolio_repo = portfolio_repo or PortfolioRepository()
        self.financial_repo = financial_repo or FinancialRepository()
        self.stock_provider = stock_provider or YFinanceProvider()
        if defeat_beta_provider is None:
            from dependencies import get_defeat_beta_provider
            defeat_beta_provider = get_defeat_beta_provider()
        self.defeat_beta_provider = defeat_beta_provider
        # Keep strong references to fire-and-forget tasks so they are not
        # garbage-collected mid-run (ruff RUF006).
        self._background_tasks: set[asyncio.Task] = set()

    # ========================================================================
    # DUPLICATE DETECTION
    # ========================================================================

    def _calculate_csv_hash(self, csv_content: str) -> str:
        """Calculate SHA-256 hash of CSV content for duplicate detection."""
        return hashlib.sha256(csv_content.encode('utf-8')).hexdigest()

    async def check_duplicate_import(
        self, user_id: int, csv_hash: str
    ) -> dict[str, Any] | None:
        """
        Check if this CSV has been imported before.

        A no-op re-upload also gets a history row, so report the most recent
        import that actually inserted rows; otherwise the duplicate warning
        claims the file was previously imported with "0 transactions".

        Returns:
            Previous import record if found, None otherwise
        """
        try:
            def query():
                return (
                    supabase.table("portfolio_import_history")
                    .select("*")
                    .eq("user_id", user_id)
                    .eq("csv_hash", csv_hash)
                )

            res = (
                query()
                .eq("status", "completed")
                .gt("imported_rows", 0)
                .order("started_at", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0]

            res = query().order("started_at", desc=True).limit(1).execute()
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
        account_filter: list[str] | None = None,
        csv_filename: str | None = None,
    ) -> dict[str, Any]:
        """
        Queue a CSV import for background processing.

        Validates input, creates a pending job record, and kicks off
        async background processing. Returns immediately.
        """
        # Legacy brokerage labels (e.g. WS_TRADE) must resolve to the same
        # brokerage, parser and idempotency namespace as "wealthsimple";
        # otherwise selecting "Wealthsimple Trade" would duplicate every row.
        brokerage_code = canonical_brokerage_code(brokerage_code)

        csv_hash = self._calculate_csv_hash(csv_content)
        csv_size = len(csv_content.encode('utf-8'))
        import_batch_id = uuid.uuid4()

        # 1. Check for a previous upload of this exact file. It is informational
        # only: imports are append-only and resume by row identity, so a repeat
        # upload must be allowed to add rows that arrived after the last export.
        previous_import = await self.check_duplicate_import(user_id, csv_hash)
        duplicate_warning = None
        if previous_import:
            duplicate_warning = (
                "This CSV has already been imported; only new rows will be added. "
                f"Previously imported on {previous_import['started_at']}: "
                f"{previous_import['imported_rows']} transactions"
            )

        # 2. Validate brokerage
        brokerage = self.portfolio_repo.get_brokerage_by_code(brokerage_code)
        if not brokerage:
            return {"success": False, "error": f"Unsupported brokerage: {brokerage_code}"}

        brokerage_id = brokerage["brokerage_id"]

        # 3. Parse CSV (quick validation parse)
        parser = get_parser(brokerage_code)
        parse_result: ParseResult = parser.parse_csv(csv_content, account_filter)

        if not parse_result.success:
            # Surface the parser's concrete reason (e.g. "Missing required
            # columns: effective_date") — a bare "CSV parsing failed" is what
            # made the UI show a generic failure for a fixable CSV problem.
            details = "; ".join(parse_result.errors[:3]) if parse_result.errors else "Unknown parsing error"
            return {
                "success": False,
                "error": f"CSV parsing failed: {details}",
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
        task = asyncio.create_task(
            self._process_import_background(
                import_batch_id=import_batch_id,
                csv_hash=csv_hash,
                csv_size=csv_size,
                account_filter=account_filter,
                parse_result=parse_result,
                brokerage_id=brokerage_id,
                brokerage_code=brokerage_code,
                user_id=user_id,
            )
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        warnings = list(parse_result.warnings)
        if duplicate_warning:
            warnings.append(duplicate_warning)

        return {
            "success": True,
            "import_batch_id": str(import_batch_id),
            "status": "pending",
            "total_rows": total_rows,
            "account_types": parse_result.account_type_summary,
            "warnings": warnings,
            "duplicate_import": bool(previous_import),
            "previous_import_date": (
                previous_import.get("started_at") if previous_import else None
            ),
            "previous_import_id": (
                previous_import.get("import_id") if previous_import else None
            ),
            "warning": duplicate_warning,
        }

    async def _process_import_background(
        self,
        import_batch_id: uuid.UUID,
        csv_hash: str,
        csv_size: int,
        account_filter: list[str] | None,
        parse_result: ParseResult,
        brokerage_id: int,
        brokerage_code: str,
        user_id: int,
    ) -> dict[str, Any]:
        """
        Process a queued CSV import in the background.
        Updates progress in portfolio_import_history throughout.
        """
        repo = self.portfolio_repo
        created_company_ids: list[int] = []

        try:
            repo.update_import_progress(import_batch_id, status="processing", rows_parsed=0)

            # --- Resolve duplicates BEFORE any writes ---
            # The event log is the only persisted import result. Resolving keys
            # first means a failed lookup (e.g. PostgREST 414 on a large in.(...)
            # filter) cannot leave orphan accounts/companies behind, and duplicate
            # rows never trigger company creation.
            from infrastructure.repositories.event_store import EventStore

            event_store = EventStore()
            event_keys = [
                csv_import_event_key(
                    brokerage_code, tx.row_fingerprint, tx.fingerprint_occurrence
                )
                for tx in parse_result.transactions
            ]
            existing_keys = event_store.get_existing_idempotency_keys(event_keys)
            new_flags = [key not in existing_keys for key in event_keys]
            duplicate_count = len(event_keys) - sum(new_flags)

            # --- Create accounts ---
            accounts_map: dict[str, int] = {}
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
            # Only genuinely new rows may create companies; duplicate-only symbols
            # have no event to reference their company and would be pure debris.
            symbols_meta: dict[str, str | None] = {}
            for tx, is_new in zip(parse_result.transactions, new_flags, strict=True):
                if is_new and tx.symbol:
                    override = getattr(tx, "exchange_override", None)
                    if tx.symbol not in symbols_meta:
                        symbols_meta[tx.symbol] = override
                    elif override:
                        symbols_meta[tx.symbol] = "TOR"  # prefer TOR if any transaction is CDR
            companies_map, symbols_created = await self._ensure_companies_exist_with_tracking(
                symbols_meta
            )
            created_company_ids = [
                companies_map[symbol] for symbol in symbols_created if symbol in companies_map
            ]

            # --- Convert to DB records ---
            db_transactions = []
            symbols_missing = set()

            for tx, is_new in zip(parse_result.transactions, new_flags, strict=True):
                account_id = accounts_map[tx.account_external_id]
                company_id = None

                if tx.symbol:
                    company_id = companies_map.get(tx.symbol)
                    if is_new and not company_id:
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
                    "exchange_override": tx.exchange_override,
                    "currency": tx.currency,
                    "quantity": float(tx.quantity) if tx.quantity else None,
                    "unit_price": float(tx.unit_price) if tx.unit_price else None,
                    "commission": float(tx.commission),
                    "net_cash_amount": float(tx.net_cash_amount),
                    "raw_data": tx.raw_data,
                    "entry_source": "csv_import",
                    "created_by_user_id": None,
                })

            # --- Write events only (legacy transactions table is frozen) ---
            # Keys are derived from row content, not from this batch's UUID or
            # row position, so an overlapping export resumes instead of
            # duplicating history.
            transfer_reconciliation = None
            new_events = []
            for tx, tx_data, event_key, is_new in zip(
                parse_result.transactions,
                db_transactions,
                event_keys,
                new_flags,
                strict=True,
            ):
                if not is_new:
                    continue
                new_events.append({
                    "event_type": "transaction_imported",
                    "aggregate_id": f"account_{tx_data.get('account_id')}",
                    "aggregate_type": "account",
                    "data": build_transaction_event_data(
                        account_id=tx_data.get("account_id"),
                        company_id=tx_data.get("company_id"),
                        transaction_date=tx_data.get("transaction_date"),
                        settlement_date=tx_data.get("settlement_date"),
                        activity_type=tx_data.get("activity_type"),
                        activity_sub_type=tx_data.get("activity_sub_type"),
                        direction=tx_data.get("direction"),
                        symbol=tx_data.get("symbol"),
                        security_name=tx_data.get("security_name"),
                        exchange_override=tx_data.get("exchange_override"),
                        quantity=tx_data.get("quantity"),
                        unit_price=tx_data.get("unit_price"),
                        net_cash_amount=tx_data.get("net_cash_amount"),
                        currency=tx_data.get("currency"),
                    ),
                    "metadata": {
                        "import_batch_id": str(import_batch_id),
                        "entry_source": "csv_import",
                    },
                    "idempotency_key": event_key,
                })

            # The event log is the only persisted import result: a failure here
            # must fail the job, not report a successful import with zero rows.
            if new_events:
                event_store.append_events_batch(new_events)
            inserted_count = len(new_events)
            transfer_reconciliation = reconcile_transfers(new_events)

            repo.update_import_progress(import_batch_id, rows_inserted=inserted_count)

            # --- Update account timestamps ---
            for account_id in accounts_map.values():
                repo.update_account_import_timestamp(account_id)

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
                "holdings_updated": 0,
                "dividends_extracted": dividends_extracted,
                "symbols_missing": list(symbols_missing),
                "symbols_created": symbols_created,
                "companies_created_count": len(symbols_created),
                "account_types": parse_result.account_type_summary,
                "transfer_reconciliation": (
                    {
                        "transfer_count": transfer_reconciliation.transfer_count,
                        "paired_count": transfer_reconciliation.paired_count,
                        "unpaired_count": transfer_reconciliation.unpaired_count,
                    }
                    if transfer_reconciliation is not None
                    else None
                ),
                "warnings": list(parse_result.warnings),
            }

            warnings = list(parse_result.warnings)
            if (
                transfer_reconciliation is not None
                and transfer_reconciliation.transfer_count
            ):
                warnings.append(transfer_reconciliation.summary())
                leg_warnings = transfer_reconciliation.warnings
                warnings.extend(leg_warnings[:10])
                if len(leg_warnings) > 10:
                    warnings.append(
                        f"...and {len(leg_warnings) - 10} further unpaired transfer "
                        "leg(s) not listed individually"
                    )
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
                duplicate_rows=duplicate_count,
                skipped_rows=parse_result.skipped_rows,
                accounts_created=accounts_created,
                accounts_updated=len(accounts_map),
                symbols_created=len(symbols_created),
            )

            logger.info(
                f"Background import {import_batch_id} complete: "
                f"{inserted_count} inserted, {duplicate_count} duplicates, "
                f"{len(accounts_map)} accounts updated"
            )
            return result

        except Exception as e:
            logger.error(f"Background import {import_batch_id} failed: {e}", exc_info=True)
            # Compensate for companies this batch created: without events they
            # are unreferenced debris. Never delete a company an event uses.
            self._purge_unreferenced_companies(created_company_ids)
            repo.update_import_progress(
                import_batch_id,
                status="failed",
                error_message=f"Import failed: {e!s}",
            )
            return {"success": False, "error": str(e)}

    @staticmethod
    def _purge_unreferenced_companies(company_ids: list[int]) -> None:
        """Delete only companies created by a failed import that no event references."""
        if not company_ids:
            return
        try:
            rows = (
                supabase.table("portfolio_events")
                .select("data")
                .in_("data->>company_id", [str(cid) for cid in company_ids])
                .execute()
                .data
                or []
            )
            referenced = {
                int((row.get("data") or {}).get("company_id"))
                for row in rows
                if isinstance(row.get("data"), dict)
                and (row.get("data") or {}).get("company_id") is not None
            }
            orphans = [cid for cid in company_ids if cid not in referenced]
            if orphans:
                supabase.table("companies").delete().in_("company_id", orphans).execute()
                logger.warning(f"Removed {len(orphans)} company record(s) from failed import")
        except Exception as cleanup_exc:
            logger.warning(f"Could not clean up companies from failed import: {cleanup_exc}")

    async def _ensure_companies_exist_with_tracking(
        self, symbols: dict[str, str | None]
    ) -> tuple[dict[str, int], list[str]]:
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

        companies_map: dict[str, int] = {}
        created_symbols: list[str] = []

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
            provider_calls = 0
            for symbol in sorted(missing):
                if not _is_provider_ticker(symbol):
                    # Option/contract identifiers (e.g. "GIS   260918P00030000")
                    # are not tickers. Keep them on the event with no company_id;
                    # never send them to a market-data provider.
                    logger.warning(
                        f"Skipping company creation for non-ticker identifier {symbol!r}"
                    )
                    continue
                try:
                    # Rate-limit: insert a small delay between provider calls to
                    # avoid triggering Yahoo Finance rate limiting (especially
                    # during CSV imports with many unique tickers).
                    if provider_calls > 0:
                        await asyncio.sleep(0.5)
                    provider_calls += 1
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



    async def _enrich_holdings(
        self, holdings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not holdings:
            return holdings
        cids = list(set(h["company_id"] for h in holdings if h.get("company_id")))
        prices = {}
        # Fetch cdr_ratio for CDR pricing
        cdr_ratios: dict[int, float] = {}
        if cids:
            try:
                cmr = supabase.table("current_market_data").select("company_id, current_price").in_("company_id", cids).execute()
                for row in cmr.data or []:
                    cid = row["company_id"]
                    px = row.get("current_price")
                    if px is not None:
                        prices[cid] = float(px)
            except Exception:
                pass
            # Fetch cdr_ratio from companies table (per-company ratio)
            try:
                comp_result = supabase.table("companies").select("company_id, cdr_ratio") \
                    .in_("company_id", cids).execute()
                for row in comp_result.data or []:
                    cid = row["company_id"]
                    ratio = row.get("cdr_ratio")
                    if ratio is not None:
                        cdr_ratios[cid] = float(ratio)
            except Exception:
                pass
        # Resolve currencies + FX before pricing: CDR prices FX-convert inside the
        # single valuation rule, and price_currency stays "CAD" afterwards so the
        # already-CAD cost basis is not re-converted below.
        account_ids = list(set(h.get("account_id") for h in holdings if h.get("account_id")))
        account_currency_map: dict[int, str] = {}
        if account_ids:
            try:
                acc_result = supabase.table("portfolio_accounts").select("account_id, currency") \
                    .in_("account_id", account_ids).execute()
                account_currency_map = {
                    a["account_id"]: a.get("currency", "CAD") for a in (acc_result.data or [])
                }
            except Exception:
                pass
        today = now_utc().date()
        fx_svc = FXService(supabase) if settings.ENABLE_FX_CONVERSION else None

        for h in holdings:
            cid = h.get("company_id")
            price = prices.get(cid)
            qty = h.get("quantity", 0) or 0
            total_cost = h.get("total_cost", 0) or 0
            avg_cost = h.get("average_cost", 0) or 0
            if price is not None:
                effective_price = price
                if h.get("exchange_override") == "TOR":
                    acc_currency = account_currency_map.get(h.get("account_id"), "CAD")
                    fx_rate = None
                    if fx_svc is not None:
                        try:
                            fx_rate = fx_svc.get_rate("USD", acc_currency, today)
                        except Exception:
                            fx_rate = None
                    adjusted = adjust_cdr_price(
                        price,
                        is_cdr=True,
                        cdr_ratio=cdr_ratios.get(cid),
                        price_source="current_market_data",
                        account_currency=acc_currency,
                        fx_rate=fx_rate,
                        layer="portfolio_service.enrich",
                        company_id=cid,
                    )
                    effective_price = float(adjusted.price)
                    h["price_currency"] = "CAD"  # CAD now; do not re-convert below
                h["current_price"] = effective_price
                h["current_value"] = effective_price * qty
            else:
                h["current_price"] = float(avg_cost) if avg_cost else 0.0
                h["current_value"] = float(total_cost) if total_cost else 0.0

        # Apply FX conversion per-account
        if settings.ENABLE_FX_CONVERSION:
            for h in holdings:
                acc_id = h.get("account_id")
                acc_currency = account_currency_map.get(acc_id, "CAD") if acc_id else "CAD"
                raw_value = Decimal(str(h.get("current_value") or 0))
                raw_cost = Decimal(str(h.get("total_cost") or 0))
                conv_value, conv_cost = convert_holding_fx(
                    h, raw_value, raw_cost, acc_currency,
                    fx_svc, today, True,
                )
                h["current_value"] = float(conv_value)
                h["total_cost"] = float(conv_cost)
                h["value_currency"] = acc_currency
        else:
            for h in holdings:
                h["value_currency"] = "CAD"

        for h in holdings:
            total_cost = h.get("total_cost", 0) or 0
            h["unrealized_gain_loss"] = h["current_value"] - float(total_cost)
            h["unrealized_gain_loss_pct"] = (
                (h["unrealized_gain_loss"] / float(total_cost) * 100)
                if float(total_cost) > 0 else 0.0
            )
        holdings.sort(key=lambda h: h.get("current_value") or 0, reverse=True)
        return holdings

    def _get_price_currency(self, company_id: int | None) -> str:
        """Look up the price currency for a company from the companies table."""
        if not company_id:
            return "USD"
        try:
            result = supabase.table("companies").select("currency") \
                .eq("company_id", company_id).maybe_single().execute()
            if result.data:
                return result.data.get("currency", "USD")
        except Exception:
            pass
        return "USD"

    def aggregate_holdings(
        self, holdings: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Group holdings by company_id, aggregating quantities and costs.

        Returns one record per symbol with combined quantities, weighted
        average cost, and a per-account breakdown.
        """
        groups: dict[int, dict[str, Any]] = {}

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

    async def _get_current_price(self, symbol: str) -> dict[str, float] | None:
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

            # Tier 2: price_history (latest close, split-adjusted via adj_close)
            res = (
                supabase.table("price_history")
                .select("adj_close, close_price, price_date")
                .eq("company_id", cid)
                .order("price_date", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                row = res.data[0]
                adj = row.get("adj_close")
                if adj is None:
                    adj = row.get("close_price")
                if adj is not None:
                    return {"price": float(adj), "source": "price_history"}

        except Exception as e:
            logger.error(f"Failed to get price for {symbol}: {e}")

        return None

    # ========================================================================
    # ON-DEMAND PRICE FETCH (Phase 2)
    # ========================================================================



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
                    daily_out = sanitize_daily_price_rows(daily_rows, default_source="yfinance")
                    if daily_out:
                        split_rows = await self.defeat_beta_provider.get_splits_optimized(symbol, cid)
                        if split_rows:
                            await self.financial_repo.upsert_splits(split_rows)
                        await self.financial_repo.upsert_price_history(daily_out)
                        await self.financial_repo.update_price_refresh_marker(cid)
                        logger.info("Price history loaded for %s: %d daily rows", symbol, len(daily_out))

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
        self, symbol: str, company_id: int, exchange: str | None = None
    ) -> list[dict[str, Any]]:
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

    # ========================================================================
    # DIVIDEND EXTRACTION
    # ========================================================================

    async def _extract_dividends(self, account_ids: list[int]) -> int:
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
                            "fiscal_year": payment_date.year if isinstance(payment_date, date) else parse_db_timestamp(payment_date).year,
                            "fiscal_month": payment_date.month if isinstance(payment_date, date) else parse_db_timestamp(payment_date).month,
                        })

        if dividend_records:
            return self.portfolio_repo.insert_dividends(dividend_records)

        return 0

    # ========================================================================
    # PORTFOLIO SUMMARY
    # ========================================================================

    @timed()
    async def get_user_portfolio_overview(
        self, user_id: int,
        account_ids: list[int] | None = None,
        display_currency: str | None = None,
    ) -> dict[str, Any]:
        """
        Get comprehensive portfolio overview for user.

        When account_ids is provided, scope to those accounts only.
        None or empty list = all user accounts.
        When display_currency is provided, converts all values to that currency.

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

        all_holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        holdings = await self._enrich_holdings(all_holdings)
        if account_ids:
            holdings = [h for h in holdings if h.get("account_id") in account_ids]

        # Calculate totals
        total_value = sum(h.get("current_value") or 0 for h in holdings)
        total_cost = sum(h.get("total_cost") or 0 for h in holdings)
        total_gain_loss = total_value - total_cost
        total_gain_loss_pct = (
            (total_gain_loss / total_cost * 100) if total_cost > 0 else 0
        )

        # Get dividend summary for current year (batched query)
        current_year = now_utc().year
        ytd_dividends = Decimal("0")
        account_ids_list = [a["account_id"] for a in accounts]

        all_divs = self.portfolio_repo.get_accounts_dividends_by_year(account_ids_list, current_year)
        ytd_dividends = sum(
            Decimal(str(d.get("amount") or 0)) for d in all_divs
        )

        # Lifetime dividends (all records, no fiscal-year filter)
        lifetime_divs = self.portfolio_repo.get_accounts_dividends_by_year(account_ids_list)
        lifetime_dividends = sum(
            Decimal(str(d.get("amount") or 0)) for d in lifetime_divs
        )

        # Current cash per account, FX-converted to account currency.
        # Mirrors the snapshot path so the overview "Total Value" (holdings +
        # cash) aligns with the performance chart's snapshot total_value.
        today = now_utc().date()
        cash_by_account: dict[int, Decimal] = {}
        total_cash = Decimal("0.00")
        try:
            from shared.fx_service import FXService
            _fx_svc = FXService(supabase) if settings.ENABLE_FX_CONVERSION else None
            for account in accounts:
                acc_ccy = account.get("currency") or "CAD"
                cb = self.portfolio_repo.get_cash_balance(
                    account["account_id"], today, acc_ccy, _fx_svc,
                )
                cash_by_account[account["account_id"]] = cb
                total_cash += cb
        except Exception as e:
            logger.warning(f"Cash balance computation failed for overview (user {user_id}): {e}")

        # Top 10 holdings by value
        top_holdings = sorted(
            holdings, key=lambda h: h.get("current_value") or 0, reverse=True
        )[:10]

        # Account breakdown
        value_currency = display_currency or (holdings[0].get("value_currency") if holdings else "USD")
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
                "cash_balance": float(cash_by_account.get(account["account_id"], Decimal("0.00"))),
                "gain_loss": float(acc_value - acc_cost),
                "gain_loss_pct": (
                    float((acc_value - acc_cost) / acc_cost * 100) if acc_cost > 0 else 0
                ),
                "value_currency": value_currency,
            })

        return {
            "success": True,
            "net_worth": float(total_value),
            "total_value": float(total_value) + float(total_cash),
            "cash_balance": float(total_cash),
            "total_cost_basis": float(total_cost),
            "total_gain_loss": float(total_gain_loss),
            "total_gain_loss_pct": float(total_gain_loss_pct),
            "ytd_dividends": float(ytd_dividends),
            "total_dividends": float(lifetime_dividends),
            "total_holdings_count": len(holdings),
            "accounts_count": len(accounts),
            "top_holdings": top_holdings,
            "account_breakdown": account_breakdown,
            "value_currency": value_currency,
        }
    # ========================================================================
    # ALL-ACCOUNTS DIVIDENDS
    # ========================================================================

    async def get_user_all_dividends(
        self, user_id: int,
        account_ids: list[int] | None = None,
    ) -> dict[str, Any]:
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

        current_year = now_utc().year
        all_divs = self.portfolio_repo.get_accounts_dividends_by_year(account_ids, current_year)
        current_year_total = sum(Decimal(str(d.get("amount", 0))) for d in all_divs)
        all_monthly_summaries = self.portfolio_repo.get_accounts_monthly_dividends(account_ids, months=12)

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
        account_ids: list[int] | None = None,
        limit: int = 100,
        activity_type: str | None = None,
        search: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> dict[str, Any]:
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

        all_transactions = self.portfolio_repo.get_accounts_transactions(
            account_ids, limit=limit, activity_types=activity_types,
        )

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
    ) -> dict[str, Any]:
        """Get detailed dividend history for an account with company names."""
        repo = self.portfolio_repo
        account = repo.get_account_by_id(account_id)
        if not account:
            return {"success": False, "error": "Account not found"}
        if account["user_id"] != user_id:
            return {"success": False, "error": "Access denied"}

        dividends = repo.get_account_dividends_by_year(account_id, None)
        dividends.sort(key=lambda d: d.get("payment_date", ""), reverse=True)

        current_year = now_utc().year
        current_year_total = sum(
            float(d.get("amount", 0)) for d in dividends
            if d.get("fiscal_year") == current_year
        )

        company_ids = list({d.get("company_id") for d in dividends if d.get("company_id")})
        company_names: dict[int, str] = {}
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
        symbol: str | None,
        quantity: Decimal | None,
        unit_price: Decimal | None,
        commission: Decimal = Decimal("0"),
        notes: str | None = None,
    ) -> dict[str, Any]:
        try:
            company_id = None
            company_created = False
            company_name = None

            if symbol:
                existing_check = (
                    supabase.table("companies")
                    .select("company_id, company_name")
                    .eq("ticker_symbol", symbol)
                    .limit(1)
                    .execute()
                )

                if existing_check.data and len(existing_check.data) > 0:
                    company_id = existing_check.data[0]["company_id"]
                    company_name = existing_check.data[0]["company_name"]
                    company_created = False
                    logger.info(f"Using existing company: {symbol} (ID={company_id})")
                else:
                    logger.info(f"Creating new company for symbol: {symbol}")
                    company_id = await self._create_company_from_symbol(symbol)

                    if company_id:
                        company_created = True
                        created_company = (
                            supabase.table("companies")
                            .select("company_name")
                            .eq("company_id", company_id)
                            .single()
                            .execute()
                        )
                        company_name = created_company.data.get("company_name", symbol) if created_company.data else symbol
                        logger.info(f"Created new company: {company_name} (ID={company_id})")

            from infrastructure.repositories.event_store import EventStore
            event_store = EventStore()
            idempotency_key = f"manual_{uuid.uuid4().hex}"
            net_cash_amount = 0.0
            if quantity and unit_price:
                net_cash_amount = float(quantity) * float(unit_price) - float(commission)

            event = event_store.append_event(
                event_type="transaction_imported",
                aggregate_id=f"account_{account_id}",
                aggregate_type="account",
                data=build_transaction_event_data(
                    account_id=account_id,
                    company_id=company_id,
                    transaction_date=transaction_date.isoformat(),
                    activity_type=activity_type,
                    symbol=symbol,
                    quantity=float(quantity) if quantity else None,
                    unit_price=float(unit_price) if unit_price else None,
                    net_cash_amount=net_cash_amount,
                    notes=notes,
                ),
                metadata={
                    "entry_source": "manual",
                    "created_by_user_id": user_id,
                },
                idempotency_key=idempotency_key,
            )

            logger.info(
                f"Manual transaction created: {activity_type} {symbol} "
                f"for account {account_id} by user {user_id}"
                + (f" (NEW COMPANY: {company_name})" if company_created else "")
            )

            return {
                "success": True,
                "transaction_id": event.get("id"),
                "transaction": event,
                "company_created": company_created,
                "company_name": company_name,
            }

        except Exception as e:
            logger.error(f"Failed to add manual transaction: {e}", exc_info=True)
            return {"success": False, "error": f"Failed to create transaction: {e!s}"}

    async def _create_company_from_symbol(self, symbol: str, exchange_override: str | None = None) -> int | None:
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
            # 1. Convert the stored (fingerprint-stable) ticker to provider form.
            #    ENB-TO is stored in companies/events; Yahoo only knows ENB.TO.
            base_symbol = _provider_lookup_symbol(symbol)
            lookup_symbol = _provider_lookup_symbol(symbol, exchange_override)

            # Attempt lookup
            sd = self.stock_provider.get_stock_details(lookup_symbol)

            # 2. If override failed (e.g., CDR no longer trades on TSX),
            #    fall back to the unsuffixed provider symbol
            if not sd and exchange_override:
                logger.warning(f"Exchange override {exchange_override} failed for {symbol}, falling back to normal lookup")
                sd = self.stock_provider.get_stock_details(base_symbol)

            # 3. Retry with Canadian exchange suffixes if still no data. Skip a
            #    suffix already present: ENB.TO + .TO => ENB.TO.TO (404).
            if not sd:
                for suffix in [".TO", ".V"]:
                    if base_symbol.endswith(suffix):
                        continue
                    provider_symbol = base_symbol + suffix
                    sd = self.stock_provider.get_stock_details(provider_symbol)
                    if sd:
                        logger.info(f"Resolved {symbol} → {provider_symbol}")
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
        self, period: str, account_ids: list[int] | None = None
    ) -> tuple[date, date]:
        """Convert period string to (start_date, end_date).

        For 'ALL' period, dynamically determines start from the earliest
        transaction date across the given accounts, falling back to a safe
        default if no account_ids or transactions exist.
        """
        end = now_utc().date()
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
        if p == "1D" or p == "1W":
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
    ) -> list[str]:
        """Generate snapshot date strings at intervals appropriate for the period."""
        step = self._step_for_period(period)
        dates: list[str] = []
        current_d = start_date
        while current_d <= end_date:
            dates.append(current_d.isoformat())
            current_d += step
        end_str = end_date.isoformat()
        if dates[-1] != end_str:
            dates.append(end_str)
        return dates

    # Chart precision by range (A6c — reaffirmed A6b). The served series matches
    # the period the user is reading: daily for the short ranges (1W/1M = one bar
    # per day), monthly for 1Y/YTD, quarterly for the long ranges (5Y/ALL). This
    # mirrors the range-dependent cadence professional chart apps use and keeps a
    # bar chart readable — one bar per period instead of ~165 daily slivers over
    # a year (measured on user 1: 1Y daily would be 165 pts / 19 KB, ALL daily
    # 1370 pts / 156 KB). Bucketed ranges emit ONE point per period; see
    # `_downsample_snapshots`.
    _RESOLUTION_BY_PERIOD: ClassVar[dict[str, str]] = {
        "1D": "day",
        "1W": "day",
        "1M": "day",
        "3M": "day",
        "1Y": "month",
        "YTD": "month",
        "5Y": "quarter",
        "ALL": "quarter",
    }

    @classmethod
    def _resolution_for_period(cls, period: str) -> str:
        """Chart precision for a period: daily, monthly or quarterly (A6c)."""
        return cls._RESOLUTION_BY_PERIOD.get(period.upper(), "day")

    @classmethod
    def _downsample_snapshots(
        cls, snapshots: list[dict[str, Any]], resolution: str
    ) -> list[dict[str, Any]]:
        """Reduce the daily series to the bucketed grid the period renders.

        The precision follows the period (see `_RESOLUTION_BY_PERIOD`): the short
        ranges are served daily, 1Y/YTD monthly and 5Y/ALL quarterly. When
        bucketing applies, each calendar period contributes exactly ONE point, so
        no month/quarter ever carries two x-axis entries:

        * the first period contributes its first observation (the range start)
          and the last period its last observation (the range end), so the chart
          spans the requested window instead of starting/ending a bucket late;
        * every interior period contributes its last observation (period-end
          close).

        This is presentation only. Return metrics must be computed from the full
        daily series before this is applied -- deriving TWR or best_day from
        month-apart rows is the defect A6 removed.
        """
        if resolution == "day" or len(snapshots) <= 1:
            return snapshots

        def bucket_key(iso: str) -> tuple[int, int]:
            d = date.fromisoformat(iso)
            period_index = d.month if resolution == "month" else (d.month - 1) // 3 + 1
            return (d.year, period_index)

        first_key = bucket_key(snapshots[0]["date"])
        kept: list[dict[str, Any]] = [snapshots[0]]
        for prev, snap in itertools.pairwise(snapshots):
            if bucket_key(snap["date"]) != bucket_key(prev["date"]):
                # The first period is already represented by snapshots[0];
                # emitting its period-end close as well was the duplicate
                # window-start entry the chart showed twice.
                if bucket_key(prev["date"]) == first_key:
                    continue
                if kept[-1] is not prev:
                    kept.append(prev)
        if kept[-1] is not snapshots[-1]:
            kept.append(snapshots[-1])
        return kept

    def _compute_fifo_snapshots(
        self,
        lots: dict[tuple, list],
        in_txns_sorted: list[dict],
        sorted_dates: list[str],
        price_map: dict[str, dict[str, float]],
        cumulative_invested_map: dict[date, float] | None = None,
    ) -> list[dict]:
        """Core FIFO snapshot engine — used by both portfolio and single-stock.

        Args:
            lots: Opening FIFO lots per (account_id, symbol) key.
            in_txns_sorted: In-period transactions sorted by date.
            sorted_dates: Snapshot date strings in ascending order.
            price_map: symbol -> {date_str: close_price}.
            cumulative_invested_map: Optional date->cumulative_invested lookup.

        Returns list of {date, value, cost_basis, net_deposits} dicts.
        """
        snapshots: list[dict] = []
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
                qty_held = sum(lot["quantity"] for lot in lot_list)
                if qty_held <= 0:
                    continue
                avg_cost = sum(lot["quantity"] * lot["cost_per_share"] for lot in lot_list) / qty_held
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

    def _get_cashflow_deltas(self, account_ids: list[int]) -> list[dict]:
        """Fetch MoneyMovement & BonusPayment transactions as sorted cash flow deltas.

        Returns list of {date: date, amount: float} sorted chronologically.
        Positive amount = deposit (money in), negative = withdrawal (money out).
        """
        raw: list[dict] = []
        cft_batch = self.portfolio_repo.get_accounts_transactions(
            account_ids, activity_types=["MoneyMovement", "BonusPayment"]
        )
        for t in cft_batch:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            elif isinstance(d, datetime):
                t["transaction_date"] = d.date()
        raw.extend(cft_batch)
        raw.sort(key=lambda x: x["transaction_date"])

        return [
            {"date": t["transaction_date"], "amount": float(t.get("net_cash_amount") or 0)}
            for t in raw
        ]

    def _compute_returns_from_snapshots(
        self, snapshots: list[dict], period: str
    ) -> dict[str, Any]:
        """Compute all return metrics from a snapshot list.

        Returns dict with:
          total_return       — dollar gain (last - first)
          total_return_pct   — simple return %  (backward-compatible)
          twr_pct            — time-weighted return %
          mwr_pct            — money-weighted return % (Modified Dietz)
          cagr_pct           — annualized TWR (CAGR)
          best_day / worst_day
        """
        if not snapshots:
            return {
                "total_return": 0, "total_return_pct": 0,
                "twr_pct": 0, "mwr_pct": 0, "cagr_pct": 0,
                "best_day": None, "worst_day": None,
            }

        first_value = snapshots[0]["value"]
        last_value = snapshots[-1]["value"]
        total_return = last_value - first_value
        total_return_pct = (
            ((last_value - first_value) / first_value * 100)
            if first_value > 0 else 0
        )

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

        twr = compute_portfolio_twr(snapshots)
        mwr = compute_portfolio_mwr(snapshots)

        period_days = 0
        if len(snapshots) >= 2:
            d0 = date.fromisoformat(snapshots[0]["date"])
            dn = date.fromisoformat(snapshots[-1]["date"])
            period_days = (dn - d0).days
        cagr = annualize_return(twr, period_days)

        return {
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "twr_pct": round(twr * 100, 2),
            "mwr_pct": round(mwr * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "best_day": best_day,
            "worst_day": worst_day,
        }

    @timed()
    async def get_portfolio_performance(
        self, user_id: int, period: str = "1Y",
        account_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if account_ids is None:
            accounts = self.portfolio_repo.get_user_accounts(user_id)
            account_ids = [a["account_id"] for a in accounts]
        else:
            user_accounts = self.portfolio_repo.get_user_accounts(user_id)
            valid_ids = {a["account_id"] for a in user_accounts}
            account_ids = [aid for aid in account_ids if aid in valid_ids]

        if not account_ids:
            returns = self._compute_returns_from_snapshots([], period)
            return {
                "success": True, "period": period,
                "snapshots": [],
                "data_source": "snapshots", "data_quality_flag": "OK",
                "return_methodology": "twr",
                **returns,
            }

        if not getattr(settings, "ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", False):
            return await self._get_portfolio_performance_legacy(
                user_id, period, account_ids
            )

        start_date, end_date = self._period_to_date_range(period, account_ids)
        account_key = ",".join(str(a) for a in sorted(account_ids))
        snapshots_repo = PortfolioSnapshotsRepository()
        # Scalar-only read: the chart needs no holdings detail, and shipping
        # holdings_json cost ~3.8 KB/row (~18 MB for a multi-year window) on
        # every request. Measured 4,120 ms -> 63 ms for the same rows.
        #
        # The read spans INCEPTION -> end, not the requested window: Layer 4
        # keys the stored curve on an input fingerprint over these rows, and a
        # fingerprint is only comparable across periods if every period hashes
        # the same canonical row set. The period then slices the series, so a
        # 1M request and an ALL request agree on every shared date.
        first_dates = [
            d for d in (snapshots_repo.get_first_snapshot_date(a) for a in account_ids)
            if d is not None
        ]
        read_from = min(first_dates) if first_dates else start_date
        raw_snapshots = snapshots_repo.get_portfolio_snapshots_series(
            account_ids, read_from, end_date
        )

        # The fallback trigger stays tied to the REQUESTED WINDOW having rows
        # (not the full read): a 1D request before today's snapshot lands must
        # still fall back exactly as it did when the read was windowed.
        window_snapshots = [
            s for s in raw_snapshots
            if start_date.isoformat() <= s["snapshot_date"] <= end_date.isoformat()
        ]
        if not window_snapshots:
            result = await self._compute_performance_fallback(
                user_id, period, account_ids, start_date, end_date
            )
            result["data_source"] = "computed_fallback"
            return result

        # ── Layer 3: fingerprint-keyed response cache ────────────────────────
        # The key carries (a) a fingerprint of the exact snapshot scalars the
        # series derives from (full history, the same canonical row set Layer 4
        # hashes) and (b) the RESOLVED window dates, because the window ends at
        # now_utc().date(). An appended or corrected snapshot changes the
        # fingerprint; a later day resolves a later window. Either misses, so a
        # cached response cannot outlive the inputs or the window it was built
        # for. Cache failures never fail a request (the module guards them).
        cache = None
        cache_key = None
        if getattr(settings, "ENABLE_PORTFOLIO_RESPONSE_CACHE", True):
            from application.services.portfolio_response_cache import (
                compute_cache_key,
                compute_snapshot_fingerprint,
                get_response_cache,
            )
            cache = get_response_cache()
            cache_key = compute_cache_key(
                account_key=account_key,
                period=period,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                snapshot_fingerprint=compute_snapshot_fingerprint(raw_snapshots),
            )
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug(
                    "performance response cache hit for %s (%s)", period, cache_key[:8]
                )
                cached["served_from_cache"] = True
                return cached

        # ── Layer 4: materialised value series (migration 017) ───────────────
        # The stored curve is reused only when its INPUT fingerprint still
        # matches the snapshot rows this request just read — so an appended,
        # corrected or backdated snapshot rebuilds before any stored point is
        # served, and the store can never be staler than the snapshot table.
        # A period switch or a weekend (window end moved, inputs unchanged) is
        # a slice of the stored build at zero merge cost. A rebuild re-derives
        # the full inception->end curve so any later period is also a slice.
        series_repo = None
        series_fp = None
        if getattr(settings, "ENABLE_PORTFOLIO_VALUE_SERIES", True):
            series_repo = PortfolioValueSeriesRepository()
            series_fp = compute_portfolio_series_fingerprint(account_key, raw_snapshots)
            try:
                stored = series_repo.get_series(account_key)
            except Exception as e:  # the repo guards; belt and braces
                logger.info("value series read failed (%s) - computing live", e)
                stored = None
            if stored is not None and not stored.is_empty:
                decision = PortfolioValueSeriesGuard().decide(
                    stored_fingerprint=stored.fingerprint,
                    stored_last_mark=stored.last_mark_date,
                    expected_fingerprint=series_fp,
                    required_end=end_date,
                )
                if decision.can_reuse:
                    window_points = [
                        p for p in stored.points
                        if start_date.isoformat() <= p["date"] <= end_date.isoformat()
                    ]
                    if window_points:
                        logger.debug(
                            "value series hit for %s (%s)",
                            account_key, decision.reason,
                        )
                        response = self._performance_response_from_series(
                            window_points, period, raw_snapshots
                        )
                        if cache is not None and cache_key is not None:
                            # Warm the response cache too, so the next repeat
                            # visit does not even reach the series store.
                            cache.put(cache_key, response)
                            response["served_from_cache"] = False
                        return response

        use_locf = getattr(settings, "ENABLE_PERFORMANCE_LOCF", True)

        # fx_applied=False => unconverted USD valued as CAD; a step onto such a
        # date is an artifact, not a market move. The count is persisted on the
        # snapshot (migration 016), so this no longer walks holdings_json.
        fx_unconverted_dates: set[str] = set()
        fx_by_date: dict[str, int] = defaultdict(int)
        for s in raw_snapshots:
            n = s.get("fx_unconverted_count") or 0
            if n > 0:
                fx_unconverted_dates.add(s["snapshot_date"])
                fx_by_date[s["snapshot_date"]] += n

        by_account: dict[int, list[dict]] = defaultdict(list)
        for s in raw_snapshots:
            by_account[s["account_id"]].append(s)

        accounts_with_data = list(by_account.keys())
        all_dates = sorted({s["snapshot_date"] for s in raw_snapshots})
        latest_date = all_dates[-1] if all_dates else None

        account_iters = {}
        current_snap: dict[int, dict | None] = {}
        for aid in accounts_with_data:
            it = iter(by_account[aid])
            account_iters[aid] = it
            try:
                current_snap[aid] = next(it)
            except StopIteration:
                current_snap[aid] = None

        last_value: dict[int, float] = {}
        last_cost: dict[int, float] = {}
        last_cash: dict[int, float] = {}
        last_nd: dict[int, float] = {}
        locf_count = 0
        merged: dict[str, dict] = {}
        # Per-date build metadata, persisted with the curve (migration 017) so
        # a response served from the store reports the exact locf_count and
        # spike_detected the live merge would, without re-deriving per account.
        series_meta: dict[str, dict] = {}
        spike_detected = False
        spike_threshold = getattr(settings, "SNAPSHOT_SPIKE_THRESHOLD", 0.20)
        prev_merged: dict[str, Any] | None = None
        # I5: transfer dates are loaded lazily, only if a real-data spike fires.
        # Attribution is metadata; a failure here must never fail the response.
        transfer_dates: dict[str, int] | None = None

        def _transfer_dates() -> dict[str, int]:
            nonlocal transfer_dates
            if transfer_dates is None:
                try:
                    from infrastructure.repositories.event_store import EventStore

                    legs = EventStore().get_transfer_legs(account_ids)
                    transfer_dates = transfer_leg_counts_by_date(legs)
                except Exception as exc:  # advisory; never block a valuation
                    logger.debug("transfer spike attribution unavailable: %s", exc)
                    transfer_dates = {}
            return transfer_dates

        for d in all_dates:
            total_value = 0.0
            total_cost = 0.0
            total_cash = 0.0
            total_nd = 0.0
            date_with_locf = False
            date_points_used = 0
            date_suppressed = False

            # Save per-account state before update (for spike revert)
            saved_last_value = last_value.copy()
            saved_last_cost = last_cost.copy()
            saved_last_cash = last_cash.copy()
            saved_last_nd = last_nd.copy()

            for aid in accounts_with_data:
                cs = current_snap.get(aid)
                if cs is not None and cs["snapshot_date"] == d:
                    total_value += cs["total_value"]
                    total_cost += cs["cost_basis"]
                    total_cash += cs.get("cash_balance", 0)
                    total_nd += cs.get("net_deposits", 0)
                    date_points_used += 1
                    last_value[aid] = cs["total_value"]
                    last_cost[aid] = cs["cost_basis"]
                    last_cash[aid] = cs.get("cash_balance", 0)
                    last_nd[aid] = cs.get("net_deposits", 0)
                    try:
                        current_snap[aid] = next(account_iters[aid])
                    except StopIteration:
                        current_snap[aid] = None
                elif aid in last_value:
                    if use_locf:
                        total_value += last_value[aid]
                        total_cost += last_cost.get(aid, 0)
                        total_cash += last_cash.get(aid, 0)
                        total_nd += last_nd.get(aid, 0)
                        date_with_locf = True

            current_merged = {
                "date": d, "value": round(total_value, 2),
                "cost_basis": round(total_cost, 2),
                "cash_balance": round(total_cash, 2),
                "net_deposits": round(total_nd, 2),
            }

            if prev_merged is not None:
                spike = check_snapshot_spike(
                    {"total_value": prev_merged["value"],
                     "net_deposits": prev_merged["net_deposits"],
                     "snapshot_date": prev_merged["date"]},
                    {"total_value": current_merged["value"],
                     "net_deposits": current_merged["net_deposits"],
                     "snapshot_date": current_merged["date"]},
                    threshold=spike_threshold,
                )
                if spike and d != latest_date and (date_with_locf or d in fx_unconverted_dates):
                    # Suppress only known-artifact dates (fx-conversion failure
                    # or LOCF gap-fill). A fully-real date must NOT be
                    # suppressed: the frozen anchor re-triggers every later check.
                    spike_detected = True
                    date_suppressed = True
                    if d in fx_unconverted_dates and not date_with_locf:
                        logger.warning(
                            "FX-unconverted spike on %s: %s", d, spike["message"]
                        )
                        # Keep per-account state: it holds real, fx-flawed values.
                    else:
                        logger.warning(
                            "LOCF merge spike on %s: %s", d, spike["message"]
                        )
                        # Revert per-account state so future LOCF uses old values
                        last_value = saved_last_value
                        last_cost = saved_last_cost
                        last_cash = saved_last_cash
                        last_nd = saved_last_nd
                        date_with_locf = False
                    current_merged = {
                        "date": d,
                        "value": prev_merged["value"],
                        "cost_basis": prev_merged["cost_basis"],
                        "cash_balance": prev_merged["cash_balance"],
                        "net_deposits": prev_merged["net_deposits"],
                    }
                elif spike:
                    # A spike on a fully-real date is genuine source data: the
                    # value stays in the curve (suppressing it would freeze a
                    # wrong anchor and re-trigger every later check). Attribute
                    # the step so the log explains *why* it is real instead of
                    # asserting "real data" (I5 / USER-ASK A3).
                    legs = _transfer_dates().get(d, 0)
                    if legs:
                        logger.info(
                            "LOCF merge: spike on %s explained by "
                            "InternalSecurityTransfer round-trip (%d legs); "
                            "value retained: %s",
                            d, legs, spike["message"],
                        )
                    else:
                        logger.info(
                            "LOCF merge: spike on %s retained "
                            "(no LOCF/FX artifact marker): %s",
                            d, spike["message"],
                        )

            merged[d] = current_merged
            prev_merged = current_merged
            if date_with_locf:
                locf_count += 1
            series_meta[d] = {
                "points_used": date_points_used,
                "locf_filled": 1 if date_with_locf else 0,
                "spike_suppressed": 1 if date_suppressed else 0,
            }

        # Overall quality = quality of the latest snapshot (not worst-of-all).
        # Historical STALE_PRICE/FORWARD_FILL flags are informational, not system failures.
        latest_snap = max(raw_snapshots, key=lambda s: s["snapshot_date"]) if raw_snapshots else None
        overall_quality = latest_snap.get("data_quality_flag", "OK") if latest_snap else "OK"

        if locf_count and accounts_with_data:
            locf_pct = locf_count / len(all_dates) * 100
            logger.info(
                "LOCF applied to %d/%d dates (%.1f%%) across %d accounts",
                locf_count, len(all_dates), locf_pct, len(accounts_with_data),
            )

        # The merge covered inception -> end; the response serves only the
        # requested window, exactly as the windowed read did before Layer 4.
        sorted_dates = sorted(
            d for d in merged
            if start_date.isoformat() <= d <= end_date.isoformat()
        )
        snapshots = [merged[d] for d in sorted_dates]

        if not snapshots:
            returns = self._compute_returns_from_snapshots([], period)
            return {
                "success": True, "period": period,
                "snapshots": [],
                "data_source": "snapshots", "data_quality_flag": overall_quality,
                "return_methodology": "twr",
                "spike_detected": False,
                **returns,
            }

        if series_repo is not None and series_fp is not None:
            # shortcut: every rebuild re-upserts the full inception->end curve
            # even when only the tail day changed (~10k rows for a 5-year,
            # 10-account history). Upgrade when a daily rebuild is observed to
            # rewrite >10k unchanged rows per account set per day: diff the
            # stored points (already read above) against the computed ones and
            # upsert only the changed dates plus the new fingerprint.
            build_points = [
                {
                    "date": d,
                    "value": merged[d]["value"],
                    "holdings_market_value": round(
                        merged[d]["value"] - merged[d]["cash_balance"], 2
                    ),
                    "cost_basis": merged[d]["cost_basis"],
                    "cash_balance": merged[d]["cash_balance"],
                    "net_deposits": merged[d]["net_deposits"],
                    "fx_unconverted_count": fx_by_date.get(d, 0),
                    "points_used": series_meta[d]["points_used"],
                    "locf_filled": series_meta[d]["locf_filled"],
                    "spike_suppressed": series_meta[d]["spike_suppressed"],
                }
                for d in sorted(merged.keys())
            ]
            try:
                series_repo.upsert_points(
                    account_key, build_points,
                    fingerprint=series_fp, last_mark_date=end_date,
                )
            except Exception as e:  # the repo guards; belt and braces
                logger.info(
                    "value series write failed (%s) - response still served", e
                )

        # Metrics come from the FULL daily series; only the served series is bucketed.
        # The former _compress_snapshots_by_interval was removed because it sampled one
        # row per step days and then derived best_day/worst_day/twr from rows a month
        # apart, so the spike threshold never saw the series it was meant to judge. That
        # defect cannot recur while the ordering below holds: _compute_returns_from_
        # snapshots runs on every daily row, and bucketing happens after it.
        #
        # Buckets are calendar month/quarter period-end closes rather than LTTB, because
        # a portfolio value series is read as month-end and quarter-end balances; LTTB
        # would keep shape at the cost of dates that mean nothing financially.
        # Rationale: .planning/USER-ASK.md A6.
        returns = self._compute_returns_from_snapshots(snapshots, period)
        chart_snapshots = self._downsample_snapshots(
            snapshots, self._resolution_for_period(period)
        )

        response = {
            "success": True,
            "period": period,
            "snapshots": chart_snapshots,
            "data_source": "snapshots",
            "data_quality_flag": overall_quality,
            "return_methodology": "twr",
            "locf_count": locf_count,
            "spike_detected": spike_detected,
            **returns,
        }
        if cache is not None and cache_key is not None:
            # Store the exact payload that was computed. The key already
            # fingerprints these inputs, so this entry is valid for them alone.
            cache.put(cache_key, response)
            response["served_from_cache"] = False
        return response

    def _performance_response_from_series(
        self,
        window_points: list[dict[str, Any]],
        period: str,
        raw_snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the performance response from stored curve points (Layer 4).

        Must produce the same payload the live merge would for the same window:
        returns and the chart are derived from the same daily series keys the
        merge emits, locf_count and spike_detected come from the per-point flags
        the merge persisted (they cannot be re-derived per account from the
        aggregated curve), and the quality flag comes from the snapshot rows
        THIS request already read — never from the store — so it cannot lag the
        snapshot table the input fingerprint was just verified against.
        """
        series = [
            {
                "date": p["date"],
                "value": float(p["value"]),
                "cost_basis": float(p["cost_basis"]),
                "cash_balance": float(p["cash_balance"]),
                "net_deposits": float(p["net_deposits"]),
            }
            for p in window_points
        ]
        latest = max(raw_snapshots, key=lambda s: s["snapshot_date"])
        returns = self._compute_returns_from_snapshots(series, period)
        chart_snapshots = self._downsample_snapshots(
            series, self._resolution_for_period(period)
        )
        return {
            "success": True,
            "period": period,
            "snapshots": chart_snapshots,
            "data_source": "snapshots",
            "data_quality_flag": latest.get("data_quality_flag", "OK"),
            "return_methodology": "twr",
            "locf_count": sum(int(p.get("locf_filled") or 0) for p in window_points),
            "spike_detected": any(
                int(p.get("spike_suppressed") or 0) for p in window_points
            ),
            **returns,
        }

    async def _get_portfolio_performance_legacy(
        self, user_id: int, period: str = "1Y",
        account_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        start_date, end_date = self._period_to_date_range(period, account_ids)
        return await self._compute_performance_fallback(
            user_id, period, account_ids, start_date, end_date
        )

    async def _compute_performance_fallback(
        self, user_id, period, account_ids, start_date, end_date
    ):
        txns_batch = self.portfolio_repo.get_accounts_transactions(
            account_ids, activity_types=["Trade"]
        )
        for t in txns_batch:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            elif isinstance(d, datetime):
                t["transaction_date"] = d.date()

        all_txns = sorted(txns_batch, key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))
        pre_txns = [t for t in all_txns if t["transaction_date"] < start_date]
        in_txns = [t for t in all_txns if start_date <= t["transaction_date"] <= end_date]

        # Pre-fetch ALL cash-related transactions once for in-memory cash/ND computation
        all_cash_txns = self.portfolio_repo.get_accounts_transactions(
            account_ids, activity_types=None
        )
        for t in all_cash_txns:
            d = t.get("transaction_date")
            if isinstance(d, str):
                t["transaction_date"] = date.fromisoformat(d)
            elif isinstance(d, datetime):
                t["transaction_date"] = d.date()

        # FX service for cash balance conversion in cached functions
        _perf_fx_svc = None
        if settings.ENABLE_FX_CONVERSION:
            try:
                from database import supabase as _db
                from shared.fx_service import FXService as FXServiceCls
                _perf_fx_svc = FXServiceCls(_db)
            except Exception:
                _perf_fx_svc = None

        @cache
        def _cached_cash_balance(aid: int, dt_str: str, acct_ccy: str) -> Decimal:
            target = date.fromisoformat(dt_str)
            total = Decimal("0.00")
            for t in all_cash_txns:
                if t["account_id"] == aid and t["transaction_date"] <= target:
                    nca = t.get("net_cash_amount") or 0
                    act = t.get("activity_type", "")
                    if act in PortfolioRepository.CASH_ACTIVITY_TYPES:
                        txn_ccy = (t.get("currency") or "CAD").upper()
                        if txn_ccy != acct_ccy.upper() and _perf_fx_svc:
                            rate = _perf_fx_svc.get_rate(txn_ccy, acct_ccy.upper(), target)
                            if rate is not None:
                                nca = float(Decimal(str(nca)) * rate)
                        total += Decimal(str(nca))
            return total

        @cache
        def _cached_net_deposits(aid: int, dt_str: str, acct_ccy: str) -> Decimal:
            target = date.fromisoformat(dt_str)
            total = Decimal("0.00")
            for t in all_cash_txns:
                if t["account_id"] == aid and t["transaction_date"] <= target:
                    act = t.get("activity_type", "")
                    if act in ("MoneyMovement", "BonusPayment"):
                        nca = t.get("net_cash_amount") or 0
                        txn_ccy = (t.get("currency") or "CAD").upper()
                        if txn_ccy != acct_ccy.upper() and _perf_fx_svc:
                            rate = _perf_fx_svc.get_rate(txn_ccy, acct_ccy.upper(), target)
                            if rate is not None:
                                nca = float(Decimal(str(nca)) * rate)
                        total += Decimal(str(nca))
            return total

        lots: dict[tuple, list] = defaultdict(list)
        for t in pre_txns:
            action = _classify_lot_action(t)
            if action is None:
                continue
            cid = t.get("company_id")
            if not cid:
                continue
            key = (t.get("account_id"), cid)
            if action == "BUY":
                qty = Decimal(str(t.get("quantity") or 0))
                price = Decimal(str(t.get("unit_price") or 0))
                commission = Decimal(str(t.get("commission") or 0))
                cost_per_share = price + (commission / qty) if qty else price
                lots[key].append({
                    "quantity": float(qty), "cost_per_share": float(cost_per_share),
                    "date": t["transaction_date"].isoformat(),
                    "symbol": t.get("symbol", ""),
                    "is_cdr": is_cdr_transaction(t.get("raw_data"), t.get("security_name")),
                })
            elif action == "SELL":
                sell_qty = abs(float(t.get("quantity") or 0))
                remaining = sell_qty
                while remaining > 0 and lots[key]:
                    lot = lots[key][0]
                    if lot["quantity"] <= remaining:
                        remaining -= lot["quantity"]
                        lots[key].pop(0)
                    else:
                        lot["quantity"] -= remaining
                        remaining = 0

        company_ids = list({t.get("company_id") for t in all_txns if t.get("company_id")})
        price_map = self.portfolio_repo.get_all_prices_historical(company_ids, end_date)

        sorted_dates = self._generate_snapshot_dates(period, start_date, end_date)

        # Get account currencies
        all_accounts = self.portfolio_repo.get_user_accounts(user_id)
        acc_currency = {a["account_id"]: a.get("currency", "CAD") for a in all_accounts}

        snapshots = []
        in_txns_sorted = sorted(in_txns, key=lambda x: (x["transaction_date"], x.get("transaction_id", 0)))
        txn_index = 0

        for d in sorted_dates:
            current_date = date.fromisoformat(d)
            while txn_index < len(in_txns_sorted) and in_txns_sorted[txn_index]["transaction_date"].isoformat() <= d:
                t = in_txns_sorted[txn_index]
                action = _classify_lot_action(t)
                cid = t.get("company_id")
                if action and cid:
                    key = (t.get("account_id"), cid)
                    if action == "BUY":
                        qty = Decimal(str(t.get("quantity") or 0))
                        price = Decimal(str(t.get("unit_price") or 0))
                        commission = Decimal(str(t.get("commission") or 0))
                        cost_per_share = price + (commission / qty) if qty else price
                        lots[key].append({
                            "quantity": float(qty), "cost_per_share": float(cost_per_share),
                            "date": d,
                            "symbol": t.get("symbol", ""),
                            "is_cdr": is_cdr_transaction(t.get("raw_data"), t.get("security_name")),
                        })
                    elif action == "SELL":
                        sell_qty = abs(float(t.get("quantity") or 0))
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

            # Key by (cid, is_cdr), not cid: one row can carry only one exchange_override, so a
            # collapsed mixed position prices one lot wrongly (BLK-027's 10x overvaluation).
            cid_holdings_by_account: dict[int, dict[tuple[int, bool], dict]] = defaultdict(dict)
            for (aid, cid), lot_list in lots.items():
                by_cdr: dict[bool, list] = defaultdict(list)
                for lot in lot_list:
                    by_cdr[bool(lot.get("is_cdr"))].append(lot)
                for is_cdr, cdr_lots in by_cdr.items():
                    qty_held = sum(lot["quantity"] for lot in cdr_lots)
                    if qty_held <= 0.001:
                        continue
                    avg_cost = sum(lot["quantity"] * lot["cost_per_share"] for lot in cdr_lots) / qty_held
                    total_cost_holding = qty_held * avg_cost
                    earliest_lot_date = min((lot["date"] for lot in cdr_lots if lot.get("date")), default=None)
                    lots_for_holding = [
                        {"quantity": lot["quantity"], "cost_per_share": lot["cost_per_share"], "date": lot.get("date")}
                        for lot in cdr_lots
                    ]
                    symbol = next((lot.get("symbol", "") for lot in cdr_lots if lot.get("symbol")), "")
                    cid_holdings_by_account[aid][(cid, is_cdr)] = {
                        "company_id": cid, "symbol": symbol,
                        "quantity": qty_held,
                        "total_cost": total_cost_holding,
                        "average_cost": avg_cost,
                        "account_id": aid,
                        "trade_date": earliest_lot_date,
                        "lots": lots_for_holding,
                        "exchange_override": "TOR" if is_cdr else None,
                    }

            # Build per-account snapshots and combine
            total_value = Decimal("0")
            total_cost = Decimal("0")
            total_cash = Decimal("0")
            total_net_deposits = Decimal("0")

            for aid, cid_holdings in cid_holdings_by_account.items():
                holdings_state = list(cid_holdings.values())
                prices_by_company = {}
                for cid in company_ids:
                    result = resolve_price_forward_filled(cid, current_date, price_map)
                    if result:
                        prices_by_company[cid] = result

                # Use in-memory cached computation instead of N+1 DB queries
                dt_str = current_date.isoformat()
                account_currency = acc_currency.get(aid, "CAD")
                cash_balance = _cached_cash_balance(aid, dt_str, account_currency)
                net_deposits = _cached_net_deposits(aid, dt_str, account_currency)

                total_cash += cash_balance
                total_net_deposits += net_deposits

                snapshot_row = build_snapshot_row(
                    account_id=aid,
                    snapshot_date=current_date,
                    holdings_state=holdings_state,
                    cash_balance=cash_balance,
                    net_deposits=net_deposits,
                    prices_by_company=prices_by_company,
                    job_id="fallback",
                    account_currency=account_currency,
                    lot_cdr_authoritative=True,
                )
                total_value += Decimal(str(snapshot_row["total_value"]))
                total_cost += Decimal(str(snapshot_row["cost_basis"]))

            snapshots.append({
                "date": d,
                "value": round(float(total_value), 2),
                "cost_basis": round(float(total_cost), 2),
                "net_deposits": round(float(total_net_deposits), 2),
            })

        if not snapshots:
            return {"snapshots": [], "total_return": 0, "total_return_pct": 0}

        returns = self._compute_returns_from_snapshots(snapshots, period)

        return {
            "success": True,
            "period": period,
            "snapshots": snapshots,
            "data_source": "computed_fallback",
            "data_quality_flag": "OK",
            "return_methodology": "twr",
            **returns,
        }

    # ========================================================================
    # SINGLE-HOLDING PERFORMANCE
    # ========================================================================

    def check_holding_exists(self, user_id: int, symbol: str) -> bool:
        """Check if user holds a position in the given symbol."""
        holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        return any(h.get("symbol", "").upper() == symbol.upper() for h in holdings)

    # ------------------------------------------------------------------
    # Performance Summary helpers (used by get_holding_performance)
    # ------------------------------------------------------------------

    def _compute_monthly_returns(
        self, snapshots: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if len(snapshots) < 2:
            return None, None

        monthly_map: dict[str, list[float]] = {}
        for i in range(1, len(snapshots)):
            prev_val = snapshots[i - 1]["position_value"]
            curr_val = snapshots[i]["position_value"]
            if prev_val > 0:
                ret_pct = (curr_val - prev_val) / prev_val * 100
                month_key = snapshots[i]["date"][:7]
                monthly_map.setdefault(month_key, []).append(ret_pct)

        best: dict[str, Any] | None = None
        worst: dict[str, Any] | None = None
        for month_key, returns in monthly_map.items():
            avg_ret = sum(returns) / len(returns)
            dt = datetime.strptime(month_key + "-01", "%Y-%m-%d").replace(tzinfo=UTC)
            label = dt.strftime("%b %Y")
            entry = {"month": month_key, "return_pct": round(avg_ret, 2), "label": label}
            if best is None or avg_ret > best["return_pct"]:
                best = entry
            if worst is None or avg_ret < worst["return_pct"]:
                worst = entry
        return best, worst

    def _compute_longest_drawdown(
        self, snapshots: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if len(snapshots) < 2:
            return None

        values = np.array([s["position_value"] for s in snapshots], dtype=np.float64)
        running_max = np.maximum.accumulate(values)
        drawdown_series = (values - running_max) / running_max

        longest_duration = 0
        longest_start = 0
        longest_end = 0

        current_start = None
        for i in range(len(drawdown_series)):
            if drawdown_series[i] < 0 and current_start is None:
                current_start = i
            elif drawdown_series[i] >= 0 and current_start is not None:
                duration = i - current_start
                if duration > longest_duration:
                    longest_duration = duration
                    longest_start = current_start
                    longest_end = i - 1
                current_start = None

        if current_start is not None:
            duration = len(drawdown_series) - current_start
            if duration > longest_duration:
                longest_duration = duration
                longest_start = current_start
                longest_end = len(drawdown_series) - 1

        if longest_duration == 0:
            return None

        dd_pct = float(drawdown_series[longest_end])
        is_ongoing = current_start is not None and longest_start == current_start
        return {
            "dd_pct": round(dd_pct * 100, 2),
            "start_date": snapshots[longest_start]["date"],
            "end_date": snapshots[longest_end]["date"] if not is_ongoing else None,
            "duration_days": longest_duration,
            "is_ongoing": is_ongoing,
        }

    def _compute_30d_volatility(
        self, snapshots: list[dict[str, Any]],
    ) -> float:
        values = np.array([s["position_value"] for s in snapshots], dtype=np.float64)
        daily_returns = compute_daily_returns(values)
        if len(daily_returns) < 2:
            return 0.0
        return round(compute_annualized_volatility(daily_returns) * 100, 2)

    def _compute_days_above_cost_basis(
        self, snapshots: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        total_days = len(snapshots)
        if total_days < 2:
            return None
        days_above = sum(
            1 for s in snapshots
            if s["cost_basis"] > 0 and s["position_value"] > s["cost_basis"]
        )
        return {
            "days_above": days_above,
            "total_days": total_days,
            "pct_above": round(days_above / total_days * 100, 1),
        }

    def _compute_performance_summary(
        self, snapshots: list[dict[str, Any]], total_return: float, total_dividends: float, period: str,
    ) -> dict[str, Any]:
        combined_return = round(total_return + total_dividends, 2)
        best_month, worst_month = self._compute_monthly_returns(snapshots)
        month_info = {}
        if period.upper() in ("ALL", "5Y"):
            month_info = {"best_month": None, "worst_month": None}
        else:
            month_info = {"best_month": best_month, "worst_month": worst_month}

        max_dd = self._compute_max_drawdown_info(snapshots)
        longest_dd = self._compute_longest_drawdown(snapshots)

        return {
            "combined_return": combined_return,
            **month_info,
            "max_drawdown": max_dd,
            "longest_drawdown": longest_dd,
            "volatility_30d": self._compute_30d_volatility(snapshots),
            "days_above_cost_basis": self._compute_days_above_cost_basis(snapshots),
        }

    def _compute_max_drawdown_info(
        self, snapshots: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if len(snapshots) < 2:
            return None
        values = np.array([s["position_value"] for s in snapshots], dtype=np.float64)
        _dd_value, dd_pct, peak_idx, trough_idx = compute_max_drawdown(values)
        is_ongoing = trough_idx == len(snapshots) - 1 and dd_pct < 0
        return {
            "dd_pct": round(dd_pct * 100, 2),
            "start_date": snapshots[peak_idx]["date"],
            "end_date": snapshots[trough_idx]["date"],
            "duration_days": trough_idx - peak_idx,
            "is_ongoing": is_ongoing,
        }

    async def get_holding_performance(
        self, user_id: int, symbol: str, period: str = "1Y",
    ) -> dict[str, Any]:
        """
        Compute time-series performance for a single stock in user's portfolio.

        Reuses the shared FIFO snapshot engine from _compute_fifo_snapshots()
        but filtered to a single symbol across all user accounts.
        """
        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_ids = [a["account_id"] for a in accounts]

        empty_result = {
            "success": True, "symbol": symbol.upper(), "period": period,
            "snapshots": [], "total_return": 0, "total_return_pct": 0,
            "total_dividends": 0, "total_dividends_pct": 0,
            "combined_return": 0, "best_month": None, "worst_month": None,
            "max_drawdown": None, "longest_drawdown": None,
            "volatility_30d": 0, "days_above_cost_basis": None,
        }
        if not account_ids:
            return empty_result

        txns = self.portfolio_repo.get_transactions_for_symbol(user_id, symbol)
        if not txns:
            return empty_result

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

        price_map: dict[str, dict[str, float]] = {}
        try:
            sym_up = symbol.upper()
            company_id = txns[0].get("company_id") if txns else None
            is_cdr = False
            cdr_ratio_val = None
            if company_id:
                # Check if this is a CDR holding
                try:
                    hold_check = supabase.table("portfolio_holdings").select("exchange_override") \
                        .eq("company_id", company_id).eq("exchange_override", "TOR").limit(1).execute()
                    if hold_check.data:
                        is_cdr = True
                        # Look up CDR ratio
                        comp_res = supabase.table("companies").select("cdr_ratio") \
                            .eq("company_id", company_id).maybe_single().execute()
                        if comp_res.data and comp_res.data.get("cdr_ratio") is not None:
                            cdr_ratio_val = float(comp_res.data["cdr_ratio"])
                        else:
                            cdr_ratio_val = float(CDR_RATIO)
                except Exception:
                    pass
            if company_id:
                rows = (
                    supabase.table("price_history")
                    .select("price_date, adj_close, close_price")
                    .eq("company_id", company_id)
                    .gte("price_date", (start_date - timedelta(days=7)).isoformat())
                    .lte("price_date", end_date.isoformat())
                    .order("price_date", desc=False)
                    .execute()
                )
                if rows.data:
                    for row in rows.data:
                        adj = row.get("adj_close")
                        px = float(adj if adj is not None else row["close_price"])
                        pd_str = row["price_date"]
                        if isinstance(pd_str, str):
                            pd = date.fromisoformat(pd_str)
                        elif isinstance(pd_str, datetime):
                            pd = pd_str.date()
                        else:
                            pd = pd_str
                        # Apply CDR adjustment via the single valuation rule:
                        # CDR price = (US_price / ratio) * FX (USD→CAD) when a
                        # rate is available -- the same kernel the snapshot and
                        # live overview paths use (shared.valuation).
                        if is_cdr:
                            fx_rate = None
                            try:
                                from shared.fx_service import FXService
                                fx_svc = FXService(supabase)
                                fx_rate = fx_svc.get_rate("USD", "CAD", pd)
                            except Exception:
                                pass
                            px = float(
                                adjust_cdr_price(
                                    px, is_cdr=True, cdr_ratio=cdr_ratio_val,
                                    price_source="price_history",
                                    price_currency="USD",
                                    account_currency="CAD",
                                    fx_rate=fx_rate,
                                    layer="portfolio_service.historical",
                                    company_id=company_id,
                                ).price
                            )
                        price_map.setdefault(sym_up, {})[row["price_date"]] = px
        except Exception as e:
            logger.warning(f"Failed to fetch price_history for {symbol}: {e}")

        lots: dict[tuple, list] = defaultdict(list)
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
        cumulative_invested_map: dict[date, float] = {}
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
                "combined_return": round(total_dividends, 2),
                "best_month": None, "worst_month": None,
                "max_drawdown": None, "longest_drawdown": None,
                "volatility_30d": 0, "days_above_cost_basis": None,
            }

        last_value = snapshots[-1]["position_value"]
        last_cost_basis = snapshots[-1]["cost_basis"]
        last_cumulative_invested = snapshots[-1].get("cumulative_invested", 0)
        total_return = last_value - last_cost_basis
        total_return_pct = (total_return / last_cost_basis * 100) if last_cost_basis > 0 else 0
        total_dividends_pct = (total_dividends / last_cumulative_invested * 100) if last_cumulative_invested > 0 else 0

        summary = self._compute_performance_summary(snapshots, total_return, total_dividends, period)

        return {
            "success": True,
            "symbol": symbol.upper(),
            "period": period,
            "snapshots": snapshots,
            "total_return": round(total_return, 2),
            "total_return_pct": round(total_return_pct, 2),
            "total_dividends": round(total_dividends, 2),
            "total_dividends_pct": round(total_dividends_pct, 2),
            "combined_return": summary["combined_return"],
            "best_month": summary["best_month"],
            "worst_month": summary["worst_month"],
            "max_drawdown": summary["max_drawdown"],
            "longest_drawdown": summary["longest_drawdown"],
            "volatility_30d": summary["volatility_30d"],
            "days_above_cost_basis": summary["days_above_cost_basis"],
        }

    async def get_holding_dividends(
        self, user_id: int, symbol: str,
    ) -> list[dict[str, Any]]:
        """Get dividend history for a single held stock, aggregated by fiscal quarter."""
        divs = self.portfolio_repo.get_dividends_for_symbol(user_id, symbol)
        if not divs:
            return []

        quarterly: dict[tuple, dict] = {}
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
    ) -> list[dict[str, Any]]:
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
    ) -> list[dict[str, Any]]:
        """Return per-account breakdown of a single holding."""
        symbol_up = symbol.upper()
        holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        symbol_holdings = [h for h in holdings if h.get("symbol", "").upper() == symbol_up]

        self.portfolio_repo.get_user_accounts(user_id)
        enriched = await self._enrich_holdings(symbol_holdings)

        divs = self.portfolio_repo.get_dividends_for_symbol(user_id, symbol)
        divs_by_account: dict[int, float] = {}
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
        self, user_id: int, symbol: str, period: str, benchmark_symbols: list[str],
    ) -> dict[str, Any]:
        """Compare single-stock performance against benchmarks using the
        symbol's own buy/sell cash flows (not portfolio-level deposits).

        The benchmark is seeded and simulated from the holding's INCEPTION, not
        from the window: the period selector may only clip the visible slice of
        one series, never re-invest a window-filtered cash-flow set
        (timeline-invariance requirement).
        """
        perf = await self.get_holding_performance(user_id, symbol, period)
        if not perf.get("success") or not perf.get("snapshots"):
            return {
                "success": True, "period": period,
                "portfolio": [], "benchmarks": [],
            }

        snapshots = perf["snapshots"]
        window_start, end_date = self._period_to_date_range(period)

        win_first_nz = next(
            (i for i, s in enumerate(snapshots) if s["position_value"] > 0), 0
        )
        snapshots_subset = snapshots[win_first_nz:]
        if not snapshots_subset:
            return {
                "success": True, "period": period,
                "portfolio": snapshots, "benchmarks": [],
            }

        # Seed from the holding's inception (the ALL series), not the window's
        # first snapshot. A failed/empty ALL read falls back to the window
        # anchor: degraded, but the same shape the code had before.
        all_perf = await self.get_holding_performance(user_id, symbol, "ALL")
        all_snaps = (all_perf.get("snapshots") or []) if all_perf.get("success") else []
        anchor_nz = next(
            (i for i, s in enumerate(all_snaps) if s["position_value"] > 0), None
        )
        anchor = all_snaps[anchor_nz] if anchor_nz is not None else snapshots_subset[0]
        inception_raw = anchor["date"]
        inception_date = (
            date.fromisoformat(inception_raw)
            if isinstance(inception_raw, str) else inception_raw
        )
        initial_value = anchor["position_value"]

        window_dates = [s["date"] for s in snapshots_subset]
        grid = self._benchmark_grid(
            period, inception_date, window_start, end_date, window_dates,
        )

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

        holding_cashflows = [
            cf for cf in holding_cashflows
            if not (cf["date"] == inception_date and abs(cf["amount"] - initial_value) < 1e-6)
        ]

        accounts = self.portfolio_repo.get_user_accounts(user_id)
        account_key = ",".join(
            str(a) for a in sorted(acc["account_id"] for acc in accounts)
        )

        benchmark_series_list = []
        if benchmark_symbols:
            for sym in benchmark_symbols:
                company = await self.financial_repo.get_company_by_symbol(sym)
                if not company:
                    logger.info("Holding benchmark %s not found — skipping", sym)
                    continue
                series = await self._benchmark_series_with_reuse(
                    account_key=account_key,
                    symbol=sym,
                    benchmark_company_id=company["company_id"],
                    inception_date=inception_date,
                    end_date=end_date,
                    initial_value=initial_value,
                    cashflows=holding_cashflows,
                    window_dates=grid,
                )
                if series:
                    window_start_iso = window_start.isoformat()
                    window_end_iso = end_date.isoformat()
                    clipped = [
                        p for p in series
                        if window_start_iso <= p["date"] <= window_end_iso
                    ]
                    benchmark_series_list.append({
                        "symbol": sym,
                        "name": sym,
                        "data": clipped,
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

    def _nearest_price(self, price_map: dict[str, float], target: str) -> float | None:
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
        cashflow_deltas: list[dict],
        snapshot_dates: list[str],
        price_rows: list[dict] | None = None,
    ) -> list[dict] | None:
        """
        Simulate what a benchmark (e.g. SPY) would be worth if the same
        deposits/withdrawals had been invested in it instead of the portfolio.

        ``price_rows`` lets a caller that already fetched the rows (the
        materialised-series path shares them with the fingerprint) skip a
        second fetch; None preserves the fetch-inside behaviour.

        Returns list of {date, value} in dollar terms at each snapshot date,
        or None if no price data is available for the benchmark.
        """
        if price_rows is None:
            try:
                resp = (
                    supabase.table("price_history")
                    .select("price_date, adj_close, close_price")
                    .eq("company_id", benchmark_company_id)
                    .gte("price_date", (start_date - timedelta(days=7)).isoformat())
                    .lte("price_date", end_date.isoformat())
                    .order("price_date", desc=False)
                    .execute()
                )
            except Exception as e:
                logger.warning("Failed to fetch benchmark price data for company_id=%s: %s", benchmark_company_id, e)
                return None
            rows = resp.data or []
        else:
            rows = price_rows

        if not rows:
            logger.info("No price history for benchmark company_id=%s", benchmark_company_id)
            return None

        price_map: dict[str, float] = {}
        for row in rows:
            pd_val = row["price_date"]
            if isinstance(pd_val, str):
                pd_str = pd_val
            elif isinstance(pd_val, date):
                pd_str = pd_val.isoformat()
            else:
                continue
            adj = row.get("adj_close")
            px = float(adj if adj is not None else row["close_price"])
            price_map[pd_str] = px

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

        # If start price is missing or invalid, cannot simulate
        if not start_price or start_price <= 0:
            return None

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

        series: list[dict] = []
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

    def _fetch_benchmark_price_rows(
        self, benchmark_company_id: int, inception_date: date, end_date: date,
    ) -> list[dict]:
        """Price rows the benchmark series is simulated and fingerprinted from.

        Fetched once per request and shared by both halves: the guard
        fingerprints exactly what the simulator replays, so a price correction,
        backfill or split restatement between two requests changes the
        fingerprint before a stored dollar can be served. Returns [] on any
        failure - the simulator then has no prices and the compare path skips
        the benchmark, exactly as before materialisation existed.
        """
        try:
            res = (
                supabase.table("price_history")
                .select("price_date, adj_close, close_price")
                .eq("company_id", benchmark_company_id)
                .gte("price_date", (inception_date - timedelta(days=7)).isoformat())
                .lte("price_date", end_date.isoformat())
                .order("price_date", desc=False)
                .execute()
            )
            return list(res.data or [])
        except Exception as e:
            logger.warning(
                "Failed to fetch benchmark price rows for company_id=%s: %s",
                benchmark_company_id, e,
            )
            return []

    def _benchmark_grid(
        self, period: str, inception: date, window_start: date, end: date,
        window_dates: list[str],
    ) -> list[str]:
        """Simulation grid: window dates at native resolution + monthly carry.

        A benchmark simulated only over the window's dates would seed from the
        window's start and produce a different final value per period. The grid
        therefore carries the pre-window history at a MONTHLY step: early cash
        flows are invested at real benchmark prices, and a 1W window over eight
        years is ~115 points, not ~3,200. The window's own dates are always
        included verbatim, at their native resolution.

        shortcut: carry step is monthly regardless of period. Upgrade when a
        zoomed period is observed to mis-shape around a large pre-window cash
        flow - then carry at the window's resolution below, say, one year.
        """
        if inception >= window_start:
            return list(window_dates)
        carry: list[str] = []
        d = inception
        while d < window_start:
            carry.append(d.isoformat())
            d += timedelta(days=30)
        return sorted(set(carry) | set(window_dates))

    async def _benchmark_series_with_reuse(
        self,
        *,
        account_key: str,
        symbol: str,
        benchmark_company_id: int,
        inception_date: date,
        end_date: date,
        initial_value: float,
        cashflows: list[dict],
        window_dates: list[str],
    ) -> list[dict]:
        """Serve the benchmark series from the materialised store (migration 015).

        Guard gates: coverage first, then the input fingerprint (cash flows +
        price signature of the same rows the simulator replays). A reused
        series must return EXACTLY the dollars a live simulation would - so
        only the requested dates the store lacks are computed, and a
        fingerprint mismatch rebuilds the whole grid (rebuild replaces, never
        merges). Store failures degrade to live simulation; a failed read
        never serves stored rows whose freshness was not verified.
        """
        price_rows = self._fetch_benchmark_price_rows(
            benchmark_company_id=benchmark_company_id,
            inception_date=inception_date,
            end_date=end_date,
        )
        expected_fp = compute_series_fingerprint(
            account_key=account_key, symbol=symbol,
            inception_date=inception_date, initial_value=initial_value,
            cashflows=cashflows, price_signature=price_signature(price_rows),
        )

        stored_map: dict[str, float] = {}
        stored_fp = stored_inception = stored_mark = None
        try:
            stored = BenchmarkSeriesRepository().get_series(account_key, symbol)
            if stored.points:
                stored_fp = stored.fingerprint
                stored_inception = stored.inception_date
                stored_mark = stored.last_mark_date
                stored_map = {p["date"]: p["value"] for p in stored.points}
        except Exception as e:
            logger.info("benchmark_series read failed (%s) - simulating live", e)

        decision = BenchmarkSeriesGuard().decide(
            stored_fingerprint=stored_fp,
            stored_inception=stored_inception,
            stored_last_mark=stored_mark,
            expected_fingerprint=expected_fp,
            required_inception=inception_date,
            required_end=end_date,
        )
        if decision.can_reuse and stored_map:
            to_compute = [d for d in window_dates if d not in stored_map]
        else:
            # Rebuild replaces: a stored date from an invalid build must
            # never be served alongside the new one.
            stored_map = {}
            to_compute = list(window_dates)

        computed_map: dict[str, float] = {}
        if to_compute:
            computed = self._simulate_benchmark_value(
                benchmark_company_id=benchmark_company_id,
                start_date=inception_date,
                end_date=end_date,
                initial_value=initial_value,
                cashflow_deltas=cashflows,
                snapshot_dates=to_compute,
                price_rows=price_rows,
            )
            if computed:
                computed_map = {p["date"]: p["value"] for p in computed}
                # Never persist a build computed without prices: its
                # fingerprint (over an empty price signature) could not be
                # re-verified, and a stored row nobody can validate is worse
                # than an empty store.
                if price_rows:
                    try:
                        BenchmarkSeriesRepository().upsert_points(
                            account_key,
                            symbol,
                            points=[
                                {"date": d, "value": computed_map[d]}
                                for d in to_compute if d in computed_map
                            ],
                            inception_date=inception_date,
                            initial_value=initial_value,
                            fingerprint=expected_fp,
                            last_mark_date=end_date,
                        )
                    except Exception as e:
                        logger.info(
                            "benchmark_series write failed (%s) - serving computed series",
                            e,
                        )

        if not stored_map and not computed_map:
            return []
        return [
            {"date": d, "value": stored_map.get(d, computed_map.get(d, 0.0))}
            for d in window_dates
        ]

    # ------------------------------------------------------------------
    # Benchmark list & comparison
    # ------------------------------------------------------------------

    async def get_portfolio_allocation(
        self, user_id: int, group_by: str = "sector",
        account_ids: list[int] | None = None,
    ) -> dict[str, Any]:
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

        accounts = self.portfolio_repo.get_user_accounts(user_id)
        all_holdings = self.portfolio_repo.get_user_all_holdings(user_id)
        holdings = await self._enrich_holdings(all_holdings)
        holdings = [h for h in holdings if h.get("account_id") in account_ids]

        if not holdings:
            return {
                "success": True,
                "group_by": group_by,
                "segments": [],
                "total_value": 0,
            }

        security_type_labels = {
            "stock": "Stocks",
            "etf": "ETFs",
            "fund": "Funds",
            "index": "Indices",
            "crypto": "Cryptocurrencies",
            "currency": "Currencies",
        }

        if group_by == "sector":
            return self._group_allocation_by_type(holdings, security_type_labels)
        else:
            return self._group_allocation_flat(holdings, group_by)

    def _group_allocation_by_type(
        self, holdings: list[dict[str, Any]],
        type_labels: dict[str, str],
    ) -> dict[str, Any]:
        """Two-level grouping: security_type → sector."""
        types: dict[str, dict[str, Any]] = {}

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
        self, holdings: list[dict[str, Any]], group_by: str,
    ) -> dict[str, Any]:
        """Flat grouping for geography or account views."""
        segments: dict[str, dict[str, Any]] = {}

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

    async def get_benchmarks(self) -> list[dict[str, Any]]:
        """List all active benchmarks from benchmark_config — delegates to shared repository logic."""
        from infrastructure.repositories.analysis_repository import AnalysisRepository
        from infrastructure.repositories.valuation_repository import ValuationRepository
        repo = AnalysisRepository(ValuationRepository())
        return await repo.list_active_benchmarks()

    async def get_performance_compare(
        self, user_id: int, period: str, benchmark_symbols: list[str],
        account_ids: list[int] | None = None,
    ) -> dict[str, Any]:
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

        # The benchmark is seeded from the ALL series (the account set's
        # inception), never from the window: the period selector may only
        # clip one series, not re-invest a window-filtered cash-flow set.
        all_perf = await self.get_portfolio_performance(user_id, "ALL", account_ids)
        all_snaps = (all_perf.get("snapshots") or []) if all_perf.get("success") else []
        anchor_nz = next((i for i, s in enumerate(all_snaps) if s["value"] > 0), None)
        anchor = all_snaps[anchor_nz] if anchor_nz is not None else snapshots_subset[0]
        inception_raw = anchor["date"]
        inception_date = (
            date.fromisoformat(inception_raw)
            if isinstance(inception_raw, str) else inception_raw
        )
        initial_value = anchor["value"]

        window_dates = [s["date"] for s in snapshots_subset]
        grid = self._benchmark_grid(
            period, inception_date, start_date, end_date, window_dates,
        )
        cashflow_deltas = self._get_cashflow_deltas(account_ids)

        # Prevent double-counting: a cash flow on the inception date that
        # equals initial_value (within tolerance) is already reflected in the
        # initial portfolio value.
        cashflow_deltas = [
            cf for cf in cashflow_deltas
            if not (cf["date"] == inception_date and abs(cf["amount"] - initial_value) < 1e-6)
        ]

        account_key = ",".join(str(a) for a in sorted(account_ids))

        benchmark_series_list = []
        if benchmark_symbols:
            for sym in benchmark_symbols:
                company = await self.financial_repo.get_company_by_symbol(sym)
                if not company:
                    logger.info("Benchmark symbol %s not found in companies table — skipping", sym)
                    continue

                series = await self._benchmark_series_with_reuse(
                    account_key=account_key,
                    symbol=sym,
                    benchmark_company_id=company["company_id"],
                    inception_date=inception_date,
                    end_date=end_date,
                    initial_value=initial_value,
                    cashflows=cashflow_deltas,
                    window_dates=grid,
                )
                if series:
                    window_start_iso = start_date.isoformat()
                    window_end_iso = end_date.isoformat()
                    clipped = [
                        p for p in series
                        if window_start_iso <= p["date"] <= window_end_iso
                    ]
                    benchmark_series_list.append({
                        "symbol": sym,
                        "name": sym,
                        "data": clipped,
                    })

        return {
            "success": True,
            "period": period,
            "portfolio": snapshots,
            "benchmarks": benchmark_series_list,
        }
