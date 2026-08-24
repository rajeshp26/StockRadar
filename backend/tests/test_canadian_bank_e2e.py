"""End-to-end test for Canadian bank tickers (TD.TO, RY.TO, CM.TO).

Verifies that the full provider chain — DefeatBeta primary → Stockdex IFRS
fallback → YFinance fallback — correctly propagates field_sources metadata
through all parsing stages for Canadian bank tickers.

Uses mocked external API responses simulating realistic IFRS data gaps.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock

import pandas as pd
import pytest

from providers.defeat_beta_provider import DefeatBetaProvider

CANADIAN_TICKERS = ["TD.TO", "RY.TO", "CM.TO"]


@pytest.fixture
def mock_stockdex():
    m = MagicMock()
    m.is_rate_limited.return_value = False
    m.get_annual_income_statement.return_value = None
    m.get_quarterly_income_statement.return_value = None
    m.get_annual_balance_sheet.return_value = None
    m.get_quarterly_balance_sheet.return_value = None
    m.get_annual_cash_flow.return_value = None
    m.get_quarterly_cash_flow.return_value = None
    return m


@pytest.fixture
def mock_yfinance():
    m = MagicMock()
    m.get_annual_income_statement.return_value = None
    m.get_quarterly_income_statement.return_value = None
    m.get_annual_balance_sheet.return_value = None
    m.get_quarterly_balance_sheet.return_value = None
    m.get_annual_cash_flow.return_value = None
    m.get_quarterly_cash_flow.return_value = None
    return m


@pytest.fixture
def mock_edgar():
    m = MagicMock()
    return m


@pytest.fixture
def provider(mock_stockdex, mock_yfinance, mock_edgar):
    return DefeatBetaProvider(
        yfinance_provider=mock_yfinance,
        edgar_provider=mock_edgar,
        stockdex_provider=mock_stockdex,
    )


def _make_yf_income_df(revenue, net_income, gross_profit=None, operating_income=None):
    """Build yfinance-format income DataFrame (DatetimeIndex columns, row labels as index)."""
    index_labels = ["Total Revenue", "Net Income"]
    values = [revenue, net_income]
    if gross_profit is not None:
        index_labels.append("Gross Profit")
        values.append(gross_profit)
    if operating_income is not None:
        index_labels.append("Operating Income")
        values.append(operating_income)
    return pd.DataFrame(
        {pd.to_datetime("2024-09-30"): values},
        index=index_labels,
    )


def _make_yf_balance_df(total_assets, current_assets=None, total_liabilities=None):
    """Build yfinance-format balance sheet DataFrame (DatetimeIndex columns, row labels as index)."""
    index_labels = ["Total Assets"]
    values = [total_assets]
    if current_assets is not None:
        index_labels.append("Total Current Assets")
        values.append(current_assets)
    if total_liabilities is not None:
        index_labels.append("Total Liabilities")
        values.append(total_liabilities)
    return pd.DataFrame(
        {pd.to_datetime("2024-09-30"): values},
        index=index_labels,
    )


def _make_yf_cashflow_df(operating=None, investing=None, financing=None, capex=None):
    """Build yfinance-format cash flow DataFrame (DatetimeIndex columns, row labels as index).

    Row labels match what _parse_yf_cash_flow expects:
      - 'Operating Cash Flow' for cash_from_operating_activities
      - 'Total Cash From Investing Activities' for cash_from_investing_activities
      - 'Total Cash From Financing Activities' for cash_from_financing_activities
      - 'Capital Expenditure' for capital_expenditures
    """
    index_labels = []
    values = []
    if operating is not None:
        index_labels.append("Operating Cash Flow")
        values.append(operating)
    if investing is not None:
        index_labels.append("Total Cash From Investing Activities")
        values.append(investing)
    if financing is not None:
        index_labels.append("Total Cash From Financing Activities")
        values.append(financing)
    if capex is not None:
        index_labels.append("Capital Expenditure")
        values.append(capex)
    if not index_labels:
        return None
    return pd.DataFrame(
        {pd.to_datetime("2024-09-30"): values},
        index=index_labels,
    )


class TestCanadianBankProviderChain:
    """End-to-end provider chain tests for Canadian bank tickers."""

    def _parse_via_yf_income(self, provider, symbol, company_id=1):
        df = _make_yf_income_df(
            revenue=500000, net_income=80000,
            gross_profit=250000, operating_income=150000,
        )
        return provider._parse_yf_income_statement(
            df, company_id=company_id, is_quarterly=False,
            symbol=symbol, only_after=None, source="yfinance",
        )

    def _parse_via_yf_balance(self, provider, symbol, company_id=1):
        df = _make_yf_balance_df(
            total_assets=2000000, current_assets=500000,
            total_liabilities=1800000,
        )
        return provider._parse_yf_balance_sheet(
            df, company_id=company_id, is_quarterly=False,
            symbol=symbol, only_after=None, source="yfinance",
        )

    def _parse_via_yf_cashflow(self, provider, symbol, company_id=1):
        df = _make_yf_cashflow_df(
            operating=120000, investing=-50000,
            financing=-30000, capex=-25000,
        )
        return provider._parse_yf_cash_flow(
            df, company_id=company_id, is_quarterly=False,
            symbol=symbol, only_after=None, source="yfinance",
        )

    def _parse_via_stockdex_income(self, provider, symbol, company_id=1):
        df = _make_yf_income_df(
            revenue=480000, net_income=75000,
            gross_profit=240000, operating_income=140000,
        )
        return provider._parse_yf_income_statement(
            df, company_id=company_id, is_quarterly=False,
            symbol=symbol, only_after=None, source="stockdex",
        )

    @pytest.mark.parametrize("ticker", CANADIAN_TICKERS)
    def test_yfinance_fallback_income_provenance(self, provider, ticker):
        rows = self._parse_via_yf_income(provider, ticker)
        assert len(rows) == 1
        row = rows[0]
        assert row.data_source == "yfinance"
        fs = row.field_sources
        assert fs is not None
        assert fs["revenue"] == ["yfinance"]
        assert fs["net_income"] == ["yfinance"]
        assert fs["gross_profit"] == ["yfinance"]
        assert fs["operating_income"] == ["yfinance"]

    @pytest.mark.parametrize("ticker", CANADIAN_TICKERS)
    def test_yfinance_fallback_balance_provenance(self, provider, ticker):
        rows = self._parse_via_yf_balance(provider, ticker)
        assert len(rows) == 1
        row = rows[0]
        assert row.data_source == "yfinance"
        fs = row.field_sources
        assert fs is not None
        assert fs["total_assets"] == ["yfinance"]
        assert fs["current_assets"] == ["yfinance"]
        assert fs["total_liabilities"] == ["yfinance"]

    @pytest.mark.parametrize("ticker", CANADIAN_TICKERS)
    def test_yfinance_fallback_cashflow_provenance(self, provider, ticker):
        rows = self._parse_via_yf_cashflow(provider, ticker)
        assert len(rows) == 1
        row = rows[0]
        assert row.data_source == "yfinance"
        fs = row.field_sources
        assert fs is not None
        assert fs["cash_from_operating_activities"] == ["yfinance"]
        assert fs["capital_expenditures"] == ["yfinance"]

    @pytest.mark.parametrize("ticker", CANADIAN_TICKERS)
    def test_stockdex_fallback_income_provenance(self, provider, ticker):
        rows = self._parse_via_stockdex_income(provider, ticker)
        assert len(rows) == 1
        row = rows[0]
        assert row.data_source == "stockdex"
        fs = row.field_sources
        assert fs["revenue"] == ["stockdex"]
        assert fs["net_income"] == ["stockdex"]

    @pytest.mark.parametrize("ticker", CANADIAN_TICKERS)
    def test_yfinance_partial_coverage_provenance(self, provider, ticker):
        """YFinance with incomplete data — only revenue available."""
        df = pd.DataFrame(
            {pd.to_datetime("2024-09-30"): [500000.0]},
            index=["Total Revenue"],
        )
        rows = provider._parse_yf_income_statement(
            df, company_id=1, is_quarterly=False, symbol=ticker,
            only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs is not None
        assert fs["revenue"] == ["yfinance"]
        assert "net_income" not in fs
        assert "gross_profit" not in fs

    def test_td_to_yfinance_income_has_all_core_fields(self, provider):
        rows = self._parse_via_yf_income(provider, "TD.TO")
        assert len(rows) == 1
        fs = rows[0].field_sources
        required_core = ["revenue", "net_income", "gross_profit", "operating_income"]
        for f in required_core:
            assert f in fs, f"Missing core field: {f}"

    def test_ry_to_yfinance_balance_has_equity(self, provider):
        df = pd.DataFrame(
            {pd.to_datetime("2024-09-30"): [2000000.0, 150000.0]},
            index=["Total Assets", "Stockholders' Equity"],
        )
        rows = provider._parse_yf_balance_sheet(
            df, company_id=1, is_quarterly=False, symbol="RY.TO",
            only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert "total_assets" in fs
        assert "shareholders_equity" in fs
        assert fs["total_assets"] == ["yfinance"]
        assert fs["shareholders_equity"] == ["yfinance"]

    def test_cm_to_yfinance_cashflow_full_coverage(self, provider):
        df = _make_yf_cashflow_df(
            operating=100000, investing=-40000,
            financing=-20000, capex=-15000,
        )
        rows = provider._parse_yf_cash_flow(
            df, company_id=1, is_quarterly=False, symbol="CM.TO",
            only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert "cash_from_operating_activities" in fs
        assert "cash_from_investing_activities" in fs
        assert "cash_from_financing_activities" in fs
        assert "capital_expenditures" in fs
        for f in ["cash_from_operating_activities", "cash_from_investing_activities",
                   "cash_from_financing_activities", "capital_expenditures"]:
            assert fs[f] == ["yfinance"]
