
from .base import StockDataProvider, TickerInfo, StockDetails
from domain.interfaces.stock_provider import StockProvider
from typing import Optional, List, Dict, Any
import yfinance as yf
from datetime import datetime, date

class YFinanceProvider(StockDataProvider, StockProvider):
    def __init__(self):
        self._cache: Dict[str, StockDetails] = {}

    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]:
        details = self.get_stock_details(ticker_symbol)
        if details:
            return TickerInfo(long_name=details.long_name, ticker_symbol=details.ticker_symbol)
        return None

    def get_stock_details(self, ticker_symbol: str) -> Optional[StockDetails]:
        # Check cache first
        ticker_upper = ticker_symbol.upper()
        if ticker_upper in self._cache:
            return self._cache[ticker_upper]

        try:
            ticker = yf.Ticker(ticker_upper)
            info = ticker.info

            long_name = info.get('longName', info.get('shortName'))
            
            # Robust price logic
            current_price_val = info.get('postMarketPrice') or info.get('currentPrice') or info.get('regularMarketPrice')
            previous_close_val = info.get('regularMarketPreviousClose') or info.get('previousClose')

            if not long_name or current_price_val is None or previous_close_val is None:
                return None

            current_price = float(current_price_val)
            previous_close = float(previous_close_val)
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close != 0 else 0

            # Date conversion
            earnings_date = None
            if info.get('earningsTimestamp'):
                try:
                    earnings_date = datetime.fromtimestamp(info['earningsTimestamp']).date()
                except (ValueError, TypeError):
                    pass

            details = StockDetails(
                long_name=long_name,
                ticker_symbol=ticker_upper,
                price=current_price,
                change=change,
                change_percent=change_percent,
                
                # Market Data
                open_price=info.get('regularMarketOpen'),
                high_price=info.get('regularMarketDayHigh'),
                low_price=info.get('regularMarketDayLow'),
                close_price=info.get('regularMarketPreviousClose'),
                volume=info.get('regularMarketVolume'),
                market_state=info.get('marketState'),

                # Company Info
                exchange=info.get('exchange'),
                sector=info.get('sector'),
                industry=info.get('industry'),
                currency=info.get('currency'),
                fiscal_year_end_month=None, # Not reliably in basic info
                description=info.get('longBusinessSummary'),
                website=info.get('website'),
                next_earnings_date=earnings_date
            )
            
            # Update cache
            self._cache[ticker_upper] = details
            return details

        except Exception as e:
            print(f"YFinance Error for {ticker_symbol}: {e}")
            return None

    def get_tickers_data(self, ticker_symbols: List[str]) -> Dict[str, Any]:
        if not ticker_symbols:
            return {}
        tickers = yf.Tickers(ticker_symbols)
        return tickers.tickers
