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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
):
    """
    Get all holdings across all user accounts (aggregated view).
    
    Useful for portfolio-wide analysis and top holdings display.
    """
    try:
        auth_id = user["uid"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        repo = PortfolioRepository()
        service = _get_portfolio_service()
        holdings = await service.enrich_holdings_with_prices(
            repo.get_user_all_holdings(db_user_id)
        )
        
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
    user: dict = Depends(get_current_user_dep),
) -> PortfolioOverviewResponse:
    """
    Get comprehensive portfolio overview.
    
    Returns:
    - Net worth (total current value)
    - Total cost basis
    - Total gain/loss ($ and %)
    - YTD dividends
    - Holdings count
    - Accounts count
    - Top 10 holdings by value
    - Per-account breakdown
    """
    try:
        auth_id = user["uid"]
        db_user_id = _resolve_db_user_id(auth_id)
        
        service = _get_portfolio_service()
        overview = await service.get_user_portfolio_overview(db_user_id)
        
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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
        auth_id = user["uid"]
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