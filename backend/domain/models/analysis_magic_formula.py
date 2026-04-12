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
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DiagnosticFlag(BaseModel):
    code: str
    severity: str          # "critical" | "high" | "medium" | "low" | "info"
    message: str
    recommendation: Optional[str] = None
    evidence: Optional[Dict[str, Any]] = None


# ── Core computation outputs ───────────────────────────────────────────────────

class MagicFormulaInputs(BaseModel):
    """Raw financial inputs resolved during computation."""
    ttm_ebit: Optional[float]
    ttm_ebit_source: str             # "ttm_quarterly" | "annual_fallback"
    ttm_quarters_used: int           # 1–4
    enterprise_value: Optional[float]
    current_assets: Optional[float]
    cash_and_equivalents: Optional[float]
    current_liabilities: Optional[float]
    short_term_debt: Optional[float]
    ppe_net: Optional[float]
    goodwill_excluded: Optional[float]
    intangibles_excluded: Optional[float]
    fiscal_year_bs: Optional[int]    # balance sheet vintage


class MagicFormulaValuation(BaseModel):
    """Computed Magic Formula metrics."""
    # Primary metrics
    earnings_yield: Optional[float]          # EBIT / EV — higher is cheaper
    return_on_capital: Optional[float]       # Greenblatt ROC = EBIT / (NWC + NFA)

    # Decomposition
    net_working_capital: Optional[float]     # Greenblatt NWC (excess cash excluded)
    net_fixed_assets: Optional[float]        # PPE net (intangibles excluded)
    invested_capital_mf: Optional[float]     # NWC + NFA

    # Cross-check (from financial_ratios — methodologically close but not identical)
    roic_from_ratios: Optional[float]
    roic_delta_note: Optional[str]           # explains methodology difference if material

    # Formatted for display
    earnings_yield_pct: Optional[float]      # earnings_yield * 100
    return_on_capital_pct: Optional[float]   # return_on_capital * 100


class MagicFormulaIndustryContext(BaseModel):
    """Industry-level context for interpreting absolute metrics."""
    sector: Optional[str]
    industry: Optional[str]
    avg_ev_ebitda: Optional[float]
    implied_industry_earnings_yield: Optional[float]   # 1 / avg_ev_ebitda (approx)
    earnings_yield_vs_industry: Optional[str]          # "above" | "below" | "inline"
    earnings_yield_premium_pct: Optional[float]        # how far above/below (pct pts)
    avg_eps_growth: Optional[float]
    sample_size: Optional[int]
    calculation_date: Optional[str]
    context_note: str = (
        "Industry multiples provide directional context. "
        "Magic Formula ranking requires a full-universe dataset."
    )


class MagicFormulaApplicability(BaseModel):
    """Suitability assessment — some sectors invalidate the formula."""
    score: int                        # 0–100
    category: str                     # "Applicable" | "Caution" | "Not Applicable"
    excluded: bool                    # True for financials / utilities / REITs
    exclusion_reason: Optional[str]
    flags: List[DiagnosticFlag] = []
    suitability_summary: Optional[str]    # AI-generated plain-English summary


class MagicFormulaDataQuality(BaseModel):
    ttm_coverage: str           # "full_4q" | "partial_Nq" | "annual_only"
    ev_source: str              # "company_summary" | "unavailable"
    bs_fiscal_year: Optional[int]
    days_since_bs_update: Optional[int]
    days_since_ev_snapshot: Optional[int]
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