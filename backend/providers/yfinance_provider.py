from .base import StockDataProvider, TickerInfo
from typing import Optional
import yfinance as yf

class YFinanceProvider(StockDataProvider):
    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]:
        """
        Fetches ticker information from Yahoo Finance.
        Returns a TickerInfo object if the ticker is valid, otherwise None.
        """
        ticker = yf.Ticker(ticker_symbol)
        
        # Check for essential data to validate the ticker
        if not ticker.info or not ticker.info.get('longName'):
            return None
            
        return TickerInfo(
            long_name=ticker.info.get('longName', ticker.info.get('shortName', ticker_symbol)),
            ticker_symbol=ticker_symbol.upper()
        )
