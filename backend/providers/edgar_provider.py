# -*- coding: utf-8 -*-
"""
EdgarTools-based provider for SEC EDGAR financial statements.

Position in the fallback chain:
    DefeatBeta (primary) → EdgarTools (fallback 1) → YFinance (fallback 2)

EdgarTools reads directly from SEC 10-K / 10-Q XBRL filings. Data is highly
authoritative but limited to what the SEC requires companies to disclose.

✅ Provides:  annual & quarterly IS / BS / CF
              (matching the same method signatures as YFinanceProvider so
              DefeatBetaProvider can call them transparently)
❌ Cannot provide: live prices, price history, splits, revenue/earnings forecasts,
                   company summary (market cap, PE, beta), earnings surprises

Setup:
    Set EDGAR_IDENTITY environment variable:
        EDGAR_IDENTITY="YourName yourname@example.com"
    OR add EDGAR_IDENTITY to your Pydantic settings.
    The SEC requires this for fair-use rate limiting.

Notes on edgartools DataFrame format
--------------------------------------
`financials.income_statement().to_dataframe()` returns a *long-format* DataFrame:

    label                       | standard_concept          | 2023-09-30 | 2022-09-24
    Total net sales             | us-gaap_Revenues          | 383285e9   | 394328e9
    Cost of sales               | us-gaap_CostOfRevenue     | 214137e9   | 223546e9

The `standard_concept` column contains XBRL tags with a `us-gaap_` prefix that
edgartools uses internally for cross-company normalisation.

This provider normalises that to the wide-format that DefeatBetaProvider's
`_parse_yf_*` parsers expect:

    index                | pd.Timestamp(2023-09-30) | pd.Timestamp(2022-09-24)
    Total Revenue        | 383285e9                 | 394328e9
    Cost Of Revenue      | 214137e9                 | 223546e9
"""
from __future__ import annotations

import logging
import os
from typing import Dict, Optional

import pandas as pd

