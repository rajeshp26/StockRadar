"""
FX rate provider — fetches live exchange rates from yfinance.

Uses yfinance ticker symbols like CADUSD=X or USDCAD=X.
Uses yf.download() (historical endpoint) instead of ticker.info to avoid
heavy scraping that can return partial data.
"""

from decimal import Decimal
from typing import Optional
import logging
import math

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


def fetch_fx_rate(base: str, target: str) -> Optional[Decimal]:
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
