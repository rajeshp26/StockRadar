# backend/api/portfolio.py
"""
Portfolio API Routes

Endpoints for portfolio management:
- Import transactions from CSV
- View holdings and performance
- Manage accounts
- Query dividends
"""

import base64
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from dependencies import get_current_user_dep, limiter
from application.services.portfolio_service import PortfolioService
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.supabase_repository import SupabaseUserRepository
from schemas_portfolio import (
    ImportTransactionsRequest,
    ImportTransactionsResponse,
    ImportStatusResponse,
    ListBrokeragesResponse,
    ListAccountsResponse,
    AccountHoldingsResponse,
    PortfolioOverviewResponse,
    AccountTransactionsResponse,
    AccountDividendsResponse,
    DeleteAccountRequest,
    ManualTransactionRequest,
    ManualTransactionResponse,
    PerformanceResponse,
    BenchmarkListResponse,
    BenchmarkCompareResponse,
    PortfolioAllocationResponse,
    DividendHistoryResponse,
    HoldingExistsResponse,
    HoldingPerformanceResponse,
    HoldingTransactionInfo,
    HoldingAccountBreakdown,
    RiskMetricsResponse,
    DrawdownResponse,
    CovarianceResponse,
    EfficientFrontierResponse,
    RollingSharpeResponse,
    RiskContributionResponse,
    FactorExposureResponse,
)
from shared.exceptions.base import AppException
from database import supabase

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _resolve_db_user_id(auth_id: str) -> int:
    """Resolve Firebase auth_id → internal user_id. Raises 403 if not found."""
    user_repo = SupabaseUserRepository(client=supabase)
    user = user_repo.find_by_firebase_uid(auth_id)
    if not user:
        raise HTTPException(status_code=403, detail="User not found.")
    return user["user_id"]


def _get_portfolio_service() -> PortfolioService:
    """Factory for PortfolioService with all dependencies."""
    return PortfolioService()


_portfolio_risk_service_instance: Optional["PortfolioRiskService"] = None


def _get_portfolio_risk_service() -> "PortfolioRiskService":
    """Cached singleton factory for PortfolioRiskService."""
    global _portfolio_risk_service_instance
    if _portfolio_risk_service_instance is None:
        from application.services.portfolio_risk_service import PortfolioRiskService
        _portfolio_risk_service_instance = PortfolioRiskService()
    return _portfolio_risk_service_instance


def _resolve_user(user: dict) -> int:
    """Resolve auth user dict → internal db_user_id. Caches in-memory."""
    auth_id = user["sub"]
    cache_key = f"user_id:{auth_id}"
    cached = getattr(_resolve_user, "_cache", {}).get(cache_key)
    if cached is not None:
        return cached
    db_user_id = _resolve_db_user_id(auth_id)
    if not hasattr(_resolve_user, "_cache"):
        _resolve_user._cache = {}
    _resolve_user._cache[cache_key] = db_user_id
    return db_user_id


def _parse_account_ids(raw: Optional[str]) -> Optional[List[int]]:
    """Parse comma-separated account_ids query param."""
    if not raw:
        return None
    return [int(x) for x in raw.split(",") if x.strip()]


# ============================================================================
# BROKERAGES
# ============================================================================

