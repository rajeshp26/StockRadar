# -*- coding: utf-8 -*-
"""
Super Investors API Endpoint

GET /api/analysis/{symbol}/super-investors
Returns institutional ownership data from 13F filings.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Any, Dict
from datetime import datetime, timedelta
import logging
from database import supabase

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])

# Cache freshness: 24 hours
CACHE_FRESHNESS_HOURS = 24


@router.get("/{symbol}/super-investors")
async def get_super_investors(
    symbol: str,
) -> Dict[str, Any]:
    """
    Get institutional ownership data for a stock.
    
    Flow:
    1. Check DB for recent data (last 24 hours)
    2. If found, return from DB
    3. If not found or stale, fetch from SEC and update DB
    """
    try:
        ticker = symbol.upper()
        
        # Step 1: Try to get from database
        db_data = _get_holdings_from_db(ticker)
        
        if db_data and db_data["overlap_count"] > 0:
            logger.info(f"[DEBUG] Returning {ticker} data from database")
            return db_data
        
        # Step 2: Fetch from SEC (live)
        logger.info(f"[DEBUG] No cached data for {ticker}, fetching from SEC...")
        from application.services.super_investors_service import SuperInvestorsService
        
        service = SuperInvestorsService()
        data = service.get_super_investor_holdings(ticker, limit=10)

        if data["overlap_count"] == 0:
            return {
                "ticker": ticker,
                "holders": [],
                "overlap_count": 0,
                "avg_portfolio_weight": 0.0,
                "conviction_level": "none",
                "recent_activity": {"buyers": [], "sellers": []},
                "message": "No tracked super investors currently hold this stock.",
            }

        return data

    except Exception as e:
        logger.error(f"Failed to fetch super investors for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch super investor data: {str(e)}"
        )


def _get_holdings_from_db(ticker: str) -> Dict[str, Any] | None:
    """Get holdings from database if fresh enough."""
    try:
        # Get company_id
        company_result = supabase.table("companies").select(
            "company_id"
        ).eq("ticker_symbol", ticker).execute()
        
        if not company_result.data or len(company_result.data) == 0:
            return None
        
        company_id = company_result.data[0]["company_id"]
        
        # Get holdings from last 30 days
        cutoff_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        
        holdings_result = supabase.table("institutional_holdings").select(
            "holding_id, shares_held, position_value, portfolio_weight, "
            "shares_change, shares_change_pct, change_type, quarter_end_date, filing_date, investor_id"
        ).eq("company_id", company_id).gte("filing_date", cutoff_date).execute()
        
        if not holdings_result.data or len(holdings_result.data) == 0:
            return None
        
        # Get investor IDs and query investors separately
        investor_ids = [h["investor_id"] for h in holdings_result.data]
        if not investor_ids:
            return None
        
        investors_result = supabase.table("institutional_investors").select(
            "investor_id, investor_name, firm_name, investor_tag, investment_style"
        ).in_("investor_id", investor_ids).execute()
        
        # Build lookup map
        investors_map = {inv["investor_id"]: inv for inv in (investors_result.data or [])}
        
        # Build holders list
        holders = []
        for holding in holdings_result.data:
            investor_id = holding.get("investor_id")
            inv = investors_map.get(investor_id, {})
            
            if not inv:
                continue
            
            holders.append({
                "investor_name": inv.get("investor_name", ""),
                "firm": inv.get("firm_name", ""),
                "tag": inv.get("investor_tag", ""),
                "style": inv.get("investment_style", ""),
                "shares": holding.get("shares_held", 0),
                "value": holding.get("position_value", 0),
                "portfolio_weight": holding.get("portfolio_weight", 0),
                "change_pct": holding.get("shares_change_pct", 0) or 0,
                "change_type": holding.get("change_type", "held"),
                "quarter_date": str(holding.get("quarter_end_date", "")),
            })
        
        if not holders:
            return None
        
        # Calculate aggregations
        overlap_count = len(holders)
        avg_weight = sum(h["portfolio_weight"] for h in holders) / overlap_count if overlap_count > 0 else 0
        
        buyers = [h for h in holders if h["change_type"] in ("new", "increased")]
        sellers = [h for h in holders if h["change_type"] in ("decreased", "sold")]
        
        return {
            "ticker": ticker,
            "holders": holders,
            "overlap_count": overlap_count,
            "avg_portfolio_weight": round(avg_weight, 4),
            "conviction_level": "moderate" if avg_weight >= 0.005 else "low",
            "recent_activity": {
                "buyers": buyers[:5],
                "sellers": sellers[:5],
            },
            "source": "database",
        }
        
    except Exception as e:
        logger.error(f"[DEBUG] Error reading from DB: {e}")
        return None

