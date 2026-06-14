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


def _resolve_db_user_id(auth_id: str) -> int:
    """Resolve Firebase auth_id (JWT sub) -> internal user_id. Raises 403 if not found."""
    from database import supabase
    from infrastructure.repositories.supabase_repository import SupabaseUserRepository
    user_repo = SupabaseUserRepository(client=supabase)
    user = user_repo.find_by_firebase_uid(auth_id)
    if not user:
        raise HTTPException(status_code=403, detail="User not found.")
    return user["user_id"]


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
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    from providers.edgar_provider import EdgarToolsProvider
    repo = ValuationRepository()
    arepo = AnalysisRepository(repo)
    yf = YFinanceProvider()
    dbeta = DefeatBetaProvider(
        yfinance_provider=yf,
        stockdex_provider=StockdexMacrotrendsProvider(),
        edgar_provider=EdgarToolsProvider(),
    )
    return CANSlimService(repo, arepo, dbeta, yf)


def _get_technical_service():
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from application.services.technical_analysis_service import TechnicalAnalysisService
    from providers.defeat_beta_provider import DefeatBetaProvider
    from providers.yfinance_provider import YFinanceProvider
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    from providers.edgar_provider import EdgarToolsProvider
    repo = ValuationRepository()
    yf = YFinanceProvider()
    dbeta = DefeatBetaProvider(
        yfinance_provider=yf,
        stockdex_provider=StockdexMacrotrendsProvider(),
        edgar_provider=EdgarToolsProvider(),
    )
    return TechnicalAnalysisService(repo, dbeta, yf)


def _get_stock_vs_index_service():
    from database import supabase
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from infrastructure.repositories.analysis_repository import AnalysisRepository
    from application.services.stock_index_comparison_service import (
        StockIndexComparisonService,
    )
    repo = ValuationRepository()
    arepo = AnalysisRepository(repo)
    return StockIndexComparisonService(arepo)


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


