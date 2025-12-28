from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel

class TickerInfo(BaseModel):
    """Standardized model for ticker information from any provider."""
    long_name: str
    ticker_symbol: str

class StockDataProvider(ABC):
    """Abstract base class for a stock data provider."""

    @abstractmethod
    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]:
        """Fetches information for a given ticker symbol."""
        pass
