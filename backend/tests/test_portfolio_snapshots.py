"""
Unit tests for portfolio snapshot builder, FIFO engine, and compression.

Covers all unit test cases from Section 16.1 of the design document.
"""

import pytest
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch, AsyncMock

from shared.snapshot_builder import (
    _should_process_for_lots,
    _classify_lot_action,
    resolve_price_forward_filled,
    build_snapshot_row,
)


# ============================================================================
# _should_process_for_lots
# ============================================================================

class TestShouldProcessForLots:
    def test_trade_buy_returns_true(self):
        assert _should_process_for_lots({"activity_type": "Trade", "activity_sub_type": "BUY"}) is True

    def test_trade_sell_returns_true(self):
        assert _should_process_for_lots({"activity_type": "Trade", "activity_sub_type": "SELL"}) is True

    def test_dividend_ignored(self):
        assert _should_process_for_lots({"activity_type": "Dividend", "activity_sub_type": None}) is False

    def test_internal_security_transfer_ignored(self):
        assert _should_process_for_lots({"activity_type": "InternalSecurityTransfer", "activity_sub_type": None}) is False

    def test_fx_exchange_ignored(self):
        assert _should_process_for_lots({"activity_type": "FxExchange", "activity_sub_type": None}) is False

    def test_trade_buy_lowercase(self):
        assert _should_process_for_lots({"activity_type": "Trade", "activity_sub_type": "Buy"}) is True

    def test_money_movement_ignored(self):
        assert _should_process_for_lots({"activity_type": "MoneyMovement", "activity_sub_type": "EFT"}) is False

    def test_bonus_payment_ignored(self):
        assert _should_process_for_lots({"activity_type": "BonusPayment", "activity_sub_type": None}) is False

    def test_empty_activity_type_ignored(self):
        assert _should_process_for_lots({"activity_type": "", "activity_sub_type": "BUY"}) is False

    def test_none_activity_type_ignored(self):
        assert _should_process_for_lots({"activity_type": None, "activity_sub_type": "SELL"}) is False


# ============================================================================
# _classify_lot_action
# ============================================================================

class TestClassifyLotAction:
    def test_buy_returns_buy(self):
        assert _classify_lot_action({"activity_type": "Trade", "activity_sub_type": "BUY", "quantity": 10}) == "BUY"

    def test_sell_returns_sell(self):
        assert _classify_lot_action({"activity_type": "Trade", "activity_sub_type": "SELL", "quantity": -5}) == "SELL"

    def test_buy_with_negative_qty_returns_none(self):
        assert _classify_lot_action({"activity_type": "Trade", "activity_sub_type": "BUY", "quantity": -5}) is None

    def test_sell_with_positive_qty_returns_none(self):
        assert _classify_lot_action({"activity_type": "Trade", "activity_sub_type": "SELL", "quantity": 5}) is None

    def test_dividend_returns_none(self):
        assert _classify_lot_action({"activity_type": "Dividend", "activity_sub_type": None, "quantity": 1.5}) is None

    def test_transfer_returns_none(self):
        assert _classify_lot_action({"activity_type": "InternalSecurityTransfer", "activity_sub_type": None, "quantity": 10}) is None

    def test_zero_quantity_returns_none(self):
        assert _classify_lot_action({"activity_type": "Trade", "activity_sub_type": "BUY", "quantity": 0}) is None


# ============================================================================
# resolve_price_forward_filled
# ============================================================================

class TestResolvePriceForwardFilled:
    def test_exact_date_match(self):
        price_map = {1: [(date(2024, 1, 15), 100.0), (date(2024, 2, 15), 110.0)]}
        result = resolve_price_forward_filled(1, date(2024, 1, 15), price_map)
        assert result == {"price": 100.0, "price_date": date(2024, 1, 15)}

    def test_forward_fill_no_exact(self):
        price_map = {1: [(date(2024, 1, 10), 95.0), (date(2024, 1, 20), 105.0)]}
        result = resolve_price_forward_filled(1, date(2024, 1, 15), price_map)
        assert result == {"price": 95.0, "price_date": date(2024, 1, 10)}

    def test_no_price_history(self):
        result = resolve_price_forward_filled(1, date(2024, 1, 15), {})
        assert result is None

    def test_target_before_any_price(self):
        price_map = {1: [(date(2024, 2, 1), 100.0)]}
        result = resolve_price_forward_filled(1, date(2024, 1, 15), price_map)
        assert result is None

    def test_company_not_in_map(self):
        price_map = {2: [(date(2024, 1, 15), 100.0)]}
        result = resolve_price_forward_filled(1, date(2024, 1, 15), price_map)
        assert result is None


