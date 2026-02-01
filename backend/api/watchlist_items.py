"""
Watchlist Items API Endpoints
Updated with financial data loading support while preserving existing functionality.
"""

import logging
import re
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request, Depends
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional

from database import supabase
from providers.yfinance_provider import YFinanceProvider
from services.sync_service import sync_service
from dependencies import get_current_user_dep, get_watchlist_service, limiter
from application.services.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)

router = APIRouter()
stock_provider = YFinanceProvider()


# ============================================================================
# HELPER FUNCTIONS (Existing)
# ============================================================================

def get_db_user_id(auth_id: str) -> int:
    """Get user ID from Firebase auth ID."""
    res = supabase.table('users').select('user_id').eq('auth_id', auth_id).single().execute()
    if not res.data:
        raise HTTPException(status_code=403, detail="User not found.")
    return res.data['user_id']


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class WatchlistItemData(BaseModel):
    """Watchlist item database record."""
    watchlist_item_id: int
    watchlist_id: int
    company_id: int
    target_buy: float | None
    target_sell: float | None
    
    class Config:
        populate_by_name = True
        from_attributes = True


class StockData(BaseModel):
    """Real-time stock price data for UI display (sourced from YF only)."""
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
    """Response when adding stock to watchlist."""
    watchlist_item: WatchlistItemData
    stock_data: StockData
    financials_loading: bool = False  # NEW: indicates if background task is running
    is_new_stock: bool = False  # NEW: indicates if this is a new company


class WatchlistItemIn(BaseModel):
    """Request to add item to watchlist."""
    watchlist_id: int
    symbol: str = Field(..., min_length=1, max_length=10)
    target_buy: float | None = Field(None, ge=0)
    target_sell: float | None = Field(None, ge=0)
    
    @field_validator('symbol')
    @classmethod
    def validate_symbol(cls, v: str):
        if not re.match(r'^[A-Z0-9.-]+$', v.upper()):
            raise ValueError('Invalid ticker symbol format')
        return v.upper()


class WatchlistItemUpdate(BaseModel):
    """Request to update target buy/sell prices."""
    target_buy: float | None = Field(None, ge=0)
    target_sell: float | None = Field(None, ge=0)


class DeleteItemRequest(BaseModel):
    """Request to delete watchlist item."""
    item_id: int


# ============================================================================
# POST /watchlist-items - Add Stock (UPDATED)
# ============================================================================

@router.post("/watchlist-items", status_code=201, response_model=AddStockResponse)
@limiter.limit("10/minute")
async def add_item_to_watchlist(
    request: Request,
    item: WatchlistItemIn,
    background_tasks: BackgroundTasks,
    user_token: dict = Depends(get_current_user_dep),
    service: WatchlistService = Depends(get_watchlist_service),  # NEW: Financial service
) -> AddStockResponse:
    """
    Add a stock to watchlist.
    
    **Design:**
    - Phase 1 (Fast): Delegated to WatchlistService.add_stock_to_watchlist()
        * Upsert company
        * Fetch **YF** current price -> upsert into public.current_market_data
        * Insert watchlist item
        * Schedule background fundamentals load via DefeatBetaProvider (full for new, incremental otherwise)
    - Phase 2 (Background): DefeatBeta -> fallback YF for all fundamentals (IS/BS/CF/Earnings/Dividends)

    **Guarantees:**
    - YF is used only for current market data (and optionally to enrich the returned response).
    - All fundamentals enter via DefeatBetaProvider.get_all_financials_optimized().
    """
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        # Verify user owns this watchlist
        watchlist_res = supabase.table('watchlists').select('user_id').eq('id', item.watchlist_id).single().execute()
        if not watchlist_res.data or watchlist_res.data['user_id'] != db_user_id:
            raise HTTPException(status_code=403, detail="Permission denied.")
        
        symbol = item.symbol.upper()

        # Delegate full add flow to the service (single orchestration point)
        svc_result = await service.add_stock_to_watchlist(
            user_id=db_user_id,
            symbol=symbol,
            watchlist_id=item.watchlist_id,            
            target_buy=item.target_buy,
            target_sell=item.target_sell,
        )
        # Expected keys from service:
        # - watchlist_item_id, company_id, symbol, current_price, financials_loading, is_new_stock, message

        # Optionally enrich response display with fresh YF details (no DB writes here)
        # This keeps UI fields like 'name', 'change', and 'changePercent' without re-implementing logic.
        try:
            sd = stock_provider.get_stock_details(symbol)
        except Exception:
            sd = None

        # Update market data
        now_iso = datetime.now().isoformat()
        stock_name = getattr(sd, "long_name", None) or symbol
        price = svc_result.get("current_price") or (getattr(sd, "price", None) or 0.0)
        prev_close = getattr(sd, "close_price", None) or getattr(sd, "previous_close", None)
        change = float(price - prev_close) if (price is not None and prev_close) else 0.0
        change_pct = float((change / prev_close) * 100) if (prev_close and prev_close != 0) else 0.0

        # Compose response models
        watchlist_item_out = WatchlistItemData(
            watchlist_item_id=svc_result["watchlist_item_id"],
            watchlist_id=item.watchlist_id,
            company_id=svc_result["company_id"],
            target_buy=item.target_buy,
            target_sell=item.target_sell,
        )
        stock_data_out = StockData(
            id=svc_result["watchlist_item_id"],
            symbol=svc_result["symbol"],
            name=stock_name,
            price=float(price or 0.0),
            change=float(change),
            changePercent=float(change_pct),
            lastUpdated=now_iso,
        )

        return AddStockResponse(
            watchlist_item=watchlist_item_out,
            stock_data=stock_data_out,
            financials_loading=bool(svc_result.get("financials_loading", False)),
            is_new_stock=bool(svc_result.get("is_new_stock", False)),
        )
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"[ERROR] add_item_to_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


