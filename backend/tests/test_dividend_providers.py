"""
Unit tests for provider upcoming-ex-date methods (§7.6.1 — 7 tests).

YFinanceProvider:
  - Primary: info.exDividendDate present
  - Secondary: calendar.Ex-Dividend Date present
  - No future date → None
  - Missing info dict → None

StockdexProvider:
  - Valid response with future date
  - Empty response → None
  - Missing dividendExDate → None
  - Rate-limited → None
"""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from providers.yfinance_provider import YFinanceProvider
from providers.stockdex_provider import StockdexMacrotrendsProvider


def _future_timestamp(days_from_now: int = 30) -> float:
    """Unix timestamp for a future date."""
    target = date.today() + timedelta(days=days_from_now)
    dt = datetime(target.year, target.month, target.day, tzinfo=timezone.utc)
    return dt.timestamp()


def _future_date_str(days_from_now: int = 60) -> str:
    """ISO date string for a future date."""
    return (date.today() + timedelta(days=days_from_now)).isoformat()


class TestYFinanceProvider:
    """Tests for YFinanceProvider.get_upcoming_ex_date."""

    @patch("providers.yfinance_provider.yf")
    def test_primary_exdividenddate_present(self, mock_yf):
        """info.exDividendDate (Unix timestamp, future) → date returned."""
        ts = _future_timestamp(30)
        mock_tkr = MagicMock()
        mock_yf.Ticker.return_value = mock_tkr
        mock_tkr.info = {"exDividendDate": ts}
        mock_tkr.calendar = None  # skip secondary

        provider = YFinanceProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is not None
        assert result >= date.today()

    @patch("providers.yfinance_provider.yf")
    def test_secondary_calendar_present(self, mock_yf):
        """calendar.Ex-Dividend Date present, primary absent → date returned."""
        future_date = date.today() + timedelta(days=60)
        mock_tkr = MagicMock()
        mock_yf.Ticker.return_value = mock_tkr
        mock_tkr.info = {}  # No exDividendDate

        mock_cal_df = pd.DataFrame({"Ex-Dividend Date": [future_date.isoformat()]})
        mock_tkr.calendar = mock_cal_df

        provider = YFinanceProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is not None
        assert result >= date.today()

    @patch("providers.yfinance_provider.yf")
    def test_no_future_date(self, mock_yf):
        """Both fields absent or past → None."""
        mock_tkr = MagicMock()
        mock_yf.Ticker.return_value = mock_tkr
        mock_tkr.info = {}
        # Calendar with no Ex-Dividend Date column
        mock_cal_df = pd.DataFrame({"Dividend Rate": [1.0]})
        mock_tkr.calendar = mock_cal_df

        provider = YFinanceProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is None

    @patch("providers.yfinance_provider.yf")
    def test_missing_info_dict(self, mock_yf):
        """tkr.info = {} → None."""
        mock_tkr = MagicMock()
        mock_yf.Ticker.return_value = mock_tkr
        mock_tkr.info = {}
        mock_tkr.calendar = None

        provider = YFinanceProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is None


class TestStockdexProvider:
    """Tests for StockdexMacrotrendsProvider.get_upcoming_ex_date."""

    @patch.object(StockdexMacrotrendsProvider, "_get_or_create_ticker")
    @patch("providers.stockdex_provider.time")
    def test_valid_finviz_response(self, mock_time, mock_get_ticker):
        """Finviz dict with future date → date returned."""
        mock_time.monotonic.return_value = 1000.0
        future_date = _future_date_str(60)
        mock_ticker = MagicMock()
        mock_get_ticker.return_value = mock_ticker
        mock_ticker.finviz_overall_dividend.return_value = {
            "dividendExDate": future_date,
        }

        provider = StockdexMacrotrendsProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is not None
        assert result >= date.today()

    @patch.object(StockdexMacrotrendsProvider, "_get_or_create_ticker")
    @patch("providers.stockdex_provider.time")
    def test_empty_dataframe(self, mock_time, mock_get_ticker):
        """Empty response → None."""
        mock_time.monotonic.return_value = 1000.0
        mock_ticker = MagicMock()
        mock_get_ticker.return_value = mock_ticker
        mock_ticker.finviz_overall_dividend.return_value = {}

        provider = StockdexMacrotrendsProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is None

    @patch.object(StockdexMacrotrendsProvider, "_get_or_create_ticker")
    @patch("providers.stockdex_provider.time")
    def test_missing_dividendexdate_column(self, mock_time, mock_get_ticker):
        """Response missing dividendExDate → None."""
        mock_time.monotonic.return_value = 1000.0
        mock_ticker = MagicMock()
        mock_get_ticker.return_value = mock_ticker
        mock_ticker.finviz_overall_dividend.return_value = {"dividendYield": "3.5%"}

        provider = StockdexMacrotrendsProvider()
        result = provider.get_upcoming_ex_date("KO")

        assert result is None

    @patch.object(StockdexMacrotrendsProvider, "_get_or_create_ticker")
    @patch("providers.stockdex_provider.time")
    def test_rate_limited(self, mock_time, mock_get_ticker):
        """Cooldown active → None without calling stockdex."""
        mock_time.monotonic.return_value = 500.0
        provider = StockdexMacrotrendsProvider()
        provider._finviz_cooldown_until = 1000.0

        result = provider.get_upcoming_ex_date("KO")

        assert result is None
        mock_get_ticker.assert_not_called()
