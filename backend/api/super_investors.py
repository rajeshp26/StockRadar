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
 
@router.get("/{symbol}/super-investors/history")
async def get_super_investors_history(
    symbol: str,
) -> Dict[str, Any]:
    """
    Get historical position data for super investors holding this stock.
    
    Returns quarterly holdings from 2021 onwards (or last 5 years).
    
    Response:
    {
        "ticker": "BAC",
        "investors": [
            {
                "investor_id": 1,
                "investor_name": "Warren Buffett",
                "firm": "Berkshire Hathaway Inc.",
                "tag": "BUFFETT",
                "style": "Value / Quality",
                "holdings": [
                    {
                        "quarter_date": "2021-03-31",
                        "shares_held": 1000000000,
                        "position_value": 39000000000,
                        "portfolio_weight": 0.12,
                        "change_shares": 50000000,
                        "change_pct": 5.26,
                        "change_type": "increased"
                    },
                    ...
                ]
            },
            ...
        ],
        "quarters": ["2021-03-31", "2021-06-30", ...],
        "earliest_date": "2021-03-31",
        "latest_date": "2024-12-31"
    }
    """
    try:
        ticker = symbol.upper()
        
        # Get company_id
        company_result = supabase.table("companies").select(
            "company_id"
        ).eq("ticker_symbol", ticker).execute()
        
        if not company_result.data or len(company_result.data) == 0:
            return {
                "ticker": ticker,
                "investors": [],
                "quarters": [],
                "earliest_date": None,
                "latest_date": None,
                "message": "Stock not found in database."
            }
        
        company_id = company_result.data[0]["company_id"]
        
        # Get cutoff date (5 years ago or 2021-01-01, whichever is more recent)
        from datetime import datetime, timedelta
        five_years_ago = (datetime.now() - timedelta(days=5*365)).date()
        cutoff_date = max(five_years_ago, datetime(2021, 1, 1).date())
        
        # Get all holdings for this company since cutoff
        holdings_result = supabase.table("institutional_holdings").select(
            "holding_id, investor_id, quarter_end_date, shares_held, position_value, "
            "portfolio_weight, shares_change, shares_change_pct, change_type"
        ).eq("company_id", company_id).gte(
            "quarter_end_date", str(cutoff_date)
        ).order("quarter_end_date").execute()
        
        if not holdings_result.data or len(holdings_result.data) == 0:
            return {
                "ticker": ticker,
                "investors": [],
                "quarters": [],
                "earliest_date": None,
                "latest_date": None,
                "message": "No historical holdings data available."
            }
        
        # Get unique investor IDs
        investor_ids = list(set(h["investor_id"] for h in holdings_result.data))
        
        # Get investor details
        investors_result = supabase.table("institutional_investors").select(
            "investor_id, investor_name, firm_name, investor_tag, investment_style"
        ).in_("investor_id", investor_ids).eq("is_super_investor", True).execute()
        
        if not investors_result.data:
            return {
                "ticker": ticker,
                "investors": [],
                "quarters": [],
                "earliest_date": None,
                "latest_date": None,
                "message": "No super investor data found."
            }
        
        # Build investor lookup map
        investors_map = {
            inv["investor_id"]: {
                "investor_id": inv["investor_id"],
                "investor_name": inv["investor_name"],
                "firm": inv["firm_name"],
                "tag": inv["investor_tag"],
                "style": inv["investment_style"],
                "holdings": []
            }
            for inv in investors_result.data
        }
        
        # Group holdings by investor
        for holding in holdings_result.data:
            investor_id = holding["investor_id"]
            if investor_id not in investors_map:
                continue
                
            investors_map[investor_id]["holdings"].append({
                "quarter_date": holding["quarter_end_date"],
                "shares_held": holding["shares_held"],
                "position_value": holding["position_value"],
                "portfolio_weight": holding["portfolio_weight"],
                "change_shares": holding.get("shares_change"),
                "change_pct": holding.get("shares_change_pct"),
                "change_type": holding.get("change_type", "held"),
            })
        
        # Extract unique quarters and sort
        all_quarters = sorted(set(h["quarter_end_date"] for h in holdings_result.data))
        
        # Build response
        investors_list = [
            inv for inv in investors_map.values()
            if len(inv["holdings"]) > 0
        ]
        
        # Sort by most recent total position value
        for inv in investors_list:
            inv["holdings"].sort(key=lambda x: x["quarter_date"])
        
        investors_list.sort(
            key=lambda x: x["holdings"][-1]["position_value"] if x["holdings"] else 0,
            reverse=True
        )
        
        return {
            "ticker": ticker,
            "investors": investors_list,
            "quarters": all_quarters,
            "earliest_date": all_quarters[0] if all_quarters else None,
            "latest_date": all_quarters[-1] if all_quarters else None,
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch super investor history for {symbol}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch super investor history: {str(e)}"
        )
 