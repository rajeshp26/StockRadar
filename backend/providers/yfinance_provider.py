
from .base import StockDataProvider, TickerInfo, StockDetails
from domain.interfaces.stock_provider import StockProvider
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import yfinance as yf
import pandas as pd

logger = logging.getLogger(__name__)

class YFinanceProvider(StockDataProvider, StockProvider):
    def __init__(self):
        self._cache: Dict[str, StockDetails] = {}

    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]:
        details = self.get_stock_details(ticker_symbol)
        if details:
            return TickerInfo(long_name=details.long_name, ticker_symbol=details.ticker_symbol)
        return None

    def get_stock_details(self, ticker_symbol: str) -> Optional[StockDetails]:
        ticker_upper = ticker_symbol.upper()
        if ticker_upper in self._cache:
            return self._cache[ticker_upper]

        try:
            tkr = yf.Ticker(ticker_upper)
            info = tkr.info or {}

            long_name = info.get('longName', info.get('shortName'))
            current_price_val = info.get('postMarketPrice') or info.get('currentPrice') or info.get('regularMarketPrice')
            previous_close_val = info.get('regularMarketPreviousClose') or info.get('previousClose')

            if not long_name or current_price_val is None or previous_close_val is None:
                return None

            current_price = float(current_price_val)
            previous_close = float(previous_close_val)
            change = current_price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else 0.0

            earnings_date = None
            ts = info.get('earningsTimestamp')
            if ts:
                try:
                    earnings_date = datetime.fromtimestamp(ts).date()
                except (ValueError, TypeError):
                    pass

            details = StockDetails(
                long_name=long_name,
                ticker_symbol=ticker_upper,
                price=current_price,
                change=change,
                change_percent=change_percent,

                open_price=info.get('regularMarketOpen'),
                high_price=info.get('regularMarketDayHigh'),
                low_price=info.get('regularMarketDayLow'),
                close_price=info.get('regularMarketPreviousClose'),
                volume=info.get('regularMarketVolume'),
                market_state=info.get('marketState'),

                exchange=info.get('exchange'),
                sector=info.get('sector'),
                industry=info.get('industry'),
                currency=info.get('currency'),
                fiscal_year_end_month=None,
                description=info.get('longBusinessSummary'),
                website=info.get('website'),
                next_earnings_date=earnings_date
            )

            self._cache[ticker_upper] = details
            return details

        except Exception as e:
            logger.warning(f"YFinance Error for {ticker_symbol}: {e}")
            return None

    def get_tickers_data(self, ticker_symbols: List[str]) -> Dict[str, Any]:
        if not ticker_symbols:
            return {}
        tickers = yf.Tickers(ticker_symbols)
        return tickers.tickers

    # ---------------------------
    # Statement getters (DataFrames)
    # ---------------------------
    def get_annual_income_statement_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        return tkr.financials if isinstance(tkr.financials, pd.DataFrame) else pd.DataFrame()

    def get_quarterly_income_statement_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        return tkr.quarterly_financials if isinstance(tkr.quarterly_financials, pd.DataFrame) else pd.DataFrame()

    def get_annual_balance_sheet_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        return tkr.balance_sheet if isinstance(tkr.balance_sheet, pd.DataFrame) else pd.DataFrame()

    def get_quarterly_balance_sheet_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        return tkr.quarterly_balance_sheet if isinstance(tkr.quarterly_balance_sheet, pd.DataFrame) else pd.DataFrame()

    def get_annual_cash_flow_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        return tkr.cashflow if isinstance(tkr.cashflow, pd.DataFrame) else pd.DataFrame()

    def get_quarterly_cash_flow_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        return tkr.quarterly_cashflow if isinstance(tkr.quarterly_cashflow, pd.DataFrame) else pd.DataFrame()

    def get_dividends_df(self, symbol: str) -> pd.DataFrame:
        tkr = yf.Ticker(symbol.upper())
        ser = tkr.dividends
        if ser is None:
            return pd.DataFrame()
        if isinstance(ser, pd.Series):
            df = ser.to_frame(name='Dividend').reset_index()
            df.rename(columns={'Date': 'ex_dividend_date'}, inplace=True)
            return df
        if isinstance(ser, pd.DataFrame):
            return ser
        return pd.DataFrame()

    # ---------------------------
    # Earnings data (best-effort)
    # ---------------------------
    def get_earnings_data(self, ticker_symbol: str) -> Optional[List[Dict[str, Any]]]:
        """
        Returns list of dicts with fiscal_year, fiscal_quarter,
        report_date, announcement_date, eps_estimate, revenue_estimate, (best-effort).
        """
        try:
            tkr = yf.Ticker(ticker_symbol.upper())
            earnings_list: List[Dict[str, Any]] = []

            # Calendar (future/scheduled with estimates)
            try:
                calendar = tkr.calendar
                if calendar is not None and not calendar.empty:
                    for _, row in calendar.iterrows():
                        try:
                            earnings_date = row.get('Earnings Date')
                            if pd.isna(earnings_date):
                                continue
                            if isinstance(earnings_date, str):
                                earnings_date = datetime.strptime(earnings_date, "%Y-%m-%d").date()
                            elif isinstance(earnings_date, pd.Timestamp):
                                earnings_date = earnings_date.date()

                            report_date = row.get('Report Date')
                            if pd.notna(report_date):
                                if isinstance(report_date, str):
                                    report_date = datetime.strptime(report_date, "%Y-%m-%d").date()
                                elif isinstance(report_date, pd.Timestamp):
                                    report_date = report_date.date()
                            else:
                                report_date = earnings_date

                            fy = report_date.year
                            fq = (report_date.month - 1) // 3 + 1

                            earnings_list.append({
                                'fiscal_year': fy,
                                'fiscal_quarter': fq,
                                'announcement_date': earnings_date,
                                'report_date': report_date,
                                'eps_estimate': self._safe_float(row.get('Earnings Average')),
                                'eps_reported': None,
                                'eps_surprise_amount': None,
                                'eps_surprise_percent': None,
                                'revenue_estimate': self._safe_float(row.get('Revenue Estimate')),
                                'revenue_reported': None,
                                'revenue_surprise_amount': None,
                                'revenue_surprise_percent': None,
                            })
                        except Exception as e:
                            logger.debug(f"Error parsing calendar row for {ticker_symbol}: {e}")
                            continue
            except Exception as e:
                logger.debug(f"Failed to fetch calendar for {ticker_symbol}: {e}")

            # Quarterly financials → infer periods (no EPS/rev surprises here)
            try:
                q_fin = tkr.quarterly_financials
                if q_fin is not None and not q_fin.empty:
                    for col_date in q_fin.columns:
                        if isinstance(col_date, pd.Timestamp):
                            fy = col_date.year
                            fq = (col_date.month - 1) // 3 + 1
                            if not any(e['fiscal_year'] == fy and e['fiscal_quarter'] == fq for e in earnings_list):
                                earnings_list.append({
                                    'fiscal_year': fy,
                                    'fiscal_quarter': fq,
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
                                })
            except Exception as e:
                logger.debug(f"Failed to fetch quarterly financials for {ticker_symbol}: {e}")

            earnings_list.sort(key=lambda x: (x['fiscal_year'], x['fiscal_quarter']), reverse=True)
            return earnings_list if earnings_list else None

        except Exception as e:
            logger.warning(f"Failed to get earnings data for {ticker_symbol}: {e}")
            return None

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        if val is None:
            return None
        try:
            f = float(val)
            return f if f == f else None  # NaN check
        except (ValueError, TypeError):
            return None
