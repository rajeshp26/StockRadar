from __future__ import annotations

import logging
import time
from datetime import date


from typing import Any

import pandas as pd

from shared.time_utils import parse_db_timestamp

logger = logging.getLogger(__name__)

# ── Label translation: Macrotrends names → _parse_yf_* expected names ───
# Macrotrends uses different label strings than yfinance/edgar. This map
# renames rows so that _parse_yf_*'s gv() helper can find the values.
_PER_SHARE_LABELS: set = {"Basic EPS", "Diluted EPS"}

_LABEL_MAP: dict[str, str] = {
    # Balance Sheet
    "Cash On Hand": "Cash And Cash Equivalents",
    "Retained Earnings (Accumulated Deficit)": "Retained Earnings",
    "Share Holder Equity": "Stockholders' Equity",
    "Long Term Debt": "Long Term Debt",
    "Net PPE": "Property, Plant And Equipment Net",
    "Long Term Investments": "Long Term Investments",
    "Total Long Term Assets": "Total Non Current Assets",
    "Total Current Liabilities": "Total Current Liabilities",
    "Total Long Term Liabilities": "Total Non Current Liabilities",
    "Accounts Payable": "Accounts Payable",
    "Short Term Debt": "Short Term Debt",
    # Income Statement
    "Revenue": "Total Revenue",
    "Cost Of Goods Sold": "Cost Of Revenue",
    "Gross Profit": "Gross Profit",
    "Research And Development Expenses": "Research And Development",
    "SG&A Expenses": "Selling General And Administrative",
    "Operating Expenses": "Operating Expense",
    "Operating Income": "Operating Income",
    "Pre-Tax Income": "Pretax Income",
    "Income Taxes": "Tax Provision",
    "Net Income": "Net Income",
    "Basic EPS": "Basic EPS",
    "EPS - Earnings Per Share": "Diluted EPS",
    "Basic Shares Outstanding": "Basic Average Shares",
    "Shares Outstanding": "Diluted Average Shares",
    "EBITDA": "EBITDA",
    "EBIT": "EBIT",
    # Cash Flow
    "Net Income/Loss": "Net Income",
    "Total Depreciation And Amortization - Cash Flow": "Depreciation & Amortization",
    "Cash Flow From Operating Activities": "Operating Cash Flow",
    "Net Change In Property, Plant, And Equipment": "Capital Expenditure",
    "Cash Flow From Investing Activities": "Total Cash From Investing Activities",
    "Cash Flow From Financial Activities": "Total Cash From Financing Activities",
    "Stock-Based Compensation": "Stock Based Compensation",
    "Common Stock Dividends Paid": "Cash Dividends Paid",
    "Change In Accounts Receivable": "Change In Working Capital",
    "Change In Inventories": "Change In Working Capital",
    "Change In Accounts Payable": "Change In Working Capital",
    # IFRS-specific labels (Canadian banks)
    "Net Revenue": "Total Revenue",
    "Turnover": "Total Revenue",
    "Operating Profit": "Operating Income",
    "Profit Before Tax": "Pretax Income",
    "Profit For The Year": "Net Income",
    "Total Current Assets": "Total Current Assets",
    "Dividends Paid": "Cash Dividends Paid",
}


