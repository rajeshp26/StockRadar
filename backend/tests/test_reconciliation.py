"""Tests for alerting and reconciliation engine."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from shared.alerting import SlackAlerter, AlertLevel
from shared.reconciliation import (
    BrokerStatementCSVAdapter, BrokerStatement,
    ReconciliationEngine, ReconciliationResult,
)


class TestSlackAlerter:
    def test_no_webhook_suppresses_alert(self):
        alerter = SlackAlerter(webhook_url=None)
        result = alerter.send_alert("test message")
        assert result is False

    @patch("shared.alerting.httpx.Client")
    def test_successful_alert(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.return_value.__enter__.return_value.post.return_value = mock_resp

        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        result = alerter.send_alert("hello", level=AlertLevel.INFO)
        assert result is True

    @patch("shared.alerting.httpx.Client")
    def test_retry_on_failure(self, mock_httpx):
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 500
        mock_resp_ok = MagicMock()
        mock_resp_ok.status_code = 200

        mock_httpx.return_value.__enter__.return_value.post.side_effect = [
            mock_resp_fail, mock_resp_ok
        ]

        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        result = alerter.send_alert("retry test", level=AlertLevel.WARNING)
        assert result is True

    @patch("shared.alerting.httpx.Client")
    def test_circuit_breaker_opens(self, mock_httpx):
        mock_resp = MagicMock()
        mock_resp.status_code = 500

        mock_httpx.return_value.__enter__.return_value.post.return_value = mock_resp

        alerter = SlackAlerter(webhook_url="https://hooks.slack.com/test")
        alerter.MAX_RETRIES = 2

        # First three batches of failures
        for _ in range(3):
            alerter.send_alert("failing...")

        # Circuit should now be open
        result = alerter.send_alert("should be suppressed")
        assert result is False

    def test_alert_level_helpers(self):
        alerter = SlackAlerter(webhook_url=None)
        assert alerter.alert_critical("test") is False
        assert alerter.alert_warning("test") is False
        assert alerter.alert_info("test") is False


class TestBrokerStatementCSVAdapter:
    def test_parse_valid_row(self):
        row = {
            "account": "ws_12345",
            "date": "2026-06-23",
            "cash": "1234.56",
            "holdings_json": '{"AAPL": 50, "RY": 100}',
            "source_file": "test.csv",
        }
        stmt = BrokerStatementCSVAdapter.parse_row(row)
        assert stmt is not None
        assert stmt.account_external_id == "ws_12345"
        assert stmt.statement_date == date(2026, 6, 23)
        assert stmt.cash_balance == Decimal("1234.56")
        assert stmt.holdings["AAPL"] == Decimal("50")
        assert stmt.holdings["RY"] == Decimal("100")

    def test_parse_row_empty_account(self):
        row = {"account": "", "date": "2026-06-23", "cash": "0", "holdings_json": "{}"}
        assert BrokerStatementCSVAdapter.parse_row(row) is None

    def test_parse_row_missing_date(self):
        row = {"account": "ws_1", "date": "bad-date", "cash": "0", "holdings_json": "{}"}
        assert BrokerStatementCSVAdapter.parse_row(row) is None

    def test_parse_row_none_fields(self):
        assert BrokerStatementCSVAdapter.parse_row(None) is None

    def test_parse_csv_with_multiple_statements(self):
        csv_content = (
            "account,date,cash,holdings_json,source_file\n"
            "ws_1,2026-06-01,5000.00,\"{""AAPL"": 10}\",stmt1.csv\n"
            "ws_2,2026-06-01,10000.00,\"{""RY"": 20}\",stmt2.csv\n"
        )
        statements = BrokerStatementCSVAdapter.parse_csv(csv_content)
        assert len(statements) == 2
        assert statements[0].account_external_id == "ws_1"
        assert statements[1].account_external_id == "ws_2"

    def test_parse_csv_empty(self):
        statements = BrokerStatementCSVAdapter.parse_csv("")
        assert statements == []


class TestReconciliationEngine:
    def test_perfect_match(self, mock_supabase_client):
        store = MagicMock()
        alerter = MagicMock()
        engine = ReconciliationEngine(event_store=store, alerter=alerter)

        stmt = BrokerStatement(
            account_external_id="ws_1",
            statement_date=date(2026, 6, 23),
            cash_balance=Decimal("5000.00"),
            holdings={"AAPL": Decimal("50")},
        )

        with patch(
            "infrastructure.repositories.portfolio_repository.PortfolioRepository"
        ) as MockRepo:
            mock_instance = MagicMock()
            mock_instance.get_cash_balance.return_value = Decimal("5000.00")
            mock_instance.get_account_holdings_as_of.return_value = []
            MockRepo.return_value = mock_instance

            result = engine.reconcile(stmt, account_id=1)

        assert result.cash_delta == 0
        assert result.auto_corrected is True

    def test_small_cash_delta_auto_corrects(self, mock_supabase_client):
        store = MagicMock()
        store.append_event.return_value = {"id": "corr-evt-1"}
        alerter = MagicMock()
        engine = ReconciliationEngine(event_store=store, alerter=alerter)

        stmt = BrokerStatement(
            account_external_id="ws_1",
            statement_date=date(2026, 6, 23),
            cash_balance=Decimal("5100.00"),
            holdings={},
        )

        with patch(
            "infrastructure.repositories.portfolio_repository.PortfolioRepository"
        ) as MockRepo:
            mock_instance = MagicMock()
            mock_instance.get_cash_balance.return_value = Decimal("5000.00")
            mock_instance.get_account_holdings_as_of.return_value = []
            MockRepo.return_value = mock_instance

            result = engine.reconcile(stmt, account_id=1)

        assert result.cash_delta == Decimal("100.00")
        assert result.auto_corrected is True
        assert result.correction_event_id == "corr-evt-1"
        store.append_event.assert_called_once()

    def test_large_cash_delta_needs_review(self, mock_supabase_client):
        store = MagicMock()
        alerter = MagicMock()
        engine = ReconciliationEngine(event_store=store, alerter=alerter)

        stmt = BrokerStatement(
            account_external_id="ws_1",
            statement_date=date(2026, 6, 23),
            cash_balance=Decimal("15000.00"),
            holdings={},
        )

        with patch(
            "infrastructure.repositories.portfolio_repository.PortfolioRepository"
        ) as MockRepo:
            mock_instance = MagicMock()
            mock_instance.get_cash_balance.return_value = Decimal("5000.00")
            mock_instance.get_account_holdings_as_of.return_value = []
            MockRepo.return_value = mock_instance

            result = engine.reconcile(stmt, account_id=1)

        assert abs(result.cash_delta) == Decimal("10000.00")
        assert result.auto_corrected is False
        assert result.needs_review is True
        store.append_event.assert_not_called()
        alerter.alert_warning.assert_called_once()

    def test_repo_error_returns_early(self, mock_supabase_client):
        engine = ReconciliationEngine()
        stmt = BrokerStatement(
            account_external_id="ws_1",
            statement_date=date(2026, 6, 23),
            cash_balance=Decimal("100.00"),
            holdings={},
        )

        with patch(
            "infrastructure.repositories.portfolio_repository.PortfolioRepository"
        ) as MockRepo:
            mock_instance = MagicMock()
            mock_instance.get_cash_balance.side_effect = Exception("DB error")
            MockRepo.return_value = mock_instance

            result = engine.reconcile(stmt, account_id=1)

        assert len(result.errors) > 0
        assert "DB error" in result.errors[0]
