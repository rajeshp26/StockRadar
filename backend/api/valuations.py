# api/valuations.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi import Body, Request
import logging

from dependencies import get_current_user_dep, limiter
from domain.models.valuation_rule1 import Rule1RequestOverrides, Rule1Response
from infrastructure.repositories.valuation_repository import ValuationRepository
from application.services.recompute_guard import RecomputeGuard
from application.services.valuation_service import ValuationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/valuations", tags=["Valuations"])


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
    force: bool = Query(
        default=False,
        description=(
            "If true, recompute even when cached result is fresh. "
            "Recommended for analysts or when overrides are intentionally used."
        ),
    ),
    user=Depends(get_current_user_dep),
) -> Rule1Response:
    """
    Returns **Rule #1 (sticker & MOS) valuation** and a **diagnostics bundle**.

    Behavior:
    - **Cached vs Recompute**: Uses freshness gate (latest dependencies vs last valuation).  
      Set `?force=true` to recompute regardless.
    - **Diagnostics**: Always included—suitability score, flags, freshness details, and input decision trace.
    - **Audit**: Every recompute persists an entry in `valuation_runs`; latest snapshot upserts `intrinsic_value_analysis`.

    Request body supports optional overrides:
    ```json
    {
      "discountRate": 0.15,
      "horizonYears": 10,
      "marginOfSafety": 0.5,
      "forceGrowth": null,
      "forceFuturePE": null
    }
    ```
    """
    try:
        repo = ValuationRepository()
        guard = RecomputeGuard(repo)
        service = ValuationService(repo, guard)

        # The service will decide cached vs recompute unless force=True
        result = await service.compute_rule1_if_stale(
            symbol=symbol,
            user_id=user.get("user_id"),
            overrides=overrides,
            force=force,
        )
        return result

    except ValueError as ve:
        # e.g., symbol not found in companies
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(ve),
        ) from ve

    except Exception as e:
        logger.error("Rule #1 valuation failed for %s: %s", symbol, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute Rule #1 valuation.",
        ) from e
