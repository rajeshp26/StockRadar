# domain/models/valuation_rule1.py
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# -----------------------------
# Request (overrides)
# -----------------------------

class Rule1RequestOverrides(BaseModel):
    """
    Optional user/admin overrides for Rule #1 inputs.
    All values are optional; when omitted, defaults/DB-resolved inputs are used.
    """
    discountRate: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    horizonYears: Optional[int] = Field(default=None, ge=1, le=50)
    marginOfSafety: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # Direct numeric overrides (advanced):
    forceGrowth: Optional[float] = Field(default=None)        # decimal; e.g., 0.12 for 12%
    forceFuturePE: Optional[float] = Field(default=None, ge=0)


# -----------------------------
# Diagnostics
# -----------------------------

Severity = Literal["critical", "high", "medium", "low", "info"]


class DiagnosticFlag(BaseModel):
    """
    One structured diagnostic about suitability, input quality, or assumptions.
    """
    code: str
    severity: Severity
    message: str
    evidence: Optional[Dict[str, Any]] = None
    recommendation: Optional[str] = None


class Applicability(BaseModel):
    """
    Suitability assessment for Rule #1 on this company, with a roll-up score.
    """
    score: int = Field(ge=0, le=100)
    category: Literal["Good", "Caution", "Poor"]
    flags: List[DiagnosticFlag] = Field(default_factory=list)


class DataQuality(BaseModel):
    """
    Freshness and explainability bundle for FE transparency.
    - freshnessDays: arbitrary key->value map; includes items like:
        - trailingEPS: int days since snapshot
        - epsForecast: int days since report
        - lastComputedAt: ISO8601 string (attached by service)
    - fallbacksUsed: True if any fallback data source/path was used
    - inputDecisions: traces how inputs were chosen (source, clamping, etc.)
    """
    freshnessDays: Dict[str, Any] = Field(default_factory=dict)
    fallbacksUsed: bool = False
    inputDecisions: Dict[str, Any] = Field(default_factory=dict)


# -----------------------------
# Response (valuation)
# -----------------------------

class Rule1Valuation(BaseModel):
    """
    Rule #1 valuation fields (sticker price & MOS).
    Field names intentionally camelCase for FE parity.
    """
    symbol: str
    companyId: int
    currency: str

    # Inputs (final values used)
    eps0: float
    growth: float
    futurePE: float

    # Derived
    futureEPS: float
    futurePrice: float
    discountRate: float
    horizonYears: int
    mos: float
    stickerPrice: float
    mosPrice: float


class Rule1Response(BaseModel):
    """
    Full FE-ready payload: valuation + applicability + data quality bundle.
    """
    valuation: Rule1Valuation
    applicability: Applicability
    dataQuality: DataQuality

    class Config:
        # Pydantic v1 compatibility (harmless on v2)
        orm_mode = True
        allow_population_by_field_name = True