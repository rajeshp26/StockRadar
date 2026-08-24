"""Tests for split handling — replay engine handler, event producer, and integration."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import AccountState, HoldingState, ReplayEngine
from shared.split_utils import get_split_factors_from_rows, parse_split_date, parse_split_factor

# ---------------------------------------------------------------------------
# split_utils unit tests
# ---------------------------------------------------------------------------

class TestParseSplitFactor:
    def test_forward_3_for_1(self):
        assert parse_split_factor("3:1") == 3.0

    def test_forward_2_for_1(self):
        assert parse_split_factor("2:1") == 2.0

    def test_reverse_1_for_5(self):
        assert parse_split_factor("1:5") == 0.2

    def test_reverse_1_for_10(self):
        assert parse_split_factor("1:10") == 0.1

    def test_no_op_1_for_1(self):
        assert parse_split_factor("1:1") == 1.0

    def test_empty_string(self):
        assert parse_split_factor("") == 1.0

    def test_none(self):
        assert parse_split_factor(None) == 1.0

    def test_no_colon(self):
        assert parse_split_factor("3") == 1.0

    def test_invalid_values(self):
        assert parse_split_factor("abc:def") == 1.0

    def test_zero_denominator(self):
        assert parse_split_factor("3:0") == 1.0

    def test_spaces(self):
        assert parse_split_factor(" 3 : 1 ") == 3.0


class TestParseSplitDate:
    def test_date_object(self):
        d = date(2026, 1, 15)
        assert parse_split_date(d) == d

    def test_datetime_object(self):
        dt = datetime(2026, 1, 15, 12, 0, 0)
        assert parse_split_date(dt) == date(2026, 1, 15)

    def test_iso_string(self):
        assert parse_split_date("2026-01-15") == date(2026, 1, 15)

    def test_invalid_string(self):
        with pytest.raises(ValueError):
            parse_split_date("not-a-date")


class TestGetSplitFactorsFromRows:
    def test_empty_rows(self):
        assert get_split_factors_from_rows([]) == {}

    def test_single_forward_split(self):
        rows = [{"company_id": 10, "report_date": date(2026, 6, 1), "split_factor": "3:1"}]
        result = get_split_factors_from_rows(rows)
        assert 10 in result
        assert len(result[10]) == 1
        assert result[10][0] == (date(2026, 6, 1), 3.0)

    def test_multiple_splits_sorted(self):
        rows = [
            {"company_id": 10, "report_date": date(2026, 6, 1), "split_factor": "3:1"},
            {"company_id": 10, "report_date": date(2025, 1, 1), "split_factor": "2:1"},
        ]
        result = get_split_factors_from_rows(rows)
        assert result[10][0] == (date(2025, 1, 1), 2.0)
        assert result[10][1] == (date(2026, 6, 1), 3.0)

    def test_no_op_factor_excluded(self):
        rows = [{"company_id": 10, "report_date": date(2026, 6, 1), "split_factor": "1:1"}]
        result = get_split_factors_from_rows(rows)
        assert 10 not in result

    def test_multiple_companies(self):
        rows = [
            {"company_id": 10, "report_date": date(2026, 6, 1), "split_factor": "3:1"},
            {"company_id": 20, "report_date": date(2026, 7, 1), "split_factor": "1:5"},
        ]
        result = get_split_factors_from_rows(rows)
        assert 10 in result
        assert 20 in result
        assert result[20][0] == (date(2026, 7, 1), 0.2)


# ---------------------------------------------------------------------------
# ReplayEngine._handle_split tests
# ---------------------------------------------------------------------------

class TestHandleSplit:
    def _make_engine(self, mock_client):
        store = EventStore(client=mock_client)
        return ReplayEngine(store)

    def _make_holding(self, company_id=10, symbol="AAPL", qty=10, avg_cost=300, total_cost=3000):
        lots = [{"quantity": Decimal(str(qty)), "cost_per_share": Decimal(str(avg_cost)), "date": date(2025, 1, 1)}]
        return HoldingState(
            company_id=company_id,
            symbol=symbol,
            quantity=Decimal(str(qty)),
            total_cost=Decimal(str(total_cost)),
            average_cost=Decimal(str(avg_cost)),
            trade_date=date(2025, 1, 1),
            lots=lots,
        )

    def test_forward_split(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)
        state.holdings[10] = self._make_holding()

        event = {
            "data": {
                "company_id": 10,
                "split_factor": "3",
                "report_date": "2026-06-01",
            }
        }
        engine._handle_split(state, event)

        h = state.holdings[10]
        assert h.quantity == Decimal("30")
        assert h.average_cost == Decimal("100")
        assert h.total_cost == Decimal("3000")
        assert h.lots[0]["quantity"] == Decimal("30")
        assert h.lots[0]["cost_per_share"] == Decimal("100")

    def test_reverse_split(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)
        state.holdings[10] = self._make_holding(qty=50, avg_cost=10, total_cost=500)

        event = {
            "data": {
                "company_id": 10,
                "split_factor": "0.2",
                "report_date": "2026-06-01",
            }
        }
        engine._handle_split(state, event)

        h = state.holdings[10]
        assert h.quantity == Decimal("10")
        assert h.average_cost == Decimal("50")
        assert h.total_cost == Decimal("500")
        assert h.lots[0]["quantity"] == Decimal("10")
        assert h.lots[0]["cost_per_share"] == Decimal("50")

    def test_no_holding_for_company(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)

        event = {
            "data": {
                "company_id": 99,
                "split_factor": "3",
                "report_date": "2026-06-01",
            }
        }
        engine._handle_split(state, event)
        assert len(state.holdings) == 0

    def test_split_factor_one_noop(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)
        state.holdings[10] = self._make_holding()

        event = {
            "data": {
                "company_id": 10,
                "split_factor": "1",
                "report_date": "2026-06-01",
            }
        }
        engine._handle_split(state, event)

        h = state.holdings[10]
        assert h.quantity == Decimal("10")
        assert h.average_cost == Decimal("300")

    def test_split_factor_zero_noop(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)
        state.holdings[10] = self._make_holding()

        event = {
            "data": {
                "company_id": 10,
                "split_factor": "0",
                "report_date": "2026-06-01",
            }
        }
        engine._handle_split(state, event)

        h = state.holdings[10]
        assert h.quantity == Decimal("10")

    def test_missing_company_id_noop(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)
        state.holdings[10] = self._make_holding()

        event = {"data": {"split_factor": "3", "report_date": "2026-06-01"}}
        engine._handle_split(state, event)

        h = state.holdings[10]
        assert h.quantity == Decimal("10")

    def test_multiple_lots_adjusted(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        state = AccountState(account_id=1)
        holding = HoldingState(
            company_id=10, symbol="AAPL",
            quantity=Decimal("15"), total_cost=Decimal("4500"),
            average_cost=Decimal("300"),
            trade_date=date(2025, 1, 1),
            lots=[
                {"quantity": Decimal("10"), "cost_per_share": Decimal("300"), "date": date(2025, 1, 1)},
                {"quantity": Decimal("5"), "cost_per_share": Decimal("300"), "date": date(2025, 6, 1)},
            ],
        )
        state.holdings[10] = holding

        event = {
            "data": {
                "company_id": 10,
                "split_factor": "3",
                "report_date": "2026-06-01",
            }
        }
        engine._handle_split(state, event)

        h = state.holdings[10]
        assert h.quantity == Decimal("45")
        assert h.lots[0]["quantity"] == Decimal("30")
        assert h.lots[0]["cost_per_share"] == Decimal("100")
        assert h.lots[1]["quantity"] == Decimal("15")
        assert h.lots[1]["cost_per_share"] == Decimal("100")


# ---------------------------------------------------------------------------
# Full replay integration: buy then split
# ---------------------------------------------------------------------------

class TestReplayWithSplit:
    def test_buy_then_split(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(UTC)

        buy_event = {
            "event_type": "transaction_imported",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "account_id": 1,
                "company_id": 10,
                "activity_type": "Trade",
                "symbol": "AAPL",
                "quantity": 10,
                "unit_price": 300.0,
                "net_cash_amount": -3000.0,
                "currency": "USD",
            },
            "created_at": now.isoformat(),
        }
        split_event = {
            "event_type": "split",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "company_id": 10,
                "split_factor": "3",
                "report_date": "2026-06-01",
            },
            "created_at": now.isoformat(),
        }

        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
            data=[buy_event, split_event]
        )

        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, now.date())

        assert 10 in state.holdings
        h = state.holdings[10]
        assert h.quantity == Decimal("30")
        assert h.average_cost == Decimal("100")
        assert h.total_cost == Decimal("3000")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("30")
        assert h.lots[0]["cost_per_share"] == Decimal("100")

    def test_buy_split_sell_fifo(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(UTC)

        buy_event = {
            "event_type": "transaction_imported",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "account_id": 1, "company_id": 10, "activity_type": "Trade",
                "symbol": "AAPL", "quantity": 10, "unit_price": 300.0,
                "net_cash_amount": -3000.0, "currency": "USD",
            },
            "created_at": now.isoformat(),
        }
        split_event = {
            "event_type": "split",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {"company_id": 10, "split_factor": "3", "report_date": "2026-06-01"},
            "created_at": now.isoformat(),
        }
        sell_event = {
            "event_type": "transaction_imported",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "account_id": 1, "company_id": 10, "activity_type": "Trade",
                "symbol": "AAPL", "quantity": -15, "unit_price": 100.0,
                "net_cash_amount": 1500.0, "currency": "USD",
            },
            "created_at": now.isoformat(),
        }

        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
            data=[buy_event, split_event, sell_event]
        )

        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, now.date())

        # After split: 30 shares at $100. Sell 15 → 15 left.
        assert 10 in state.holdings
        h = state.holdings[10]
        assert h.quantity == Decimal("15")
        assert h.average_cost == Decimal("100")
        # Realized gain: sold 15 at $100, cost 15 × $100 = $1500, proceeds $1500 → gain $0
        assert h.realized_gain_loss == Decimal("0")


# ---------------------------------------------------------------------------
# Split event producer tests
# ---------------------------------------------------------------------------

class TestEmitSplitEvents:
    def _make_mock_repo(self, splits_data=None, holdings_data=None):
        repo = MagicMock()
        client = MagicMock()
        repo.client = client

        # Mock splits query
        splits_table = MagicMock()
        splits_table.select.return_value = splits_table
        splits_table.eq.return_value = splits_table
        splits_table.execute.return_value = MagicMock(data=splits_data or [])

        # Mock holdings query
        holdings_table = MagicMock()
        holdings_table.select.return_value = holdings_table
        holdings_table.eq.return_value = holdings_table
        holdings_table.execute.return_value = MagicMock(data=holdings_data or [])

        # Mock update
        update_table = MagicMock()
        update_table.update.return_value = update_table
        update_table.eq.return_value = update_table
        update_table.execute.return_value = MagicMock(data=[])

        def table_side_effect(name):
            if name == "splits":
                return splits_table
            elif name == "portfolio_holdings":
                return holdings_table
            else:
                return update_table

        client.table.side_effect = table_side_effect
        return repo, client

    @patch("infrastructure.repositories.event_store.EventStore")
    @patch("application.jobs.price_ingestion_job.repo")
    def test_emit_events_for_unprocessed_split(self, mock_repo, MockEventStore):
        from application.jobs.price_ingestion_job import _emit_split_events

        splits_data = [{"company_id": 10, "report_date": "2026-06-01", "split_factor": "3:1"}]
        holdings_data = [{"account_id": 7}, {"account_id": 8}]

        mock_repo.client = MagicMock()
        splits_table = MagicMock()
        splits_table.select.return_value = splits_table
        splits_table.eq.return_value = splits_table
        splits_table.execute.return_value = MagicMock(data=splits_data)

        holdings_table = MagicMock()
        holdings_table.select.return_value = holdings_table
        holdings_table.eq.return_value = holdings_table
        holdings_table.execute.return_value = MagicMock(data=holdings_data)

        update_table = MagicMock()
        update_table.update.return_value = update_table
        update_table.eq.return_value = update_table
        update_table.execute.return_value = MagicMock(data=[])

        def table_fn(name):
            if name == "splits":
                return splits_table
            elif name == "portfolio_holdings":
                return holdings_table
            else:
                return update_table

        mock_repo.client.table.side_effect = table_fn

        mock_store = MagicMock()
        MockEventStore.return_value = mock_store

        _emit_split_events()

        assert mock_store.append_events_batch.called
        events = mock_store.append_events_batch.call_args[0][0]
        assert len(events) == 2
        assert events[0]["event_type"] == "split"
        agg_ids = {e["aggregate_id"] for e in events}
        assert agg_ids == {"account_7", "account_8"}
        keys = {e["idempotency_key"] for e in events}
        assert keys == {"split_10_2026-06-01_7", "split_10_2026-06-01_8"}

    @patch("infrastructure.repositories.event_store.EventStore")
    @patch("application.jobs.price_ingestion_job.repo")
    def test_no_unprocessed_splits(self, mock_repo, MockEventStore):
        from application.jobs.price_ingestion_job import _emit_split_events

        mock_repo.client = MagicMock()
        splits_table = MagicMock()
        splits_table.select.return_value = splits_table
        splits_table.eq.return_value = splits_table
        splits_table.execute.return_value = MagicMock(data=[])
        mock_repo.client.table.return_value = splits_table

        mock_store = MagicMock()
        MockEventStore.return_value = mock_store

        _emit_split_events()

        assert not mock_store.append_events_batch.called

    @patch("infrastructure.repositories.event_store.EventStore")
    @patch("application.jobs.price_ingestion_job.repo")
    def test_no_accounts_holding_company(self, mock_repo, MockEventStore):
        from application.jobs.price_ingestion_job import _emit_split_events

        splits_data = [{"company_id": 10, "report_date": "2026-06-01", "split_factor": "3:1"}]

        mock_repo.client = MagicMock()
        splits_table = MagicMock()
        splits_table.select.return_value = splits_table
        splits_table.eq.return_value = splits_table
        splits_table.execute.return_value = MagicMock(data=splits_data)

        holdings_table = MagicMock()
        holdings_table.select.return_value = holdings_table
        holdings_table.eq.return_value = holdings_table
        holdings_table.execute.return_value = MagicMock(data=[])

        def table_fn(name):
            if name == "splits":
                return splits_table
            elif name == "portfolio_holdings":
                return holdings_table
            else:
                return MagicMock()

        mock_repo.client.table.side_effect = table_fn

        mock_store = MagicMock()
        MockEventStore.return_value = mock_store

        _emit_split_events()

        assert not mock_store.append_events_batch.called

    @patch("infrastructure.repositories.event_store.EventStore")
    @patch("application.jobs.price_ingestion_job.repo")
    def test_no_op_factor_skipped(self, mock_repo, MockEventStore):
        from application.jobs.price_ingestion_job import _emit_split_events

        splits_data = [{"company_id": 10, "report_date": "2026-06-01", "split_factor": "1:1"}]

        mock_repo.client = MagicMock()
        splits_table = MagicMock()
        splits_table.select.return_value = splits_table
        splits_table.eq.return_value = splits_table
        splits_table.execute.return_value = MagicMock(data=splits_data)
        mock_repo.client.table.return_value = splits_table

        mock_store = MagicMock()
        MockEventStore.return_value = mock_store

        _emit_split_events()

        assert not mock_store.append_events_batch.called
