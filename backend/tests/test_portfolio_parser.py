"""
Tests for portfolio CSV parser — CDR detection and exchange_override.
"""

import pytest

from application.parsers.portfolio_parser import ParsedTransaction, WealthsimpleParser


@pytest.fixture
def parser():
    return WealthsimpleParser()


class TestWealthsimpleParserCDR:
    """CDR (Canadian Depositary Receipt) detection tests."""

    def test_normalize_symbol_strips_cdr_suffix(self, parser):
        """CDR suffix should be stripped from the symbol."""
        result = parser.normalize_symbol("TSLA CDR (CAD Hedged)", "Tesla CDR")
        assert result == "TSLA"

    def test_normalize_symbol_strips_bare_cdr(self, parser):
        """Bare ' CDR' suffix should be stripped."""
        result = parser.normalize_symbol("META CDR", "Meta CDR")
        assert result == "META"

    def test_normalize_symbol_preserves_non_cdr(self, parser):
        """Non-CDR symbol should pass through unchanged (minus normalization)."""
        result = parser.normalize_symbol("AAPL", "Apple Inc.")
        assert result == "AAPL"

    def test_normalize_symbol_converts_dot_to_hyphen(self, parser):
        """Dot in symbol should be converted to hyphen."""
        result = parser.normalize_symbol("BRK.B", "Berkshire Hathaway")
        assert result == "BRK-B"

    def test_parse_row_cdr_sets_exchange_override_tor(self, parser):
        """CDR symbol should set exchange_override='TOR'."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "direction": "LONG",
            "symbol": "META CDR (CAD Hedged)",
            "name": "Meta CDR (CAD Hedged)",
            "currency": "CAD",
            "quantity": "10",
            "unit_price": "60.50",
            "commission": "0",
            "net_cash_amount": "-605.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol == "META"
        assert tx.exchange_override == "TOR"

    def test_parse_row_cdr_no_hedged_sets_exchange_override_tor(self, parser):
        """Bare 'CDR' symbol (no hedged) should set exchange_override='TOR'."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "direction": "LONG",
            "symbol": "GOOG CDR",
            "name": "GOOG CDR",
            "currency": "CAD",
            "quantity": "5",
            "unit_price": "30.00",
            "commission": "0",
            "net_cash_amount": "-150.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol == "GOOG"
        assert tx.exchange_override == "TOR"

    def test_parse_row_cdr_hedged_only_sets_exchange_override_tor(self, parser):
        """'CDR (Hedged)' variant should set exchange_override='TOR'."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "direction": "LONG",
            "symbol": "AAPL CDR (Hedged)",
            "name": "AAPL CDR (Hedged)",
            "currency": "CAD",
            "quantity": "10",
            "unit_price": "20.00",
            "commission": "0",
            "net_cash_amount": "-200.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol == "AAPL"
        assert tx.exchange_override == "TOR"

    def test_parse_row_cdr_in_name_only_sets_exchange_override(self, parser):
        """CDR in name field (not symbol) should still set exchange_override='TOR'."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "direction": "LONG",
            "symbol": "META",
            "name": "Meta CDR (CAD Hedged)",
            "currency": "CAD",
            "quantity": "10",
            "unit_price": "60.50",
            "commission": "0",
            "net_cash_amount": "-605.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol == "META"
        assert tx.exchange_override == "TOR"

    def test_parse_row_non_cdr_no_override(self, parser):
        """Non-CDR symbol should have exchange_override=None."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "direction": "LONG",
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "currency": "USD",
            "quantity": "10",
            "unit_price": "150.00",
            "commission": "0",
            "net_cash_amount": "-1500.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol == "AAPL"
        assert tx.exchange_override is None

    def test_parse_row_canadian_stock_no_override(self, parser):
        """Canadian stock (no CDR suffix) should have exchange_override=None."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "direction": "LONG",
            "symbol": "SHOP",
            "name": "Shopify Inc.",
            "currency": "CAD",
            "quantity": "10",
            "unit_price": "120.00",
            "commission": "0",
            "net_cash_amount": "-1200.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol == "SHOP"
        assert tx.exchange_override is None

    def test_parse_row_non_trade_no_override(self, parser):
        """Non-trade row (no symbol) should have exchange_override=None."""
        row = {
            "transaction_date": "2026-01-15",
            "settlement_date": "2026-01-17",
            "account_id": "H12345CAD",
            "account_type": "TFSA",
            "activity_type": "MoneyMovement",
            "activity_sub_type": "EFT",
            "direction": "",
            "symbol": "",
            "name": "",
            "currency": "CAD",
            "quantity": "",
            "unit_price": "",
            "commission": "0",
            "net_cash_amount": "5000.00",
        }
        tx: ParsedTransaction = parser._parse_row(row)
        assert tx.symbol is None
        assert tx.exchange_override is None