# ============================================================================
# POST /stocks/{symbol}/refresh-financials - On-Demand Refresh (NEW)
# ============================================================================

@router.post("/stocks/{symbol}/refresh-financials", status_code=200)
@limiter.limit("5/minute")
async def refresh_stock_financials(
    symbol: str,
    request: Request,
    user_token: dict = Depends(get_current_user_dep),
    service: WatchlistService = Depends(get_watchlist_service),
) -> dict:
    """
    Manually trigger financial data refresh for a stock.
    
    **Use case:** When user clicks "Refresh" button or wants latest data immediately.
    
    **What happens:**
    1. Fetches latest financial statements from defeat-beta
    2. Stores only NEW quarters (smart filtering)
    3. Updates company metadata
    4. Returns summary
    
    **Response includes:**
    - `rows_upserted`: Breakdown by statement type
    - `total_rows`: Total rows stored
    - `fetched_at`: When data was fetched
    - `next_earnings_date`: Next earnings announcement
    
    **Error cases:**
    - 404: Stock not found
    - 503: External service unavailable
    - 500: Database error
    """
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        logger.info(f"On-demand refresh request for {symbol}")
        
        # Get company ID
        company_response = supabase.table('companies').select('company_id').eq(
            'ticker_symbol', symbol.upper()
        ).single().execute()
        
        if not company_response.data:
            raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found in your watchlists")
        
        company_id = company_response.data['company_id']
        
        # Call service
        result = await service.refresh_company_financials(
            symbol=symbol.upper(),
            company_id=company_id,
        )
        
        logger.info(f"✅ On-demand refresh complete for {symbol}: {result['total_rows']} rows")
        
        return result
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"[ERROR] refresh_stock_financials: {e}")
        raise HTTPException(status_code=500, detail="Failed to refresh financial data")


# ============================================================================
# PATCH /watchlist-items/{item_id} - Update Targets (EXISTING - UNCHANGED)
# ============================================================================

@router.patch("/watchlist-items/{item_id}", response_model=WatchlistItemData)
@limiter.limit("20/minute")
def update_watchlist_item_targets(
    request: Request,
    item_id: int,
    update: WatchlistItemUpdate,
    user_token: dict = Depends(get_current_user_dep)
) -> WatchlistItemData:
    """
    Update target buy/sell prices for a watchlist item.
    
    **Unchanged from existing implementation.**
    """
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        item_res = supabase.table('watchlist_items') \
            .select('watchlist_item_id, watchlists!inner(user_id)') \
            .eq('watchlist_item_id', item_id) \
            .single().execute()
        
        if not item_res.data or item_res.data['watchlists']['user_id'] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found or permission denied.")
        
        update_res = supabase.table('watchlist_items').update({
            'target_buy': update.target_buy,
            'target_sell': update.target_sell
        }).eq('watchlist_item_id', item_id).execute()
        
        if not update_res.data:
            raise HTTPException(status_code=500, detail="Failed to update watchlist item.")
        
        return WatchlistItemData.model_validate(update_res.data[0])
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"[ERROR] update_watchlist_item_targets: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")


# ============================================================================
# POST /watchlist-items/delete - Remove Item (EXISTING - UNCHANGED)
# ============================================================================

@router.post("/watchlist-items/delete", status_code=204)
@limiter.limit("20/minute")
def remove_item_from_watchlist(
    request: Request,
    req: DeleteItemRequest,
    user_token: dict = Depends(get_current_user_dep)
) -> None:
    """
    Remove a stock from a watchlist.
    
    **Unchanged from existing implementation.**
    """
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        item_res = supabase.table('watchlist_items').select('watchlist_item_id, watchlists!inner(user_id)').eq('watchlist_item_id', req.item_id).single().execute()
        if not item_res.data or item_res.data['watchlists']['user_id'] != db_user_id:
            raise HTTPException(status_code=404, detail="Item not found or permission denied.")
        
        supabase.table('watchlist_items').delete().eq('watchlist_item_id', req.item_id).execute()
        return
    
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"[ERROR] remove_item_from_watchlist: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")