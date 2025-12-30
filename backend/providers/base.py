
from abc import ABC, abstractmethod
from typing import Optional
from pydantic import BaseModel
from datetime import date

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
    open_price: Optional[float] = None
    high_price: Optional[float] = None
    low_price: Optional[float] = None
    close_price: Optional[float] = None
    volume: Optional[int] = None
    market_state: Optional[str] = None

    # Company Info
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    currency: Optional[str] = None
    fiscal_year_end_month: Optional[int] = None
    description: Optional[str] = None
    website: Optional[str] = None
    next_earnings_date: Optional[date] = None

class StockDataProvider(ABC):
    @abstractmethod
    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]:
        pass

    @abstractmethod
    def get_stock_details(self, ticker_symbol: str) -> Optional[StockDetails]:
        pass
