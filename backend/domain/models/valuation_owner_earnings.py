# domain/models/valuation_owner_earnings.py
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

# Reuse shared primitives from Rule #1 (keeps FE behaviour consistent)
from domain.models.valuation_rule1 import Applicability, DataQuality


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
    forecastYears: int | None = Field(default=None, ge=1, le=20)

    # Growth rate applied to Owner Earnings stream
    oeGrowthRate: float | None = Field(
        default=None,
        description="Annual growth rate for Owner Earnings (accepts percent or fraction).",
    )

    # Discount rate (hurdle rate / required return on equity)
    discountRate: float | None = Field(
        default=None,
        description="Discount rate. Accepts percent or fraction.",
    )

    # Terminal value (perpetuity growth)
    terminalGrowthRate: float | None = Field(
        default=None,
        description="Perpetual growth rate for terminal value. Accepts percent or fraction.",
    )

    # Capex adjustment
    maintenanceCapexRatio: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Fraction of total capex treated as maintenance capex (0.0–1.0). Default 1.0.",
    )

    # Working capital change adjustment (optional)
    includeWorkingCapitalChange: bool | None = Field(
        default=None,
        description="Whether to include change_in_working_capital in OE calculation.",
    )

    # Equity bridge overrides
    sharesOutstanding: float | None = Field(default=None, gt=0)
    netDebt: float | None = Field(
        default=None,
        description="Net debt (total debt − cash). May be negative (net cash position).",
    )

    # Meta
    analystName: str | None = None
    notes: str | None = None

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
    oeGrowthRateUsed: float | None = None
    terminalGrowthRateUsed: float | None = None
    maintenanceCapexRatioUsed: float | None = None

    # Base OE decomposition (transparency)
    baseOe: float | None = None
    baseOeFiscalYear: int | None = None
    netIncomeUsed: float | None = None
    daUsed: float | None = None               # Depreciation & Amortization
    capexUsed: float | None = None            # Capex (sign-normalized to negative)
    wcChangeUsed: float | None = None         # Working Capital Change (optional)

    # Forecast stream
    forecastOe: list[float] = Field(default_factory=list)
    pvOe: list[float] = Field(default_factory=list)
    discountFactors: list[float] | None = None
    totalPvOe: float = 0.0

    # Terminal value
    terminalValue: float | None = None
    pvTerminalValue: float | None = None
    oeNPlus1: float | None = None             # OE_{n+1} used in perpetuity formula

    # Equity bridge
    enterpriseValue: float | None = None
    netDebtUsed: float | None = None
    equityValue: float | None = None
    sharesOutstanding: float | None = None
    intrinsicValuePerShare: float | None = None

    # Read-time market comparison
    currentPrice: float | None = None
    upsideDownsidePct: float | None = None    # fraction (e.g. 0.25 = 25% upside)

    # Sensitivity grid (discount_rate × terminal_growth_rate)
    sensitivityScenarios: OeSensitivityGrid | None = None


class OeSensitivityGrid(BaseModel):
    """
    OE sensitivity: rows = discountRates, cols = terminalGrowthRates.
    Mirrors DcfSensitivityGrid structure for FE reuse.
    """

    discountRates: list[float]
    terminalGrowthRates: list[float]
    intrinsicValuePerShareMatrix: list[list[float | None]]
    currency: str | None = None

    model_config = {"extra": "ignore"}


class OwnerEarningsResponse(BaseModel):
    valuation: OwnerEarningsValuation
    applicability: Applicability
    dataQuality: DataQuality
