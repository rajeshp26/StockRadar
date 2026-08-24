"""
Data accuracy validation tests (§7.6.3).

Structural Safety:
  - upcoming_dividend_events and dividend_history are independent

Historical Integrity:
  - Prediction filters NULL amounts via .not_.is_
  - Prediction uses .lte() to exclude future rows

Metrics Pollution:
  - estimate_next_ex_date only queries dividend_history

Expected Results Matrix (§7.6.6):
  - Quarterly prediction → in future
  - Monthly prediction → in future
  - Special exclusion → same as pure quarterly
  - Insufficient history → None
  - Empty history → None
  - Stale cleanup cutoff is today - 14
  - Source identity via unique constraint
"""

import asyncio
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from fixtures_dividend_pipeline import (
    build_insufficient_3,
    build_monthly_12,
    build_quarterly_8,
    build_quarterly_with_special,
)

from application.schedulers.market_data_scheduler import estimate_next_ex_date
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository


class TestStructuralSafety:
    """Tables are independent."""

    def test_upsert_targets_upcoming_table(self):
        """Verify upsert_upcoming_dividend targets upcoming_dividend_events."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        repo = SupabaseFinancialRepository(client=mock_client)
        asyncio.run(repo.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 12, 15), data_source="predicted",
        ))

        table_name = mock_client.table.call_args[0][0]
        assert table_name == "upcoming_dividend_events"
        assert "dividend_history" not in mock_client.table.call_args[0]


class TestMetricsPollution:
    """Events in upcoming table don't affect metrics."""

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_prediction_only_reads_dividend_history(self, mock_supabase):
        """estimate_next_ex_date only queries dividend_history."""
        rows = build_quarterly_8()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())

        table_name = mock_supabase.table.call_args[0][0]
        assert table_name == "dividend_history"
        assert result is not None


class TestHistoricalIntegrity:
    """Regression checks on historical dividend queries."""

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_uses_not_is_null_filter(self, mock_supabase):
        """Prediction uses .not_.is_('dividend_amount', 'null')."""
        rows = build_quarterly_8()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        estimate_next_ex_date(1, MagicMock())

        query_chain = mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_
        query_chain.assert_called_once_with("dividend_amount", "null")

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_uses_lte_filter(self, mock_supabase):
        """Prediction uses .lte('ex_dividend_date', today)."""
        rows = build_quarterly_8()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        estimate_next_ex_date(1, MagicMock())

        query_chain = mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte
        today_str = date.today().isoformat()
        query_chain.assert_called_once_with("ex_dividend_date", today_str)


class TestExpectedResultsMatrix:
    """Expected results matrix from §7.6.6."""

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_matrix_quarterly_prediction(self, mock_supabase):
        """Quarterly → future date."""
        rows = build_quarterly_8()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_matrix_monthly_prediction(self, mock_supabase):
        """Monthly → future date."""
        rows = build_monthly_12()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is not None
        assert result > date.today()

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_matrix_special_exclusion(self, mock_supabase):
        """With special → same as pure quarterly."""
        rows_plain = build_quarterly_8()
        rows_with = build_quarterly_with_special()

        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows_plain
        result_plain = estimate_next_ex_date(1, MagicMock())

        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows_with
        result_with = estimate_next_ex_date(1, MagicMock())

        assert result_plain is not None
        assert result_with is not None
        assert result_plain == result_with

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_matrix_insufficient_history(self, mock_supabase):
        """3 rows → None."""
        rows = build_insufficient_3()
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = rows

        result = estimate_next_ex_date(1, MagicMock())
        assert result is None

    @patch("application.schedulers.market_data_scheduler.supabase")
    def test_matrix_empty_history(self, mock_supabase):
        """Empty → None."""
        mock_supabase.table.return_value.select.return_value.eq.return_value.not_.is_.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value.data = []

        result = estimate_next_ex_date(1, MagicMock())
        assert result is None

    def test_matrix_stale_cleanup_cutoff(self):
        """Cleanup cut off is today - 14 days."""
        mock_client = MagicMock()
        mock_client.table.return_value.delete.return_value.eq.return_value.lt.return_value.execute = MagicMock()

        repo = SupabaseFinancialRepository(client=mock_client)
        asyncio.run(repo.cleanup_stale_events(company_id=1))

        expected_cutoff = (date.today() - timedelta(days=14)).isoformat()
        lt_call = mock_client.table.return_value.delete.return_value.eq.return_value.lt
        lt_call.assert_called_once_with("ex_dividend_date", expected_cutoff)

    def test_matrix_source_identity(self):
        """Unique constraint: on_conflict='company_id,data_source'."""
        mock_client = MagicMock()
        mock_table = MagicMock()
        mock_client.table.return_value = mock_table

        repo = SupabaseFinancialRepository(client=mock_client)
        asyncio.run(repo.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        asyncio.run(repo.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 22), data_source="yfinance",
        ))

        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) == 2
        for call in upsert_calls:
            assert call[1]["on_conflict"] == "company_id,data_source"
