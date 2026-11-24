from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from domain.listing_identity import normalize_provider_symbol
from shared.time_utils import now_utc

logger = logging.getLogger(__name__)


class PriceDataProvider:
    """Centralized price data fetching with caching."""

    _cache: dict[str, tuple[pd.DataFrame, date, date]] = {}

    # Exchange suffixes for yfinance (TSX/TSXV/NEO) — matches yfinance_provider.EXCHANGE_SUFFIX_MAP
    _EXCHANGE_SUFFIX_MAP: dict[str, str] = {
        "TOR": ".TO", "TSX": ".TO", "TO": ".TO",
        "VAN": ".V", "TSXV": ".V", "V": ".V",
        "CNQ": ".V", "NEO": ".NE",
    }

    def __init__(self, timeout: int = 15):
        self._timeout = timeout

    def _cache_key(self, symbols: tuple[str, ...], start: date, end: date) -> str:
        return f"{','.join(sorted(symbols))}:{start.isoformat()}:{end.isoformat()}"

    @staticmethod
    def _resolve_symbol(symbol: str, exchange: str | None = None) -> str:
        sym = normalize_provider_symbol(symbol)
        if exchange:
            suffix = PriceDataProvider._EXCHANGE_SUFFIX_MAP.get(exchange.upper())
            # Idempotent: skip suffix if the symbol already carries it
            # (e.g. "BCE.TO" + ".TO" would produce the invalid "BCE.TO.TO").
            if suffix and not sym.endswith(suffix):
                return sym + suffix
        return sym

    def fetch_prices(
        self,
        symbols: list[str],
        start: date,
        end: date | None = None,
        min_periods: int = 30,
        exchange: str | None = None,
    ) -> pd.DataFrame:
        end = end or now_utc().date()
        key = self._cache_key(tuple(symbols), start, end)
        if key in self._cache:
            cached, cached_start, cached_end = self._cache[key]
            if cached_start <= start and cached_end >= end:
                if cached.shape[0] >= min_periods and cached.shape[1] >= 2:
                    return cached

        import yfinance as yf

        resolved = [self._resolve_symbol(s, exchange) for s in symbols]
        try:
            raw = yf.download(
                resolved,
                start=start.isoformat(),
                end=end.isoformat(),
                auto_adjust=True,
                progress=False,
                timeout=self._timeout,
            )
        except Exception:
            return pd.DataFrame()

        if isinstance(raw.columns, pd.MultiIndex):
            prices = raw["Close"].dropna(axis=1, how="all")
        else:
            prices = raw.dropna(axis=1, how="all")
        prices = prices.ffill().dropna()

        self._cache[key] = (prices, start, end)
        return prices

    def clear_cache(self) -> None:
        self._cache.clear()
