# domain/models/valuation_residual_income.py
from __future__ import annotations
from typing import Any, List, Optional
from pydantic import BaseModel, Field, field_validator

# Reuse shared primitives from Rule #1 (keeps FE behaviour consistent)
from domain.models.valuation_rule1 import Applicability, DataQuality  # noqa: E402


class ResidualIncomeRequestOverrides(BaseModel):
    """
    Optional user/analyst overrides for Residual Income inputs.

    DESIGN RULE (no assumptions):
    - If requiredReturn is provided, it bypasses CAPM entirely (same as DDM).
    - beta, riskFreeRate, equityRiskPremium feed into CAPM only when
      requiredReturn is NOT provided.
    - riGrowthRate: growth rate applied to the RI per-share stream.
      Resolved from EPS CAGR / analyst estimates / defaults when not provided.
    """

    # Cost-of-equity inputs (CAPM path; mirrors DDM overrides)
    requiredReturn: Optional[float] = Field(
        default=None,
        description="Direct cost of equity override. Bypasses CAPM when provided.",
    )
    beta: Optional[float] = Field(default=None, description="Equity beta override.")
    riskFreeRate: Optional[float] = Field(default=None, description="Risk-free rate override.")
    equityRiskPremium: Optional[float] = Field(default=None, description="ERP override.")

    # Growth inputs
    riGrowthRate: Optional[float] = Field(
        default=None,
        description="Annual growth rate for Residual Income stream (accepts percent or fraction).",
    )
    terminalGrowthRate: Optional[float] = Field(
        default=None,
        description="Perpetual growth rate for terminal RI value (accepts percent or fraction).",
    )

    # Forecast horizon
    forecastYears: Optional[int] = Field(default=None, ge=1, le=20)

    # Meta
    analystName: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("requiredReturn", "riGrowthRate", "terminalGrowthRate",
                     "riskFreeRate", "equityRiskPremium", mode="before")
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


class ResidualIncomeValuation(BaseModel):
    """
    FE-ready Residual Income valuation payload.
    camelCase keys aligned with frontend convention.

    Design note:
    - No equity bridge (netDebt / EV). The RI model is equity-native:
      intrinsicPerShare = BV₀/share + PV(RI stream) + PV(terminal RI).
    - upsideDownsidePct is a fraction (e.g. 0.25 = 25% upside), consistent with DDM.
    """

    symbol: str
    companyId: int
    currency: str

    # Inputs used
    forecastYears: int
    costOfEquityUsed: float
    betaUsed: Optional[float] = None
    rfUsed: Optional[float] = None
    erpUsed: Optional[float] = None
    riGrowthRateUsed: Optional[float] = None
    terminalGrowthRateUsed: Optional[float] = None

    # Base values
    eps0: Optional[float] = None                 # Latest annual EPS (NI-to-common / shares)
    bvPerShare: Optional[float] = None           # Book value per share at t=0
    roe0: Optional[float] = None                 # ROE at t=0 = NI / Equity
    ri0PerShare: Optional[float] = None          # RI₀/share = EPS₀ − k_e × BV₀/share
    bvFiscalYear: Optional[int] = None

    # Forecast stream
    forecastRiPerShare: List[float] = Field(default_factory=list)
    pvRiPerShare: List[float] = Field(default_factory=list)
    discountFactors: Optional[List[float]] = None
    totalPvRiPerShare: float = 0.0

    # Terminal value
    terminalRiPerShare: Optional[float] = None   # RI_{n+1}/share
    terminalValueRi: Optional[float] = None      # TV = RI_{n+1} / (k_e − g_terminal)
    pvTerminalRiPerShare: Optional[float] = None

    # Intrinsic value
    intrinsicValuePerShare: Optional[float] = None

    # Read-time market comparison
    currentPrice: Optional[float] = None
    upsideDownsidePct: Optional[float] = None    # fraction, consistent with DDM convention


class ResidualIncomeResponse(BaseModel):
    valuation: ResidualIncomeValuation
    applicability: Applicability
    dataQuality: DataQuality