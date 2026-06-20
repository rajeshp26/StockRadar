"""
Unit tests for the dividend prediction algorithm (§7.6.1).

10 tests:
  - Quarterly, Monthly, Semi-annual, Annual frequency
  - Minimum history guard (< 4)
  - Boundary: exactly 4 payments
  - Special dividend exclusion
  - All-special graceful degradation
  - Self-feed prevention
  - No data (empty)
  - Suspended payer (deep-past dates suppressed)
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from application.schedulers.market_data_scheduler import estimate_next_ex_date
from fixtures_dividend_pipeline import (
    build_quarterly_8,
    build_monthly_12,
    build_semi_annual_6,
    build_annual_5,
    build_quarterly_4,
    build_quarterly_with_special,
    build_all_special,
    build_self_feed,
    build_insufficient_3,
    build_suspended,
)


def mock_supabase_for(rows):
    """Configure mock supabase to return the given dividend_history rows."""
    ms = MagicMock()
    ms.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows
    return ms


class TestPredictionQuarterly:
    """Frequency band tests."""

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_quarterly_frequency(self, mock_supabase):
        """Quarterly: avg_gap 36-100 → about 3 months after last."""
        rows = build_quarterly_8()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        # result should be in the future relative to today
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_monthly_frequency(self, mock_supabase):
        """Monthly: avg_gap ≤ 35 → about round(avg_gap) days after last."""
        rows = build_monthly_12()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_semi_annual_frequency(self, mock_supabase):
        """Semi-annual: avg_gap 101-200 → +6 months."""
        rows = build_semi_annual_6()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_annual_frequency(self, mock_supabase):
        """Annual: avg_gap > 200 → +1 year."""
        rows = build_annual_5()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()
        # Should be roughly 1 year after most recent (first in list)
        most_recent = date.fromisoformat(rows[0]["ex_dividend_date"])
        diff = (result - most_recent).days
        assert 300 <= diff <= 450


class TestPredictionEdgeCases:
    """Edge case guards."""

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_minimum_history_guard(self, mock_supabase):
        """3 payments → None."""
        rows = build_insufficient_3()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is None

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_boundary_exactly_4(self, mock_supabase):
        """Exactly 4 payments → valid prediction."""
        rows = build_quarterly_4()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_special_dividend_exclusion(self, mock_supabase):
        """Special dividend filtered → same as pure quarterly."""
        rows_plain = build_quarterly_8()
        rows_with_special = build_quarterly_with_special()

        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows_plain
        result_plain = estimate_next_ex_date(1, MagicMock())

        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows_with_special
        result_with = estimate_next_ex_date(1, MagicMock())

        assert result_plain is not None
        assert result_with is not None
        assert result_plain == result_with

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_all_special_graceful_degradation(self, mock_supabase):
        """All-special: falls back to raw rows → still predicts."""
        rows = build_all_special()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_self_feed_prevention(self, mock_supabase):
        """Prediction rows (NULL amount) excluded."""
        rows = build_self_feed()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_empty_result_set(self, mock_supabase):
        """No data → None."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        result = estimate_next_ex_date(1, MagicMock())
        assert result is None

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_suspended_payer_suppressed(self, mock_supabase):
        """Deep-past dates → None (next_date < today)."""
        rows = build_suspended()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is None