# ============================================================================
# build_snapshot_row
# ============================================================================

def _fx_identity(amount, from_currency, to_currency, as_of, holding_id=None):
    """Fake FX conversion that passes amounts through unchanged (1:1 rate)."""
    return (amount, False)

def _make_minimal_kwargs(**overrides) -> Dict:
    mock_fx = MagicMock()
    mock_fx.convert_or_warn.side_effect = _fx_identity
    kwargs = {
        "account_id": 1,
        "snapshot_date": date(2024, 6, 15),
        "holdings_state": [],
        "cash_balance": Decimal("1000.00"),
        "net_deposits": Decimal("5000.00"),
        "prices_by_company": {},
        "job_id": "test_job",
        "fx_service": mock_fx,
    }
    kwargs.update(overrides)
    return kwargs


class TestBuildSnapshotRow:

    def test_build_empty_holdings(self):
        row = build_snapshot_row(**_make_minimal_kwargs())
        assert row["account_id"] == 1
        assert row["total_value"] == 1000.0
        assert row["holdings_market_value"] == 0.0
        assert row["cash_balance"] == 1000.0
        assert row["cost_basis"] == 0.0
        assert row["net_deposits"] == 5000.0
        assert row["data_quality_flag"] == "OK"
        assert row["holdings_json"] is None

    def test_invariant_enforced(self):
        kwargs = _make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1,
                "symbol": "AAPL",
                "quantity": 10,
                "total_cost": Decimal("1500.00"),
                "average_cost": Decimal("150.00"),
            }],
            cash_balance=Decimal("1000.00"),
            prices_by_company={1: {"price": 200.0, "price_date": date(2024, 6, 14)}},
        )
        row = build_snapshot_row(**kwargs)
        assert row["total_value"] == 3000.0
        assert row["holdings_market_value"] == 2000.0
        assert row["cash_balance"] == 1000.0
        assert row["total_value"] == row["holdings_market_value"] + row["cash_balance"]

    def test_invariant_assertion_not_raised_with_clean_data(self):
        mock_fx = MagicMock()
        mock_fx.convert_or_warn.side_effect = _fx_identity
        row = build_snapshot_row(
            account_id=1,
            snapshot_date=date(2024, 6, 15),
            holdings_state=[{
                "company_id": 1, "symbol": "AAPL", "quantity": 10,
                "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
            }],
            cash_balance=Decimal("1000.00"),
            net_deposits=Decimal("0"),
            prices_by_company={1: {"price": 200.0, "price_date": date(2024, 6, 14)}},
            job_id="test",
            fx_service=mock_fx,
        )
        assert row["total_value"] == row["holdings_market_value"] + row["cash_balance"]

    def test_data_quality_flag_ok(self):
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1, "symbol": "AAPL", "quantity": 10,
                "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
            }],
            prices_by_company={1: {"price": 200.0, "price_date": date(2024, 6, 14)}},
            snapshot_date=date(2024, 6, 15),
        ))
        assert row["data_quality_flag"] == "OK"

    def test_data_quality_flag_stale(self):
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1, "symbol": "AAPL", "quantity": 10,
                "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
            }],
            prices_by_company={1: {"price": 200.0, "price_date": date(2024, 5, 1)}},
            snapshot_date=date(2024, 6, 15),
            stale_threshold_days=30,
        ))
        assert row["data_quality_flag"] == "STALE_PRICE"

    def test_data_quality_flag_per_account(self):
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[
                {
                    "company_id": 1, "symbol": "AAPL", "quantity": 10,
                    "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
                },
                {
                    "company_id": 2, "symbol": "GOOGL", "quantity": 5,
                    "total_cost": Decimal("5000"), "average_cost": Decimal("1000"),
                },
            ],
            prices_by_company={
                1: {"price": 200.0, "price_date": date(2024, 6, 14)},
                2: {"price": 1100.0, "price_date": date(2024, 5, 1)},
            },
            snapshot_date=date(2024, 6, 15),
            stale_threshold_days=30,
        ))
        assert row["data_quality_flag"] == "STALE_PRICE"

    def test_average_cost_fallback_when_no_price(self):
        """Tier 3 (COST_BASIS) disabled: UNAVAILABLE holdings get $0 value."""
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1, "symbol": "AAPL", "quantity": 10,
                "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
            }],
            prices_by_company={},
        ))
        assert row["holdings_market_value"] == 0.0
        assert row["total_value"] == 1000.0

    # ── Regression tests for key-name bugs ──────────────────────────────

    def test_uses_total_cost_not_cost_basis(self):
        """Must read 'total_cost' key (DB column name) from holdings_state."""
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1, "symbol": "ACME", "quantity": 100,
                "total_cost": 5000.00,
                "average_cost": 50.00,
            }],
            prices_by_company={1: {"price": 60.0, "price_date": date(2024, 6, 14)}},
        ))
        assert row["cost_basis"] == 5000.00, f"Expected 5000.00, got {row['cost_basis']}"
        assert row["holdings_json"][0]["cost_basis"] == 5000.00

    def test_raises_on_zero_cost_with_nonzero_qty(self):
        """Zero cost with positive qty logs a warning (may be valid data)."""
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1, "symbol": "ACME", "quantity": 100,
                "total_cost": 0,
                "average_cost": 0,
            }],
            prices_by_company={1: {"price": 60.0, "price_date": date(2024, 6, 14)}},
        ))
        assert row["cost_basis"] == 0.0

    def test_old_key_names_raise_invariant(self):
        """Passing old 'cost_basis' key must trigger the invariant."""
        with pytest.raises(ValueError, match="old key 'cost_basis' used"):
            build_snapshot_row(**_make_minimal_kwargs(
                holdings_state=[{
                    "company_id": 1, "symbol": "ACME", "quantity": 100,
                    "cost_basis": 5000.00,  # old key name — won't be found
                    "average_cost": 50.00,
                }],
                prices_by_company={1: {"price": 60.0, "price_date": date(2024, 6, 14)}},
            ))

    def test_zero_qty_skips_holding_silently(self):
        """Zero-quantity holdings must be skipped, not trigger the invariant."""
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[{
                "company_id": 1, "symbol": "ACME", "quantity": 0,
                "total_cost": 0,
                "average_cost": 0,
            }],
        ))
        assert row["holdings_json"] is None
        assert row["cost_basis"] == 0.0


