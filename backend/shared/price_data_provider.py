from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class PriceDataProvider:
    """Centralized price data fetching with caching."""

    _cache: Dict[str, Tuple[pd.DataFrame, date, date]] = {}

    def __init__(self, timeout: int = 15):
        self._timeout = timeout

    def _cache_key(self, symbols: Tuple[str, ...], start: date, end: date) -> str:
        return f"{','.join(sorted(symbols))}:{start.isoformat()}:{end.isoformat()}"

    def fetch_prices(
        self,
        symbols: List[str],
        start: date,
        end: Optional[date] = None,
        min_periods: int = 30,
    ) -> pd.DataFrame:
        end = end or date.today()
        key = self._cache_key(tuple(symbols), start, end)
        if key in self._cache:
            cached, cached_start, cached_end = self._cache[key]
            if cached_start <= start and cached_end >= end:
                if cached.shape[0] >= min_periods and cached.shape[1] >= 2:
                    return cached

        import yfinance as yf

        raw = yf.download(
            symbols,
            start=start.isoformat(),
            end=end.isoformat(),
            auto_adjust=True,
            progress=False,
            timeout=self._timeout,
        )
        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"].dropna(axis=1, how="all")
        else:
            prices = raw.dropna(axis=1, how="all")
        prices = prices.ffill().dropna()

        self._cache[key] = (prices, start, end)
        return prices

    def clear_cache(self) -> None:
        self._cache.clear()
