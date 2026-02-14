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
from infrastructure.repositories.supabase_repository import SupabaseUserRepository
from application.services.valuation_service import ValuationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/valuations", tags=["Valuations"])

# Conservative ticker validation (uppercased)
_SYMBOL_RE = re.compile(r"^[A-Z0-9.\-]{1,10}$")


# ---------------------------------------------------------------------------
# Identity helpers (provider‑agnostic)
# ---------------------------------------------------------------------------

def _extract_auth_id(user_payload: dict) -> Optional[str]:
    """
    Extract provider identity from decoded auth payload.
    Supports Firebase (`uid`) and generic OIDC (`sub`).
    """
    if not isinstance(user_payload, dict):
        return None
    return (
        user_payload.get("uid")
        or user_payload.get("user_id")
        or user_payload.get("sub")
    )


def _resolve_internal_user_id(
    user_payload: dict,
    user_repo: SupabaseUserRepository,
) -> Optional[int]:
    """
    Map provider auth_id -> internal users.user_id (INTEGER).
    Returns None if mapping does not exist (audit row stays nullable).
    """
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
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid symbol format.",
        )
    return s


# =====================================================================
# POST /valuations/{symbol}/rule1
# =====================================================================
@router.post(
    "/{symbol}/rule1",
    response_model=Rule1Response,
    summary="Compute or return cached Phil Town Rule #1 valuation with diagnostics",
)
@limiter.limit("10/minute")
async def compute_rule1_valuation(
    request: Request,  # required by slowapi limiter
    symbol: str,
    overrides: Rule1RequestOverrides = Body(default_factory=Rule1RequestOverrides),
    force: bool = Query(
        default=False,
        description=(
            "If true, recompute even when cached result is fresh. "
            "Recommended for analysts or when overrides are intentionally used."
        ),
    ),
    user=Depends(get_current_user_dep),
    user_repo: SupabaseUserRepository = Depends(get_user_repository),
    valuation_service: ValuationService = Depends(get_valuation_service),
) -> Rule1Response:
    """
    API boundary for Rule #1 valuation.

    Responsibilities (by design):
    - Enforce auth + rate limits
    - Resolve provider identity -> internal users.user_id
    - Delegate computation to ValuationService
    - Return FE‑ready Rule1Response

    This endpoint does NOT:
    - Read the database directly
    - Compute valuation logic
    - Shape raw DB rows
    """
    try:
        sym = _normalize_symbol(symbol)

        internal_user_id = _resolve_internal_user_id(user, user_repo)

        return await valuation_service.compute_rule1_if_stale(
            symbol=sym,
            user_id=internal_user_id,
            overrides=overrides,
            force=force,
        )

    except HTTPException:
        # Pass through validation / explicit HTTP errors
        raise

    except ValueError as ve:
        # Typical: symbol not found in companies table
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve),
        ) from ve

    except Exception as e:
        # Stable FE contract: always return { detail: ... }
        logger.error("Rule #1 valuation failed for %s: %s", symbol, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valuation unavailable due to missing market data or financials.",
        ) from e


# =====================================================================
# GET /valuations/{symbol}/rule1/history
# =====================================================================
@router.get(
    "/{symbol}/rule1/history",
    summary="Recent Rule #1 valuation runs. Returns empty list when no history exists.",
)
@limiter.limit("30/minute")
async def get_rule1_history(
    request: Request,  # required by slowapi limiter
    symbol: str,
    user=Depends(get_current_user_dep),
    valuation_service: ValuationService = Depends(get_valuation_service),
):
    """
    Returns prior Rule #1 valuation runs in FE‑ready shape:
    {
      "symbol": "AAPL",
      "items": [ ... ]
    }

    History must NEVER break the Analysis page.
    """
    try:
        sym = _normalize_symbol(symbol)

        # History is intentionally read-only and repo-backed
        items = await valuation_service.repo.get_rule1_history(sym)

        return {
            "symbol": sym,
            "items": items or [],
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Failed to fetch Rule #1 history for %s: %s",
            symbol,
            e,
            exc_info=True,
        )
        # Fail-safe: history endpoint must never error the UI
        return {
            "symbol": (symbol or "").strip().upper(),
            "items": [],
        }