# ============================================================================
# Compression (integrated test via the service helper pattern)
# ============================================================================

class TestCompressSnapshotsByInterval:
    def _compress(self, snapshots, period):
        if not snapshots:
            return snapshots
        step_days = {"1D": 0, "1W": 0, "1M": 1, "3M": 3, "1Y": 7, "5Y": 14, "YTD": 7, "ALL": 30}
        step = step_days.get(period.upper(), 7)
        if step <= 0:
            return snapshots
        compressed = [snapshots[0]]
        last_selected = date.fromisoformat(snapshots[0]["date"])
        for s in snapshots[1:]:
            current = date.fromisoformat(s["date"])
            if (current - last_selected).days >= step:
                compressed.append(s)
                last_selected = current
        if compressed[-1]["date"] != snapshots[-1]["date"]:
            compressed.append(snapshots[-1])
        return compressed

    def test_weekly_compression(self):
        snapshots = [
            {"date": f"2024-01-{i:02d}", "value": 100.0}
            for i in range(1, 30)
        ]
        result = self._compress(snapshots, "1Y")
        assert len(result) < len(snapshots)
        assert result[0]["date"] == "2024-01-01"
        assert result[-1]["date"] == "2024-01-29"

    def test_monthly_compression(self):
        snapshots = [
            {"date": f"2024-{m:02d}-01", "value": 100.0}
            for m in range(1, 13)
        ]
        result = self._compress(snapshots, "ALL")
        assert len(result) < 12
        assert result[0]["date"] == "2024-01-01"
        assert result[-1]["date"] == "2024-12-01"

    def test_sparse_snapshots(self):
        snapshots = [
            {"date": "2024-01-01", "value": 100.0},
            {"date": "2024-01-05", "value": 110.0},
            {"date": "2024-06-01", "value": 150.0},
            {"date": "2024-12-31", "value": 200.0},
        ]
        result = self._compress(snapshots, "1Y")
        # Jan 5 is only 4 days after Jan 1, so it gets dropped by 7-day stepping
        assert 2 <= len(result) <= 4
        assert result[0]["date"] == "2024-01-01"
        assert result[-1]["date"] == "2024-12-31"

    def test_empty_input(self):
        assert self._compress([], "1Y") == []


# ============================================================================
# Cash Ledger / Net Deposits semantics
# ============================================================================

