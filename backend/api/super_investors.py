# -*- coding: utf-8 -*-
"""
Super Investors API

Two route groups:
  /analysis/{symbol}/super-investors          — per-ticker (existing, preserved)
  /analysis/{symbol}/super-investors/history  — per-ticker (existing, preserved)

  /super-investors/overview                   — cross-investor summary
  /super-investors/top-stocks                 — ranked by breadth
  /super-investors/overlap                    — stocks held by N+ investors
  /super-investors/activity                   — chronological Q-o-Q feed
  /super-investors/investors                  — list of all tracked investors
  /super-investors/investors/{tag}            — individual portfolio deep-dive
  /super-investors/sectors                    — aggregate sector exposure
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from database import supabase

logger = logging.getLogger(__name__)

# Two prefixes under one module; main.py already does:
#   app.include_router(super_investors.router)
# so we expose a single router with both prefixes via two sub-routers merged.
router = APIRouter(tags=["super-investors"])

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _classify_conviction(avg_portfolio_weight: float) -> str:
    if avg_portfolio_weight >= 0.05:
        return "very_high"
    elif avg_portfolio_weight >= 0.02:
        return "high"
    elif avg_portfolio_weight >= 0.005:
        return "moderate"
    return "low"


def _get_latest_quarter() -> str:
    """Return the most recent quarter_end_date present in institutional_holdings."""
    result = (
        supabase.table("institutional_holdings")
        .select("quarter_end_date")
        .order("quarter_end_date", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["quarter_end_date"]
    return ""


def _prev_quarter(quarter_date: str) -> str:
    """Return the quarter_end_date that is one quarter before the given date."""
    from datetime import date
    d = datetime.strptime(quarter_date, "%Y-%m-%d").date()
    # Step back ~92 days (one quarter)
    prev = d - timedelta(days=92)
    # Snap to quarter-end
    if prev.month <= 3:
        return str(date(prev.year, 3, 31))
    elif prev.month <= 6:
        return str(date(prev.year, 6, 30))
    elif prev.month <= 9:
        return str(date(prev.year, 9, 30))
    return str(date(prev.year, 12, 31))


# ─────────────────────────────────────────────────────────────────────────────
# Existing per-ticker endpoints (preserved exactly)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/analysis/{symbol}/super-investors")
async def get_super_investors(symbol: str) -> Dict[str, Any]:
    """
    Get institutional ownership data for a stock.
    Checks DB first (last 30 days); falls back to live SEC fetch.
    """
    try:
        ticker = symbol.upper()
        db_data = _get_holdings_from_db(ticker)
        if db_data and db_data["overlap_count"] > 0:
            return db_data

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
        logger.error("Failed to fetch super investors for %s: %s", symbol, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch super investor data: {e}")


@router.get("/analysis/{symbol}/super-investors/history")
async def get_super_investors_history(symbol: str) -> Dict[str, Any]:
    """Get historical quarterly holdings for super investors in this stock."""
    try:
        ticker = symbol.upper()

        company_result = supabase.table("companies").select("company_id").eq(
            "ticker_symbol", ticker
        ).execute()
        if not company_result.data:
            return {"ticker": ticker, "investors": [], "quarters": [],
                    "earliest_date": None, "latest_date": None,
                    "message": "Stock not found in database."}

        company_id = company_result.data[0]["company_id"]
        five_years_ago = (datetime.now() - timedelta(days=5 * 365)).date()
        cutoff_date = max(five_years_ago, datetime(2021, 1, 1).date())

        holdings_result = (
            supabase.table("institutional_holdings")
            .select(
                "holding_id, investor_id, quarter_end_date, shares_held, "
                "position_value, portfolio_weight, shares_change, "
                "shares_change_pct, change_type"
            )
            .eq("company_id", company_id)
            .gte("quarter_end_date", str(cutoff_date))
            .order("quarter_end_date")
            .execute()
        )
        if not holdings_result.data:
            return {"ticker": ticker, "investors": [], "quarters": [],
                    "earliest_date": None, "latest_date": None,
                    "message": "No historical holdings data available."}

        investor_ids = list({h["investor_id"] for h in holdings_result.data})
        investors_result = (
            supabase.table("institutional_investors")
            .select("investor_id, investor_name, firm_name, investor_tag, investment_style")
            .in_("investor_id", investor_ids)
            .eq("is_super_investor", True)
            .execute()
        )
        if not investors_result.data:
            return {"ticker": ticker, "investors": [], "quarters": [],
                    "earliest_date": None, "latest_date": None,
                    "message": "No super investor data found."}

        investors_map: Dict[int, Dict] = {
            inv["investor_id"]: {
                "investor_id": inv["investor_id"],
                "investor_name": inv["investor_name"],
                "firm": inv["firm_name"],
                "tag": inv["investor_tag"],
                "style": inv["investment_style"],
                "holdings": [],
            }
            for inv in investors_result.data
        }

        for h in holdings_result.data:
            iid = h["investor_id"]
            if iid not in investors_map:
                continue
            investors_map[iid]["holdings"].append({
                "quarter_date": h["quarter_end_date"],
                "shares_held": h["shares_held"],
                "position_value": h["position_value"],
                "portfolio_weight": h["portfolio_weight"],
                "change_shares": h.get("shares_change"),
                "change_pct": h.get("shares_change_pct"),
                "change_type": h.get("change_type", "held"),
            })

        all_quarters = sorted({h["quarter_end_date"] for h in holdings_result.data})
        investors_list = [v for v in investors_map.values() if v["holdings"]]
        for inv in investors_list:
            inv["holdings"].sort(key=lambda x: x["quarter_date"])
        investors_list.sort(
            key=lambda x: x["holdings"][-1]["position_value"] if x["holdings"] else 0,
            reverse=True,
        )

        return {
            "ticker": ticker,
            "investors": investors_list,
            "quarters": all_quarters,
            "earliest_date": all_quarters[0] if all_quarters else None,
            "latest_date": all_quarters[-1] if all_quarters else None,
        }

    except Exception as e:
        logger.error("Failed to fetch history for %s: %s", symbol, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch super investor history: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Overview
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/overview")
async def get_overview() -> Dict[str, Any]:
    """
    Summary metrics + most-added and most-exited stocks for the latest quarter.

    Response:
    {
        "latest_quarter": "2024-12-31",
        "investors_tracked": 24,
        "stocks_held": 284,
        "new_positions": 12,
        "full_exits": 8,
        "most_added": [
            {"ticker": "AAPL", "company_name": "Apple Inc", "investors_added": 4,
             "investor_tags": ["BUFFETT", "ACKMAN", ...]},
            ...
        ],
        "most_exited": [...same shape...]
    }
    """
    try:
        latest_quarter = _get_latest_quarter()
        if not latest_quarter:
            return _empty_overview()

        prev_quarter = _prev_quarter(latest_quarter)

        # Total investors tracked
        inv_count_result = (
            supabase.table("institutional_investors")
            .select("investor_id", count="exact")
            .eq("is_super_investor", True)
            .eq("is_active", True)
            .execute()
        )
        investors_tracked = inv_count_result.count or 0

        # Current quarter holdings (distinct companies)
        curr_result = (
            supabase.table("institutional_holdings")
            .select("company_id, investor_id, change_type")
            .eq("quarter_end_date", latest_quarter)
            .execute()
        )
        curr_rows = curr_result.data or []
        stocks_held = len({r["company_id"] for r in curr_rows})
        new_positions = [r for r in curr_rows if r.get("change_type") == "new"]
        full_exits_curr = [r for r in curr_rows if r.get("change_type") == "sold"]

        # Previous quarter company_ids — to detect entries that now have "sold"
        # (rows present in prev but absent in curr with change_type=sold)
        prev_result = (
            supabase.table("institutional_holdings")
            .select("company_id, investor_id")
            .eq("quarter_end_date", prev_quarter)
            .execute()
        )
        prev_company_ids = {r["company_id"] for r in (prev_result.data or [])}
        curr_company_ids = {r["company_id"] for r in curr_rows}

        # Most added: companies with the most "new" or "increased" investors this quarter
        added_rows = [r for r in curr_rows if r.get("change_type") in ("new", "increased")]
        added_by_company: Dict[int, List[int]] = {}
        for r in added_rows:
            added_by_company.setdefault(r["company_id"], []).append(r["investor_id"])

        exited_rows = [r for r in curr_rows if r.get("change_type") in ("sold", "decreased")]
        exited_by_company: Dict[int, List[int]] = {}
        for r in exited_rows:
            exited_by_company.setdefault(r["company_id"], []).append(r["investor_id"])

        # Enrich with company name + investor tags
        all_company_ids = list(
            set(list(added_by_company.keys()) + list(exited_by_company.keys()))
        )
        companies_map = _fetch_companies_map(all_company_ids)

        all_investor_ids = list({r["investor_id"] for r in curr_rows})
        investors_map = _fetch_investors_map(all_investor_ids)

        def _build_list(by_company: Dict[int, List[int]], limit: int = 10) -> List[Dict]:
            items = []
            for cid, iids in by_company.items():
                co = companies_map.get(cid, {})
                tags = [investors_map.get(iid, {}).get("investor_tag", "") for iid in iids]
                items.append({
                    "ticker": co.get("ticker_symbol", ""),
                    "company_name": co.get("company_name", ""),
                    "sector": co.get("sector", ""),
                    "investor_count": len(iids),
                    "investor_tags": [t for t in tags if t],
                })
            items.sort(key=lambda x: x["investor_count"], reverse=True)
            return items[:limit]

        return {
            "latest_quarter": latest_quarter,
            "prev_quarter": prev_quarter,
            "investors_tracked": investors_tracked,
            "stocks_held": stocks_held,
            "new_positions": len(new_positions),
            "full_exits": len(full_exits_curr),
            "most_added": _build_list(added_by_company),
            "most_exited": _build_list(exited_by_company),
        }

    except Exception as e:
        logger.error("overview failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Top Stocks
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/top-stocks")
async def get_top_stocks(
    sector: Optional[str] = Query(None, description="Filter by sector"),
    style: Optional[str] = Query(None, description="Filter by investor style: value | growth | activist | lt_compounder | sector"),
    min_investors: int = Query(1, ge=1, description="Minimum number of investors holding"),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    All stocks held by tracked super investors, ranked by breadth (investor count).

    Response:
    {
        "quarter": "2024-12-31",
        "total_stocks": 284,
        "stocks": [
            {
                "rank": 1,
                "ticker": "AAPL",
                "company_name": "Apple Inc",
                "sector": "Technology",
                "investor_count": 8,
                "investor_breadth_pct": 0.67,   # 8 of 12 tracked
                "total_position_value": 182000000000,
                "avg_portfolio_weight": 0.044,
                "conviction_level": "high",
                "investor_tags": ["BUFFETT", "ACKMAN", ...]
            },
            ...
        ]
    }
    """
    try:
        latest_quarter = _get_latest_quarter()
        if not latest_quarter:
            return {"quarter": None, "total_stocks": 0, "stocks": []}

        # Build investor filter if style requested
        filtered_investor_ids: Optional[List[int]] = None
        if style:
            style_map = {
                "value": "Value",
                "growth": "Growth",
                "activist": "Activist",
                "lt_compounder": "Long-Term Compounder",
                "sector": "Sector",
            }
            style_label = style_map.get(style.lower(), style)
            inv_result = (
                supabase.table("institutional_investors")
                .select("investor_id")
                .eq("investment_style", style_label)
                .eq("is_super_investor", True)
                .execute()
            )
            filtered_investor_ids = [r["investor_id"] for r in (inv_result.data or [])]
            if not filtered_investor_ids:
                return {"quarter": latest_quarter, "total_stocks": 0, "stocks": []}

        # Fetch all holdings for latest quarter
        q = (
            supabase.table("institutional_holdings")
            .select(
                "company_id, investor_id, position_value, portfolio_weight"
            )
            .eq("quarter_end_date", latest_quarter)
        )
        if filtered_investor_ids:
            q = q.in_("investor_id", filtered_investor_ids)
        holdings_result = q.execute()
        rows = holdings_result.data or []

        # Aggregate by company
        by_company: Dict[int, Dict] = {}
        for r in rows:
            cid = r["company_id"]
            if cid not in by_company:
                by_company[cid] = {
                    "investor_ids": [],
                    "total_value": 0.0,
                    "weights": [],
                }
            by_company[cid]["investor_ids"].append(r["investor_id"])
            by_company[cid]["total_value"] += float(r.get("position_value") or 0)
            w = r.get("portfolio_weight")
            if w is not None:
                by_company[cid]["weights"].append(float(w))

        # Filter by min_investors
        by_company = {
            cid: v for cid, v in by_company.items()
            if len(v["investor_ids"]) >= min_investors
        }

        # Enrich with company metadata
        company_ids = list(by_company.keys())
        companies_q = (
            supabase.table("companies")
            .select("company_id, ticker_symbol, company_name, sector")
            .in_("company_id", company_ids)
        )
        if sector:
            companies_q = companies_q.ilike("sector", f"%{sector}%")
        companies_result = companies_q.execute()
        companies_map = {c["company_id"]: c for c in (companies_result.data or [])}

        investors_map = _fetch_investors_map(
            list({iid for v in by_company.values() for iid in v["investor_ids"]})
        )

        total_investors = len(
            filtered_investor_ids
            if filtered_investor_ids
            else _fetch_all_super_investor_ids()
        )

        stocks = []
        for cid, agg in by_company.items():
            co = companies_map.get(cid)
            if not co:
                continue  # sector filter excluded it
            inv_count = len(agg["investor_ids"])
            avg_weight = (
                sum(agg["weights"]) / len(agg["weights"]) if agg["weights"] else 0.0
            )
            tags = [
                investors_map.get(iid, {}).get("investor_tag", "")
                for iid in agg["investor_ids"]
            ]
            stocks.append({
                "ticker": co["ticker_symbol"],
                "company_name": co["company_name"],
                "sector": co.get("sector", ""),
                "investor_count": inv_count,
                "investor_breadth_pct": round(inv_count / total_investors, 4) if total_investors else 0,
                "total_position_value": round(agg["total_value"]),
                "avg_portfolio_weight": round(avg_weight, 4),
                "conviction_level": _classify_conviction(avg_weight),
                "investor_tags": [t for t in tags if t],
            })

        stocks.sort(key=lambda x: x["investor_count"], reverse=True)
        total_stocks = len(stocks)
        for i, s in enumerate(stocks[:limit], 1):
            s["rank"] = i

        return {
            "quarter": latest_quarter,
            "total_stocks": total_stocks,
            "stocks": stocks[:limit],
        }

    except Exception as e:
        logger.error("top-stocks failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Conviction Overlap
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/overlap")
async def get_overlap(
    min_investors: int = Query(3, ge=2, description="Minimum number of investors"),
    sector: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> Dict[str, Any]:
    """
    Stocks held by min_investors or more super investors (consensus picks).

    Response:
    {
        "quarter": "2024-12-31",
        "stocks": [
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc",
                "sector": "Technology",
                "investor_count": 8,
                "investors": [
                    {"tag": "BUFFETT", "investor_name": "Warren Buffett",
                     "style": "Long-Term Compounder", "portfolio_weight": 0.44,
                     "change_type": "held"},
                    ...
                ],
                "avg_portfolio_weight": 0.044,
                "conviction_level": "high"
            },
            ...
        ]
    }
    """
    try:
        latest_quarter = _get_latest_quarter()
        if not latest_quarter:
            return {"quarter": None, "stocks": []}

        holdings_result = (
            supabase.table("institutional_holdings")
            .select(
                "company_id, investor_id, portfolio_weight, change_type"
            )
            .eq("quarter_end_date", latest_quarter)
            .execute()
        )
        rows = holdings_result.data or []

        # Group by company
        by_company: Dict[int, List[Dict]] = {}
        for r in rows:
            by_company.setdefault(r["company_id"], []).append(r)

        # Filter to min_investors
        by_company = {
            cid: v for cid, v in by_company.items()
            if len(v) >= min_investors
        }

        company_ids = list(by_company.keys())
        if not company_ids:
            return {"quarter": latest_quarter, "stocks": []}

        companies_q = (
            supabase.table("companies")
            .select("company_id, ticker_symbol, company_name, sector")
            .in_("company_id", company_ids)
        )
        if sector:
            companies_q = companies_q.ilike("sector", f"%{sector}%")
        companies_result = companies_q.execute()
        companies_map = {c["company_id"]: c for c in (companies_result.data or [])}

        all_investor_ids = list({r["investor_id"] for v in by_company.values() for r in v})
        investors_map = _fetch_investors_map(all_investor_ids)

        stocks = []
        for cid, holdings in by_company.items():
            co = companies_map.get(cid)
            if not co:
                continue
            weights = [float(h.get("portfolio_weight") or 0) for h in holdings]
            avg_w = sum(weights) / len(weights) if weights else 0.0
            investors_detail = []
            for h in sorted(holdings, key=lambda x: x.get("portfolio_weight") or 0, reverse=True):
                inv = investors_map.get(h["investor_id"], {})
                investors_detail.append({
                    "tag": inv.get("investor_tag", ""),
                    "investor_name": inv.get("investor_name", ""),
                    "style": inv.get("investment_style", ""),
                    "portfolio_weight": float(h.get("portfolio_weight") or 0),
                    "change_type": h.get("change_type", "held"),
                })
            stocks.append({
                "ticker": co["ticker_symbol"],
                "company_name": co["company_name"],
                "sector": co.get("sector", ""),
                "investor_count": len(holdings),
                "investors": investors_detail,
                "avg_portfolio_weight": round(avg_w, 4),
                "conviction_level": _classify_conviction(avg_w),
            })

        stocks.sort(key=lambda x: x["investor_count"], reverse=True)
        return {"quarter": latest_quarter, "stocks": stocks[:limit]}

    except Exception as e:
        logger.error("overlap failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Activity Feed
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/activity")
async def get_activity(
    change_type: Optional[str] = Query(
        None,
        description="Filter: new | increased | decreased | sold | held"
    ),
    investor_tag: Optional[str] = Query(None, description="Filter by investor tag e.g. BUFFETT"),
    quarters: int = Query(4, ge=1, le=20, description="Number of recent quarters to include"),
    limit: int = Query(100, ge=1, le=500),
) -> Dict[str, Any]:
    """
    Chronological 13F change log across all investors.

    Response:
    {
        "quarters_shown": ["2024-12-31", "2024-09-30", ...],
        "activity": [
            {
                "quarter_end_date": "2024-12-31",
                "investor_tag": "BUFFETT",
                "investor_name": "Warren Buffett",
                "style": "Long-Term Compounder",
                "ticker": "OXY",
                "company_name": "Occidental Petroleum",
                "sector": "Energy",
                "change_type": "increased",
                "shares_held": 264_159_628,
                "shares_change": 12_000_000,
                "shares_change_pct": 4.76,
                "position_value": 14_200_000_000,
                "portfolio_weight": 0.044
            },
            ...
        ]
    }
    """
    try:
        # Determine which quarters to include
        all_quarters_result = (
            supabase.table("institutional_holdings")
            .select("quarter_end_date")
            .order("quarter_end_date", desc=True)
            .execute()
        )
        all_quarter_dates = sorted(
            {r["quarter_end_date"] for r in (all_quarters_result.data or [])},
            reverse=True,
        )
        quarters_to_show = all_quarter_dates[:quarters]
        if not quarters_to_show:
            return {"quarters_shown": [], "activity": []}

        oldest_quarter = quarters_to_show[-1]

        # Build investor filter
        investor_filter_ids: Optional[List[int]] = None
        if investor_tag:
            inv_result = (
                supabase.table("institutional_investors")
                .select("investor_id")
                .ilike("investor_tag", investor_tag)
                .execute()
            )
            investor_filter_ids = [r["investor_id"] for r in (inv_result.data or [])]
            if not investor_filter_ids:
                return {"quarters_shown": quarters_to_show, "activity": []}

        # Fetch holdings for the requested window
        q = (
            supabase.table("institutional_holdings")
            .select(
                "investor_id, company_id, quarter_end_date, shares_held, "
                "shares_change, shares_change_pct, change_type, "
                "position_value, portfolio_weight"
            )
            .gte("quarter_end_date", oldest_quarter)
            .order("quarter_end_date", desc=True)
            .order("position_value", desc=True)
        )
        if investor_filter_ids:
            q = q.in_("investor_id", investor_filter_ids)
        if change_type:
            q = q.eq("change_type", change_type)

        holdings_result = q.limit(limit * 3).execute()  # over-fetch before join filter
        rows = holdings_result.data or []

        # Enrich
        investor_ids = list({r["investor_id"] for r in rows})
        company_ids = list({r["company_id"] for r in rows})
        investors_map = _fetch_investors_map(investor_ids)
        companies_map = _fetch_companies_map(company_ids)

        activity = []
        for r in rows:
            inv = investors_map.get(r["investor_id"], {})
            co = companies_map.get(r["company_id"], {})
            if not inv or not co:
                continue
            activity.append({
                "quarter_end_date": r["quarter_end_date"],
                "investor_tag": inv.get("investor_tag", ""),
                "investor_name": inv.get("investor_name", ""),
                "style": inv.get("investment_style", ""),
                "ticker": co.get("ticker_symbol", ""),
                "company_name": co.get("company_name", ""),
                "sector": co.get("sector", ""),
                "change_type": r.get("change_type", "held"),
                "shares_held": r.get("shares_held"),
                "shares_change": r.get("shares_change"),
                "shares_change_pct": r.get("shares_change_pct"),
                "position_value": r.get("position_value"),
                "portfolio_weight": r.get("portfolio_weight"),
            })

        return {
            "quarters_shown": quarters_to_show,
            "activity": activity[:limit],
        }

    except Exception as e:
        logger.error("activity failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Investors list
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/investors")
async def get_investors_list() -> Dict[str, Any]:
    """
    List all tracked super investors with their latest portfolio summary.

    Response:
    {
        "investors": [
            {
                "investor_id": 1,
                "investor_name": "Warren Buffett",
                "firm_name": "Berkshire Hathaway Inc",
                "tag": "BUFFETT",
                "style": "Long-Term Compounder",
                "last_filed_period": "2024-12-31",
                "portfolio_value": 319_000_000_000,
                "positions_count": 44,
                "top_holding_ticker": "AAPL",
                "top_holding_weight": 0.44
            },
            ...
        ]
    }
    """
    try:
        latest_quarter = _get_latest_quarter()

        investors_result = (
            supabase.table("institutional_investors")
            .select(
                "investor_id, investor_name, firm_name, investor_tag, "
                "investment_style, last_filed_period"
            )
            .eq("is_super_investor", True)
            .eq("is_active", True)
            .execute()
        )
        investors = investors_result.data or []
        if not investors:
            return {"investors": []}

        investor_ids = [i["investor_id"] for i in investors]

        # Latest quarter holdings for each investor
        holdings_result = (
            supabase.table("institutional_holdings")
            .select(
                "investor_id, company_id, position_value, portfolio_weight"
            )
            .eq("quarter_end_date", latest_quarter)
            .in_("investor_id", investor_ids)
            .execute()
        )
        holdings_rows = holdings_result.data or []

        # Aggregate per investor
        inv_agg: Dict[int, Dict] = {}
        for h in holdings_rows:
            iid = h["investor_id"]
            if iid not in inv_agg:
                inv_agg[iid] = {"total_value": 0.0, "positions": [], "top": None}
            val = float(h.get("position_value") or 0)
            w = float(h.get("portfolio_weight") or 0)
            inv_agg[iid]["total_value"] += val
            inv_agg[iid]["positions"].append({
                "company_id": h["company_id"],
                "weight": w,
                "value": val,
            })

        # Top holding per investor
        top_company_ids = set()
        for agg in inv_agg.values():
            if agg["positions"]:
                agg["top"] = max(agg["positions"], key=lambda x: x["weight"])
                top_company_ids.add(agg["top"]["company_id"])

        companies_map = _fetch_companies_map(list(top_company_ids))

        result = []
        for inv in investors:
            iid = inv["investor_id"]
            agg = inv_agg.get(iid, {"total_value": 0.0, "positions": [], "top": None})
            top = agg.get("top")
            top_ticker = ""
            top_weight = 0.0
            if top:
                co = companies_map.get(top["company_id"], {})
                top_ticker = co.get("ticker_symbol", "")
                top_weight = top["weight"]

            result.append({
                "investor_id": iid,
                "investor_name": inv["investor_name"],
                "firm_name": inv["firm_name"],
                "tag": inv["investor_tag"],
                "style": inv["investment_style"],
                "last_filed_period": inv.get("last_filed_period"),
                "portfolio_value": round(agg["total_value"]),
                "positions_count": len(agg["positions"]),
                "top_holding_ticker": top_ticker,
                "top_holding_weight": round(top_weight, 4),
            })

        result.sort(key=lambda x: x["portfolio_value"], reverse=True)
        return {"investors": result}

    except Exception as e:
        logger.error("investors list failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Individual Investor Deep-Dive
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/investors/{tag}")
async def get_investor_portfolio(
    tag: str,
    quarters: int = Query(8, ge=1, le=20, description="Quarters of history to return"),
) -> Dict[str, Any]:
    """
    Full portfolio for a single investor including Q-o-Q history.

    Response:
    {
        "investor": {
            "investor_name": "Warren Buffett",
            "firm_name": "Berkshire Hathaway Inc",
            "tag": "BUFFETT",
            "style": "Long-Term Compounder",
            "last_filed_period": "2024-12-31"
        },
        "latest_quarter": "2024-12-31",
        "portfolio_value": 319_000_000_000,
        "positions_count": 44,
        "sector_breakdown": [
            {"sector": "Technology", "weight": 0.50, "value": 160_000_000_000},
            ...
        ],
        "holdings": [
            {
                "rank": 1,
                "ticker": "AAPL",
                "company_name": "Apple Inc",
                "sector": "Technology",
                "shares_held": 905_000_000,
                "position_value": 141_000_000_000,
                "portfolio_weight": 0.44,
                "change_type": "held",
                "shares_change": 0,
                "shares_change_pct": 0.0,
                "history": [
                    {"quarter": "2024-09-30", "shares_held": 905_000_000,
                     "portfolio_weight": 0.46, "change_type": "decreased"},
                    ...
                ]
            },
            ...
        ]
    }
    """
    try:
        # Look up investor by tag (case-insensitive)
        inv_result = (
            supabase.table("institutional_investors")
            .select(
                "investor_id, investor_name, firm_name, investor_tag, "
                "investment_style, last_filed_period"
            )
            .ilike("investor_tag", tag)
            .eq("is_super_investor", True)
            .execute()
        )
        if not inv_result.data:
            raise HTTPException(status_code=404, detail=f"Investor '{tag}' not found")

        investor = inv_result.data[0]
        investor_id = investor["investor_id"]

        # Determine quarters to fetch
        all_quarters_result = (
            supabase.table("institutional_holdings")
            .select("quarter_end_date")
            .eq("investor_id", investor_id)
            .order("quarter_end_date", desc=True)
            .execute()
        )
        available_quarters = sorted(
            {r["quarter_end_date"] for r in (all_quarters_result.data or [])},
            reverse=True,
        )
        quarters_to_fetch = available_quarters[:quarters]
        if not quarters_to_fetch:
            return {
                "investor": _investor_shape(investor),
                "latest_quarter": None,
                "portfolio_value": 0,
                "positions_count": 0,
                "sector_breakdown": [],
                "holdings": [],
            }

        oldest = quarters_to_fetch[-1]
        latest = quarters_to_fetch[0]

        # Fetch all holdings across the history window
        holdings_result = (
            supabase.table("institutional_holdings")
            .select(
                "company_id, quarter_end_date, shares_held, position_value, "
                "portfolio_weight, shares_change, shares_change_pct, change_type"
            )
            .eq("investor_id", investor_id)
            .gte("quarter_end_date", oldest)
            .order("quarter_end_date", desc=True)
            .execute()
        )
        all_holdings = holdings_result.data or []

        # Enrich companies
        company_ids = list({h["company_id"] for h in all_holdings})
        companies_map = _fetch_companies_map(company_ids)

        # Partition into latest quarter (current positions) vs history
        latest_holdings = [h for h in all_holdings if h["quarter_end_date"] == latest]
        portfolio_value = sum(float(h.get("position_value") or 0) for h in latest_holdings)

        # Build sector breakdown from latest quarter
        sector_totals: Dict[str, float] = {}
        for h in latest_holdings:
            co = companies_map.get(h["company_id"], {})
            sector = co.get("sector") or "Other"
            sector_totals[sector] = sector_totals.get(sector, 0.0) + float(
                h.get("position_value") or 0
            )
        sector_breakdown = [
            {
                "sector": s,
                "value": round(v),
                "weight": round(v / portfolio_value, 4) if portfolio_value else 0,
            }
            for s, v in sorted(sector_totals.items(), key=lambda x: x[1], reverse=True)
        ]

        # Group history by company
        history_by_company: Dict[int, List[Dict]] = {}
        for h in all_holdings:
            cid = h["company_id"]
            history_by_company.setdefault(cid, []).append(h)

        # Build holdings list (current positions + embedded history)
        holdings_out = []
        for h in sorted(latest_holdings, key=lambda x: x.get("portfolio_weight") or 0, reverse=True):
            cid = h["company_id"]
            co = companies_map.get(cid, {})
            hist = sorted(
                [
                    hh for hh in history_by_company.get(cid, [])
                    if hh["quarter_end_date"] != latest
                ],
                key=lambda x: x["quarter_end_date"],
                reverse=True,
            )
            holdings_out.append({
                "ticker": co.get("ticker_symbol", ""),
                "company_name": co.get("company_name", ""),
                "sector": co.get("sector", ""),
                "shares_held": h.get("shares_held"),
                "position_value": h.get("position_value"),
                "portfolio_weight": h.get("portfolio_weight"),
                "change_type": h.get("change_type", "held"),
                "shares_change": h.get("shares_change"),
                "shares_change_pct": h.get("shares_change_pct"),
                "history": [
                    {
                        "quarter": hh["quarter_end_date"],
                        "shares_held": hh["shares_held"],
                        "portfolio_weight": hh["portfolio_weight"],
                        "change_type": hh.get("change_type", "held"),
                        "shares_change": hh.get("shares_change"),
                        "shares_change_pct": hh.get("shares_change_pct"),
                    }
                    for hh in hist
                ],
            })

        for i, h in enumerate(holdings_out, 1):
            h["rank"] = i

        return {
            "investor": _investor_shape(investor),
            "latest_quarter": latest,
            "portfolio_value": round(portfolio_value),
            "positions_count": len(latest_holdings),
            "sector_breakdown": sector_breakdown,
            "holdings": holdings_out,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("investor portfolio failed for tag=%s: %s", tag, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Standalone page — Sector Breakdown
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/super-investors/sectors")
async def get_sector_breakdown(
    style: Optional[str] = Query(None, description="Filter by investor style"),
) -> Dict[str, Any]:
    """
    Aggregate sector exposure across all super investors for the latest quarter.

    Response:
    {
        "quarter": "2024-12-31",
        "sectors": [
            {
                "sector": "Technology",
                "total_value": 420_000_000_000,
                "avg_weight": 0.31,
                "stock_count": 48,
                "investor_count": 12,
                "top_stocks": [
                    {"ticker": "AAPL", "total_value": 182_000_000_000},
                    ...
                ]
            },
            ...
        ]
    }
    """
    try:
        latest_quarter = _get_latest_quarter()
        if not latest_quarter:
            return {"quarter": None, "sectors": []}

        filtered_investor_ids: Optional[List[int]] = None
        if style:
            style_map = {
                "value": "Value", "growth": "Growth", "activist": "Activist",
                "lt_compounder": "Long-Term Compounder", "sector": "Sector",
            }
            style_label = style_map.get(style.lower(), style)
            inv_result = (
                supabase.table("institutional_investors")
                .select("investor_id")
                .eq("investment_style", style_label)
                .eq("is_super_investor", True)
                .execute()
            )
            filtered_investor_ids = [r["investor_id"] for r in (inv_result.data or [])]

        q = (
            supabase.table("institutional_holdings")
            .select("company_id, investor_id, position_value, portfolio_weight")
            .eq("quarter_end_date", latest_quarter)
        )
        if filtered_investor_ids:
            q = q.in_("investor_id", filtered_investor_ids)
        holdings_result = q.execute()
        rows = holdings_result.data or []

        company_ids = list({r["company_id"] for r in rows})
        companies_map = _fetch_companies_map(company_ids)

        # Aggregate by sector
        by_sector: Dict[str, Dict] = {}
        for r in rows:
            co = companies_map.get(r["company_id"], {})
            sector = co.get("sector") or "Other"
            if sector not in by_sector:
                by_sector[sector] = {
                    "total_value": 0.0,
                    "weights": [],
                    "company_ids": set(),
                    "investor_ids": set(),
                    "by_company": {},
                }
            val = float(r.get("position_value") or 0)
            w = r.get("portfolio_weight")
            by_sector[sector]["total_value"] += val
            by_sector[sector]["company_ids"].add(r["company_id"])
            by_sector[sector]["investor_ids"].add(r["investor_id"])
            if w is not None:
                by_sector[sector]["weights"].append(float(w))
            cid = r["company_id"]
            by_sector[sector]["by_company"][cid] = (
                by_sector[sector]["by_company"].get(cid, 0.0) + val
            )

        # Build top stocks per sector (top 5 by value)
        sectors_out = []
        for sector, agg in by_sector.items():
            top = sorted(agg["by_company"].items(), key=lambda x: x[1], reverse=True)[:5]
            top_stocks = [
                {
                    "ticker": companies_map.get(cid, {}).get("ticker_symbol", ""),
                    "total_value": round(v),
                }
                for cid, v in top
            ]
            avg_w = sum(agg["weights"]) / len(agg["weights"]) if agg["weights"] else 0.0
            sectors_out.append({
                "sector": sector,
                "total_value": round(agg["total_value"]),
                "avg_weight": round(avg_w, 4),
                "stock_count": len(agg["company_ids"]),
                "investor_count": len(agg["investor_ids"]),
                "top_stocks": top_stocks,
            })

        sectors_out.sort(key=lambda x: x["total_value"], reverse=True)
        return {"quarter": latest_quarter, "sectors": sectors_out}

    except Exception as e:
        logger.error("sectors failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Shared DB helpers (kept private to this module)
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_companies_map(company_ids: List[int]) -> Dict[int, Dict]:
    if not company_ids:
        return {}
    result = (
        supabase.table("companies")
        .select("company_id, ticker_symbol, company_name, sector")
        .in_("company_id", company_ids)
        .execute()
    )
    return {c["company_id"]: c for c in (result.data or [])}


def _fetch_investors_map(investor_ids: List[int]) -> Dict[int, Dict]:
    if not investor_ids:
        return {}
    result = (
        supabase.table("institutional_investors")
        .select("investor_id, investor_name, firm_name, investor_tag, investment_style")
        .in_("investor_id", investor_ids)
        .execute()
    )
    return {i["investor_id"]: i for i in (result.data or [])}


def _fetch_all_super_investor_ids() -> List[int]:
    result = (
        supabase.table("institutional_investors")
        .select("investor_id")
        .eq("is_super_investor", True)
        .eq("is_active", True)
        .execute()
    )
    return [r["investor_id"] for r in (result.data or [])]


def _investor_shape(inv: Dict) -> Dict:
    return {
        "investor_name": inv["investor_name"],
        "firm_name": inv["firm_name"],
        "tag": inv["investor_tag"],
        "style": inv["investment_style"],
        "last_filed_period": inv.get("last_filed_period"),
    }


def _empty_overview() -> Dict[str, Any]:
    return {
        "latest_quarter": None,
        "prev_quarter": None,
        "investors_tracked": 0,
        "stocks_held": 0,
        "new_positions": 0,
        "full_exits": 0,
        "most_added": [],
        "most_exited": [],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Per-ticker DB helper (preserved from original)
# ─────────────────────────────────────────────────────────────────────────────

def _get_holdings_from_db(ticker: str) -> Dict[str, Any] | None:
    try:
        company_result = supabase.table("companies").select("company_id").eq(
            "ticker_symbol", ticker
        ).execute()
        if not company_result.data:
            return None
        company_id = company_result.data[0]["company_id"]

        cutoff_date = (datetime.now() - timedelta(days=30)).date().isoformat()
        holdings_result = (
            supabase.table("institutional_holdings")
            .select(
                "holding_id, shares_held, position_value, portfolio_weight, "
                "shares_change, shares_change_pct, change_type, "
                "quarter_end_date, filing_date, investor_id"
            )
            .eq("company_id", company_id)
            .gte("filing_date", cutoff_date)
            .execute()
        )
        if not holdings_result.data:
            return None

        investor_ids = [h["investor_id"] for h in holdings_result.data]
        investors_result = (
            supabase.table("institutional_investors")
            .select("investor_id, investor_name, firm_name, investor_tag, investment_style")
            .in_("investor_id", investor_ids)
            .execute()
        )
        investors_map = {i["investor_id"]: i for i in (investors_result.data or [])}

        holders = []
        for h in holdings_result.data:
            inv = investors_map.get(h.get("investor_id"), {})
            if not inv:
                continue
            holders.append({
                "investor_name": inv.get("investor_name", ""),
                "firm": inv.get("firm_name", ""),
                "tag": inv.get("investor_tag", ""),
                "style": inv.get("investment_style", ""),
                "shares": h.get("shares_held", 0),
                "value": h.get("position_value", 0),
                "portfolio_weight": h.get("portfolio_weight", 0),
                "change_pct": h.get("shares_change_pct") or 0,
                "change_type": h.get("change_type", "held"),
                "quarter_date": str(h.get("quarter_end_date", "")),
            })

        if not holders:
            return None

        avg_weight = sum(h["portfolio_weight"] for h in holders) / len(holders)
        return {
            "ticker": ticker,
            "holders": holders,
            "overlap_count": len(holders),
            "avg_portfolio_weight": round(avg_weight, 4),
            "conviction_level": _classify_conviction(avg_weight),
            "recent_activity": {
                "buyers": [h for h in holders if h["change_type"] in ("new", "increased")][:5],
                "sellers": [h for h in holders if h["change_type"] in ("decreased", "sold")][:5],
            },
            "source": "database",
        }

    except Exception as e:
        logger.error("_get_holdings_from_db failed for %s: %s", ticker, e)
        return None