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
    """Real-time stock price data."""
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
    
    **NEW:** Supports background financial data loading!
    
    **Two-phase operation:**
    
    Phase 1 (Fast, < 2 seconds):
    - Fetch stock details from yfinance
    - Create/upsert company
    - Store market data
    - Add to watchlist
    - Return to client
    
    Phase 2 (Background, 30-40 seconds for new stocks):
    - Load full financial history (14+ years) from defeat-beta
    - Store to all financial tables
    - Update company metadata
    
    **Response fields:**
    - `financials_loading`: True if background task loading financial data
    - `is_new_stock`: True if this is first time seeing this company
    
    **Error cases:**
    - 403: User doesn't own this watchlist
    - 404: Stock symbol not found
    - 409: Stock already in this watchlist
    - 500: Database error
    """
    try:
        auth_id = user_token["uid"]
        db_user_id = get_db_user_id(auth_id)
        
        # Verify user owns this watchlist
        watchlist_res = supabase.table('watchlists').select('user_id').eq('id', item.watchlist_id).single().execute()
        if not watchlist_res.data or watchlist_res.data['user_id'] != db_user_id:
            raise HTTPException(status_code=403, detail="Permission denied.")
        
        # Fetch stock details
        stock_details = stock_provider.get_stock_details(item.symbol)
        if not stock_details:
            raise HTTPException(status_code=404, detail=f"Stock symbol '{item.symbol}' not found.")
        
        # Upsert currency if needed
        if stock_details.currency:
            supabase.table('currencies').upsert(
                {'code': stock_details.currency, 'name': stock_details.currency},
                on_conflict='code'
            ).execute()
        
        # Prepare company data
        company_data = {
            'ticker_symbol': stock_details.ticker_symbol,
            'company_name': stock_details.long_name,
            'exchange': stock_details.exchange or 'UNKNOWN',
            'sector': stock_details.sector,
            'industry': stock_details.industry,
            'currency': stock_details.currency or 'USD',
            'description': stock_details.description,
            'website': stock_details.website,
            'next_earnings_date': stock_details.next_earnings_date.isoformat() if stock_details.next_earnings_date else None
        }
        
        # Upsert company
        company_res = supabase.table('companies').upsert(
            company_data, on_conflict='ticker_symbol,exchange'
        ).execute()
        
        if not company_res.data:
            raise HTTPException(status_code=500, detail="Database Error: Failed to upsert company.")
        
        company_id = company_res.data[0]['company_id']
        is_new_company = not company_res.data[0].get('created_at')  # Check if just created
        
        # Update market data
        now_iso = datetime.now().isoformat()
        market_data = {
            'company_id': company_id,
            'current_price': stock_details.price,
            'open_price': stock_details.open_price,
            'high_price': stock_details.high_price,
            'low_price': stock_details.low_price,
            'close_price': stock_details.close_price,
            'volume': stock_details.volume,
            'market_state': stock_details.market_state,
            'last_updated': now_iso
        }
        supabase.table('current_market_data').upsert(market_data, on_conflict='company_id').execute()
        
        # Add to watchlist
        item_res = supabase.table('watchlist_items').insert({
            'watchlist_id': item.watchlist_id,
            'company_id': company_id,
            'target_buy': item.target_buy,
            'target_sell': item.target_sell
        }).execute()
        
        if not item_res.data:
            check_dup = supabase.table('watchlist_items').select('*').eq('watchlist_id', item.watchlist_id).eq('company_id', company_id).execute()
            if check_dup.data:
                raise HTTPException(status_code=409, detail="This stock is already in your watchlist.")
            raise HTTPException(status_code=500, detail="Database Error: Failed to insert watchlist item.")
        
        new_item_db = item_res.data[0]
        
        # Start background tasks
        # EXISTING: Sync service (keeps existing functionality)
        background_tasks.add_task(sync_service.sync_full_company_data, company_id, stock_details.ticker_symbol)
        
        # NEW: Load financial data if new company
        financials_loading = False
        if is_new_company:
            background_tasks.add_task(
                service._fetch_and_store_financials_optimized,
                symbol=stock_details.ticker_symbol,
                company_id=company_id,
                is_new_company=True,
            )
            financials_loading = True
            logger.info(f"Started background financial load for {stock_details.ticker_symbol}")
        
        # Build response
        stock_data_out = StockData(
            id=new_item_db['watchlist_item_id'],
            symbol=stock_details.ticker_symbol,
            name=stock_details.long_name,
            price=stock_details.price,
            change=stock_details.change,
            changePercent=stock_details.change_percent,
            lastUpdated=now_iso
        )
        watchlist_item_out = WatchlistItemData.model_validate(new_item_db)
        
        return AddStockResponse(
            watchlist_item=watchlist_item_out,
            stock_data=stock_data_out,
            financials_loading=financials_loading,  # NEW
            is_new_stock=is_new_company,  # NEW
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