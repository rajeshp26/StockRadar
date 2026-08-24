
from abc import ABC, abstractmethod
from datetime import date

from pydantic import BaseModel


class TickerInfo(BaseModel):
    """Standardized model for basic ticker information."""
    long_name: str
    ticker_symbol: str

class StockDetails(TickerInfo):
    """
    Comprehensive stock data model mapping to companies and current_market_data tables.
    """
    # Market Data
    price: float
    change: float
    change_percent: float
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    close_price: float | None = None
    volume: int | None = None
    market_state: str | None = None

    # Company Info
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None
    fiscal_year_end_month: int | None = None
    description: str | None = None
    website: str | None = None
    next_earnings_date: date | None = None

    # Classification (from yfinance quoteType)
    quote_type: str | None = None

class StockDataProvider(ABC):
    @abstractmethod
    def get_ticker_info(self, ticker_symbol: str) -> TickerInfo | None:
        pass

    @abstractmethod
    def get_stock_details(self, ticker_symbol: str) -> StockDetails | None:
        pass
