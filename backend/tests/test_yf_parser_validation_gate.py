"""Regression tests for the YFinance fallback parser validation gates.

The three YF fallback parsers (_parse_yf_income_statement, _parse_yf_balance_sheet,
_parse_yf_cash_flow) must skip rows that fail validation (missing required fields ->
CRITICAL) so junk/NULL rows are never returned for upsert. Clean rows (all required
fields present) must still be returned.

These are focused unit tests: they construct a fake yfinance DataFrame (DatetimeIndex
columns with .year/.month/.date() attributes, row labels as index) and call each
parser directly. No network, no supabase.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest

from providers.defeat_beta_provider import DefeatBetaProvider


@pytest.fixture
def provider():
    return DefeatBetaProvider()


def _make_yf_df(index_labels, values, col_date="2024-09-30"):
    """Build a yfinance-format DataFrame.

    Columns are a DatetimeIndex (each col has .year/.month/.date() attributes);
    rows are index labels like 'Total Revenue'.
    """
    return pd.DataFrame(
        {pd.to_datetime(col_date): values},
        index=index_labels,
    )


# ---------------------------------------------------------------------------
# Income statement
# ---------------------------------------------------------------------------

def _income_clean_df():
    return _make_yf_df(
        ["Total Revenue", "Gross Profit", "Operating Income", "Net Income"],
        [500000.0, 250000.0, 120000.0, 80000.0],
    )


def _income_junk_df():
    # Only revenue present -> gross_profit/operating_income/net_income missing (CRITICAL)
    return _make_yf_df(["Total Revenue"], [500000.0])


class TestYfIncomeValidationGate:
    def test_clean_row_is_kept(self, provider):
        rows = provider._parse_yf_income_statement(
            _income_clean_df(), company_id=1, is_quarterly=False,
            symbol="AAPL", only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        assert rows[0].revenue == 500000.0
        assert rows[0].net_income == 80000.0

    def test_junk_row_is_dropped(self, provider):
        rows = provider._parse_yf_income_statement(
            _income_junk_df(), company_id=1, is_quarterly=False,
            symbol="AAPL", only_after=None, source="yfinance",
        )
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Balance sheet
# ---------------------------------------------------------------------------

def _balance_clean_df():
    return _make_yf_df(
        ["Total Assets", "Total Liabilities", "Stockholders' Equity"],
        [2000000.0, 1200000.0, 800000.0],
    )


def _balance_junk_df():
    # Only total_assets present -> total_liabilities/shareholders_equity missing (CRITICAL)
    return _make_yf_df(["Total Assets"], [2000000.0])


class TestYfBalanceValidationGate:
    def test_clean_row_is_kept(self, provider):
        rows = provider._parse_yf_balance_sheet(
            _balance_clean_df(), company_id=1, is_quarterly=False,
            symbol="AAPL", only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        assert rows[0].total_assets == 2000000.0
        assert rows[0].shareholders_equity == 800000.0

    def test_junk_row_is_dropped(self, provider):
        rows = provider._parse_yf_balance_sheet(
            _balance_junk_df(), company_id=1, is_quarterly=False,
            symbol="AAPL", only_after=None, source="yfinance",
        )
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Cash flow
# ---------------------------------------------------------------------------

def _cashflow_clean_df():
    return _make_yf_df(
        [
            "Operating Cash Flow",
            "Total Cash From Investing Activities",
            "Total Cash From Financing Activities",
        ],
        [120000.0, -50000.0, -30000.0],
    )


def _cashflow_junk_df():
    # Only operating present -> investing/financing missing (CRITICAL)
    return _make_yf_df(["Operating Cash Flow"], [120000.0])


class TestYfCashFlowValidationGate:
    def test_clean_row_is_kept(self, provider):
        rows = provider._parse_yf_cash_flow(
            _cashflow_clean_df(), company_id=1, is_quarterly=False,
            symbol="AAPL", only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        assert rows[0].cash_from_operating_activities == 120000.0
        assert rows[0].cash_from_financing_activities == -30000.0

    def test_junk_row_is_dropped(self, provider):
        rows = provider._parse_yf_cash_flow(
            _cashflow_junk_df(), company_id=1, is_quarterly=False,
            symbol="AAPL", only_after=None, source="yfinance",
        )
        assert len(rows) == 0
