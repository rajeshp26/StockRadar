# backend/domain/models/analysis_canslim.py
"""
Pydantic models for CANSlim analysis output.

Letter weights (O'Neil's emphasis order):
  C — 20%  Current quarterly earnings acceleration
  A — 20%  Annual earnings growth (3–5yr CAGR)
  N — 10%  New product / near 52-week high proxy
  S — 15%  Supply/demand (float, volume trend)
  L — 15%  Leader or laggard (RS vs benchmark)
  I — 10%  Institutional sponsorship (scored as unavailable — no 13F data)
  M — 10%  Market direction (SPY 50/200 SMA trend)

Composite = weighted sum of available letter scores.
Confidence adjusts downward when letters are unavailable.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DiagnosticFlag(BaseModel):
    code: str
    severity: str
    message: str
    recommendation: Optional[str] = None


class LetterEvidence(BaseModel):
    """Key metrics used to score a single letter."""
    metrics: Dict[str, Any] = {}     # label → value, shown in UI detail panel
    data_source: str = "database"    # "database" | "live_fetch" | "unavailable"
    as_of_date: Optional[str] = None


class LetterScore(BaseModel):
    letter: str                      # "C" | "A" | "N" | "S" | "L" | "I" | "M"
    name: str                        # human-readable criterion name
    score: int                       # 0–100 (0 if unavailable)
    weight: float                    # fractional weight in composite (0.0–1.0)
    available: bool                  # False when data is structurally missing (e.g. I)
    signal: str                      # "bullish" | "bearish" | "neutral" | "unavailable"
    headline: str                    # one-line plain English summary
    evidence: LetterEvidence
    flags: List[str] = []


class CANSlimLetters(BaseModel):
    C: LetterScore
    A: LetterScore
    N: LetterScore
    S: LetterScore
    L: LetterScore
    I: LetterScore
    M: LetterScore


class CANSlimMarketCondition(BaseModel):
    """
    Derived from M letter — describes overall market environment.
    O'Neil: never buy heavily during distribution; wait for confirmed uptrend.
    """
    condition: str              # "confirmed_uptrend" | "uptrend_pressure" | "distribution" | "downtrend"
    spy_price: Optional[float]
    spy_sma50: Optional[float]
    spy_sma200: Optional[float]
    sma50_vs_200: str           # "above" | "below"
    sma200_slope: str           # "rising" | "falling" | "flat"
    description: str


class CANSlimDataQuality(BaseModel):
    letters_fully_scored: int        # count of letters with available=True
    letters_unavailable: List[str]   # e.g. ["I"]
    benchmark_role: str              # "us_market" — which benchmark was used for L/M
    benchmark_symbol: str            # e.g. "SPY"
    confidence_adjustment: float     # 0.0–1.0 multiplier applied to composite
    confidence_note: Optional[str]
    last_computed_at: str


# ── Top-level response ────────────────────────────────────────────────────────

class CANSlimResponse(BaseModel):
    symbol: str
    company_id: int
    currency: str
    letters: CANSlimLetters
    composite_score: int             # 0–100, weighted, confidence-adjusted
    composite_category: str          # "Strong" | "Moderate" | "Weak"
    market_condition: CANSlimMarketCondition
    flags: List[DiagnosticFlag] = []
    data_quality: CANSlimDataQuality