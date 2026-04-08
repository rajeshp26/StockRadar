# backend/api/analysis.py
"""
Analysis endpoints — derived, non-valuation analytics.
  GET /analysis/{symbol}/dividend  → 4-tab dividend report
Future: /financial-health, /moat, /technical
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status

from dependencies import get_current_user_dep, limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["Analysis"])

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _normalize(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid symbol format.",
        )
    return s


def _get_dividend_service():
    from database import supabase
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from application.services.dividend_analysis_service import DividendAnalysisService
    repo = ValuationRepository()
    return DividendAnalysisService(repo)


@router.get(
    "/{symbol}/dividend",
    summary=(
        "Full dividend analysis: overview KPIs, safety scorecard, "
        "growth momentum, and yield positioning."
    ),
)
@limiter.limit("30/minute")
async def get_dividend_analysis(
    request: Request,
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym     = _normalize(symbol)
        service = _get_dividend_service()
        return await service.get_dividend_analysis(sym)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_dividend_analysis failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Dividend analysis failed.",
        )