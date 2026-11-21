from __future__ import annotations

import asyncio
import contextlib
import html
import json
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

import pandas as pd

from application.normalizers.statement_normalizer import (
    normalize_balance_row,
    normalize_cashflow_row,
    normalize_income_row,
)
from application.validators.financial_data_validator import (
    FinancialDataValidator,
    log_validation_result,
)

# Domain exceptions and models
from domain.exceptions import (
    DefeatBetaException,
    FinancialsFetchTimeoutError,
    MaxRetriesExceededError,
    NoDataError,
)
from domain.model_types import (
    BalanceSheetRow,
    BalanceSheetRows,
    CashFlowRow,
    CashFlowRows,
    CompleteFundamentals,
    DividendRow,
    DividendRows,
    EarningsRow,
    EarningsRows,
    IncomeStatementRow,
    IncomeStatementRows,
)
from providers.base import StockDataProvider
from shared.time_utils import now_utc

if TYPE_CHECKING:
    from providers.base import StockDetails, TickerInfo
    from providers.edgar_provider import EdgarToolsProvider
    from providers.stockdex_provider import StockdexMacrotrendsProvider
    from providers.yfinance_provider import YFinanceProvider

# Defeat Beta SDK — import via the console-safe shim (SDK prints an emoji banner
# at import time which UnicodeEncodeErrors on cp1252 Windows consoles; RC9).
# The shim is invoked here, after the pure-Python imports above, but before the
# class body below first references ``Ticker`` in a type annotation.
from providers.defeatbeta_runtime import import_ticker

Ticker = import_ticker()

logger = logging.getLogger(__name__)

# --- Gap tracking types -------------------------------------------------------
GapKey = tuple[int, int | None, date]  # (fiscal_year, fiscal_quarter, period_end)
GapDict = dict[str, set[GapKey]]          # {"is": ..., "bs": ..., "cf": ...}
# -------------------------------------------------------------------------------

# --- Provider capability rules ------------------------------------------------
# Controls which providers are tried for a given exchange + security_type.
# Security types: "stock", "etf", "fund", etc.
PROVIDER_EXCHANGE_RULES: dict[str, dict[str, Any]] = {
    "stockdex": {
        "exchanges": {"NYSE", "NYQ", "NMS", "NGM", "NCM", "NASDAQ",
                       "TOR", "TSX", "VAN", "TSXV", "V", "CNQ", "NEO"},
    },
    "edgar": {
        "exchanges": {"NYSE", "NYQ", "NMS", "NGM", "NCM", "NASDAQ"},
        "security_types": {"stock"},
    },
}
# -------------------------------------------------------------------------------

# --- RAW DEFEATBETA DUMPER (file-based) ---------------------------------------
def _logs_dir_for_provider() -> Path:
    """
    Resolve backend/logs relative to this file:
    <repo_root>/backend/providers/defeat_beta_provider.py -> <repo_root>/backend/logs
    """
    here = Path(__file__).resolve()
    backend_dir = here.parent.parent   # .../backend
    logs_dir = backend_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def dump_defeatbeta_raw(symbol: str, statement: str, obj: Any) -> None:
    """
    Writes DefeatBeta raw object, raw json (if available), and raw df to files in backend/logs.
    File names like: TSLA_quarterly_balance_sheet_raw_df.csv
    """
    try:
        logs_dir = _logs_dir_for_provider()
        base = f"{symbol}_{statement}"

        # 1) repr
        (logs_dir / f"{base}_raw_repr.txt").write_text(repr(obj))

        # 2) json() if available
        if hasattr(obj, "json"):
            (logs_dir / f"{base}_raw.json").write_text(json.dumps(obj.json(), indent=2))

        # 3) df if available (+ unique labels)
        if hasattr(obj, "df"):
            df = obj.df()
            df.to_csv(logs_dir / f"{base}_raw_df.csv", index=False)
            df.to_json(logs_dir / f"{base}_raw_df.json", orient="records", indent=2)

            if "Breakdown" in df.columns:
                with (logs_dir / f"{base}_raw_unique_labels.txt").open("w", encoding="utf-8") as f:
                    for lab in df["Breakdown"].astype(str).unique():
                        f.write(lab + "\n")

        logger.debug("[DBETA][%s] raw dumps written for %s", symbol, statement)
    except Exception as e:
        # Never let diagnostics break the fetch
        logger.warning("dump_defeatbeta_raw failure for %s/%s: %s", symbol, statement, e)
# -------------------------------------------------------------------------------


class _FallbackStatements(NamedTuple):
    is_rows: list
    bs_rows: list
    cf_rows: list
    earn_rows: list
    div_rows: list
    next_earnings_date: datetime | None


