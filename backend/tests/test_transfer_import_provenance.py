"""Tests for import provenance preservation and transfer reconciliation.

Two defects motivated this module:

1. The CSV import path discarded ``direction``, ``activity_sub_type`` and
   ``settlement_date`` when projecting a parsed transaction into an event. The
   65 outbound ``InternalSecurityTransfer`` legs dated 2024-12-23 therefore
   carried no field that could pair them with their inbound counterparts, which
   surfaced as an artificial -32.39% Q4 drop.
2. The backfill path discarded ``security_name`` and ``exchange_override``, the
   two keys CDR override derivation depends on, so backfilled CDR symbols lost
   their pricing venue.

The most important test here is
:meth:`TestReplayInertness.test_new_provenance_fields_do_not_change_valuation`.
It proves that adding these keys cannot move a single historical number, which
is what makes the change safe to apply to an existing event store.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from shared.portfolio_event_payload import (  # noqa: E402
    CANONICAL_TRANSACTION_EVENT_FIELDS,
    build_transaction_event_data,
)
from shared.replay_engine import ReplayEngine  # noqa: E402
from shared.transfer_reconciliation import (  # noqa: E402
    TRANSFER_ACTIVITY_TYPE,
    reconcile_transfers,
)
from infrastructure.repositories.event_store import EventStore  # noqa: E402

TRADE = "Trade"


def _transfer(
    *,
    account_id: int,
    symbol: str,
    quantity: float,
    net_cash_amount: float,
    currency: str = "USD",
    transaction_date: str = "2024-12-23",
) -> dict:
    return {
        "data": build_transaction_event_data(
            account_id=account_id,
            company_id=1,
            transaction_date=transaction_date,
            activity_type=TRANSFER_ACTIVITY_TYPE,
            symbol=symbol,
            quantity=quantity,
            net_cash_amount=net_cash_amount,
            currency=currency,
        )
    }


def _replay_state(client, payloads):
    store = EventStore(client=client)
    now = datetime.now(UTC)
    client.table.return_value.select.return_value.order.return_value.execute.return_value = (
        MagicMock(
            data=[
                {
                    "event_type": "transaction_imported",
                    "aggregate_id": "account_1",
                    "aggregate_type": "account",
                    "data": p,
                    "created_at": now.isoformat(),
                }
                for p in payloads
            ]
        )
    )
    return ReplayEngine(store).replay_to_date(1, now.date())


class TestCanonicalPayload:
    def test_emits_exactly_the_canonical_key_set(self):
        data = build_transaction_event_data(
            account_id=8,
            company_id=41,
            transaction_date="2024-12-23",
            activity_type=TRADE,
        )
        assert set(data) == set(CANONICAL_TRANSACTION_EVENT_FIELDS)

    def test_retains_provenance_dropped_by_the_old_import_path(self):
        data = build_transaction_event_data(
            account_id=8,
            company_id=41,
            transaction_date="2024-12-23",
            settlement_date="2024-12-24",
            activity_type=TRANSFER_ACTIVITY_TYPE,
            activity_sub_type="TransferOut",
            direction="OUT",
            symbol="PLTR",
            quantity=-40.0,
            currency="USD",
        )
        assert data["direction"] == "OUT"
        assert data["activity_sub_type"] == "TransferOut"
        assert data["settlement_date"] == "2024-12-24"

    def test_retains_cdr_fields_the_old_backfill_path_dropped(self):
        data = build_transaction_event_data(
            account_id=9,
            company_id=42,
            transaction_date="2024-12-23",
            activity_type=TRADE,
            security_name="Shopify Inc. Class A (CDN)",
            exchange_override="TOR",
        )
        assert data["security_name"] == "Shopify Inc. Class A (CDN)"
        assert data["exchange_override"] == "TOR"

    def test_absent_values_are_none_not_missing(self):
        data = build_transaction_event_data(
            account_id=1,
            company_id=None,
            transaction_date="2024-12-23",
            activity_type=TRADE,
        )
        for key in CANONICAL_TRANSACTION_EVENT_FIELDS:
            assert key in data
        assert data["direction"] is None
        assert data["settlement_date"] is None


class TestReplayInertness:
    def test_new_provenance_fields_do_not_change_valuation(self, mock_supabase_client):
        legacy = {
            "account_id": 1,
            "company_id": 10,
            "transaction_date": "2024-12-23",
            "activity_type": TRADE,
            "symbol": "AAPL",
            "quantity": 50.0,
            "unit_price": 145.0,
            "net_cash_amount": -7250.0,
            "currency": "USD",
        }
        enriched = build_transaction_event_data(
            account_id=1,
            company_id=10,
            transaction_date="2024-12-23",
            settlement_date="2024-12-24",
            activity_type=TRADE,
            activity_sub_type="BUY",
            direction="OUT",
            symbol="AAPL",
            security_name="Apple Inc.",
            exchange_override=None,
            quantity=50.0,
            unit_price=145.0,
            net_cash_amount=-7250.0,
            currency="USD",
            notes="a note",
        )
        assert set(enriched) - set(legacy) == {
            "settlement_date",
            "activity_sub_type",
            "direction",
            "security_name",
            "exchange_override",
            "notes",
        }

        before = _replay_state(mock_supabase_client, [legacy])
        after = _replay_state(mock_supabase_client, [enriched])

        assert after.cash_balance == before.cash_balance
        assert after.net_deposits == before.net_deposits
        holding_before = before.holdings[10]
        holding_after = after.holdings[10]
        assert holding_after.quantity == holding_before.quantity
        assert holding_after.total_cost == holding_before.total_cost
        assert holding_after.average_cost == holding_before.average_cost

    def test_emitting_commission_would_change_cost_basis(self, mock_supabase_client):
        """Pins the trade-off behind excluding commission from the payload.

        replay derives ``cost_per_share = unit_price + commission / quantity``.
        The parser captures commission but the import path has always dropped
        it, so every imported trade's cost basis silently ignores commission.
        Emitting the key would correct that but would also move every historical
        valuation, so it is a separate decision rather than a side effect. If a
        future change starts emitting commission, this test is what should fail
        loudly and force that decision.
        """
        base = build_transaction_event_data(
            account_id=1,
            company_id=10,
            transaction_date="2024-12-23",
            activity_type=TRADE,
            symbol="AAPL",
            quantity=50.0,
            unit_price=145.0,
            net_cash_amount=-7250.0,
            currency="USD",
        )
        with_commission = dict(base, commission=Decimal("7.25"))

        without = _replay_state(mock_supabase_client, [base])
        affected = _replay_state(mock_supabase_client, [with_commission])

        assert without.holdings[10].average_cost == Decimal("145")
        assert affected.holdings[10].average_cost == Decimal("145.145")
        assert without.holdings[10].total_cost != affected.holdings[10].total_cost


class TestTransferReconciliation:
    def test_no_transfers_reports_nothing(self):
        report = reconcile_transfers(
            [{"data": {"activity_type": TRADE, "quantity": 10, "symbol": "AAPL"}}]
        )
        assert report.transfer_count == 0
        assert report.unpaired == ()
        assert report.warnings == []
        assert "No security transfers" in report.summary()

    def test_outbound_and_inbound_in_one_batch_pair(self):
        report = reconcile_transfers(
            [
                _transfer(
                    account_id=8, symbol="PLTR", quantity=-40.0,
                    net_cash_amount=-1079.60,
                ),
                _transfer(
                    account_id=9, symbol="PLTR", quantity=40.0,
                    net_cash_amount=1079.60,
                ),
            ]
        )
        assert report.transfer_count == 2
        assert report.paired_count == 2
        assert report.unpaired_count == 0
        assert "All 2" in report.summary()

    def test_outbound_only_is_reported_not_raised(self):
        """The 2024-12-23 failure mode: 65 legs with no counterpart in the file."""
        report = reconcile_transfers(
            [
                _transfer(
                    account_id=8, symbol="PLTR", quantity=-40.0,
                    net_cash_amount=-1079.60,
                )
            ]
        )
        assert report.transfer_count == 1
        assert report.paired_count == 0
        assert report.unpaired_count == 1
        warning = report.warnings[0]
        assert "outbound leg unpaired" in warning
        assert "no matching inbound leg" in warning
        assert "PLTR" in warning
        assert "-40" in warning
        assert "USD" in warning
        assert "2024-12-23" in warning

    def test_inbound_only_is_reported(self):
        report = reconcile_transfers(
            [
                _transfer(
                    account_id=9, symbol="MO", quantity=7.0, net_cash_amount=375.06,
                )
            ]
        )
        assert report.unpaired_count == 1
        assert "inbound leg unpaired" in report.warnings[0]

    def test_pairs_across_files_via_prior_events(self):
        prior = [
            _transfer(
                account_id=8, symbol="MO", quantity=-7.0, net_cash_amount=-375.06,
            )
        ]
        current = [
            _transfer(
                account_id=9, symbol="MO", quantity=7.0, net_cash_amount=375.06,
                transaction_date="2025-05-13",
            )
        ]
        report = reconcile_transfers(current, prior_events=prior)
        assert report.transfer_count == 2
        assert report.paired_count == 2
        assert report.unpaired_count == 0

    def test_partial_overlap_leaves_only_the_surplus_unpaired(self):
        report = reconcile_transfers(
            [
                _transfer(account_id=8, symbol="MO", quantity=-7.0, net_cash_amount=-375.06),
                _transfer(account_id=8, symbol="MO", quantity=-3.0, net_cash_amount=-160.00),
                _transfer(account_id=9, symbol="MO", quantity=7.0, net_cash_amount=375.06),
            ]
        )
        assert report.transfer_count == 3
        assert report.paired_count == 2
        assert report.unpaired_count == 1
        assert report.unpaired[0].quantity == -3.0

    def test_same_symbol_different_currency_does_not_pair(self):
        report = reconcile_transfers(
            [
                _transfer(
                    account_id=8, symbol="F", quantity=-20.0,
                    net_cash_amount=-198.0, currency="USD",
                ),
                _transfer(
                    account_id=9, symbol="F", quantity=20.0,
                    net_cash_amount=270.0, currency="CAD",
                ),
            ]
        )
        assert report.paired_count == 0
        assert report.unpaired_count == 2

    def test_different_symbols_do_not_pair(self):
        report = reconcile_transfers(
            [
                _transfer(account_id=8, symbol="PLTR", quantity=-40.0, net_cash_amount=-1079.60),
                _transfer(account_id=9, symbol="MO", quantity=40.0, net_cash_amount=1079.60),
            ]
        )
        assert report.paired_count == 0
        assert report.unpaired_count == 2

    def test_float_noise_still_pairs(self):
        report = reconcile_transfers(
            [
                _transfer(account_id=8, symbol="UBS", quantity=-3.47, net_cash_amount=-500.0),
                _transfer(account_id=9, symbol="UBS", quantity=3.47, net_cash_amount=500.0),
            ]
        )
        assert report.paired_count == 2
        assert report.unpaired_count == 0

    def test_missing_quantity_is_reported_not_raised(self):
        report = reconcile_transfers(
            [{"data": {"activity_type": TRANSFER_ACTIVITY_TYPE, "symbol": "PLTR",
                       "account_id": 8, "transaction_date": "2024-12-23"}}]
        )
        assert report.unpaired_count == 1
        assert "cannot be paired" in report.warnings[0]

    def test_malformed_entries_do_not_raise(self):
        report = reconcile_transfers(
            [
                None,
                "not-a-mapping",
                {"data": None},
                {"no_data_key": True},
                _transfer(account_id=8, symbol="PLTR", quantity=-40.0, net_cash_amount=-1079.60),
            ]
        )
        assert report.transfer_count == 1
        assert report.unpaired_count == 1

    def test_bare_data_payloads_are_accepted(self):
        report = reconcile_transfers(
            [
                {
                    "activity_type": TRANSFER_ACTIVITY_TYPE,
                    "account_id": 8,
                    "symbol": "PLTR",
                    "quantity": -40.0,
                    "net_cash_amount": -1079.60,
                    "currency": "USD",
                    "transaction_date": "2024-12-23",
                }
            ]
        )
        assert report.transfer_count == 1
        assert report.unpaired_count == 1

    def test_summary_counts_legs_not_pairs(self):
        report = reconcile_transfers(
            [
                _transfer(account_id=8, symbol="A", quantity=-1.0, net_cash_amount=-1.0),
                _transfer(account_id=9, symbol="A", quantity=1.0, net_cash_amount=1.0),
                _transfer(account_id=8, symbol="B", quantity=-2.0, net_cash_amount=-2.0),
            ]
        )
        assert report.transfer_count == 3
        assert report.paired_count == 2
        assert "2/3" in report.summary()
        assert "1 unpaired" in report.summary()