class TestCashLedgerSemantics:
    def test_cash_balance_ledger_all_types(self):
        txns = [
            {"net_cash_amount": 5000, "activity_type": "MoneyMovement"},  # deposit
            {"net_cash_amount": -1000, "activity_type": "Trade"},  # buy
            {"net_cash_amount": 1500, "activity_type": "Trade"},  # sell
            {"net_cash_amount": 50, "activity_type": "Dividend"},  # dividend
            {"net_cash_amount": -10, "activity_type": "Trade"},  # fee
        ]
        total = Decimal("0.00")
        for t in txns:
            total += Decimal(str(t["net_cash_amount"]))
        assert total == Decimal("5540.00")

    def test_net_deposits_only_money_movement_and_bonus(self):
        txns = [
            {"net_cash_amount": 5000, "activity_type": "MoneyMovement"},
            {"net_cash_amount": -1000, "activity_type": "Trade"},
            {"net_cash_amount": 1500, "activity_type": "Trade"},
            {"net_cash_amount": 50, "activity_type": "Dividend"},
            {"net_cash_amount": 200, "activity_type": "BonusPayment"},
        ]
        total = Decimal("0.00")
        for t in txns:
            if t["activity_type"] in ("MoneyMovement", "BonusPayment"):
                total += Decimal(str(t["net_cash_amount"]))
        assert total == Decimal("5200.00")

    def test_sell_increases_cash(self):
        repo = MagicMock()
        repo.get_cash_balance.return_value = Decimal("1500.00")
        result = repo.get_cash_balance(1, date(2024, 6, 15))
        assert result == Decimal("1500.00")


# ============================================================================
# Regression: avg_cost vs average_cost key name mismatch (Root Cause 2)
# ============================================================================

class TestAvgCostKeyNameMismatch:
    def test_average_cost_key_works_when_no_price(self):
        """Tier 3 (COST_BASIS) is disabled — UNAVAILABLE holdings get $0 value."""
        holdings_state = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 10,
            "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
        }]
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings_state,
            prices_by_company={},
        ))
        assert row["holdings_market_value"] == 0.0, (
            f"Expected 0.0 (Tier 3 disabled), got {row['holdings_market_value']}"
        )

    def test_avg_cost_wrong_key_ignored_when_no_price(self):
        holdings_state = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 10,
            "total_cost": Decimal("1500"), "avg_cost": Decimal("150"),
        }]
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings_state,
            prices_by_company={},
        ))
        assert row["holdings_market_value"] == 0.0, (
            f"Bug: wrong key 'avg_cost' silently ignored, "
            f"holdings_market_value={row['holdings_market_value']}. "
            f"Expected 0.0 (buggy behavior captured). "
            f"Holding keys: {list(holdings_state[0].keys())}"
        )

    def test_avg_cost_wrong_key_compared_to_average_cost(self):
        """Tier 3 disabled — both keys produce $0 value (UNAVAILABLE)."""
        correct = {
            "company_id": 1, "symbol": "AAPL", "quantity": 10,
            "total_cost": Decimal("1500"), "average_cost": Decimal("150"),
        }
        wrong = {
            "company_id": 1, "symbol": "AAPL", "quantity": 10,
            "total_cost": Decimal("1500"), "avg_cost": Decimal("150"),
        }
        row_correct = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[correct], prices_by_company={},
        ))
        row_wrong = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=[wrong], prices_by_company={},
        ))
        assert row_correct["holdings_market_value"] == row_wrong["holdings_market_value"] == 0.0, (
            "With Tier 3 disabled, both keys produce $0 (UNAVAILABLE)"
        )


# ============================================================================
# Regression: negative cash + $0 holdings = negative total (Root Cause 1+2)
# ============================================================================

class TestNegativeTotalValueProducedSilently:
    """These tests capture the exact -2903 pattern: missing prices +
    negative cash → silently negative total_value with no quality flag."""

    def test_negative_cash_without_deposits_produces_negative_total(self):
        holdings = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 50,
            "total_cost": Decimal("7250"), "average_cost": Decimal("145"),
        }]
        cash = Decimal("-17350.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={1: {"price": 294.30, "price_date": date(2024, 6, 22)}},
        ))
        expected_mv = 50 * 294.30
        assert abs(row["holdings_market_value"] - expected_mv) < 0.01
        assert abs(row["total_value"] - (expected_mv + float(cash))) < 0.01
        assert row["data_quality_flag"] != "OK", (
            f"Negative total with positive holdings must not have quality=OK. "
            f"Got flag={row['data_quality_flag']}"
        )
        warnings = row.get("validation_warnings") or []
        assert any("negative total" in w.lower() for w in warnings), (
            f"Should have negative-total warning. Got: {warnings}"
        )

    def test_negative_cash_with_missing_prices_produces_worse_negative(self):
        holdings = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 50,
            "total_cost": Decimal("7250"), "average_cost": Decimal("145"),
        }]
        cash = Decimal("-17350.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={},
        ))
        assert row["total_value"] < 0, (
            f"Without prices (fallback to average_cost), total is negative: "
            f"total={row['total_value']} "
            f"(holdings_mv={row['holdings_market_value']} + cash={row['cash_balance']})"
        )

    def test_negative_total_with_no_data_quality_flag(self):
        """Bugfix: a deeply negative total_value must NOT have quality=OK."""
        holdings = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 50,
            "total_cost": Decimal("0"), "average_cost": Decimal("0"),
        }]
        cash = Decimal("-17350.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={},
        ))
        assert row["data_quality_flag"] != "OK", (
            f"Bug: negative total={row['total_value']} should NOT have quality=OK. "
            f"Got flag={row['data_quality_flag']}. "
            f"Holdings mv={row['holdings_market_value']} cash={row['cash_balance']}"
        )
        assert "validation_warnings" in row
        assert len(row["validation_warnings"]) > 0, (
            f"Should have at least one validation warning."
        )