class StockdexMacrotrendsProvider:
    """
    Wraps stockdex's Macrotrends source for historical financial statements.

    Position in the fallback chain:
        DefeatBeta (primary) -> Stockdex/Macrotrends (this) -> EdgarTools -> YFinance

    Macrotrends provides 15+ years of quarterly data -- far deeper than
    Yahoo Finance (~5 years) or SEC EDGAR (~2 recent BS quarters).

    Exposes the same 6 method signatures as EdgarToolsProvider and YFinanceProvider:

        get_{quarterly,annual}_{income_statement,balance_sheet,cash_flow}_df(symbol)

    All public methods return a wide-format DataFrame with:
        index   = standard string labels (e.g. "Total Revenue", "Net Income")
        columns = pd.Timestamp objects   (period-end dates)
        values  = float / NaN

    Returns pd.DataFrame() (empty) on any failure.
    """

    def __init__(self) -> None:
        self._ticker_cache: dict[str, Any] = {}
        self._cooldown_until: float = 0.0
        self._finviz_cooldown_until: float = 0.0
        self._consecutive_429: int = 0
        self._symbol_403_counts: dict[str, int] = {}
        self._symbol_403_until: dict[str, float] = {}
        self._blocked_403_symbols: set[str] = set()
        logger.info("StockdexMacrotrendsProvider initialized")

    def is_rate_limited(self) -> bool:
        return time.monotonic() < self._cooldown_until

    def is_symbol_blocked(self, symbol: str) -> bool:
        now = time.monotonic()
        until = self._symbol_403_until.get(symbol)
        if until is not None and now >= until:
            self._symbol_403_counts.pop(symbol, None)
            self._symbol_403_until.pop(symbol, None)
            self._blocked_403_symbols.discard(symbol)
        return symbol in self._blocked_403_symbols

    def _register_symbol_failure(self, symbol: str) -> None:
        c = self._symbol_403_counts.get(symbol, 0) + 1
        self._symbol_403_counts[symbol] = c
        if c >= 3:
            self._block_symbol(symbol)

    def _handle_fetch_error(self, symbol: str, err: Exception) -> None:
        estr = str(err)
        # `/TBD/` is stockdex's unresolved-slug placeholder. The URL is identical
        # on every retry, so waiting for three failures only guarantees three
        # 403s. Block the symbol immediately and let other providers handle it.
        if "/TBD/" in estr:
            self._block_symbol(symbol)
            return
        if "403" in estr or "Forbidden" in estr or "forbidden" in estr:
            self._register_symbol_failure(symbol)

    def _block_symbol(self, symbol: str) -> None:
        """Block a symbol for one cooldown window (permanent-slug failure)."""
        self._blocked_403_symbols.add(symbol)
        self._symbol_403_until[symbol] = time.monotonic() + 300
        self._symbol_403_counts.pop(symbol, None)


    # ------------------------------------------------------------------
    # Public statement accessors
    # ------------------------------------------------------------------

    def get_annual_income_statement_df(self, symbol: str) -> pd.DataFrame:
        return self._fetch("annual", "income", symbol)

    def get_quarterly_income_statement_df(self, symbol: str) -> pd.DataFrame:
        return self._fetch("quarterly", "income", symbol)

    def get_annual_balance_sheet_df(self, symbol: str) -> pd.DataFrame:
        return self._fetch("annual", "balance", symbol)

    def get_quarterly_balance_sheet_df(self, symbol: str) -> pd.DataFrame:
        return self._fetch("quarterly", "balance", symbol)

    def get_annual_cash_flow_df(self, symbol: str) -> pd.DataFrame:
        return self._fetch("annual", "cashflow", symbol)

    def get_quarterly_cash_flow_df(self, symbol: str) -> pd.DataFrame:
        return self._fetch("quarterly", "cashflow", symbol)

    # ------------------------------------------------------------------
    # Upcoming ex-dividend date (Finviz via stockdex)
    # ------------------------------------------------------------------

    def get_upcoming_ex_date(self, symbol: str) -> date | None:
        """Get next ex-dividend date from Finviz via stockdex.
        
        Returns the ex-date string parsed to date, or None if the stock
        doesn't pay dividends or the data is unavailable.
        Finviz has its own rate limit — tracked separately from Macrotrends.
        """
        now = time.monotonic()
        if now < self._finviz_cooldown_until:
            logger.debug("[STOCKDEX][%s] Finviz rate-limited, skipping", symbol)
            return None

        try:
            ticker = self._get_or_create_ticker(symbol)
            div = ticker.finviz_overall_dividend()
            if div is None or not isinstance(div, dict):
                return None

            ex_str = div.get("dividendExDate")
            if not ex_str:
                return None

            return parse_db_timestamp(str(ex_str).strip()).date()

        except Exception as e:
            estr = str(e)
            if "429" in estr or "Too Many Requests" in estr:
                cool_secs = 300
                self._finviz_cooldown_until = time.monotonic() + cool_secs
                logger.warning(
                    "[STOCKDEX][%s] Finviz 429 rate-limited – cooling off %ds",
                    symbol, cool_secs,
                )
            logger.debug("[STOCKDEX][%s] get_upcoming_ex_date failed: %s", symbol, e)
            return None

    # ------------------------------------------------------------------
    # Core fetch & normalisation
    # ------------------------------------------------------------------

    def _fetch(self, period: str, statement: str, symbol: str) -> pd.DataFrame:
        """
        Fetch a financial statement from stockdex Macrotrends and return in
        yfinance-compatible wide format.
        """
        if self.is_rate_limited():
            logger.debug(
                "[STOCKDEX][%s] Macrotrends rate-limited, skipping", symbol,
            )
            return pd.DataFrame()
        if self.is_symbol_blocked(symbol):
            logger.debug(
                "[STOCKDEX][%s] symbol blocked by 403 history, skipping", symbol,
            )
            return pd.DataFrame()
        try:
            raw_df = self._get_raw_dataframe(period, statement, symbol)
            if raw_df is None or raw_df.empty:
                logger.debug(
                    "[STOCKDEX][%s] %s %s returned empty", symbol, period, statement
                )
                return pd.DataFrame()

            result = self._normalise(raw_df)
            # Reset backoff on success
            if self._consecutive_429 > 0:
                self._consecutive_429 = 0
            logger.debug(
                "[STOCKDEX][%s] %s %s: %d labels x %d periods",
                symbol, period, statement, len(result.index), len(result.columns),
            )
            return result

        except ImportError:
            logger.error(
                "[STOCKDEX] stockdex is not installed. Run: pip install stockdex"
            )
            return pd.DataFrame()
        except Exception as e:
            self._handle_fetch_error(symbol, e)
            estr = str(e)
            if "429" in estr or "Too Many Requests" in estr:
                self._consecutive_429 += 1
                cool_secs = min(300 * (2 ** (self._consecutive_429 - 1)), 1800)
                self._cooldown_until = time.monotonic() + cool_secs
                logger.warning(
                    "[STOCKDEX][%s] 429 rate-limited (attempt #%d) – cooling off %ds",
                    symbol, self._consecutive_429, cool_secs,
                )
            logger.warning(
                "[STOCKDEX][%s] %s %s failed: %s", symbol, period, statement, e
            )
            return pd.DataFrame()

    def _get_raw_dataframe(
        self, period: str, statement: str, symbol: str
    ) -> pd.DataFrame | None:
        """
        Pull the raw DataFrame from stockdex Macrotrends API.

        Macrotrends returns a wide-format DataFrame with:
            Columns: date strings like "2026-01-31"
            Index:   named "field_name" with metric labels
            Values:  string-encoded floats
        """
        ticker = self._get_or_create_ticker(symbol)

        method_map = {
            ("quarterly", "income"): lambda: ticker.macrotrends_income_statement(
                frequency="quarterly"
            ),
            ("annual", "income"): lambda: ticker.macrotrends_income_statement(
                frequency="annual"
            ),
            ("quarterly", "balance"): lambda: ticker.macrotrends_balance_sheet(
                frequency="quarterly"
            ),
            ("annual", "balance"): lambda: ticker.macrotrends_balance_sheet(
                frequency="annual"
            ),
            ("quarterly", "cashflow"): lambda: ticker.macrotrends_cash_flow(
                frequency="quarterly"
            ),
            ("annual", "cashflow"): lambda: ticker.macrotrends_cash_flow(
                frequency="annual"
            ),
        }

        method = method_map.get((period, statement))
        if method is None:
            logger.warning(
                "[STOCKDEX][%s] unknown statement type: %s/%s",
                symbol, period, statement,
            )
            return None

        df = method()
        if df is None or df.empty:
            return None

        return df

    def _get_or_create_ticker(self, symbol: str) -> Any:
        """Cache and return a stockdex Ticker for the given symbol."""
        key = symbol.upper()
        if key not in self._ticker_cache:
            from stockdex import Ticker as StockdexTicker

            self._ticker_cache[key] = StockdexTicker(ticker=key)
        return self._ticker_cache[key]

    @staticmethod
    def _normalise(raw_df: pd.DataFrame) -> pd.DataFrame:
        """
        Convert stockdex Macrotrends wide-format to the format _parse_yf_* expects.

        Macrotrends in:
            Columns: date strings    e.g. "2026-01-31"
            Index:   metric labels   e.g. "Cash On Hand"
            Values:  string-encoded floats

        Normalised out:
            Columns: pd.Timestamp
            Index:   metric labels
            Values:  float / NaN
        """
        df = raw_df.copy()

        # Step 1: Identify period (date) columns
        period_cols: dict[str, pd.Timestamp] = {}
        for col in df.columns:
            col_str = str(col).strip()
            ts = pd.to_datetime(col_str, errors="coerce")
            if not pd.isna(ts):
                period_cols[col_str] = ts

        if not period_cols:
            logger.debug("[STOCKDEX] no parseable date columns found")
            return pd.DataFrame()

        # Step 2: Extract and translate labels from index
        labels = list(df.index)
        if not labels:
            logger.debug("[STOCKDEX] no labels found in index")
            return pd.DataFrame()

        # Translate labels to names _parse_yf_* expects
        translated: dict[str, str] = {}
        used_labels: set = set()
        for label in labels:
            mapped = _LABEL_MAP.get(label, label)
            # If multiple Macrotrends labels map to same target (e.g. change_in_wc),
            # keep only the first
            if mapped not in used_labels:
                translated[label] = mapped
                used_labels.add(mapped)

        # Step 3: Build result DataFrame -- translated labels as index, Timestamps as columns
        all_periods = sorted(period_cols.values())

        data: dict[str, list[float]] = {}
        for raw_label, output_label in translated.items():
            vals: list[float] = []
            for orig_col_str, ts in period_cols.items():
                raw_val = df.loc[raw_label, orig_col_str]
                num = pd.to_numeric(raw_val, errors="coerce")
                vals.append(float(num) if not pd.isna(num) else float("nan"))
            data[output_label] = vals

        result = pd.DataFrame(data, index=all_periods).T
        result.index.name = None
        result.columns.name = None

        # Macrotrends reports financial values in millions of USD.
        # Multiply all rows by 1,000,000 to convert to full dollars,
        # except per-share labels (EPS etc.) which are already in dollars.
        for label in result.index:
            if label not in _PER_SHARE_LABELS:
                result.loc[label] = result.loc[label].apply(
                    lambda v: v * 1_000_000 if not pd.isna(v) else v
                )

        return result
