# backend/shared/finance_math.py
"""
Shared financial math utilities.

Centralises formulas used across multiple services to prevent silent
divergence (the root cause of BUG-01, where dcf_service and
derived_financial_metrics_job had different FCF sign implementations).

Functions:
  compute_fcf           — sign-aware Free Cash Flow
  safe_div              — division returning None instead of raising
  clamp                 — clamp value into [lo, hi]
  safe_float            — safe Any → Optional[float] conversion
  pct_or_frac_to_frac   — normalise percent or fraction to fraction
  build_fingerprint     — deterministic SHA-256 fingerprint for cache gating
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional


def compute_fcf(
    cash_from_operations: Optional[float],
    capital_expenditures: Optional[float],
) -> Optional[float]:
    """
    Compute Free Cash Flow from Operating Cash Flow and Capital Expenditures.

    CapEx convention in our DB: stored as NEGATIVE outflow
    (e.g. BN 2024: capital_expenditures = -11_172_000_000).

        FCF = OCF + capex      when capex < 0   (outflow stored negative)
        FCF = OCF - capex      when capex >= 0  (edge case: positive storage)

    This matches the defeatbeta sign convention and is consistent with the
    existing correct implementation in derived_financial_metrics_job._fcf().

    Examples:
        compute_fcf(7_569M, -11_172M) → -3_603M  ✓  (BN 2024)
        compute_fcf(90_000M, -9_000M) → +81_000M ✓  (AAPL-style)
        compute_fcf(None, -9_000M)    → None
    """
    if cash_from_operations is None or capital_expenditures is None:
        return None
    ocf   = float(cash_from_operations)
    capex = float(capital_expenditures)
    return (ocf + capex) if capex < 0 else (ocf - capex)


def safe_div(
    numerator: Optional[float],
    denominator: Optional[float],
) -> Optional[float]:
    """Division returning None instead of raising on None or zero denominator."""
    if numerator is None or denominator is None:
        return None
    try:
        return numerator / denominator if denominator != 0 else None
    except Exception:
        return None


def clamp(value: float, lo: float, hi: float) -> float:
    """Clamp value into [lo, hi]."""
    return max(lo, min(hi, value))


def safe_float(x: Any) -> Optional[float]:
    """
    Safely convert any value to float, returning None on failure or NaN.

    Centralised here to prevent the pattern of every service defining its own
    _safe_float() helper — which was the root cause of the DDM NameError
    (ddm_service.py's get_cached() referenced _safe_float that was never defined
    locally because each service copy was ad-hoc rather than shared).

    Examples:
        safe_float(None)     → None
        safe_float("3.14")   → 3.14
        safe_float(float("nan")) → None
        safe_float("bad")    → None
    """
    try:
        if x is None:
            return None
        f = float(x)
        return f if f == f else None  # NaN check: NaN != NaN is always True
    except Exception:
        return None


def pct_or_frac_to_frac(x: float) -> float:
    """
    Normalise a rate that may be stored as percent (e.g. 5.0) or fraction
    (e.g. 0.05) to a fraction.

    Convention: values > 1.0 are assumed to be percent and are divided by 100.
    Values ≤ 1.0 are returned unchanged.

    This is used consistently across DDM, DCF, OE, and RI services for WACC,
    growth rates, and discount rates.

    Examples:
        pct_or_frac_to_frac(5.0)  → 0.05
        pct_or_frac_to_frac(0.05) → 0.05
        pct_or_frac_to_frac(0.0)  → 0.0
        pct_or_frac_to_frac(1.5)  → 0.015   (rare; treated as 1.5%)
    """
    return x / 100.0 if x > 1.0 else x


def build_fingerprint(dep_values: dict) -> str:
    """
    Compute a deterministic 32-hex-char (128-bit) SHA-256 fingerprint of a
    dependency values dict used for Gate 2 cache invalidation.

    All services (DDM, DCF, OE, RI, Rule1) use this same fingerprint logic
    so the hashing is guaranteed consistent — same input always produces the
    same hash regardless of which service calls it.

    The dict must be JSON-serialisable. Values should be pre-rounded and
    lists pre-sorted by the caller to guarantee hash stability across calls.

    Examples:
        build_fingerprint({"beta": 0.85, "roe": 0.12}) → "a3f8c2e1b4d79501..."
        build_fingerprint({}) → sha256("{}").hexdigest()[:32]
    """
    raw = json.dumps(dep_values, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]

def compute_wacc(
    equity_value: Optional[float],
    debt_value: Optional[float],
    cost_of_equity: Optional[float],
    cost_of_debt: Optional[float],
    tax_rate: Optional[float],
) -> Optional[float]:
    """
    Compute Weighted Average Cost of Capital (WACC).

        WACC = (E/V) * ke + (D/V) * kd * (1 - t)

    Where:
        E/V  = equity weight
        D/V  = debt weight
        ke   = cost of equity (CAPM: rf + beta * ERP)
        kd   = cost of debt (pre-tax)
        t    = effective tax rate

    Returns fraction (e.g. 0.10 for 10%). Returns None if inputs are insufficient.

    Examples:
        compute_wacc(100_000, 50_000, 0.10, 0.05, 0.21)  ? ~0.0833
        compute_wacc(None, 50_000, 0.10, 0.05, 0.21)      ? None
    """
    if equity_value is None and debt_value is None:
        return None
    if cost_of_equity is None:
        return None
    ev = float(equity_value) if equity_value is not None else 0.0
    dv = float(debt_value) if debt_value is not None else 0.0
    total = ev + dv
    if total <= 0:
        return None
    w_equity = ev / total
    w_debt   = dv / total
    ke = float(cost_of_equity)
    kd_after_tax = 0.0
    if cost_of_debt is not None and debt_value is not None and debt_value > 0:
        kd = float(cost_of_debt)
        t  = float(tax_rate) if tax_rate is not None else 0.0
        t  = clamp(t, 0.0, 1.0)
        kd_after_tax = kd * (1.0 - t)
    return w_equity * ke + w_debt * kd_after_tax


def compute_cost_of_equity(
    risk_free_rate: Optional[float],
    beta: Optional[float],
    equity_risk_premium: Optional[float],
    default_value: Optional[float] = None,
) -> Optional[float]:
    """
    Compute Cost of Equity using CAPM.

        ke = rf + beta * ERP

    All inputs as fractions. Returns fraction (e.g. 0.10 for 10%).

    Examples:
        compute_cost_of_equity(0.045, 1.2, 0.055)  ? 0.111
        compute_cost_of_equity(None, 1.2, 0.055)    ? None
        compute_cost_of_equity(0.045, None, 0.055, default_value=0.10) ? 0.10
    """
    if risk_free_rate is None or beta is None or equity_risk_premium is None:
        return default_value
    rf  = float(risk_free_rate)
    b   = float(beta)
    erp = float(equity_risk_premium)
    return rf + b * erp


def compute_roic(
    nopat: Optional[float],
    invested_capital: Optional[float],
) -> Optional[float]:
    """
    Compute Return on Invested Capital (ROIC).

        ROIC = NOPAT / Invested Capital

    NOPAT = EBIT * (1 - tax_rate)

    Returns fraction (e.g. 0.15 for 15%). Returns None if inputs missing.

    Examples:
        compute_roic(10_000, 100_000)  ? 0.10
        compute_roic(None, 100_000)    ? None
    """
    return safe_div(nopat, invested_capital)


def compute_nopat(
    ebit: Optional[float],
    tax_rate: Optional[float],
) -> Optional[float]:
    """
    Compute Net Operating Profit After Tax (NOPAT).

        NOPAT = EBIT * (1 - tax_rate)

    If tax_rate is None, assumes 21% default.

    Examples:
        compute_nopat(10_000, 0.21)  ? 7_900
        compute_nopat(10_000, None)  ? 7_900  (default 21%)
    """
    if ebit is None:
        return None
    t = float(tax_rate) if tax_rate is not None else 0.21
    t = clamp(t, 0.0, 1.0)
    return float(ebit) * (1.0 - t)