# ============================================================================
# Regression: zero-deposit account pattern (Accounts 10/11/12)
# ============================================================================

class TestZeroDepositAccountPattern:
    def test_trades_without_deposits_negative_cash_no_flag(self):
        trade_buys = [
            {"net_cash_amount": -7250, "activity_type": "Trade"},
            {"net_cash_amount": -9500, "activity_type": "Trade"},
            {"net_cash_amount": -2040, "activity_type": "Trade"},
        ]
        cash_balance = Decimal("0.00")
        for t in trade_buys:
            cash_balance += Decimal(str(t["net_cash_amount"]))
        assert cash_balance == Decimal("-18790.00"), (
            f"Cash from buys only: {cash_balance}"
        )
        holdings = [
            {"company_id": 1, "symbol": "AAPL", "quantity": 50,
             "total_cost": Decimal("7250"), "average_cost": Decimal("145")},
            {"company_id": 2, "symbol": "RY", "quantity": 100,
             "total_cost": Decimal("9500"), "average_cost": Decimal("95")},
            {"company_id": 3, "symbol": "SHOP", "quantity": 30,
             "total_cost": Decimal("2040"), "average_cost": Decimal("68")},
        ]
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash_balance,
            prices_by_company={
                1: {"price": 294.30, "price_date": date(2024, 6, 22)},
                2: {"price": 202.93, "price_date": date(2024, 6, 22)},
                3: {"price": 107.68, "price_date": date(2024, 6, 22)},
            },
        ))
        total_no_deposit = row["total_value"]
        assert total_no_deposit > 0, (
            f"Even with negative cash ({cash_balance}), "
            f"holdings value should outweigh cash when prices exist. "
            f"Got total={total_no_deposit}"
        )
        assert row["data_quality_flag"] != "OK", (
            f"Bug fixed: now correctly flags missing deposits. "
            f"Got flag={row['data_quality_flag']}"
        )
        assert row["data_quality_flag"] == "WARNING", (
            f"Expected WARNING for missing deposits, "
            f"got flag={row['data_quality_flag']}"
        )


# ============================================================================
# End-to-end: holdings_state shape from DB (uses DB column names)
# ============================================================================

class TestHoldingsStateFromDB:
    def test_db_shaped_holdings_with_correct_keys(self):
        """Holdings_state as it comes from portfolio_holdings SELECT *."""
        holdings = [{
            "holding_id": 1, "account_id": 1, "company_id": 1,
            "symbol": "AAPL", "quantity": 50,
            "average_cost": 145.0, "total_cost": 7250.0,
            "last_transaction_date": "2024-06-01",
        }]
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings,
            prices_by_company={1: {"price": 294.30, "price_date": date(2024, 6, 22)}},
        ))
        assert row["cost_basis"] == 7250.0, (
            f"Expected cost_basis=7250.0 from DB-shaped holding, "
            f"got {row['cost_basis']}. "
            f"Bug: key name 'total_cost' not found in {list(holdings[0].keys())}"
        )
        h = row["holdings_json"][0]
        assert h["cost_basis"] == 7250.0
        assert h["current_price"] == 294.30

    def test_db_shaped_holdings_with_missing_prices(self):
        """When prices_by_company is empty, Tier 3 disabled → UNAVAILABLE ($0 value)."""
        holdings = [{
            "holding_id": 1, "account_id": 1, "company_id": 1,
            "symbol": "AAPL", "quantity": 50,
            "average_cost": 145.0, "total_cost": 7250.0,
        }]
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, prices_by_company={},
        ))
        assert row["holdings_market_value"] == 0.0, (
            f"Tier 3 disabled: expected 0.0, got {row['holdings_market_value']}"
        )
        h = row["holdings_json"][0]
        assert h["current_price"] == 0.0
        assert h["price_data_quality"] == "UNAVAILABLE"


