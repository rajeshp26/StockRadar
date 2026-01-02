from abc import ABC, abstractmethod
from typing import Dict, List, Any

class StockProvider(ABC):
    @abstractmethod
    def get_tickers_data(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch real-time data for multiple symbols"""
        pass

    @abstractmethod
    def get_ticker_info(self, symbol: str) -> Dict[str, Any]:
        """Fetch detailed info for a single symbol"""
        pass
