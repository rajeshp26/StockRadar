# backend/api/analysis.py
"""
Analysis endpoints — derived, non-valuation analytics.
  GET /analysis/{symbol}/dividend  → 4-tab dividend report
Future: /financial-health, /moat, /technical
"""
from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status, Query

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

# ── New dependency factories (add after _get_dividend_service()) ─────────────
 
def _get_magic_formula_service():
    from database import supabase
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from infrastructure.repositories.analysis_repository import AnalysisRepository
    from application.services.magic_formula_service import MagicFormulaService
    repo = ValuationRepository()
    arepo = AnalysisRepository(repo)
    return MagicFormulaService(repo, arepo)
 
 
def _get_canslim_service():
    from database import supabase
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from infrastructure.repositories.analysis_repository import AnalysisRepository
    from application.services.canslim_service import CANSlimService
    from providers.defeat_beta_provider import DefeatBetaProvider
    from providers.yfinance_provider import YFinanceProvider
    repo = ValuationRepository()
    arepo = AnalysisRepository(repo)
    yf = YFinanceProvider()
    dbeta = DefeatBetaProvider(yfinance_provider=yf)
    return CANSlimService(repo, arepo, dbeta, yf)
 
 
def _get_technical_service():
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from application.services.technical_analysis_service import TechnicalAnalysisService
    from providers.defeat_beta_provider import DefeatBetaProvider
    from providers.yfinance_provider import YFinanceProvider
    repo = ValuationRepository()
    yf = YFinanceProvider()
    dbeta = DefeatBetaProvider(yfinance_provider=yf)
    return TechnicalAnalysisService(repo, dbeta, yf)

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

# ── New route handlers (add after get_dividend_analysis) ─────────────────────
 
@router.get(
    "/{symbol}/magic-formula",
    summary=(
        "Greenblatt Magic Formula: Earnings Yield (EBIT/EV) and "
        "Return on Capital (EBIT/(NWC+NFA)), with industry context."
    ),
)
@limiter.limit("30/minute")
async def get_magic_formula(
    request: Request,
    symbol: str,
    force: bool = Query(False, description="Bypass cache and recompute"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_magic_formula_service()
        result = await service.get_magic_formula(sym, force=force)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_magic_formula failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Magic Formula analysis failed.",
        )
 
 
@router.get(
    "/{symbol}/canslim",
    summary=(
        "CANSlim analysis (O'Neil): seven-letter scorecard with composite score. "
        "L and M use live benchmark data."
    ),
)
@limiter.limit("20/minute")
async def get_canslim(
    request: Request,
    symbol: str,
    force: bool = Query(False, description="Bypass cache and recompute"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_canslim_service()
        result = await service.get_canslim(sym, force=force)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_canslim failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="CANSlim analysis failed.",
        )
 
 
@router.get(
    "/{symbol}/technical/murphy",
    summary=(
        "Murphy Style Technical Analysis: trend (50/200 SMA), momentum (MACD, RSI), "
        "volume (OBV), support/resistance (pivots), oscillators (Bollinger, Stochastic). "
        "Stateless — computed on demand from live daily OHLCV."
    ),
)
@limiter.limit("30/minute")
async def get_murphy_technical(
    request: Request,
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_technical_service()
        result = await service.get_murphy_analysis(sym)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_murphy_technical failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Murphy technical analysis failed.",
        )