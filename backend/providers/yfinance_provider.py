
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
    """
    Add this method to your YFinanceProvider class
    Extracts earnings data including estimates and surprises
    """

def get_earnings_data(self, ticker_symbol: str) -> Optional[List[Dict[str, Any]]]:
    """
    Extract earnings data from yfinance including estimates and surprises.
    
    Returns list of earnings records with:
    - fiscal_year, fiscal_quarter
    - eps_estimate, eps_reported, eps_surprise_percent
    - revenue_estimate, revenue_reported, revenue_surprise_percent
    - announcement_date
    
    Args:
        ticker_symbol: Stock ticker (e.g., 'TSLA')
    
    Returns:
        List of earnings dicts, or None if not available
    """
    try:
        ticker = yf.Ticker(ticker_symbol.upper())
        info = ticker.info
        
        earnings_list = []
        
        # Try to get calendar data (next earnings date + history)
        try:
            calendar = ticker.calendar
            if calendar is not None and not calendar.empty:
                # calendar has columns: ['Earnings Date', 'Earnings Average', 'Earnings Low', 'Earnings High', 'Revenue Estimate', 'Report Date']
                for idx, row in calendar.iterrows():
                    try:
                        earnings_date = row.get('Earnings Date')
                        if pd.isna(earnings_date):
                            continue
                        
                        # Convert to date
                        if isinstance(earnings_date, str):
                            earnings_date = datetime.strptime(earnings_date, "%Y-%m-%d").date()
                        elif isinstance(earnings_date, pd.Timestamp):
                            earnings_date = earnings_date.date()
                        
                        # Try to infer fiscal period from earnings date
                        # This is approximate - ideally use report_date
                        report_date = row.get('Report Date')
                        if pd.notna(report_date):
                            if isinstance(report_date, str):
                                report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
                            elif isinstance(report_date, pd.Timestamp):
                                report_date = report_date.date()
                        else:
                            report_date = earnings_date
                        
                        fiscal_year = report_date.year
                        fiscal_month = report_date.month
                        fiscal_quarter = (fiscal_month - 1) // 3 + 1
                        
                        # Extract earnings metrics
                        eps_estimate = row.get('Earnings Average')
                        eps_low = row.get('Earnings Low')
                        eps_high = row.get('Earnings High')
                        
                        revenue_estimate = row.get('Revenue Estimate')
                        
                        earnings_record = {
                            'fiscal_year': fiscal_year,
                            'fiscal_quarter': fiscal_quarter,
                            'announcement_date': earnings_date,
                            'report_date': report_date,
                            'eps_estimate': self._safe_float(eps_estimate),
                            'eps_reported': None,  # Not available in calendar
                            'eps_surprise_amount': None,
                            'eps_surprise_percent': None,
                            'revenue_estimate': self._safe_float(revenue_estimate),
                            'revenue_reported': None,  # Not available in calendar
                            'revenue_surprise_amount': None,
                            'revenue_surprise_percent': None,
                        }
                        earnings_list.append(earnings_record)
                    
                    except Exception as e:
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.debug(f"Error parsing calendar row for {ticker_symbol}: {str(e)}")
                        continue
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to fetch calendar for {ticker_symbol}: {str(e)}")
        
        # Try to get earnings dates and history from quarterly financials
        try:
            quarterly_financials = ticker.quarterly_financials
            if quarterly_financials is not None and not quarterly_financials.empty:
                # Columns are dates, extract fiscal info from dates
                for col_date in quarterly_financials.columns:
                    if isinstance(col_date, pd.Timestamp):
                        fiscal_year = col_date.year
                        fiscal_month = col_date.month
                        fiscal_quarter = (fiscal_month - 1) // 3 + 1
                        
                        # Check if this period already exists in earnings_list
                        exists = any(
                            e['fiscal_year'] == fiscal_year and e['fiscal_quarter'] == fiscal_quarter
                            for e in earnings_list
                        )
                        
                        if not exists:
                            earnings_record = {
                                'fiscal_year': fiscal_year,
                                'fiscal_quarter': fiscal_quarter,
                                'announcement_date': None,
                                'report_date': col_date.date(),
                                'eps_estimate': None,
                                'eps_reported': None,
                                'eps_surprise_amount': None,
                                'eps_surprise_percent': None,
                                'revenue_estimate': None,
                                'revenue_reported': None,
                                'revenue_surprise_amount': None,
                                'revenue_surprise_percent': None,
                            }
                            earnings_list.append(earnings_record)
        
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Failed to fetch quarterly financials for {ticker_symbol}: {str(e)}")
        
        # Sort by fiscal year and quarter
        earnings_list.sort(key=lambda x: (x['fiscal_year'], x['fiscal_quarter']), reverse=True)
        
        if earnings_list:
            return earnings_list
        
        return None
    
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Failed to get earnings data for {ticker_symbol}: {str(e)}")
        return None

def _safe_float(self, val) -> Optional[float]:
    """Safely convert value to float."""
    if val is None:
        return None
    if isinstance(val, float):
        if val != val:  # NaN check
            return None
        return val
    try:
        return float(val)
    except (ValueError, TypeError):
        return None