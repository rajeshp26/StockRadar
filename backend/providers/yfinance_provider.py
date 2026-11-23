
import asyncio
import logging
import time
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import yfinance as yf

from domain.interfaces.stock_provider import StockProvider
from domain.provider_resilience import get_provider_pacer
from shared.time_utils import now_utc, parse_db_timestamp

from .base import StockDataProvider, StockDetails, TickerInfo

logger = logging.getLogger(__name__)


# Exchange codes known to be Canadian TSX/TSXV/NEO — yfinance requires .TO /.V suffix
EXCHANGE_SUFFIX_MAP: dict[str, str] = {
    "TOR": ".TO", "TSX": ".TO", "TO": ".TO",
    "VAN": ".V", "TSXV": ".V", "V": ".V",
    "CNQ": ".V", "NEO": ".NE",
}


class YFinanceProvider(StockDataProvider, StockProvider):
    """
    yfinance fallback provider with helpers for:
      - annual/quarterly statements
      - dividends
      - best-effort earnings data (calendar + inferred periods)
      - NEW: price history (daily OHLCV), splits, summary snapshot
    """
    def __init__(self):
        self._cache: dict[str, StockDetails] = {}

    def _resolve_symbol(self, ticker_symbol: str, exchange: str | None = None) -> str:
        """Resolve a ticker symbol to YFinance-compatible form.

        When exchange is known and maps to a Canadian exchange, append the
        required yfinance suffix (.TO / .V) so the symbol works directly.
        When exchange is not known, return the symbol as-is — the caller
        can fall back through .TO / .V suffixes on failure.
        """
        symbol = ticker_symbol.upper()
        if exchange:
            suffix = EXCHANGE_SUFFIX_MAP.get(exchange.upper())
            # Idempotent: skip suffix if the stored symbol already carries it
            # (e.g. "BCE.TO" + ".TO" would produce the invalid "BCE.TO.TO").
            if suffix and not symbol.endswith(suffix):
                return symbol + suffix
        return symbol

    def get_ticker_info(self, ticker_symbol: str, exchange: str | None = None) -> TickerInfo | None:
        details = self.get_stock_details(ticker_symbol, exchange=exchange)
        if details:
            return TickerInfo(long_name=details.long_name, ticker_symbol=details.ticker_symbol)
        return None

    def get_stock_details(self, ticker_symbol: str, exchange: str | None = None) -> StockDetails | None:
        ticker_upper = self._resolve_symbol(ticker_symbol, exchange)
        if ticker_upper in self._cache:
            return self._cache[ticker_upper]

        try:
            # Share one throttle with the price monitor: Yahoo limits the egress,
            # not the caller, so every yfinance entry point must use one clock.
            wait = get_provider_pacer().acquire()
            if wait > 0:
                time.sleep(wait)
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
                    earnings_date = datetime.fromtimestamp(ts, tz=UTC).date()
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
                next_earnings_date=earnings_date,
                quote_type=info.get('quoteType')
            )

            self._cache[ticker_upper] = details
            return details

        except Exception as e:
            logger.warning(f"YFinance Error for {ticker_symbol}: {e}")
            return None

    def get_tickers_data(self, ticker_symbols: list[str]) -> dict[str, Any]:
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
            df.rename(columns={'Date': 'ex_dividend_date', 'Dividend': 'dividend'}, inplace=True)
            return df
        if isinstance(ser, pd.DataFrame):
            return ser
        return pd.DataFrame()

    # ---------------------------
    # NEW: Price History (DataFrame)
    # ---------------------------
    def get_price_history_df(self, symbol: str, exchange: str | None = None) -> pd.DataFrame:
        """
        Returns DataFrame with columns: price_date, open_price, high_price, low_price, close_price, volume
        """
        tkr = yf.Ticker(self._resolve_symbol(symbol, exchange))
        try:
            # D1 (backend/docs/price-history-professional-model.md): store RAW OHLC as the
            # provider serves it. Adjusted values are derived from the owned `splits`
            # calendar at write time — provider Adj Close is unreliable (no-op for
            # some names, mixed with dividend effects for others).
            hist = tkr.history(period="max", auto_adjust=False)  # columns: Open, High, Low, Close, Volume
            if hist is None or hist.empty:
                return pd.DataFrame()
            df = hist.reset_index().rename(columns={
                "Date": "price_date",
                "Open": "open_price",
                "High": "high_price",
                "Low": "low_price",
                "Close": "close_price",
                "Volume": "volume",
            })
            # yfinance returns a tz-aware DatetimeIndex (e.g. America/New_York).
            # Normalise to tz-naive so downstream date-window comparisons against
            # a naive pd.Timestamp are valid; a tz-aware column raises
            # "Invalid comparison between dtype=datetime64[s, America/New_York]
            # and Timestamp" in defeat_beta_provider.get_price_history_optimized
            # whenever start_date/end_date is supplied.
            df["price_date"] = pd.to_datetime(df["price_date"], errors='coerce')
            if isinstance(df["price_date"].dtype, pd.DatetimeTZDtype):
                df["price_date"] = df["price_date"].dt.tz_localize(None)
            return df
        except Exception:
            return pd.DataFrame()

    # ---------------------------
    # NEW: Splits (DataFrame)
    # ---------------------------
    def get_splits_df(self, symbol: str) -> pd.DataFrame:
        """
        Returns DataFrame with columns: report_date, split_factor (string like '3:1')
        """
        tkr = yf.Ticker(symbol.upper())
        try:
            s = tkr.splits  # Series where value is numeric split ratio, e.g., 3.0 for 3-for-1
            if s is None or s.empty:
                return pd.DataFrame()
            df = s.reset_index()
            # Normalize columns (yfinance's column name varies across versions)
            # Ensure df has ['Date', value_name]; rename to ['report_date','ratio']
            if 'Date' not in df.columns:
                # sometimes the index level name is None; ensure first column is datetime index
                df.rename(columns={df.columns[0]: 'Date'}, inplace=True)
            value_col = [c for c in df.columns if c != 'Date'][0]
            df.rename(columns={'Date': 'report_date', value_col: 'ratio'}, inplace=True)

            def to_factor(x) -> str | None:
                try:
                    if x and float(x) > 0:
                        # 3.0 => "3:1"; 0.5 => "1:2"
                        f = float(x)
                        if f >= 1:
                            return f"{int(round(f))}:1"
                        else:
                            denom = int(round(1 / f))
                            return f"1:{denom}"
                except Exception:
                    return None
                return None

            df["split_factor"] = df["ratio"].apply(to_factor)
            df["report_date"] = pd.to_datetime(df["report_date"], errors='coerce')
            return df[["report_date", "split_factor"]]
        except Exception:
            return pd.DataFrame()

    # ---------------------------
    # NEW: Company Summary (dict)
    # ---------------------------
    def get_summary_snapshot(self, symbol: str) -> dict[str, Any] | None:
        """
        Returns dict with summary metrics mapped to your company_summary schema.
        """
        try:
            tkr = yf.Ticker(symbol.upper())
            info = tkr.info or {}
            return {
                "snapshot_date": now_utc().date(),
                "market_cap": info.get("marketCap"),
                "enterprise_value": info.get("enterpriseValue"),
                "shares_outstanding": info.get("sharesOutstanding"),
                "implied_shares_outstanding": info.get("impliedSharesOutstanding"),
                "beta": info.get("beta"),
                "trailing_pe": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "trailing_eps": info.get("trailingEps"),
                "forward_eps": info.get("forwardEps"),
                "enterprise_to_ebitda": info.get("enterpriseToEbitda"),
                "enterprise_to_revenue": info.get("enterpriseToRevenue"),
                "peg_ratio": info.get("pegRatio"),
                "currency": info.get("currency") or "USD",
                "provider": "yfinance",
            }
        except Exception:
            return None

    # ---------------------------
    # Earnings data (best-effort)
    # ---------------------------
    def get_earnings_data(self, ticker_symbol: str) -> list[dict[str, Any]] | None:
        """
        Returns list of dicts with fiscal_year, fiscal_quarter,
        report_date, announcement_date, eps_estimate, revenue_estimate, (best-effort).

        Changed to use earnings_history instead of calendar (Feb 2026).
        earnings_history provides actual reported EPS, not just estimates.
        """
        try:
            tkr = yf.Ticker(ticker_symbol.upper())
            earnings_list: list[dict[str, Any]] = []

            # Earnings history (actual reported EPS + estimates)
            # This is the correct API - provides epsActual, epsEstimate, epsDifference, surprisePercent
            try:
                earnings_history = tkr.earnings_history
                if earnings_history is not None and not earnings_history.empty:
                    for quarter_date, row in earnings_history.iterrows():
                        try:
                            # quarter_date is the earnings date (index)
                            if isinstance(quarter_date, pd.Timestamp):
                                report_date = quarter_date.date()
                            elif isinstance(quarter_date, str):
                                report_date = parse_db_timestamp(quarter_date).date()
                            else:
                                report_date = quarter_date

                            fy = report_date.year
                            fq = (report_date.month - 1) // 3 + 1

                            eps_actual = self._safe_float(row.get('epsActual'))
                            eps_estimate = self._safe_float(row.get('epsEstimate'))
                            eps_difference = self._safe_float(row.get('epsDifference'))
                            surprise_percent = self._safe_float(row.get('surprisePercent'))

                            # Calculate surprise amount if we have actual and estimate
                            eps_surprise_amount = None
                            if eps_actual is not None and eps_estimate is not None:
                                eps_surprise_amount = eps_actual - eps_estimate

                            earnings_list.append({
                                'fiscal_year': fy,
                                'fiscal_quarter': fq,
                                'announcement_date': report_date,
                                'report_date': report_date,
                                'eps_estimate': eps_estimate,
                                'eps_reported': eps_actual,
                                'eps_surprise_amount': eps_surprise_amount,
                                'eps_surprise_percent': surprise_percent,
                                'revenue_estimate': None,
                                'revenue_reported': None,
                                'revenue_surprise_amount': None,
                                'revenue_surprise_percent': None,
                            })
                        except Exception as e:
                            logger.debug(f"Error parsing earnings_history row for {ticker_symbol}: {e}")
                            continue
            except Exception as e:
                logger.debug(f"Failed to fetch earnings_history for {ticker_symbol}: {e}")

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

    # ---------------------------
    # NEW: Upcoming ex-dividend date
    # ---------------------------
    def get_upcoming_ex_date(self, symbol: str) -> date | None:
        """Get the next ex-dividend date from yfinance info.
        
        Primary source: info.exDividendDate (Unix timestamp).
        Secondary source: calendar.Ex-Dividend Date (ISO string).
        Returns None if the stock doesn't pay dividends or both
        fields are missing/past.
        Ex-dates are NYSE calendar — uses America/New_York timezone.
        """
        try:
            from zoneinfo import ZoneInfo
            tkr = yf.Ticker(symbol.upper())
            info = tkr.info or {}
            today = now_utc().date()

            # Primary: info.exDividendDate (Unix timestamp)
            ts = info.get("exDividendDate")
            if ts is not None:
                try:
                    ex_date = datetime.fromtimestamp(float(ts), tz=ZoneInfo("America/New_York")).date()
                    if ex_date >= today:
                        return ex_date
                except (ValueError, TypeError):
                    pass

            # Secondary: calendar.Ex-Dividend Date (ISO date string)
            try:
                cal = tkr.calendar
                if cal is not None and not cal.empty:
                    cal_row = cal.iloc[0] if isinstance(cal, pd.DataFrame) else cal
                    cal_date_str = cal_row.get("Ex-Dividend Date")
                    if cal_date_str is not None:
                        cal_date = pd.Timestamp(cal_date_str).date()
                        if cal_date >= today:
                            return cal_date
            except Exception:
                pass

            return None
        except Exception as e:
            logger.debug("[YF] get_upcoming_ex_date(%s) failed: %s", symbol, e)
            return None

    # ---------------------------
    # Analyst consensus forecasts (revenue / EPS)
    # ---------------------------
    async def fetch_revenue_forecast(self, symbol: str, company_id: int) -> list[dict[str, Any]]:
        """Annual analyst revenue consensus via yfinance.

        Replaces the dead DefeatBeta path: defeatbeta-api ships no forecast
        accessors in any release. report_date anchors relative yfinance
        periods ('0y', '+1y') to an approximate Dec-31 fiscal year-end.
        """
        return await asyncio.to_thread(self._fetch_estimate_rows, symbol, company_id, 'revenue')

    async def fetch_earnings_forecast(self, symbol: str, company_id: int) -> list[dict[str, Any]]:
        """Annual analyst EPS consensus via yfinance (see fetch_revenue_forecast).

        The *_days_ago EPS-revision fields stay None: yfinance models those
        in a separate eps_trend frame, which is out of scope here.
        """
        return await asyncio.to_thread(self._fetch_estimate_rows, symbol, company_id, 'earnings')

    def _fetch_estimate_rows(self, symbol: str, company_id: int, kind: str) -> list[dict[str, Any]]:
        rows_out: list[dict[str, Any]] = []
        try:
            tkr = yf.Ticker(symbol.upper())
            df = tkr.revenue_estimate if kind == 'revenue' else tkr.earnings_estimate
            if df is None or df.empty:
                return []
            this_year = now_utc().year
            for label, row in df.iterrows():
                label_str = str(label).strip()
                if label_str not in ('0y', '+1y'):
                    continue
                avg = self._safe_float(row.get('avg'))
                if avg is None:
                    continue
                offset = 0 if label_str == '0y' else int(''.join(ch for ch in label_str if ch.isdigit()))
                analysts = row.get('numberOfAnalysts')
                try:
                    analysts = int(analysts) if analysts is not None else None
                except (ValueError, TypeError):
                    analysts = None
                record: dict[str, Any] = {
                    'company_id': company_id,
                    'report_date': date(this_year + offset, 12, 31),
                    'period_type': 'annual',
                    'number_of_analysts': analysts,
                    'currency': 'USD',
                    'provider': 'yfinance',
                }
                if kind == 'revenue':
                    record.update({
                        'estimate_revenue_growth': self._safe_float(row.get('growth')),
                        'estimate_avg_revenue': avg,
                        'estimate_high_revenue': self._safe_float(row.get('high')),
                        'estimate_low_revenue': self._safe_float(row.get('low')),
                        'year_ago_estimate_avg_revenue': self._safe_float(row.get('yearAgoRevenue')),
                    })
                else:
                    record.update({
                        'estimate_eps_growth': self._safe_float(row.get('growth')),
                        'estimate_avg_eps': avg,
                        'estimate_high_eps': self._safe_float(row.get('high')),
                        'estimate_low_eps': self._safe_float(row.get('low')),
                        'thirty_days_ago_estimate_avg_eps': None,
                        'sixty_days_ago_estimate_avg_eps': None,
                        'ninety_days_ago_estimate_avg_eps': None,
                        'year_ago_estimate_avg_eps': self._safe_float(row.get('yearAgoEps')),
                    })
                rows_out.append(record)
            return rows_out
        except Exception as e:
            logger.warning(f'Failed to fetch {kind} forecast for {symbol}: {e}')
            return []

    @staticmethod
    def _safe_float(val) -> float | None:
        if val is None:
            return None
        try:
            f = float(val)
            return f if f == f else None  # NaN check
        except (ValueError, TypeError):
            return None
