from datetime import date
from unittest.mock import MagicMock, patch

import pytest


class TestGetCompaniesWithUpcomingEarnings:
    """Verify the .or_('security_type.eq.stock,security_type.is.null') filter."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_supabase_client):
        self.client = mock_supabase_client
        self.table = self.client.table.return_value

    def _make_repo(self):
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        return SupabaseFinancialRepository(client=self.client)

    async def test_stock_filter_applies_or_with_null(self):
        repo = self._make_repo()
        self.table.execute.return_value = MagicMock(data=[])

        result = await repo.get_companies_with_upcoming_earnings(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        self.table.or_.assert_called_once_with(
            "security_type.eq.stock,security_type.is.null"
        )
        assert result == []

    async def test_returns_data_correctly(self):
        repo = self._make_repo()
        fake_data = [
            {"company_id": 1, "ticker_symbol": "AAPL", "next_earnings_date": "2025-01-30"},
            {"company_id": 2, "ticker_symbol": "MSFT", "next_earnings_date": "2025-01-28"},
        ]
        self.table.execute.return_value = MagicMock(data=fake_data)

        result = await repo.get_companies_with_upcoming_earnings(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        assert len(result) == 2
        assert result[0]["ticker_symbol"] == "AAPL"

    async def test_empty_result_returns_empty_list(self):
        repo = self._make_repo()
        self.table.execute.return_value = MagicMock(data=None)

        result = await repo.get_companies_with_upcoming_earnings(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31),
        )

        assert result == []

    async def test_propagates_exception(self):
        repo = self._make_repo()
        self.table.execute.side_effect = Exception("DB connection failed")

        with pytest.raises(Exception, match="DB connection failed"):
            await repo.get_companies_with_upcoming_earnings(
                start_date=date(2025, 1, 1),
                end_date=date(2025, 1, 31),
            )


class TestUpsertSplitsCategoricalConflict:
    """Verify upsert_splits never calls log_conflict for split_factor/reverse_split."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_supabase_client):
        self.client = mock_supabase_client
        self.table = self.client.table.return_value

    def _make_repo(self):
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        return SupabaseFinancialRepository(client=self.client)

    async def test_no_log_conflict_called_for_categorical_fields(self):
        repo = self._make_repo()
        existing = MagicMock()
        existing.data = {
            "split_factor": "2:1",
            "reverse_split": False,
            "data_source": "defeatbeta",
        }
        self.table.single.return_value = existing
        self.table.execute.return_value = existing

        rows = [
            {
                "company_id": 1,
                "report_date": "2025-01-01",
                "split_factor": "3:1",
                "reverse_split": True,
                "data_source": "yfinance",
            }
        ]

        with patch.object(repo, "log_conflict") as mock_log:
            result = await repo.upsert_splits(rows)

            mock_log.assert_not_called()

        assert result == {"count": 1}

    async def test_identical_values_no_log(self):
        repo = self._make_repo()
        existing = MagicMock()
        existing.data = {
            "split_factor": "2:1",
            "reverse_split": False,
            "data_source": "defeatbeta",
        }
        self.table.single.return_value = existing
        self.table.execute.return_value = existing

        rows = [
            {
                "company_id": 1,
                "report_date": "2025-01-01",
                "split_factor": "2:1",
                "reverse_split": False,
                "data_source": "defeatbeta",
            }
        ]

        with patch.object(repo, "log_conflict") as mock_log:
            result = await repo.upsert_splits(rows)

            mock_log.assert_not_called()

        assert result == {"count": 1}


class TestUpsertPriceHistoryNullCloseFilter:
    """Regression: null-OHLC provider rows must never reach the DB
    (close_price is NOT NULL; delisted/suspended days report null prices)."""

    @pytest.fixture(autouse=True)
    def _setup(self, mock_supabase_client, monkeypatch):
        from config import settings
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        monkeypatch.setattr(settings, "ENABLE_CONFLICT_DETECTION", False)
        self.repo = SupabaseFinancialRepository(client=mock_supabase_client)
        self.client = mock_supabase_client

    async def test_drops_rows_with_null_close_price(self):
        rows = [
            {"company_id": 1, "price_date": date(2026, 7, 31), "open_price": 10.0,
             "close_price": 11.0, "high_price": 12.0, "low_price": 9.0,
             "volume": 100, "data_source": "yfinance"},
            {"company_id": 1, "price_date": date(2026, 8, 31), "open_price": None,
             "close_price": None, "high_price": None, "low_price": None,
             "volume": 0, "data_source": "yfinance"},
        ]

        result = await self.repo.upsert_price_history(rows)

        assert result == {"count": 1}
        payload = self.client.table.return_value.upsert.call_args[0][0]
        assert len(payload) == 1
        assert payload[0]["price_date"] == "2026-07-31"

    async def test_all_null_close_prices_upserts_nothing(self):
        rows = [
            {"company_id": 1, "price_date": date(2026, 7, 31),
             "open_price": None, "close_price": None, "high_price": None,
             "low_price": None, "volume": 0, "data_source": "yfinance"},
        ]

        result = await self.repo.upsert_price_history(rows)

        assert result == {"count": 0}
        self.client.table.assert_not_called()
