"""
Watchlist Items API Endpoints
Updated with financial data loading support while preserving existing functionality.
"""
import logging
import re
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from pydantic import BaseModel, Field, field_validator
from shared.time_utils import now_iso
from typing import Optional
from providers.yfinance_provider import YFinanceProvider
from dependencies import (
    get_current_user_dep,
    get_watchlist_service,
    get_watchlist_repository,
    limiter,
)
from application.services.watchlist_service import WatchlistService
from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository

logger = logging.getLogger(__name__)
router = APIRouter()
stock_provider = YFinanceProvider()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_db_user_id(auth_id: str, repo: SupabaseWatchlistRepository) -> int:
    """Resolve Firebase auth_id to internal user_id via repository."""
    user = repo.find_user_by_auth_id(auth_id)
    if not user:
        raise HTTPException(status_code=403, detail="User not found.")
    return user["user_id"]

# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class WatchlistItemData(BaseModel):
    watchlist_item_id: int
    watchlist_id: int
    company_id: int
    target_buy: float | None
    target_sell: float | None

    class Config:
        populate_by_name = True
        from_attributes = True


class StockData(BaseModel):
    id: int
    symbol: str
    name: str
    price: float
    change: float
    changePercent: float
    lastUpdated: str | None = Field(None, alias="lastUpdated")

    class Config:
        populate_by_name = True


class AddStockResponse(BaseModel):
    watchlist_item: WatchlistItemData
    stock_data: StockData
    financials_loading: bool = False
    is_new_stock: bool = False


class WatchlistItemIn(BaseModel):
    watchlist_id: int
    symbol: str = Field(..., min_length=1, max_length=10)
    target_buy: float | None = Field(None, ge=0)
    target_sell: float | None = Field(None, ge=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str):
        if not re.match(r"^[A-Z0-9.-]+$", v.upper()):
            raise ValueError("Invalid ticker symbol format")
        return v.upper()


class WatchlistItemUpdate(BaseModel):
    target_buy: float | None = Field(None, ge=0)
    target_sell: float | None = Field(None, ge=0)


class DeleteItemRequest(BaseModel):
    item_id: int

# ============================================================================
# GET /stocks/search — Symbol Typeahead
# ============================================================================
@router.get("/stocks/search")
@limiter.limit("30/minute")
async def search_stocks(
    request: Request,
    q: str,
    user_token: dict = Depends(get_current_user_dep),
) -> dict:
    """
    Typeahead search for ticker symbols.
    Uses yfinance.Search — same data universe as defeatbeta.
    Returns max 8 results with symbol, name, exchange, type.
    """
    q = q.strip()
    if len(q) < 1:
        return {"results": []}
    try:
        import yfinance as yf
        search = yf.Search(q, max_results=8, enable_fuzzy_query=False)
        quotes = search.quotes or []
        results = [
            {
                "symbol":   r.get("symbol", ""),
                "name":     r.get("shortname") or r.get("longname") or r.get("symbol", ""),
                "exchange": r.get("exchDisp") or r.get("exchange") or "",
                "type":     (r.get("typeDisp") or r.get("quoteType") or "").lower(),
            }
            for r in quotes
            if r.get("symbol")
        ]
        return {"results": results}
    except Exception as e:
        logger.warning(f"Stock search failed for query '{q}': {e}")
        return {"results": []}


# ============================================================================
# POST /watchlist-items — Add Stock
# ============================================================================

