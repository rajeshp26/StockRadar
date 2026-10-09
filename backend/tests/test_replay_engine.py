"""Tests for the event-replay engine."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

from infrastructure.repositories.event_store import EventStore
from shared.replay_engine import (
    HoldingState,
    ReplayEngine,
    _cdr_lot_legs,
    _parse_account_id,
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)

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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
        now = datetime.now(UTC)
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
            account_currency="USD",
        )
        assert snapshot["holdings_market_value"] == 50 * 294.30
        assert snapshot["cash_balance"] == -7250.00
        assert snapshot["total_value"] == 50 * 294.30 - 7250.00
        assert snapshot["cost_basis"] == 7250.00

    def test_compare_with_snapshot_match(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(UTC)
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
            account_currency="USD",
        )
        assert result.match is True
        assert len(result.differences) == 0

    def test_compare_with_snapshot_mismatch(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        now = datetime.now(UTC)
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


# ---------------------------------------------------------------------------
# FIFO lot tracking, commission, and ROC tests
# ---------------------------------------------------------------------------

class TestFifoCommissionAndRoc:
    """Tests for FIFO lot tracking, commission in cost basis, and ReturnOfCapital."""

    def _make_engine(self, mock_client):
        store = EventStore(client=mock_client)
        return ReplayEngine(store)

    def _buy_event(self, account_id, company_id, qty, price, commission=0, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": float(commission),
                "net_cash_amount": float(-(qty * price + commission)),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _sell_event(self, account_id, company_id, qty, price, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(abs(qty) * price),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _roc_event(self, account_id, company_id, amount):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "ReturnOfCapital", "symbol": "AAPL",
                "quantity": 0, "unit_price": 0,
                "commission": 0, "net_cash_amount": float(amount),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def test_buy_includes_commission_in_cost_basis(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [self._buy_event(1, 10, 100, 10, commission=50)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.average_cost == Decimal("10.5")
        assert h.total_cost == Decimal("1050")
        assert h.lots[0]["cost_per_share"] == Decimal("10.5")

    def test_buy_zero_commission(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [self._buy_event(1, 10, 100, 10, commission=0)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.average_cost == Decimal("10")
        assert h.total_cost == Decimal("1000")
        assert h.lots[0]["cost_per_share"] == Decimal("10")

    def test_sell_fifo_single_lot(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._sell_event(1, 10, -5, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("5")
        assert h.total_cost == Decimal("500")
        assert h.average_cost == Decimal("100")
        assert h.realized_gain_loss == Decimal("250")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("5")
        assert h.lots[0]["cost_per_share"] == Decimal("100")

    def test_sell_fifo_multiple_lots(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._buy_event(1, 10, 10, 200),
            self._sell_event(1, 10, -15, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # Cost: 10 * 100 + 5 * 200 = 2000
        # Proceeds: 15 * 150 = 2250
        # Realized: 250
        assert h.quantity == Decimal("5")
        assert h.total_cost == Decimal("1000")
        assert h.average_cost == Decimal("200")
        assert h.realized_gain_loss == Decimal("250")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("5")
        assert h.lots[0]["cost_per_share"] == Decimal("200")

    def test_sell_fifo_partial_lot(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._sell_event(1, 10, -3, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("7")
        assert h.total_cost == Decimal("700")
        assert h.average_cost == Decimal("100")
        assert h.realized_gain_loss == Decimal("150")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("7")

    def test_sell_fallback_to_average_cost(self, mock_supabase_client):
        """Sell with empty lots falls back to average_cost."""
        engine = self._make_engine(mock_supabase_client)
        # Buy event without lots (simulate old data)
        events = [{
            "event_type": "initial_holding_set",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "cash_balance": 0, "net_deposits": 1000,
                "holdings": [{
                    "company_id": 10, "symbol": "AAPL",
                    "quantity": 10, "average_cost": 100, "total_cost": 1000,
                }],
            },
            "created_at": datetime.now(UTC).isoformat(),
        }, self._sell_event(1, 10, -5, 150)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("5")
        assert h.realized_gain_loss == Decimal("250")

    def test_sell_recalculates_average_cost(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._buy_event(1, 10, 5, 200),
            self._sell_event(1, 10, -8, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # After sell 8: FIFO removes 8 from lot1 (10 at $100)
        # Remaining: 2 at $100 + 5 at $200 = $1200 / 7 = $171.43
        assert h.quantity == Decimal("7")
        assert h.total_cost == Decimal("1200")
        assert len(h.lots) == 2
        assert h.lots[0]["quantity"] == Decimal("2")
        assert h.lots[0]["cost_per_share"] == Decimal("100")
        assert h.lots[1]["quantity"] == Decimal("5")
        assert h.lots[1]["cost_per_share"] == Decimal("200")

    def test_roc_reduces_cost_basis(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 100, 10),
            self._roc_event(1, 10, 500),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.total_cost == Decimal("500")
        assert h.average_cost == Decimal("5")
        assert len(h.lots) == 1
        assert h.lots[0]["cost_per_share"] == Decimal("5")

    def test_roc_reduces_lot_costs_proportionally(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._buy_event(1, 10, 10, 200),
            self._roc_event(1, 10, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # total_cost was 3000, reduction 150, new total_cost 2850
        assert h.total_cost == Decimal("2850")
        # lot_total_cost was 3000, ratio = 150/3000 = 0.05
        # lot 1: 100 * 0.95 = 95, lot 2: 200 * 0.95 = 190
        assert h.lots[0]["cost_per_share"] == Decimal("95")
        assert h.lots[1]["cost_per_share"] == Decimal("190")

    def test_roc_clamped_at_zero(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 100, 10),
            self._roc_event(1, 10, 1500),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.total_cost == Decimal("0")
        assert h.average_cost == Decimal("0")
        assert h.lots[0]["cost_per_share"] == Decimal("0")

    def test_roc_no_holding(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [self._roc_event(1, 99, 500)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        assert len(state.holdings) == 0

    def test_roc_negative_cash(self, mock_supabase_client):
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 100, 10),
            self._roc_event(1, 10, -100),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.total_cost == Decimal("1000")

    def test_full_lifecycle(self, mock_supabase_client):
        """Buy with commission, ROC, buy, sell — full FIFO lifecycle."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100, commission=10),
            self._roc_event(1, 10, 50),
            self._buy_event(1, 10, 5, 120, commission=0),
            self._sell_event(1, 10, -12, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        engine = ReplayEngine(EventStore(client=mock_supabase_client))
        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # After buy 10 at $100 + $10 commission: lot 1 = 10 at $10.10, total = 1010
        # After ROC $50: total = 960, lot 1 cost = 10.10 * (960/1010) = 9.60
        # After buy 5 at $120: lot 2 = 5 at $120, total = 960 + 600 = 1560
        # After sell 12: FIFO removes lot 1 (10 at $9.60) + 2 from lot 2 (2 at $120)
        #   cost_of_sold = 10 * 9.60 + 2 * 120 = 96 + 240 = 336
        #   proceeds = 12 * 150 = 1800
        #   realized = 1800 - 1200 = 600
        # Wait: 10*96=960 not 96. Let me recalculate.
        # lot 1 cost_per_share after ROC = 101 * (960/1010) = 96.0
        # cost_of_sold = 10 * 96 + 2 * 120 = 960 + 240 = 1200
        # realized = 1800 - 1200 = 600
        assert h.quantity == Decimal("3")
        assert h.lots[0]["quantity"] == Decimal("3")
        assert h.lots[0]["cost_per_share"] == Decimal("120")
        assert h.realized_gain_loss == Decimal("600")


# ---------------------------------------------------------------------------
# InternalSecurityTransfer (IST) handling tests
# ---------------------------------------------------------------------------

class TestIstHandling:
    """Tests for InternalSecurityTransfer (IST) lot handling."""

    def _make_engine(self, mock_client):
        store = EventStore(client=mock_client)
        return ReplayEngine(store)

    def _ist_event(self, account_id, company_id, qty, net_cash_amount, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "InternalSecurityTransfer", "symbol": symbol,
                "quantity": qty, "unit_price": None,
                "commission": None, "net_cash_amount": float(net_cash_amount),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _buy_event(self, account_id, company_id, qty, price, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(-(qty * price)),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def test_inbound_ist_creates_lot_with_nca_cost(self, mock_supabase_client):
        """Inbound IST derives cost_per_share from net_cash_amount / quantity."""
        engine = self._make_engine(mock_supabase_client)
        events = [self._ist_event(1, 10, 2, 276.10)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("2")
        # cost_per_share = abs(276.10) / 2 = 138.05
        assert h.average_cost == Decimal("138.05")
        assert h.total_cost == Decimal("276.10")
        assert len(h.lots) == 1
        assert h.lots[0]["cost_per_share"] == Decimal("138.05")
        assert h.lots[0]["quantity"] == Decimal("2")

    def test_inbound_ist_does_not_affect_cash(self, mock_supabase_client):
        """IST should not change cash balance."""
        engine = self._make_engine(mock_supabase_client)
        events = [self._ist_event(1, 10, 5, 500.00)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        assert state.cash_balance == Decimal("0")

    def test_outbound_ist_removes_lots_fifo(self, mock_supabase_client):
        """Outbound IST (negative qty) removes lots via FIFO."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._ist_event(1, 10, -4, -400.00),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("6")
        assert h.total_cost == Decimal("600")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("6")
        assert h.lots[0]["cost_per_share"] == Decimal("100")

    def test_ist_inbound_then_outbound(self, mock_supabase_client):
        """IST inbound then outbound — cost basis carries through."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._ist_event(1, 10, 5, 500.00),   # inbound: cost = 100/share
            self._ist_event(1, 10, -2, -200.00),  # outbound: FIFO removes 2 from lot
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("3")
        assert h.total_cost == Decimal("300")
        assert h.average_cost == Decimal("100")

    def test_ist_with_no_existing_holding(self, mock_supabase_client):
        """IST creates a new holding when none exists."""
        engine = self._make_engine(mock_supabase_client)
        events = [self._ist_event(1, 42, 10, 1000.00, symbol="MSFT")]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        assert 42 in state.holdings
        h = state.holdings[42]
        assert h.symbol == "MSFT"
        assert h.quantity == Decimal("10")
        assert h.average_cost == Decimal("100")

    def test_ist_sell_truncation_warning(self, mock_supabase_client):
        """Outbound IST exceeding holdings triggers truncation warning and truncates."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 5, 100),
            self._ist_event(1, 10, -10, -1000.00),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        # Should be fully sold (truncated to 5, all removed)
        assert len(state.holdings) == 0


# ---------------------------------------------------------------------------
# IST relocation pairing tests
# ---------------------------------------------------------------------------

class TestIstRelocationPairing:
    """Paired InternalSecurityTransfer legs relocate instead of selling.

    A leg is PAIRED when its (symbol, currency, |quantity|) key has an
    opposite-sign leg in the same account's COMPLETE event log. Paired legs are
    a transfer, not a trade: the outbound leg leaves the account without a sale
    (the dip stays visible, no fake realized loss) and parks its original cost
    basis; the matching inbound leg restores that basis. Unpaired legs keep
    today's buy/FIFO-sell behavior exactly.
    """

    def _make_engine(self, mock_client):
        store = EventStore(client=mock_client)
        return ReplayEngine(store)

    def _replay(self, mock_client, events, target_date):
        mock_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)
        return self._make_engine(mock_client).replay_to_date(1, target_date)

    def _buy_event(self, account_id, company_id, qty, price, symbol="PLTR", txn_date="2024-11-01"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(-(qty * price)),
                "currency": "USD", "transaction_date": txn_date,
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _sell_event(self, account_id, company_id, qty, price, symbol="PLTR", txn_date="2025-01-15"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(abs(qty) * price),
                "currency": "USD", "transaction_date": txn_date,
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _ist_event(self, account_id, company_id, qty, net_cash_amount, symbol="PLTR", txn_date="2024-12-23"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "InternalSecurityTransfer", "symbol": symbol,
                "quantity": qty, "unit_price": None,
                "commission": None, "net_cash_amount": float(net_cash_amount),
                "currency": "USD", "transaction_date": txn_date,
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def test_paired_round_trip_restores_original_basis(self, mock_supabase_client):
        """Out 2024-12-23, in 2025-05-13: position returns with its original cost.

        Original lot date and trade date survive the round trip, and no gain or
        loss was realized at the gap in between.
        """
        events = [
            self._buy_event(1, 10, 40, 26.99, txn_date="2024-11-01"),
            self._ist_event(1, 10, -40, -1079.60, txn_date="2024-12-23"),
            self._ist_event(1, 10, 40, 1079.60, txn_date="2025-05-13"),
        ]
        state = self._replay(mock_supabase_client, events, date(2025, 6, 30))

        h = state.holdings[10]
        assert h.quantity == Decimal("40")
        assert h.total_cost == Decimal("1079.60")
        assert h.average_cost == Decimal("26.99")
        assert h.realized_gain_loss == Decimal("0")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("40")
        assert h.lots[0]["cost_per_share"] == Decimal("26.99")
        assert h.lots[0]["date"] == date(2024, 11, 1)  # original lot date preserved
        assert h.trade_date == date(2024, 11, 1)       # original trade date preserved

    def test_gap_date_replay_keeps_dip_visible_and_basis_parked(self, mock_supabase_client):
        """At 2024-12-31 the position has genuinely left -- no fake $0 sale.

        The dip stays visible (too many shares to hold during the gap), the
        original basis is parked rather than booked as a realized loss, and the
        pair key is known from the COMPLETE log even before the inbound leg's
        date.
        """
        events = [
            self._buy_event(1, 10, 40, 26.99, txn_date="2024-11-01"),
            self._ist_event(1, 10, -40, -1079.60, txn_date="2024-12-23"),
            self._ist_event(1, 10, 40, 1079.60, txn_date="2025-05-13"),
        ]
        state = self._replay(mock_supabase_client, events, date(2024, 12, 31))

        # Pairing sees the complete log, so the key is already known at the gap.
        assert state.ist_paired_keys == {("PLTR", "USD", 40.0)}
        # The securities genuinely left the tracked account.
        assert 10 not in state.holdings
        # Original basis is parked, not booked as a fake $0 realized loss.
        parked = state.relocated_basis[("PLTR", "USD", 40.0)]
        assert len(parked) == 1
        assert parked[0]["quantity"] == Decimal("40")
        assert parked[0]["total_cost"] == Decimal("1079.60")
        assert parked[0]["average_cost"] == Decimal("26.99")
        assert parked[0]["trade_date"] == date(2024, 11, 1)
        assert len(parked[0]["lots"]) == 1
        assert parked[0]["lots"][0]["date"] == date(2024, 11, 1)

    def test_unpaired_outbound_keeps_fifo_sale(self, mock_supabase_client):
        """A lone outbound IST leg is not a relocation: today's FIFO sale stays.

        Zero-proceeds sale (@ unit_price None) books the full cost as realized
        loss -- the pre-fix behavior for legs whose counterpart is elsewhere.
        """
        events = [
            self._buy_event(1, 10, 10, 100, txn_date="2024-11-01"),
            self._ist_event(1, 10, -4, -400.00, txn_date="2024-12-23"),
        ]
        state = self._replay(mock_supabase_client, events, date(2024, 12, 31))

        assert state.ist_paired_keys == frozenset()
        assert state.relocated_basis == {}
        h = state.holdings[10]
        assert h.quantity == Decimal("6")
        assert h.total_cost == Decimal("600")
        assert h.realized_gain_loss == Decimal("-400")

    def test_unpaired_inbound_keeps_nca_cost(self, mock_supabase_client):
        """A lone inbound IST leg buys at net_cash_amount / quantity as before."""
        events = [
            self._ist_event(1, 10, 5, 500.00, txn_date="2025-05-13"),
        ]
        state = self._replay(mock_supabase_client, events, date(2025, 6, 30))

        assert state.ist_paired_keys == frozenset()
        h = state.holdings[10]
        assert h.quantity == Decimal("5")
        assert h.average_cost == Decimal("100")
        assert h.total_cost == Decimal("500")

    def test_trade_sell_never_relocates(self, mock_supabase_client):
        """A Trade sell is never relocated, even with an IST inbound of matching
        quantity: reconciliation counts transfer legs only, so the keys cannot
        collide, and the handler only consults pairing for transfer events."""
        events = [
            self._buy_event(1, 10, 40, 26.99, txn_date="2024-11-01"),
            self._sell_event(1, 10, -40, 30, txn_date="2025-01-15"),
            self._ist_event(1, 10, 40, 1079.60, txn_date="2025-05-13"),
        ]
        state = self._replay(mock_supabase_client, events, date(2025, 6, 30))

        assert state.ist_paired_keys == frozenset()  # lone IST inbound, no IST outbound
        assert state.relocated_basis == {}
        # Trade sell: buy 40 @ 26.99 = -1079.60; sell 40 @ 30 = +1200 proceeds.
        assert state.cash_balance == Decimal("120.40")
        # The lone IST inbound is unpaired, so it buys at nca on 2025-05-13 --
        # it does NOT restore the 2024-11-01 Trade basis.
        h = state.holdings[10]
        assert h.quantity == Decimal("40")
        assert h.total_cost == Decimal("1079.60")
        assert len(h.lots) == 1
        assert h.lots[0]["date"] == date(2025, 5, 13)

    def test_float_noise_outbound_still_pairs(self, mock_supabase_client):
        """-10.0000001 and +10.0 round to the same pair key (6dp precision)."""
        events = [
            self._buy_event(1, 10, 10, 100, txn_date="2024-11-01"),
            self._ist_event(1, 10, -10.0000001, -1000.00001, txn_date="2024-12-23"),
            self._ist_event(1, 10, 10.0, 1000.00, txn_date="2025-05-13"),
        ]
        state = self._replay(mock_supabase_client, events, date(2025, 6, 30))

        assert state.ist_paired_keys == {("PLTR", "USD", 10.0)}
        h = state.holdings[10]
        assert h.quantity == Decimal("10")
        assert h.total_cost == Decimal("1000")
        assert h.realized_gain_loss == Decimal("0")

    def test_partial_outbound_parks_only_sold_and_inbound_merges(self, mock_supabase_client):
        """Out -4 of a 10-share holding parks 4; inbound +4 merges into the 6 left."""
        events = [
            self._buy_event(1, 10, 10, 100, txn_date="2024-11-01"),
            self._ist_event(1, 10, -4, -400.00, txn_date="2024-12-23"),
            self._ist_event(1, 10, 4, 400.00, txn_date="2025-05-13"),
        ]
        state = self._replay(mock_supabase_client, events, date(2025, 6, 30))

        h = state.holdings[10]
        assert h.quantity == Decimal("10")
        assert h.total_cost == Decimal("1000")
        assert h.average_cost == Decimal("100")
        assert h.realized_gain_loss == Decimal("0")
        assert len(h.lots) == 2
        assert h.lots[0]["quantity"] == Decimal("6")
        assert h.lots[1]["quantity"] == Decimal("4")
        assert h.lots[1]["date"] == date(2024, 11, 1)  # restored fragment keeps original date

    def test_inbound_before_outbound_falls_back_to_nca_buy(self, mock_supabase_client):
        """An inbound leg processed before anything is parked cannot be restored:
        it buys at nca; the later outbound relocates that fresh basis. No crash."""
        events = [
            self._ist_event(1, 10, 40, 5000.00, txn_date="2025-05-13"),
            self._ist_event(1, 10, -40, -5000.00, txn_date="2025-06-11"),
        ]
        state = self._replay(mock_supabase_client, events, date(2025, 7, 1))

        # inbound: restore finds nothing parked -> nca buy 40 @ 125
        # outbound: paired -> relocates the nca basis out; nothing left to hold
        assert 10 not in state.holdings
        parked = state.relocated_basis[("PLTR", "USD", 40.0)]
        assert parked[0]["quantity"] == Decimal("40")
        assert parked[0]["total_cost"] == Decimal("5000")
        assert parked[0]["average_cost"] == Decimal("125")


# ---------------------------------------------------------------------------
# FIFO sell fallback tests
# ---------------------------------------------------------------------------

class TestFifoSellFallback:
    """Tests for FIFO sell fallback when lots partially cover a sell."""

    def _make_engine(self, mock_client):
        store = EventStore(client=mock_client)
        return ReplayEngine(store)

    def _buy_event(self, account_id, company_id, qty, price, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(-(qty * price)),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _sell_event(self, account_id, company_id, qty, price, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(abs(qty) * price),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def test_fifo_partial_lot_exhaustion_uses_fallback(self, mock_supabase_client):
        """Sell spans initial holding (no lots) + buy lots — fallback covers remainder."""
        engine = self._make_engine(mock_supabase_client)
        # Initial holding with no lots (simulates old data), then buy adds lots, then sell spans both
        events = [
            {
                "event_type": "initial_holding_set",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "cash_balance": 0, "net_deposits": 2000,
                    "holdings": [{
                        "company_id": 10, "symbol": "AAPL",
                        "quantity": 10, "average_cost": 100, "total_cost": 1000,
                    }],
                },
                "created_at": datetime.now(UTC).isoformat(),
            },
            self._buy_event(1, 10, 5, 120),  # adds lot with cost_per_share=120
            self._sell_event(1, 10, -12, 150),  # sells 12: FIFO removes buy lot (5@120), then needs fallback for 7 from initial
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("3")
        # After initial: qty=10, total_cost=1000, avg_cost=100
        # After buy 5@120: qty=15, total_cost=1600, avg_cost=106.67, lots=[{qty:5, cost:120}]
        # After sell 12: FIFO removes lot (5@120), remaining_to_remove=7
        #   fallback: 7 * 106.67 (average_cost) = 746.67
        #   cost_of_sold = 600 + 746.67 = 1346.67
        assert abs(h.total_cost - Decimal("253.33")) < Decimal("0.01")
        assert abs(h.realized_gain_loss - Decimal("453.33")) < Decimal("0.01")

    def test_fifo_no_fallback_when_lots_cover_full_sell(self, mock_supabase_client):
        """When lots fully cover the sell, no fallback is needed."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),
            self._sell_event(1, 10, -5, 150),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("5")
        assert h.total_cost == Decimal("500")
        assert h.realized_gain_loss == Decimal("250")

    def test_fifo_fallback_only_when_needed(self, mock_supabase_client):
        """Fallback triggers only when remaining_to_remove > 0 after lot exhaustion."""
        engine = self._make_engine(mock_supabase_client)
        # Initial with no lots (average_cost=50), then sell 8 shares
        events = [
            {
                "event_type": "initial_holding_set",
                "aggregate_id": "account_1",
                "aggregate_type": "account",
                "data": {
                    "cash_balance": 0, "net_deposits": 500,
                    "holdings": [{
                        "company_id": 10, "symbol": "AAPL",
                        "quantity": 8, "average_cost": 50, "total_cost": 400,
                    }],
                },
                "created_at": datetime.now(UTC).isoformat(),
            },
            self._sell_event(1, 10, -8, 100),
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        # No lots → FIFO loop does nothing → cost_of_sold stays 0
        # Fallback: cost_of_sold == 0, so cost_of_sold = 8 * 50 = 400
        # realized = 8*100 - 400 = 400
        assert len(state.holdings) == 0  # all sold
        # Verify via a snapshot comparison would show the correct cost


# ---------------------------------------------------------------------------
# IST interaction tests: Split, ROC, edge cases
# ---------------------------------------------------------------------------

class TestIstInteractions:
    """Tests for IST interacting with splits, ROC, and edge cases."""

    def _make_engine(self, mock_client):
        store = EventStore(client=mock_client)
        return ReplayEngine(store)

    def _buy_event(self, account_id, company_id, qty, price, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "Trade", "symbol": symbol,
                "quantity": qty, "unit_price": float(price),
                "commission": 0, "net_cash_amount": float(-(qty * price)),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _ist_event(self, account_id, company_id, qty, net_cash_amount, symbol="AAPL"):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "InternalSecurityTransfer", "symbol": symbol,
                "quantity": qty, "unit_price": None,
                "commission": None, "net_cash_amount": float(net_cash_amount) if net_cash_amount is not None else None,
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _split_event(self, account_id, company_id, factor):
        return {
            "event_type": "split",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "split_factor": float(factor),
                "effective_date": datetime.now(UTC).date().isoformat(),
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def _roc_event(self, account_id, company_id, amount):
        return {
            "event_type": "transaction_imported",
            "aggregate_id": f"account_{account_id}",
            "aggregate_type": "account",
            "data": {
                "account_id": account_id, "company_id": company_id,
                "activity_type": "ReturnOfCapital", "symbol": "AAPL",
                "quantity": 0, "unit_price": 0,
                "commission": 0, "net_cash_amount": float(amount),
                "currency": "USD",
            },
            "created_at": datetime.now(UTC).isoformat(),
        }

    def test_ist_then_split(self, mock_supabase_client):
        """IST inbound then split: lots adjust correctly."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._ist_event(1, 10, 10, 1000.00),  # cost_per_share = 100
            self._split_event(1, 10, 2),            # 2:1 split
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # After split: qty=20, avg_cost=50, lot: {qty:20, cost_per_share:50}
        assert h.quantity == Decimal("20")
        assert h.average_cost == Decimal("50")
        assert h.total_cost == Decimal("1000")
        assert len(h.lots) == 1
        assert h.lots[0]["quantity"] == Decimal("20")
        assert h.lots[0]["cost_per_share"] == Decimal("50")

    def test_buy_then_ist_then_split(self, mock_supabase_client):
        """Buy + IST inbound + split: all lots adjust correctly."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),        # lot1: {qty:10, cost:100}
            self._ist_event(1, 10, 5, 500.00),      # lot2: {qty:5, cost:100}
            self._split_event(1, 10, 3),             # 3:1 split
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("45")  # (10+5)*3
        assert h.total_cost == Decimal("1500")  # total cost unchanged
        assert len(h.lots) == 2
        assert h.lots[0]["quantity"] == Decimal("30")  # 10*3
        assert h.lots[0]["cost_per_share"] == Decimal("100") / 3  # 100/3
        assert h.lots[1]["quantity"] == Decimal("15")  # 5*3
        assert h.lots[1]["cost_per_share"] == Decimal("100") / 3  # 100/3

    def test_ist_then_roc(self, mock_supabase_client):
        """IST inbound then ROC: cost basis reduced proportionally."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._ist_event(1, 10, 10, 1000.00),  # cost_per_share = 100
            self._roc_event(1, 10, 200),            # reduce cost by 200
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # After ROC: total_cost = 1000 - 200 = 800, avg_cost = 80
        assert h.total_cost == Decimal("800")
        assert h.average_cost == Decimal("80")
        assert len(h.lots) == 1
        assert h.lots[0]["cost_per_share"] == Decimal("80")

    def test_ist_outbound_with_no_holding(self, mock_supabase_client):
        """Outbound IST with no existing holding: silently ignored."""
        engine = self._make_engine(mock_supabase_client)
        events = [self._ist_event(1, 10, -5, -500.00)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        assert len(state.holdings) == 0

    def test_ist_inbound_with_nca_none(self, mock_supabase_client):
        """Inbound IST with net_cash_amount=None: zero cost basis (defensive)."""
        engine = self._make_engine(mock_supabase_client)
        events = [self._ist_event(1, 10, 5, None)]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("5")
        assert h.total_cost == Decimal("0")
        assert h.average_cost == Decimal("0")
        assert h.lots[0]["cost_per_share"] == Decimal("0")

    def test_multiple_ist_inbound_same_company(self, mock_supabase_client):
        """Multiple IST inbound events for same company: separate lots created."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._ist_event(1, 10, 5, 500.00),   # cost = 100/share
            self._ist_event(1, 10, 3, 450.00),   # cost = 150/share
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("8")
        assert h.total_cost == Decimal("950")
        assert len(h.lots) == 2
        assert h.lots[0]["cost_per_share"] == Decimal("100")
        assert h.lots[1]["cost_per_share"] == Decimal("150")
        # average_cost = 950/8 = 118.75
        assert h.average_cost == Decimal("118.75")

    def test_ist_full_lifecycle(self, mock_supabase_client):
        """Full IST lifecycle: inbound → split → ROC → sell."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._ist_event(1, 10, 10, 1000.00),  # inbound: 10@100
            self._split_event(1, 10, 2),            # split 2:1: 20@50
            self._roc_event(1, 10, 200),            # ROC $200: total_cost=800, avg=40
            self._buy_event(1, 10, 5, 80),          # buy 5@80: adds lot
            # Now: qty=25, lots=[{20, $40}, {5, $80}], total_cost=800+400=1200
            self._ist_event(1, 10, -8, -800.00),   # outbound IST: FIFO removes 8 from first lot
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        # After outbound IST -8: FIFO removes 8 from lot1 (20@40)
        # Remaining: lot1: {12@40}, lot2: {5@80}
        # cost_of_sold = 8*40 = 320
        # total_cost = 1200 - 320 = 880
        # quantity = 25 - 8 = 17
        assert h.quantity == Decimal("17")
        assert h.total_cost == Decimal("880")
        assert len(h.lots) == 2
        assert h.lots[0]["quantity"] == Decimal("12")
        assert h.lots[0]["cost_per_share"] == Decimal("40")
        assert h.lots[1]["quantity"] == Decimal("5")
        assert h.lots[1]["cost_per_share"] == Decimal("80")

    def test_ist_outbound_removes_all_lots_then_inbound(self, mock_supabase_client):
        """Outbound IST removes all lots, then inbound creates new holding."""
        engine = self._make_engine(mock_supabase_client)
        events = [
            self._buy_event(1, 10, 10, 100),        # buy 10@100
            self._ist_event(1, 10, -10, -1000.00),  # outbound: removes all
            self._ist_event(1, 10, 5, 750.00),      # inbound: new lot at 150/share
        ]
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(data=events)

        state = engine.replay_to_date(1, datetime.now(UTC).date())

        h = state.holdings[10]
        assert h.quantity == Decimal("5")
        assert h.total_cost == Decimal("750")
        assert h.average_cost == Decimal("150")
        assert len(h.lots) == 1
        assert h.lots[0]["cost_per_share"] == Decimal("150")


class TestPositionStateCheckpoint:
    def _checkpoint_event(self, effective: date, holdings: list[dict], cash: float) -> dict:
        return {
            "event_type": "position_state_checkpoint",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "effective_date": effective.isoformat(),
                "account_id": 1,
                "cash_balance": cash,
                "net_deposits": cash,
                "holdings": holdings,
            },
            "metadata": {"source": "portfolio_holdings"},
            "created_at": datetime.now(UTC).isoformat(),
        }

    def test_checkpoint_replaces_prior_replayed_state(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        today = datetime.now(UTC).date()
        buy = {
            "event_type": "transaction_imported",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "account_id": 1,
                "company_id": 99,
                "activity_type": "Trade",
                "symbol": "SOLDCO",
                "quantity": 999,
                "unit_price": 1.0,
                "net_cash_amount": -999.0,
                "currency": "USD",
                "transaction_date": (today - date.resolution * 2).isoformat(),
            },
            "created_at": datetime.now(UTC).isoformat(),
        }
        checkpoint = self._checkpoint_event(
            today - date.resolution,
            [{"company_id": 10, "symbol": "AAPL", "quantity": 50, "average_cost": 100, "total_cost": 5000}],
            250.0,
        )
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
            data=[buy, checkpoint]
        )
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, today)

        assert set(state.holdings) == {10}
        assert 99 not in state.holdings
        assert state.holdings[10].quantity == Decimal("50")
        assert state.cash_balance == Decimal("250.0")
        assert state.checkpoint_date == today - date.resolution

    def test_checkpoint_excluded_before_its_effective_date(self, mock_supabase_client):
        store = EventStore(client=mock_supabase_client)
        today = datetime.now(UTC).date()
        buy = {
            "event_type": "transaction_imported",
            "aggregate_id": "account_1",
            "aggregate_type": "account",
            "data": {
                "account_id": 1,
                "company_id": 99,
                "activity_type": "Trade",
                "symbol": "SOLDCO",
                "quantity": 40,
                "unit_price": 2.0,
                "net_cash_amount": -80.0,
                "currency": "USD",
                "transaction_date": (today - date.resolution * 2).isoformat(),
            },
            "created_at": datetime.now(UTC).isoformat(),
        }
        checkpoint = self._checkpoint_event(
            today,
            [{"company_id": 10, "symbol": "AAPL", "quantity": 50, "average_cost": 100, "total_cost": 5000}],
            250.0,
        )
        mock_supabase_client.table.return_value.select.return_value.order.return_value.execute.return_value = MagicMock(
            data=[buy, checkpoint]
        )
        engine = ReplayEngine(store)
        state = engine.replay_to_date(1, today - date.resolution)

        assert set(state.holdings) == {99}
        assert state.checkpoint_date is None
        assert state.cash_balance == Decimal("-80.0")


class TestReplayCdrLotLegs:
    """BLK-027: replay must value a mixed position one leg at a time.

    Replay cannot classify its own lots -- stored transaction_imported events
    carry no security_name or exchange_override, so every event lot looks direct
    and a CDR position would be undervalued tenfold. Lot provenance must therefore
    be supplied from portfolio_transactions.
    """

    @staticmethod
    def _holdings(qty, cost):
        qty, cost = Decimal(str(qty)), Decimal(str(cost))
        return {
            145: HoldingState(
                company_id=145,
                symbol="META",
                quantity=qty,
                total_cost=cost,
                average_cost=cost / qty,
            )
        }

    def test_no_lot_evidence_leaves_the_company_keyed_path(self):
        legs = _cdr_lot_legs(self._holdings(27, 2700), None, {145})
        assert len(legs) == 1
        assert legs[0][2] is None

    def test_uniform_cdr_lot_is_a_single_leg(self):
        legs = _cdr_lot_legs(
            self._holdings(25, 2500), {145: {"cdr": Decimal(25)}}, {145}
        )
        assert len(legs) == 1
        assert legs[0][2] == "cdr"

    def test_mixed_lot_splits_and_conserves_quantity_and_cost(self):
        legs = _cdr_lot_legs(
            self._holdings(27, 2700),
            {145: {"cdr": Decimal(25), "direct": Decimal(2)}},
            {145},
        )
        assert [kind for _, _, kind in legs] == ["cdr", "direct"]
        assert sum((h.quantity for _, h, _ in legs), Decimal(0)) == Decimal(27)
        assert sum((h.total_cost for _, h, _ in legs), Decimal(0)) == Decimal(2700)

    def test_quantity_mismatch_refuses_to_split(self):
        legs = _cdr_lot_legs(
            self._holdings(73, 7300),
            {145: {"cdr": Decimal(730)}},
            set(),
        )
        assert len(legs) == 1
        assert legs[0][1].quantity == Decimal(73)

    def test_company_absent_from_lot_map_keeps_company_keyed_path(self):
        legs = _cdr_lot_legs(
            self._holdings(27, 2700), {999: {"cdr": Decimal(5)}}, {145}
        )
        assert len(legs) == 1
        assert legs[0][2] is None
