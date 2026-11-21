"""I5 -- real-data spikes are attributed to transfer round-trips, not suppressed.

USER-ASK A3 proved the 2024-12-23 -> 2025-05/06 steps are genuine
InternalSecurityTransfer movements. Suppressing them would hide real portfolio
history; logging a vague "real data" verdict is honest but unhelpful. The fix
consults the transfer knowledge and names the cause while retaining the value.
"""

import logging
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.repositories.event_store import EventStore
from shared.transfer_reconciliation import transfer_leg_counts_by_date


def _payload(d="2024-12-23", qty=-2.0):
    return {
        "activity_type": "InternalSecurityTransfer",
        "symbol": "HOOD",
        "currency": "USD",
        "quantity": qty,
        "net_cash_amount": -500.0,
        "transaction_date": d,
    }


class TestTransferLegCountsByDate:
    def test_counts_bare_and_enveloped_payloads(self):
        events = [
            _payload("2024-12-23", -2.0),
            {"data": _payload("2024-12-23", -3.0)},
            {"data": _payload("2025-05-13", 2.0)},
            {"data": _payload("2025-05-13", 3.0)},
            {"data": _payload("2025-05-13", 4.0)},
        ]
        assert transfer_leg_counts_by_date(events) == {
            "2024-12-23": 2,
            "2025-05-13": 3,
        }

    def test_ignores_non_transfers_malformed_and_undated(self):
        events = [
            {"data": {"activity_type": "transaction_imported", "transaction_date": "2024-12-23"}},
            {"data": _payload("2024-12-23") | {"transaction_date": None}},
            {"data": "not a mapping"},
            None,
            {"data": _payload("2025-06-11")},
        ]
        assert transfer_leg_counts_by_date(events) == {"2025-06-11": 1}

    def test_empty_events(self):
        assert transfer_leg_counts_by_date([]) == {}


class TestGetTransferLegs:
    def test_queries_transaction_imported_and_filters_activity_type(self):
        client = MagicMock()
        chain = client.table.return_value.select.return_value.eq.return_value
        chain.in_.return_value.execute.return_value = MagicMock(data=[
            {"data": _payload("2024-12-23")},
            {"data": {"activity_type": "transaction_imported", "transaction_date": "2024-12-23"}},
            {"data": None},
        ])
        store = EventStore(client=client)

        legs = store.get_transfer_legs([8, 9])

        client.table.assert_called_once_with("portfolio_events")
        client.table.return_value.select.assert_called_once_with("data")
        client.table.return_value.select.return_value.eq.assert_called_once_with(
            "event_type", "transaction_imported"
        )
        chain.in_.assert_called_once_with("aggregate_id", ["account_8", "account_9"])
        assert legs == [_payload("2024-12-23")]

    def test_no_accounts_short_circuits(self):
        client = MagicMock()
        store = EventStore(client=client)
        assert store.get_transfer_legs([]) == []
        client.table.assert_not_called()


# --- read-path attribution (models test_portfolio_performance_spike_suppression) ---

def _snap(account_id, d, total_value):
    return {
        "account_id": account_id,
        "snapshot_date": d.isoformat(),
        "total_value": total_value,
        "holdings_market_value": total_value,
        "cost_basis": total_value * 0.7,
        "cash_balance": 0.0,
        "net_deposits": 0.0,
        "data_quality_flag": "OK",
    }


def _make_service(rows):
    from application.services.portfolio_service import PortfolioService
    from config import settings as real_settings

    accounts = [
        {"account_id": 7, "account_name": "TFSA", "is_active": True},
        {"account_id": 8, "account_name": "RRSP", "is_active": True},
        {"account_id": 9, "account_name": "Margin", "is_active": True},
    ]
    repo = MagicMock()
    repo.get_user_accounts.return_value = accounts

    snaps = MagicMock()
    snaps.get_portfolio_snapshots_series.return_value = rows
    snaps.get_first_snapshot_date.return_value = date(2025, 1, 1)

    patchers = []
    for attr, value in (
        ("ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH", True),
        ("ENABLE_PORTFOLIO_RESPONSE_CACHE", False),
        ("ENABLE_PORTFOLIO_VALUE_SERIES", False),
        ("ENABLE_PERFORMANCE_LOCF", True),
        ("SNAPSHOT_SPIKE_THRESHOLD", 0.20),
    ):
        p = patch.object(real_settings, attr, value)
        p.start()
        patchers.append(p)

    p = patch.object(
        PortfolioService, "_period_to_date_range",
        return_value=(date(2025, 1, 1), date(2025, 1, 4)),
    )
    p.start()
    patchers.append(p)
    p = patch(
        "application.services.portfolio_service.PortfolioSnapshotsRepository",
        return_value=snaps,
    )
    p.start()
    patchers.append(p)

    return PortfolioService(repo, MagicMock()), [7, 8, 9], patchers


def _spike_rows():
    rows = []
    for i, d in enumerate([date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 4)]):
        vals = {7: 100.0, 8: 200.0, 9: 300.0} if i < 2 else (
            {7: 150.0, 8: 250.0, 9: 350.0} if i == 2 else {7: 155.0, 8: 260.0, 9: 360.0}
        )
        for aid in (7, 8, 9):
            rows.append(_snap(aid, d, vals[aid]))
    return rows


@pytest.mark.anyio
async def test_spike_on_transfer_date_is_attributed_and_retained(caplog):
    service, account_ids, patchers = _make_service(_spike_rows())
    try:
        with caplog.at_level(logging.INFO, logger="application.services.portfolio_service"), \
             patch("infrastructure.repositories.event_store.EventStore") as mock_store:
            mock_store.return_value.get_transfer_legs.return_value = [
                _payload("2025-01-03"), _payload("2025-01-03", 2.0)
            ]
            result = await service.get_portfolio_performance(1, "1W", account_ids)
    finally:
        for p in patchers:
            p.stop()

    values = [s["value"] for s in result["snapshots"]]
    assert values == [600.0, 600.0, 750.0, 775.0]  # genuine step retained
    assert "InternalSecurityTransfer round-trip (2 legs)" in caplog.text
    assert "not suppressed (real data)" not in caplog.text


@pytest.mark.anyio
async def test_spike_without_transfer_uses_honest_generic_message(caplog):
    service, account_ids, patchers = _make_service(_spike_rows())
    try:
        with caplog.at_level(logging.INFO, logger="application.services.portfolio_service"), \
             patch("infrastructure.repositories.event_store.EventStore") as mock_store:
            mock_store.return_value.get_transfer_legs.return_value = []
            await service.get_portfolio_performance(1, "1W", account_ids)
    finally:
        for p in patchers:
            p.stop()

    assert "retained (no LOCF/FX artifact marker)" in caplog.text
    assert "not suppressed (real data)" not in caplog.text


@pytest.mark.anyio
async def test_attribution_failure_never_fails_response(caplog):
    service, account_ids, patchers = _make_service(_spike_rows())
    try:
        with patch("infrastructure.repositories.event_store.EventStore") as mock_store:
            mock_store.return_value.get_transfer_legs.side_effect = RuntimeError("db down")
            result = await service.get_portfolio_performance(1, "1W", account_ids)
    finally:
        for p in patchers:
            p.stop()

    assert result["success"] is True
    assert [s["value"] for s in result["snapshots"]] == [600.0, 600.0, 750.0, 775.0]
