"""Integration tests for provider chain provenance (field_sources).

Tests that the full provider chain — DefeatBeta primary, YFinance fallback,
Stockdex IFRS — correctly propagates field_sources metadata through
parse_income_statement, parse_balance_sheet, parse_cash_flow.

These are integration tests because they exercise real provider classes
and real pandas parsing logic with mocked DataFrames, NOT mocked providers.
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


class TestDefeatBetaPrimaryProvenance:
    """DefeatBeta primary parser sets field_sources with source='defeat_beta'.

    Raw DataFrame format: Breakdown column + date-string columns like "2024-09-30".
    The provider's _normalize_defeatbeta_df converts this to index-by-label.
    """

    def _make_raw_df(self, rows_data):
        return pd.DataFrame(rows_data)

    def test_primary_income_field_sources(self, provider):
        raw = self._make_raw_df([
            {"Breakdown": "Total Revenue", "2024-09-30": 100000},
            {"Breakdown": "Gross Profit", "2024-09-30": 50000},
            {"Breakdown": "Operating Income", "2024-09-30": 20000},
            {"Breakdown": "Net Income Common Stockholders", "2024-09-30": 15000},
        ])
        rows, gaps = provider._parse_income_statement(
            raw, company_id=1, is_quarterly=False, symbol="AAPL",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs is not None
        assert "revenue" in fs
        assert fs["revenue"] == ["defeat_beta"]
        assert "gross_profit" in fs
        assert fs["gross_profit"] == ["defeat_beta"]
        assert "net_income" in fs
        assert fs["net_income"] == ["defeat_beta"]

    def test_primary_balance_field_sources(self, provider):
        raw = self._make_raw_df([
            {"Breakdown": "Total Assets", "2024-09-30": 500000},
            {"Breakdown": "Total Current Assets", "2024-09-30": 200000},
            {"Breakdown": "Total Liabilities", "2024-09-30": 300000},
            {"Breakdown": "Stockholders' Equity", "2024-09-30": 200000},
        ])
        rows, gaps = provider._parse_balance_sheet(
            raw, company_id=1, is_quarterly=False, symbol="AAPL",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs is not None
        assert "total_assets" in fs
        assert fs["total_assets"] == ["defeat_beta"]
        assert "current_assets" in fs

    def test_primary_cashflow_field_sources(self, provider):
        raw = self._make_raw_df([
            {"Breakdown": "Operating Cash Flow", "2024-09-30": 30000},
            {"Breakdown": "Investing Cash Flow", "2024-09-30": -10000},
            {"Breakdown": "Financing Cash Flow", "2024-09-30": -5000},
            {"Breakdown": "Capital Expenditure (CapEx)", "2024-09-30": -8000},
        ])
        rows, gaps = provider._parse_cash_flow(
            raw, company_id=1, is_quarterly=False, symbol="AAPL",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs is not None
        assert "cash_from_operating_activities" in fs
        assert fs["cash_from_operating_activities"] == ["defeat_beta"]

    def test_null_fields_excluded_from_field_sources(self, provider):
        raw = self._make_raw_df([
            {"Breakdown": "Total Revenue", "2024-09-30": 500000},
            {"Breakdown": "Gross Profit", "2024-09-30": 250000},
            {"Breakdown": "Operating Income", "2024-09-30": 100000},
            {"Breakdown": "Net Income Common Stockholders", "2024-09-30": 80000},
        ])
        rows, gaps = provider._parse_income_statement(
            raw, company_id=1, is_quarterly=False, symbol="AAPL",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert "revenue" in fs
        assert "gross_profit" in fs
        assert "operating_income" in fs
        assert "net_income" in fs
        assert "cost_of_goods_sold" not in fs
        assert "ebitda" not in fs


class TestYFinanceFallbackProvenance:
    """YFinance fallback parsers set field_sources correctly.

    DataFrame format: columns are DatetimeIndex, rows are index labels like
    "Total Revenue", "Net Income", etc.  These parsers return List[...] (no gaps).
    """

    def _make_yf_df(self, index_labels, col_date="2024-09-30", values=None):
        data = {}
        for label in index_labels:
            data[label] = [values.get(label, 0) if values else 0]
        df = pd.DataFrame(data, index=[pd.to_datetime(col_date)])
        df.index.name = None
        return df.T

    def test_yf_income_source_label(self, provider):
        df = self._make_yf_df(
            ["Total Revenue", "Net Income"],
            values={"Total Revenue": 100000.0, "Net Income": 15000.0},
        )
        rows = provider._parse_yf_income_statement(
            df, company_id=1, is_quarterly=False, symbol="AAPL",
            only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs is not None
        assert fs["revenue"] == ["yfinance"]
        assert rows[0].data_source == "yfinance"

    def test_yf_balance_source_label(self, provider):
        df = self._make_yf_df(
            ["Total Assets"],
            values={"Total Assets": 500000.0},
        )
        rows = provider._parse_yf_balance_sheet(
            df, company_id=1, is_quarterly=False, symbol="AAPL",
            only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs["total_assets"] == ["yfinance"]

    def test_yf_cashflow_source_label(self, provider):
        df = self._make_yf_df(
            ["Operating Cash Flow"],
            values={"Operating Cash Flow": 30000.0},
        )
        rows = provider._parse_yf_cash_flow(
            df, company_id=1, is_quarterly=False, symbol="AAPL",
            only_after=None, source="yfinance",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs["cash_from_operating_activities"] == ["yfinance"]

    def test_stockdex_source_label(self, provider):
        df = self._make_yf_df(
            ["Total Revenue", "Net Income"],
            values={"Total Revenue": 100000.0, "Net Income": 15000.0},
        )
        rows = provider._parse_yf_income_statement(
            df, company_id=1, is_quarterly=False, symbol="TD.TO",
            only_after=None, source="stockdex",
        )
        assert len(rows) == 1
        fs = rows[0].field_sources
        assert fs["revenue"] == ["stockdex"]
        assert rows[0].data_source == "stockdex"


class TestMultiplePeriodsProvenance:
    """field_sources is built correctly for multi-period DataFrames."""

    def test_multi_period_income(self, provider):
        raw = pd.DataFrame([
            {"Breakdown": "Total Revenue", "2024-09-30": 500000, "2023-09-30": 400000},
            {"Breakdown": "Gross Profit", "2024-09-30": 250000, "2023-09-30": 200000},
            {"Breakdown": "Operating Income", "2024-09-30": 100000, "2023-09-30": 80000},
            {"Breakdown": "Net Income Common Stockholders", "2024-09-30": 80000, "2023-09-30": 60000},
        ])
        rows, gaps = provider._parse_income_statement(
            raw, company_id=1, is_quarterly=False, symbol="AAPL",
        )
        assert len(rows) == 2
        for row in rows:
            fs = row.field_sources
            assert fs is not None
            assert fs["revenue"] == ["defeat_beta"]
            assert fs["net_income"] == ["defeat_beta"]


class TestCoverageEndpointContract:
    """Verify the FinancialCoverageResponse models are correctly structured."""

    def test_response_model_structure(self):
        from api.stocks import (
            FieldCoverage,
            FinancialCoverageResponse,
            StatementCoverage,
        )
        fc = FieldCoverage(field="revenue", total_rows=5, present=4, missing=1,
                           providers={"defeat_beta": 3, "yfinance": 1})
        sc = StatementCoverage(
            statement_type="income", total_rows=5,
            fields=[fc], data_source_breakdown={"defeat_beta": 3, "yfinance": 2},
        )
        resp = FinancialCoverageResponse(
            success=True, symbol="AAPL", company_id=1,
            statements={"income": sc},
        )
        d = resp.model_dump()
        assert d["success"] is True
        assert d["statements"]["income"]["fields"][0]["providers"]["defeat_beta"] == 3
