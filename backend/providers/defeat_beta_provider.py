
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple, List, Dict, Any

import pandas as pd
import html
import re

# Defeat Beta SDK
from defeatbeta_api.data.ticker import Ticker

# Domain exceptions and models
from domain.exceptions import (
    DefeatBetaException,
    FinancialsFetchTimeoutError,
    NoDataError,
    MaxRetriesExceededError,
)
from domain.models import (
    CompleteFundamentals,
    IncomeStatementRow,
    IncomeStatementRows,
    BalanceSheetRow,
    BalanceSheetRows,
    CashFlowRow,
    CashFlowRows,
    EarningsRow,
    EarningsRows,
    DividendRow,
    DividendRows,
)

from providers.base import StockDataProvider

logger = logging.getLogger(__name__)


class DefeatBetaProvider(StockDataProvider):
    """
    Defeat Beta provider with:
      - Correct method invocation for DBeta (e.g., ticker.quarterly_income_statement())
      - Robust normalization for Defeat Beta .df() shape (Breakdown col, drop TTM, '*' -> NaN)
      - Expanded alias-based mapping for row labels to DB schema fields
      - Timeout wrapper invoking callables INSIDE the timeout
      - yfinance fallback + gap-fill (IS/BS/CF/Earnings/Dividends, next_earnings_date)
      - Coverage-aware filtering for fallback ("only_after" (year, quarter))
    """

    # ---------------------------------------------------------------------
    # Expanded aliases tuned to Defeat Beta labels you shared
    # ---------------------------------------------------------------------

    # Income Statement aliases
    DB_INCOME_ALIASES = {
        # Core P&L
        'revenue': ['Total Revenue', 'Operating Revenue'],
        'cost_of_goods_sold': ['Cost of Revenue', 'Reconciled Cost of Revenue'],
        'gross_profit': ['Gross Profit'],

        # Opex + components
        'operating_expenses': ['Operating Expense', 'Total Operating Expenses'],
        'rd_expenses': ['Research & Development'],
        'sga_expenses': ['Selling General and Administrative'],

        # Operating result
        'operating_income': ['Operating Income', 'Total Operating Income as Reported'],

        # Non-operating and interest
        'non_operating_income_expense': ['Other Income Expense', 'Other Non Operating Income Expenses'],
        'interest_expense': ['Non-Operating Interest Expense', 'Interest Expense'],

        # Taxes / before tax
        'pretax_income': ['Pretax Income', 'Income Before Tax', 'Earnings Before Tax'],
        'tax_expense': ['Tax Provision', 'Income Tax Expense'],

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
        'preferred_dividends': ['Otherunder Preferred Stock Dividend'],
        'net_income_to_common': ['Net Income Common Stockholders'],

        # EBIT/EBITDA
        'ebit': ['EBIT'],
        'ebitda': ['EBITDA', 'Normalized EBITDA'],

        # Optional metrics present in some outputs
        'normalized_income': ['Normalized Income'],
        'total_expenses': ['Total Expenses'],
        'rent_expense': ['Rent Expense Supplemental'],
    }

    # Balance Sheet aliases
    DB_BALANCE_ALIASES = {
        # Assets
        'total_assets': ['Total Assets'],
        'current_assets': ['Total Current Assets'],
        'cash_and_cash_equivalents': ['Cash And Cash Equivalents'],
        'accounts_receivable': ['Accounts receivable', 'Accounts Receivable'],
        'inventory': ['Inventory'],
        'property_plant_equipment_net': ['Net PPE', 'Property Plant And Equipment Net', 'Property, Plant & Equipment Net'],
        'intangible_assets': ['Other Intangible Assets', 'Intangible Assets'],
        'goodwill': ['Goodwill'],

        # Liabilities
        'total_liabilities': ['Total Liabilities'],
        'current_liabilities': ['Total Current Liabilities'],
        'accounts_payable': ['Accounts Payable', 'Payables'],
        'short_term_debt': ['Current Debt', 'Current Debt And Capital Lease Obligation'],
        'long_term_debt': ['Long Term Debt'],
        'total_debt': ['Total Debt'],

        # Equity
        'shareholders_equity': ["Stockholders' Equity", 'Common Stock Equity', 'Total Stockholder Equity'],
        'retained_earnings': ['Retained Earnings'],
        'common_stock': ['Common Stock', 'Capital Stock'],

        # Extended
        'long_term_investments': ['Long Term Investments'],
        'other_non_current_assets': ['Other Non Current Assets'],
        'other_current_liabilities': ['Other Current Liabilities'],
        'minority_interest': ['Minority Interest'],
        'total_liabilities_and_equity': ['Total Liabilities & Stockholders Equity', 'Total Assets'],  # sanity equality
    }

    # Cash Flow aliases
    DB_CASHFLOW_ALIASES = {
        # Operating
        'cash_from_operating_activities': ['Operating Cash Flow', 'Cash Flow from Continuing Operating Activities'],
        'net_income': ['Net Income from Continuing Operations'],
        'depreciation_amortization': ['Depreciation & Amortization', 'Depreciation Amortization Depletion', 'Depreciation'],
        'change_in_working_capital': ['Change In Working Capital'],
        'deferred_taxes': ['Deferred Income Tax', 'Deferred Tax'],
        'stock_based_compensation': ['Stock Based Compensation'],

        # Investing
        'capital_expenditures': ['Capital Expenditure (CapEx)', 'Capital Expenditure Reported（CapEx）'],
        'acquisitions': ['Purchase of Business'],
        'asset_sales': ['Sale of PPE', 'Sale of Property Plant Equipment'],
        'investment_purchases': ['Purchase of Investment', 'Investments'],
        'cash_from_investing_activities': ['Cash Flow from Continuing Investing Activities'],

        # Financing
        'debt_issued': ['Long Term Debt Issuance', 'Issuance of Debt'],
        'debt_repayment': ['Long Term Debt Payments', 'Repayment of Debt'],
        'dividends_paid': ['Cash Dividends Paid', 'Dividends Paid'],
        'share_repurchases': ['Sale Purchase Of Stock', 'Repurchase Of Capital Stock'],
        'share_issuance': ['Issuance of Capital Stock', 'Common Stock Issuance'],

        # Supplemental/rollups exist, not persisted here (we only map schema fields)
    }

    def __init__(self, yfinance_provider: Optional["YFinanceProvider"] = None):
        from config import settings
        self.settings = settings
        self.yfinance_provider = yfinance_provider
        logger.info("DefeatBetaProvider initialized")

    def get_ticker_info(self, ticker_symbol: str) -> Optional['TickerInfo']:
        if self.yfinance_provider:
            try:
                return self.yfinance_provider.get_ticker_info(ticker_symbol)
            except Exception as e:
                logger.warning(f"YFinance get_ticker_info failed for {ticker_symbol}: {str(e)}")
        return None

    def get_stock_details(self, ticker_symbol: str) -> Optional['StockDetails']:
        if self.yfinance_provider:
            try:
                return self.yfinance_provider.get_stock_details(ticker_symbol)
            except Exception as e:
                logger.warning(f"YFinance get_stock_details failed for {ticker_symbol}: {str(e)}")
        return None
        
    # ---------------------------------------------------------------------
    # Public entry: retry + fallback + gap-fill + coverage-aware filter
    # ---------------------------------------------------------------------
    async def get_all_financials_optimized(
        self,
        symbol: str,
        company_id: int,
        last_refreshed_fiscal_year: Optional[int] = None,
        last_refreshed_fiscal_quarter: Optional[int] = None,
        force_full_history: bool = False,
    ) -> CompleteFundamentals:
        logger.info(f"Starting financials fetch for {symbol} (company_id={company_id})")
        last_error: Optional[Exception] = None

        for attempt in range(self.settings.RETRY_MAX_ATTEMPTS):
            try:
                fin = await self._fetch_all_financials_internal(symbol, company_id)

                # incremental filter if not first load
                if not force_full_history and last_refreshed_fiscal_year is not None:
                    fin = self._filter_to_new_data(fin, last_refreshed_fiscal_year, last_refreshed_fiscal_quarter)

                # gap-fill missing statements from yfinance (if enabled)
                if self.settings.ENABLE_YFINANCE_FALLBACK and self.yfinance_provider:
                    only_after = None if force_full_history else (last_refreshed_fiscal_year, last_refreshed_fiscal_quarter)
                    fin = await self._fill_gaps_with_yfinance(fin, only_after=only_after)

                logger.info(f"✅ Fetched {symbol}: {fin.total_rows_fetched} total rows")
                return fin

            except (DefeatBetaException, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < self.settings.RETRY_MAX_ATTEMPTS - 1:
                    backoff = self.settings.RETRY_BACKOFF_SECONDS[attempt]
                    logger.warning(
                        f"Attempt {attempt + 1}/{self.settings.RETRY_MAX_ATTEMPTS} failed for {symbol}: "
                        f"retrying in {backoff}s. Error: {str(e)}"
                    )
                    await asyncio.sleep(backoff)

        # total failure → fallback to yfinance
        if self.settings.ENABLE_YFINANCE_FALLBACK and self.yfinance_provider:
            logger.warning(f"Defeat-beta failed for {symbol}, attempting yfinance fallback")
            only_after = None if force_full_history else (last_refreshed_fiscal_year, last_refreshed_fiscal_quarter)
            return await self._fallback_to_yfinance(symbol, company_id, only_after=only_after)

        raise MaxRetriesExceededError(
            company_id=company_id,
            symbol=symbol,
            attempts=self.settings.RETRY_MAX_ATTEMPTS,
            last_error=last_error,
        )

    # ---------------------------------------------------------------------
    # Primary fetch (Defeat Beta)
    # ---------------------------------------------------------------------
    async def _fetch_all_financials_internal(self, symbol: str, company_id: int) -> CompleteFundamentals:
        try:
            ticker = Ticker(symbol)
            logger.debug(f"Created Ticker object for {symbol}")

            tasks = [
                self._fetch_income_statements(ticker, symbol, company_id),
                self._fetch_balance_sheets(ticker, symbol, company_id),
                self._fetch_cash_flows(ticker, symbol, company_id),
                self._fetch_earnings(ticker, symbol, company_id),
                self._fetch_dividends(ticker, symbol, company_id),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            income_rows = self._extract_result(results[0], IncomeStatementRows(rows=[]))
            balance_rows = self._extract_result(results[1], BalanceSheetRows(rows=[]))
            cash_rows = self._extract_result(results[2], CashFlowRows(rows=[]))
            earnings_rows = self._extract_result(results[3], EarningsRows(rows=[]))
            dividend_rows = self._extract_result(results[4], DividendRows(rows=[]))

            if not any([income_rows.rows, balance_rows.rows, cash_rows.rows]):
                raise NoDataError(symbol, ['income_statements', 'balance_sheets', 'cash_flows'])

            # next earnings date
            next_earnings = await self._fetch_next_earnings_date(ticker, symbol)

            fin = CompleteFundamentals(
                company_id=company_id,
                symbol=symbol,
                income_statements=income_rows,
                balance_sheets=balance_rows,
                cash_flows=cash_rows,
                earnings=earnings_rows,
                dividends=dividend_rows,
                next_earnings_date=next_earnings,
                fetched_at=datetime.utcnow(),
            )
            return fin

        except NoDataError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch financials for {symbol}: {str(e)}", exc_info=True)
            raise DefeatBetaException(
                message=f"Failed to fetch financials for {symbol}: {str(e)}",
                error_code="DEFEAT_BETA_FETCH_ERROR",
                details={"symbol": symbol, "original_error": str(e)},
            )

    async def _fetch_income_statements(self, ticker: Ticker, symbol: str, company_id: int) -> IncomeStatementRows:
        try:
            rows: List[IncomeStatementRow] = []

            q_obj = await self._timeout_fetch(lambda: ticker.quarterly_income_statement(), f"quarterly_income_statement for {symbol}")
            if q_obj is not None:
                q_df = q_obj.df() if hasattr(q_obj, 'df') else q_obj
                rows.extend(self._parse_income_statement(q_df, company_id, is_quarterly=True, symbol=symbol))

            a_obj = await self._timeout_fetch(lambda: ticker.annual_income_statement(), f"annual_income_statement for {symbol}")
            if a_obj is not None:
                a_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                rows.extend(self._parse_income_statement(a_df, company_id, is_quarterly=False, symbol=symbol))

            return IncomeStatementRows(rows=rows)
        except Exception as e:
            logger.warning(f"Income statement fetch failed for {symbol}: {str(e)}")
            return IncomeStatementRows(rows=[])

    async def _fetch_balance_sheets(self, ticker: Ticker, symbol: str, company_id: int) -> BalanceSheetRows:
        try:
            rows: List[BalanceSheetRow] = []

            q_obj = await self._timeout_fetch(lambda: ticker.quarterly_balance_sheet(), f"quarterly_balance_sheet for {symbol}")
            if q_obj is not None:
                q_df = q_obj.df() if hasattr(q_obj, 'df') else q_obj
                rows.extend(self._parse_balance_sheet(q_df, company_id, is_quarterly=True, symbol=symbol))

            a_obj = await self._timeout_fetch(lambda: ticker.annual_balance_sheet(), f"annual_balance_sheet for {symbol}")
            if a_obj is not None:
                a_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                rows.extend(self._parse_balance_sheet(a_df, company_id, is_quarterly=False, symbol=symbol))

            return BalanceSheetRows(rows=rows)
        except Exception as e:
            logger.warning(f"Balance sheet fetch failed for {symbol}: {str(e)}")
            return BalanceSheetRows(rows=[])

    async def _fetch_cash_flows(self, ticker: Ticker, symbol: str, company_id: int) -> CashFlowRows:
        try:
            rows: List[CashFlowRow] = []

            q_obj = await self._timeout_fetch(lambda: ticker.quarterly_cash_flow(), f"quarterly_cash_flow for {symbol}")
            if q_obj is not None:
                q_df = q_obj.df() if hasattr(q_obj, 'df') else q_obj
                rows.extend(self._parse_cash_flow(q_df, company_id, is_quarterly=True, symbol=symbol))

            a_obj = await self._timeout_fetch(lambda: ticker.annual_cash_flow(), f"annual_cash_flow for {symbol}")
            if a_obj is not None:
                a_df = a_obj.df() if hasattr(a_obj, 'df') else a_obj
                rows.extend(self._parse_cash_flow(a_df, company_id, is_quarterly=False, symbol=symbol))

            return CashFlowRows(rows=rows)
        except Exception as e:
            logger.warning(f"Cash flow fetch failed for {symbol}: {str(e)}")
            return CashFlowRows(rows=[])

    async def _fetch_earnings(self, ticker: Ticker, symbol: str, company_id: int) -> EarningsRows:
        """
        Uses Ticker.earnings() per the docs you shared:
        columns: symbol, eps_actual, eps_estimate, surprise_percent, quarter_name, quarter_date
        Maps to EarningsRow with eps_reported_diluted, eps_estimate, eps_surprise_amount, eps_surprise_percent.
        Revenue fields are not present here → left None. Announcement date not provided here → None.
        """
        try:
            earn_obj = await self._timeout_fetch(lambda: ticker.earnings(), f"earnings for {symbol}")
            # Normalize to DataFrame
            if isinstance(earn_obj, pd.DataFrame):
                df = earn_obj
            elif hasattr(earn_obj, 'df'):
                df = earn_obj.df()
            else:
                try:
                    df = pd.DataFrame(earn_obj)
                except Exception:
                    df = None
            if df is None or df.empty:
                return EarningsRows(rows=[])
            rows: List[EarningsRow] = []
            for _, r in df.iterrows():
                qdate = r.get('quarter_date')
                fy: Optional[int] = None
                fq: Optional[int] = None
                period_end: Optional[date] = None
                if pd.notna(qdate):
                    ts = pd.to_datetime(str(qdate), errors='coerce')
                    if not pd.isna(ts):
                        period_end = ts.date()
                        fy = int(ts.year)
                        fq = int((ts.month - 1) // 3 + 1)
                eps_actual = self._safe_decimal(r.get('eps_actual'))
                eps_estimate = self._safe_decimal(r.get('eps_estimate'))
                eps_surprise_pct = self._safe_decimal(r.get('surprise_percent'))
                eps_surprise_amt: Optional[Decimal] = None
                if eps_actual is not None and eps_estimate is not None:
                    try:
                        eps_surprise_amt = Decimal(str(eps_actual)) - Decimal(str(eps_estimate))
                    except InvalidOperation:
                        eps_surprise_amt = None
                rows.append(EarningsRow(
                    company_id=company_id,
                    fiscal_year=fy,
                    fiscal_quarter=fq,
                    period_end_date=period_end,
                    announcement_date=None,                 # not exposed by earnings()
                    eps_reported_basic=None,                # doc exposes single EPS; map to diluted
                    eps_reported_diluted=eps_actual,
                    eps_estimate=eps_estimate,
                    eps_surprise_amount=eps_surprise_amt,
                    eps_surprise_percent=eps_surprise_pct,
                    revenue_reported=None,                  # not in Ticker.earnings()
                    revenue_estimate=None,
                    revenue_surprise_amount=None,
                    revenue_surprise_percent=None,
                    shares_outstanding_basic=None,
                    shares_outstanding_diluted=None,
                    currency="USD",
                    confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                    last_validated_at=None,
                    validation_notes=None,
                ))
            return EarningsRows(rows=rows)
        except Exception as e:
            # Per your design, failures here should not break the full fetch.
            # Earnings are supplemental; we return empty and allow fallback/gap-fill elsewhere.
            self._log_debug_once(f"Earnings fetch failed for {symbol}: {e}")
            return EarningsRows(rows=[])


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
            logger.warning(f"Dividends fetch failed for {symbol}: {str(e)}")
            return DividendRows(rows=[])
    
    async def _fetch_next_earnings_date(self, ticker: Ticker, symbol: str) -> Optional[date]:
        """
        Uses Ticker.calendar() per docs; extracts 'report_date' as next earnings date (if present).
        """
        try:
            cal_obj = await self._timeout_fetch(lambda: ticker.calendar(), f"calendar for {symbol}")
            df = cal_obj.df() if hasattr(cal_obj, 'df') else cal_obj
            if df is not None and not df.empty:
                rd = df.iloc[0].get('report_date')
                if rd is not None:
                    ts = pd.to_datetime(str(rd), errors='coerce')
                    if not pd.isna(ts):
                        return ts.date()
        except Exception as e:
            self._log_debug_once(f"Failed to fetch earnings date for {symbol}: {e}")
        return None


    # ---------------------------------------------------------------------
    # Fallbacks (YFinance): full fallback and gap-fill
    # ---------------------------------------------------------------------
    async def _fallback_to_yfinance(
        self,
        symbol: str,
        company_id: int,
        only_after: Optional[Tuple[Optional[int], Optional[int]]] = None
    ) -> CompleteFundamentals:
        if not self.yfinance_provider:
            logger.warning("Fallback failed: yfinance_provider not configured")
            return CompleteFundamentals(
                company_id=company_id,
                symbol=symbol,
                income_statements=IncomeStatementRows(rows=[]),
                balance_sheets=BalanceSheetRows(rows=[]),
                cash_flows=CashFlowRows(rows=[]),
                earnings=EarningsRows(rows=[]),
                dividends=DividendRows(rows=[]),
                fetched_at=datetime.utcnow(),
            )

        fyq_filter = only_after

        # Income
        yf_q_is = await asyncio.to_thread(self.yfinance_provider.get_quarterly_income_statement_df, symbol)
        yf_a_is = await asyncio.to_thread(self.yfinance_provider.get_annual_income_statement_df, symbol)
        is_rows = self._parse_yf_income_statement(yf_q_is, company_id, True, symbol, fyq_filter) + \
                  self._parse_yf_income_statement(yf_a_is, company_id, False, symbol, fyq_filter)

        # Balance
        yf_q_bs = await asyncio.to_thread(self.yfinance_provider.get_quarterly_balance_sheet_df, symbol)
        yf_a_bs = await asyncio.to_thread(self.yfinance_provider.get_annual_balance_sheet_df, symbol)
        bs_rows = self._parse_yf_balance_sheet(yf_q_bs, company_id, True, symbol, fyq_filter) + \
                  self._parse_yf_balance_sheet(yf_a_bs, company_id, False, symbol, fyq_filter)

        # Cash Flow
        yf_q_cf = await asyncio.to_thread(self.yfinance_provider.get_quarterly_cash_flow_df, symbol)
        yf_a_cf = await asyncio.to_thread(self.yfinance_provider.get_annual_cash_flow_df, symbol)
        cf_rows = self._parse_yf_cash_flow(yf_q_cf, company_id, True, symbol, fyq_filter) + \
                  self._parse_yf_cash_flow(yf_a_cf, company_id, False, symbol, fyq_filter)

        # Earnings (best-effort)
        yf_earn = await asyncio.to_thread(self.yfinance_provider.get_earnings_data, symbol)
        earn_rows = self._build_earnings_rows_from_yf(company_id, yf_earn)

        # Dividends (best-effort)
        yf_div = await asyncio.to_thread(self.yfinance_provider.get_dividends_df, symbol)
        div_rows = self._parse_dividends(yf_div, company_id, symbol, provider='yfinance') if (yf_div is not None and not yf_div.empty) else []

        # Next earnings date via YF details
        next_earnings_date = None
        try:
            details = await asyncio.to_thread(self.yfinance_provider.get_stock_details, symbol)
            if details and details.next_earnings_date:
                next_earnings_date = details.next_earnings_date
        except Exception:
            pass

        return CompleteFundamentals(
            company_id=company_id,
            symbol=symbol,
            income_statements=IncomeStatementRows(rows=is_rows),
            balance_sheets=BalanceSheetRows(rows=bs_rows),
            cash_flows=CashFlowRows(rows=cf_rows),
            earnings=EarningsRows(rows=earn_rows),
            dividends=DividendRows(rows=div_rows),
            next_earnings_date=next_earnings_date,
            fetched_at=datetime.utcnow(),
        )

    async def _fill_gaps_with_yfinance(
        self,
        fin: CompleteFundamentals,
        only_after: Optional[Tuple[Optional[int], Optional[int]]] = None
    ) -> CompleteFundamentals:
        if not self.yfinance_provider:
            return fin

        symbol = fin.symbol
        company_id = fin.company_id
        fyq_filter = only_after

        need_is = not fin.income_statements.rows
        need_bs = not fin.balance_sheets.rows
        need_cf = not fin.cash_flows.rows
        need_earn = not fin.earnings.rows
        need_div = not fin.dividends.rows

        if need_is:
            yf_q_is = await asyncio.to_thread(self.yfinance_provider.get_quarterly_income_statement_df, symbol)
            yf_a_is = await asyncio.to_thread(self.yfinance_provider.get_annual_income_statement_df, symbol)
            fin.income_statements = IncomeStatementRows(
                rows=self._parse_yf_income_statement(yf_q_is, company_id, True, symbol, fyq_filter) +
                     self._parse_yf_income_statement(yf_a_is, company_id, False, symbol, fyq_filter)
            )

        if need_bs:
            yf_q_bs = await asyncio.to_thread(self.yfinance_provider.get_quarterly_balance_sheet_df, symbol)
            yf_a_bs = await asyncio.to_thread(self.yfinance_provider.get_annual_balance_sheet_df, symbol)
            fin.balance_sheets = BalanceSheetRows(
                rows=self._parse_yf_balance_sheet(yf_q_bs, company_id, True, symbol, fyq_filter) +
                     self._parse_yf_balance_sheet(yf_a_bs, company_id, False, symbol, fyq_filter)
            )

        if need_cf:
            yf_q_cf = await asyncio.to_thread(self.yfinance_provider.get_quarterly_cash_flow_df, symbol)
            yf_a_cf = await asyncio.to_thread(self.yfinance_provider.get_annual_cash_flow_df, symbol)
            fin.cash_flows = CashFlowRows(
                rows=self._parse_yf_cash_flow(yf_q_cf, company_id, True, symbol, fyq_filter) +
                     self._parse_yf_cash_flow(yf_a_cf, company_id, False, symbol, fyq_filter)
            )

        if need_earn:
            yf_earn = await asyncio.to_thread(self.yfinance_provider.get_earnings_data, symbol)
            fin.earnings = EarningsRows(rows=self._build_earnings_rows_from_yf(company_id, yf_earn))

        if need_div:
            yf_div = await asyncio.to_thread(self.yfinance_provider.get_dividends_df, symbol)
            if yf_div is not None and not yf_div.empty:
                fin.dividends = DividendRows(rows=self._parse_dividends(yf_div, company_id, symbol, provider='yfinance'))

        if fin.next_earnings_date is None:
            try:
                details = await asyncio.to_thread(self.yfinance_provider.get_stock_details, symbol)
                if details and details.next_earnings_date:
                    fin.next_earnings_date = details.next_earnings_date
            except Exception:
                pass

        return fin

    # ---------------------------------------------------------------------
    # Normalization + Parsers (Defeat Beta)
    # ---------------------------------------------------------------------
    def _clean_breakdown_label(self, s: str) -> str:
        if s is None:
            return ""
        s = html.unescape(str(s)).replace("&amp;", "&").strip()
        s = re.sub(r'^[+\s]+', '', s)
        s = re.sub(r'\s+', ' ', s)
        return s

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
        col_to_dt: Dict[str, pd.Timestamp] = {}
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
        for c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

        df._defeatbeta_col_dates = col_to_dt  # attach mapping
        return df

    def _iter_defeatbeta_periods(self, df: pd.DataFrame, is_quarterly: bool):
        if not hasattr(df, '_defeatbeta_col_dates'):
            col_to_dt = {c: pd.to_datetime(str(c), errors='coerce') for c in df.columns}
        else:
            col_to_dt = df._defeatbeta_col_dates  # type: ignore[attr-defined]

        for c, ts in col_to_dt.items():
            if pd.isna(ts):
                continue
            fy = int(ts.year)
            fq = int((ts.month - 1) // 3 + 1) if is_quarterly else None
            yield c, ts.date(), fy, fq

    def _db_val(self, df: pd.DataFrame, aliases: List[str], col: str):
        for key in aliases:
            if key in df.index:
                v = df.at[key, col]
                if pd.isna(v):
                    continue
                return v
        return None

    # ---- Income Statement parser (DBeta) ----
    def _parse_income_statement(self, raw_df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str) -> List[IncomeStatementRow]:
        rows: List[IncomeStatementRow] = []
        df = self._normalize_defeatbeta_df(raw_df)
        if df.empty:
            return rows

        a = self.DB_INCOME_ALIASES
        for col, period_end, fy, fq in self._iter_defeatbeta_periods(df, is_quarterly):
            rows.append(IncomeStatementRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=period_end,

                revenue=self._safe_decimal(self._db_val(df, a['revenue'], col)),
                cost_of_goods_sold=self._safe_decimal(self._db_val(df, a['cost_of_goods_sold'], col)),
                gross_profit=self._safe_decimal(self._db_val(df, a['gross_profit'], col)),
                operating_expenses=self._safe_decimal(self._db_val(df, a['operating_expenses'], col)),
                rd_expenses=self._safe_decimal(self._db_val(df, a['rd_expenses'], col)),
                sga_expenses=self._safe_decimal(self._db_val(df, a['sga_expenses'], col)),
                operating_income=self._safe_decimal(self._db_val(df, a['operating_income'], col)),
                interest_expense=self._safe_decimal(self._db_val(df, a['interest_expense'], col)),
                tax_expense=self._safe_decimal(self._db_val(df, a['tax_expense'], col)),
                net_income=self._safe_decimal(self._db_val(df, a['net_income'], col)),
                ebitda=self._safe_decimal(self._db_val(df, a['ebitda'], col)),
                currency="USD",

                non_operating_income_expense=self._safe_decimal(self._db_val(df, a['non_operating_income_expense'], col)),
                pretax_income=self._safe_decimal(self._db_val(df, a['pretax_income'], col)),
                equity_in_earnings=self._safe_decimal(self._db_val(df, a.get('equity_in_earnings', []), col)),
                minority_interest=self._safe_decimal(self._db_val(df, a.get('minority_interest', []), col)),
                income_from_continuing_operations=self._safe_decimal(self._db_val(df, a.get('income_from_continuing_operations', []), col)),
                discontinued_operations=self._safe_decimal(self._db_val(df, a.get('discontinued_operations', []), col)),
                net_income_to_common=self._safe_decimal(self._db_val(df, a.get('net_income_to_common', []), col)),
                preferred_dividends=self._safe_decimal(self._db_val(df, a.get('preferred_dividends', []), col)),
                ebit=self._safe_decimal(self._db_val(df, a.get('ebit', []), col)),
                last_validated_at=None,

                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    # ---- Balance Sheet parser (DBeta) ----
    def _parse_balance_sheet(self, raw_df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str) -> List[BalanceSheetRow]:
        rows: List[BalanceSheetRow] = []
        df = self._normalize_defeatbeta_df(raw_df)
        if df.empty:
            return rows

        a = self.DB_BALANCE_ALIASES
        for col, period_end, fy, fq in self._iter_defeatbeta_periods(df, is_quarterly):
            rows.append(BalanceSheetRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=period_end,

                total_assets=self._safe_decimal(self._db_val(df, a['total_assets'], col)),
                current_assets=self._safe_decimal(self._db_val(df, a['current_assets'], col)),
                cash_and_cash_equivalents=self._safe_decimal(self._db_val(df, a['cash_and_cash_equivalents'], col)),
                accounts_receivable=self._safe_decimal(self._db_val(df, a['accounts_receivable'], col)),
                inventory=self._safe_decimal(self._db_val(df, a['inventory'], col)),
                property_plant_equipment_net=self._safe_decimal(self._db_val(df, a['property_plant_equipment_net'], col)),
                intangible_assets=self._safe_decimal(self._db_val(df, a['intangible_assets'], col)),
                goodwill=self._safe_decimal(self._db_val(df, a['goodwill'], col)),

                total_liabilities=self._safe_decimal(self._db_val(df, a['total_liabilities'], col)),
                current_liabilities=self._safe_decimal(self._db_val(df, a['current_liabilities'], col)),
                accounts_payable=self._safe_decimal(self._db_val(df, a['accounts_payable'], col)),
                short_term_debt=self._safe_decimal(self._db_val(df, a['short_term_debt'], col)),
                long_term_debt=self._safe_decimal(self._db_val(df, a['long_term_debt'], col)),
                total_debt=self._safe_decimal(self._db_val(df, a['total_debt'], col)),

                shareholders_equity=self._safe_decimal(self._db_val(df, a['shareholders_equity'], col)),
                retained_earnings=self._safe_decimal(self._db_val(df, a['retained_earnings'], col)),
                common_stock=None,  # DBeta often doesn't provide; keep None unless found elsewhere
                currency="USD",

                long_term_investments=self._safe_decimal(self._db_val(df, a.get('long_term_investments', []), col)),
                other_non_current_assets=self._safe_decimal(self._db_val(df, a.get('other_non_current_assets', []), col)),
                other_current_liabilities=self._safe_decimal(self._db_val(df, a.get('other_current_liabilities', []), col)),
                minority_interest=self._safe_decimal(self._db_val(df, a.get('minority_interest', []), col)),
                total_liabilities_and_equity=self._safe_decimal(self._db_val(df, a.get('total_liabilities_and_equity', []), col)),
                last_validated_at=None,

                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    # ---- Cash Flow parser (DBeta) ----
    def _parse_cash_flow(self, raw_df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str) -> List[CashFlowRow]:
        rows: List[CashFlowRow] = []
        df = self._normalize_defeatbeta_df(raw_df)
        if df.empty:
            return rows

        a = self.DB_CASHFLOW_ALIASES
        for col, period_end, fy, fq in self._iter_defeatbeta_periods(df, is_quarterly):
            rows.append(CashFlowRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=period_end,

                cash_from_operating_activities=self._safe_decimal(self._db_val(df, a['cash_from_operating_activities'], col)),
                net_income=self._safe_decimal(self._db_val(df, a['net_income'], col)),
                depreciation_amortization=self._safe_decimal(self._db_val(df, a['depreciation_amortization'], col)),
                capital_expenditures=self._safe_decimal(self._db_val(df, a['capital_expenditures'], col)),
                cash_from_investing_activities=self._safe_decimal(self._db_val(df, a['cash_from_investing_activities'], col)),
                cash_from_financing_activities=self._safe_decimal(self._db_val(df, a['cash_from_financing_activities'], col)),
                dividends_paid=self._safe_decimal(self._db_val(df, a['dividends_paid'], col)),
                currency="USD",

                change_in_working_capital=self._safe_decimal(self._db_val(df, a.get('change_in_working_capital', []), col)),
                deferred_taxes=self._safe_decimal(self._db_val(df, a.get('deferred_taxes', []), col)),
                stock_based_compensation=self._safe_decimal(self._db_val(df, a.get('stock_based_compensation', []), col)),
                acquisitions=self._safe_decimal(self._db_val(df, a.get('acquisitions', []), col)),
                asset_sales=self._safe_decimal(self._db_val(df, a.get('asset_sales', []), col)),
                investment_purchases=self._safe_decimal(self._db_val(df, a.get('investment_purchases', []), col)),
                debt_issued=self._safe_decimal(self._db_val(df, a.get('debt_issued', []), col)),
                debt_repayment=self._safe_decimal(self._db_val(df, a.get('debt_repayment', []), col)),
                share_repurchases=self._safe_decimal(self._db_val(df, a.get('share_repurchases', []), col)),
                share_issuance=self._safe_decimal(self._db_val(df, a.get('share_issuance', []), col)),
                last_validated_at=None,

                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    # ---- Dividends parser (DBeta & YF) ----
    def _parse_dividends(self, df: pd.DataFrame, company_id: int, symbol: str, provider: str) -> List[DividendRow]:
        rows: List[DividendRow] = []
        # Map possible column names
        cols = {c.lower(): c for c in df.columns}
        exd_col = cols.get('ex_dividend_date') or cols.get('report_date') or cols.get('date')  # DBeta uses report_date; YF uses index/Date
        amt_col = cols.get('dividend') or cols.get('amount')

        # Optional fields if present
        pay_col = cols.get('payment_date')
        rec_col = cols.get('record_date')
        freq_col = cols.get('frequency')

        if not exd_col or not amt_col:
            # Attempt YF Series-to-DF fallback is handled before calling this
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
                dividend_type='regular',   # schema default; adjust if source provides types
                currency='USD',
                frequency=freq,
                last_validated_at=None,
                confidence_score=self.settings.DEFEAT_BETA_CONFIDENCE_SCORE if provider == 'dbeta' else self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    # ---------------------------------------------------------------------
    # YF parsers (best-effort to schema)
    # ---------------------------------------------------------------------
    def _parse_yf_income_statement(
        self, df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str,
        only_after: Optional[Tuple[Optional[int], Optional[int]]]
    ) -> List[IncomeStatementRow]:
        rows: List[IncomeStatementRow] = []
        if df is None or df.empty:
            return rows

        for col in df.columns:
            if not hasattr(col, 'year'):
                continue
            fy = col.year
            fq = (col.month - 1) // 3 + 1 if is_quarterly else None
            if only_after and not self._is_new_fiscal_period(fy, fq, only_after[0], only_after[1]):
                continue

            def gv(keys: List[str]) -> Any:
                for k in keys:
                    if k in df.index:
                        v = df.loc[k, col]
                        if pd.isna(v):
                            continue
                        return v
                return None

            rows.append(IncomeStatementRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=col.date(),

                revenue=self._safe_decimal(pd.to_numeric(gv(['Total Revenue', 'TotalRevenue', 'Revenue']), errors='coerce')),
                cost_of_goods_sold=self._safe_decimal(pd.to_numeric(gv(['Cost Of Revenue', 'Cost of Revenue', 'CostOfRevenue']), errors='coerce')),
                gross_profit=self._safe_decimal(pd.to_numeric(gv(['Gross Profit', 'GrossProfit']), errors='coerce')),
                operating_expenses=None,  # YF roll-ups vary; leave None unless mapped explicitly
                rd_expenses=None,
                sga_expenses=None,
                operating_income=self._safe_decimal(pd.to_numeric(gv(['Operating Income', 'OperatingIncome']), errors='coerce')),
                interest_expense=self._safe_decimal(pd.to_numeric(gv(['Interest Expense', 'InterestExpense']), errors='coerce')),
                tax_expense=self._safe_decimal(pd.to_numeric(gv(['Income Tax Expense', 'Tax Provision']), errors='coerce')),
                net_income=self._safe_decimal(pd.to_numeric(gv(['Net Income', 'NetIncome', 'Net Income Common Stockholders']), errors='coerce')),
                ebitda=self._safe_decimal(pd.to_numeric(gv(['EBITDA']), errors='coerce')),
                ebit=self._safe_decimal(pd.to_numeric(gv(['EBIT']), errors='coerce')),
                currency="USD",

                non_operating_income_expense=None,
                pretax_income=self._safe_decimal(pd.to_numeric(gv(['Pretax Income', 'Income Before Tax', 'Earnings Before Tax']), errors='coerce')),
                equity_in_earnings=None,
                minority_interest=None,
                income_from_continuing_operations=None,
                discontinued_operations=None,
                net_income_to_common=None,
                preferred_dividends=None,
                last_validated_at=None,

                confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    def _parse_yf_balance_sheet(
        self, df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str,
        only_after: Optional[Tuple[Optional[int], Optional[int]]]
    ) -> List[BalanceSheetRow]:
        rows: List[BalanceSheetRow] = []
        if df is None or df.empty:
            return rows

        for col in df.columns:
            if not hasattr(col, 'year'):
                continue
            fy = col.year
            fq = (col.month - 1) // 3 + 1 if is_quarterly else None
            if only_after and not self._is_new_fiscal_period(fy, fq, only_after[0], only_after[1]):
                continue

            def gv(keys: List[str]) -> Any:
                for k in keys:
                    if k in df.index:
                        v = df.loc[k, col]
                        if pd.isna(v):
                            continue
                        return v
                return None

            rows.append(BalanceSheetRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=col.date(),

                total_assets=self._safe_decimal(pd.to_numeric(gv(['Total Assets', 'TotalAssets']), errors='coerce')),
                current_assets=self._safe_decimal(pd.to_numeric(gv(['Total Current Assets', 'TotalCurrentAssets']), errors='coerce')),
                cash_and_cash_equivalents=self._safe_decimal(pd.to_numeric(gv(['Cash And Cash Equivalents', 'CashAndCashEquivalents']), errors='coerce')),
                accounts_receivable=self._safe_decimal(pd.to_numeric(gv(['Accounts Receivable', 'Receivables']), errors='coerce')),
                inventory=self._safe_decimal(pd.to_numeric(gv(['Inventory']), errors='coerce')),
                property_plant_equipment_net=self._safe_decimal(pd.to_numeric(gv(['Net PPE', 'Property Plant And Equipment Net']), errors='coerce')),
                intangible_assets=self._safe_decimal(pd.to_numeric(gv(['Intangible Assets']), errors='coerce')),
                goodwill=self._safe_decimal(pd.to_numeric(gv(['Goodwill']), errors='coerce')),

                total_liabilities=self._safe_decimal(pd.to_numeric(gv(['Total Liabilities', 'TotalLiab']), errors='coerce')),
                current_liabilities=self._safe_decimal(pd.to_numeric(gv(['Total Current Liabilities', 'TotalCurrentLiabilities']), errors='coerce')),
                accounts_payable=self._safe_decimal(pd.to_numeric(gv(['Accounts Payable']), errors='coerce')),
                short_term_debt=self._safe_decimal(pd.to_numeric(gv(['Short Term Debt']), errors='coerce')),
                long_term_debt=self._safe_decimal(pd.to_numeric(gv(['Long Term Debt', 'LongTermDebt']), errors='coerce')),
                total_debt=self._safe_decimal(pd.to_numeric(gv(['Total Debt']), errors='coerce')),

                shareholders_equity=self._safe_decimal(pd.to_numeric(gv(["Stockholders' Equity", 'Total Stockholder Equity']), errors='coerce')),
                retained_earnings=self._safe_decimal(pd.to_numeric(gv(['Retained Earnings']), errors='coerce')),
                common_stock=None,
                currency="USD",

                long_term_investments=self._safe_decimal(pd.to_numeric(gv(['Long Term Investments', 'LongTermInvestments']), errors='coerce')),
                other_non_current_assets=None,
                other_current_liabilities=None,
                minority_interest=self._safe_decimal(pd.to_numeric(gv(['Minority Interest', 'MinorityInterest']), errors='coerce')),
                total_liabilities_and_equity=None,
                last_validated_at=None,

                confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    def _parse_yf_cash_flow(
        self, df: pd.DataFrame, company_id: int, is_quarterly: bool, symbol: str,
        only_after: Optional[Tuple[Optional[int], Optional[int]]]
    ) -> List[CashFlowRow]:
        rows: List[CashFlowRow] = []
        if df is None or df.empty:
            return rows

        for col in df.columns:
            if not hasattr(col, 'year'):
                continue
            fy = col.year
            fq = (col.month - 1) // 3 + 1 if is_quarterly else None
            if only_after and not self._is_new_fiscal_period(fy, fq, only_after[0], only_after[1]):
                continue

            def gv(keys: List[str]) -> Any:
                for k in keys:
                    if k in df.index:
                        v = df.loc[k, col]
                        if pd.isna(v):
                            continue
                        return v
                return None

            rows.append(CashFlowRow(
                company_id=company_id,
                fiscal_year=fy,
                fiscal_quarter=fq,
                period_end_date=col.date(),

                cash_from_operating_activities=self._safe_decimal(pd.to_numeric(gv(['Operating Cash Flow', 'Total Cash From Operating Activities']), errors='coerce')),
                net_income=self._safe_decimal(pd.to_numeric(gv(['Net Income', 'NetIncome']), errors='coerce')),
                depreciation_amortization=self._safe_decimal(pd.to_numeric(gv(['Depreciation & Amortization', 'Depreciation']), errors='coerce')),
                capital_expenditures=self._safe_decimal(pd.to_numeric(gv(['Capital Expenditure', 'Capital Expenditures']), errors='coerce')),
                cash_from_investing_activities=self._safe_decimal(pd.to_numeric(gv(['Total Cash From Investing Activities']), errors='coerce')),
                cash_from_financing_activities=self._safe_decimal(pd.to_numeric(gv(['Total Cash From Financing Activities']), errors='coerce')),
                dividends_paid=self._safe_decimal(pd.to_numeric(gv(['Cash Dividends Paid', 'Dividends Paid']), errors='coerce')),
                currency="USD",

                change_in_working_capital=self._safe_decimal(pd.to_numeric(gv(['Change In Working Capital']), errors='coerce')),
                deferred_taxes=self._safe_decimal(pd.to_numeric(gv(['Deferred Income Tax', 'DeferredTax']), errors='coerce')),
                stock_based_compensation=self._safe_decimal(pd.to_numeric(gv(['Stock Based Compensation']), errors='coerce')),
                acquisitions=self._safe_decimal(pd.to_numeric(gv(['Purchase of Business']), errors='coerce')),
                asset_sales=self._safe_decimal(pd.to_numeric(gv(['Sale Of Property Plant Equipment']), errors='coerce')),
                investment_purchases=self._safe_decimal(pd.to_numeric(gv(['Investments', 'Purchase Of Investments']), errors='coerce')),
                debt_issued=self._safe_decimal(pd.to_numeric(gv(['Issuance Of Debt', 'Issuance Of Long Term Debt']), errors='coerce')),
                debt_repayment=self._safe_decimal(pd.to_numeric(gv(['Repayment Of Debt', 'Repayment Of Long Term Debt']), errors='coerce')),
                share_repurchases=self._safe_decimal(pd.to_numeric(gv(['Sale Purchase Of Stock', 'Repurchase Of Capital Stock']), errors='coerce')),
                share_issuance=self._safe_decimal(pd.to_numeric(gv(['Sale Of Stock', 'Issuance Of Capital Stock']), errors='coerce')),
                last_validated_at=None,

                confidence_score=self.settings.YFINANCE_FALLBACK_CONFIDENCE_SCORE,
                validation_notes=None,
            ))
        return rows

    def _build_earnings_rows_from_yf(self, company_id: int, yf_earn: Optional[List[Dict[str, Any]]]) -> List[EarningsRow]:
        rows: List[EarningsRow] = []
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
                        if rev_est != 0:
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
            logger.debug(f"Fetch failed: {str(result)}")
            return default
        return result if result else default

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
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {description}")
            symbol = description.split(" for ")[-1] if " for " in description else "unknown"
            raise FinancialsFetchTimeoutError(
                symbol, description, self.settings.DEFEAT_BETA_TIMEOUT_SECONDS
            )

    def _filter_to_new_data(
        self,
        fin: CompleteFundamentals,
        last_year: int,
        last_quarter: Optional[int]
    ) -> CompleteFundamentals:
        def keep(fy: Optional[int], fq: Optional[int]) -> bool:
            return self._is_new_fiscal_period(fy, fq, last_year, last_quarter)

        fin.income_statements.rows = [r for r in fin.income_statements.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        fin.balance_sheets.rows = [r for r in fin.balance_sheets.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        fin.cash_flows.rows = [r for r in fin.cash_flows.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        fin.earnings.rows = [r for r in fin.earnings.rows if keep(r.fiscal_year, r.fiscal_quarter)]
        # dividends filtered by date if you wish; currently keep all
        return fin

    def _is_new_fiscal_period(
        self,
        fy: Optional[int],
        fq: Optional[int],
        last_year: Optional[int],
        last_quarter: Optional[int]
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
            return False  # annual vs annual -> not "newer" by itself
        if last_quarter is None:
            return True
        return fq > last_quarter

    def _safe_decimal(self, val: Any) -> Optional[Decimal]:
        if val is None:
            return None
        # Handle NaN floats
        if isinstance(val, float) and val != val:
            return None
        try:
            return Decimal(str(val))
        except (InvalidOperation, ValueError, TypeError):
            return None

    def _log_debug_once(self, msg: str):
        # Simple hook to avoid noisy logs; customize or deduplicate if you like.
        logger.debug(msg)

    
    def _clean_breakdown_label(self, s: str) -> str:
        if s is None:
            return ""
        s = html.unescape(str(s)).strip()  # unescape once; it handles &amp; → &
        s = re.sub(r'^[+\s]+', '', s)
        s = re.sub(r'\s+', ' ', s)
        return s
