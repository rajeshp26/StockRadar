# domain/models/valuation_ddm.py
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

DdmVariant = Literal["gordon", "two_stage"]
DdmMethod = Literal["ddm_gordon", "ddm_two_stage"]


class DdmRequestOverrides(BaseModel):
    # Dividend inputs
    currentDps: float | None = None  # D0 annual DPS override

    # CAPM-ish inputs (optional overrides)
    requiredReturn: float | None = None
    beta: float | None = None
    riskFreeRate: float | None = None
    equityRiskPremium: float | None = None

    # Growth inputs
    dividendGrowthRate: float | None = None  # g override (fraction)

    # Two-stage inputs
    highGrowthYears: int | None = None
    highGrowthRate: float | None = None
    stableGrowthRate: float | None = None

    # Meta
    analystName: str | None = None
    notes: str | None = None


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
    highGrowthYears: int | None = None
    highGrowthRate: float | None = None
    stableGrowthRate: float | None = None
    pvStage1: float | None = None
    pvTerminal: float | None = None

    # Market comparison (read-time)
    currentPrice: float | None = None
    upsideDownsidePct: float | None = None  # fraction (NOT percent), consistent with existing ddm draft


class DdmResponse(BaseModel):
    valuation: DdmValuation

    # Reuse existing primitives from Rule1 model (keeps FE behavior consistent)
    applicability: Any
    dataQuality: Any
