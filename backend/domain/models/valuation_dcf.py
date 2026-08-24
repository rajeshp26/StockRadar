from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Keep method names explicit and stable: stored in valuation_runs.method ("dcf")
TerminalMethod = Literal["perpetuity_growth", "exit_multiple"]
TerminalMetric = Literal["ebitda"]  # Extend later only if explicitly supported in services.


class DcfRequestOverrides(BaseModel):
    """
    DCF request overrides (optional inputs only).

    IMPORTANT DESIGN RULE (no assumptions):
    - This model intentionally avoids enforcing cross-field requirements
      (e.g., exitMultiple must exist when terminalMethod=exit_multiple),
      because missing values may be supplied by method defaults or company overrides
      in the service layer. The service performs final validation after resolution.
    """

    # Forecast controls
    forecastYears: int | None = Field(default=None, ge=1, le=20)
    forecastFcf: list[float] | None = Field(
        default=None,
        description="Explicit Free Cash Flow forecast series (absolute values).",
    )

    # If forecastFcf is not provided, service may derive forecast using:
    # fcfGrowthRate = growth applied directly to base FCF (NOT revenue).
    fcfGrowthRate: float | None = Field(
        default=None,
        description="FCF growth rate used to grow base FCF (accepts percent or fraction).",
    )

    # Backward-compatible alias (deprecated)
    revenueGrowthRate: float | None = Field(
        default=None,
        description="[DEPRECATED] Use fcfGrowthRate instead. If provided, will be treated as fcfGrowthRate.",
    )

    fcfMarginAssumption: float | None = Field(
        default=None,
        description="FCF margin assumption (accepts percent or fraction).",
    )

    # Discount rate (WACC)
    wacc: float | None = Field(
        default=None,
        description="Discount rate (WACC). Accepts percent or fraction.",
    )

    # Terminal Value method
    terminalMethod: TerminalMethod | None = Field(
        default=None,
        description="Terminal value method: perpetuity_growth | exit_multiple",
    )

    # Perpetuity Growth terminal inputs
    terminalGrowthRate: float | None = Field(
        default=None,
        description="Perpetual growth rate (g). Accepts percent or fraction.",
    )

    # Exit Multiple terminal inputs
    exitMultiple: float | None = Field(
        default=None,
        gt=0,
        description="Exit multiple (e.g., EV/EBITDA multiple).",
    )
    terminalMetric: TerminalMetric | None = Field(
        default=None,
        description="Metric used for exit multiple method (currently ebitda only).",
    )
    ebitdaMarginAssumption: float | None = Field(
        default=None,
        description="EBITDA margin used if terminal EBITDA must be derived.",
    )

    terminalEbitda: float | None = Field(
        default=None,
        gt=0,
        description="Terminal EBITDA (absolute). Required for exit_multiple unless deterministic derivation exists.",
    )

    # Equity bridge (optional overrides)
    sharesOutstanding: float | None = Field(
        default=None,
        gt=0,
        description="Shares outstanding. If omitted, service may resolve from financial tables.",
    )
    netDebt: float | None = Field(
        default=None,
        description="Net debt (debt - cash). If omitted, service may compute when inputs exist.",
    )

    # Metadata
    analystName: str | None = None
    notes: str | None = None

    # -------------------------------
    # Validators (Pydantic v2)
    # -------------------------------

    @field_validator("forecastFcf", mode="before")
    @classmethod
    def _validate_forecast_fcf(cls, v: list[float] | None) -> list[float] | None:
        if v is None:
            return None
        if not isinstance(v, list) or len(v) == 0:
            raise ValueError("forecastFcf must be a non-empty list when provided.")
        if len(v) > 20:
            raise ValueError("forecastFcf cannot exceed 20 years.")

        out: list[float] = []
        for i, x in enumerate(v):
            if x is None:
                raise ValueError(f"forecastFcf[{i}] is null; all values must be numbers.")
            try:
                fx = float(x)
            except Exception as e:
                raise ValueError(f"forecastFcf[{i}] is not a valid number.") from e
            if fx != fx:  # NaN
                raise ValueError(f"forecastFcf[{i}] cannot be NaN.")
            out.append(fx)
        return out

    @field_validator(
        "fcfGrowthRate",
        "revenueGrowthRate",
        "fcfMarginAssumption",
        "wacc",
        "terminalGrowthRate",
        "ebitdaMarginAssumption",
        mode="before",
    )
    @classmethod
    def _reject_nan(cls, v: Any) -> Any:
        # Do NOT normalize percent → fraction here.
        # Service layer owns normalization + audit logging.
        if v is None:
            return None
        try:
            f = float(v)
        except Exception as e:
            raise ValueError("Value must be a number.") from e
        if f != f:  # NaN
            raise ValueError("Value cannot be NaN.")
        return f

    @model_validator(mode="after")
    def _backcompat_growth_alias(self) -> DcfRequestOverrides:
        """
        Backward compatibility:
        - If fcfGrowthRate is not set but revenueGrowthRate is set,
          treat revenueGrowthRate as fcfGrowthRate.
        """
        if self.fcfGrowthRate is None and self.revenueGrowthRate is not None:
            self.fcfGrowthRate = self.revenueGrowthRate
        return self


class DcfValuation(BaseModel):
    """
    FE-ready DCF valuation payload.
    Keep camelCase keys aligned with frontend types.
    """

    symbol: str
    companyId: int
    currency: str

    terminalMethod: TerminalMethod

    forecastYears: int
    forecastFcf: list[float]
    pvFcf: list[float]
    totalPvFcf: float

    # Transparency
    discountFactors: list[float] | None = None

    waccUsed: float

    terminalValue: float | None = None
    pvTerminalValue: float | None = None

    terminalGrowthRateUsed: float | None = None
    cashFlowNPlus1: float | None = None

    baseFcf: float | None = None
    baseFcfFiscalYear: int | None = None

    enterpriseValue: float | None = None
    netDebtUsed: float | None = None
    equityValue: float | None = None

    sharesOutstanding: float | None = None
    intrinsicValuePerShare: float | None = None

    currentPrice: float | None = None
    upsideDownsidePct: float | None = None

    sensitivityScenarios: DcfSensitivityGrid | None = None


class DcfSensitivityGrid(BaseModel):
    """
    Canonical DCF sensitivity grid:
      - rows = discountRates (r)
      - cols = terminalGrowthRates (g)
      - values = intrinsicValuePerShareMatrix[r_index][g_index]
    """

    discountRates: list[float]
    terminalGrowthRates: list[float]
    intrinsicValuePerShareMatrix: list[list[float | None]]
    currency: str | None = None

    model_config = {
        "extra": "ignore",
    }


# Reuse standardized blocks from Rule #1 / DDM
from domain.models.valuation_rule1 import Applicability, DataQuality  # noqa: E402


class DcfResponse(BaseModel):
    valuation: DcfValuation
    applicability: Applicability
    dataQuality: DataQuality
