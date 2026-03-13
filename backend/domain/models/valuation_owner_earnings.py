# domain/models/valuation_owner_earnings.py
from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator

# Reuse shared primitives from Rule #1 (keeps FE behaviour consistent)
from domain.models.valuation_rule1 import Applicability, DataQuality  # noqa: E402


class OwnerEarningsRequestOverrides(BaseModel):
    """
    Optional user/analyst overrides for Owner Earnings inputs.

    DESIGN RULE (no assumptions):
    - Missing values are resolved from DB defaults / financial statements.
    - Service owns normalization and clamping. This model only validates types.
    - maintenanceCapexRatio: fraction of total capex treated as maintenance capex.
      Default (service-side) = 1.0 (all capex = maintenance, conservative Buffett stance).
    """

    # Forecast controls
    forecastYears: Optional[int] = Field(default=None, ge=1, le=20)

    # Growth rate applied to Owner Earnings stream
    oeGrowthRate: Optional[float] = Field(
        default=None,
        description="Annual growth rate for Owner Earnings (accepts percent or fraction).",
    )

    # Discount rate (hurdle rate / required return on equity)
    discountRate: Optional[float] = Field(
        default=None,
        description="Discount rate. Accepts percent or fraction.",
    )

    # Terminal value (perpetuity growth)
    terminalGrowthRate: Optional[float] = Field(
        default=None,
        description="Perpetual growth rate for terminal value. Accepts percent or fraction.",
    )

    # Capex adjustment
    maintenanceCapexRatio: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of total capex treated as maintenance capex (0.0–1.0). Default 1.0.",
    )

    # Working capital change adjustment (optional)
    includeWorkingCapitalChange: Optional[bool] = Field(
        default=None,
        description="Whether to include change_in_working_capital in OE calculation.",
    )

    # Equity bridge overrides
    sharesOutstanding: Optional[float] = Field(default=None, gt=0)
    netDebt: Optional[float] = Field(
        default=None,
        description="Net debt (total debt − cash). May be negative (net cash position).",
    )

    # Meta
    analystName: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("oeGrowthRate", "discountRate", "terminalGrowthRate", mode="before")
    @classmethod
    def _reject_nan(cls, v: Any) -> Any:
        if v is None:
            return None
        try:
            f = float(v)
        except Exception as e:
            raise ValueError("Value must be a number.") from e
        if f != f:  # NaN check
            raise ValueError("Value cannot be NaN.")
        return f


class OwnerEarningsValuation(BaseModel):
    """
    FE-ready Owner Earnings valuation payload.
    camelCase keys aligned with frontend convention.
    """

    symbol: str
    companyId: int
    currency: str

    # Forecast parameters used
    forecastYears: int
    discountRateUsed: float
    oeGrowthRateUsed: Optional[float] = None
    terminalGrowthRateUsed: Optional[float] = None
    maintenanceCapexRatioUsed: Optional[float] = None

    # Base OE decomposition (transparency)
    baseOe: Optional[float] = None
    baseOeFiscalYear: Optional[int] = None
    netIncomeUsed: Optional[float] = None
    daUsed: Optional[float] = None               # Depreciation & Amortization
    capexUsed: Optional[float] = None            # Capex (sign-normalized to negative)
    wcChangeUsed: Optional[float] = None         # Working Capital Change (optional)

    # Forecast stream
    forecastOe: List[float] = Field(default_factory=list)
    pvOe: List[float] = Field(default_factory=list)
    discountFactors: Optional[List[float]] = None
    totalPvOe: float = 0.0

    # Terminal value
    terminalValue: Optional[float] = None
    pvTerminalValue: Optional[float] = None
    oeNPlus1: Optional[float] = None             # OE_{n+1} used in perpetuity formula

    # Equity bridge
    enterpriseValue: Optional[float] = None
    netDebtUsed: Optional[float] = None
    equityValue: Optional[float] = None
    sharesOutstanding: Optional[float] = None
    intrinsicValuePerShare: Optional[float] = None

    # Read-time market comparison
    currentPrice: Optional[float] = None
    upsideDownsidePct: Optional[float] = None    # fraction (e.g. 0.25 = 25% upside)

    # Sensitivity grid (discount_rate × terminal_growth_rate)
    sensitivityScenarios: Optional["OeSensitivityGrid"] = None


class OeSensitivityGrid(BaseModel):
    """
    OE sensitivity: rows = discountRates, cols = terminalGrowthRates.
    Mirrors DcfSensitivityGrid structure for FE reuse.
    """

    discountRates: List[float]
    terminalGrowthRates: List[float]
    intrinsicValuePerShareMatrix: List[List[Optional[float]]]
    currency: Optional[str] = None

    model_config = {"extra": "ignore"}


class OwnerEarningsResponse(BaseModel):
    valuation: OwnerEarningsValuation
    applicability: Applicability
    dataQuality: DataQuality