from providers.base import StockDataProvider, TickerInfo, StockDetails

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Concept maps
# ---------------------------------------------------------------------------
# Primary: XBRL concept name (us-gaap_ prefix stripped) → standard label
# that DefeatBetaProvider._parse_yf_* parsers check for.
_CONCEPT_MAP: Dict[str, str] = {
    # ── Income Statement ─────────────────────────────────────────────────
    "RevenueFromContractWithCustomerExcludingAssessedTax": "Total Revenue",
    "RevenueFromContractWithCustomerIncludingAssessedTax": "Total Revenue",
    "Revenues": "Total Revenue",
    "Revenue": "Total Revenue",
    "SalesRevenueNet": "Total Revenue",
    "SalesRevenueGoodsNet": "Total Revenue",
    "CostOfRevenue": "Cost Of Revenue",
    "CostOfGoodsSold": "Cost Of Revenue",
    "CostOfGoodsAndServicesSold": "Cost Of Revenue",
    "GrossProfit": "Gross Profit",
    "OperatingIncomeLoss": "Operating Income",
    "InterestExpense": "Interest Expense",
    "InterestExpenseNonoperating": "Interest Expense",
    "IncomeTaxExpenseBenefit": "Income Tax Expense",
    "NetIncomeLoss": "Net Income",
    "NetIncomeLossAvailableToCommonStockholdersBasic": "Net Income Common Stockholders",
    "NetIncomeLossAvailableToCommonStockholdersDiluted": "Net Income Common Stockholders",
    # Pre-tax
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": "Pretax Income",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments": "Pretax Income",
    # EPS
    "EarningsPerShareBasic": "BasicEPS",
    "EarningsPerShareDiluted": "DilutedEPS",
    # Shares
    "WeightedAverageNumberOfSharesOutstandingBasic": "BasicAverageShares",
    "WeightedAverageNumberOfDilutedSharesOutstanding": "DilutedAverageShares",
    "CommonStockSharesOutstanding": "BasicAverageShares",

    # ── Balance Sheet ────────────────────────────────────────────────────
    "Assets": "Total Assets",
    "AssetsCurrent": "Total Current Assets",
    "CashAndCashEquivalentsAtCarryingValue": "Cash And Cash Equivalents",
    "CashCashEquivalentsAndShortTermInvestments": "Cash And Cash Equivalents",
    "AccountsReceivableNetCurrent": "Accounts Receivable",
    "ReceivablesNetCurrent": "Accounts Receivable",
    "InventoryNet": "Inventory",
    "PropertyPlantAndEquipmentNet": "Net PPE",
    "FiniteLivedIntangibleAssetsNet": "Intangible Assets",
    "IntangibleAssetsNetExcludingGoodwill": "Intangible Assets",
    "Goodwill": "Goodwill",
    "Liabilities": "Total Liabilities",
    "LiabilitiesCurrent": "Total Current Liabilities",
    "AccountsPayableCurrent": "Accounts Payable",
    "ShortTermBorrowings": "Short Term Debt",
    "DebtCurrent": "Short Term Debt",
    "CommercialPaper": "Short Term Debt",
    "LongTermDebtNoncurrent": "Long Term Debt",
    "LongTermDebt": "Long Term Debt",
    "LongTermDebtAndCapitalLeaseObligations": "Long Term Debt",
    "StockholdersEquity": "Stockholders' Equity",
    "StockholdersEquityAttributableToParent": "Stockholders' Equity",
    "RetainedEarningsAccumulatedDeficit": "Retained Earnings",
    "MinorityInterest": "Minority Interest",
    "MinorityInterestInSubsidiaries": "Minority Interest",

    # ── Cash Flow ────────────────────────────────────────────────────────
    "NetCashProvidedByUsedInOperatingActivities": "Operating Cash Flow",
    "NetCashProvidedByUsedInInvestingActivities": "Total Cash From Investing Activities",
    "NetCashProvidedByUsedInFinancingActivities": "Total Cash From Financing Activities",
    "PaymentsToAcquirePropertyPlantAndEquipment": "Capital Expenditure",
    "PaymentsForCapitalImprovements": "Capital Expenditure",
    "DepreciationDepletionAndAmortization": "Depreciation & Amortization",
    "Depreciation": "Depreciation & Amortization",
    "PaymentsOfDividendsCommonStock": "Cash Dividends Paid",
    "PaymentsOfDividends": "Cash Dividends Paid",
    "PaymentsForRepurchaseOfCommonStock": "Repurchase Of Capital Stock",
    "ProceedsFromIssuanceOfLongTermDebt": "Issuance Of Debt",
    "RepaymentsOfLongTermDebt": "Repayment Of Debt",
    "ShareBasedCompensation": "Stock Based Compensation",
    "IncreaseDecreaseInOperatingCapital": "Change In Working Capital",
    "IncreaseDecreaseInOperatingLiabilities": "Change In Working Capital",
}