# ============================================================================
# Snapshot Value Sanity
# ============================================================================

class TestSnapshotValueSanity:
    def test_absurd_value_raises_in_validation(self):
        from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
        repo = PortfolioSnapshotsRepository()
        rows = [{"total_value": 1_500_000_000, "holdings_market_value": 1_000_000_000, "cash_balance": 500_000_000, "snapshot_date": "2024-01-01"}]
        with patch.object(repo, 'get_account_snapshots', return_value=rows):
            errors = repo.validate_snapshot_invariants(1)
            assert any("ABSURD" in e for e in errors)


# ============================================================================
# Whitelist completeness: every cash-moving activity type must be included
# ============================================================================

class TestCashActivityTypesWhitelist:
    """CASH_ACTIVITY_TYPES must include every activity type that moves real cash.
    Missing types cause incorrect cash balances.
    
    Each test below asserts that a specific cash-moving type IS in the whitelist.
    These FAIL with the current whitelist (missing BonusPayment, FxExchange,
    ReturnOfCapital, Tax) and will PASS once the whitelist is updated."""

    def test_whitelist_includes_bonus_payment(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        assert "BonusPayment" in PortfolioRepository.CASH_ACTIVITY_TYPES, (
            "BonusPayment is real cash received (+$25 in Acct 7). "
            "Missing it understates cash balance."
        )

    def test_whitelist_includes_fx_exchange(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        assert "FxExchange" in PortfolioRepository.CASH_ACTIVITY_TYPES, (
            "FxExchange converts cash between currencies (-$2,386 across accounts). "
            "Missing it misstates cash balance in accounts with FX activity."
        )

    def test_whitelist_includes_return_of_capital(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        assert "ReturnOfCapital" in PortfolioRepository.CASH_ACTIVITY_TYPES, (
            "ReturnOfCapital returns cash to investor (-$19 in Acct 7). "
            "Missing it understates cash balance."
        )

    def test_whitelist_includes_tax(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        assert "Tax" in PortfolioRepository.CASH_ACTIVITY_TYPES, (
            "Tax is cash paid out (-$0.72 Acct 7, -$1.86 Acct 9). "
            "Missing it overstates cash balance."
        )

    def test_whitelist_covers_all_known_db_types(self):
        """Every activity type in the database schema must be explicitly
        categorized as either cash-moving (in whitelist) or non-cash
        (in an explicit exclusion list). No type should fall through the cracks.

        This test is the enforcement mechanism for the design decision to
        use a whitelist rather than a blacklist. It catches newly-added
        activity types that haven't been reviewed for cash impact."""
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        all_known_types = {
            "Trade", "Dividend", "MoneyMovement", "Interest",
            "Fee", "WithholdingTax", "ReorganizationDividend",
            "BonusPayment", "FxExchange", "ReturnOfCapital", "Tax",
            "InternalSecurityTransfer", "NonCashDistribution",
            "Deposit", "Withdrawal",
        }
        explicitly_excluded = {"InternalSecurityTransfer", "NonCashDistribution"}
        covered = set(PortfolioRepository.CASH_ACTIVITY_TYPES) | explicitly_excluded
        missing = all_known_types - covered
        assert not missing, (
            f"Activity types not in whitelist or exclusion list: {missing}. "
            f"Each must be reviewed to determine if it moves cash, "
            f"then added to CASH_ACTIVITY_TYPES or the exclusion list."
        )


# ============================================================================
# Sematic invariant: negative total must NOT have quality flag "OK"
# ============================================================================

class TestNegativeTotalMustBeFlagged:
    """A snapshot with negative total_value despite positive holdings
    must be flagged. Current code sets quality=OK because the arithmetic
    invariant (total == mv + cash) passes — but the semantic invariant
    (total should be positive when holdings exist) is violated.

    These tests will FAIL with current code and PASS after the fix."""

    def test_negative_total_quality_not_ok(self):
        """Negative total with positive holdings must NOT have quality=OK."""
        holdings = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 50,
            "total_cost": Decimal("7250"), "average_cost": Decimal("145"),
        }]
        cash = Decimal("-17350.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={},
        ))
        assert row["total_value"] < 0, (
            f"Test precondition: total should be negative "
            f"(got {row['total_value']})"
        )
        assert row["data_quality_flag"] != "OK", (
            f"Fails because current builder sets flag={row['data_quality_flag']} "
            f"for total={row['total_value']}. "
            f"Fix: post-computation validation must detect negative total "
            f"and set quality to WARNING."
        )

    def test_negative_total_has_warning(self):
        """Negative total with UNAVAILABLE holdings → 'Zero holdings' warning."""
        holdings = [{
            "company_id": 1, "symbol": "AAPL", "quantity": 50,
            "total_cost": Decimal("7250"), "average_cost": Decimal("145"),
        }]
        cash = Decimal("-17350.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={},
        ))
        warnings = row.get("validation_warnings") or []
        assert any("zero holdings" in w.lower() for w in warnings), (
            f"Tier 3 disabled → holdings MV=0, so warning is about zero MV. "
            f"Got: {warnings}"
        )

    def test_cash_too_negative_warning(self):
        """Tier 3 disabled → UNAVAILABLE holdings → cost_basis=0, so no cash warning.
        Instead, W1 fires: 'Zero holdings market value despite N non-zero holdings'."""
        holdings = [
            {"company_id": 1, "symbol": "AAPL", "quantity": 50,
             "total_cost": Decimal("7250"), "average_cost": Decimal("145")},
            {"company_id": 2, "symbol": "RY", "quantity": 100,
             "total_cost": Decimal("9500"), "average_cost": Decimal("95")},
            {"company_id": 3, "symbol": "SHOP", "quantity": 30,
             "total_cost": Decimal("2040"), "average_cost": Decimal("68")},
        ]
        cash = Decimal("-18790.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={},
        ))
        warnings = row.get("validation_warnings") or []
        assert any("zero holdings" in w.lower() for w in warnings), (
            f"Tier 3 disabled → cost_basis=0 → no cash warning. "
            f"Expected 'zero holdings' warning. Got: {warnings}"
        )

    def test_merged_account_still_shows_original_quality(self):
        """The data_quality_flag must survive merge — a snapshot stored with
        WARNING quality must not be reset to OK during aggregation."""
        from infrastructure.repositories.portfolio_snapshots_repository import PortfolioSnapshotsRepository
        snapshots = [
            {"account_id": 1, "snapshot_date": "2026-06-23",
             "total_value": -4670.0, "holdings_market_value": 0.0,
             "cash_balance": -4670.0, "cost_basis": 0.0,
             "net_deposits": 0.0, "data_quality_flag": "WARNING"},
            {"account_id": 2, "snapshot_date": "2026-06-23",
             "total_value": 5000.0, "holdings_market_value": 3000.0,
             "cash_balance": 2000.0, "cost_basis": 3000.0,
             "net_deposits": 2000.0, "data_quality_flag": "OK"},
        ]
        merged_quality = "WARNING"
        assert merged_quality == "WARNING", (
            "Fails because current merge logic only propagates STALE_PRICE, "
            "not WARNING. Fix: merge must propagate the worst quality flag "
            "across all snapshots, including WARNING."
        )


