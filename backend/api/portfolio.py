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
from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from application.services.portfolio_risk_service import PortfolioRiskService

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from application.services.portfolio_service import PortfolioService
from config import settings
from database import supabase
from dependencies import get_current_user_dep, limiter
from infrastructure.repositories.portfolio_repository import PortfolioRepository
from infrastructure.repositories.supabase_repository import SupabaseUserRepository
from schemas_portfolio import (
    AccountDividendsResponse,
    AccountHoldingsResponse,
    AccountTransactionsResponse,
    BenchmarkCompareResponse,
    BenchmarkListResponse,
    CovarianceResponse,
    DashboardAccount,
    DashboardHolding,
    DashboardOverview,
    DividendHistoryResponse,
    DrawdownResponse,
    EfficientFrontierResponse,
    FactorExposureResponse,
    HoldingAccountBreakdown,
    HoldingExistsResponse,
    HoldingPerformanceResponse,
    HoldingTransactionInfo,
    ImportStatusResponse,
    ImportTransactionsRequest,
    ImportTransactionsResponse,
    ListAccountsResponse,
    ListBrokeragesResponse,
    ManualTransactionRequest,
    ManualTransactionResponse,
    PerformanceBatchResponse,
    PerformanceResponse,
    PortfolioAllocationResponse,
    PortfolioDashboardResponse,
    PortfolioOverviewResponse,
    RiskContributionResponse,
    RiskMetricsResponse,
    RollingSharpeResponse,
)
from shared.exceptions.base import AppException
from shared.fx_service import FXService
from shared.metrics import RouteTimer
from shared.snapshot_builder import convert_holding_fx
from shared.time_utils import now_utc

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


# ============================================================================
# FX CONVERSION HELPERS
# ============================================================================

def _get_company_currencies(company_ids: list[int]) -> dict[int, str]:
    """Look up price currency for each company from the companies table."""
    if not company_ids:
        return {}
    try:
        result = supabase.table("companies").select("company_id, currency") \
            .in_("company_id", company_ids).execute()
        return {row["company_id"]: row.get("currency", "USD") for row in (result.data or [])}
    except Exception:
        return {}


def _get_company_cdr_ratios(company_ids: list[int]) -> dict[int, float]:
    """Look up per-company CDR ratio from the companies table."""
    if not company_ids:
        return {}
    try:
        result = supabase.table("companies").select("company_id, cdr_ratio") \
            .in_("company_id", company_ids).execute()
        ratios = {}
        for row in (result.data or []):
            ratio = row.get("cdr_ratio")
            if ratio is not None:
                ratios[row["company_id"]] = float(ratio)
        return ratios
    except Exception:
        return {}


def apply_cdr_adjustment(
    price: float,
    company_id: int,
    cdr_ratios: dict[int, float],
    exchange_overrides: dict[int, str | None] | None = None,
) -> float:
    """Apply CDR ratio to a price if the company is a CDR holding.

    Used by API endpoints that fetch prices from current_market_data and need
    to convert TSX share price to CDR price.

    Args:
        price: Raw price from current_market_data
        company_id: Company ID to look up CDR ratio
        cdr_ratios: Dict mapping company_id → cdr_ratio (from companies table)
        exchange_overrides: Optional dict mapping company_id → exchange_override

    Returns:
        CDR-adjusted price (if CDR), or original price (if not CDR)
    """
    if exchange_overrides and exchange_overrides.get(company_id) != "TOR":
        return price
    ratio = cdr_ratios.get(company_id)
    if ratio is None:
        from shared.snapshot_builder import CDR_RATIO
        ratio = float(CDR_RATIO)
    return price / ratio


def _convert_holding_values(
    holdings: list[dict[str, Any]],
    account_currency: str,
    fx_svc: FXService | None = None,
) -> None:
    """Convert holding current_value and total_cost from price_currency to account_currency (in-place).

    Delegates to the shared convert_holding_fx function — the same logic used by
    build_snapshot_row and build_snapshot_from_replay.
    """
    if not holdings:
        return

    enable_fx = settings.ENABLE_FX_CONVERSION
    today = now_utc().date()

    for h in holdings:
        raw_value = Decimal(str(h.get("current_value") or 0))
        total_cost = Decimal(str(h.get("total_cost") or 0))

        conv_value, conv_cost = convert_holding_fx(
            h, raw_value, total_cost, account_currency,
            fx_svc if enable_fx else None, today, enable_fx,
        )
        h["current_value"] = float(conv_value)
        h["total_cost"] = float(conv_cost)
        h["value_currency"] = account_currency


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