# Fallback: display label (lowercased, whitespace-collapsed) → standard label.
# Used when standard_concept is absent or not in _CONCEPT_MAP.
_LABEL_MAP: Dict[str, str] = {
    # Income
    "net sales": "Total Revenue",
    "total net sales": "Total Revenue",
    "total revenues": "Total Revenue",
    "total revenue": "Total Revenue",
    "net revenue": "Total Revenue",
    "net revenues": "Total Revenue",
    "revenue": "Total Revenue",
    "revenues": "Total Revenue",
    "cost of sales": "Cost Of Revenue",
    "cost of revenue": "Cost Of Revenue",
    "cost of goods sold": "Cost Of Revenue",
    "gross profit": "Gross Profit",
    "operating income": "Operating Income",
    "operating income (loss)": "Operating Income",
    "income from operations": "Operating Income",
    "interest expense": "Interest Expense",
    "provision for income taxes": "Income Tax Expense",
    "income tax expense": "Income Tax Expense",
    "income tax expense (benefit)": "Income Tax Expense",
    "net income": "Net Income",
    "net earnings": "Net Income",
    "net income (loss)": "Net Income",
    "income before provision for income taxes": "Pretax Income",
    "income before income taxes": "Pretax Income",
    "earnings per share - basic": "BasicEPS",
    "earnings per share - diluted": "DilutedEPS",
    "earnings per share — basic": "BasicEPS",
    "earnings per share — diluted": "DilutedEPS",
    "basic earnings per share": "BasicEPS",
    "diluted earnings per share": "DilutedEPS",
    # Balance
    "total assets": "Total Assets",
    "total current assets": "Total Current Assets",
    "cash and cash equivalents": "Cash And Cash Equivalents",
    "accounts receivable, net": "Accounts Receivable",
    "accounts receivable": "Accounts Receivable",
    "inventories": "Inventory",
    "inventory": "Inventory",
    "property, plant and equipment, net": "Net PPE",
    "property and equipment, net": "Net PPE",
    "goodwill": "Goodwill",
    "total liabilities": "Total Liabilities",
    "total current liabilities": "Total Current Liabilities",
    "accounts payable": "Accounts Payable",
    "long-term debt": "Long Term Debt",
    "total stockholders' equity": "Stockholders' Equity",
    "total shareholders' equity": "Stockholders' Equity",
    "retained earnings": "Retained Earnings",
    "accumulated deficit": "Retained Earnings",
    # Cash flow
    "net cash provided by operating activities": "Operating Cash Flow",
    "net cash generated by operating activities": "Operating Cash Flow",
    "net cash used in operating activities": "Operating Cash Flow",
    "net cash provided by (used in) investing activities": "Total Cash From Investing Activities",
    "net cash used in investing activities": "Total Cash From Investing Activities",
    "net cash provided by (used in) financing activities": "Total Cash From Financing Activities",
    "net cash used in financing activities": "Total Cash From Financing Activities",
    "capital expenditures": "Capital Expenditure",
    "purchases of property, plant and equipment": "Capital Expenditure",
    "depreciation and amortization": "Depreciation & Amortization",
    "payments of dividends": "Cash Dividends Paid",
    "repurchases of common stock": "Repurchase Of Capital Stock",
}

# Columns in the edgartools to_dataframe() output that are metadata, not period values.
_METADATA_COLS = frozenset({
    "label", "standard_concept", "level", "parent_concept",
    "parent_abstract_concept", "concept", "abstract", "negated",
    "period_type",
})


