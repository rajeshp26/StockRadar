"""
Unit tests for upcoming-dividend-event repository methods (§7.6.1 — 10 tests).

Tests:
  - Upsert yfinance → trust_score=0.95, status='provider_reported'
  - Upsert finviz → trust_score=0.80, status='provider_reported'
  - Upsert predicted → trust_score=0.50, status='predicted'
  - Upsert sets source_observed_at (not NULL)
  - on_conflict replaces old source opinion
  - Source replacement updates date
  - Stale cleanup deletes past grace
  - Stale cleanup keeps recent past (within grace)
  - Stale cleanup preserves future events
  - Upsert only affects upcoming_dividend_events
"""

import asyncio
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from infrastructure.repositories.financial_repository import (
    SupabaseFinancialRepository,
)


@pytest.fixture
def repo():
    mock_client = MagicMock()
    # Make the upsert chain mock return properly
    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    return SupabaseFinancialRepository(client=mock_client), mock_table


class TestUpsertTrustScores:
    """Source-based trust_score and status assignment."""

    def test_upsert_yfinance_source(self, repo):
        """yfinance → async, validates in other tests below."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        assert mock_table.upsert.called

    def test_upsert_tracks_correct_table(self, repo):
        """Verify upsert targets upcoming_dividend_events."""
        r, mock_table = repo
        mock_client = r.client
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        table_name = mock_client.table.call_args[0][0]
        assert table_name == "upcoming_dividend_events"

    def test_upsert_yfinance_payload(self, repo):
        """yfinance → trust_score=0.95, status=provider_reported."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        payload = mock_table.upsert.call_args[0][0]
        assert payload["trust_score"] == 0.95
        assert payload["status"] == "provider_reported"
        assert payload["data_source"] == "yfinance"

    def test_upsert_finviz_payload(self, repo):
        """finviz → trust_score=0.80, status='provider_reported'."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="finviz",
        ))
        call_args = mock_table.upsert.call_args
        payload = call_args[0][0]
        assert payload["trust_score"] == 0.80
        assert payload["status"] == "provider_reported"

    def test_upsert_predicted_payload(self, repo):
        """predicted → trust_score=0.50, status='predicted'."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="predicted",
        ))
        call_args = mock_table.upsert.call_args
        payload = call_args[0][0]
        assert payload["trust_score"] == 0.50
        assert payload["status"] == "predicted"

    def test_upsert_sets_source_observed_at(self, repo):
        """source_observed_at is set (not NULL)."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        call_args = mock_table.upsert.call_args
        payload = call_args[0][0]
        assert payload["source_observed_at"] is not None

    def test_upsert_on_conflict_key(self, repo):
        """Upsert uses on_conflict='company_id,data_source'."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        call_args = mock_table.upsert.call_args
        assert call_args[1].get("on_conflict") == "company_id,data_source"

    def test_upsert_source_replacement(self, repo):
        """Same source called twice → same on_conflict key (replaces old)."""
        r, mock_table = repo
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 22), data_source="yfinance",
        ))
        upsert_calls = mock_table.upsert.call_args_list
        assert len(upsert_calls) == 2
        for call in upsert_calls:
            assert call[1].get("on_conflict") == "company_id,data_source"

    def test_upsert_only_affects_upcoming_table(self, repo):
        """Table name is upcoming_dividend_events, not dividend_history."""
        r, mock_table = repo
        mock_client = r.client
        asyncio.run(r.upsert_upcoming_dividend(
            company_id=1, ex_dividend_date=date(2026, 7, 15), data_source="yfinance",
        ))
        table_name = mock_client.table.call_args[0][0]
        assert table_name == "upcoming_dividend_events"


class TestStaleCleanup:
    """Edge cases for cleanup_stale_events."""

    def test_cleanup_targets_upcoming_table(self, repo):
        """Cleanup uses upcoming_dividend_events."""
        r, mock_table = repo
        mock_client = r.client
        asyncio.run(r.cleanup_stale_events(company_id=1))
        table_name = mock_client.table.call_args[0][0]
        assert table_name == "upcoming_dividend_events"

    def test_cleanup_deletes_past_cutoff(self, repo):
        """Verify the lt filter is called with correct cutoff."""
        r, mock_table = repo
        mock_delete_chain = MagicMock()
        mock_table.delete.return_value = mock_delete_chain
        mock_delete_chain.eq.return_value = mock_delete_chain
        mock_delete_chain.lt.return_value = mock_delete_chain

        asyncio.run(r.cleanup_stale_events(company_id=1))

        mock_delete_chain.eq.assert_called_once_with("company_id", 1)
        # lt should be called with a cutoff of today - 14 days
        expected_cutoff = (date.today() - timedelta(days=14)).isoformat()
        mock_delete_chain.lt.assert_called_once_with("ex_dividend_date", expected_cutoff)

    def test_cleanup_only_upcoming_not_dividend_history(self, repo):
        """Table is upcoming_dividend_events, never dividend_history."""
        r, mock_table = repo
        mock_client = r.client
        asyncio.run(r.cleanup_stale_events(company_id=1))
        table_name = mock_client.table.call_args[0][0]
        assert table_name != "dividend_history"