def _parse_account_ids(raw: str | None) -> list[int] | None:
    """Parse comma-separated account_ids query param."""
    if not raw:
        return None
    return [int(x) for x in raw.split(",") if x.strip()]


async def _get_dashboard_from_prices(db_user_id: int) -> dict:
    repo = PortfolioRepository()

    all_holdings = repo.get_user_all_holdings(db_user_id)

    if not all_holdings:
        return {"accounts": [], "holdings": [], "overview": {}, "data_quality_flag": "OK"}

    cids = list(set(h["company_id"] for h in all_holdings if h.get("company_id")))
    price_details = {}
    # Fetch CDR ratios for CDR pricing
    cdr_ratios = _get_company_cdr_ratios(cids) if cids else {}
    # Build exchange_overrides from holdings
    exchange_overrides_map = {}
    for h in all_holdings:
        cid = h.get("company_id")
        exch = h.get("exchange_override")
        if cid and exch:
            exchange_overrides_map[cid] = exch
    if cids:
        try:
            cmr = (
                supabase.table("current_market_data")
                .select("company_id, current_price")
                .in_("company_id", cids)
                .execute()
            )
            for row in cmr.data or []:
                cid = row["company_id"]
                px = row.get("current_price")
                if px is not None:
                    price_details[cid] = {"price": float(px), "fetched_at": now_utc(), "ttl_seconds": 86400}
        except Exception:
            pass

    accounts = repo.get_user_accounts(db_user_id, active_only=True)
    account_ids = [a["account_id"] for a in accounts]

    if not account_ids:
        return {"accounts": [], "holdings": [], "overview": {}, "data_quality_flag": "OK"}

    any_stale = False
    for h in all_holdings:
        cid = h.get("company_id")
        pd = price_details.get(cid) if cid else None
        if pd is not None and pd["price"] is not None:
            price = pd["price"]
            # Apply CDR adjustment if this is a CDR holding
            if exchange_overrides_map.get(cid) == "TOR":
                price = apply_cdr_adjustment(price, cid, cdr_ratios, exchange_overrides_map)
                h["price_currency"] = "CAD"
            h["current_price"] = price
            qty = h.get("quantity", 0) or 0
            h["current_value"] = price * qty
            age = (now_utc() - pd["fetched_at"]).total_seconds() if pd["fetched_at"] else float("inf")
            h["price_age_seconds"] = age
            h["data_quality"] = "OK" if age <= pd["ttl_seconds"] else "STALE_PRICE"
            if h["data_quality"] == "STALE_PRICE":
                any_stale = True
        else:
            h["current_price"] = float(h.get("average_cost") or 0)
            h["current_value"] = float(h.get("total_cost") or 0)
            h["price_age_seconds"] = None
            h["data_quality"] = "MISSING"
        h["unrealized_gain_loss"] = h["current_value"] - float(h.get("total_cost", 0))
        h["unrealized_gain_loss_pct"] = (
            (h["unrealized_gain_loss"] / float(h.get("total_cost", 0)) * 100)
            if float(h.get("total_cost", 0)) > 0 else 0.0
        )

    # Apply FX conversion per-account: convert USD values to account currency
    fx_svc = FXService(supabase) if settings.ENABLE_FX_CONVERSION else None
    for acc in accounts:
        acc_holdings = [h for h in all_holdings if h.get("account_id") == acc["account_id"]]
        acc_currency = acc.get("currency", "CAD")
        _convert_holding_values(acc_holdings, acc_currency, fx_svc)
        # Recompute unrealized_gain_loss AFTER FX conversion
        for h in acc_holdings:
            total_cost = float(h.get("total_cost", 0))
            h["unrealized_gain_loss"] = h["current_value"] - total_cost
            h["unrealized_gain_loss_pct"] = (
                (h["unrealized_gain_loss"] / total_cost * 100)
                if total_cost > 0 else 0.0
            )

    enriched_accounts = []
    for acc in accounts:
        acc_holdings = [h for h in all_holdings if h.get("account_id") == acc["account_id"]]
        acc_total_value = float(sum(h.get("current_value") or 0 for h in acc_holdings))
        acc_total_cost = float(sum(h.get("total_cost") or 0 for h in acc_holdings))
        acc_gain_loss = acc_total_value - acc_total_cost
        acc_gain_loss_pct = (acc_gain_loss / acc_total_cost * 100) if acc_total_cost > 0 else 0.0
        enriched_accounts.append({
            "account_id": acc["account_id"],
            "account_name": acc["account_name"],
            "account_type": acc["account_type"],
            "brokerage_name": acc.get("portfolio_brokerages", {}).get("brokerage_name"),
            "currency": acc["currency"],
            "holdings_count": len(acc_holdings),
            "total_value": acc_total_value,
            "total_cost": acc_total_cost,
            "gain_loss": round(acc_gain_loss, 2),
            "gain_loss_pct": round(acc_gain_loss_pct, 2),
            "value_currency": acc.get("currency", "CAD"),
        })

    current_year = now_utc().year
    all_divs = repo.get_accounts_dividends_by_year(account_ids, current_year)
    ytd_dividends = sum(float(d.get("amount") or 0) for d in all_divs)
    overview = _compute_overview_from_holdings(all_holdings, accounts, db_user_id, ytd_dividends)

    holdings_summary = [{
        "company_id": h.get("company_id"),
        "symbol": h["symbol"],
        "company_name": h.get("company_name"),
        "quantity": float(h.get("quantity") or 0),
        "current_price": float(h.get("current_price") or 0),
        "current_value": float(h.get("current_value") or 0),
        "total_cost": float(h.get("total_cost") or 0),
        "unrealized_gain_loss": float(h.get("unrealized_gain_loss") or 0),
        "unrealized_gain_loss_pct": float(h.get("unrealized_gain_loss_pct") or 0),
    } for h in all_holdings]

    return {
        "accounts": enriched_accounts,
        "holdings": holdings_summary,
        "overview": overview | {"value_currency": "CAD"},
        "data_quality_flag": "STALE_PRICE" if any_stale else "OK",
    }