@router.get(
    "/{symbol}/stock-vs-index",
    summary=(
        "Stock vs Index outperformance analysis: quantitative metrics (alpha, beta, Sharpe), "
        "fundamental growth (revenue, EPS, FCF CAGR), and visual signals (relative strength, drawdown)."
    ),
)
@limiter.limit("30/minute")
async def get_stock_vs_index(
    request: Request,
    symbol: str,
    benchmark_symbols: str = Query("SPY", description="Comma-separated benchmark tickers (e.g. SPY,QQQ)"),
    years: int = Query(3, ge=1, le=10, description="Historical years to analyze"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        bsym_list = [s.strip().upper() for s in benchmark_symbols.split(",") if s.strip()]
        if not bsym_list:
            bsym_list = ["SPY"]
        service = _get_stock_vs_index_service()
        result = await service.evaluate_outperformance(sym, bsym_list, years)
        return result
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error(f"get_stock_vs_index failed for {symbol}: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Stock vs index analysis failed.",
        )


# ── MOAT Analysis ──────────────────────────────────────────────────────────────

def _get_moat_service():
    from database import supabase
    from infrastructure.repositories.moat_repository import MoatRepository
    from application.services.moat_wacc_service import MoatWaccService
    from application.services.edgar_filing_service import EdgarFilingService
    from application.services.moat_keyword_analyzer import MoatKeywordAnalyzer
    from application.services.moat_analysis_service import MoatAnalysisService
    repo = MoatRepository()
    wacc = MoatWaccService(repo)
    edgar = EdgarFilingService()
    analyzer = MoatKeywordAnalyzer()
    return MoatAnalysisService(repo, wacc, edgar, analyzer)


@router.get(
    "/{symbol}/moat",
    summary=(
        "Moat Analysis: ROIC durability, margin strength, return stability, "
        "and capital efficiency composite score."
    ),
)
@limiter.limit("30/minute")
async def get_moat_analysis(
    request: Request,
    symbol: str,
    force: bool = Query(False, description="Bypass cache and recompute"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_moat_service()
        result = await service.get_moat_analysis(sym, force=force)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_moat_analysis failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Moat analysis failed.",
        )


@router.get(
    "/{symbol}/moat/evidence",
    summary="EDGAR 10-K keyword evidence for moat analysis.",
)
@limiter.limit("20/minute")
async def get_moat_evidence(
    request: Request,
    symbol: str,
    refresh: bool = Query(False, description="Re-fetch from EDGAR and re-run keyword analysis"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_moat_service()
        if refresh:
            result = await service.run_text_analysis(sym)
        else:
            result = await service.get_moat_evidence(sym)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_moat_evidence failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Moat evidence retrieval failed.",
        )


@router.get(
    "/{symbol}/moat/ai",
    summary="Cached AI narrative for moat analysis.",
)
@limiter.limit("10/minute")
async def get_moat_ai_narrative(
    request: Request,
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_moat_service()
        result = await service.get_moat_ai_narrative(sym)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_moat_ai_narrative failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Moat AI narrative retrieval failed.",
        )


@router.post(
    "/{symbol}/moat/ai",
    summary="Generate a new AI moat narrative.",
)
@limiter.limit("5/minute")
async def generate_moat_ai_narrative(
    request: Request,
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_moat_service()
        result = await service.generate_moat_ai_narrative(sym)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("generate_moat_ai_narrative failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Moat AI narrative generation failed.",
        )


# ── Risk Assessment ─────────────────────────────────────────────────────────

def _get_risk_service():
    from database import supabase
    from infrastructure.repositories.moat_repository import MoatRepository
    from infrastructure.repositories.valuation_repository import ValuationRepository
    from infrastructure.repositories.risk_repository import RiskRepository
    from application.services.moat_wacc_service import MoatWaccService
    from application.services.moat_analysis_service import MoatAnalysisService
    from application.services.risk_assessment_service import RiskAssessmentService
    repo = ValuationRepository()
    risk_repo = RiskRepository(repo)
    moat_repo = MoatRepository()
    wacc = MoatWaccService(moat_repo)
    moat = MoatAnalysisService(moat_repo, wacc)
    return RiskAssessmentService(risk_repo, moat, wacc)


@router.get(
    "/{symbol}/risk-assessment",
    summary="Risk Assessment: composite downside risk across 5 layers.",
)
@limiter.limit("30/minute")
async def get_risk_assessment(
    request: Request,
    symbol: str,
    force: bool = Query(False, description="Bypass cache and recompute"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_risk_service()
        result = await service.get_risk_assessment(sym, force=force)
        return result.dict()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_risk_assessment failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Risk assessment failed.",
        )


@router.post(
    "/{symbol}/risk-assessment/ai",
    summary="Generate AI summary for risk assessment.",
)
@limiter.limit("5/minute")
async def generate_risk_ai_narrative(
    request: Request,
    symbol: str,
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_risk_service()
        assessment = await service.get_risk_assessment(sym, force=True)
        narrative = await service.generate_ai_narrative(sym, assessment)
        return {"narrative": narrative.narrative, "model": narrative.model}
    except Exception as exc:
        logger.error("generate_risk_ai failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(status_code=500, detail="AI narrative generation failed.")


@router.get(
    "/benchmarks",
    summary="Lists all active benchmarks for the Stock vs Index feature.",
)
@limiter.limit("60/minute")
async def list_benchmarks(
    request: Request,
    user=Depends(get_current_user_dep),
) -> list:
    try:
        service = _get_stock_vs_index_service()
        return await service.list_benchmarks()
    except Exception as exc:
        logger.error("list_benchmarks failed: %s", exc, exc_info=True)
        return []


# ── Fundamentals Tab ───────────────────────────────────────────────────────────

def _get_fundamentals_service():
    from infrastructure.repositories.fundamentals_repository import FundamentalsRepository
    from application.services.fundamentals_service import FundamentalsService
    repo = FundamentalsRepository()
    return FundamentalsService(repo)


@router.get(
    "/{symbol}/fundamentals",
    summary=(
        "Fundamentals Tab: Quality, Growth, Health, Valuation, and Narrative "
        "section scores with trend data and health metrics."
    ),
)
@limiter.limit("30/minute")
async def get_fundamentals(
    request: Request,
    symbol: str,
    frequency: str = Query("quarterly", regex="^(quarterly|annual)$"),
    user=Depends(get_current_user_dep),
) -> dict:
    try:
        sym = _normalize(symbol)
        service = _get_fundamentals_service()
        auth_id = user.get("sub") if isinstance(user, dict) else None
        user_id = str(_resolve_db_user_id(auth_id)) if auth_id else None
        result = await service.get_fundamentals(sym, user_id=user_id, frequency=frequency)
        return result.model_dump()
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as exc:
        logger.error("get_fundamentals failed for %s: %s", symbol, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Fundamentals analysis failed.",
        )