class EdgarToolsProvider(StockDataProvider):
    """
    SEC EDGAR financial statement provider (edgartools library).

    Plugs into DefeatBetaProvider as `edgar_provider`. Both providers expose
    the same method signatures for statement DataFrames so the existing
    `_parse_yf_*` parsers work without modification.

    This provider is intentionally synchronous — callers wrap it in
    ``asyncio.to_thread()`` just like YFinanceProvider.
    """

    def __init__(self, identity: Optional[str] = None):
        self._identity: str = self._resolve_identity(identity)
        self._initialized: bool = False
        logger.info("EdgarToolsProvider created (identity=%s)", self._identity)

    # ──────────────────────────────────────────────────────────────────────
    # StockDataProvider interface — not available from SEC filings
    # ──────────────────────────────────────────────────────────────────────

    def get_ticker_info(self, ticker_symbol: str) -> Optional[TickerInfo]:
        return None  # SEC filings carry no live price data

    def get_stock_details(self, ticker_symbol: str) -> Optional[StockDetails]:
        return None  # SEC filings carry no live price data

    # ──────────────────────────────────────────────────────────────────────
    # Public statement accessors
    # Same names as YFinanceProvider so DefeatBetaProvider can call either
    # ──────────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────────
    # Core fetch & normalisation
    # ──────────────────────────────────────────────────────────────────────

    def _fetch(self, period: str, statement: str, symbol: str) -> pd.DataFrame:
        """
        Fetch a financial statement from EDGAR and return in yfinance-compatible format.

        Target format (what _parse_yf_* parsers expect):
            index   = standard string labels  e.g. "Total Revenue", "Net Income"
            columns = pd.Timestamp objects    (period-end dates)
            values  = float / NaN
        """
        self._ensure_initialized()
        try:
            from edgar import Company  # noqa: PLC0415
            company = Company(symbol.upper())
            financials = (
                company.get_financials()
                if period == "annual"
                else company.get_quarterly_financials()
            )
            if financials is None:
                logger.debug("[EDGAR][%s] no %s financials returned", symbol, period)
                return pd.DataFrame()

            raw_df = self._extract_statement_df(financials, statement, symbol)
            if raw_df is None or raw_df.empty:
                return pd.DataFrame()

            result = self._normalise(raw_df, symbol)
            logger.debug(
                "[EDGAR][%s] %s %s: %d labels × %d periods",
                symbol, period, statement, len(result.index), len(result.columns),
            )
            return result

        except ImportError:
            logger.error(
                "[EDGAR] edgartools is not installed. Run: pip install edgartools"
            )
            return pd.DataFrame()
        except Exception as e:
            logger.warning(
                "[EDGAR][%s] %s %s failed: %s", symbol, period, statement, e
            )
            return pd.DataFrame()

    def _extract_statement_df(
        self, financials, statement: str, symbol: str
    ) -> Optional[pd.DataFrame]:
        """
        Pull the raw DataFrame from an edgartools Financials object.

        edgartools' `income_statement()` / `balance_sheet()` / `cashflow_statement()`
        return a FinancialStatement object with a `.to_dataframe()` method.

        The resulting DataFrame looks like:
            label                 | standard_concept              | 2023-09-30 | 2022-09-24
            Total net sales       | us-gaap_Revenues              | 383285e9   | 394328e9
            ...

        We request `view="summary"` to suppress dimensional segment breakdowns
        and get only the high-level aggregate line items.
        """
        accessor_candidates = {
            "income": [
                ("income_statement", True),
                ("income", False),
            ],
            "balance": [
                ("balance_sheet", True),
                ("balance_sheet", False),
            ],
            "cashflow": [
                ("cashflow_statement", True),
                ("cash_flow_statement", True),
                ("cashflow", False),
                ("cash_flow", False),
            ],
        }
        for attr, is_callable in accessor_candidates.get(statement, []):
            if not hasattr(financials, attr):
                continue
            try:
                obj = getattr(financials, attr)
                if is_callable and callable(obj):
                    obj = obj()

                # edgartools returns a FinancialStatement; convert to DataFrame
                df = self._to_dataframe(obj, symbol)
                if df is not None and not df.empty:
                    return df
            except Exception as e:
                logger.debug(
                    "[EDGAR][%s] %s via %s failed: %s", symbol, statement, attr, e
                )
        return None

    @staticmethod
    def _to_dataframe(obj, symbol: str) -> Optional[pd.DataFrame]:
        """
        Convert an edgartools FinancialStatement (or plain DataFrame) to a
        raw pandas DataFrame, preferring the `view="summary"` layout.
        """
        if obj is None:
            return None

        # Already a plain DataFrame
        if isinstance(obj, pd.DataFrame):
            return obj if not obj.empty else None

        # FinancialStatement with to_dataframe()
        if hasattr(obj, "to_dataframe") and callable(obj.to_dataframe):
            for kwargs in [{"view": "summary"}, {"include_dimensions": False}, {}]:
                try:
                    df = obj.to_dataframe(**kwargs)
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        return df
                except Exception:
                    continue

        # .data attribute fallback
        if hasattr(obj, "data"):
            d = obj.data
            if isinstance(d, pd.DataFrame) and not d.empty:
                return d

        return None

    def _normalise(self, raw_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Converts the edgartools long-format DataFrame to the wide-format that
        DefeatBetaProvider._parse_yf_* parsers consume.

        Steps:
        1. Identify period (date) columns vs metadata columns
        2. Resolve each row to a standard label via standard_concept or label
        3. De-duplicate rows (keep the first match for each standard label)
        4. Build a new DataFrame with standard labels as index and pd.Timestamps as columns
        """
        df = raw_df.copy()

        # ── Step 1: Identify period columns ───────────────────────────────
        period_cols: Dict = {}          # original col → pd.Timestamp
        for col in df.columns:
            col_str = str(col).strip()
            if col_str.lower() in _METADATA_COLS:
                continue
            # Try direct timestamp parse ("2023-09-30")
            ts = pd.to_datetime(col_str, errors="coerce")
            if not pd.isna(ts):
                period_cols[col] = ts
                continue
            # Year integer e.g. 2023 → 2023-12-31
            try:
                yr = int(col_str)
                if 1990 <= yr <= 2100:
                    period_cols[col] = pd.Timestamp(f"{yr}-12-31")
            except (ValueError, TypeError):
                pass

        if not period_cols:
            logger.debug("[EDGAR][%s] no parseable date columns found", symbol)
            return pd.DataFrame()

        # ── Step 2: Resolve labels ─────────────────────────────────────────
        label_col = "label" if "label" in df.columns else None
        concept_col = "standard_concept" if "standard_concept" in df.columns else None

        rows: Dict[str, Dict] = {}      # standard_label → {period_ts: value}

        for _, row in df.iterrows():
            standard_label = self._resolve_label(row, label_col, concept_col)
            if standard_label is None:
                continue
            if standard_label in rows:
                continue  # keep first occurrence only

            vals: Dict[pd.Timestamp, float] = {}
            for orig_col, ts in period_cols.items():
                raw_val = row.get(orig_col)
                num = pd.to_numeric(raw_val, errors="coerce")
                if not pd.isna(num):
                    vals[ts] = float(num)
            if vals:
                rows[standard_label] = vals

        if not rows:
            logger.debug("[EDGAR][%s] no rows survived label resolution", symbol)
            return pd.DataFrame()

        # ── Step 3: Build result DataFrame ────────────────────────────────
        all_periods = sorted({ts for vals in rows.values() for ts in vals})
        data = {label: [vals.get(ts, float("nan")) for ts in all_periods]
                for label, vals in rows.items()}
        result = pd.DataFrame(data, index=all_periods).T  # labels=rows, periods=cols
        result.index.name = None
        result.columns.name = None
        return result

    @staticmethod
    def _resolve_label(
        row: pd.Series,
        label_col: Optional[str],
        concept_col: Optional[str],
    ) -> Optional[str]:
        """
        Try to map a DataFrame row to a standard label.

        Priority:
          1. standard_concept → strip 'us-gaap_' prefix → look up _CONCEPT_MAP
          2. display label (lowercased, collapsed) → look up _LABEL_MAP
        """
        # 1. standard_concept
        if concept_col and concept_col in row:
            raw_concept = str(row[concept_col] or "").strip()
            # Strip namespace prefix: "us-gaap_Revenues" → "Revenues"
            concept = raw_concept.split("_", 1)[-1] if "_" in raw_concept else raw_concept
            mapped = _CONCEPT_MAP.get(concept)
            if mapped:
                return mapped

        # 2. display label fallback
        if label_col and label_col in row:
            raw_label = str(row[label_col] or "").strip()
            norm_label = " ".join(raw_label.lower().split())
            return _LABEL_MAP.get(norm_label)

        return None

    # ──────────────────────────────────────────────────────────────────────
    # Initialisation helpers
    # ──────────────────────────────────────────────────────────────────────

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            from edgar import set_identity  # noqa: PLC0415
            set_identity(self._identity)
            logger.info("[EDGAR] SEC identity set: %s", self._identity)
        except ImportError:
            logger.error("[EDGAR] edgartools not installed — pip install edgartools")
        except Exception as e:
            logger.warning("[EDGAR] set_identity failed (continuing): %s", e)
        finally:
            self._initialized = True

    @staticmethod
    def _resolve_identity(explicit: Optional[str]) -> str:
        if explicit:
            return explicit
        env = os.getenv("EDGAR_IDENTITY", "").strip()
        if env:
            return env
        try:
            from config import settings  # noqa: PLC0415
            return getattr(settings, "EDGAR_IDENTITY", "stockerpro@example.com")
        except Exception:
            return "stockerpro@example.com"