"""Unit tests for batched repository methods — chunking, fallback, edge cases."""

from unittest import mock

from infrastructure.repositories.portfolio_repository import PortfolioRepository, _batch_execute


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


class TestBatchHelper:
    """Tests for the _batch_execute helper function."""

    def test_batch_execute_empty_list(self):
        """Empty list returns empty list, no functions called."""
        batch_fn = mock.Mock()
        single_fn = mock.Mock()
        result = _batch_execute([], batch_fn, single_fn)
        assert result == []
        batch_fn.assert_not_called()
        single_fn.assert_not_called()

    def test_batch_execute_single_chunk(self):
        """Small number of ids fits in one chunk."""
        batch_fn = mock.Mock(return_value=[{"id": 1}, {"id": 2}])
        single_fn = mock.Mock()
        result = _batch_execute([1, 2], batch_fn, single_fn, batch_size=500)
        assert result == [{"id": 1}, {"id": 2}]
        batch_fn.assert_called_once_with([1, 2])
        single_fn.assert_not_called()

    def test_batch_execute_chunking(self):
        """More ids than batch size splits into multiple chunks."""
        batch_fn = mock.Mock(return_value=[])
        single_fn = mock.Mock(return_value=[])
        account_ids = list(range(1, 1501))

        _batch_execute(account_ids, batch_fn, single_fn, batch_size=500)
        assert batch_fn.call_count == 3

        calls = batch_fn.call_args_list
        assert calls[0][0][0] == list(range(1, 501))
        assert calls[1][0][0] == list(range(501, 1001))
        assert calls[2][0][0] == list(range(1001, 1501))

    def test_batch_execute_exactly_boundary(self):
        """Exactly 500 ids should produce 1 chunk."""
        batch_fn = mock.Mock(return_value=[])
        single_fn = mock.Mock(return_value=[])
        _batch_execute(list(range(500)), batch_fn, single_fn, batch_size=500)
        assert batch_fn.call_count == 1

    def test_batch_execute_boundary_plus_one(self):
        """501 ids should produce 2 chunks."""
        batch_fn = mock.Mock(return_value=[])
        single_fn = mock.Mock(return_value=[])
        _batch_execute(list(range(501)), batch_fn, single_fn, batch_size=500)
        assert batch_fn.call_count == 2

    def test_fallback_on_batch_failure(self):
        """When a chunk fails, individual queries are used as fallback."""
        call_count = [0]

        def batch_fn(chunk):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Batch failed")
            return [{"id": aid} for aid in chunk]

        single_fn = mock.Mock(side_effect=lambda aid: [{"id": aid}])
        result = _batch_execute([1, 2, 3, 4, 5, 6], batch_fn, single_fn, batch_size=3)
        # First chunk (3 ids) failed -> 3 individual calls
        # Second chunk (3 ids) succeeded -> 3 from batch
        assert len(result) == 6
        assert single_fn.call_count == 3

    def test_partial_fallback_returns_valid_chunks(self):
        """Failed chunk should fall back, but successful chunks still return data."""
        def batch_fn(chunk):
            if 1 in chunk:
                raise Exception("Bad chunk")
            return [{"id": aid} for aid in chunk]

        single_fn = mock.Mock(side_effect=lambda aid: [{"id": aid}])
        result = _batch_execute([1, 2, 3, 4], batch_fn, single_fn, batch_size=2)
        # Chunk [1,2] fails -> 2 individual calls
        # Chunk [3,4] succeeds -> returns from batch
        ids = {r["id"] for r in result}
        assert ids == {1, 2, 3, 4}
        assert single_fn.call_count == 2


class TestPortfolioBatchMethods:
    """Tests for the repository-level batch methods."""

    def test_batch_dividends_calls_in_query(self):
        """get_accounts_dividends_by_year uses in_() filter."""
        mock_client = make_mock_client()
        repo = PortfolioRepository()
        repo.client = mock_client
        account_ids = [1, 2, 3]

        repo._batch_dividends(account_ids, 2025)

        table = mock_client.table("portfolio_dividends")
        assert table.select.called
        table.in_.assert_called_once()
        assert table.in_.call_args[0][0] == "account_id"
        assert set(table.in_.call_args[0][1]) == {1, 2, 3}

    def test_batch_transactions_calls_in_query(self):
        """get_accounts_transactions uses in_() filter."""
        mock_client = make_mock_client()
        repo = PortfolioRepository()
        repo.client = mock_client
        account_ids = [1, 2, 3]

        repo._batch_transactions(account_ids, activity_types=["Trade"])

        table = mock_client.table("portfolio_transactions")
        assert table.select.called
        assert table.in_.call_count == 2  # account_id + activity_type
        first_in_call = table.in_.call_args_list[0]
        assert first_in_call[0][0] == "account_id"
        assert set(first_in_call[0][1]) == {1, 2, 3}

    def test_batch_dividends_with_none_year(self):
        """fiscal_year=None -> no eq filter applied."""
        mock_client = make_mock_client()
        repo = PortfolioRepository()
        repo.client = mock_client

        repo._batch_dividends([1, 2], None)

        table = mock_client.table("portfolio_dividends")
        assert table.in_.called
        table.eq.assert_not_called()

    def test_batch_dividends_with_year(self):
        """fiscal_year provided -> eq filter applied."""
        mock_client = make_mock_client()
        repo = PortfolioRepository()
        repo.client = mock_client

        repo._batch_dividends([1, 2], 2025)

        table = mock_client.table("portfolio_dividends")
        assert table.in_.called
        table.eq.assert_called_with("fiscal_year", 2025)
