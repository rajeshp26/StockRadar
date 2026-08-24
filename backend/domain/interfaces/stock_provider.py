from abc import ABC, abstractmethod
from typing import Any


class StockProvider(ABC):
    @abstractmethod
    def get_tickers_data(self, symbols: list[str]) -> dict[str, Any]:
        """Fetch real-time data for multiple symbols"""
        pass

    @abstractmethod
    def get_ticker_info(self, symbol: str) -> dict[str, Any]:
        """Fetch detailed info for a single symbol"""
        pass
