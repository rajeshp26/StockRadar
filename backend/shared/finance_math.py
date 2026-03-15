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