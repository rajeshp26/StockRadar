from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd

from providers.edgar_provider import EdgarToolsProvider as EdgarProvider


class TestEdgarProvider:
    @patch("edgar.Financials")
    @patch("edgar.Company")
    def test_quarterly_uses_10q_filings_not_quarterly_financials(
        self, mock_company_cls, mock_financials_cls
    ):
        mock_company = MagicMock()
        mock_company_cls.return_value = mock_company

        mock_filings = MagicMock()
        mock_latest = MagicMock()
        mock_filings.latest.return_value = mock_latest
        mock_company.get_filings.return_value = mock_filings

        mock_fin_obj = MagicMock()
        mock_financials_cls.extract.return_value = mock_fin_obj

        provider = EdgarProvider()

        normalised_df = pd.DataFrame(
            {"Revenue": [100.0]}, index=pd.to_datetime(["2024-09-30"])
        )

        with patch.object(
            provider, "_extract_statement_df", return_value=pd.DataFrame({"x": [1]})
        ), patch.object(provider, "_normalise", return_value=normalised_df):
            df = provider.get_quarterly_income_statement_df("AAPL")

        mock_company.get_filings.assert_called_once_with(
            form="10-Q", amendments=False, trigger_full_load=False
        )
        mock_company.get_quarterly_financials.assert_not_called()
        mock_financials_cls.extract.assert_called_once_with(mock_latest)
        assert not df.empty

    @patch("edgar.Financials")
    @patch("edgar.Company")
    def test_annual_uses_get_financials_not_10q_filings(
        self, mock_company_cls, mock_financials_cls
    ):
        mock_company = MagicMock()
        mock_company_cls.return_value = mock_company
        mock_fin_obj = MagicMock()
        mock_company.get_financials.return_value = mock_fin_obj

        provider = EdgarProvider()

        normalised_df = pd.DataFrame(
            {"Revenue": [200.0]}, index=pd.to_datetime(["2023-09-30"])
        )

        with patch.object(
            provider, "_extract_statement_df", return_value=pd.DataFrame({"x": [1]})
        ), patch.object(provider, "_normalise", return_value=normalised_df):
            df = provider.get_annual_income_statement_df("AAPL")

        mock_company.get_financials.assert_called_once()
        mock_company.get_filings.assert_not_called()
        mock_company.get_quarterly_financials.assert_not_called()
        mock_financials_cls.extract.assert_not_called()
        assert not df.empty
