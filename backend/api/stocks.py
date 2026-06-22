"""
Stock data endpoints — price history, news, and related data.

Endpoints:
  GET /stocks/{symbol}/price-history?days=7|30  → OHLCV time-series
  GET /stocks/{symbol}/news?limit=10             → Recent news articles
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from shared.time_utils import now_utc
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from dependencies import get_current_user_dep, limiter
from database import supabase

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Stocks"])

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _normalize(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid symbol format.",
        )
    return s


# ── Schemas ───────────────────────────────────────────────────────────────

class PriceHistoryPoint(BaseModel):
    date: str
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None


class PriceHistoryResponse(BaseModel):
    success: bool
    symbol: str
    days: int
    data: List[PriceHistoryPoint]
    error: Optional[str] = None


class NewsArticle(BaseModel):
    uuid: Optional[str] = None
    title: str
    summary: Optional[str] = None
    publisher: str
    published_at: str
    article_type: str = "STORY"
    url: Optional[str] = None
    related_symbols: List[str] = []


class NewsResponse(BaseModel):
    success: bool
    symbol: str
    articles: List[NewsArticle]
    source: str
    error: Optional[str] = None


# ── Price History ─────────────────────────────────────────────────────────

@router.get("/stocks/{symbol}/price-history", status_code=200)
@limiter.limit("30/minute")
async def get_price_history(
    request: Request,
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    user: dict = Depends(get_current_user_dep),
) -> PriceHistoryResponse:
    """
    Get daily OHLCV price history for a stock symbol.

    Queries the `price_history` table which is populated by the
    market_data_scheduler. Falls back to yfinance if DB has no data.
    """
    sym = _normalize(symbol)

    try:
        end = now_utc().date()
        start = end - timedelta(days=days)

        # Resolve company_id
        company = (
            supabase.table("companies")
            .select("company_id")
            .eq("ticker_symbol", sym)
            .limit(1)
            .execute()
        )
        if not company.data:
            return PriceHistoryResponse(
                success=False, symbol=sym, days=days, data=[],
                error="Symbol not found",
            )

        company_id = company.data[0]["company_id"]

        # Query price_history
        rows = (
            supabase.table("price_history")
            .select("price_date, open_price, high_price, low_price, close_price, volume")
            .eq("company_id", company_id)
            .gte("price_date", start.isoformat())
            .lte("price_date", end.isoformat())
            .order("price_date", desc=False)
            .execute()
        )

        if rows.data:
            data = [
                PriceHistoryPoint(
                    date=r["price_date"],
                    open=r.get("open_price"),
                    high=r.get("high_price"),
                    low=r.get("low_price"),
                    close=r.get("close_price"),
                    volume=r.get("volume"),
                )
                for r in rows.data
            ]
            return PriceHistoryResponse(success=True, symbol=sym, days=days, data=data)

        # Fallback to yfinance
        return await _fallback_price_history(sym, days)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Price history failed for {sym}: {e}")
        return PriceHistoryResponse(
            success=False, symbol=sym, days=days, data=[],
            error="Failed to fetch price history",
        )


async def _fallback_price_history(symbol: str, days: int) -> PriceHistoryResponse:
    """Fallback: fetch price history from yfinance."""
    try:
        import yfinance as yf
        tkr = yf.Ticker(symbol)
        hist = tkr.history(period=f"{days}d", auto_adjust=True)
        if hist is None or hist.empty:
            return PriceHistoryResponse(
                success=False, symbol=symbol, days=days, data=[],
                error="No price data available",
            )

        data = []
        for idx, row in hist.iterrows():
            dt = idx if isinstance(idx, str) else idx.isoformat()[:10]
            data.append(PriceHistoryPoint(
                date=dt,
                open=float(row.get("Open", 0)) if pd.notna(row.get("Open")) else None,
                high=float(row.get("High", 0)) if pd.notna(row.get("High")) else None,
                low=float(row.get("Low", 0)) if pd.notna(row.get("Low")) else None,
                close=float(row.get("Close", 0)) if pd.notna(row.get("Close")) else None,
                volume=int(row.get("Volume", 0)) if pd.notna(row.get("Volume")) else None,
            ))

        return PriceHistoryResponse(success=True, symbol=symbol, days=days, data=data)

    except Exception as e:
        logger.error(f"YFinance price history fallback failed for {symbol}: {e}")
        return PriceHistoryResponse(
            success=False, symbol=symbol, days=days, data=[],
            error="No price data available from any source",
        )


# ── News ──────────────────────────────────────────────────────────────────

def _get_news_from_defeatbeta(symbol: str, limit: int) -> Optional[List[NewsArticle]]:
    """Fetch news from DefeatBeta provider (primary)."""
    try:
        from defeatbeta_api.data.ticker import Ticker
        ticker = Ticker(symbol)
        news_obj = ticker.news()
        df = news_obj.get_news_list()
        if df is None or df.empty:
            return None

        articles = []
        for _, row in df.iterrows():
            if len(articles) >= limit:
                break
            articles.append(NewsArticle(
                uuid=str(row.get("uuid", "")),
                title=str(row.get("title", "")),
                publisher=str(row.get("publisher", "Unknown")),
                published_at=str(row.get("report_date", "")),
                article_type=str(row.get("type", "STORY")),
                url=str(row.get("link", "")),
                related_symbols=(
                    [s.strip() for s in str(row.get("related_symbols", "")).split(",") if s.strip()]
                ),
            ))

        return articles

    except Exception as e:
        logger.debug(f"DefeatBeta news failed for {symbol}: {e}")
        return None


def _get_news_from_yfinance(symbol: str, limit: int) -> Optional[List[NewsArticle]]:
    """Fetch news from YFinance (fallback)."""
    try:
        import yfinance as yf
        tkr = yf.Ticker(symbol)
        raw = getattr(tkr, "news", None)
        if not raw:
            return None

        articles = []
        for item in raw[:limit]:
            articles.append(NewsArticle(
                title=str(item.get("title", "")),
                summary=str(item.get("summary", "")),
                publisher=str(item.get("publisher", "Yahoo Finance")),
                published_at=str(item.get("providerPublishTime", "")),
                article_type=str(item.get("type", "STORY")),
                url=str(item.get("link", "")),
                related_symbols=item.get("relatedTickers", []),
            ))

        return articles

    except Exception as e:
        logger.debug(f"YFinance news failed for {symbol}: {e}")
        return None


@router.get("/stocks/{symbol}/news", status_code=200)
@limiter.limit("20/minute")
async def get_stock_news(
    request: Request,
    symbol: str,
    limit: int = Query(10, ge=1, le=50, description="Number of articles"),
    user: dict = Depends(get_current_user_dep),
) -> NewsResponse:
    """
    Get recent news for a stock symbol.

    Primary source: DefeatBeta (structured historical news with full articles)
    Fallback: YFinance (live headlines from Yahoo Finance)

    Returns up to `limit` articles sorted by recency.
    """
    sym = _normalize(symbol)

    try:
        # Primary: DefeatBeta
        articles = _get_news_from_defeatbeta(sym, limit)
        source = "defeatbeta"

        # Fallback: YFinance
        if not articles:
            articles = _get_news_from_yfinance(sym, limit)
            source = "yfinance"

        if not articles:
            return NewsResponse(
                success=False, symbol=sym, articles=[],
                source="none",
                error="No news available from any provider",
            )

        return NewsResponse(success=True, symbol=sym, articles=articles, source=source)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"News fetch failed for {sym}: {e}")
        return NewsResponse(
            success=False, symbol=sym, articles=[], source="none",
            error="Failed to fetch news",
        )
