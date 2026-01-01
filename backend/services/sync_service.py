
import asyncio
import pandas as pd
import yfinance as yf
from database import supabase
from typing import Optional
from datetime import datetime

class SyncService:
    def __init__(self):
        pass

    async def sync_full_company_data(self, company_id: int, ticker_symbol: str):
        """
        Main entry point for deep syncing company financials in the background.
        """
        print(f"[DEBUG] Starting deep sync for {ticker_symbol} (ID: {company_id})")
        try:
            ticker = yf.Ticker(ticker_symbol)
            
            # Run different syncs
            await self._sync_income_statements(company_id, ticker)
            await self._sync_balance_sheets(company_id, ticker)
            await self._sync_cash_flow_statements(company_id, ticker)
            await self._sync_dividend_history(company_id, ticker)
            await self._sync_earnings(company_id, ticker)
            await self._sync_statistics(company_id, ticker)
            
            print(f"[DEBUG] Deep sync completed for {ticker_symbol}")
        except Exception as e:
            print(f"[ERROR] Sync failed for {ticker_symbol}: {e}")
            import traceback
            traceback.print_exc()

    async def _sync_income_statements(self, company_id: int, ticker: yf.Ticker):
        """Syncs annual and quarterly income statements."""
        # Annual
        df = ticker.income_stmt
        if not df.empty:
            await self._upsert_financials(company_id, df, 'income_statements', is_quarterly=False)
        
        # Quarterly
        df_q = ticker.quarterly_income_stmt
        if not df_q.empty:
            await self._upsert_financials(company_id, df_q, 'income_statements', is_quarterly=True)

    async def _sync_balance_sheets(self, company_id: int, ticker: yf.Ticker):
        # Annual
        df = ticker.balance_sheet
        if not df.empty:
            await self._upsert_financials(company_id, df, 'balance_sheets', is_quarterly=False)
        
        # Quarterly
        df_q = ticker.quarterly_balance_sheet
        if not df_q.empty:
            await self._upsert_financials(company_id, df_q, 'balance_sheets', is_quarterly=True)

    async def _sync_cash_flow_statements(self, company_id: int, ticker: yf.Ticker):
        # Annual
        df = ticker.cashflow
        if not df.empty:
            await self._upsert_financials(company_id, df, 'cash_flow_statements', is_quarterly=False)
        
        # Quarterly
        df_q = ticker.quarterly_cashflow
        if not df_q.empty:
            await self._upsert_financials(company_id, df_q, 'cash_flow_statements', is_quarterly=True)

    async def _upsert_financials(self, company_id: int, df: pd.DataFrame, table_name: str, is_quarterly: bool):
        """
        Generic helper to map yfinance DataFrames to Supabase tables.
        """
        df_t = df.T
        
        mapping = {
            'Total Revenue': 'revenue',
            'Cost Of Revenue': 'cost_of_goods_sold',
            'Gross Profit': 'gross_profit',
            'Operating Expense': 'operating_expenses',
            'Research And Development': 'rd_expenses',
            'Selling General And Administrative': 'sga_expenses',
            'Operating Income': 'operating_income',
            'Interest Expense': 'interest_expense',
            'Tax Provision': 'tax_expense',
            'Net Income': 'net_income',
            'EBITDA': 'ebitda',
            'EBIT': 'ebit',
            
            # Balance Sheet
            'Total Assets': 'total_assets',
            'Current Assets': 'current_assets',
            'Cash And Cash Equivalents': 'cash_and_cash_equivalents',
            'Inventory': 'inventory',
            'Net PPE': 'property_plant_equipment_net',
            'Total Liabilities Net Minority Interest': 'total_liabilities',
            'Current Liabilities': 'current_liabilities',
            'Total Debt': 'total_debt',
            'Stockholders Equity': 'shareholders_equity',
            
            # Cash Flow
            'Operating Cash Flow': 'cash_from_operating_activities',
            'Investing Cash Flow': 'cash_from_investing_activities',
            'Financing Cash Flow': 'cash_from_financing_activities',
            'Capital Expenditure': 'capital_expenditures'
        }

        records = []
        for timestamp, row in df_t.iterrows():
            record = {
                'company_id': company_id,
                'period_end_date': timestamp.date().isoformat(),
                'fiscal_year': timestamp.year,
                'fiscal_quarter': ((timestamp.month - 1) // 3 + 1) if is_quarterly else None,
                'data_source': 'yfinance'
            }
            
            for yf_key, db_col in mapping.items():
                if yf_key in row and not pd.isna(row[yf_key]):
                    record[db_col] = float(row[yf_key])
            
            records.append(record)

        if records:
            try:
                supabase.table(table_name).upsert(records).execute()
            except Exception as e:
                print(f"[WARN] Upsert to {table_name} failed: {e}")

    async def _sync_dividend_history(self, company_id: int, ticker: yf.Ticker):
        dividends = ticker.dividends
        if dividends.empty:
            return

        records = []
        for timestamp, amount in dividends.items():
            records.append({
                'company_id': company_id,
                'ex_dividend_date': timestamp.date().isoformat(),
                'dividend_amount': float(amount),
                'dividend_type': 'regular',
                'data_source': 'yfinance'
            })

        if records:
            try:
                supabase.table('dividend_history').upsert(records, on_conflict='company_id,ex_dividend_date').execute()
            except Exception as e:
                print(f"[WARN] Dividend upsert failed: {e}")

    async def _sync_earnings(self, company_id: int, ticker: yf.Ticker):
        """Syncs earnings history from yfinance."""
        try:
            # yfinance provides earnings_dates (historical and upcoming)
            df = ticker.earnings_dates
            if df is None or df.empty:
                return

            records = []
            for timestamp, row in df.iterrows():
                # Some dates are in the future, we mainly want historical for this table
                # but we can store both. announcement_date is the index.
                
                # We don't easily have 'fiscal_year' and 'fiscal_quarter' from this DF index alone
                # without more processing, so we'll use announcement_date for period_end_date fallback
                
                record = {
                    'company_id': company_id,
                    'announcement_date': timestamp.date().isoformat(),
                    'period_end_date': timestamp.date().isoformat(), # Fallback
                    'fiscal_year': timestamp.year, # Fallback
                    'eps_reported_diluted': float(row['Reported EPS']) if not pd.isna(row.get('Reported EPS')) else None,
                    'eps_estimate': float(row['EPS Estimate']) if not pd.isna(row.get('EPS Estimate')) else None,
                    'eps_surprise_amount': float(row['Surprise(%)']) if not pd.isna(row.get('Surprise(%)')) else None, # This is usually % in yf
                    'data_source': 'yfinance'
                }
                records.append(record)

            if records:
                supabase.table('earnings').upsert(records).execute()
        except Exception as e:
            print(f"[WARN] Earnings sync failed: {e}")

    async def _sync_statistics(self, company_id: int, ticker: yf.Ticker):
        """Syncs current statistics/ratios from yfinance."""
        try:
            info = ticker.info
            if not info:
                return

            # yfinance info is a snapshot, so we map it to a 'ttm' period type record
            # We use the current date as the period_end_date for the TTM entry
            now = datetime.now()
            
            record = {
                'company_id': company_id,
                'fiscal_year': now.year,
                'period_end_date': now.date().isoformat(),
                'period_type': 'ttm',
                'pe_ratio': info.get('trailingPE'),
                'ps_ratio': info.get('priceToSalesTrailing12Months'),
                'pb_ratio': info.get('priceToBook'),
                'enterprise_value': info.get('enterpriseValue'),
                'ev_to_ebitda': info.get('enterpriseToEbitda'),
                'gross_margin_pct': info.get('grossMargins'),
                'operating_margin_pct': info.get('operatingMargins'),
                'ebitda_margin_pct': info.get('ebitdaMargins'),
                'net_margin_pct': info.get('profitMargins'),
                'return_on_assets_pct': info.get('returnOnAssets'),
                'return_on_equity_pct': info.get('returnOnEquity'),
                'current_ratio': info.get('currentRatio'),
                'quick_ratio': info.get('quickRatio'),
                'debt_to_equity': info.get('debtToEquity'),
                'revenue_per_share': info.get('revenuePerShare'),
                'cash_per_share': info.get('totalCashPerShare'),
                'book_value_per_share': info.get('bookValue'),
                'shares_outstanding_basic': info.get('sharesOutstanding'),
                'dividend_yield_pct': info.get('dividendYield'),
                'payout_ratio_pct': info.get('payoutRatio'),
                'data_source': 'yfinance'
            }

            # Convert 0-1 decimals to percentages if that's what the schema expects (numeric(6,3))
            # Actually schema says _pct, so usually means percent. yfinance gives decimals (e.g. 0.25 for 25%).
            pct_cols = ['gross_margin_pct', 'operating_margin_pct', 'ebitda_margin_pct', 'net_margin_pct', 
                        'return_on_assets_pct', 'return_on_equity_pct', 'dividend_yield_pct', 'payout_ratio_pct']
            for col in pct_cols:
                if record[col] is not None:
                    record[col] = float(record[col]) * 100

            supabase.table('statistics').upsert(record).execute()
        except Exception as e:
            print(f"[WARN] Statistics sync failed: {e}")

sync_service = SyncService()
