"""Tests for the price plausibility gate root fix.

Covers:
- _build_price_plausibility_anchors: tx-first precedence, current-quote raise,
  history fallback only for anchorless companies (never raises a tx anchor).
- _apply_price_plausibility_gate: reject scale errors, accept legit high-priced
  rows, accept-and-flag anchorless rows.
- upsert_price_history wiring: all-rejected rows return count 0 + gate_rejected.
- increment_price_failures: read-then-increment (was flat-set to 1, so the
  quarantine counter never tripped).
- check_snapshot_spike rewrite: deposits-adjusted unexplained, whitelist hole
  removed.
- compute_daily_snapshots spike policy: withhold the write instead of persisting
  a garbage total, and instead of laundering the previous day's values into a row
  under the spike date.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from shared.snapshot_builder import check_snapshot_spike


def _make_table_mock(data=None):
    t = MagicMock()
    t.select.return_value = t
    t.eq.return_value = t
    t.in_.return_value = t
    t.not_.is_.return_value = t
    t.order.return_value = t
    t.limit.return_value = t
    t.update.return_value = t
    t.upsert.return_value = t
    t.insert.return_value = t
    t.single.return_value = t
    t.execute.return_value = MagicMock(data=data or [])
    return t


def _make_gate_client(tables):
    """Client whose .table(name) hands back a distinct chained mock per table."""
    mocks = {name: _make_table_mock(data) for name, data in tables.items()}

    def _table(name):
        return mocks.get(name, _make_table_mock([]))

    client = MagicMock()
    client.table.side_effect = _table
    return client, mocks


def _make_gate_repo(client):
    from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
    return SupabaseFinancialRepository(client=client)


# ---------------------------------------------------------------------------
# _build_price_plausibility_anchors
# ---------------------------------------------------------------------------

class TestBuildPricePlausibilityAnchors:
    def test_tx_anchor_dominates_and_history_never_raises_it(self):
        client, _ = _make_gate_client({
            "companies": [{"company_id": 3159, "ticker_symbol": "RSLS"}],
            "portfolio_transactions": [{"symbol": "RSLS", "unit_price": 5.66}],
            "current_market_data": [{"company_id": 3159, "current_price": 15.00}],
            # Poisoned history close must NOT raise the anchor above the tx price.
            "price_history": [
                {"company_id": 3159, "price_date": "2021-07-19", "close_price": 50000.0},
            ],
        })
        repo = _make_gate_repo(client)

        anchors = _run(repo._build_price_plausibility_anchors([3159]))

        # max(tx 5.66, current 15.00) = 15.00; the 50000 history row is ignored.
        assert anchors == {3159: 15.00}

    def test_tx_anchor_without_current_quote(self):
        client, _ = _make_gate_client({
            "companies": [{"company_id": 3159, "ticker_symbol": "RSLS"}],
            "portfolio_transactions": [{"symbol": "RSLS", "unit_price": 5.66}],
            "current_market_data": [],
        })
        repo = _make_gate_repo(client)

        anchors = _run(repo._build_price_plausibility_anchors([3159]))

        assert anchors == {3159: 5.66}

    def test_anchorless_falls_back_to_current_then_history(self):
        client, _ = _make_gate_client({
            "companies": [
                {"company_id": 7, "ticker_symbol": "NEWCO"},
                {"company_id": 8, "ticker_symbol": "OLDCO"},
            ],
            "portfolio_transactions": [],
            "current_market_data": [{"company_id": 7, "current_price": 12.5}],
            "price_history": [
                {"company_id": 8, "price_date": "2025-01-31", "close_price": 9.75},
            ],
        })
        repo = _make_gate_repo(client)

        anchors = _run(repo._build_price_plausibility_anchors([7, 8]))

        assert anchors == {7: 12.5, 8: 9.75}

    def test_cold_start_no_ground_truth_is_none(self):
        client, _ = _make_gate_client({
            "companies": [{"company_id": 9, "ticker_symbol": "GHOST"}],
            "portfolio_transactions": [],
            "current_market_data": [],
            "price_history": [],
        })
        repo = _make_gate_repo(client)

        anchors = _run(repo._build_price_plausibility_anchors([9]))

        assert anchors == {9: None}


# ---------------------------------------------------------------------------
# _apply_price_plausibility_gate
# ---------------------------------------------------------------------------

class TestApplyPricePlausibilityGate:
    def _repo(self, tables):
        client, _ = _make_gate_client(tables)
        repo = _make_gate_repo(client)
        repo.increment_price_failures = AsyncMock()
        return repo

    def test_rejects_close_above_anchor_times_ratio(self):
        repo = self._repo({
            "companies": [{"company_id": 3159, "ticker_symbol": "RSLS"}],
            "portfolio_transactions": [{"symbol": "RSLS", "unit_price": 5.66}],
            "current_market_data": [],
        })
        rows = [
            {"company_id": 3159, "price_date": "2021-07-19", "close_price": 835194.0},
            {"company_id": 3159, "price_date": "2021-08-19", "close_price": 835194.0},
        ]

        accepted, rejected = _run(repo._apply_price_plausibility_gate(rows))

        assert accepted == []
        assert rejected == {3159: 2}
        # Gate — not the scheduler — counts the failure; scheduler must not double it.
        repo.increment_price_failures.assert_awaited_once_with(3159)

    def test_accepts_high_priced_legit_close(self):
        repo = self._repo({
            "companies": [{"company_id": 10, "ticker_symbol": "LEGIT"}],
            "portfolio_transactions": [{"symbol": "LEGIT", "unit_price": 15.00}],
            "current_market_data": [],
        })
        rows = [{"company_id": 10, "price_date": "2025-01-31", "close_price": 1450.0}]

        accepted, rejected = _run(repo._apply_price_plausibility_gate(rows))

        assert accepted == rows
        assert rejected == {}
        repo.increment_price_failures.assert_not_awaited()

    def test_anchorless_rows_accepted_and_flagged_low_confidence(self):
        repo = self._repo({
            "companies": [{"company_id": 9, "ticker_symbol": "GHOST"}],
            "portfolio_transactions": [],
            "current_market_data": [],
            "price_history": [],
        })
        rows = [{"company_id": 9, "price_date": "2025-01-31", "close_price": 5.0}]

        accepted, rejected = _run(repo._apply_price_plausibility_gate(rows))

        assert accepted == rows
        assert rejected == {}
        repo.increment_price_failures.assert_not_awaited()

    def test_gate_disabled_passthrough(self, monkeypatch):
        monkeypatch.setattr("config.settings.ENABLE_PRICE_PLAUSIBILITY_GATE", False)
        client, _ = _make_gate_client({
            "companies": [{"company_id": 3159, "ticker_symbol": "RSLS"}],
            "portfolio_transactions": [{"symbol": "RSLS", "unit_price": 5.66}],
            "current_market_data": [],
        })
        repo = _make_gate_repo(client)
        rows = [{"company_id": 3159, "price_date": "2021-07-19", "close_price": 835194.0}]

        accepted, rejected = _run(repo._apply_price_plausibility_gate(rows))

        assert accepted == rows
        assert rejected == {}


# ---------------------------------------------------------------------------
# upsert_price_history wiring
# ---------------------------------------------------------------------------

class TestUpsertPriceHistoryGateWiring:
    def test_all_rows_rejected_returns_zero_count_and_gate_rejected(self):
        client, _ = _make_gate_client({
            "companies": [{"company_id": 3159, "ticker_symbol": "RSLS"}],
            "portfolio_transactions": [{"symbol": "RSLS", "unit_price": 5.66}],
            "current_market_data": [],
        })
        repo = _make_gate_repo(client)
        repo.increment_price_failures = AsyncMock()
        rows = [
            {"company_id": 3159, "price_date": "2021-07-19",
             "close_price": 835194.0, "open_price": None, "high_price": None,
             "low_price": None, "volume": None, "data_source": "defeatbeta"},
        ]

        result = _run(repo.upsert_price_history(rows))

        assert result == {"count": 0, "gate_rejected": {3159: 1}}
        # Rejected rows never reach conflict detection or upsert: price_history
        # is neither queried nor written for a fully-rejected batch.
        assert "price_history" not in {c.args[0] for c in client.table.call_args_list}

    def test_accepted_rows_are_upserted(self):
        client, _ = _make_gate_client({
            "companies": [{"company_id": 10, "ticker_symbol": "LEGIT"}],
            "portfolio_transactions": [{"symbol": "LEGIT", "unit_price": 15.00}],
            "current_market_data": [],
        })
        repo = _make_gate_repo(client)
        rows = [
            {"company_id": 10, "price_date": "2025-01-31", "close_price": 1450.0,
             "open_price": 1400.0, "high_price": 1500.0, "low_price": 1390.0,
             "volume": 1000, "data_source": "defeatbeta"},
        ]

        result = _run(repo.upsert_price_history(rows))

        assert result["count"] == 1
        assert result["gate_rejected"] == {}
        assert any(c.args[0] == "price_history" for c in client.table.call_args_list)


# ---------------------------------------------------------------------------
# increment_price_failures
# ---------------------------------------------------------------------------

class TestIncrementPriceFailures:
    async def test_increments_existing_counter(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.return_value = MagicMock(data=[{"consecutive_price_failures": 3}])
        repo = _make_gate_repo(mock_supabase_client)

        await repo.increment_price_failures(3159)

        calls = table.update.call_args_list
        assert calls and calls[0].args[0].get("consecutive_price_failures") == 4

    async def test_starts_at_one_when_no_current_value(self, mock_supabase_client):
        table = mock_supabase_client.table.return_value
        table.execute.return_value = MagicMock(data=[])
        repo = _make_gate_repo(mock_supabase_client)

        await repo.increment_price_failures(3159)

        calls = table.update.call_args_list
        assert calls and calls[0].args[0].get("consecutive_price_failures") == 1


# ---------------------------------------------------------------------------
# check_snapshot_spike rewrite
# ---------------------------------------------------------------------------

class TestCheckSnapshotSpikeRewrite:
    def test_deposit_masked_change_is_not_a_spike(self):
        prev = {"snapshot_date": "2026-08-18", "total_value": 1000.0, "net_deposits": 5000.0}
        curr = {"snapshot_date": "2026-08-19", "total_value": 1250.0, "net_deposits": 5250.0}

        assert check_snapshot_spike(prev, curr, threshold=0.20) is None

    def test_change_exceeding_threshold_is_flagged_with_unexplained(self):
        prev = {"snapshot_date": "2026-08-18", "total_value": 1000.0, "net_deposits": 5000.0}
        curr = {"snapshot_date": "2026-08-19", "total_value": 1500.0, "net_deposits": 5200.0}

        spike = check_snapshot_spike(prev, curr, threshold=0.20)

        assert spike is not None
        assert spike["unexplained"] == 300.0   # 500 change - 200 deposits
        assert spike["deposits"] == 200.0
        assert spike["unexplained_pct"] == 30.0
        assert "message" in spike  # callers read spike["message"]

    def test_small_change_within_threshold_no_spike(self):
        prev = {"snapshot_date": "2026-08-18", "total_value": 1000.0, "net_deposits": 5000.0}
        curr = {"snapshot_date": "2026-08-19", "total_value": 1100.0, "net_deposits": 5100.0}

        assert check_snapshot_spike(prev, curr, threshold=0.20) is None

    def test_nonpositive_previous_total_no_spike(self):
        prev = {"snapshot_date": "2026-08-18", "total_value": 0.0, "net_deposits": 0.0}
        curr = {"snapshot_date": "2026-08-19", "total_value": 9999.0, "net_deposits": 0.0}

        assert check_snapshot_spike(prev, curr, threshold=0.20) is None


# ---------------------------------------------------------------------------
# compute_daily_snapshots spike policy
# ---------------------------------------------------------------------------

class TestComputeDailySnapshotsSpikePolicy:
    async def test_spike_withholds_the_write_instead_of_carrying_forward(
        self, monkeypatch
    ):
        import application.jobs.portfolio_snapshot_job as job_mod
        from config import settings

        monkeypatch.setattr(settings, "ENABLE_EVENT_REPLAY_SNAPSHOTS", False)
        monkeypatch.setattr(settings, "ENABLE_FX_CONVERSION", False)
        monkeypatch.setattr(settings, "SNAPSHOT_SPIKE_THRESHOLD", 0.20)

        prev = {
            "snapshot_date": "2026-08-18",
            "total_value": 244.0,
            "holdings_market_value": 244.0,
            "cash_balance": 0.0,
            "holdings_json": [{"symbol": "RSLS", "quantity": 43.2}],
            "net_deposits": 1000.0,
        }

        snapshots_repo = MagicMock()
        snapshots_repo.get_previous_snapshot.return_value = prev
        snapshots_repo.get_last_snapshot_date.return_value = date(2026, 8, 18)
        snapshots_repo.get_first_snapshot_date.return_value = date(2021, 1, 1)
        snapshots_repo.get_missing_dates.return_value = []
        upsert_calls = []
        snapshots_repo.upsert_snapshot = MagicMock(side_effect=lambda row: upsert_calls.append(row))

        portfolio_repo = MagicMock()
        portfolio_repo.get_user_accounts_all.return_value = [{"account_id": 1, "currency": "CAD"}]
        portfolio_repo.get_holdings_for_accounts.return_value = [
            {"account_id": 1, "company_id": 3159, "symbol": "RSLS", "quantity": 43.2,
             "exchange_override": None, "first_purchase_date": "2021-07-19"},
        ]
        portfolio_repo.get_company_names.return_value = []
        portfolio_repo.get_company_currencies.return_value = []
        portfolio_repo.get_companies_info.return_value = []
        portfolio_repo.get_all_prices_historical.return_value = {}
        portfolio_repo.get_cash_balance.return_value = 0.0
        portfolio_repo.get_net_deposits.return_value = 1000.0

        financial_repo = MagicMock()
        financial_repo.get_latest_prices = AsyncMock(return_value={})

        inflated = {
            "account_id": 1,
            "snapshot_date": "2026-08-19",
            "total_value": 36_000_000.0,   # RSLS-style garbage total
            "holdings_market_value": 36_000_000.0,
            "cash_balance": 0.0,
            "holdings_json": [{"symbol": "RSLS", "quantity": 43.2}],
            "net_deposits": 1000.0,
            "data_quality_flag": "OK",
        }

        with (
            patch.object(job_mod, "PortfolioRepository", return_value=portfolio_repo),
            patch.object(job_mod, "SupabaseFinancialRepository", return_value=financial_repo),
            patch.object(job_mod, "PortfolioSnapshotsRepository", return_value=snapshots_repo),
            patch.object(job_mod, "build_snapshot_row", return_value=dict(inflated)),
        ):
            await job_mod.compute_daily_snapshots()

        assert upsert_calls == [], (
            "a 36M spike must not be persisted, and must not be laundered into a "
            "row carrying the previous day's values under the spike date either"
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async method via asyncio.run (works even from sync pytest tests)."""
    import asyncio
    return asyncio.run(coro)
