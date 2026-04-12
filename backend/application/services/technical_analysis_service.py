# backend/application/services/technical_analysis_service.py
"""
Murphy Style Technical Analysis Service.

Stateless — fetches live daily OHLCV, computes all indicators in-memory,
returns structured response.  No DB writes.  No valuation_runs entry.

Indicator implementations:
  - SMA(50), SMA(200)
  - RSI(14) using Wilder's exponential smoothing (not simple average)
  - MACD(12, 26, 9) using standard EMA
  - OBV with 10/50 bar volume SMA trend
  - Pivot highs/lows (n=2 bars each side) for support/resistance
  - Stochastic(14, 3, 3)
  - Bollinger Bands(20, 2σ) with bandwidth percentile

Murphy hierarchy enforced in synthesis:
  trend > volume > momentum > oscillators
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from domain.models.analysis_technical import (
    BollingerReadings,
    MACDReadings,
    MomentumAnalysis,
    MurphyAnalysisResponse,
    MurphySynthesis,
    OscillatorAnalysis,
    PriceLevel,
    RSIReadings,
    StochasticReadings,
    SupportResistanceAnalysis,
    TechnicalDataQuality,
    TrendAnalysis,
    VolumeAnalysis,
)
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

_FETCH_DAYS = 420       # calendar days — yields ~290 trading days on average
_MIN_BARS_FULL = 200    # needed for 200-day SMA
_MIN_BARS_MACD = 35     # 26 slow EMA + 9 signal warmup
_MIN_BARS_RSI = 15      # 14 + 1 seed bar
_MIN_BARS_ANY = 26      # absolute minimum for partial analysis


class TechnicalAnalysisService:
    def __init__(
        self,
        valuation_repo: ValuationRepository,
        defeat_beta_provider: Any,
        yfinance_provider: Any,
    ) -> None:
        self._repo = valuation_repo
        self._dbeta = defeat_beta_provider
        self._yf = yfinance_provider

    # ── Public entry point ─────────────────────────────────────────────────────

    async def get_murphy_analysis(self, symbol: str) -> MurphyAnalysisResponse:
        ctx = await self._repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")

        company_id = int(ctx["company_id"])
        currency = ctx.get("currency") or "USD"

        bars = await self._fetch_daily_bars(symbol, company_id)
        if len(bars) < _MIN_BARS_ANY:
            raise ValueError(
                f"Insufficient price history for {symbol}: "
                f"{len(bars)} bars available, {_MIN_BARS_ANY} required."
            )

        closes = [float(b["close_price"]) for b in bars]
        highs = [float(b.get("high_price") or b["close_price"]) for b in bars]
        lows = [float(b.get("low_price") or b["close_price"]) for b in bars]
        volumes = [int(b.get("volume") or 0) for b in bars]
        dates_str = [str(b["price_date"]) for b in bars]

        data_quality = self._assess_data_quality(bars, dates_str)
        trend = self._compute_trend(closes, dates_str)
        momentum = self._compute_momentum(closes)
        volume = self._compute_volume(closes, volumes)
        sr = self._compute_support_resistance(highs, lows, closes, dates_str)
        oscillators = self._compute_oscillators(highs, lows, closes)
        synthesis = self._compute_synthesis(trend, momentum, volume, oscillators, data_quality)

        return MurphyAnalysisResponse(
            symbol=symbol.upper(),
            currency=currency,
            as_of_date=dates_str[-1],
            current_price=closes[-1],
            data_quality=data_quality,
            trend=trend,
            momentum=momentum,
            volume=volume,
            support_resistance=sr,
            oscillators=oscillators,
            synthesis=synthesis,
        )

    # ── Data fetch ─────────────────────────────────────────────────────────────

    async def _fetch_daily_bars(
        self, symbol: str, company_id: int
    ) -> List[Dict[str, Any]]:
        """
        Primary: DefeatBetaProvider (already returns daily OHLCV).
        Fallback: YFinanceProvider.
        Sorted oldest-first, last _FETCH_DAYS calendar days only.
        """
        start = date.today() - timedelta(days=_FETCH_DAYS)
        bars: List[Dict[str, Any]] = []

        try:
            bars = await self._dbeta.fetch_price_history(
                symbol, company_id, start_date=start
            )
        except Exception as e:
            logger.warning("[TECH] DefeatBeta price fetch failed for %s: %s", symbol, e)

        if not bars and self._yf:
            try:
                import pandas as pd
                df = await asyncio.to_thread(self._yf.get_price_history_df, symbol)
                if df is not None and not df.empty:
                    df["price_date"] = pd.to_datetime(df["price_date"], errors="coerce")
                    df = df[df["price_date"] >= pd.Timestamp(start)]
                    bars = [
                        {
                            "company_id": company_id,
                            "price_date": str(r["price_date"].date()),
                            "open_price": r.get("open_price"),
                            "close_price": r.get("close_price"),
                            "high_price": r.get("high_price"),
                            "low_price": r.get("low_price"),
                            "volume": r.get("volume"),
                        }
                        for _, r in df.iterrows()
                        if r.get("close_price") is not None
                    ]
            except Exception as e:
                logger.warning("[TECH] YFinance price fetch failed for %s: %s", symbol, e)

        # Ensure oldest-first and remove any bars with null close
        bars = [b for b in bars if b.get("close_price") is not None]
        bars.sort(key=lambda b: str(b["price_date"]))
        return bars

    # ── Data quality ───────────────────────────────────────────────────────────

    def _assess_data_quality(
        self, bars: List[Dict], dates_str: List[str]
    ) -> TechnicalDataQuality:
        n = len(bars)
        degraded: List[str] = []
        if n < _MIN_BARS_FULL:
            degraded.append("sma200")
        if n < _MIN_BARS_MACD:
            degraded.append("macd")
            degraded.append("signal_line")
        if n < _MIN_BARS_RSI:
            degraded.append("rsi")
        source = str(bars[0].get("data_source", "defeatbeta")) if bars else "unknown"
        return TechnicalDataQuality(
            bars_available=n,
            data_source=source,
            oldest_bar_date=dates_str[0] if dates_str else None,
            newest_bar_date=dates_str[-1] if dates_str else None,
            sufficient_for_full_analysis=(n >= _MIN_BARS_FULL),
            degraded_indicators=degraded,
        )

    # ── Indicator math ─────────────────────────────────────────────────────────

    @staticmethod
    def _sma(values: List[float], period: int) -> List[Optional[float]]:
        n = len(values)
        result: List[Optional[float]] = [None] * n
        for i in range(period - 1, n):
            result[i] = sum(values[i - period + 1 : i + 1]) / period
        return result

    @staticmethod
    def _slope(sma_series: List[Optional[float]], lookback: int = 10) -> str:
        """Classify SMA slope using last `lookback` non-None values."""
        vals = [v for v in sma_series if v is not None]
        if len(vals) < lookback:
            return "flat"
        recent = vals[-lookback:]
        delta = (recent[-1] - recent[0]) / recent[0] if recent[0] else 0
        if delta > 0.01:
            return "rising"
        if delta < -0.01:
            return "falling"
        return "flat"

    @staticmethod
    def _ema(values: List[Optional[float]], period: int) -> List[Optional[float]]:
        n = len(values)
        result: List[Optional[float]] = [None] * n
        k = 2.0 / (period + 1)
        # Seed: find first contiguous window of `period` non-None values
        for start in range(n):
            if values[start] is not None:
                window = values[start : start + period]
                if len(window) == period and all(v is not None for v in window):
                    seed = sum(v for v in window if v is not None) / period  # type: ignore[arg-type]
                    result[start + period - 1] = seed
                    ema = seed
                    for j in range(start + period, n):
                        if values[j] is not None:
                            ema = float(values[j]) * k + ema * (1 - k)
                        result[j] = ema
                    break
        return result

    @staticmethod
    def _wilder_rsi(closes: List[float], period: int = 14) -> List[Optional[float]]:
        """
        Wilder's smoothed RSI.  The first RS value is seeded with a simple
        average of the first `period` gains/losses; subsequent values use
        Wilder's EMA: avg = (prev_avg * (period-1) + current) / period.
        """
        n = len(closes)
        result: List[Optional[float]] = [None] * n
        if n < period + 1:
            return result

        gains = [max(closes[i] - closes[i - 1], 0.0) for i in range(1, n)]
        losses = [max(closes[i - 1] - closes[i], 0.0) for i in range(1, n)]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        def _rsi(ag: float, al: float) -> float:
            return 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)

        result[period] = _rsi(avg_gain, avg_loss)
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
            result[i + 1] = _rsi(avg_gain, avg_loss)

        return result

    @classmethod
    def _macd(
        cls,
        closes: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
    ) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
        ema_fast = cls._ema(closes, fast)  # type: ignore[arg-type]
        ema_slow = cls._ema(closes, slow)  # type: ignore[arg-type]
        macd_line: List[Optional[float]] = [
            (f - s) if (f is not None and s is not None) else None
            for f, s in zip(ema_fast, ema_slow)
        ]
        signal_line = cls._ema(macd_line, signal)
        histogram: List[Optional[float]] = [
            (m - s) if (m is not None and s is not None) else None
            for m, s in zip(macd_line, signal_line)
        ]
        return macd_line, signal_line, histogram

    @staticmethod
    def _obv(closes: List[float], volumes: List[int]) -> List[float]:
        result = [0.0]
        for i in range(1, len(closes)):
            vol = volumes[i] or 0
            if closes[i] > closes[i - 1]:
                result.append(result[-1] + vol)
            elif closes[i] < closes[i - 1]:
                result.append(result[-1] - vol)
            else:
                result.append(result[-1])
        return result

    @staticmethod
    def _pivot_highs(
        highs: List[float], n: int = 2
    ) -> List[Tuple[int, float]]:
        pivots = []
        for i in range(n, len(highs) - n):
            if all(highs[i] >= highs[i - j] for j in range(1, n + 1)) and all(
                highs[i] >= highs[i + j] for j in range(1, n + 1)
            ):
                pivots.append((i, highs[i]))
        return pivots

    @staticmethod
    def _pivot_lows(
        lows: List[float], n: int = 2
    ) -> List[Tuple[int, float]]:
        pivots = []
        for i in range(n, len(lows) - n):
            if all(lows[i] <= lows[i - j] for j in range(1, n + 1)) and all(
                lows[i] <= lows[i + j] for j in range(1, n + 1)
            ):
                pivots.append((i, lows[i]))
        return pivots

    @staticmethod
    def _stochastic(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        k_period: int = 14,
        k_smooth: int = 3,
        d_smooth: int = 3,
    ) -> Tuple[List[Optional[float]], List[Optional[float]]]:
        n = len(closes)
        raw_k: List[Optional[float]] = [None] * n
        for i in range(k_period - 1, n):
            h = max(highs[i - k_period + 1 : i + 1])
            lo = min(lows[i - k_period + 1 : i + 1])
            raw_k[i] = 50.0 if h == lo else 100.0 * (closes[i] - lo) / (h - lo)

        # %K = smoothed raw_k; %D = smoothed %K
        def _sma_opt(vals: List[Optional[float]], p: int) -> List[Optional[float]]:
            out: List[Optional[float]] = [None] * len(vals)
            for i in range(p - 1, len(vals)):
                window = vals[i - p + 1 : i + 1]
                if all(v is not None for v in window):
                    out[i] = sum(v for v in window if v is not None) / p  # type: ignore[misc]
            return out

        k_line = _sma_opt(raw_k, k_smooth)
        d_line = _sma_opt(k_line, d_smooth)
        return k_line, d_line

    @staticmethod
    def _bollinger(
        closes: List[float], period: int = 20, n_std: float = 2.0
    ) -> Tuple[
        List[Optional[float]],
        List[Optional[float]],
        List[Optional[float]],
        List[Optional[float]],
    ]:
        size = len(closes)
        upper: List[Optional[float]] = [None] * size
        mid: List[Optional[float]] = [None] * size
        lower: List[Optional[float]] = [None] * size
        bw: List[Optional[float]] = [None] * size
        for i in range(period - 1, size):
            w = closes[i - period + 1 : i + 1]
            mean = sum(w) / period
            std = (sum((v - mean) ** 2 for v in w) / period) ** 0.5
            mid[i] = mean
            upper[i] = mean + n_std * std
            lower[i] = mean - n_std * std
            bw[i] = (upper[i] - lower[i]) / mean if mean else None  # type: ignore[operator]
        return upper, mid, lower, bw

    # ── Divergence detection ───────────────────────────────────────────────────

    @staticmethod
    def _detect_rsi_divergence(
        closes: List[float], rsi_vals: List[Optional[float]], lookback: int = 60
    ) -> Tuple[str, Optional[str]]:
        """
        Compare the last two price peaks and the corresponding RSI peaks.
        Returns ("bullish"|"bearish"|"none"|"insufficient_data", note).
        """
        n = len(closes)
        if n < lookback or all(v is None for v in rsi_vals[-lookback:]):
            return "insufficient_data", None

        c_window = closes[-lookback:]
        r_window = [v for v in rsi_vals[-lookback:]]

        # Find two price highs
        price_peaks = sorted(
            [i for i in range(2, len(c_window) - 2)
             if c_window[i] >= c_window[i-1] and c_window[i] >= c_window[i-2]
             and c_window[i] >= c_window[i+1] and c_window[i] >= c_window[i+2]],
            key=lambda i: c_window[i],
            reverse=True,
        )[:2]

        if len(price_peaks) < 2:
            return "none", None

        p1, p2 = sorted(price_peaks)  # chronological
        r1 = r_window[p1]
        r2 = r_window[p2]
        if r1 is None or r2 is None:
            return "none", None

        if c_window[p2] > c_window[p1] and r2 < r1:
            return "bearish", "Price made higher high but RSI made lower high — bearish divergence."
        if c_window[p2] < c_window[p1] and r2 > r1:
            return "bullish", "Price made lower high but RSI made higher high — bullish divergence."
        return "none", None

    @staticmethod
    def _detect_macd_divergence(
        closes: List[float], macd_line: List[Optional[float]], lookback: int = 60
    ) -> Tuple[str, Optional[str]]:
        n = len(closes)
        if n < lookback:
            return "insufficient_data", None
        c_w = closes[-lookback:]
        m_w = macd_line[-lookback:]
        price_peaks = [
            i for i in range(2, len(c_w) - 2)
            if c_w[i] >= c_w[i-1] and c_w[i] >= c_w[i-2]
            and c_w[i] >= c_w[i+1] and c_w[i] >= c_w[i+2]
        ]
        if len(price_peaks) < 2:
            return "none", None
        p1, p2 = sorted(price_peaks[-2:])
        m1, m2 = m_w[p1], m_w[p2]
        if m1 is None or m2 is None:
            return "none", None
        if c_w[p2] > c_w[p1] and m2 < m1:
            return "bearish", "Price higher high, MACD lower high — bearish divergence."
        if c_w[p2] < c_w[p1] and m2 > m1:
            return "bullish", "Price lower high, MACD higher high — bullish divergence."
        return "none", None

    # ── Layer computation ──────────────────────────────────────────────────────

    def _compute_trend(self, closes: List[float], dates: List[str]) -> TrendAnalysis:
        n = len(closes)
        price = closes[-1]

        sma50_series = self._sma(closes, 50)
        sma200_series = self._sma(closes, 200)

        sma50 = sma50_series[-1]
        sma200 = sma200_series[-1]

        def _pos(price: float, sma: Optional[float]) -> str:
            if sma is None:
                return "unknown"
            return "above" if price >= sma else "below"

        def _rel(a: Optional[float], b: Optional[float]) -> str:
            if a is None or b is None:
                return "unknown"
            return "above" if a >= b else "below"

        sma200_slope = self._slope(sma200_series, lookback=20)
        sma50_slope = self._slope(sma50_series, lookback=20)

        # Golden / death cross detection (look back 60 bars)
        golden_cross = death_cross = False
        cross_bars_ago: Optional[int] = None
        lookback_cross = min(60, n)
        s50 = sma50_series[-lookback_cross:]
        s200 = sma200_series[-lookback_cross:]
        for i in range(len(s50) - 1, 0, -1):
            if s50[i] is None or s200[i] is None:
                continue
            if s50[i - 1] is None or s200[i - 1] is None:
                continue
            if s50[i] > s200[i] and s50[i - 1] <= s200[i - 1]:
                golden_cross = True
                cross_bars_ago = len(s50) - 1 - i
                break
            if s50[i] < s200[i] and s50[i - 1] >= s200[i - 1]:
                death_cross = True
                cross_bars_ago = len(s50) - 1 - i
                break

        # Primary trend classification (Murphy: 200 SMA is the arbiter)
        if sma200 is None:
            primary_trend = "sideways"
        elif price > sma200 and sma200_slope == "rising":
            primary_trend = "uptrend"
        elif price < sma200 and sma200_slope == "falling":
            primary_trend = "downtrend"
        elif price > sma200:
            primary_trend = "uptrend"
        elif price < sma200:
            primary_trend = "downtrend"
        else:
            primary_trend = "sideways"

        # Intermediate trend (50 SMA)
        if sma50 is None:
            intermediate_trend = "sideways"
        elif price > sma50 and sma50_slope != "falling":
            intermediate_trend = "uptrend"
        elif price < sma50 and sma50_slope != "rising":
            intermediate_trend = "downtrend"
        else:
            intermediate_trend = "sideways"

        # Trend strength
        if primary_trend == intermediate_trend and primary_trend != "sideways":
            strength = "strong"
        elif primary_trend == "sideways" and intermediate_trend == "sideways":
            strength = "weak"
        else:
            strength = "moderate"

        dist200 = ((price - sma200) / sma200 * 100) if sma200 else None
        dist50 = ((price - sma50) / sma50 * 100) if sma50 else None

        return TrendAnalysis(
            sma50=round(sma50, 4) if sma50 is not None else None,
            sma200=round(sma200, 4) if sma200 is not None else None,
            current_price=round(price, 4),
            price_vs_sma50=_pos(price, sma50),
            price_vs_sma200=_pos(price, sma200),
            sma50_vs_sma200=_rel(sma50, sma200),
            sma200_slope=sma200_slope,
            sma50_slope=sma50_slope,
            golden_cross=golden_cross,
            death_cross=death_cross,
            cross_bars_ago=cross_bars_ago,
            primary_trend=primary_trend,
            intermediate_trend=intermediate_trend,
            trend_strength=strength,
            distance_from_sma200_pct=round(dist200, 2) if dist200 is not None else None,
            distance_from_sma50_pct=round(dist50, 2) if dist50 is not None else None,
        )

    def _compute_momentum(self, closes: List[float]) -> MomentumAnalysis:
        macd_line, sig_line, histogram = self._macd(closes)
        rsi_series = self._wilder_rsi(closes)

        # MACD readings
        ml = macd_line[-1]
        sl = sig_line[-1]
        hl = histogram[-1]
        hl_prev = next(
            (histogram[i] for i in range(len(histogram) - 2, -1, -1)
             if histogram[i] is not None), None
        )

        zero_pos = ("above" if ml is not None and ml > 0 else "below") if ml is not None else "below"

        # Signal line crossover (last 3 bars)
        sig_cross = "none"
        for i in range(len(macd_line) - 1, max(len(macd_line) - 4, 1), -1):
            m_now, s_now = macd_line[i], sig_line[i]
            m_prev, s_prev = macd_line[i - 1], sig_line[i - 1]
            if all(v is not None for v in [m_now, s_now, m_prev, s_prev]):
                if m_now > s_now and m_prev <= s_prev:  # type: ignore[operator]
                    sig_cross = "bullish_cross"
                    break
                if m_now < s_now and m_prev >= s_prev:  # type: ignore[operator]
                    sig_cross = "bearish_cross"
                    break

        # Zero-line crossover (last 3 bars)
        zero_cross = "none"
        for i in range(len(macd_line) - 1, max(len(macd_line) - 4, 1), -1):
            m_now, m_prev = macd_line[i], macd_line[i - 1]
            if m_now is not None and m_prev is not None:
                if m_now > 0 and m_prev <= 0:
                    zero_cross = "bullish_cross"
                    break
                if m_now < 0 and m_prev >= 0:
                    zero_cross = "bearish_cross"
                    break

        # Histogram direction
        if hl is not None and hl_prev is not None:
            if hl > 0 and hl > hl_prev:
                hist_dir = "expanding_bullish"
            elif hl > 0 and hl < hl_prev:
                hist_dir = "contracting_bullish"
            elif hl < 0 and hl < hl_prev:
                hist_dir = "expanding_bearish"
            elif hl < 0 and hl > hl_prev:
                hist_dir = "contracting_bearish"
            else:
                hist_dir = "flat"
        else:
            hist_dir = "flat"

        macd_div, macd_div_note = self._detect_macd_divergence(closes, macd_line)
        rsi_div, rsi_div_note = self._detect_rsi_divergence(closes, rsi_series)

        rsi_val = rsi_series[-1]
        if rsi_val is None:
            rsi_zone = "lower_neutral"
            rsi_trend_ctx = "RSI unavailable — insufficient data."
        elif rsi_val >= 70:
            rsi_zone = "overbought"
            rsi_trend_ctx = "Overbought. In a confirmed uptrend this is NOT a sell signal — wait for divergence."
        elif rsi_val >= 55:
            rsi_zone = "upper_neutral"
            rsi_trend_ctx = "Healthy bullish momentum territory."
        elif rsi_val >= 45:
            rsi_zone = "lower_neutral"
            rsi_trend_ctx = "Neutral. Neither bullish nor bearish momentum advantage."
        else:
            rsi_zone = "oversold"
            rsi_trend_ctx = "Oversold. In a downtrend this is NOT a buy signal — wait for divergence confirmation."

        return MomentumAnalysis(
            macd=MACDReadings(
                macd_line=round(ml, 4) if ml is not None else None,
                signal_line=round(sl, 4) if sl is not None else None,
                histogram=round(hl, 4) if hl is not None else None,
                histogram_prev=round(hl_prev, 4) if hl_prev is not None else None,
                zero_line_position=zero_pos,
                signal_cross=sig_cross,
                zero_cross=zero_cross,
                histogram_direction=hist_dir,
                divergence=macd_div,
                divergence_note=macd_div_note,
            ),
            rsi=RSIReadings(
                value=round(rsi_val, 2) if rsi_val is not None else None,
                zone=rsi_zone,
                trend_context=rsi_trend_ctx,
                divergence=rsi_div,
                divergence_note=rsi_div_note,
            ),
        )

    def _compute_volume(
        self, closes: List[float], volumes: List[int]
    ) -> VolumeAnalysis:
        obv_series = self._obv(closes, volumes)
        obv_current = obv_series[-1] if obv_series else None

        # OBV slope over last 20 bars
        obv_slice = obv_series[-20:] if len(obv_series) >= 20 else obv_series
        if len(obv_slice) >= 5:
            delta = (obv_slice[-1] - obv_slice[0]) / (abs(obv_slice[0]) + 1)
            obv_trend = "rising" if delta > 0.02 else "falling" if delta < -0.02 else "flat"
        else:
            obv_trend = "flat"

        # Volume SMA
        vol_10 = sum(volumes[-10:]) / min(10, len(volumes)) if volumes else None
        vol_50 = sum(volumes[-50:]) / min(50, len(volumes)) if volumes else None
        vol_ratio = (vol_10 / vol_50) if (vol_10 and vol_50 and vol_50 > 0) else None

        # Price trend for confirmation check
        price_delta = (closes[-1] - closes[-20]) / closes[-20] if len(closes) >= 20 and closes[-20] else 0
        price_up = price_delta > 0

        obv_confirms = (price_up and obv_trend == "rising") or (not price_up and obv_trend == "falling")

        if vol_ratio and vol_ratio > 1.1 and price_up:
            vol_signal = "accumulation"
            vol_note = f"Above-average volume ({vol_ratio:.1f}x 50-bar avg) on advancing price — accumulation signal."
        elif vol_ratio and vol_ratio > 1.1 and not price_up:
            vol_signal = "distribution"
            vol_note = f"Above-average volume ({vol_ratio:.1f}x 50-bar avg) on declining price — distribution signal."
        elif obv_trend == "rising" and price_up:
            vol_signal = "accumulation"
            vol_note = "OBV rising with price — volume confirms the advance."
        elif obv_trend == "falling" and not price_up:
            vol_signal = "distribution"
            vol_note = "OBV falling with price — volume confirms the decline."
        elif obv_trend == "rising" and not price_up:
            vol_signal = "accumulation"
            vol_note = "OBV rising despite price weakness — potential bullish divergence (smart money accumulating)."
        elif obv_trend == "falling" and price_up:
            vol_signal = "distribution"
            vol_note = "OBV falling despite price advance — volume not confirming the move. Watch for reversal."
        else:
            vol_signal = "neutral"
            vol_note = "Volume trend inconclusive."

        return VolumeAnalysis(
            obv_current=round(obv_current, 0) if obv_current is not None else None,
            obv_trend=obv_trend,
            obv_confirms_price=obv_confirms,
            vol_avg_10=round(vol_10, 0) if vol_10 else None,
            vol_avg_50=round(vol_50, 0) if vol_50 else None,
            vol_ratio=round(vol_ratio, 2) if vol_ratio else None,
            volume_signal=vol_signal,
            volume_signal_note=vol_note,
        )

    def _compute_support_resistance(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
        dates: List[str],
    ) -> SupportResistanceAnalysis:
        price = closes[-1]

        ph = self._pivot_highs(highs, n=2)
        pl = self._pivot_lows(lows, n=2)

        # Keep 3 most recent pivots of each type
        recent_highs = sorted(ph, key=lambda x: x[0], reverse=True)[:3]
        recent_lows = sorted(pl, key=lambda x: x[0], reverse=True)[:3]

        levels: List[PriceLevel] = []

        for _, p in recent_highs:
            dist = (p - price) / price * 100
            strength = "strong" if abs(dist) < 3 else "moderate" if abs(dist) < 8 else "weak"
            levels.append(PriceLevel(
                price=round(p, 4),
                level_type="resistance",
                strength=strength,
                source="pivot_high",
                distance_pct=round(dist, 2),
            ))

        for _, p in recent_lows:
            dist = (p - price) / price * 100
            strength = "strong" if abs(dist) < 3 else "moderate" if abs(dist) < 8 else "weak"
            levels.append(PriceLevel(
                price=round(p, 4),
                level_type="support",
                strength=strength,
                source="pivot_low",
                distance_pct=round(dist, 2),
            ))

        # Sort by distance from current price
        levels.sort(key=lambda lv: abs(lv.distance_pct))

        nearest_support = next((lv for lv in levels if lv.level_type == "support"), None)
        nearest_resistance = next((lv for lv in levels if lv.level_type == "resistance"), None)
        in_range = bool(nearest_support and nearest_resistance)

        high_52w = max(highs[-252:]) if len(highs) >= 20 else max(highs)
        low_52w = min(lows[-252:]) if len(lows) >= 20 else min(lows)
        pct_from_high = (price - high_52w) / high_52w * 100 if high_52w else None
        pct_from_low = (price - low_52w) / low_52w * 100 if low_52w else None

        return SupportResistanceAnalysis(
            levels=levels[:8],
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            price_in_range=in_range,
            high_52w=round(high_52w, 4) if high_52w else None,
            low_52w=round(low_52w, 4) if low_52w else None,
            pct_from_52w_high=round(pct_from_high, 2) if pct_from_high is not None else None,
            pct_from_52w_low=round(pct_from_low, 2) if pct_from_low is not None else None,
        )

    def _compute_oscillators(
        self,
        highs: List[float],
        lows: List[float],
        closes: List[float],
    ) -> OscillatorAnalysis:
        # Bollinger Bands
        bb_upper, bb_mid, bb_lower, bb_bw = self._bollinger(closes, period=20, n_std=2.0)
        bbu, bbm, bbl, bwidth = bb_upper[-1], bb_mid[-1], bb_lower[-1], bb_bw[-1]
        price = closes[-1]

        if bbu is None or bbl is None or bbm is None:
            bb_pos = "middle"
            squeeze = False
        elif price > bbu:
            bb_pos = "above_upper"
            squeeze = False
        elif price >= bbu * 0.98:
            bb_pos = "near_upper"
            squeeze = False
        elif price <= bbl:
            bb_pos = "below_lower"
            squeeze = False
        elif price <= bbl * 1.02:
            bb_pos = "near_lower"
            squeeze = False
        else:
            bb_pos = "middle"
            squeeze = False

        # Bandwidth percentile (compare to last 52 bars of bandwidth)
        bw_history = [v for v in bb_bw[-52:] if v is not None]
        if bwidth is not None and len(bw_history) >= 10:
            below = sum(1 for v in bw_history if v <= bwidth)
            bw_pct = round(below / len(bw_history) * 100)
            squeeze = bw_pct <= 20   # bottom quintile of recent bandwidth = compression
        else:
            bw_pct = None
            squeeze = False

        # Stochastic
        k_line, d_line = self._stochastic(highs, lows, closes)
        k_val = k_line[-1]
        d_val = d_line[-1]

        if k_val is None:
            stoch_zone = "neutral"
            stoch_signal = "none"
        elif k_val >= 80:
            stoch_zone = "overbought"
            stoch_signal = "none"
        elif k_val <= 20:
            stoch_zone = "oversold"
            stoch_signal = "none"
        else:
            stoch_zone = "neutral"
            stoch_signal = "none"

        # Stochastic crossover (last 3 bars)
        for i in range(len(k_line) - 1, max(len(k_line) - 4, 1), -1):
            k_now, d_now = k_line[i], d_line[i]
            k_prev, d_prev = k_line[i - 1], d_line[i - 1]
            if all(v is not None for v in [k_now, d_now, k_prev, d_prev]):
                if k_now > d_now and k_prev <= d_prev:  # type: ignore[operator]
                    stoch_signal = "bullish_cross"
                    break
                if k_now < d_now and k_prev >= d_prev:  # type: ignore[operator]
                    stoch_signal = "bearish_cross"
                    break

        return OscillatorAnalysis(
            bollinger=BollingerReadings(
                upper=round(bbu, 4) if bbu is not None else None,
                middle=round(bbm, 4) if bbm is not None else None,
                lower=round(bbl, 4) if bbl is not None else None,
                bandwidth=round(bwidth, 4) if bwidth is not None else None,
                bandwidth_percentile=bw_pct,
                price_position=bb_pos,
                squeeze=squeeze,
            ),
            stochastic=StochasticReadings(
                k_line=round(k_val, 2) if k_val is not None else None,
                d_line=round(d_val, 2) if d_val is not None else None,
                zone=stoch_zone,
                signal=stoch_signal,
            ),
        )

    # ── Murphy synthesis ───────────────────────────────────────────────────────

    def _compute_synthesis(
        self,
        trend: TrendAnalysis,
        momentum: MomentumAnalysis,
        volume: VolumeAnalysis,
        oscillators: OscillatorAnalysis,
        dq: TechnicalDataQuality,
    ) -> MurphySynthesis:
        """
        Murphy's rule: trend > volume > momentum > oscillators.
        An overbought oscillator in a confirmed uptrend is not a sell signal.
        """
        observations: List[str] = []
        conflicts: List[str] = []
        score = 50  # start neutral

        # ── Layer 1: Trend (most important) ───────────────────────────────────
        if trend.primary_trend == "uptrend" and trend.sma200_slope == "rising":
            score += 20
            observations.append(
                f"Price is above its rising 200-day SMA ({trend.sma200:.2f}) — primary uptrend confirmed."
                if trend.sma200 else "Primary uptrend confirmed by 200-day SMA."
            )
            dominant = "trend"
        elif trend.primary_trend == "downtrend" and trend.sma200_slope == "falling":
            score -= 20
            observations.append(
                f"Price is below its falling 200-day SMA ({trend.sma200:.2f}) — primary downtrend in force."
                if trend.sma200 else "Primary downtrend in force."
            )
            dominant = "trend"
        elif trend.primary_trend == "uptrend":
            score += 10
            observations.append("Price is above the 200-day SMA — uptrend bias, but SMA not yet rising.")
            dominant = "trend"
        elif trend.primary_trend == "downtrend":
            score -= 10
            observations.append("Price is below the 200-day SMA — downtrend bias.")
            dominant = "trend"
        else:
            observations.append("200-day SMA is flat — no clear primary trend. Range-bound conditions.")
            dominant = "momentum"

        # Golden/death cross
        if trend.golden_cross:
            score += 10
            obs = "Golden Cross confirmed"
            if trend.cross_bars_ago is not None:
                obs += f" ({trend.cross_bars_ago} bars ago)"
            observations.append(obs + " — bullish intermediate signal.")
        elif trend.death_cross:
            score -= 10
            obs = "Death Cross confirmed"
            if trend.cross_bars_ago is not None:
                obs += f" ({trend.cross_bars_ago} bars ago)"
            observations.append(obs + " — bearish intermediate signal.")

        # ── Layer 2: Volume ────────────────────────────────────────────────────
        if volume.volume_signal == "accumulation":
            score += 8
            if dominant == "momentum":
                dominant = "volume"
            observations.append(volume.volume_signal_note)
        elif volume.volume_signal == "distribution":
            score -= 8
            if dominant == "momentum":
                dominant = "volume"
            observations.append(volume.volume_signal_note)
            if trend.primary_trend == "uptrend":
                conflicts.append("Price in uptrend but volume showing distribution — watch for potential top.")

        if not volume.obv_confirms_price and volume.volume_signal != "neutral":
            conflicts.append("OBV is not confirming the price trend direction.")

        # ── Layer 3: Momentum / MACD ───────────────────────────────────────────
        macd = momentum.macd
        if macd.zero_cross == "bullish_cross":
            score += 12
            observations.append("MACD crossed above zero line — stronger bullish momentum signal.")
            dominant = "momentum" if dominant not in ("trend",) else dominant
        elif macd.zero_cross == "bearish_cross":
            score -= 12
            observations.append("MACD crossed below zero line — stronger bearish momentum signal.")
        elif macd.signal_cross == "bullish_cross":
            score += 6
            observations.append("MACD bullish signal-line crossover — weaker momentum signal.")
        elif macd.signal_cross == "bearish_cross":
            score -= 6
            observations.append("MACD bearish signal-line crossover.")

        if macd.divergence == "bearish":
            score -= 8
            conflicts.append(f"MACD: {macd.divergence_note}")
        elif macd.divergence == "bullish":
            score += 8
            observations.append(f"MACD: {macd.divergence_note}")

        # RSI — only use as timing within trend context
        rsi = momentum.rsi
        if rsi.value is not None:
            if rsi.zone == "overbought" and trend.primary_trend != "uptrend":
                score -= 5
                conflicts.append(f"RSI at {rsi.value:.1f} — overbought outside of uptrend.")
            elif rsi.zone == "oversold" and trend.primary_trend != "downtrend":
                score += 5
                observations.append(f"RSI at {rsi.value:.1f} — oversold, potential mean-reversion setup.")

        if rsi.divergence == "bearish" and rsi.divergence_note:
            score -= 6
            conflicts.append(f"RSI: {rsi.divergence_note}")
        elif rsi.divergence == "bullish" and rsi.divergence_note:
            score += 6
            observations.append(f"RSI: {rsi.divergence_note}")

        # ── Layer 4: Oscillators (weakest signal) ──────────────────────────────
        bb = oscillators.bollinger
        if bb.squeeze:
            observations.append(
                "Bollinger Band squeeze detected — volatility compression often precedes a significant move."
            )
        if bb.price_position == "above_upper" and trend.primary_trend != "uptrend":
            score -= 4
        elif bb.price_position == "below_lower" and trend.primary_trend != "downtrend":
            score += 4

        stoch = oscillators.stochastic
        if stoch.signal == "bullish_cross" and stoch.zone == "oversold":
            score += 5
            observations.append("Stochastic bullish crossover from oversold — short-term timing signal.")
        elif stoch.signal == "bearish_cross" and stoch.zone == "overbought":
            score -= 5

        # ── Clamp and classify ─────────────────────────────────────────────────
        score = max(0, min(100, score))

        if score >= 75:
            overall = "strong_buy"
            risk = "low"
        elif score >= 60:
            overall = "buy"
            risk = "moderate"
        elif score >= 40:
            overall = "neutral"
            risk = "moderate"
        elif score >= 25:
            overall = "sell"
            risk = "high"
        else:
            overall = "strong_sell"
            risk = "high"

        dominant_notes = {
            "trend": "Primary and intermediate trend alignment is the dominant signal.",
            "volume": "Volume analysis is providing the clearest signal in this reading.",
            "momentum": "Momentum indicators (MACD/RSI) are driving the synthesis — trend is ambiguous.",
            "oscillators": "Oscillator signals are in focus; use with caution in absence of clear trend.",
        }

        caution = None
        if not dq.sufficient_for_full_analysis:
            caution = (
                f"Only {dq.bars_available} daily bars available "
                f"(200+ recommended). Indicators requiring more data are marked degraded."
            )

        return MurphySynthesis(
            overall_signal=overall,
            signal_strength=score,
            risk_level=risk,
            dominant_factor=dominant,
            dominant_factor_note=dominant_notes.get(dominant, ""),
            key_observations=observations[:5],
            conflicts=conflicts[:3],
            caution_note=caution,
        )