"""
FX rate provider — fetches live exchange rates from yfinance.

Uses yfinance ticker symbols like CADUSD=X or USDCAD=X.
Uses yf.download() (historical endpoint) instead of ticker.info to avoid
heavy scraping that can return partial data.
"""

import logging
import math
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_fx_rate(base: str, target: str) -> Decimal | None:
    """Fetch live FX rate via yfinance.

    Uses the last 5 trading days of history and returns the most recent close.
    Handles MultiIndex columns that newer yfinance versions may return.

    Returns Decimal for clean boundary from float arithmetic.
    """
    symbol = f"{base.upper()}{target.upper()}=X"
    try:
        df = yf.download(symbol, period="5d", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None

        close_series = df["Close"]
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]

        close = close_series.dropna().iloc[-1]
        if close is not None and not (isinstance(close, float) and math.isnan(close)):
            return Decimal(str(round(float(close), 8)))
    except Exception as e:
        logger.warning("Failed to fetch FX rate for %s: %s", symbol, e)
    return None


def fetch_fx_history(
    base: str, target: str, start_date: date, end_date: date
) -> list[tuple[date, Decimal]]:
    """Fetch daily FX closes between start_date and end_date (inclusive).

    Returns [(close_date, Decimal(close)), ...] ascending by close_date.
    Every close is stamped under its ACTUAL calendar date - unlike
    fetch_fx_rate, which only returns the most recent close. This is what
    keeps an as-of lookup for any date in the window resolvable.

    Returns an empty list on failure or empty data (never None).
    """
    symbol = f"{base.upper()}{target.upper()}=X"
    try:
        df = yf.download(
            symbol,
            start=start_date.isoformat(),
            end=(end_date + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            progress=False,
            interval="1d",
        )
        if df is None or df.empty:
            return []

        close_series = df["Close"]
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
        close_series = close_series.dropna()

        out: list[tuple[date, Decimal]] = []
        for idx, close in close_series.items():
            ts = idx.date() if hasattr(idx, "date") else pd.Timestamp(idx).date()
            if isinstance(close, float) and math.isnan(close):
                continue
            out.append((ts, Decimal(str(round(float(close), 8)))))
        out.sort(key=lambda t: t[0])
        return out
    except Exception as e:
        logger.warning("Failed to fetch FX history for %s: %s", symbol, e)
        return []