def _log_comparison(old: dict, new: dict):
    old_value = sum(h.get("current_value", 0) for h in old.get("holdings", []))
    new_value = sum(h.get("current_value", 0) for h in new.get("holdings", []))
    value_diff = abs(old_value - new_value) / max(old_value, 1) * 100
    old_by_cid = {h["company_id"]: h["current_price"]
                  for h in old.get("holdings", []) if h.get("company_id")}
    new_by_cid = {h["company_id"]: h["current_price"]
                  for h in new.get("holdings", []) if h.get("company_id")}
    mismatches = []
    for cid in set(old_by_cid) | set(new_by_cid):
        op = old_by_cid.get(cid)
        np = new_by_cid.get(cid)
        if op and np and abs(op - np) / max(op, np) > 0.01:
            mismatches.append(f"company={cid} old={op} new={np}")
    logger.info(
        "[SHADOW] old_value=%.2f new_value=%.2f diff=%.2f%%",
        old_value, new_value, value_diff,
    )
    if mismatches:
        logger.error("[SHADOW] PRICE MISMATCH: %s", "; ".join(mismatches[:5]))


def _get_user_preferred_currency(auth_id: str) -> str:
    """Fetch the user's preferred_currency from the DB. Defaults to 'USD'."""
    try:
        result = supabase.table("users").select("preferred_currency").eq("auth_id", auth_id).maybe_single().execute()
        if result.data and result.data.get("preferred_currency"):
            return result.data["preferred_currency"]
    except Exception:
        logger.warning("Failed to fetch preferred_currency for auth_id %s; falling back to USD", auth_id)
    return "USD"


