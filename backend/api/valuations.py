# backend/api/valuations.py
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi import Body

from dependencies import get_current_user_dep, limiter, get_user_repository
from domain.models.valuation_rule1 import Rule1RequestOverrides, Rule1Response
from infrastructure.repositories.valuation_repository import ValuationRepository
from infrastructure.repositories.supabase_repository import SupabaseUserRepository
from application.services.recompute_guard import RecomputeGuard
from application.services.valuation_service import ValuationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/valuations", tags=["Valuations"])


# ---------------------------------------------------------------------------
# Identity helpers (provider-agnostic)
# ---------------------------------------------------------------------------

def _extract_auth_id(user_payload: dict) -> Optional[str]:
    """
    Extract the provider identity (auth_id) from the decoded auth payload without
    binding to a specific provider. For Firebase, `uid` is canonical; some SDKs may
    also alias it as `user_id`. OIDC-compatible tokens may use `sub`.
    """
    if not isinstance(user_payload, dict):
        return None
    return (
        user_payload.get("uid")
        or user_payload.get("user_id")  # some SDKs alias uid as user_id
        or user_payload.get("sub")      # OIDC fallback
    )


def _resolve_internal_user_id(
    user_payload: dict,
    user_repo: SupabaseUserRepository,
) -> Optional[int]:
    """
    Map provider identity (auth_id) -> internal numeric users.user_id using Supabase.
    If the mapping is not found, return None (audit row will be nullable). This keeps
    the endpoint provider-agnostic and mirrors the watchlist flow.
    """
    auth_id = _extract_auth_id(user_payload)
    if not auth_id:
        # No provider identity available (should not happen when auth is enforced)
        return None

    row = user_repo.find_by_firebase_uid(auth_id)
    # Row shape: {'user_id': <int>} or None
    try:
        return int(row["user_id"]) if row and row.get("user_id") is not None else None
    except Exception:
        return None


# =====================================================================
# POST /valuations/{symbol}/rule1
# Compute or return cached Rule #1 valuation
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
) -> Rule1Response:
    """
    Computes or returns cached **Rule #1 valuation** plus diagnostics.

    Behavior:
    - Uses freshness gate unless `force=true`.
    - Includes diagnostics (flags, growth inputs, PE, MOS breakdown).
    - Persists valuation_runs audit trail (with internal users.user_id when available).
    - Upserts into intrinsic_value_analysis table.

    The endpoint remains auth-provider-agnostic:
    - `get_current_user_dep` provides provider identity (e.g., Firebase UID).
    - We resolve it to the internal numeric users.user_id *here* at the API boundary,
      mirroring the watchlist flow and keeping service/repo layers decoupled from auth.
    """
    try:
        # Resolve internal user_id (INTEGER) from provider auth_id (string)
        internal_user_id = _resolve_internal_user_id(user, user_repo)

        repo = ValuationRepository()
        guard = RecomputeGuard(repo)
        service = ValuationService(repo, guard)

        # Cached vs recompute (service decides unless force=True)
        result = await service.compute_rule1_if_stale(
            symbol=symbol,
            user_id=internal_user_id,  # <- INTERNAL numeric ID or None
            overrides=overrides,
            force=force,
        )
        return result

    except ValueError as ve:
        # Typical: symbol not found in companies table
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve),
        ) from ve

    except Exception as e:
        # Common causes:
        # - Missing current market data
        # - Missing financial statements
        # - Provider/transient failure
        logger.error("Rule #1 valuation failed for %s: %s", symbol, e, exc_info=True)

        # Return 422 so the frontend can show a friendly message and keep the page stable.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Valuation unavailable due to missing market data or financials.",
        ) from e


# =====================================================================
# GET /valuations/{symbol}/rule1/history
# Returns valuation run history (or empty list)
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
):
    """
    Returns prior Rule #1 valuation runs in FE-ready shape.

    Response shape:
    {
      "symbol": "AAPL",
      "items": [
        {
          "runAt": "...",
          "stickerPrice": 123.45,
          "mosPrice": 98.76,
          "futurePrice": 150.00,
          "growth": 0.12,
          "futurePE": 18,
          "score": 72,
          "category": "Good"
        }
      ]
    }
    """
    try:
        repo = ValuationRepository()
        items = await repo.get_rule1_history(symbol.upper())

        return {
            "symbol": symbol.upper(),
            "items": items or [],
        }

    except Exception as e:
        logger.error(
            "Failed to fetch Rule #1 history for %s: %s",
            symbol,
            e,
            exc_info=True,
        )
        # Fail-safe: history must never break the Analysis page
        return {
            "symbol": symbol.upper(),
            "items": [],
        }