# domain/models/valuation_ddm.py
from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field


DdmVariant = Literal["gordon", "two_stage"]
DdmMethod = Literal["ddm_gordon", "ddm_two_stage"]


class DdmRequestOverrides(BaseModel):
    # Dividend inputs
    currentDps: Optional[float] = None  # D0 annual DPS override

    # CAPM-ish inputs (optional overrides)
    requiredReturn: Optional[float] = None
    beta: Optional[float] = None
    riskFreeRate: Optional[float] = None
    equityRiskPremium: Optional[float] = None

    # Growth inputs
    dividendGrowthRate: Optional[float] = None  # g override (fraction)

    # Two-stage inputs
    highGrowthYears: Optional[int] = None
    highGrowthRate: Optional[float] = None
    stableGrowthRate: Optional[float] = None

    # Meta
    analystName: Optional[str] = None
    notes: Optional[str] = None


class DdmValuation(BaseModel):
    # FE-ready, camelCase
    symbol: str
    companyId: int
    currency: str
    method: DdmVariant

    currentDps: float
    nextYearDps: float
    dividendGrowthRate: float
    requiredReturn: float

    intrinsicValue: float

    # Two-stage fields
    highGrowthYears: Optional[int] = None
    highGrowthRate: Optional[float] = None
    stableGrowthRate: Optional[float] = None
    pvStage1: Optional[float] = None
    pvTerminal: Optional[float] = None

    # Market comparison (read-time)
    currentPrice: Optional[float] = None
    upsideDownsidePct: Optional[float] = None  # fraction (NOT percent), consistent with existing ddm draft


class DdmResponse(BaseModel):
    valuation: DdmValuation

    # Reuse existing primitives from Rule1 model (keeps FE behavior consistent)
    applicability: Any
    dataQuality: Any