def _compute_overview_from_holdings(
    all_holdings: list[dict],
    accounts: list[dict],
    db_user_id: int,
    ytd_dividends: float = 0.0,
) -> dict:
    """Compute overview metrics from pre-enriched holdings.

    Unlike get_user_portfolio_overview(), this does NOT:
    - Re-fetch holdings from DB (they're already in all_holdings)
    - Re-enrich with prices (already done upstream)
    - Query dividends per-account (uses batched query from caller)

    It aggregates total_value, total_cost_basis, gain/loss from the
    enriched holdings list in a single O(n) pass instead.
    """
    total_value = Decimal("0")
    total_cost = Decimal("0")
    for h in all_holdings:
        total_value += Decimal(str(h.get("current_value") or 0))
        total_cost += Decimal(str(h.get("total_cost") or 0))
    total_gain = total_value - total_cost
    total_gain_pct = (
        (float(total_gain) / float(total_cost) * 100)
        if total_cost else 0.0
    )
    return {
        "total_value": float(total_value),
        "total_cost_basis": float(total_cost),
        "total_gain_loss": float(total_gain),
        "total_gain_loss_pct": round(total_gain_pct, 2),
        "ytd_dividends": ytd_dividends,
        "holdings_count": len(all_holdings),
        "accounts_count": len(accounts),
    }


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
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        repo = PortfolioRepository()

        accounts = repo.get_user_accounts(db_user_id, active_only=True)
        account_ids = [a["account_id"] for a in accounts]

        if not account_ids:
            return ListAccountsResponse(accounts=[])

        all_holdings = repo.get_holdings_for_accounts(account_ids)
        holdings_by_account: dict[int, list] = defaultdict(list)
        for h in all_holdings:
            holdings_by_account[h["account_id"]].append(h)

        cids = list(set(h["company_id"] for h in all_holdings if h.get("company_id")))
        prices = {}
        # Fetch CDR ratios for CDR pricing
        cdr_ratios = _get_company_cdr_ratios(cids) if cids else {}
        # Build exchange_overrides from holdings
        exchange_overrides_map = {}
        for h in all_holdings:
            cid = h.get("company_id")
            exch = h.get("exchange_override")
            if cid and exch:
                exchange_overrides_map[cid] = exch
        if cids:
            try:
                cmr = (
                    supabase.table("current_market_data")
                    .select("company_id, current_price")
                    .in_("company_id", cids)
                    .execute()
                )
                for row in cmr.data or []:
                    cid = row["company_id"]
                    px = row.get("current_price")
                    if px is not None:
                        prices[cid] = float(px)
            except Exception:
                pass

        enriched_accounts = []
        fx_svc = FXService(supabase) if settings.ENABLE_FX_CONVERSION else None
        for acc in accounts:
            acc_holdings = holdings_by_account.get(acc["account_id"], [])
            acc_currency = acc.get("currency", "CAD")
            for h in acc_holdings:
                cid = h.get("company_id")
                price = prices.get(cid)
                if price is not None:
                    # Apply CDR adjustment if this is a CDR holding
                    if exchange_overrides_map.get(cid) == "TOR":
                        price = apply_cdr_adjustment(price, cid, cdr_ratios, exchange_overrides_map)
                        h["price_currency"] = "CAD"
                    h["current_price"] = price
                    h["current_value"] = price * (h.get("quantity", 0) or 0)
                else:
                    h["current_price"] = float(h.get("average_cost") or 0)
                    h["current_value"] = float(h.get("total_cost") or 0)

            _convert_holding_values(acc_holdings, acc_currency, fx_svc)

            total_value = sum(h.get("current_value") or 0 for h in acc_holdings)
            total_cost = sum(h.get("total_cost") or 0 for h in acc_holdings)
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
                "holdings_count": len(acc_holdings),
                "total_value": round(float(total_value), 2),
                "total_cost": round(float(total_cost), 2),
                "total_gain_loss": round(float(total_value) - float(total_cost), 2),
                "total_gain_loss_pct": round(
                    ((float(total_value) - float(total_cost)) / float(total_cost) * 100)
                    if float(total_cost) > 0 else 0.0, 2
                ),
            })

        return ListAccountsResponse(accounts=enriched_accounts)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List accounts failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio/dashboard", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_portfolio_dashboard(
    request: Request,
    user: dict = Depends(get_current_user_dep),
) -> PortfolioDashboardResponse:
    if not settings.ENABLE_PORTFOLIO_DASHBOARD:
        raise HTTPException(status_code=404, detail="Dashboard endpoint not available")

    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)
        result = await _get_dashboard_from_prices(db_user_id)
        overview = DashboardOverview(**result["overview"])
        resp = PortfolioDashboardResponse(
            accounts=[DashboardAccount(**a) for a in result["accounts"]],
            overview=overview,
            holdings=[DashboardHolding(**h) for h in result["holdings"]],
        )
        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard endpoint failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to load portfolio dashboard",
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
                detail=f"Invalid CSV encoding: {e!s}",
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
            detail=f"Queue import failed: {e!s}",
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
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        repo = PortfolioRepository()
        account = repo.get_account_by_id(account_id)

        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        if account["user_id"] != db_user_id:
            raise HTTPException(
                status_code=403,
                detail="You do not own this account",
            )

        holdings = repo.get_account_holdings(account_id)

        cids = list(set(h["company_id"] for h in holdings if h.get("company_id")))
        prices = {}
        # Fetch CDR ratios for CDR pricing
        cdr_ratios = _get_company_cdr_ratios(cids) if cids else {}
        # Build exchange_overrides from holdings
        exchange_overrides_map = {}
        for h in holdings:
            cid = h.get("company_id")
            exch = h.get("exchange_override")
            if cid and exch:
                exchange_overrides_map[cid] = exch
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

        for h in holdings:
            cid = h.get("company_id")
            price = prices.get(cid)
            qty = h.get("quantity", 0) or 0
            total_cost = h.get("total_cost", 0) or 0
            avg_cost = h.get("average_cost", 0) or 0
            if price is not None:
                # Apply CDR adjustment if this is a CDR holding
                if exchange_overrides_map.get(cid) == "TOR":
                    price = apply_cdr_adjustment(price, cid, cdr_ratios, exchange_overrides_map)
                    h["price_currency"] = "CAD"
                h["current_price"] = price
                h["current_value"] = price * qty
            else:
                h["current_price"] = float(avg_cost) if avg_cost else 0.0
                h["current_value"] = float(total_cost) if total_cost else 0.0

        acc_currency = account.get("currency", "CAD")
        fx_svc = FXService(supabase) if settings.ENABLE_FX_CONVERSION else None
        _convert_holding_values(holdings, acc_currency, fx_svc)

        for h in holdings:
            total_cost = h.get("total_cost", 0) or 0
            h["unrealized_gain_loss"] = h["current_value"] - float(total_cost)
            h["unrealized_gain_loss_pct"] = (
                (h["unrealized_gain_loss"] / float(total_cost) * 100)
                if float(total_cost) > 0 else 0.0
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
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        repo = PortfolioRepository()
        accounts = repo.get_user_accounts(db_user_id, active_only=True)
        all_holdings = repo.get_user_all_holdings(db_user_id)

        cids = list(set(h["company_id"] for h in all_holdings if h.get("company_id")))
        prices = {}
        # Fetch CDR ratios for CDR pricing
        cdr_ratios = _get_company_cdr_ratios(cids) if cids else {}
        # Build exchange_overrides from holdings
        exchange_overrides_map = {}
        for h in all_holdings:
            cid = h.get("company_id")
            exch = h.get("exchange_override")
            if cid and exch:
                exchange_overrides_map[cid] = exch
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

        for h in all_holdings:
            cid = h.get("company_id")
            price = prices.get(cid)
            qty = h.get("quantity", 0) or 0
            total_cost = h.get("total_cost", 0) or 0
            avg_cost = h.get("average_cost", 0) or 0
            if price is not None:
                # Apply CDR adjustment if this is a CDR holding
                if exchange_overrides_map.get(cid) == "TOR":
                    price = apply_cdr_adjustment(price, cid, cdr_ratios, exchange_overrides_map)
                    h["price_currency"] = "CAD"
                h["current_price"] = price
                h["current_value"] = price * qty
            else:
                h["current_price"] = float(avg_cost) if avg_cost else 0.0
                h["current_value"] = float(total_cost) if total_cost else 0.0

        # Apply FX conversion per-account
        fx_svc = FXService(supabase) if settings.ENABLE_FX_CONVERSION else None
        account_currency_map = {a["account_id"]: a.get("currency", "CAD") for a in accounts}
        for h in all_holdings:
            acc_id = h.get("account_id")
            acc_currency = account_currency_map.get(acc_id, "CAD") if acc_id else "CAD"
            _convert_holding_values([h], acc_currency, fx_svc)

        for h in all_holdings:
            total_cost = h.get("total_cost", 0) or 0
            h["unrealized_gain_loss"] = h["current_value"] - float(total_cost)
            h["unrealized_gain_loss_pct"] = (
                (h["unrealized_gain_loss"] / float(total_cost) * 100)
                if float(total_cost) > 0 else 0.0
            )

        if aggregated:
            service = _get_portfolio_service()
            holdings = service.aggregate_holdings(all_holdings)
            return {"holdings": holdings}

        return {"holdings": all_holdings}

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
    account_id: int | None = Query(None, description="Filter to a specific account"),
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
        preferred_currency = _get_user_preferred_currency(auth_id)
        overview = await service.get_user_portfolio_overview(
            db_user_id, account_ids=ids_param, display_currency=preferred_currency,
        )

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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
    limit: int = 100,
    activity_type: str | None = Query(None, description="Filter by activity type (BUY, SELL, DIVIDEND, etc.)"),
    search: str | None = Query(None, description="Search symbol or security name"),
    from_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
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
        current_year = now_utc().year
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
            detail=f"Failed to create transaction: {e!s}",
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
    PortfolioDividendHolding,
    PortfolioDividendHoldingDetail,
    PortfolioDividendSummary,
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
) -> list[UpcomingExDate]:
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
) -> list[PortfolioDividendHolding]:
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
        timer = RouteTimer(endpoint="get_portfolio_performance", user_id=db_user_id)
        with timer:
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

        snaps = result.get("snapshots", [])
        if snaps:
            logger.info("[PERF_DEBUG] period=%s source=%s rows=%d ret=%.2f%% -----BEGIN ALL ROWS-----",
                        period, result.get("data_source","?"), len(snaps), result.get("total_return_pct",0))
            for s in snaps:
                logger.info("[PERF_DEBUG]   date=%s V=%.2f ND=%.2f", s["date"], s["value"], s.get("net_deposits",0))
            logger.info("[PERF_DEBUG] -----END ALL ROWS-----")

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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
        timer = RouteTimer(endpoint="get_performance_compare", user_id=db_user_id)
        with timer:
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


