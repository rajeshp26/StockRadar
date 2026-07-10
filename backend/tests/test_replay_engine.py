"""Tests for the event-replay engine."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import (
    ReplayEngine, _parse_account_id, AccountState, HoldingState,
)


class TestParseAccountId:
    def test_valid_account_id(self):
        assert _parse_account_id("account_42") == 42

    def test_invalid_prefix(self):
        assert _parse_account_id("user_42") is None

    def test_missing_number(self):
        assert _parse_account_id("account_") is None

    def test_non_numeric(self):
        assert _parse_account_id("account_abc") is None

    def test_empty(self):
        assert _parse_account_id("") is None


class TestReplayState:
    def test_empty_replay(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[])
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, date(2026, 7, 6))
        assert state.account_id == 1
        assert state.cash_balance == Decimal("0")
        assert state.net_deposits == Decimal("0")
        assert len(state.holdings) == 0

    def test_single_buy_event(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1,
                    "company_id": 10,
                    "activity_type": "Trade",
                    "symbol": "AAPL",
                    "quantity": 50,
                    "unit_price": 145.00,
                    "net_cash_amount": -7250.00,
                    "currency": "USD",
                },
                "created_at": now.isoformat(),
            }
        ])
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, now.date())

        assert state.cash_balance == Decimal("-7250.00")
        assert len(state.holdings) == 1
        assert 10 in state.holdings
        h = state.holdings[10]
        assert h.quantity == Decimal("50")
        assert h.average_cost == Decimal("145")
        assert h.total_cost == Decimal("7250")

    def test_sell_reduces_quantity(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)

        def mock_execute():
            return MagicMock

        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": 10,
                    "activity_type": "Trade", "symbol": "AAPL",
                    "quantity": 50, "unit_price": 145.00,
                    "net_cash_amount": -7250.00, "currency": "USD",
                },
                "created_at": now.isoformat(),
            },
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": 10,
                    "activity_type": "Trade", "symbol": "AAPL",
                    "quantity": -20, "unit_price": 294.30,
                    "net_cash_amount": 5886.00, "currency": "USD",
                },
                "created_at": now.isoformat(),
            },
        ])
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, now.date())

        assert state.cash_balance == Decimal("-1364.00")  # -7250 + 5886
        assert state.holdings[10].quantity == Decimal("30")  # 50 - 20

    def test_deposit_updates_net_deposits(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": None,
                    "activity_type": "MoneyMovement", "symbol": None,
                    "quantity": None, "unit_price": None,
                    "net_cash_amount": 5000.00, "currency": "CAD",
                },
                "created_at": now.isoformat(),
            }
        ])
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, now.date())
        assert state.cash_balance == Decimal("5000.00")
        assert state.net_deposits == Decimal("5000.00")

    def test_dividend_affects_cash_not_holdings(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": 10,
                    "activity_type": "Dividend", "symbol": "AAPL",
                    "quantity": None, "unit_price": None,
                    "net_cash_amount": 75.00, "currency": "USD",
                },
                "created_at": now.isoformat(),
            }
        ])
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, now.date())
        assert state.cash_balance == Decimal("75.00")
        assert len(state.holdings) == 0  # Dividend doesn't create holdings

    def test_multi_account_filtering(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "data": {
                    "account_id": 1, "activity_type": "Deposit",
                    "net_cash_amount": 10000.00,
                },
                "created_at": now.isoformat(),
            },
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_2",
                "data": {
                    "account_id": 2, "activity_type": "Deposit",
                    "net_cash_amount": 5000.00,
                },
                "created_at": now.isoformat(),
            },
        ])
        engine = ReplayEngine(store)
        state_1 = engine.replay_to_date(1, now.date())
        state_2 = engine.replay_to_date(2, now.date())
        assert state_1.cash_balance == Decimal("10000.00")
        assert state_2.cash_balance == Decimal("5000.00")


class TestReplayBuildSnapshot:
    def test_build_snapshot_from_replay(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": 10,
                    "activity_type": "Trade", "symbol": "AAPL",
                    "quantity": 50, "unit_price": 145.00,
                    "net_cash_amount": -7250.00, "currency": "USD",
                },
                "created_at": now.isoformat(),
            }
        ])
        engine = ReplayEngine(store)
        prices = {10: {"price": 294.30, "price_date": now.date()}}
        snapshot = engine.build_snapshot_from_replay(
            account_id=1,
            target_date=now.date(),
            prices_by_company=prices,
            account_currency="CAD",
        )
        assert snapshot["holdings_market_value"] == 50 * 294.30
        assert snapshot["cash_balance"] == -7250.00
        assert snapshot["total_value"] == 50 * 294.30 - 7250.00
        assert snapshot["cost_basis"] == 7250.00

    def test_compare_with_snapshot_match(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": 10,
                    "activity_type": "Trade", "symbol": "AAPL",
                    "quantity": 50, "unit_price": 145.00,
                    "net_cash_amount": -7250.00, "currency": "USD",
                },
                "created_at": now.isoformat(),
            }
        ])
        engine = ReplayEngine(store)
        prices = {10: {"price": 294.30, "price_date": now.date()}}
        stored = {
            "total_value": 50 * 294.30 - 7250.00,
            "holdings_market_value": 50 * 294.30,
            "cash_balance": -7250.00,
            "cost_basis": 7250.00,
            "net_deposits": 0.0,
        }
        result = engine.compare_with_snapshot(
            account_id=1,
            snapshot_date=now.date(),
            stored_snapshot=stored,
            prices_by_company=prices,
        )
        assert result.match is True
        assert len(result.differences) == 0

    def test_compare_with_snapshot_mismatch(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(timezone.utc)
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=[
            {
                "event_type": "transaction_imported",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "account_id": 1, "company_id": 10,
                    "activity_type": "Trade", "symbol": "AAPL",
                    "quantity": 50, "unit_price": 145.00,
                    "net_cash_amount": -7250.00, "currency": "USD",
                },
                "created_at": now.isoformat(),
            }
        ])
        engine = ReplayEngine(store)
        prices = {10: {"price": 294.30, "price_date": now.date()}}
        stored = {
            "total_value": 0.0,
            "holdings_market_value": 0.0,
            "cash_balance": 0.0,
            "cost_basis": 0.0,
        }
        result = engine.compare_with_snapshot(
            account_id=1,
            snapshot_date=now.date(),
            stored_snapshot=stored,
            prices_by_company=prices,
        )
        assert result.match is False
        assert len(result.differences) > 0
        assert "total_value" in result.differences[0]