@router.get("/portfolio/brokerages", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def list_brokerages(
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> ListBrokeragesResponse:
    """
    List supported brokerages.
    
    Returns all active brokerages that users can import transactions from.
    """
    try:
        repo = PortfolioRepository()
        brokerages = repo.list_active_brokerages()
        
        return ListBrokeragesResponse(brokerages=brokerages)
    
    except Exception as e:
        logger.error(f"List brokerages failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list brokerages",
        )


# ============================================================================
# ACCOUNTS
# ============================================================================

@router.get("/portfolio/accounts", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def list_accounts(
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> ListAccountsResponse:
    """
    List all portfolio accounts for the authenticated user.
    
    Returns account metadata with holdings count and total value per account.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        service = _get_portfolio_service()
        accounts = repo.get_user_accounts(db_user_id, active_only=True)
        
        # Enrich with holdings count and value
        enriched_accounts = []
        for acc in accounts:
            holdings = await service.enrich_holdings_with_prices(
                repo.get_account_holdings(acc["account_id"])
            )
            total_value = sum(h.get("current_value") or 0 for h in holdings)
            total_cost = sum(h.get("total_cost") or 0 for h in holdings)
            
            brokerage_info = acc.get("portfolio_brokerages", {})
            
            enriched_accounts.append({
                "account_id": acc["account_id"],
                "account_name": acc["account_name"],
                "account_type": acc["account_type"],
                "account_external_id": acc["account_external_id"],
                "brokerage_name": brokerage_info.get("brokerage_name", "Unknown"),
                "brokerage_code": brokerage_info.get("brokerage_code", "unknown"),
                "currency": acc["currency"],
                "is_active": acc["is_active"],
                "created_at": acc["created_at"],
                "last_import_at": acc.get("last_import_at"),
                "holdings_count": len(holdings),
                "total_value": float(total_value),
                "total_cost": float(total_cost),
            })
        
        return ListAccountsResponse(accounts=enriched_accounts)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List accounts failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list accounts",
        )


@router.delete("/portfolio/accounts/{account_id}", tags=["Portfolio"], status_code=204)
@limiter.limit("10/minute")
async def delete_account(
    request: Request,
    account_id: int,
    user: dict = Depends(get_current_user_dep),
):
    """
    Delete a portfolio account and all associated data.
    
    Cascade deletes:
    - All transactions for this account
    - All holdings for this account
    - All performance snapshots for this account
    - All dividend records for this account
    
    Security: Ownership verified via account.user_id.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        account = repo.get_account_by_id(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Verify ownership
        if account["user_id"] != db_user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not own this account",
            )
        
        # Delete account (cascades to transactions, holdings, etc.)
        supabase.table("portfolio_accounts").delete().eq(
            "account_id", account_id
        ).execute()
        
        logger.info(f"Deleted account {account_id} for user {db_user_id}")
        return None
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete account failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account",
        )


# ============================================================================
# IMPORT TRANSACTIONS
# ============================================================================

@router.post("/portfolio/import", tags=["Portfolio"], status_code=200)
@limiter.limit("5/minute")
async def queue_import(
    request: Request,
    body: ImportTransactionsRequest,
    user: dict = Depends(get_current_user_dep),
) -> ImportTransactionsResponse:
    """
    Queue a CSV import for background processing.
    
    Returns immediately with import_batch_id and status='pending'.
    Frontend polls GET /portfolio/import/{import_batch_id}/status for progress.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        # Decode CSV content
        try:
            csv_bytes = base64.b64decode(body.csv_content)
            csv_content = csv_bytes.decode("utf-8")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid CSV encoding: {str(e)}",
            )
        
        # Queue import for background processing
        service = _get_portfolio_service()
        result = await service.queue_import(
            user_id=db_user_id,
            brokerage_code=body.brokerage_code,
            csv_content=csv_content,
            account_filter=body.account_filter,
        )
        
        if not result.get("success"):
            return ImportTransactionsResponse(
                success=False,
                error=result.get("error", "Import failed"),
                warnings=result.get("warnings", []),
                duplicate_import=result.get("duplicate_import", False),
                previous_import_date=result.get("previous_import_date"),
                previous_import_id=result.get("previous_import_id"),
                warning=result.get("warning"),
            )
        
        return ImportTransactionsResponse(**result)
    
    except HTTPException:
        raise
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Queue import failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Queue import failed: {str(e)}",
        )


@router.get("/portfolio/import/{import_batch_id}/status", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_import_status(
    request: Request,
    import_batch_id: str,
    user: dict = Depends(get_current_user_dep),
) -> ImportStatusResponse:
    """
    Poll import job status and progress.
    
    Status values:
    - pending:   Queued, waiting to start
    - processing: Actively importing
    - completed: Done, result available in 'result' field
    - failed:    Error, details in 'error' field
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        job = repo.get_import_job(uuid.UUID(import_batch_id))
        
        if not job:
            raise HTTPException(
                status_code=404,
                detail="Import job not found",
            )
        
        # Verify ownership
        if job.get("user_id") != db_user_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )
        
        status = job.get("status", "unknown")
        total_rows = job.get("total_rows", 0)
        rows_parsed = job.get("rows_parsed", 0)
        rows_inserted = job.get("imported_rows", 0)
        
        response = ImportStatusResponse(
            success=status in ("completed", "processing", "pending"),
            import_batch_id=import_batch_id,
            status=status,
            total_rows=total_rows,
            rows_parsed=rows_parsed,
            rows_inserted=rows_inserted,
            error=job.get("error_message"),
        )
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get import status failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get import status",
        )


# ============================================================================
# HOLDINGS
# ============================================================================

@router.get("/portfolio/accounts/{account_id}/holdings", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_account_holdings(
    request: Request,
    account_id: int,
    user: dict = Depends(get_current_user_dep),
) -> AccountHoldingsResponse:
    """
    Get all holdings for a specific account.
    
    Returns current positions with:
    - Quantity, average cost, total cost
    - Current price and value (from current_market_data)
    - Unrealized gain/loss
    - Realized gain/loss (from closed positions)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        account = repo.get_account_by_id(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Verify ownership
        if account["user_id"] != db_user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not own this account",
            )
        
        # Get holdings enriched with computed prices
        service = _get_portfolio_service()
        holdings = await service.enrich_holdings_with_prices(
            repo.get_account_holdings(account_id)
        )
        
        return AccountHoldingsResponse(
            account_id=account_id,
            account_name=account["account_name"],
            holdings=holdings,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get holdings failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get holdings",
        )


@router.get("/portfolio/holdings", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_all_holdings(
    request: Request,
    user: dict = Depends(get_current_user_dep),
    aggregated: bool = Query(False, description="Group by symbol, aggregate quantities across accounts"),
):
    """
    Get all holdings across all user accounts.

    When ``aggregated=true``, holdings with the same symbol across multiple
    accounts are combined into a single row with weighted average cost,
    total quantity, and a per-account breakdown.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        repo = PortfolioRepository()
        service = _get_portfolio_service()
        holdings = await service.enrich_holdings_with_prices(
            repo.get_user_all_holdings(db_user_id)
        )

        if aggregated:
            holdings = service.aggregate_holdings(holdings)

        return {"holdings": holdings}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get all holdings failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get holdings",
        )


# ============================================================================
# PORTFOLIO OVERVIEW
# ============================================================================

@router.get("/portfolio/overview", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_portfolio_overview(
    request: Request,
    account_id: Optional[int] = Query(None, description="Filter to a specific account"),
    user: dict = Depends(get_current_user_dep),
) -> PortfolioOverviewResponse:
    """
    Get comprehensive portfolio overview.

    Optional account_id filters to a single account for per-account overview.

    Returns:
    - Net worth (total current value)
    - Total cost basis
    - Total gain/loss ($ and %)
    - YTD dividends
    - Holdings count
    - Accounts count
    - Top holdings by value
    - Per-account breakdown
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        service = _get_portfolio_service()

        ids_param = [account_id] if account_id else None
        overview = await service.get_user_portfolio_overview(db_user_id, account_ids=ids_param)
        
        if not overview.get("success"):
            return PortfolioOverviewResponse(
                success=False,
                error=overview.get("error", "Failed to generate overview"),
                net_worth=0,
                total_cost_basis=0,
                total_gain_loss=0,
                total_gain_loss_pct=0,
                ytd_dividends=0,
                total_holdings_count=0,
                accounts_count=0,
                top_holdings=[],
                account_breakdown=[],
            )
        
        return PortfolioOverviewResponse(**overview)
    
    except HTTPException:
        raise
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Get portfolio overview failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get portfolio overview",
        )


# ============================================================================
# TRANSACTIONS
# ============================================================================

@router.get("/portfolio/accounts/{account_id}/transactions", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_account_transactions(
    request: Request,
    account_id: int,
    limit: int = 100,
    user: dict = Depends(get_current_user_dep),
) -> AccountTransactionsResponse:
    """
    Get transaction history for an account.
    
    Query params:
    - limit: Max transactions to return (default 100, max 1000)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        # Cap limit
        if limit > 1000:
            limit = 1000
        
        repo = PortfolioRepository()
        account = repo.get_account_by_id(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Verify ownership
        if account["user_id"] != db_user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not own this account",
            )
        
        transactions = repo.get_account_transactions(account_id, limit=limit)
        
        return AccountTransactionsResponse(
            account_id=account_id,
            transactions=transactions,
            total_count=len(transactions),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get transactions failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get transactions",
        )


@router.get("/portfolio/transactions", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_all_transactions(
    request: Request,
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    limit: int = 100,
    activity_type: Optional[str] = Query(None, description="Filter by activity type (BUY, SELL, DIVIDEND, etc.)"),
    search: Optional[str] = Query(None, description="Search symbol or security name"),
    from_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    user: dict = Depends(get_current_user_dep),
) -> AccountTransactionsResponse:
    """
    Get transaction history across all (or specified) accounts.

    Supports the same filters as the per-account endpoint:
    - limit: Max transactions to return (default 100, max 1000)
    - activity_type: Filter by BUY, SELL, DIVIDEND, etc.
    - search: Text search on symbol or security name
    - from_date / to_date: Date range filter

    When account_ids is omitted, returns transactions for all user accounts.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = [int(x) for x in account_ids.split(",") if x.strip()] if account_ids else None

        if limit > 1000:
            limit = 1000

        service = _get_portfolio_service()
        result = await service.get_user_all_transactions(
            db_user_id,
            account_ids=parsed_ids,
            limit=limit,
            activity_type=activity_type,
            search=search,
            from_date=from_date,
            to_date=to_date,
        )

        return AccountTransactionsResponse(
            account_id=None,
            transactions=result["transactions"],
            total_count=result["total_count"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get all transactions failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get transactions",
        )


# ============================================================================
# DIVIDENDS
# ============================================================================

@router.get("/portfolio/accounts/{account_id}/dividends", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_account_dividends(
    request: Request,
    account_id: int,
    user: dict = Depends(get_current_user_dep),
) -> AccountDividendsResponse:
    """
    Get dividend summary for an account.
    
    Returns:
    - Current year total dividends
    - Monthly breakdown for last 12 months
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        account = repo.get_account_by_id(account_id)
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        # Verify ownership
        if account["user_id"] != db_user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not own this account",
            )
        
        # Get current year total
        from datetime import datetime
        current_year = datetime.now().year
        yearly_divs = repo.get_account_dividends_by_year(account_id, current_year)
        current_year_total = sum(d.get("amount", 0) for d in yearly_divs)
        
        # Get monthly summaries
        monthly_summaries = repo.get_monthly_dividends(account_id, months=12)
        
        return AccountDividendsResponse(
            account_id=account_id,
            current_year_total=float(current_year_total),
            monthly_summaries=monthly_summaries,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get dividends failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get dividends",
        )


@router.get("/portfolio/dividends", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_all_dividends(
    request: Request,
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> AccountDividendsResponse:
    """
    Get aggregated dividends across all (or specified) accounts.

    When account_ids is omitted, returns dividends for all user accounts.
    When provided, scopes to those accounts only.

    Returns:
    - Current year total dividends
    - Monthly breakdown for last 12 months (aggregated)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = [int(x) for x in account_ids.split(",") if x.strip()] if account_ids else None

        service = _get_portfolio_service()
        result = await service.get_user_all_dividends(db_user_id, account_ids=parsed_ids)

        if not result.get("success"):
            return AccountDividendsResponse(
                success=False,
                current_year_total=0,
                monthly_summaries=[],
                error=result.get("error", "Failed to aggregate dividends"),
            )

        return AccountDividendsResponse(
            account_id=None,
            current_year_total=result["current_year_total"],
            monthly_summaries=result["monthly_summaries"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get all dividends failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get dividends",
        )


@router.get("/portfolio/accounts/{account_id}/dividend-history", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_account_dividend_history(
    request: Request,
    account_id: int,
    user: dict = Depends(get_current_user_dep),
) -> DividendHistoryResponse:
    """
    Get detailed dividend history for an account.

    Returns every dividend record with:
    - Symbol, company name
    - Payment date, amount
    - Shares held and amount per share (if available)
    - Account name and type
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        service = _get_portfolio_service()
        result = await service.get_dividend_history_detail(db_user_id, account_id)

        if not result.get("success"):
            return DividendHistoryResponse(
                success=False,
                dividends=[],
                total_count=0,
                current_year_total=0,
                error=result.get("error", "Failed to get dividend history"),
            )

        return DividendHistoryResponse(
            success=True,
            account_id=account_id,
            dividends=result["dividends"],
            total_count=result["total_count"],
            current_year_total=result["current_year_total"],
        )

    except HTTPException:
        raise
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Get dividend history failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get dividend history",
        )


@router.post("/portfolio/transactions/manual", tags=["Portfolio"], status_code=201)
@limiter.limit("30/minute")  # Allow 30 manual entries per minute
async def add_manual_transaction(
    request: Request,
    body: ManualTransactionRequest,
    user: dict = Depends(get_current_user_dep),
) -> ManualTransactionResponse:
    """
    Manually add a single transaction.
    
    Use cases:
    - User wants to backfill historical trades not in CSV
    - User wants to enter trades without uploading CSV
    - User wants to record transactions from multiple sources
    
    Validates:
    - Account ownership
    - Required fields based on activity type
    - Stock symbol exists (creates if needed)
    
    Auto-triggers:
    - Holdings recalculation for affected account
    - Dividend extraction if type is DIVIDEND
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        service = _get_portfolio_service()
        result = await service.add_manual_transaction(
            user_id=db_user_id,
            account_id=body.account_id,
            transaction_date=body.transaction_date,
            activity_type=body.activity_type,
            symbol=body.symbol,
            quantity=body.quantity,
            unit_price=body.unit_price,
            commission=body.commission,
            notes=body.notes,
        )
        
        if not result.get("success"):
            return ManualTransactionResponse(
                success=False,
                error=result.get("error", "Failed to create transaction"),
            )
        
        return ManualTransactionResponse(**result)
    
    except HTTPException:
        raise
    except AppException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"Manual transaction failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create transaction: {str(e)}",
        )
 
 
@router.get("/portfolio/import-history", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_import_history(
    request: Request,
    limit: int = 20,
    user: dict = Depends(get_current_user_dep),
):
    """
    Get CSV import history for the user.
    
    Shows:
    - When CSVs were imported
    - How many transactions per import
    - Which brokerages
    - Duplicate detection results
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        history = repo.get_import_history(db_user_id, limit=min(limit, 100))
        
        return {"import_history": history}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get import history failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to get import history",
        )
 
@router.get("/companies/search", tags=["Companies"], status_code=200)
@limiter.limit("60/minute")
async def check_company_exists(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
):
    """
    Check if a company exists in the database.
    
    Used by manual trade form for real-time validation:
    - Shows "Company exists: Tesla Inc" (green)
    - Shows "New company will be created" (amber)
    
    This helps users understand what will happen when they submit.
    """
    try:
        # Simple lookup
        res = (
            supabase.table("companies")
            .select("company_id, ticker_symbol, company_name")
            .eq("ticker_symbol", symbol.upper())
            .limit(1)
            .execute()
        )
        
        if res.data and len(res.data) > 0:
            company = res.data[0]
            return {
                "exists": True,
                "company_id": company["company_id"],
                "ticker_symbol": company["ticker_symbol"],
                "company_name": company["company_name"],
            }
        else:
            return {
                "exists": False,
                "ticker_symbol": symbol.upper(),
            }
    
    except Exception as e:
        logger.error(f"Company check failed for {symbol}: {e}")
        # Return false on error so form still works
        return {
            "exists": False,
            "ticker_symbol": symbol.upper(),
        }


# ============================================================================
# DIVIDEND DASHBOARD ENDPOINTS
# ============================================================================

from application.services.dividend_dashboard_service import DividendDashboardService
from schemas_portfolio import (
    PortfolioDividendSummary,
    PortfolioDividendHolding,
    PortfolioDividendHoldingDetail,
    UpcomingExDate,
)


def _get_dividend_dashboard_service() -> DividendDashboardService:
    """Factory for DividendDashboardService."""
    return DividendDashboardService()


@router.get("/portfolio/dividends/summary", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_dividend_dashboard_summary(
    request: Request,
    account_ids: str = Query(..., description="Comma-separated account IDs"),
    user: dict = Depends(get_current_user_dep),
) -> PortfolioDividendSummary:
    """
    Portfolio dividend summary.

    Returns high-level metrics:
    - Trailing 12M income (actual)
    - Forward annual estimate
    - YTD dividends
    - Forward yield on cost
    - Average monthly (trailing and forward)
    - Portfolio growth 5Y (with coverage_pct)
    - Portfolio safety score (with coverage_pct)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = _parse_account_ids(account_ids)
        service = _get_dividend_dashboard_service()
        result = service.get_summary(parsed_ids)

        return PortfolioDividendSummary(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dividend dashboard summary failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dividend summary")


@router.get("/portfolio/dividends/upcoming", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_dividend_dashboard_upcoming(
    request: Request,
    account_ids: str = Query(..., description="Comma-separated account IDs"),
    user: dict = Depends(get_current_user_dep),
) -> List[UpcomingExDate]:
    """
    Upcoming ex-dividend dates for held positions.

    Returns:
    - Symbol, company name
    - Ex-dividend date
    - Amount per share
    - Estimated income (shares × DPS)
    - Confidence: high (announced) or low (inferred from pattern)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = _parse_account_ids(account_ids)
        service = _get_dividend_dashboard_service()
        result = service.get_upcoming(parsed_ids)

        return [UpcomingExDate(**r) for r in result]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dividend dashboard upcoming failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get upcoming ex-dates")


@router.get("/portfolio/dividends/holdings", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_dividend_dashboard_holdings(
    request: Request,
    account_ids: str = Query(..., description="Comma-separated account IDs"),
    user: dict = Depends(get_current_user_dep),
) -> List[PortfolioDividendHolding]:
    """
    Per-holding dividend data for the holdings table.

    Each row contains:
    - Symbol, company name, sector
    - Quantity, market value, total cost
    - Forward income and trailing 12M income
    - Current yield, yield on cost
    - Payout ratio, increase streak, safety score
    - Next event (upcoming ex-date, nullable)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = _parse_account_ids(account_ids)
        service = _get_dividend_dashboard_service()
        result = service.get_holdings(parsed_ids)

        return [PortfolioDividendHolding(**r) for r in result]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dividend dashboard holdings failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dividend holdings")


@router.get("/portfolio/dividends/holdings/{symbol}", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_dividend_dashboard_holding_detail(
    request: Request,
    symbol: str,
    account_ids: str = Query(..., description="Comma-separated account IDs"),
    user: dict = Depends(get_current_user_dep),
) -> PortfolioDividendHoldingDetail:
    """
    Detailed dividend data for a single holding (lazy-loaded on drawer open).

    Returns:
    - Income summary (trailing 12M, forward, YTD, YoC)
    - Quality metrics (safety, payout ratio, growth 5Y, streak)
    - Dividend history (from company dividend_history)
    - Recent payments (from user's portfolio_dividends)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = _parse_account_ids(account_ids)
        service = _get_dividend_dashboard_service()
        result = service.get_holding_detail(parsed_ids, symbol)

        return PortfolioDividendHoldingDetail(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dividend dashboard detail failed for {symbol}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get holding dividend detail")


# ============================================================================
# HOLDING-LEVEL ENDPOINTS (single-stock performance)
# ============================================================================

@router.get("/portfolio/holdings/{symbol}/exists", tags=["Portfolio"], status_code=200)
@limiter.limit("60/minute")
async def check_holding_exists(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> HoldingExistsResponse:
    """Check if the current user holds a position in this symbol."""
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        service = _get_portfolio_service()
        held = service.check_holding_exists(db_user_id, symbol)
        return HoldingExistsResponse(symbol=symbol.upper(), held=held)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Check holding exists failed for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to check holding exists")


@router.get("/portfolio/holdings/{symbol}/performance", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_holding_performance(
    request: Request,
    symbol: str,
    period: str = Query("1Y", pattern="^(1D|1W|1M|3M|1Y|5Y|YTD|ALL)$"),
    user: dict = Depends(get_current_user_dep),
) -> HoldingPerformanceResponse:
    """Time-series performance for a single stock in user's portfolio."""
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        service = _get_portfolio_service()
        result = await service.get_holding_performance(db_user_id, symbol, period)

        if not result.get("success"):
            return HoldingPerformanceResponse(
                success=False,
                symbol=symbol.upper(),
                period=period,
                snapshots=[],
                total_return=0,
                total_return_pct=0,
                total_dividends=0,
                total_dividends_pct=0,
                error=result.get("error"),
            )

        return HoldingPerformanceResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get holding performance failed for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get holding performance")


@router.get("/portfolio/holdings/{symbol}/dividends", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_holding_dividends(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> list[dict]:
    """Quarterly-aggregated dividend history for a single held stock."""
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        service = _get_portfolio_service()
        result = await service.get_holding_dividends(db_user_id, symbol)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get holding dividends failed for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get holding dividends")


@router.get("/portfolio/holdings/{symbol}/transactions", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_holding_transactions(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> list[HoldingTransactionInfo]:
    """Return all BUY/SELL transactions for a symbol across user accounts. (P-04)"""
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        service = _get_portfolio_service()
        result = await service.get_holding_transactions(db_user_id, symbol)
        return [HoldingTransactionInfo(**r) for r in result]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get holding transactions failed for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get holding transactions")


@router.get("/portfolio/holdings/{symbol}/accounts", tags=["Portfolio"], status_code=200)
@limiter.limit("30/minute")
async def get_holding_accounts(
    request: Request,
    symbol: str,
    user: dict = Depends(get_current_user_dep),
) -> list[HoldingAccountBreakdown]:
    """Return per-account breakdown of a single holding. (P-05)"""
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        service = _get_portfolio_service()
        result = await service.get_holding_accounts(db_user_id, symbol)
        return [HoldingAccountBreakdown(**r) for r in result]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get holding accounts failed for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get holding accounts")


@router.get("/portfolio/holdings/{symbol}/performance/compare", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_holding_performance_compare(
    request: Request,
    symbol: str,
    period: str = Query("1Y", pattern="^(1D|1W|1M|3M|1Y|5Y|YTD|ALL)$"),
    benchmarks: str = "SPY",
    user: dict = Depends(get_current_user_dep),
) -> BenchmarkCompareResponse:
    """Compare single-stock performance vs benchmarks using holding-level cash flows. (P-03)"""
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        benchmark_symbols = [s.strip().upper() for s in benchmarks.split(",") if s.strip()]
        service = _get_portfolio_service()
        result = await service.get_holding_performance_compare(
            db_user_id, symbol, period, benchmark_symbols
        )
        return BenchmarkCompareResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get holding performance compare failed for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compare holding performance")


# ============================================================================
# PORTFOLIO PERFORMANCE
# ============================================================================

@router.get("/portfolio/performance", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_portfolio_performance(
    request: Request,
    period: str = "1Y",
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> PerformanceResponse:
    """
    Get portfolio value over time.

    Period options: 1D, 1W, 1M, 3M, 1Y, 5Y, ALL
    Optional account_ids filter: ?account_ids=1,3,5 (empty = all accounts)
    Returns time-series snapshots of portfolio value and cost basis.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = [int(x) for x in account_ids.split(",") if x.strip()] if account_ids else None

        service = _get_portfolio_service()
        result = await service.get_portfolio_performance(db_user_id, period, parsed_ids)

        if not result.get("success"):
            return PerformanceResponse(
                success=False,
                period=period,
                snapshots=[],
                total_return=0,
                total_return_pct=0,
                error=result.get("error"),
            )

        return PerformanceResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get portfolio performance failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get portfolio performance",
        )


@router.get("/portfolio/performance/compare", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_performance_compare(
    request: Request,
    period: str = "1Y",
    benchmarks: str = "SPY",
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> BenchmarkCompareResponse:
    """
    Compare portfolio performance against benchmark indices.

    All series normalized to 100 at period start for side-by-side comparison.
    Multiple benchmarks: ?benchmarks=SPY,QQQ
    Optional account_ids filter: ?account_ids=1,3,5 (empty = all accounts)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        benchmark_symbols = [s.strip().upper() for s in benchmarks.split(",") if s.strip()]
        parsed_ids = [int(x) for x in account_ids.split(",") if x.strip()] if account_ids else None

        service = _get_portfolio_service()
        result = await service.get_performance_compare(db_user_id, period, benchmark_symbols, parsed_ids)

        return BenchmarkCompareResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get performance compare failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to compare performance",
        )


@router.get("/portfolio/allocation", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_portfolio_allocation(
    request: Request,
    group_by: str = Query("sector", description="Group by: sector, geography, or account"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs"),
    user: dict = Depends(get_current_user_dep),
) -> PortfolioAllocationResponse:
    """
    Get portfolio allocation breakdown.

    Group by options:
    - sector: By GICS sector (default)
    - geography: By market group (US, CA, INTL)
    - account: By account name

    Optional account_ids filter: ?account_ids=1,3,5 (empty = all accounts)
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        parsed_ids = [int(x) for x in account_ids.split(",") if x.strip()] if account_ids else None

        service = _get_portfolio_service()
        result = await service.get_portfolio_allocation(
            db_user_id, group_by=group_by, account_ids=parsed_ids
        )

        return PortfolioAllocationResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get allocation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to get allocation",
        )


@router.get("/benchmarks", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def list_benchmarks(
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> BenchmarkListResponse:
    """
    List available benchmark indices for performance comparison.

    Returns all active benchmarks from benchmark_config table.
    Used by the benchmark selector in the portfolio UI.
    """
    try:
        service = _get_portfolio_service()
        benchmarks = await service.get_benchmarks()

        return BenchmarkListResponse(
            success=True,
            benchmarks=benchmarks,
        )

    except Exception as e:
        logger.error(f"List benchmarks failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to list benchmarks",
        )


# ============================================================================
# RISK METRICS
# ============================================================================

@router.get("/portfolio/risk-metrics", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_risk_metrics(
    request: Request,
    period: str = Query("1Y", description="Period: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, MAX"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> RiskMetricsResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_risk_metrics(
            db_user_id, period=period, account_ids=_parse_account_ids(account_ids),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Risk metrics failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute risk metrics")


@router.get("/portfolio/drawdown", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_drawdown(
    request: Request,
    period: str = Query("1Y", description="Period: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y, MAX"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> DrawdownResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_drawdown(
            db_user_id, period=period, account_ids=_parse_account_ids(account_ids),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Drawdown failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute drawdown")


@router.get("/portfolio/covariance", tags=["Portfolio"], status_code=200)
@limiter.limit("10/minute")
async def get_covariance(
    request: Request,
    period: str = Query("1Y", description="Period: 1M, 3M, 6M, 1Y, 2Y, 3Y, 5Y"),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> CovarianceResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_covariance_matrix(
            db_user_id, period=period, account_ids=_parse_account_ids(account_ids),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Covariance failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute covariance")


@router.get("/portfolio/efficient-frontier", tags=["Portfolio"], status_code=200)
@limiter.limit("10/minute")
async def get_efficient_frontier(
    request: Request,
    points: int = Query(50, description="Number of frontier points", ge=10, le=200),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> EfficientFrontierResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_efficient_frontier(
            db_user_id, account_ids=_parse_account_ids(account_ids), points=points,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Efficient frontier failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute efficient frontier")


@router.get("/portfolio/rolling-sharpe", tags=["Portfolio"], status_code=200)
@limiter.limit("10/minute")
async def get_rolling_sharpe(
    request: Request,
    window: int = Query(252, description="Rolling window in trading days", ge=30, le=756),
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> RollingSharpeResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_rolling_sharpe(
            db_user_id, window=window, account_ids=_parse_account_ids(account_ids),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rolling sharpe failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute rolling sharpe")


@router.get("/portfolio/risk-contribution", tags=["Portfolio"], status_code=200)
@limiter.limit("10/minute")
async def get_risk_contribution(
    request: Request,
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> RiskContributionResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_risk_contribution(
            db_user_id, account_ids=_parse_account_ids(account_ids),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Risk contribution failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute risk contribution")


@router.get("/portfolio/market-exposure", tags=["Portfolio"], status_code=200)
@limiter.limit("10/minute")
async def get_market_exposure(
    request: Request,
    account_ids: Optional[str] = Query(None, description="Comma-separated account IDs; empty = all"),
    user: dict = Depends(get_current_user_dep),
) -> FactorExposureResponse:
    try:
        db_user_id = _resolve_user(user)
        service = _get_portfolio_risk_service()
        return await service.compute_market_exposure(
            db_user_id, account_ids=_parse_account_ids(account_ids),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Market exposure failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to compute market exposure")