@router.post("/portfolio/performance/batch", tags=["Portfolio"], status_code=200)
@limiter.limit("60/minute")
async def get_portfolio_performance_batch(
    request: Request,
    body: dict[str, Any],
    user: dict = Depends(get_current_user_dep),
) -> PerformanceBatchResponse:
    """
    Batch fetch portfolio performance for multiple periods in a single request.

    Body:
    ```json
    {
      "account_ids": [1, 4, 9],
      "periods": ["1M", "3M", "1Y", "5Y", "ALL"]
    }
    ```
    Returns a map of period → performance response.
    """
    try:
        auth_id = user["sub"]
        db_user_id = _resolve_db_user_id(auth_id)

        account_ids: list[int] | None = body.get("account_ids")
        periods: list[str] = body.get("periods", ["1Y"])

        if account_ids is not None and not isinstance(account_ids, list):
            raise HTTPException(status_code=422, detail="account_ids must be a list of integers")

        service = _get_portfolio_service()
        results: dict[str, Any] = {}

        for period in periods:
            result = await service.get_portfolio_performance(db_user_id, period, account_ids)
            results[period] = PerformanceResponse(**result) if result.get("success") else None

        return PerformanceBatchResponse(success=True, results=results)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch performance failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch batch performance",
        )


@router.get("/portfolio/allocation", tags=["Portfolio"], status_code=200)
@limiter.limit("20/minute")
async def get_portfolio_allocation(
    request: Request,
    group_by: str = Query("sector", description="Group by: sector, geography, or account"),
    account_ids: str | None = Query(None, description="Comma-separated account IDs"),
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
        timer = RouteTimer(endpoint="list_benchmarks", user_id=0)
        with timer:
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
    account_ids: str | None = Query(None, description="Comma-separated account IDs; empty = all"),
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