@router.post("/watchlist-items", status_code=201, response_model=AddStockResponse)
@limiter.limit("10/minute")
async def add_item_to_watchlist(
    request: Request,
    item: WatchlistItemIn,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user_dep),
    service: WatchlistService = Depends(get_watchlist_service),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
) -> AddStockResponse:
    try:
        auth_id = user_token["sub"]
        db_user_id = get_db_user_id(auth_id, repo)

        # Verify ownership
        watchlist = repo.find_watchlist_owner(item.watchlist_id)
        if not watchlist or watchlist["user_id"] != db_user_id:
            raise HTTPException(status_code=403, detail="Permission denied.")

        # Hard cap enforced server-side
        if repo.count_watchlist_items(item.watchlist_id) >= 50:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This watchlist is full (50/50 stocks). "
                    "Create a new watchlist to continue adding stocks."
                ),
            )

        symbol = item.symbol.upper()

        # ── 1. Business logic ──────────────────────────────────────────────
        svc_result = await service.add_stock_to_watchlist(
            user_id=db_user_id,
            symbol=symbol,
            watchlist_id=item.watchlist_id,
            target_buy=item.target_buy,
            target_sell=item.target_sell,
        )

        # ── 2. Subscribe to SSE ──────────────────────────────────────────────
        from api.watchlists import subscribe_symbol, broadcast_with_retry
        subscribed = await subscribe_symbol(svc_result["symbol"], auth_id)

        # ── 3. Broadcast with retry ─────────────────────────────────────────
        # Uses service data — NO re-fetch needed
        if subscribed and svc_result.get("current_price"):
            await broadcast_with_retry(
                svc_result["symbol"],
                svc_result["current_price"],
                svc_result.get("change", 0.0),
                svc_result.get("change_percent", 0.0)
            )

        # ── 4. Return response ─────────────────────────────────────────────
        # Uses service data — NO re-fetch needed
        return AddStockResponse(
            watchlist_item=WatchlistItemData(
                watchlist_item_id=svc_result["watchlist_item_id"],
                watchlist_id=item.watchlist_id,
                company_id=svc_result["company_id"],
                target_buy=item.target_buy,
                target_sell=item.target_sell,
            ),
            stock_data=StockData(
                id=svc_result["watchlist_item_id"],
                symbol=svc_result["symbol"],
                name=svc_result.get("company_name", svc_result["symbol"]),
                price=float(svc_result.get("current_price") or 0.0),
                change=float(svc_result.get("change") or 0.0),
                changePercent=float(svc_result.get("change_percent") or 0.0),
                lastUpdated=now_iso(),
            ),
            financials_loading=bool(svc_result.get("financials_loading", False)),
            is_new_stock=bool(svc_result.get("is_new_stock", False)),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] add_item_to_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

# ============================================================================
# POST /stocks/{symbol}/refresh-financials — On-Demand Refresh
# ============================================================================

@router.post("/stocks/{symbol}/refresh-financials", status_code=200)
@limiter.limit("5/minute")
async def refresh_stock_financials(
    symbol: str,
    request: Request,
    user_token: dict = Depends(get_current_user_dep),
    service: WatchlistService = Depends(get_watchlist_service),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
) -> dict:
    try:
        auth_id = user_token["sub"]
        get_db_user_id(auth_id, repo)  # auth check — result unused

        company = repo.find_company_by_symbol(symbol.upper())
        if not company:
            raise HTTPException(
                status_code=404,
                detail=f"Stock '{symbol}' not found in your watchlists",
            )

        result = await service.refresh_company_financials(
            symbol=symbol.upper(),
            company_id=company["company_id"],
        )

        logger.info(f"✅ On-demand refresh complete for {symbol}: {result['total_rows']} rows")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] refresh_stock_financials: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh financial data")

# ============================================================================
# PATCH /watchlist-items/{item_id} — Update Targets
# ============================================================================

@router.patch("/watchlist-items/{item_id}", response_model=WatchlistItemData)
@limiter.limit("20/minute")
def update_watchlist_item_targets(
    request: Request,
    item_id: int,
    update: WatchlistItemUpdate,
    user_token: dict = Depends(get_current_user_dep),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
) -> WatchlistItemData:
    try:
        auth_id = user_token["sub"]
        db_user_id = get_db_user_id(auth_id, repo)

        item = repo.find_watchlist_item_with_owner(item_id)
        if not item or item["watchlists"]["user_id"] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found or permission denied.")

        update_res = repo.update_item_targets(
            item_id=item_id,
            target_buy=update.target_buy,
            target_sell=update.target_sell,
        )
        if not update_res:
            raise HTTPException(status_code=500, detail="Failed to update watchlist item.")

        return WatchlistItemData.model_validate(update_res)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] update_watchlist_item_targets: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

# ============================================================================
# POST /watchlist-items/delete — Remove Item
# ============================================================================

@router.post("/watchlist-items/delete", status_code=204)
@limiter.limit("20/minute")
async def remove_item_from_watchlist(
    request: Request,
    req: DeleteItemRequest,
    user_token: dict = Depends(get_current_user_dep),
    repo: SupabaseWatchlistRepository = Depends(get_watchlist_repository),
) -> None:
    try:
        auth_id = user_token["sub"]
        db_user_id = get_db_user_id(auth_id, repo)

        # ── 1. Verify ownership and get symbol ──────────────────────────────
        item = repo.find_watchlist_item_with_owner(req.item_id)
        if not item or item["watchlists"]["user_id"] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found.")

        symbol = item["companies"]["ticker_symbol"]

        # ── 2. Check BEFORE delete ──────────────────────────────────────────
        # Critical: check BEFORE delete to avoid race condition
        remaining = repo.user_has_symbol(db_user_id, symbol)

        # ── 3. Delete from database ─────────────────────────────────────────
        repo.delete_item(req.item_id)

        # ── 4. Unsubscribe only if no remaining copies ──────────────────────
        if not remaining:
            from api.watchlists import unsubscribe_symbol
            await unsubscribe_symbol(symbol, auth_id)

        return None

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ERROR] remove_item_from_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")