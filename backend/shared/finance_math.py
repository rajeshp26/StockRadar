# backend/shared/finance_math.py
"""
Shared financial math utilities.

Centralises formulas used across multiple services to prevent silent
divergence (the root cause of BUG-01, where dcf_service and
derived_financial_metrics_job had different FCF sign implementations).
"""
from __future__ import annotations
from typing import Optional


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