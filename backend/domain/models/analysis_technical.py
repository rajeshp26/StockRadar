# backend/domain/models/analysis_technical.py
"""
Pydantic models for Murphy Style Technical Analysis output.

Murphy's analytical hierarchy (most → least important):
  1. Trend    — 200/50 SMA direction and relative position
  2. Volume   — OBV confirms or diverges from price
  3. Momentum — MACD zero-line crossover (strong), signal crossover (weak)
  4. RSI      — level interpretation in context of trend, divergences
  5. Oscillators — Stochastic, Bollinger (timing tools, not trend tools)

This response is stateless — computed on demand from live daily OHLCV,
never persisted to valuation_runs.
"""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel


# ── Shared primitives ─────────────────────────────────────────────────────────

class PriceLevel(BaseModel):
    """A significant support or resistance price level."""
    price: float
    level_type: str          # "support" | "resistance"
    strength: str            # "strong" | "moderate" | "weak"
    source: str              # "pivot_high" | "pivot_low" | "sma200" | "sma50"
    distance_pct: float      # % distance from current price (signed: + above, - below)


class MACDReadings(BaseModel):
    macd_line: Optional[float]
    signal_line: Optional[float]
    histogram: Optional[float]
    histogram_prev: Optional[float]    # prior bar — direction of change
    zero_line_position: str            # "above" | "below"
    signal_cross: str                  # "bullish_cross" | "bearish_cross" | "none"
    zero_cross: str                    # "bullish_cross" | "bearish_cross" | "none"
    histogram_direction: str           # "expanding_bullish" | "contracting_bullish" |
                                       # "expanding_bearish" | "contracting_bearish" | "flat"
    divergence: str                    # "bullish" | "bearish" | "none" | "insufficient_data"
    divergence_note: Optional[str]


class RSIReadings(BaseModel):
    value: Optional[float]
    zone: str                # "overbought" | "upper_neutral" | "lower_neutral" | "oversold"
    trend_context: str       # how RSI should be interpreted given the price trend
    divergence: str          # "bullish" | "bearish" | "none" | "insufficient_data"
    divergence_note: Optional[str]


# ── Layer 1: Trend ────────────────────────────────────────────────────────────

class TrendAnalysis(BaseModel):
    sma50: Optional[float]
    sma200: Optional[float]
    current_price: float

    price_vs_sma50: str      # "above" | "below"
    price_vs_sma200: str     # "above" | "below"
    sma50_vs_sma200: str     # "above" | "below"

    sma200_slope: str        # "rising" | "falling" | "flat"
    sma50_slope: str         # "rising" | "falling" | "flat"

    golden_cross: bool       # sma50 crossed above sma200 within last 60 bars
    death_cross: bool        # sma50 crossed below sma200 within last 60 bars
    cross_bars_ago: Optional[int]    # how many bars since the cross

    primary_trend: str       # "uptrend" | "downtrend" | "sideways"
    intermediate_trend: str  # "uptrend" | "downtrend" | "sideways"
    trend_strength: str      # "strong" | "moderate" | "weak"

    distance_from_sma200_pct: Optional[float]   # % above/below 200 SMA
    distance_from_sma50_pct: Optional[float]


# ── Layer 2: Volume / OBV ─────────────────────────────────────────────────────

class VolumeAnalysis(BaseModel):
    obv_current: Optional[float]
    obv_trend: str           # "rising" | "falling" | "flat"
    obv_confirms_price: bool # True when OBV trend matches price trend

    vol_avg_10: Optional[float]
    vol_avg_50: Optional[float]
    vol_ratio: Optional[float]       # vol_avg_10 / vol_avg_50
    volume_signal: str               # "accumulation" | "distribution" | "neutral"
    volume_signal_note: str


# ── Layer 3: Momentum / MACD ──────────────────────────────────────────────────

class MomentumAnalysis(BaseModel):
    macd: MACDReadings
    rsi: RSIReadings


# ── Layer 4: Support / Resistance ─────────────────────────────────────────────

class SupportResistanceAnalysis(BaseModel):
    levels: List[PriceLevel]                  # sorted by distance_pct absolute value
    nearest_support: Optional[PriceLevel]
    nearest_resistance: Optional[PriceLevel]
    price_in_range: bool                      # between nearest support and resistance
    high_52w: Optional[float]
    low_52w: Optional[float]
    pct_from_52w_high: Optional[float]
    pct_from_52w_low: Optional[float]


# ── Layer 5: Oscillators ──────────────────────────────────────────────────────

class BollingerReadings(BaseModel):
    upper: Optional[float]
    middle: Optional[float]        # 20-period SMA
    lower: Optional[float]
    bandwidth: Optional[float]     # (upper - lower) / middle — volatility proxy
    bandwidth_percentile: Optional[float]    # vs. last 52 weeks of bandwidth
    price_position: str            # "above_upper" | "near_upper" | "middle" |
                                   # "near_lower" | "below_lower"
    squeeze: bool                  # bandwidth in bottom 20% of recent range


class StochasticReadings(BaseModel):
    k_line: Optional[float]
    d_line: Optional[float]
    zone: str                      # "overbought" | "neutral" | "oversold"
    signal: str                    # "bullish_cross" | "bearish_cross" | "none"


class OscillatorAnalysis(BaseModel):
    bollinger: BollingerReadings
    stochastic: StochasticReadings


# ── Murphy Synthesis ──────────────────────────────────────────────────────────

class MurphySynthesis(BaseModel):
    """
    Hierarchical synthesis following Murphy's rule:
    trend overrules oscillators — an overbought RSI in a strong uptrend
    is NOT a sell signal.
    """
    overall_signal: str          # "strong_buy" | "buy" | "neutral" | "sell" | "strong_sell"
    signal_strength: int         # 0–100
    risk_level: str              # "low" | "moderate" | "high"

    # Which Murphy principle is dominating the current signal
    dominant_factor: str         # "trend" | "momentum" | "volume" | "oscillators"
    dominant_factor_note: str

    # Plain-English observations (3–5 bullets)
    key_observations: List[str]

    # Flags for meaningful divergences or conflicts between layers
    conflicts: List[str]         # e.g. "Price above 200 SMA but OBV declining"

    caution_note: Optional[str]  # non-null when data quality limits confidence


# ── Data quality ──────────────────────────────────────────────────────────────

class TechnicalDataQuality(BaseModel):
    bars_available: int
    bars_required_200sma: int = 200
    bars_required_rsi: int = 14
    bars_required_macd: int = 35    # 26 slow EMA + 9 signal warmup
    data_source: str                # "defeatbeta" | "yfinance"
    oldest_bar_date: Optional[str]
    newest_bar_date: Optional[str]
    sufficient_for_full_analysis: bool
    degraded_indicators: List[str]  # indicators that could not be computed


# ── Top-level response ────────────────────────────────────────────────────────

class MurphyAnalysisResponse(BaseModel):
    symbol: str
    currency: str
    as_of_date: str              # newest bar date
    current_price: float
    data_quality: TechnicalDataQuality
    trend: TrendAnalysis
    momentum: MomentumAnalysis
    volume: VolumeAnalysis
    support_resistance: SupportResistanceAnalysis
    oscillators: OscillatorAnalysis
    synthesis: MurphySynthesis