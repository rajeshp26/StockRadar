# backend/domain/models/analysis_magic_formula.py
"""
Pydantic models for Magic Formula (Greenblatt) analysis output.

Earnings Yield = TTM EBIT / Enterprise Value
Return on Capital = TTM EBIT / (Net Working Capital + Net Fixed Assets)

NWC (Greenblatt) = (current_assets - excess_cash) - (current_liabilities - short_term_debt)
NFA              = property_plant_equipment_net   [goodwill / intangibles excluded]

These are GET-only derived analytics — no user override parameters.
The output is cached in valuation_runs (method='magic_formula').
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DiagnosticFlag(BaseModel):
    code: str
    severity: str          # "critical" | "high" | "medium" | "low" | "info"
    message: str
    recommendation: str | None = None
    evidence: dict[str, Any] | None = None


# ── Core computation outputs ───────────────────────────────────────────────────

class MagicFormulaInputs(BaseModel):
    """Raw financial inputs resolved during computation."""
    ttm_ebit: float | None
    ttm_ebit_source: str             # "ttm_quarterly" | "annual_fallback"
    ttm_quarters_used: int           # 1–4
    enterprise_value: float | None
    current_assets: float | None
    cash_and_equivalents: float | None
    current_liabilities: float | None
    short_term_debt: float | None
    ppe_net: float | None
    goodwill_excluded: float | None
    intangibles_excluded: float | None
    fiscal_year_bs: int | None    # balance sheet vintage


class MagicFormulaValuation(BaseModel):
    """Computed Magic Formula metrics."""
    # Primary metrics
    earnings_yield: float | None          # EBIT / EV — higher is cheaper
    return_on_capital: float | None       # Greenblatt ROC = EBIT / (NWC + NFA)

    # Decomposition
    net_working_capital: float | None     # Greenblatt NWC (excess cash excluded)
    net_fixed_assets: float | None        # PPE net (intangibles excluded)
    invested_capital_mf: float | None     # NWC + NFA

    # Cross-check (from financial_ratios — methodologically close but not identical)
    roic_from_ratios: float | None
    roic_delta_note: str | None           # explains methodology difference if material

    # Formatted for display
    earnings_yield_pct: float | None      # earnings_yield * 100
    return_on_capital_pct: float | None   # return_on_capital * 100


class MagicFormulaIndustryContext(BaseModel):
    """Industry-level context for interpreting absolute metrics."""
    sector: str | None
    industry: str | None
    avg_ev_ebitda: float | None
    implied_industry_earnings_yield: float | None   # 1 / avg_ev_ebitda (approx)
    earnings_yield_vs_industry: str | None          # "above" | "below" | "inline"
    earnings_yield_premium_pct: float | None        # how far above/below (pct pts)
    avg_eps_growth: float | None
    sample_size: int | None
    calculation_date: str | None
    context_note: str = (
        "Industry multiples provide directional context. "
        "Magic Formula ranking requires a full-universe dataset."
    )


class MagicFormulaApplicability(BaseModel):
    """Suitability assessment — some sectors invalidate the formula."""
    score: int                        # 0–100
    category: str                     # "Applicable" | "Caution" | "Not Applicable"
    excluded: bool                    # True for financials / utilities / REITs
    exclusion_reason: str | None
    flags: list[DiagnosticFlag] = []
    suitability_summary: str | None    # AI-generated plain-English summary


class MagicFormulaDataQuality(BaseModel):
    ttm_coverage: str           # "full_4q" | "partial_Nq" | "annual_only"
    ev_source: str              # "company_summary" | "unavailable"
    bs_fiscal_year: int | None
    days_since_bs_update: int | None
    days_since_ev_snapshot: int | None
    fallbacks_used: bool
    last_computed_at: str


# ── Top-level response ────────────────────────────────────────────────────────

class MagicFormulaResponse(BaseModel):
    symbol: str
    company_id: int
    currency: str
    inputs: MagicFormulaInputs
    valuation: MagicFormulaValuation
    industry_context: MagicFormulaIndustryContext
    applicability: MagicFormulaApplicability
    data_quality: MagicFormulaDataQuality
