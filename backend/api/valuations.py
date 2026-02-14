# backend/api/valuations.py
from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status

from dependencies import (
    get_current_user_dep,
    get_user_repository,
    get_valuation_service,
    limiter,
)
from domain.models.valuation_rule1 import Rule1RequestOverrides, Rule1Response
from domain.models.valuation_ddm import DdmRequestOverrides, DdmResponse
from infrastructure.repositories.supabase_repository import SupabaseUserRepository
from application.services.valuation_service import ValuationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/valuations", tags=["Valuations"])

_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


def _extract_auth_id(user_payload: dict) -> Optional[str]:
    if not isinstance(user_payload, dict):
        return None
    return user_payload.get("uid") or user_payload.get("user_id") or user_payload.get("sub")


def _resolve_internal_user_id(user_payload: dict, user_repo: SupabaseUserRepository) -> Optional[int]:
    auth_id = _extract_auth_id(user_payload)
    if not auth_id:
        return None
    row = user_repo.find_by_firebase_uid(auth_id)
    try:
        return int(row["user_id"]) if row and row.get("user_id") is not None else None
    except Exception:
        return None


def _normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid symbol format.")
    return s


@router.post(
    "/{symbol}/rule1",
    response_model=Rule1Response,
    summary="Compute or return cached Phil Town Rule #1 valuation with diagnostics",
)
@limiter.limit("10/minute")
async def compute_rule1_valuation(
    request: Request,
    symbol: str,
    overrides: Rule1RequestOverrides = Body(default_factory=Rule1RequestOverrides),
    force: bool = Query(default=False, description="If true, recompute even when cached result is fresh."),
    user=Depends(get_current_user_dep),
    user_repo: SupabaseUserRepository = Depends(get_user_repository),
    valuation_service: ValuationService = Depends(get_valuation_service),
) -> Rule1Response:
    try:
        sym = _normalize_symbol(symbol)
        internal_user_id = _resolve_internal_user_id(user, user_repo)
        return await valuation_service.compute_rule1_if_stale(sym, internal_user_id, overrides, force=force)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve)) from ve
    except Exception as e:
        logger.error("Rule #1 valuation failed for %s: %s", symbol, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valuation unavailable due to missing market data or financials.",
        ) from e


@router.post(
    "/{symbol}/ddm",
    response_model=DdmResponse,
    summary="Compute or return cached Dividend Discount Model (DDM) valuation (Gordon or Two-Stage)",
)
@limiter.limit("10/minute")
async def compute_ddm_valuation(
    request: Request,
    symbol: str,
    variant: str = Query(default="gordon", description="DDM variant: gordon | two_stage"),
    overrides: DdmRequestOverrides = Body(default_factory=DdmRequestOverrides),
    force: bool = Query(default=False, description="If true, recompute even when cached result is fresh."),
    user=Depends(get_current_user_dep),
    user_repo: SupabaseUserRepository = Depends(get_user_repository),
    valuation_service: ValuationService = Depends(get_valuation_service),
) -> DdmResponse:
    try:
        sym = _normalize_symbol(symbol)
        v = (variant or "gordon").strip().lower()
        if v not in {"gordon", "two_stage"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid variant. Use gordon|two_stage.")
        internal_user_id = _resolve_internal_user_id(user, user_repo)
        return await valuation_service.compute_ddm_if_stale(sym, internal_user_id, variant=v, overrides=overrides, force=force)
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve)) from ve
    except Exception as e:
        logger.error("DDM valuation failed for %s: %s", symbol, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="DDM valuation unavailable due to missing dividend or financial data.",
        ) from e

@router.get(
    "/{symbol}/ddm/history",
    summary="Recent DDM valuation runs (method-specific). Returns empty list when none exist.",
)
@limiter.limit("30/minute")
async def get_ddm_history(
    request: Request,
    symbol: str,
    variant: str = Query(default="gordon", description="gordon | two_stage"),
    user=Depends(get_current_user_dep),
    valuation_service: ValuationService = Depends(get_valuation_service),
):
    try:
        sym = _normalize_symbol(symbol)
        v = (variant or "gordon").strip().lower()
        if v not in {"gordon", "two_stage"}:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid variant. Use gordon|two_stage.")

        method = "ddm_gordon" if v == "gordon" else "ddm_two_stage"
        items = await valuation_service.repo.get_ddm_history(sym, method=method)

        return {"symbol": sym, "items": items or []}
    except Exception:
        # fail-safe: never break UI
        return {"symbol": (symbol or "").strip().upper(), "items": []}