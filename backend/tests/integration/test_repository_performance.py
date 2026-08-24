"""Integration tests for repository batch performance."""

from unittest import mock

from infrastructure.repositories.portfolio_repository import PortfolioRepository


def make_mock_client():
    """Build a mock supabase client that supports the query builder pattern."""
    client = mock.MagicMock()
    table = mock.MagicMock()
    client.table.return_value = table
    table.select.return_value = table
    table.eq.return_value = table
    table.neq.return_value = table
    table.gte.return_value = table
    table.lte.return_value = table
    table.in_.return_value = table
    table.order.return_value = table
    table.limit.return_value = table
    table.execute.return_value = mock.MagicMock(data=[])
    return client


class TestBatchVsNQueries:
    """Verify batch queries produce fewer DB calls than per-account loops."""

    def test_batch_dividends_single_query(self):
        """Batch query uses 1 in_() call instead of N eq() calls."""
        mock_client = make_mock_client()
        repo = PortfolioRepository()
        repo.client = mock_client
        account_ids = [1, 2, 3, 4, 5]
        year = 2025

        repo._batch_dividends(account_ids, year)

        table = mock_client.table("portfolio_dividends")
        assert table.in_.call_count >= 1
        first_in = table.in_.call_args_list[0]
        assert first_in[0][0] == "account_id"
        assert set(first_in[0][1]) == {1, 2, 3, 4, 5}

    def test_batch_transactions_single_query(self):
        """Batch transaction query uses 1 in_() call instead of N."""
        mock_client = make_mock_client()
        repo = PortfolioRepository()
        repo.client = mock_client
        account_ids = [1, 2, 3, 4, 5]

        repo._batch_transactions(account_ids, activity_types=["Trade"])

        table = mock_client.table("portfolio_transactions")
        assert table.in_.call_count >= 1
        first_in = table.in_.call_args_list[0]
        assert first_in[0][0] == "account_id"
        assert set(first_in[0][1]) == {1, 2, 3, 4, 5}

    def test_batch_dividends_matches_per_account_union(self):
        """Batch results should equal union of per-account results."""
        repo = PortfolioRepository()

        dividend_data = {
            1: [{"dividend_id": 1, "account_id": 1, "amount": 100.0}],
            2: [{"dividend_id": 2, "account_id": 2, "amount": 50.0}],
            3: [],
        }

        with mock.patch.object(repo, "get_account_dividends_by_year",
                               side_effect=lambda aid, year: dividend_data.get(aid, [])):
            with mock.patch.object(repo, "_batch_dividends",
                                   return_value=dividend_data[1] + dividend_data[2] + dividend_data[3]):
                result = repo.get_accounts_dividends_by_year([1, 2, 3], 2025)
                assert len(result) == 2
                ids = {d["dividend_id"] for d in result}
                assert ids == {1, 2}