class DefeatBetaProvider(StockDataProvider):
    """
    Defeat Beta provider with:
      - Correct method invocation for DBeta (e.g., ticker.quarterly_income_statement())
      - Robust normalization for Defeat Beta .df() shape (Breakdown col, drop TTM, '*' -> NaN)
      - Expanded alias-based mapping for row labels to DB schema fields
      - Timeout wrapper invoking callables INSIDE the timeout
      - yfinance fallback + gap-fill (IS/BS/CF/Earnings/Dividends, next_earnings_date)
      - Coverage-aware filtering for fallback ("only_after" (year, quarter))
      - NEW: price_history (+ optional start/end filtering), splits (+ optional start filtering),
             revenue_forecast, earnings_forecast, company_summary
    """

    # ---------------------------------------------------------------------
    # Expanded aliases tuned to Defeat Beta labels you shared
    # ---------------------------------------------------------------------

    # Income Statement aliases
    DB_INCOME_ALIASES: ClassVar[dict[str, list[str]]] = {
        # Core P&L
        'revenue': ['Total Revenue', 'Operating Revenue'],
        # --- Phase 3 additions ---
        'interest_income': ['Non-Operating Interest Income'],
        'effective_tax_rate': ['Tax Rate for Calcs'],
        # Phase 5 — Tier 2 additions
        'total_unusual_items': ['Total Unusual Items'],
        'special_charges': ['Special Income Charges', 'Restructuring & Mergers Acquisition', 'Write Off'],
        # -------------------------
        'cost_of_goods_sold': ['Cost of Revenue'],
        'gross_profit': ['Gross Profit'],

        # Opex + components
        'operating_expenses': ['Operating Expense'],
        'rd_expenses': ['Research & Development'],
        'sga_expenses': ['Selling General and Administrative'],

        # Operating result
        'operating_income': ['Operating Income'],

        # Non-operating and interest
        'non_operating_income_expense': [
            'Other Income Expense',
            'Other Non Operating Income Expenses',
            'Gain on Sale of Security',
        ],
        'interest_expense': ['Non-Operating Interest Expense', 'Interest Expense'],

        # Taxes / before tax
        'pretax_income': ['Pretax Income'],
        'tax_expense': ['Tax Provision'],

        # Income lines
        'net_income': [
            'Net Income Common Stockholders',
            'Net Income(Attributable to Parent Company Shareholders)',
            'Net Income Including Non-Controlling Interests',
            'Net Income from Continuing & Discontinued Operation',
            'Net Income Continuous Operations',
        ],
        'income_from_continuing_operations': ['Net Income Continuous Operations'],
        'discontinued_operations': ['Discontinued Operations'],
        'equity_in_earnings': ['Equity in Earnings'],
        'minority_interest': ['Minority Interests'],
        'preferred_dividends': ['Preferred Stock Dividends', 'Preferred Dividends'],
        'net_income_to_common': ['Net Income Common Stockholders'],

        # EBIT/EBITDA
        'ebit': ['EBIT'],
        'ebitda': ['EBITDA', 'Normalized EBITDA'],

        # Optional metrics present in some outputs
        'normalized_income': ['Normalized Income'],
        'total_expenses': ['Total Expenses'],
        'rent_expense': ['Rent Expense Supplemental'],

        # Per-share metrics
        'eps_basic': ['Basic EPS'],
        'eps_diluted': ['Diluted EPS'],
        'shares_outstanding_basic': ['Basic Average Shares'],
        'shares_outstanding_diluted': ['Diluted Average Shares'],
    }

    # Balance Sheet aliases
    DB_BALANCE_ALIASES: ClassVar[dict[str, list[str]]] = {
        # Assets
        'total_assets': ['Total Assets'],
        # Phase 5 — Tier 2 additions
        'capital_lease_obligations': ['Capital Lease Obligations', 'Long Term Capital Lease Obligation'],
        'total_non_current_liabilities': ['Total Non Current Liabilities'],
        'total_non_current_assets': ['Total non-current assets'],
        'tangible_book_value': ['Net Tangible Assets', 'Tangible Book Value'],
        'deferred_revenue_current': ['Current Deferred Revenue'],
        'deferred_revenue_non_current': ['Non Current Deferred Revenue'],
        'other_current_assets': ['Other Current Assets'],
        # --- Phase 3 additions ---
        'shares_outstanding': ['Ordinary Shares Number', 'Share Issued'],
        'invested_capital': ['Invested Capital'],
        # -------------------------
        'current_assets': ['Total Current Assets'],
        'cash_and_cash_equivalents': ['Cash And Cash Equivalents'],
        'accounts_receivable': ['Accounts receivable', 'Receivables'],
        'inventory': ['Inventory'],
        'property_plant_equipment_net': ['Net PPE'],
        'intangible_assets': ['Other Intangible Assets'],
        'goodwill': ['Goodwill'],

        # Liabilities
        'total_liabilities': ['Total Liabilities'],
        'current_liabilities': ['Total Current Liabilities'],
        'accounts_payable': ['Accounts Payable', 'Payables', 'Payables And Accrued Expenses'],
        'short_term_debt': ['Current Debt', 'Current Debt And Capital Lease Obligation'],
        'long_term_debt': ['Long Term Debt'],
        'total_debt': ['Total Debt'],

        # Equity
        'shareholders_equity': ["Stockholders' Equity", 'Common Stock Equity', 'Total Equity'],
        'retained_earnings': ['Retained Earnings'],
        'common_stock': ['Common Stock', 'Capital Stock'],

        # Extended
        'long_term_investments': [
            'Long Term Equity Investment',
            'Investment in Financial Assets',
            'Available for Sale Securities',
        ],
        'other_non_current_assets': ['Other Non Current Assets'],
        'other_current_liabilities': ['Other Current Liabilities'],
        'minority_interest': ['Minority Interest'],
        'total_liabilities_and_equity': ['Total Assets'],
    }

    # Cash Flow aliases
    DB_CASHFLOW_ALIASES: ClassVar[dict[str, list[str]]] = {
        # Operating
        'cash_from_operating_activities': ['Operating Cash Flow', 'Cash Flow from Continuing Operating Activities'],
         # Phase 5 — Tier 2 additions
        'net_change_in_cash': ['Changes in Cash'],
        'effect_of_fx_on_cash': ['Effect of Exchange Rate Changes'],
        'beginning_cash': ['Beginning Cash Position'],
        'ending_cash': ['End Cash Position'],
        'short_term_debt_net_change': ['Net Short Term Debt Issuance'],
        'asset_impairment_charge': ['Asset Impairment Charge'],
        'free_cash_flow': ['Free Cash Flow'],
        # --------------------------
        'net_income': ['Net Income from Continuing Operations'],
        'depreciation_amortization': ['Depreciation & Amortization', 'Depreciation Amortization Depletion'],
        'change_in_working_capital': ['Change In Working Capital'],
        'deferred_taxes': ['Deferred Income Tax', 'Deferred Tax'],
        'stock_based_compensation': ['Stock Based Compensation'],

        # Investing
        'capital_expenditures': ['Capital Expenditure (CapEx)', 'Purchase of PPE'],
        'acquisitions': ['Purchase of Business'],
        'asset_sales': ['Sale of Investment', 'Net PPE Purchase And Sale'],
        'investment_purchases': ['Purchase of Investment'],
        'cash_from_investing_activities': ['Cash Flow from Continuing Investing Activities', 'Investing Cash Flow'],

        # Financing
        'cash_from_financing_activities': [
            'Cash Flow from Continuing Financing Activities',
            'Financing Cash Flow',
        ],
        'debt_issued': ['Long Term Debt Issuance', 'Issuance of Debt'],
        'debt_repayment': ['Long Term Debt Payments', 'Repayment of Debt'],
        'dividends_paid': ['Cash Dividends Paid', 'Common Stock Dividend Paid'],
        'share_repurchases': ['Common Stock Payments', 'Repurchase of Capital Stock'],
        'share_issuance': ['Issuance of Capital Stock', 'Common Stock Issuance'],
    }

    # ---------------------------------------------------------------------
    # Provider applicability (exchange + security_type aware routing)
    # ---------------------------------------------------------------------
    @staticmethod
    def _provider_applicable(
        provider_name: str,
        exchange: str | None = None,
        security_type: str | None = None,
    ) -> bool:
        rules = PROVIDER_EXCHANGE_RULES.get(provider_name)
        if rules is None:
            return True
        if exchange and "exchanges" in rules and exchange.upper() not in rules["exchanges"]:
            return False
        return not (
            security_type
            and "security_types" in rules
            and security_type.lower() not in rules["security_types"]
        )

    @staticmethod
    async def warm_cache() -> None:
        """Pre-warm DuckDB httpfs cache by querying a known stock."""
        try:
            from providers.defeatbeta_runtime import import_get_duckdb_client
            get_duckdb_client = import_get_duckdb_client()
            client = get_duckdb_client()
            spec_url = "https://huggingface.co/datasets/defeatbeta/yahoo-finance-data/resolve/main/spec.json"
            client.query(f"SELECT * FROM '{spec_url}'")
            logger.info("DuckDB cache pre-warmed")
        except Exception as e:
            logger.warning(f"DuckDB cache pre-warm failed: {e}")

    def __init__(
        self,
        yfinance_provider: YFinanceProvider | None = None,
        edgar_provider: EdgarToolsProvider | None = None,
        stockdex_provider: StockdexMacrotrendsProvider | None = None,
    ):
        from config import settings
        self.settings = settings
        self.yfinance_provider = yfinance_provider
        self.edgar_provider = edgar_provider
        self.stockdex_provider = stockdex_provider
        logger.info(
            "DefeatBetaProvider initialized (edgar=%s, stockdex=%s, yfinance=%s)",
            edgar_provider is not None,
            stockdex_provider is not None,
            yfinance_provider is not None,
        )

    def get_ticker_info(self, ticker_symbol: str, exchange: str | None = None) -> TickerInfo | None:
        if self.yfinance_provider:
            try:
                return self.yfinance_provider.get_ticker_info(ticker_symbol, exchange=exchange)
            except Exception as e:
                logger.warning(f"YFinance get_ticker_info failed for {ticker_symbol}: {e!s}")
        return None

    def get_stock_details(self, ticker_symbol: str, exchange: str | None = None) -> StockDetails | None:
        if self.yfinance_provider:
            try:
                return self.yfinance_provider.get_stock_details(ticker_symbol, exchange=exchange)
            except Exception as e:
                logger.warning(f"YFinance get_stock_details failed for {ticker_symbol}: {e!s}")
        return None

    # ---------------------------------------------------------------------
    # Public entry: retry + fallback + gap-fill + coverage-aware filter
    # ---------------------------------------------------------------------
    async def get_all_financials_optimized(
        self,
        symbol: str,
        company_id: int,
        last_refreshed_fiscal_year: int | None = None,
        last_refreshed_fiscal_quarter: int | None = None,
        force_full_history: bool = False,
        min_fiscal_year: int | None = None,
        exchange: str | None = None,
        security_type: str | None = None,
    ) -> CompleteFundamentals:
        logger.info(f"Starting financials fetch for {symbol} (company_id={company_id})")
        last_error: Exception | None = None

        for attempt in range(self.settings.RETRY_MAX_ATTEMPTS):
            try:
                fin, gaps = await self._fetch_all_financials_internal(symbol, company_id)

                # incremental filter if not first load
                if not force_full_history and last_refreshed_fiscal_year is not None:
                    fin = self._filter_to_new_data(fin, last_refreshed_fiscal_year, last_refreshed_fiscal_quarter)

                # gap-fill missing statements from yfinance (if enabled)
                if self.settings.ENABLE_YFINANCE_FALLBACK and self.yfinance_provider:
                    only_after = None if force_full_history else (last_refreshed_fiscal_year, last_refreshed_fiscal_quarter)
                    fin = await self._fill_gaps_with_yfinance(fin, gaps, only_after=only_after, exchange=exchange, security_type=security_type)

                # strip rows older than min_fiscal_year
                if min_fiscal_year is not None:
                    fin = self._filter_by_min_year(fin, min_fiscal_year)

                logger.info(f"✅ Fetched {symbol}: {fin.total_rows_fetched} total rows")
                return fin

            except (TimeoutError, DefeatBetaException) as e:
                last_error = e
                if isinstance(e, NoDataError):
                    # NoDataError is a deterministic "this provider has no
                    # coverage for the symbol" verdict, not a transient fault.
                    # Retrying it with backoff and a shared DuckDB cache clear
                    # cannot change the result and races the other workers (I9).
                    # Canadian `.TO` tickers are the live case: DefeatBeta is a
                    # US dataset. The job layer already treats NO_DATA as
                    # terminal; go straight to the fallback instead.
                    logger.info(
                        "DefeatBeta has no data for %s (%s); skipping retries, "
                        "using fallback",
                        symbol, e.error_code,
                    )
                    break
                if attempt < self.settings.RETRY_MAX_ATTEMPTS - 1:
                    backoff = self.settings.RETRY_BACKOFF_SECONDS[attempt]
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.settings.RETRY_MAX_ATTEMPTS} failed for {symbol}: "
                        f"retrying in {backoff}s. Error: {e!s}"
                    )
                    # Deliberately no cache clear here. `get_duckdb_client()` is a
                    # process-wide singleton and `_clear_cache()` wipes the shared
                    # on-disk httpfs cache, so one symbol's transient retry evicted
                    # every other worker's downloads (and raced their file locks)
                    # under concurrency. The SDK validates cache freshness at client
                    # init, and a failed fetch still falls back to yfinance, so the
                    # global clear bought nothing and cost everyone (I9).
                    await asyncio.sleep(backoff)

        # total failure → fallback to yfinance
        if self.settings.ENABLE_YFINANCE_FALLBACK and self.yfinance_provider:
            logger.warning(f"Defeat-beta failed for {symbol}, attempting yfinance fallback")
            only_after = None if force_full_history else (last_refreshed_fiscal_year, last_refreshed_fiscal_quarter)
            fin = await self._fallback_to_yfinance(symbol, company_id, only_after=only_after, exchange=exchange, security_type=security_type)
            if min_fiscal_year is not None:
                fin = self._filter_by_min_year(fin, min_fiscal_year)
            return fin

        raise MaxRetriesExceededError(
            company_id=company_id,
            symbol=symbol,
            attempts=self.settings.RETRY_MAX_ATTEMPTS,
            last_error=last_error,
        )

    # -----------------------------------------------------------
    # NEW (enhanced): Market/Forecast/Summary fetchers
    #   - support start_date/end_date filters where applicable
    # -----------------------------------------------------------
    @staticmethod
    def _yfinance_result_is_sufficient(
        rows: list[dict[str, Any]],
        start_date: date | None,
        end_date: date | None,
    ) -> bool:
        """Whether a YFinance result credibly covers the range DefeatBeta would serve.

        YFinance is retained as the primary source only when it actually provides a
        series: an unbounded (bootstrap) request needs a deep history, and a
        bounded request needs the rows it asked for. A single trailing quote
        satisfies neither and must not short-circuit the deep-history provider.

        shallow window: >= 2 rows threshold, revisit if a symbol legitimately
        trades on <2 days within the requested range.
        """
        if not rows:
            return False
        # Bootstrap (no explicit window): a real daily history, not a lone quote.
        if start_date is None and end_date is None:
            return len(rows) >= 2
        dates = sorted(r["price_date"] for r in rows if r.get("price_date"))
        if not dates:
            return False
        # Bounded request: accept when the earliest row reaches the start bound
        # (or near it), i.e. the window was actually covered rather than clipped.
        return not (start_date is not None and dates[0] > start_date + timedelta(days=7))

    async def get_price_history_optimized(
        self,
        symbol: str,
        company_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        exchange: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Priority: YFinance (primary) → DefeatBeta (last resort).
        Dates are applied client-side after provider retrieval.

        YFinance is a RECENT-QUOTE source, not a history source: for many symbols
        it returns a single trailing row (or a shallow window) rather than a deep
        daily series. Treating any non-empty YFinance result as the answer caused
        bootstrap to persist 1 row and then mark the symbol refreshed, starving
        price_history while looking successful. YFinance is therefore only
        accepted as sufficient when it actually covers the requested span;
        otherwise DefeatBeta, which serves the deep daily history, is consulted
        and its richer result is preferred.
        """
        # ── Primary: YFinance (full daily OHLCV, reliable) ──
        _yf_out: list[dict[str, Any]] = []
        if self.yfinance_provider:
            try:
                df = await asyncio.to_thread(self.yfinance_provider.get_price_history_df, symbol, exchange)
                if df is not None and not df.empty:
                    df = df.copy()
                    if start_date is not None:
                        df = df[df["price_date"] >= pd.Timestamp(start_date)]
                    if end_date is not None:
                        df = df[df["price_date"] <= pd.Timestamp(end_date)]
                    out: list[dict[str, Any]] = []
                    for _, r in df.iterrows():
                        dt = pd.to_datetime(str(r.get("price_date")), errors='coerce')
                        if pd.isna(dt):
                            continue
                        out.append({
                            "company_id": company_id,
                            "price_date": dt.date(),
                            "open_price": self._safe_decimal(r.get("open_price")),
                            "close_price": self._safe_decimal(r.get("close_price")),
                            "high_price": self._safe_decimal(r.get("high_price")),
                            "low_price": self._safe_decimal(r.get("low_price")),
                            "volume": int(r.get("volume")) if pd.notna(r.get("volume")) else None,
                            "data_source": "yfinance",
                        })
                    if out:
                        logger.info("[PRICE] YFinance returned %d rows for %s", len(out), symbol)
                        # Accept only when YFinance plausibly represents the range
                        # asked for. With no window (bootstrap) a deep series is
                        # required; a handful of trailing quotes must not be
                        # mistaken for one.
                        if not self._yfinance_result_is_sufficient(out, start_date, end_date):
                            logger.info(
                                "[PRICE] YFinance result for %s is a shallow window "
                                "(%d rows); consulting DefeatBeta for depth",
                                symbol, len(out),
                            )
                            _yf_out = out
                        else:
                            return out
            except Exception as e:
                logger.warning("[PRICE] YFinance failed for %s: %s", symbol, e)

        # ── Fallback: DefeatBeta (deep daily history) ──
        try:
            rows = await self.fetch_price_history(symbol, company_id, start_date=start_date, end_date=end_date, exchange=exchange)
            if rows:
                logger.info("[PRICE] DefeatBeta returned %d rows for %s", len(rows), symbol)
                return rows
        except Exception as e:
            logger.warning("[PRICE] DefeatBeta failed for %s: %s", symbol, e)

        # DefeatBeta did not serve the range; fall back to whatever YFinance gave
        # rather than discarding a usable (if shallow) result.
        if _yf_out:
            logger.info(
                "[PRICE] DefeatBeta empty for %s; using %d YFinance rows",
                symbol, len(_yf_out),
            )
            return _yf_out

        logger.warning("[PRICE] All providers failed for %s", symbol)
        return []

    async def get_splits_optimized(
        self,
        symbol: str,
        company_id: int,
        start_date: date | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self.fetch_splits(symbol, company_id, start_date=start_date)
        if rows:
            return rows
        if self.yfinance_provider:
            df = await asyncio.to_thread(self.yfinance_provider.get_splits_df, symbol)
            if df is not None and not df.empty:
                if start_date is not None:
                    df = df[df["report_date"] >= pd.Timestamp(start_date)]
                out = []
                for _, r in df.iterrows():
                    dt = pd.to_datetime(str(r.get("report_date")), errors='coerce')
                    if pd.isna(dt):
                        continue
                    factor = str(r.get("split_factor")) if pd.notna(r.get("split_factor")) else None
                    reverse = False
                    if factor and ":" in factor:
                        try:
                            a, b = factor.split(":")
                            reverse = (Decimal(a) < Decimal(b))
                        except Exception:
                            pass
                    out.append({
                        "company_id": company_id,
                        "report_date": dt.date(),
                        "split_factor": factor,
                        "reverse_split": reverse,
                        "data_source": "yfinance",
                    })
                return out
        return []

    async def get_company_summary_optimized(self, symbol: str, company_id: int) -> dict[str, Any] | None:
        snap = await self.fetch_company_summary(symbol, company_id)
        if snap:
            return snap
        if self.yfinance_provider:
            s = await asyncio.to_thread(self.yfinance_provider.get_summary_snapshot, symbol)
            if s:
                s["company_id"] = company_id
                return s
        return None

    # ---------------------------------------------------------------------
    # Primary DBeta fetch (statements & market)
    # ---------------------------------------------------------------------
    async def _fetch_all_financials_internal(self, symbol: str, company_id: int) -> tuple[CompleteFundamentals, GapDict]:
        try:
            ticker = Ticker(symbol)
            logger.debug(f"Created Ticker object for {symbol}")

            tasks = [
                self._fetch_income_statements(ticker, symbol, company_id),
                self._fetch_balance_sheets(ticker, symbol, company_id),
                self._fetch_cash_flows(ticker, symbol, company_id),
                # _fetch_earnings removed - DefeatBeta ticker.earnings() API removed Feb 2026
                # YFinance fallback will populate earnings via get_earnings_data()
                self._fetch_dividends(ticker, symbol, company_id),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            income_rows, income_gaps = self._extract_pair_result(results[0], IncomeStatementRows(rows=[]))
            balance_rows, balance_gaps = self._extract_pair_result(results[1], BalanceSheetRows(rows=[]))
            cash_rows, cash_gaps = self._extract_pair_result(results[2], CashFlowRows(rows=[]))
            # earnings_rows - now empty from DefeatBeta, filled by YFinance fallback
            earnings_rows: EarningsRows = EarningsRows(rows=[])
            # dividends is at index 3 (4th task in the list)
            dividend_rows: DividendRows = self._extract_result(results[3], DividendRows(rows=[]))

            if not any([income_rows.rows, balance_rows.rows, cash_rows.rows]):
                raise NoDataError(symbol, ['income_statements', 'balance_sheets', 'cash_flows'])

            # next earnings date
            next_earnings = await self._fetch_next_earnings_date(ticker, symbol)

            gaps: GapDict = {
                "is": income_gaps,
                "bs": balance_gaps,
                "cf": cash_gaps,
            }

            fin = CompleteFundamentals(
                company_id=company_id,
                symbol=symbol,
                income_statements=income_rows,
                balance_sheets=balance_rows,
                cash_flows=cash_rows,
                earnings=earnings_rows,
                dividends=dividend_rows,
                next_earnings_date=next_earnings,
                fetched_at=now_utc(),
            )
            return fin, gaps

        except NoDataError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch financials for {symbol}: {e!s}", exc_info=True)
            raise DefeatBetaException(
                message=f"Failed to fetch financials for {symbol}: {e!s}",
                error_code="DEFEAT_BETA_FETCH_ERROR",
                details={"symbol": symbol, "original_error": str(e)},
            ) from e

    async def _fetch_income_statements(self, ticker: Ticker, symbol: str, company_id: int) -> tuple[IncomeStatementRows, set[GapKey]]:
        logger.debug("[DBETA][%s] enter _fetch_income_statements", symbol)
        try:
            all_rows: list[IncomeStatementRow] = []
            all_gaps: set[GapKey] = set()

            q_obj = await self._timeout_fetch(lambda: ticker.quarterly_income_statement(), f"quarterly_income_statement for {symbol}")
            if q_obj is not None:
                dump_defeatbeta_raw(symbol, "quarterly_income_statement", q_obj)
                q_df = q_obj.df() if hasattr(q_obj, 'df') else q_obj
                q_rows, q_gaps = self._parse_income_statement(q_df, company_id, is_quarterly=True, symbol=symbol)
                all_rows.extend(q_rows)
                all_gaps |= q_gaps

            a_obj = await self._timeout_fetch(lambda: ticker.annual_income_statement(), f"annual_income_statement for {symbol}")
            if a_obj is not None:
                dump_defeatbeta_raw(symbol, "annual_income_statement", a_obj)
                a_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                a_rows, a_gaps = self._parse_income_statement(a_df, company_id, is_quarterly=False, symbol=symbol)
                all_rows.extend(a_rows)
                all_gaps |= a_gaps

            return (IncomeStatementRows(rows=all_rows), all_gaps)
        except Exception as e:
            logger.warning(f"Income statement fetch failed for {symbol}: {e!s}")
            return (IncomeStatementRows(rows=[]), set())

    async def _fetch_balance_sheets(self, ticker: Ticker, symbol: str, company_id: int) -> tuple[BalanceSheetRows, set[GapKey]]:
        logger.debug("[DBETA][%s] enter _fetch_balance_sheets", symbol)
        try:
            all_rows: list[BalanceSheetRow] = []
            all_gaps: set[GapKey] = set()

            q_obj = await self._timeout_fetch(lambda: ticker.quarterly_balance_sheet(), f"quarterly_balance_sheet for {symbol}")
            if q_obj is not None:
                dump_defeatbeta_raw(symbol, "quarterly_balance_sheet", q_obj)
                q_df = q_obj.df() if hasattr(q_obj, 'df') else q_obj
                q_rows, q_gaps = self._parse_balance_sheet(q_df, company_id, is_quarterly=True, symbol=symbol)
                all_rows.extend(q_rows)
                all_gaps |= q_gaps

            a_obj = await self._timeout_fetch(lambda: ticker.annual_balance_sheet(), f"annual_balance_sheet for {symbol}")
            if a_obj is not None:
                # FIX: log only after null-check to avoid deref None
                try:
                    raw_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                    logger.debug("[DBETA][%s] annual BS raw columns: %s", symbol, list(raw_df.columns))
                except Exception:
                    pass
                dump_defeatbeta_raw(symbol, "annual_balance_sheet", a_obj)
                a_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                a_rows, a_gaps = self._parse_balance_sheet(a_df, company_id, is_quarterly=False, symbol=symbol)
                all_rows.extend(a_rows)
                all_gaps |= a_gaps

            return (BalanceSheetRows(rows=all_rows), all_gaps)
        except Exception as e:
            logger.warning(f"Balance sheet fetch failed for {symbol}: {e!s}")
            return (BalanceSheetRows(rows=[]), set())

    async def _fetch_cash_flows(self, ticker: Ticker, symbol: str, company_id: int) -> tuple[CashFlowRows, set[GapKey]]:
        logger.debug("[DBETA][%s] enter _fetch_cash_flows", symbol)
        try:
            all_rows: list[CashFlowRow] = []
            all_gaps: set[GapKey] = set()

            q_obj = await self._timeout_fetch(lambda: ticker.quarterly_cash_flow(), f"quarterly_cash_flow for {symbol}")
            if q_obj is not None:
                dump_defeatbeta_raw(symbol, "quarterly_cash_flow", q_obj)
                q_df = q_obj.df() if hasattr(q_obj, 'df') else q_obj
                q_rows, q_gaps = self._parse_cash_flow(q_df, company_id, is_quarterly=True, symbol=symbol)
                all_rows.extend(q_rows)
                all_gaps |= q_gaps

            a_obj = await self._timeout_fetch(lambda: ticker.annual_cash_flow(), f"annual_cash_flow for {symbol}")
            if a_obj is not None:
                dump_defeatbeta_raw(symbol, "annual_cash_flow", a_obj)
                a_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                a_rows, a_gaps = self._parse_cash_flow(a_df, company_id, is_quarterly=False, symbol=symbol)
                all_rows.extend(a_rows)
                all_gaps |= a_gaps

            return (CashFlowRows(rows=all_rows), all_gaps)
        except Exception as e:
            logger.warning(f"Cash flow fetch failed for {symbol}: {e!s}")
            return (CashFlowRows(rows=[]), set())

    # _fetch_earnings removed Feb 2026 - DefeatBeta ticker.earnings() API no longer exists
    # Earnings data now populated via YFinance fallback in _fill_gaps_with_yfinance()
    # See yfinance_provider.py get_earnings_data() for the implementation

    async def _fetch_dividends(self, ticker: Ticker, symbol: str, company_id: int) -> DividendRows:
        """
        DBeta dividends() often returns (symbol, report_date, amount).
        frequency/record_date are typically not present -> left None unless present.
        """
        try:
            div_obj = await self._timeout_fetch(lambda: ticker.dividends(), f"dividends for {symbol}")
            div_df = div_obj.df() if hasattr(div_obj, 'df') else div_obj
            if div_df is None or div_df.empty:
                return DividendRows(rows=[])
            return DividendRows(rows=self._parse_dividends(div_df, company_id, symbol=symbol, provider='dbeta'))
        except Exception as e:
            logger.warning(f"Dividends fetch failed for {symbol}: {e!s}")
            return DividendRows(rows=[])

    async def fetch_next_earnings_date(self, symbol: str) -> date | None:
        """
        Public method — fetch the next earnings date for a symbol.
        Lightweight (single ticker.calendar() call), suitable for calendar sync.
        """
        try:
            ticker = Ticker(symbol)
            return await self._fetch_next_earnings_date(ticker, symbol)
        except Exception as e:
            logger.warning("fetch_next_earnings_date failed for %s: %s", symbol, e)
            return None

    async def _fetch_next_earnings_date(self, ticker: Ticker, symbol: str) -> date | None:
        """
        Uses Ticker.calendar() per docs; extracts 'report_date' as next earnings date (if present).
        """
        try:
            cal_obj = await self._timeout_fetch(lambda: ticker.calendar(), f"calendar for {symbol}")
            df = cal_obj.df() if hasattr(cal_obj, 'df') else cal_obj
            if df is not None and not df.empty and 'report_date' in df.columns:
                df = df.copy()
                df['report_date'] = pd.to_datetime(df['report_date'], errors='coerce')
                future = df[df['report_date'] >= pd.Timestamp(now_utc().date())].sort_values('report_date')
                if not future.empty:
                    return future.iloc[0]['report_date'].date()
                # else: fallback to earliest available
                df = df.sort_values('report_date')
                if not df.empty and not pd.isna(df.iloc[0]['report_date']):
                    return df.iloc[0]['report_date'].date()
        except Exception as e:
            self._log_debug_once(f"Failed to fetch earnings date for {symbol}: {e}")
        return None

    # ---------------------------------------------------------------------
    # Fallbacks (YFinance): full fallback and gap-fill
    # ---------------------------------------------------------------------

    async def _fetch_all_fallback_statements(
        self,
        symbol: str,
        company_id: int,
        only_after: tuple[int | None, int | None] | None = None,
        exchange: str | None = None,
        security_type: str | None = None,
    ) -> _FallbackStatements:
        fyq_filter = only_after

        yf_q_is, q_src = await self._fetch_statement_df_with_fallback(symbol, "get_quarterly_income_statement_df", exchange, security_type)
        yf_a_is, a_src = await self._fetch_statement_df_with_fallback(symbol, "get_annual_income_statement_df", exchange, security_type)
        is_rows = self._parse_yf_income_statement(yf_q_is, company_id, True, symbol, fyq_filter, q_src) + \
                  self._parse_yf_income_statement(yf_a_is, company_id, False, symbol, fyq_filter, a_src)

        yf_q_bs, q_src = await self._fetch_statement_df_with_fallback(symbol, "get_quarterly_balance_sheet_df", exchange, security_type)
        yf_a_bs, a_src = await self._fetch_statement_df_with_fallback(symbol, "get_annual_balance_sheet_df", exchange, security_type)
        bs_rows = self._parse_yf_balance_sheet(yf_q_bs, company_id, True, symbol, fyq_filter, q_src) + \
                  self._parse_yf_balance_sheet(yf_a_bs, company_id, False, symbol, fyq_filter, a_src)

        yf_q_cf, q_src = await self._fetch_statement_df_with_fallback(symbol, "get_quarterly_cash_flow_df", exchange, security_type)
        yf_a_cf, a_src = await self._fetch_statement_df_with_fallback(symbol, "get_annual_cash_flow_df", exchange, security_type)
        cf_rows = self._parse_yf_cash_flow(yf_q_cf, company_id, True, symbol, fyq_filter, q_src) + \
                  self._parse_yf_cash_flow(yf_a_cf, company_id, False, symbol, fyq_filter, a_src)

        yf_earn = await asyncio.to_thread(self.yfinance_provider.get_earnings_data, symbol)
        earn_rows = self._build_earnings_rows_from_yf(company_id, yf_earn)

        yf_div = await asyncio.to_thread(self.yfinance_provider.get_dividends_df, symbol)
        div_rows = self._parse_dividends(yf_div, company_id, symbol, provider='yfinance') if (yf_div is not None and not yf_div.empty) else []

        next_earnings_date = None
        try:
            details = await asyncio.to_thread(self.yfinance_provider.get_stock_details, symbol)
            if details and details.next_earnings_date:
                next_earnings_date = details.next_earnings_date
        except Exception:
            pass

        return _FallbackStatements(is_rows, bs_rows, cf_rows, earn_rows, div_rows, next_earnings_date)

    async def _fallback_to_yfinance(
        self,
        symbol: str,
        company_id: int,
        only_after: tuple[int | None, int | None] | None = None,
        exchange: str | None = None,
        security_type: str | None = None,
    ) -> CompleteFundamentals:
        if not self.edgar_provider and not self.yfinance_provider:
            logger.warning(
                "Fallback failed: neither edgar_provider nor yfinance_provider configured"
            )
            return CompleteFundamentals(
                company_id=company_id,
                symbol=symbol,
                income_statements=IncomeStatementRows(rows=[]),
                balance_sheets=BalanceSheetRows(rows=[]),
                cash_flows=CashFlowRows(rows=[]),
                earnings=EarningsRows(rows=[]),
                dividends=DividendRows(rows=[]),
                fetched_at=now_utc(),
            )

        fb = await self._fetch_all_fallback_statements(symbol, company_id, only_after, exchange, security_type)

        return CompleteFundamentals(
            company_id=company_id,
            symbol=symbol,
            income_statements=IncomeStatementRows(rows=fb.is_rows),
            balance_sheets=BalanceSheetRows(rows=fb.bs_rows),
            cash_flows=CashFlowRows(rows=fb.cf_rows),
            earnings=EarningsRows(rows=fb.earn_rows),
            dividends=DividendRows(rows=fb.div_rows),
            next_earnings_date=fb.next_earnings_date,
            fetched_at=now_utc(),
        )

    async def _fill_gaps_with_yfinance(
        self,
        fin: CompleteFundamentals,
        gaps: GapDict,
        only_after: tuple[int | None, int | None] | None = None,
        exchange: str | None = None,
        security_type: str | None = None,
    ) -> CompleteFundamentals:
        if not self.yfinance_provider:
            return fin

        symbol = fin.symbol
        company_id = fin.company_id

        # ═══════════════════════════════════════════════════════════════════
        # Phase A: Per-period gap-fill
        #   Detects which quarterly periods DefeatBeta returned * for
        #   (dropped by validation gate) and fills them from the existing
        #   Edgar → YFinance fallback chain.
        # ═══════════════════════════════════════════════════════════════════

        for gap_key, quarter_method, parser, rows_list in [
            ("bs", "get_quarterly_balance_sheet_df", self._parse_yf_balance_sheet, fin.balance_sheets.rows),
            ("cf", "get_quarterly_cash_flow_df", self._parse_yf_cash_flow, fin.cash_flows.rows),
            ("is", "get_quarterly_income_statement_df", self._parse_yf_income_statement, fin.income_statements.rows),
        ]:
            # Gap periods are periods DefeatBeta returned empty or dropped by the
            # validation gate. They must ALWAYS be repairable: gating on `only_after`
            # left old gaps (e.g. FY2022) unrepaired forever on incremental refreshes.
            # `key not in existing` below dedupes; once healed `missing` empties and
            # the fetch is skipped (self-limiting).
            missing = {(fy, fq) for (fy, fq, _ped) in gaps.get(gap_key, set()) if fq is not None}
            if not missing:
                continue

            df, source = await self._fetch_statement_df_with_fallback(symbol, quarter_method, exchange, security_type)
            # Parse all periods — no only_after filter here, we filter by missing set below
            fallback_rows = parser(df, company_id, True, symbol, None, source)
            existing = {(r.fiscal_year, r.fiscal_quarter) for r in rows_list}

            added = 0
            for row in fallback_rows:
                key = (row.fiscal_year, row.fiscal_quarter)
                if key in missing and key not in existing:
                    rows_list.append(row)
                    added += 1
            if added:
                logger.info(
                    "[GAP-FILL][%s] %s: added %d rows from %s",
                    symbol, gap_key.upper(), added, source,
                )

        # ═══════════════════════════════════════════════════════════════════
        # Phase B: Table-level fallback
        #   Handles statements that are COMPLETELY empty (DefeatBeta returned
        #   zero rows, not * gaps). need_* is re-computed after Phase A may
        #   have added rows above.
        # ═══════════════════════════════════════════════════════════════════

        need_is = not fin.income_statements.rows
        need_bs = not fin.balance_sheets.rows
        need_cf = not fin.cash_flows.rows
        need_earn = not fin.earnings.rows
        need_div = not fin.dividends.rows
        need_next_earn = fin.next_earnings_date is None
        logger.debug("[DBETA][%s] need_bs=%s (rows=%d)", symbol, need_bs, len(fin.balance_sheets.rows))

        if need_is or need_bs or need_cf or need_earn or need_div or need_next_earn:
            fb = await self._fetch_all_fallback_statements(symbol, company_id, only_after, exchange, security_type)

        if need_is:
            fin.income_statements = IncomeStatementRows(rows=fb.is_rows)
        if need_bs:
            fin.balance_sheets = BalanceSheetRows(rows=fb.bs_rows)
        if need_cf:
            fin.cash_flows = CashFlowRows(rows=fb.cf_rows)
        if need_earn:
            fin.earnings = EarningsRows(rows=fb.earn_rows)
        if need_div and fb.div_rows:
            fin.dividends = DividendRows(rows=fb.div_rows)
        if need_next_earn:
            fin.next_earnings_date = fb.next_earnings_date

        if fin.income_statements.rows and any(
           r.shares_outstanding_diluted is None for r in fin.income_statements.rows
        ):
           fin = await self._fill_shares_gap(fin, symbol)

        return fin

    async def _fill_shares_gap(
       self,
       fin: CompleteFundamentals,
       symbol: str,
    ) -> CompleteFundamentals:
        """
        Field-level gap-fill for shares_outstanding_diluted.

        Strategy (in order of preference):
            1. yfinance income statement has shares for this period -> use it
                (already populated by _parse_yf_income_statement if called)
            2. yfinance info.sharesOutstanding -> backfill into rows missing shares
                (snapshot value, same for all years — acceptable for ratios)

        Only fills rows where shares_outstanding_diluted IS None.
        Skips rows that already have a value.
        """
        if not self.yfinance_provider:
            return fin
        try:
            # Attempt 1: fetch yfinance annual IS which may contain share counts
            yf_a_is = await asyncio.to_thread(
                self.yfinance_provider.get_annual_income_statement_df, symbol
            )
            if yf_a_is is not None and not yf_a_is.empty:
                # Build year -> shares map from yfinance IS
                shares_by_year: dict[int, int | None] = {}
                for col in yf_a_is.columns:
                    if not hasattr(col, "year"):
                        continue
                    fy = col.year
                    for label in ["DilutedAverageShares", "Diluted Average Shares",
                                  "BasicAverageShares", "Basic Average Shares",
                                  "Ordinary Shares Number"]:
                        if label in yf_a_is.index:
                            v = yf_a_is.loc[label, col]
                            if pd.notna(v):
                                shares_by_year[fy] = self._safe_int_field(
                                   pd.to_numeric(v, errors="coerce")
                                )
                                break
                # Fill annual IS rows with year-matched share counts
                if shares_by_year:
                    for row in fin.income_statements.rows:
                        if row.shares_outstanding_diluted is None and row.fiscal_year in shares_by_year:
                            row.shares_outstanding_diluted = shares_by_year[row.fiscal_year]
                            if row.shares_outstanding_basic is None:
                                row.shares_outstanding_basic = shares_by_year[row.fiscal_year]
                    # Check if any rows still missing shares
                    still_missing = any(
                        r.shares_outstanding_diluted is None for r in fin.income_statements.rows
                    )
                    if not still_missing:
                        logger.debug("[SHARES][%s] Filled from yfinance annual IS", symbol)
                        return fin

            # Attempt 2: yfinance info.sharesOutstanding (snapshot, applies to all years)
            snapshot_shares: int | None = None
            try:
                await asyncio.to_thread(self.yfinance_provider.get_stock_details, symbol)
                # get_stock_details caches yf.Ticker.info; sharesOutstanding lives there
                # Access the raw yfinance ticker to get sharesOutstanding directly
                import yfinance as yf
                info = await asyncio.to_thread(lambda: yf.Ticker(symbol.upper()).info)
                raw_shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
                if raw_shares:
                    snapshot_shares = self._safe_int_field(raw_shares)
            except Exception as e:
                logger.debug("[SHARES][%s] yfinance info fetch failed: %s", symbol, e)

            if snapshot_shares is not None:
                for row in fin.income_statements.rows:
                    if row.shares_outstanding_diluted is None:
                        row.shares_outstanding_diluted = snapshot_shares
                    if row.shares_outstanding_basic is None:
                        row.shares_outstanding_basic = snapshot_shares
                logger.debug("[SHARES][%s] Filled from yfinance sharesOutstanding snapshot", symbol)

        except Exception as e:
            logger.warning("[SHARES][%s] shares gap-fill failed: %s", symbol, e)

        return fin




    # -----------------------------------------------------------
    # NEW: DefeatBeta fetchers for new tables (+ date filters)
    # -----------------------------------------------------------
    async def fetch_price_history(
        self,
        symbol: str,
        company_id: int,
        start_date: date | None = None,
        end_date: date | None = None,
        exchange: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Returns rows for public.price_history (daily OHLCV).
        Applies client-side date filtering if start_date/end_date provided.
        """
        try:
            from .yfinance_provider import EXCHANGE_SUFFIX_MAP
            suffix = EXCHANGE_SUFFIX_MAP.get(exchange.upper()) if exchange else None
            sym_upper = symbol.upper()
            # Idempotent: never double-append (.TO + .TO => BCE.TO.TO)
            db_symbol = sym_upper + suffix if suffix and not sym_upper.endswith(suffix) else sym_upper
            t = Ticker(db_symbol)
            obj = await self._timeout_fetch(lambda: t.price(), f"price history for {symbol}")
            df = obj.df() if hasattr(obj, 'df') else obj
            if df is None or df.empty:
                return []
            rows = []
            # expected columns: symbol, report_date, open, close, high, low, volume
            df = df.copy()
            # Normalize date column
            if 'report_date' in df.columns:
                df['report_date'] = pd.to_datetime(df['report_date'], errors='coerce')
            else:
                # best-effort: try common date-like headers
                date_col = next((c for c in df.columns if str(c).lower() in ('date', 'pricedate', 'price_date')), None)
                if date_col:
                    df['report_date'] = pd.to_datetime(df[date_col], errors='coerce')
                else:
                    return []

            # Apply optional filters
            if start_date is not None:
                df = df[df['report_date'] >= pd.Timestamp(start_date)]
            if end_date is not None:
                df = df[df['report_date'] <= pd.Timestamp(end_date)]

            for _, r in df.iterrows():
                dt = r.get('report_date')
                if pd.isna(dt):
                    continue
                rows.append({
                    "company_id": company_id,
                    "price_date": dt.date(),
                    "open_price": self._safe_decimal(r.get('open')),
                    "close_price": self._safe_decimal(r.get('close')),
                    "high_price": self._safe_decimal(r.get('high')),
                    "low_price": self._safe_decimal(r.get('low')),
                    "volume": int(r.get('volume')) if pd.notna(r.get('volume')) else None,
                    "data_source": "defeatbeta",
                })
            return rows
        except Exception as e:
            self._log_debug_once(f"Price history fetch failed for {symbol}: {e}")
            return []

    async def fetch_splits(
        self,
        symbol: str,
        company_id: int,
        start_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """
        Returns rows for public.splits
        """
        try:
            t = Ticker(symbol)
            obj = await self._timeout_fetch(lambda: t.splits(), f"splits for {symbol}")
            df = obj.df() if hasattr(obj, 'df') else obj
            if df is None or df.empty:
                return []
            rows = []
            df = df.copy()
            # Normalize date
            if 'report_date' in df.columns:
                df['report_date'] = pd.to_datetime(df['report_date'], errors='coerce')
            else:
                date_col = next((c for c in df.columns if str(c).lower() in ('date', 'reportdate', 'split_date')), None)
                if date_col:
                    df['report_date'] = pd.to_datetime(df[date_col], errors='coerce')
                else:
                    return []

            # Date filter if provided
            if start_date is not None:
                df = df[df['report_date'] >= pd.Timestamp(start_date)]

            for _, r in df.iterrows():
                dt = r.get('report_date')
                if pd.isna(dt):
                    continue
                factor = str(r.get('split_factor') or "").strip()
                reverse = False
                if ":" in factor:
                    try:
                        a, b = factor.split(":")
                        reverse = (Decimal(a) < Decimal(b))
                    except Exception:
                        pass
                rows.append({
                    "company_id": company_id,
                    "report_date": dt.date(),
                    "split_factor": factor or None,
                    "reverse_split": reverse,
                    "data_source": "defeatbeta",
                })
            return rows
        except Exception as e:
            self._log_debug_once(f"Splits fetch failed for {symbol}: {e}")
            return []

    async def fetch_revenue_forecast(self, symbol: str, company_id: int) -> list[dict[str, Any]]:
        """
        Maps defeatbeta.ticker.revenue_forecast() into public.revenue_forecast rows
        """
        try:
            t = Ticker(symbol)
            obj = await self._timeout_fetch(lambda: t.revenue_forecast(), f"revenue_forecast for {symbol}")
            df = obj.df() if hasattr(obj, 'df') else obj
            if df is None or df.empty:
                return []
            rows = []
            for _, r in df.iterrows():
                dt = pd.to_datetime(str(r.get('report_date')), errors='coerce')
                if pd.isna(dt):
                    continue
                rows.append({
                    "company_id": company_id,
                    "report_date": dt.date(),
                    "period_type": str(r.get('period_type') or 'annual'),
                    "estimate_revenue_growth": self._safe_decimal(r.get('estimate_revenue_growth')),
                    "number_of_analysts": int(r.get('number_of_analysts')) if pd.notna(r.get('number_of_analysts')) else None,
                    "estimate_avg_revenue": self._safe_decimal(r.get('estimate_avg_revenue')),
                    "estimate_high_revenue": self._safe_decimal(r.get('estimate_high_revenue')),
                    "estimate_low_revenue": self._safe_decimal(r.get('estimate_low_revenue')),
                    "year_ago_estimate_avg_revenue": self._safe_decimal(r.get('year_ago_estimate_avg_revenue')),
                    "currency": (r.get('currency') or 'USD'),
                    "provider": "defeatbeta",
                })
            return rows
        except Exception as e:
            self._log_debug_once(f"Revenue forecast fetch failed for {symbol}: {e}")
            return []

    async def fetch_earnings_forecast(self, symbol: str, company_id: int) -> list[dict[str, Any]]:
        """
        Maps defeatbeta.ticker.earnings_forecast() into public.earnings_forecast rows
        """
        try:
            t = Ticker(symbol)
            obj = await self._timeout_fetch(lambda: t.earnings_forecast(), f"earnings_forecast for {symbol}")
            df = obj.df() if hasattr(obj, 'df') else obj
            if df is None or df.empty:
                return []
            rows = []
            for _, r in df.iterrows():
                dt = pd.to_datetime(str(r.get('report_date')), errors='coerce')
                if pd.isna(dt):
                    continue
                rows.append({
                    "company_id": company_id,
                    "report_date": dt.date(),
                    "period_type": str(r.get('period_type') or 'annual'),
                    "currency": (r.get('currency') or 'USD'),
                    "estimate_eps_growth": self._safe_decimal(r.get('estimate_eps_growth')),
                    "estimate_avg_eps": self._safe_decimal(r.get('estimate_avg_eps')),
                    "estimate_high_eps": self._safe_decimal(r.get('estimate_high_eps')),
                    "estimate_low_eps": self._safe_decimal(r.get('estimate_low_eps')),
                    "number_of_analysts": int(r.get('number_of_analysts')) if pd.notna(r.get('number_of_analysts')) else None,
                    "thirty_days_ago_estimate_avg_eps": self._safe_decimal(r.get('thirty_days_ago_estimate_avg_eps')),
                    "sixty_days_ago_estimate_avg_eps": self._safe_decimal(r.get('sixty_days_ago_estimate_avg_eps')),
                    "ninety_days_ago_estimate_avg_eps": self._safe_decimal(r.get('ninety_days_ago_estimate_avg_eps')),
                    "year_ago_estimate_avg_eps": self._safe_decimal(r.get('year_ago_estimate_avg_eps')),
                    "provider": "defeatbeta",
                })
            return rows
        except Exception as e:
            self._log_debug_once(f"Earnings forecast fetch failed for {symbol}: {e}")
            return []

    async def fetch_company_summary(self, symbol: str, company_id: int) -> dict[str, Any] | None:
        """
        One row for public.company_summary; snapshot_date defaults to today.

        Uses individual Ticker data methods (ttm_pe, enterprise_value, etc.)
        since Ticker.summary() does not exist in defeatbeta-api.
        """
        try:
            t = Ticker(symbol)

            pe_df = await self._timeout_fetch(lambda: t.ttm_pe(), f"ttm_pe for {symbol}")
            ev_df = await self._timeout_fetch(lambda: t.enterprise_value(), f"ev for {symbol}")
            ev_ebitda_df = await self._timeout_fetch(lambda: t.enterprise_to_ebitda(), f"ev_ebitda for {symbol}")
            mcap_df = await self._timeout_fetch(lambda: t.market_capitalization(), f"mcap for {symbol}")
            peg_df = await self._timeout_fetch(lambda: t.peg_ratio(), f"peg for {symbol}")
            shares_df = await self._timeout_fetch(lambda: t.shares(), f"shares for {symbol}")

            return {
                "company_id": company_id,
                "snapshot_date": now_utc().date(),
                "market_cap": self._safe_decimal(self._extract_latest_metric(mcap_df, 'market_capitalization')),
                "enterprise_value": self._safe_decimal(self._extract_latest_metric(ev_df, 'enterprise_value')),
                "shares_outstanding": self._safe_decimal(self._extract_latest_metric(shares_df, 'shares_outstanding')),
                "implied_shares_outstanding": None,
                "beta": None,
                "trailing_pe": self._safe_decimal(self._extract_latest_metric(pe_df, 'ttm_pe')),
                "forward_pe": None,
                "trailing_eps": self._safe_decimal(self._extract_latest_metric(pe_df, 'ttm_eps')),
                "forward_eps": None,
                "enterprise_to_ebitda": self._safe_decimal(self._extract_latest_metric(ev_ebitda_df, 'ev_to_ebitda')),
                "enterprise_to_revenue": None,
                "peg_ratio": self._safe_decimal(self._extract_latest_metric(peg_df, 'peg_ratio')),
                "currency": "USD",
                "provider": "defeatbeta",
            }
        except Exception as e:
            self._log_debug_once(f"Company summary fetch failed for {symbol}: {e}")
            return None

    # ---------------------------------------------------------------------
    # Normalization + Parsers (Defeat Beta)
    # ---------------------------------------------------------------------
    def _clean_breakdown_label(self, s: str) -> str:
        if s is None:
            return ""
        s = html.unescape(str(s)).strip()
        s = s.replace('\u2019', "'")
        s = re.sub(r'^[+\s]+', '', s)
        s = re.sub(r'\s+', ' ', s)
        s = s.replace(' and ', ' & ')
        return s

    def _normalize_alias_key(self, s: str) -> str:
        return self._clean_breakdown_label(s)

    def _normalize_defeatbeta_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        - Ensure 'Breakdown' exists and becomes index
        - Replace '*' with NaN
        - Keep only date-like columns (YYYY-MM-DD), drop 'TTM'
        - Coerce to numerics
        """
        if df is None or df.empty:
            return pd.DataFrame()

        df = df.copy()

        if 'Breakdown' not in df.columns:
            for c in df.columns:
                if str(c).strip().lower() == 'breakdown':
                    df.rename(columns={c: 'Breakdown'}, inplace=True)
                    break

        if 'Breakdown' not in df.columns:
            return pd.DataFrame()

        df['Breakdown'] = df['Breakdown'].map(self._clean_breakdown_label)
        df.set_index('Breakdown', inplace=True)
        df.replace('*', pd.NA, inplace=True)

        kept_cols = []
        col_to_dt: dict[str, pd.Timestamp] = {}
        for c in df.columns:
            cs = str(c).strip()
            if cs.upper() == 'TTM':
                continue
            ts = pd.to_datetime(cs, format="%Y-%m-%d", errors='coerce')
            if pd.isna(ts):
                continue
            kept_cols.append(c)
            col_to_dt[c] = ts

        if not kept_cols:
            return pd.DataFrame()

        df = df[kept_cols]
        # Remove thousands separators before numeric coercion, preserving NaNs
        for c in df.columns:
            ser = df[c]
            df[c] = pd.to_numeric(
                ser.where(ser.isna(), ser.astype(str).str.replace(',', '', regex=False)),
                errors='coerce'
            )

        df.attrs['defeatbeta_col_dates'] = col_to_dt
        return df

    def _iter_defeatbeta_periods(self, df: pd.DataFrame, is_quarterly: bool):
        col_to_dt = df.attrs.get('defeatbeta_col_dates', {})
        if not col_to_dt:
            col_to_dt = {c: pd.to_datetime(str(c), errors='coerce') for c in df.columns}

        # IMPORTANT: deterministic chronological iteration (oldest -> newest)
        for c, ts in sorted(col_to_dt.items(), key=lambda kv: kv[1]):
            if pd.isna(ts):
                continue
            fy = int(ts.year)
            fq = int((ts.month - 1) // 3 + 1) if is_quarterly else None
            yield c, ts.date(), fy, fq

    def _db_val(self, df: pd.DataFrame, aliases: list[str], col: str):
        for key in (aliases or []):
            k = self._normalize_alias_key(key)
            if k in df.index:
                v = df.at[k, col]
                if pd.isna(v):
                    continue
                return v
        return None

    # ---- Income Statement parser (DBeta) ----
    def _parse_income_statement(self, raw_df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str) -> tuple[list[IncomeStatementRow], set[GapKey]]:
        rows: list[IncomeStatementRow] = []
        gaps: set[GapKey] = set()
        df = self._normalize_defeatbeta_df(raw_df)
        if df.empty:
            return rows, gaps

        a = self.DB_INCOME_ALIASES
        for col, period_end, fy, fq in self._iter_defeatbeta_periods(df, is_quarterly):
            fv = {
                'revenue': self._safe_decimal(self._db_val(df, a.get('revenue', []), col)),
                'cost_of_goods_sold': self._safe_decimal(self._db_val(df, a.get('cost_of_goods_sold', []), col)),
                'gross_profit': self._safe_decimal(self._db_val(df, a.get('gross_profit', []), col)),
                'operating_expenses': self._safe_decimal(self._db_val(df, a.get('operating_expenses', []), col)),
                'rd_expenses': self._safe_decimal(self._db_val(df, a.get('rd_expenses', []), col)),
                'sga_expenses': self._safe_decimal(self._db_val(df, a.get('sga_expenses', []), col)),
                'operating_income': self._safe_decimal(self._db_val(df, a.get('operating_income', []), col)),
                'interest_expense': self._safe_decimal(self._db_val(df, a.get('interest_expense', []), col)),
                'tax_expense': self._safe_decimal(self._db_val(df, a.get('tax_expense', []), col)),
                'net_income': self._safe_decimal(self._db_val(df, a.get('net_income', []), col)),
                'ebitda': self._safe_decimal(self._db_val(df, a.get('ebitda', []), col)),
                'non_operating_income_expense': self._safe_decimal(self._db_val(df, a.get('non_operating_income_expense', []), col)),
                'pretax_income': self._safe_decimal(self._db_val(df, a.get('pretax_income', []), col)),
                'equity_in_earnings': self._safe_decimal(self._db_val(df, a.get('equity_in_earnings', []), col)),
                'minority_interest': self._safe_decimal(self._db_val(df, a.get('minority_interest', []), col)),
                'income_from_continuing_operations': self._safe_decimal(self._db_val(df, a.get('income_from_continuing_operations', []), col)),
                'discontinued_operations': self._safe_decimal(self._db_val(df, a.get('discontinued_operations', []), col)),
                'net_income_to_common': self._safe_decimal(self._db_val(df, a.get('net_income_to_common', []), col)),
                'preferred_dividends': self._safe_decimal(self._db_val(df, a.get('preferred_dividends', []), col)),
                'ebit': self._safe_decimal(self._db_val(df, a.get('ebit', []), col)),
                'eps_basic': self._safe_decimal(self._db_val(df, a.get('eps_basic', []), col)),
                'eps_diluted': self._safe_decimal(self._db_val(df, a.get('eps_diluted', []), col)),
                'shares_outstanding_basic': self._safe_int_field(self._db_val(df, a.get('shares_outstanding_basic', []), col)),
                'shares_outstanding_diluted': self._safe_int_field(self._db_val(df, a.get('shares_outstanding_diluted', []), col)),
                'interest_income': self._safe_decimal(self._db_val(df, a.get('interest_income', []), col)),
                'effective_tax_rate': self._safe_decimal(self._db_val(df, a.get('effective_tax_rate', []), col)),
                'total_unusual_items': self._safe_decimal(self._db_val(df, a.get('total_unusual_items', []), col)),
                'special_charges': self._safe_decimal(self._db_val(df, a.get('special_charges', []), col)),
            }
            row = IncomeStatementRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=period_end,
                currency="USD",
                last_validated_at=None,
                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                validation_notes=None,
                field_sources=self._build_field_sources(fv, "defeat_beta"),
                **fv,
            )
            # Normalize row
            normalized_row = normalize_income_row(row)

            # Validate before adding to results
            validation_result = FinancialDataValidator.validate_income_statement(
                row=normalized_row.model_dump(),
                symbol=symbol
            )
            log_validation_result(validation_result)

            # Only add if no critical issues; track dropped periods as gaps
            if not validation_result.has_critical_issues():
                rows.append(normalized_row)
            else:
                gaps.add((fy, fq, period_end))

        return rows, gaps

    # ---- Balance Sheet parser (DBeta) ----
    def _parse_balance_sheet(self, raw_df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str) -> tuple[list[BalanceSheetRow], set[GapKey]]:
        rows: list[BalanceSheetRow] = []
        gaps: set[GapKey] = set()
        df = self._normalize_defeatbeta_df(raw_df)
        logger.debug("[DBETA][%s] BS kept date columns: %s", symbol, list(df.columns))
        logger.debug("[DBETA][%s] BS normalized labels (first 20): %s", symbol, list(df.index[:20]))
        if df.empty:
            return rows, gaps

        a = self.DB_BALANCE_ALIASES
        for col, period_end, fy, fq in self._iter_defeatbeta_periods(df, is_quarterly):

            # Coverage diagnostics for last column
            if not df.empty:
                last_col = sorted(df.columns)[-1]
                cov = self._debug_alias_coverage(df, self.DB_BALANCE_ALIASES, last_col)
                missing = [k for k, v in cov.items() if not v['matched']]
                logger.debug("[DBETA][%s] BS coverage for %s — missing canonicals: %s",
                            symbol, last_col, missing)

            fv = {
                'total_assets': self._safe_decimal(self._db_val(df, a.get('total_assets', []), col)),
                'current_assets': self._safe_decimal(self._db_val(df, a.get('current_assets', []), col)),
                'cash_and_cash_equivalents': self._safe_decimal(self._db_val(df, a.get('cash_and_cash_equivalents', []), col)),
                'accounts_receivable': self._safe_decimal(self._db_val(df, a.get('accounts_receivable', []), col)),
                'inventory': self._safe_decimal(self._db_val(df, a.get('inventory', []), col)),
                'property_plant_equipment_net': self._safe_decimal(self._db_val(df, a.get('property_plant_equipment_net', []), col)),
                'intangible_assets': self._safe_decimal(self._db_val(df, a.get('intangible_assets', []), col)),
                'goodwill': self._safe_decimal(self._db_val(df, a.get('goodwill', []), col)),
                'total_liabilities': self._safe_decimal(self._db_val(df, a.get('total_liabilities', []), col)),
                'current_liabilities': self._safe_decimal(self._db_val(df, a.get('current_liabilities', []), col)),
                'accounts_payable': self._safe_decimal(self._db_val(df, a.get('accounts_payable', []), col)),
                'short_term_debt': self._safe_decimal(self._db_val(df, a.get('short_term_debt', []), col)),
                'long_term_debt': self._safe_decimal(self._db_val(df, a.get('long_term_debt', []), col)),
                'total_debt': self._safe_decimal(self._db_val(df, a.get('total_debt', []), col)),
                'shareholders_equity': self._safe_decimal(self._db_val(df, a.get('shareholders_equity', []), col)),
                'retained_earnings': self._safe_decimal(self._db_val(df, a.get('retained_earnings', []), col)),
                'common_stock': self._safe_decimal(self._db_val(df, a.get('common_stock', []), col)),
                'long_term_investments': self._safe_decimal(self._db_val(df, a.get('long_term_investments', []), col)),
                'other_non_current_assets': self._safe_decimal(self._db_val(df, a.get('other_non_current_assets', []), col)),
                'other_current_liabilities': self._safe_decimal(self._db_val(df, a.get('other_current_liabilities', []), col)),
                'minority_interest': self._safe_decimal(self._db_val(df, a.get('minority_interest', []), col)),
                'total_liabilities_and_equity': self._safe_decimal(self._db_val(df, a.get('total_liabilities_and_equity', []), col)),
                'shares_outstanding': self._safe_int_field(self._db_val(df, a.get('shares_outstanding', []), col)),
                'invested_capital': self._safe_decimal(self._db_val(df, a.get('invested_capital', []), col)),
                'capital_lease_obligations': self._safe_decimal(self._db_val(df, a.get('capital_lease_obligations', []), col)),
                'total_non_current_liabilities': self._safe_decimal(self._db_val(df, a.get('total_non_current_liabilities', []), col)),
                'total_non_current_assets': self._safe_decimal(self._db_val(df, a.get('total_non_current_assets', []), col)),
                'tangible_book_value': self._safe_decimal(self._db_val(df, a.get('tangible_book_value', []), col)),
                'deferred_revenue_current': self._safe_decimal(self._db_val(df, a.get('deferred_revenue_current', []), col)),
                'deferred_revenue_non_current': self._safe_decimal(self._db_val(df, a.get('deferred_revenue_non_current', []), col)),
                'other_current_assets': self._safe_decimal(self._db_val(df, a.get('other_current_assets', []), col)),
            }

            if fv['total_debt'] is None and fv['short_term_debt'] is not None and fv['long_term_debt'] is not None:
                with contextlib.suppress(InvalidOperation):
                    fv['total_debt'] = Decimal(str(fv['short_term_debt'])) + Decimal(str(fv['long_term_debt']))

            if fv['total_liabilities_and_equity'] is None and fv['total_liabilities'] is not None and fv['shareholders_equity'] is not None:
                with contextlib.suppress(InvalidOperation):
                    fv['total_liabilities_and_equity'] = Decimal(str(fv['total_liabilities'])) + Decimal(str(fv['shareholders_equity'])) + (Decimal(str(fv['minority_interest'])) if fv['minority_interest'] is not None else Decimal('0'))

            row = BalanceSheetRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=period_end,
                currency="USD",
                last_validated_at=None,
                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                validation_notes=None,
                field_sources=self._build_field_sources(fv, "defeat_beta"),
                **fv,
            )
            # Normalize row
            normalized_row = normalize_balance_row(row)

            # Validate before adding to results
            validation_result = FinancialDataValidator.validate_balance_sheet(
                row=normalized_row.model_dump(),
                symbol=symbol
            )
            log_validation_result(validation_result)

            # Only add if no critical issues; track dropped periods as gaps
            if not validation_result.has_critical_issues():
                rows.append(normalized_row)
            else:
                gaps.add((fy, fq, period_end))
        return rows, gaps

    # ---- Cash Flow parser (DBeta) ----
    def _parse_cash_flow(self, raw_df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str) -> tuple[list[CashFlowRow], set[GapKey]]:
        rows: list[CashFlowRow] = []
        gaps: set[GapKey] = set()
        df = self._normalize_defeatbeta_df(raw_df)
        if df.empty:
            return rows, gaps

        a = self.DB_CASHFLOW_ALIASES
        for col, period_end, fy, fq in self._iter_defeatbeta_periods(df, is_quarterly):
            fv = {
                'cash_from_operating_activities': self._safe_decimal(self._db_val(df, a.get('cash_from_operating_activities', []), col)),
                'net_income': self._safe_decimal(self._db_val(df, a.get('net_income', []), col)),
                'depreciation_amortization': self._safe_decimal(self._db_val(df, a.get('depreciation_amortization', []), col)),
                'capital_expenditures': self._safe_decimal(self._db_val(df, a.get('capital_expenditures', []), col)),
                'cash_from_investing_activities': self._safe_decimal(self._db_val(df, a.get('cash_from_investing_activities', []), col)),
                'cash_from_financing_activities': self._safe_decimal(self._db_val(df, a.get('cash_from_financing_activities', []), col)),
                'dividends_paid': self._safe_decimal(self._db_val(df, a.get('dividends_paid', []), col)),
                'net_change_in_cash': self._safe_decimal(self._db_val(df, a.get('net_change_in_cash', []), col)),
                'effect_of_fx_on_cash': self._safe_decimal(self._db_val(df, a.get('effect_of_fx_on_cash', []), col)),
                'beginning_cash': self._safe_decimal(self._db_val(df, a.get('beginning_cash', []), col)),
                'ending_cash': self._safe_decimal(self._db_val(df, a.get('ending_cash', []), col)),
                'short_term_debt_net_change': self._safe_decimal(self._db_val(df, a.get('short_term_debt_net_change', []), col)),
                'asset_impairment_charge': self._safe_decimal(self._db_val(df, a.get('asset_impairment_charge', []), col)),
                'free_cash_flow': self._safe_decimal(self._db_val(df, a.get('free_cash_flow', []), col)),
                'change_in_working_capital': self._safe_decimal(self._db_val(df, a.get('change_in_working_capital', []), col)),
                'deferred_taxes': self._safe_decimal(self._db_val(df, a.get('deferred_taxes', []), col)),
                'stock_based_compensation': self._safe_decimal(self._db_val(df, a.get('stock_based_compensation', []), col)),
                'acquisitions': self._safe_decimal(self._db_val(df, a.get('acquisitions', []), col)),
                'asset_sales': self._safe_decimal(self._db_val(df, a.get('asset_sales', []), col)),
                'investment_purchases': self._safe_decimal(self._db_val(df, a.get('investment_purchases', []), col)),
                'debt_issued': self._safe_decimal(self._db_val(df, a.get('debt_issued', []), col)),
                'debt_repayment': self._safe_decimal(self._db_val(df, a.get('debt_repayment', []), col)),
                'share_repurchases': self._safe_decimal(self._db_val(df, a.get('share_repurchases', []), col)),
                'share_issuance': self._safe_decimal(self._db_val(df, a.get('share_issuance', []), col)),
            }
            row = CashFlowRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=period_end,
                currency="USD",
                last_validated_at=None,
                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                validation_notes=None,
                field_sources=self._build_field_sources(fv, "defeat_beta"),
                **fv,
            )
            # Normalize row
            normalized_row = normalize_cashflow_row(row)

            # Validate before adding to results
            validation_result = FinancialDataValidator.validate_cash_flow(
                row=normalized_row.model_dump(),
                symbol=symbol
            )
            log_validation_result(validation_result)

            # Only add if no critical issues; track dropped periods as gaps
            if not validation_result.has_critical_issues():
                rows.append(normalized_row)
            else:
                gaps.add((fy, fq, period_end))
        return rows, gaps

    # ---- Dividends parser (DBeta & YF) ----
    def _parse_dividends(self, df: pd.DataFrame, company_id: int, symbol: str, provider: str) -> list[DividendRow]:
        rows: list[DividendRow] = []
        if df is None or df.empty:
            return rows
        # Map possible column names
        cols = {c.lower(): c for c in df.columns}
        exd_col = cols.get('ex_dividend_date') or cols.get('report_date') or cols.get('date')
        amt_col = cols.get('dividend') or cols.get('amount')

        # Optional fields if present
        pay_col = cols.get('payment_date')
        rec_col = cols.get('record_date')
        freq_col = cols.get('frequency')

        if not exd_col or not amt_col:
            return rows

        for _, r in df.iterrows():
            exd = r.get(exd_col)
            if pd.isna(exd):
                continue
            ts = pd.to_datetime(str(exd), errors='coerce')
            if pd.isna(ts):
                continue

            pay_date = None
            if pay_col:
                pdv = r.get(pay_col)
                if pd.notna(pdv):
                    pdt = pd.to_datetime(str(pdv), errors='coerce')
                    pay_date = pdt.date() if not pd.isna(pdt) else None

            rec_date = None
            if rec_col:
                rdv = r.get(rec_col)
                if pd.notna(rdv):
                    rdt = pd.to_datetime(str(rdv), errors='coerce')
                    rec_date = rdt.date() if not pd.isna(rdt) else None

            freq = None
            if freq_col:
                fv = r.get(freq_col)
                if pd.notna(fv):
                    freq = str(fv)

            rows.append(DividendRow(
                company_id=company_id,
                ex_dividend_date=ts.date(),
                payment_date=pay_date,
                record_date=rec_date,
                dividend_amount=self._safe_decimal(r.get(amt_col)),
                dividend_type='regular',
                currency='USD',
                frequency=freq,
                last_validated_at=None,
                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE if provider == 'dbeta' else self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                data_source="defeat_beta" if provider == 'dbeta' else "yfinance",
                validation_notes=None,
            ))
        return rows

    # ---------------------------------------------------------------------
    # YF parsers (best-effort to schema)  [unchanged]
    # ---------------------------------------------------------------------
    def _parse_yf_income_statement(
        self, df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str,
        only_after: tuple[int | None, int | None] | None,
        source: str = "yfinance"
    ) -> list[IncomeStatementRow]:
        rows: list[IncomeStatementRow] = []
        if df is None or df.empty:
            return rows

        for col in df.columns:
            if not hasattr(col, 'year'):
                continue
            fy = col.year
            fq = (col.month - 1) // 3 + 1 if is_quarterly else None
            if only_after and not self._is_new_fiscal_period(fy, fq, only_after[0], only_after[1]):
                continue

            def gv(keys: list[str], col=col) -> Any:
                for k in keys:
                    if k in df.index:
                        v = df.loc[k, col]
                        if pd.isna(v):
                            continue
                        return v
                return None

            fv = {
                'revenue': self._safe_decimal(pd.to_numeric(gv(['Total Revenue', 'TotalRevenue', 'Revenue']), errors='coerce')),
                'cost_of_goods_sold': self._safe_decimal(pd.to_numeric(gv(['Cost Of Revenue', 'Cost of Revenue', 'CostOfRevenue']), errors='coerce')),
                'gross_profit': self._safe_decimal(pd.to_numeric(gv(['Gross Profit', 'GrossProfit']), errors='coerce')),
                'operating_income': self._safe_decimal(pd.to_numeric(gv(['Operating Income', 'OperatingIncome']), errors='coerce')),
                'interest_expense': self._safe_decimal(pd.to_numeric(gv(['Interest Expense', 'InterestExpense']), errors='coerce')),
                'tax_expense': self._safe_decimal(pd.to_numeric(gv(['Income Tax Expense', 'Tax Provision']), errors='coerce')),
                'net_income': self._safe_decimal(pd.to_numeric(gv(['Net Income', 'NetIncome', 'Net Income Common Stockholders']), errors='coerce')),
                'ebitda': self._safe_decimal(pd.to_numeric(gv(['EBITDA']), errors='coerce')),
                'ebit': self._safe_decimal(pd.to_numeric(gv(['EBIT']), errors='coerce')),
                'pretax_income': self._safe_decimal(pd.to_numeric(gv(['Pretax Income', 'Income Before Tax', 'Earnings Before Tax']), errors='coerce')),
                'shares_outstanding_basic': self._safe_int_field(
                    pd.to_numeric(gv(['BasicAverageShares', 'Basic Average Shares', 'Ordinary Shares Number']), errors='coerce')
                ),
                'shares_outstanding_diluted': self._safe_int_field(
                    pd.to_numeric(gv(['DilutedAverageShares', 'Diluted Average Shares', 'BasicAverageShares', 'Basic Average Shares']), errors='coerce')
                ),
                'eps_basic': self._safe_decimal(pd.to_numeric(gv(['Basic EPS', 'BasicEps']), errors='coerce')),
                'eps_diluted': self._safe_decimal(pd.to_numeric(gv(['Diluted EPS', 'DilutedEps']), errors='coerce')),
            }
            row = IncomeStatementRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=col.date(),
                currency="USD",
                last_validated_at=None,
                confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                data_source=source,
                validation_notes=None,
                field_sources=self._build_field_sources(fv, source),
                **fv,
            )
            # Validate before adding to results; skip junk rows (no gaps channel here)
            validation_result = FinancialDataValidator.validate_income_statement(
                row=row.model_dump(),
                symbol=symbol
            )
            log_validation_result(validation_result)
            if not validation_result.has_critical_issues():
                rows.append(row)
        return rows

    def _parse_yf_balance_sheet(
        self, df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str,
        only_after: tuple[int | None, int | None] | None,
        source: str = "yfinance"
    ) -> list[BalanceSheetRow]:
        rows: list[BalanceSheetRow] = []
        if df is None or df.empty:
            return rows

        for col in df.columns:
            if not hasattr(col, 'year'):
                continue
            fy = col.year
            fq = (col.month - 1) // 3 + 1 if is_quarterly else None
            if only_after and not self._is_new_fiscal_period(fy, fq, only_after[0], only_after[1]):
                continue

            def gv(keys: list[str], col=col) -> Any:
                for k in keys:
                    if k in df.index:
                        v = df.loc[k, col]
                        if pd.isna(v):
                            continue
                        return v
                return None

            fv = {
                'total_assets': self._safe_decimal(pd.to_numeric(gv(['Total Assets', 'TotalAssets']), errors='coerce')),
                'current_assets': self._safe_decimal(pd.to_numeric(gv(['Total Current Assets', 'TotalCurrentAssets']), errors='coerce')),
                'cash_and_cash_equivalents': self._safe_decimal(pd.to_numeric(gv(['Cash And Cash Equivalents', 'CashAndCashEquivalents']), errors='coerce')),
                'accounts_receivable': self._safe_decimal(pd.to_numeric(gv(['Accounts Receivable', 'Receivables']), errors='coerce')),
                'inventory': self._safe_decimal(pd.to_numeric(gv(['Inventory']), errors='coerce')),
                'property_plant_equipment_net': self._safe_decimal(pd.to_numeric(gv(['Net PPE', 'Property Plant And Equipment Net']), errors='coerce')),
                'intangible_assets': self._safe_decimal(pd.to_numeric(gv(['Intangible Assets']), errors='coerce')),
                'goodwill': self._safe_decimal(pd.to_numeric(gv(['Goodwill']), errors='coerce')),
                'total_liabilities': self._safe_decimal(pd.to_numeric(gv(['Total Liabilities', 'TotalLiab']), errors='coerce')),
                'current_liabilities': self._safe_decimal(pd.to_numeric(gv(['Total Current Liabilities', 'TotalCurrentLiabilities']), errors='coerce')),
                'accounts_payable': self._safe_decimal(pd.to_numeric(gv(['Accounts Payable']), errors='coerce')),
                'short_term_debt': self._safe_decimal(pd.to_numeric(gv(['Short Term Debt']), errors='coerce')),
                'long_term_debt': self._safe_decimal(pd.to_numeric(gv(['Long Term Debt', 'LongTermDebt']), errors='coerce')),
                'total_debt': self._safe_decimal(pd.to_numeric(gv(['Total Debt']), errors='coerce')),
                'shareholders_equity': self._safe_decimal(pd.to_numeric(gv(["Stockholders' Equity", 'Total Stockholder Equity']), errors='coerce')),
                'retained_earnings': self._safe_decimal(pd.to_numeric(gv(['Retained Earnings']), errors='coerce')),
                'long_term_investments': self._safe_decimal(pd.to_numeric(gv(['Long Term Investments', 'LongTermInvestments']), errors='coerce')),
                'minority_interest': self._safe_decimal(pd.to_numeric(gv(['Minority Interest', 'MinorityInterest']), errors='coerce')),
            }
            row = BalanceSheetRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=col.date(),
                currency="USD",
                last_validated_at=None,
                confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                data_source=source,
                validation_notes=None,
                field_sources=self._build_field_sources(fv, source),
                **fv,
            )
            # Validate before adding to results; skip junk rows (no gaps channel here)
            validation_result = FinancialDataValidator.validate_balance_sheet(
                row=row.model_dump(),
                symbol=symbol
            )
            log_validation_result(validation_result)
            if not validation_result.has_critical_issues():
                rows.append(row)
        return rows

    def _parse_yf_cash_flow(
        self, df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str,
        only_after: tuple[int | None, int | None] | None,
        source: str = "yfinance"
    ) -> list[CashFlowRow]:
        rows: list[CashFlowRow] = []
        if df is None or df.empty:
            return rows

        for col in df.columns:
            if not hasattr(col, 'year'):
                continue
            fy = col.year
            fq = (col.month - 1) // 3 + 1 if is_quarterly else None
            if only_after and not self._is_new_fiscal_period(fy, fq, only_after[0], only_after[1]):
                continue

            def gv(keys: list[str], col=col) -> Any:
                for k in keys:
                    if k in df.index:
                        v = df.loc[k, col]
                        if pd.isna(v):
                            continue
                        return v
                return None

            fv = {
                'cash_from_operating_activities': self._safe_decimal(pd.to_numeric(gv(['Operating Cash Flow', 'Total Cash From Operating Activities']), errors='coerce')),
                'net_income': self._safe_decimal(pd.to_numeric(gv(['Net Income', 'NetIncome']), errors='coerce')),
                'depreciation_amortization': self._safe_decimal(pd.to_numeric(gv(['Depreciation & Amortization', 'Depreciation']), errors='coerce')),
                'capital_expenditures': self._safe_decimal(pd.to_numeric(gv(['Capital Expenditure', 'Capital Expenditures']), errors='coerce')),
                'cash_from_investing_activities': self._safe_decimal(pd.to_numeric(gv(['Total Cash From Investing Activities']), errors='coerce')),
                'cash_from_financing_activities': self._safe_decimal(pd.to_numeric(gv(['Total Cash From Financing Activities']), errors='coerce')),
                'dividends_paid': self._safe_decimal(pd.to_numeric(gv(['Cash Dividends Paid', 'Dividends Paid']), errors='coerce')),
                'change_in_working_capital': self._safe_decimal(pd.to_numeric(gv(['Change In Working Capital']), errors='coerce')),
                'deferred_taxes': self._safe_decimal(pd.to_numeric(gv(['Deferred Income Tax', 'DeferredTax']), errors='coerce')),
                'stock_based_compensation': self._safe_decimal(pd.to_numeric(gv(['Stock Based Compensation']), errors='coerce')),
                'acquisitions': self._safe_decimal(pd.to_numeric(gv(['Purchase of Business']), errors='coerce')),
                'asset_sales': self._safe_decimal(pd.to_numeric(gv(['Sale Of Property Plant Equipment']), errors='coerce')),
                'investment_purchases': self._safe_decimal(pd.to_numeric(gv(['Investments', 'Purchase Of Investments']), errors='coerce')),
                'debt_issued': self._safe_decimal(pd.to_numeric(gv(['Issuance Of Debt', 'Issuance Of Long Term Debt']), errors='coerce')),
                'debt_repayment': self._safe_decimal(pd.to_numeric(gv(['Repayment Of Debt', 'Repayment Of Long Term Debt']), errors='coerce')),
                'share_repurchases': self._safe_decimal(pd.to_numeric(gv(['Sale Purchase Of Stock', 'Repurchase Of Capital Stock']), errors='coerce')),
                'share_issuance': self._safe_decimal(pd.to_numeric(gv(['Sale Of Stock', 'Issuance Of Capital Stock']), errors='coerce')),
            }
            row = CashFlowRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=col.date(),
                currency="USD",
                last_validated_at=None,
                confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                data_source=source,
                validation_notes=None,
                field_sources=self._build_field_sources(fv, source),
                **fv,
            )
            # Validate before adding to results; skip junk rows (no gaps channel here)
            validation_result = FinancialDataValidator.validate_cash_flow(
                row=row.model_dump(),
                symbol=symbol
            )
            log_validation_result(validation_result)
            if not validation_result.has_critical_issues():
                rows.append(row)
        return rows

    def _build_earnings_rows_from_yf(self, company_id: int, yf_earn: list[dict[str, Any]] | None) -> list[EarningsRow]:
        rows: list[EarningsRow] = []
        if not yf_earn:
            return rows

        for e in yf_earn:
            try:
                # Compute revenue surprises if both present
                rev_rep = self._safe_decimal(e.get('revenue_reported'))
                rev_est = self._safe_decimal(e.get('revenue_estimate'))
                rev_surprise_amt = None
                rev_surprise_pct = None
                if rev_rep is not None and rev_est is not None:
                    try:
                        rev_surprise_amt = Decimal(str(rev_rep)) - Decimal(str(rev_est))
                        if Decimal(str(rev_est)) != 0:
                            rev_surprise_pct = (rev_surprise_amt / Decimal(str(rev_est))) * Decimal('100')
                    except InvalidOperation:
                        rev_surprise_amt = None
                        rev_surprise_pct = None

                rows.append(EarningsRow(
                    company_id=company_id,
                    fiscal_year=e.get('fiscal_year'),
                    fiscal_quarter=e.get('fiscal_quarter'),
                    period_end_date=e.get('report_date') or e.get('announcement_date'),
                    announcement_date=e.get('announcement_date'),

                    eps_reported_basic=None,
                    eps_reported_diluted=self._safe_decimal(e.get('eps_reported')),
                    eps_estimate=self._safe_decimal(e.get('eps_estimate')),
                    eps_surprise_amount=self._safe_decimal(e.get('eps_surprise_amount')),
                    eps_surprise_percent=self._safe_decimal(e.get('eps_surprise_percent')),

                    revenue_reported=rev_rep,
                    revenue_estimate=rev_est,
                    revenue_surprise_amount=rev_surprise_amt,
                    revenue_surprise_percent=rev_surprise_pct,

                    shares_outstanding_basic=None,
                    shares_outstanding_diluted=None,

                    currency="USD",
                    confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                    data_source="yfinance",
                    last_validated_at=None,
                    validation_notes=None,
                ))
            except Exception:
                continue
        return rows

    # ---------------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------------
    def _extract_result(self, result, default):
        if isinstance(result, Exception):
            logger.debug(f"Fetch failed: {result!s}")
            return default
        return result if result else default

    @staticmethod
    def _extract_pair_result(result, default_rows, default_gaps=None):
        if default_gaps is None:
            default_gaps = set()
        if isinstance(result, Exception):
            return default_rows, default_gaps
        if result:
            return result
        return default_rows, default_gaps

    async def _timeout_fetch(self, func, description: str):
        """
        Run callable in a thread with timeout; ensure callable is executed INSIDE the timeout.
        """
        try:
            if not callable(func):
                raise TypeError(f"_timeout_fetch expected callable for {description}, got {type(func)}")
            return await asyncio.wait_for(
                asyncio.to_thread(func),
                timeout=self.settings.DEFEAT_BETA_TIMEOUT_SECONDS
            )
        except TimeoutError as e:
            logger.warning(f"Timeout fetching {description}")
            symbol = description.split(" for ")[-1] if " for " in description else "unknown"
            raise FinancialsFetchTimeoutError(
                symbol, description, self.settings.DEFEAT_BETA_TIMEOUT_SECONDS
            ) from e

    def _filter_to_new_data(
        self,
        fin: CompleteFundamentals,
        last_year: int,
        last_quarter: int | None
    ) -> CompleteFundamentals:
        def keep(fy: int | None, fq: int | None) -> bool:
            return self._is_new_fiscal_period(fy, fq, last_year, last_quarter)

        fin.income_statements.rows = [r for r in fin.income_statements.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        fin.balance_sheets.rows = [r for r in fin.balance_sheets.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        fin.cash_flows.rows = [r for r in fin.cash_flows.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        fin.earnings.rows = [r for r in fin.earnings.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        # dividends: keep all; optional date filtering can be added if needed
        return fin

    def _filter_by_min_year(
        self,
        fin: CompleteFundamentals,
        min_year: int,
    ) -> CompleteFundamentals:
        def keep(fy: int | None) -> bool:
            return fy is None or fy >= min_year

        fin.income_statements.rows = [r for r in fin.income_statements.rows if keep(r.fiscal_year)]
        fin.balance_sheets.rows = [r for r in fin.balance_sheets.rows if keep(r.fiscal_year)]
        fin.cash_flows.rows = [r for r in fin.cash_flows.rows if keep(r.fiscal_year)]
        fin.earnings.rows = [r for r in fin.earnings.rows if keep(r.fiscal_year)]
        return fin

    def _is_new_fiscal_period(
        self,
        fy: int | None,
        fq: int | None,
        last_year: int | None,
        last_quarter: int | None
    ) -> bool:
        if fy is None:
            return False
        if last_year is None:
            return True
        if fy > last_year:
            return True
        if fy < last_year:
            return False
        # same year
        if fq is None:
            return False
        if last_quarter is None:
            return True
        return fq > last_quarter

    def _safe_decimal(self, val: Any) -> Decimal | None:
        if val is None:
            return None
        # Handle NaN floats
        if isinstance(val, float) and val != val:
            return None
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            return None

    def _safe_int_field(self, val: Any) -> int | None:
        """Convert a raw numeric value (float/Decimal/str) to int for bigint columns."""
        if val is None:
            return None
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _build_field_sources(field_values: dict[str, Any], source: str) -> dict[str, list[str]]:
        """Build field_sources metadata: maps non-null field names to their provider source."""
        return {k: [source] for k, v in field_values.items() if v is not None}

    @staticmethod
    def _extract_latest_metric(df, column: str):
        """Extract latest value from a time-series DataFrame."""
        if df is None or (hasattr(df, 'empty') and df.empty):
            return None
        try:
            row = df.iloc[-1] if hasattr(df, 'iloc') else df
            return row.get(column) if hasattr(row, 'get') else None
        except (IndexError, KeyError, TypeError):
            return None

    def _log_debug_once(self, msg: str):
        logger.debug(msg)

    def _debug_alias_coverage(self, df: pd.DataFrame, alias_map: dict[str, list[str]], col: str):
        out = {}
        idx = set(df.index)
        for canonical, aliases in alias_map.items():
            matched, alias_used, value = False, None, None
            for a in aliases or []:
                k = self._normalize_alias_key(a)
                if k in idx:
                    v = df.at[k, col]
                    if pd.isna(v):
                        continue
                    matched, alias_used, value = True, a, v
                    break
            out[canonical] = {'matched': matched, 'alias_used': alias_used, 'value': value}
        return out

    # ---------------------------------------------------------------------
    # Fallback chain helper — Stockdex → Edgar → YFinance
    # ---------------------------------------------------------------------
    async def _fetch_statement_df_with_fallback(
        self,
        symbol: str,
        method_name: str,
        exchange: str | None = None,
        security_type: str | None = None,
    ) -> tuple[pd.DataFrame, str]:
        # 1. Try Stockdex/Macrotrends
        if self.stockdex_provider:
            if self._provider_applicable("stockdex", exchange, security_type):
                if not self.stockdex_provider.is_rate_limited():
                    try:
                        df = await asyncio.to_thread(
                            getattr(self.stockdex_provider, method_name), symbol
                        )
                        if df is not None and not df.empty:
                            logger.debug(
                                "[STOCKDEX][%s] %s succeeded (%d cols)",
                                symbol, method_name, len(df.columns),
                            )
                            return (df, "stockdex")
                        logger.debug("[STOCKDEX][%s] %s returned empty", symbol, method_name)
                    except Exception as e:
                        logger.debug("[STOCKDEX][%s] %s failed: %s", symbol, method_name, e)
                else:
                    logger.debug("[SKIP] stockdex rate-limited for %s, skipping", symbol)
            else:
                logger.debug("[SKIP] stockdex not applicable for %s (exchange=%s, type=%s)", symbol, exchange, security_type)

        # 2. Try Edgar
        if self.edgar_provider:
            if self._provider_applicable("edgar", exchange, security_type):
                try:
                    df = await asyncio.to_thread(
                        getattr(self.edgar_provider, method_name), symbol
                    )
                    if df is not None and not df.empty:
                        logger.debug(
                            "[EDGAR][%s] %s succeeded (%d cols)",
                            symbol, method_name, len(df.columns),
                        )
                        return (df, "edgar")
                    logger.debug("[EDGAR][%s] %s returned empty", symbol, method_name)
                except Exception as e:
                    logger.debug("[EDGAR][%s] %s failed: %s", symbol, method_name, e)
            else:
                logger.debug("[SKIP] edgar not applicable for %s (exchange=%s, type=%s)", symbol, exchange, security_type)

        # 3. Fall through to YFinance
        if self.yfinance_provider:
            try:
                df = await asyncio.to_thread(
                    getattr(self.yfinance_provider, method_name), symbol
                )
                return (df if df is not None else pd.DataFrame(), "yfinance")
            except Exception as e:
                logger.debug("[YF][%s] %s failed: %s", symbol, method_name, e)

        return (pd.DataFrame(), "yfinance")