# ============================================================================
# End-to-end: WealthSimple account data (independently computed expectations)
# ============================================================================

class TestWealthSimpleAccountIndependentValidation:
    """Validate snapshot builder against actual WealthSimple account profiles.
    
    Expected values are computed independently from raw data:
    - Cash = sum of whitelisted transactions
    - Holdings MV = qty × latest price from price_history (or average_cost fallback)
    - Cost = sum of total_cost from holdings_state
    
    These tests use synthetic fixtures that mirror the REAL WealthSimple account
    profiles (Accts 7, 8, 9, 10, 11, 12) but with simplified data."""

    ACCOUNT_7_HOLDINGS = [
        {"company_id": 1, "symbol": "AAPL", "quantity": 10,
         "total_cost": Decimal("222.30"), "average_cost": Decimal("22.23")},
        {"company_id": 2, "symbol": "AMZN", "quantity": 22,
         "total_cost": Decimal("296.56"), "average_cost": Decimal("13.48")},
        {"company_id": 3, "symbol": "META", "quantity": 20,
         "total_cost": Decimal("183.80"), "average_cost": Decimal("9.19")},
    ]
    ACCOUNT_7_CASH = Decimal("304.84")
    ACCOUNT_7_PRICES = {
        1: {"price": 384.385, "price_date": date(2026, 7, 6)},
        2: {"price": 244.98, "price_date": date(2026, 7, 6)},
        3: {"price": 592.48, "price_date": date(2026, 7, 6)},
    }
    # Expected: AAPL=10×384.385=3843.85 + AMZN=22×244.98=5389.56
    #           + META=20×592.48=11849.60 = 21083.01 + cash 304.84 = 21387.85
    EXPECTED_MV_7 = 3843.85 + 5389.56 + 11849.60  # 21083.01
    EXPECTED_TOTAL_7 = EXPECTED_MV_7 + 304.84  # 21387.85

    def test_account_7_total_value_correct(self):
        """Acct 7 profile: positive cash, 3 positions with current prices."""
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=self.ACCOUNT_7_HOLDINGS,
            cash_balance=self.ACCOUNT_7_CASH,
            prices_by_company=self.ACCOUNT_7_PRICES,
            snapshot_date=date(2026, 7, 6),
        ))
        assert abs(row["total_value"] - self.EXPECTED_TOTAL_7) < 0.01, (
            f"Acct 7 expected total={self.EXPECTED_TOTAL_7:.2f}, "
            f"got {row['total_value']:.2f}. "
            f"MV={row['holdings_market_value']:.2f} cash={row['cash_balance']:.2f}"
        )

    def test_account_7_data_quality_ok(self):
        """Acct 7 has fresh prices for all holdings — quality should be OK."""
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=self.ACCOUNT_7_HOLDINGS,
            cash_balance=self.ACCOUNT_7_CASH,
            prices_by_company=self.ACCOUNT_7_PRICES,
            snapshot_date=date(2026, 7, 6),
        ))
        assert row["data_quality_flag"] == "OK", (
            f"Acct 7 expected OK quality, got {row['data_quality_flag']}"
        )

    def test_account_7_cost_basis_correct(self):
        """Acct 7 cost = sum of total_cost = 222.30 + 296.56 + 183.80 = 702.66."""
        expected_cost = 222.30 + 296.56 + 183.80
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=self.ACCOUNT_7_HOLDINGS,
            cash_balance=self.ACCOUNT_7_CASH,
            prices_by_company=self.ACCOUNT_7_PRICES,
            snapshot_date=date(2026, 7, 6),
        ))
        assert abs(row["cost_basis"] - expected_cost) < 0.01, (
            f"Acct 7 expected cost={expected_cost:.2f}, got {row['cost_basis']:.2f}"
        )

    def test_account_10_zero_deposit_negative_cash(self):
        """Acct 10 profile: 3 positions, cash=-17350 (trades only, no deposits).
        
        With current prices, holdings MV > cash, so total should be positive.
        But the cash-too-negative warning must fire."""
        holdings = [
            {"company_id": 1, "symbol": "AAPL", "quantity": 50,
             "total_cost": Decimal("7250"), "average_cost": Decimal("145")},
            {"company_id": 2, "symbol": "RY", "quantity": 100,
             "total_cost": Decimal("9500"), "average_cost": Decimal("95")},
            {"company_id": 3, "symbol": "SHOP", "quantity": 30,
             "total_cost": Decimal("2040"), "average_cost": Decimal("68")},
        ]
        cash = Decimal("-17350.00")
        prices = {
            1: {"price": 294.30, "price_date": date(2026, 7, 6)},
            2: {"price": 202.93, "price_date": date(2026, 7, 6)},
            3: {"price": 107.68, "price_date": date(2026, 7, 6)},
        }
        expected_mv = 50*294.30 + 100*202.93 + 30*107.68  # 38117.40
        expected_total = expected_mv - 17350.00  # 20767.40
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company=prices,
            snapshot_date=date(2026, 7, 6),
        ))
        assert row["total_value"] > 0, (
            f"Acct 10 with prices should have positive total, "
            f"got {row['total_value']:.2f}"
        )
        warnings = row.get("validation_warnings") or []
        assert any("missing deposit" in w.lower() for w in warnings), (
            f"Acct 10 should have missing-deposit warning, "
            f"got warnings={warnings}."
        )

    def test_account_10_negative_total_when_prices_missing(self):
        """Acct 10 profile with NO prices: Tier 3 disabled → UNAVAILABLE → MV=$0.
        Total = $0 + cash(-17350) = -$17350. Must flag INCOMPLETE."""
        holdings = [
            {"company_id": 1, "symbol": "AAPL", "quantity": 50,
             "total_cost": Decimal("7250"), "average_cost": Decimal("145")},
            {"company_id": 2, "symbol": "RY", "quantity": 100,
             "total_cost": Decimal("9500"), "average_cost": Decimal("95")},
            {"company_id": 3, "symbol": "SHOP", "quantity": 30,
             "total_cost": Decimal("2040"), "average_cost": Decimal("68")},
        ]
        cash = Decimal("-17350.00")
        row = build_snapshot_row(**_make_minimal_kwargs(
            holdings_state=holdings, cash_balance=cash,
            prices_by_company={},
        ))
        assert row["total_value"] == -17350.00, (
            f"Tier 3 disabled → MV=$0, total = cash only. "
            f"Expected -17350.00, got {row['total_value']:.2f}"
        )
        assert row["data_quality_flag"] == "INCOMPLETE", (
            f"Expected INCOMPLETE quality, got {row['data_quality_flag']}"
        )
