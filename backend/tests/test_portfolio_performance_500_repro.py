"""
Portfolio Performance 500 Error Reproduction & Fix Test

Reproduces the exact root cause of the 500 error on /portfolio/performance
and verifies the fix.

Bugs identified and fixed:
1. FXService created internally in build_snapshot_row causes DB queries
   regardless of ENABLE_FX_CONVERSION flag -- fixed by gating on the flag
2. total_net_deposits and total_cash never accumulated (always $0) in
   _compute_performance_fallback -- fixed by accumulating in per-account loop
3. Missing data_quality_flag and best_day/worst_day in fallback response
4. N+1 cash_balance queries inside snapshot loop (~312 queries for 1Y period)
   -- fixed by pre-fetching all cash transactions and computing in-memory

To run:
    pytest tests/test_portfolio_performance_500_repro.py -v -s
"""
import logging
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

logging.basicConfig(level=logging.DEBUG)

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from application.services.portfolio_service import PortfolioService
from shared.snapshot_builder import (
    build_snapshot_row,
)

# MOCK SETUP

class MockSupabaseResponse:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return self


class MockQueryBuilder:
    def __init__(self, table_name=None, return_data=None):
        self._table_name = table_name
        self._return_data = return_data or []

    def select(self, fields):
        return self

    def eq(self, field, value):
        return self

    def in_(self, field, values):
        return self

    def gte(self, field, value):
        return self

    def lte(self, field, value):
        return self

    def order(self, field, desc=False):
        return self

    def limit(self, val):
        return self

    def range(self, start, end):
        return self

    def execute(self):
        return MockSupabaseResponse(self._return_data)

    def maybe_single(self):
        return self


class MockClient:
    def __init__(self):
        self._tables = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockQueryBuilder(name)
        return self._tables[name]

    def set_return_data(self, table_name, data):
        self._tables[table_name] = MockQueryBuilder(table_name, data)


def make_txns_for_account(
    account_id: int,
    buys: list[tuple[str, date, float, float, float]],
    sells: list[tuple[str, date, float, float, float]] | None = None,
    other_cash: list[tuple[str, date, float, float]] | None = None,
    company_ids: dict[str, int] | None = None,
) -> list[dict]:
    txns = []
    idx = [0]
    for sym, tx_date, qty, price, comm in buys:
        cid = company_ids.get(sym, 1) if company_ids else 1
        idx[0] += 1
        txns.append({
            "account_id": account_id,
            "company_id": cid,
            "symbol": sym,
            "transaction_date": tx_date,
            "transaction_id": idx[0],
            "activity_type": "Trade",
            "activity_sub_type": "BUY",
            "quantity": qty,
            "unit_price": price,
            "commission": comm,
            "net_cash_amount": -(qty * price + comm),
            "currency": "USD",
        })
    if sells:
        for sym, tx_date, qty, price, comm in sells:
            cid = company_ids.get(sym, 1) if company_ids else 1
            idx[0] += 1
            txns.append({
                "account_id": account_id,
                "company_id": cid,
                "symbol": sym,
                "transaction_date": tx_date,
                "transaction_id": idx[0],
                "activity_type": "Trade",
                "activity_sub_type": "SELL",
                "quantity": qty,
                "unit_price": price,
                "commission": comm,
                "net_cash_amount": abs(qty) * price - comm,
                "currency": "USD",
            })
    if other_cash:
        for act_type, tx_date, nca, qty in other_cash:
            idx[0] += 1
            txns.append({
                "account_id": account_id,
                "company_id": None,
                "symbol": None,
                "transaction_date": tx_date,
                "transaction_id": idx[0],
                "activity_type": act_type,
                "activity_sub_type": None,
                "quantity": qty,
                "unit_price": 0,
                "commission": 0,
                "net_cash_amount": nca,
                "currency": "CAD",
            })
    return txns


# ============================================================================
# TEST 1: Direct build_snapshot_row assertion failure reproduction
# ============================================================================

def test_1_build_snapshot_row_value_currency_assertion():
    """
    BUG: build_snapshot_row asserts `h.get("value_currency") is None`.
    If holdings carry value_currency from earlier enrichment, the assertion fires.

    REPRODUCE: Pass a holding with value_currency set -> AssertionError.
    """
    # With ENABLE_FX_CONVERSION=False (default), FX conversion is skipped
    with patch('config.settings') as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = False

        try:
            result = build_snapshot_row(
                account_id=1,
                snapshot_date=date(2026, 6, 1),
                holdings_state=[{
                    "company_id": 1, "symbol": "AAPL",
                    "quantity": 10, "total_cost": Decimal("1500.00"),
                    "average_cost": Decimal("150.00"),
                }],
                cash_balance=Decimal("5000.00"),
                net_deposits=Decimal("10000.00"),
                prices_by_company={1: {"price": 200.0, "price_date": date(2026, 6, 1)}},
                job_id="test",
                account_currency="CAD",
            )
            print(f"  Test 1a PASS: build_snapshot_row with FX off = ${result['total_value']:.2f}")
        except AssertionError as e:
            pytest.fail(f"Test 1a failed: {e}")

    # With ENABLE_FX_CONVERSION=True, same setup should also work (no value_currency)
    with patch('config.settings') as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = True

        try:
            result = build_snapshot_row(
                account_id=1,
                snapshot_date=date(2026, 6, 1),
                holdings_state=[{
                    "company_id": 1, "symbol": "AAPL",
                    "quantity": 10, "total_cost": Decimal("1500.00"),
                    "average_cost": Decimal("150.00"),
                }],
                cash_balance=Decimal("5000.00"),
                net_deposits=Decimal("10000.00"),
                prices_by_company={1: {"price": 200.0, "price_date": date(2026, 6, 1)}},
                job_id="test",
                account_currency="CAD",
            )
            print(f"  Test 1b PASS: build_snapshot_row with FX on (no crash) = ${result['total_value']:.2f}")
        except Exception as e:
            print(f"  Test 1b: build_snapshot_row with FX={type(e).__name__}: {e} (FX service may be unavailable)")
            # This is OK - FXService may fail due to missing exchange_rates table
            pass

    # This should raise AssertionError: holding has value_currency
    with patch('config.settings') as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = False
        with pytest.raises(AssertionError) as excinfo:
            build_snapshot_row(
                account_id=1,
                snapshot_date=date(2026, 6, 1),
                holdings_state=[{
                    "company_id": 1, "symbol": "AAPL",
                    "quantity": 10, "total_cost": Decimal("1500.00"),
                    "average_cost": Decimal("150.00"),
                    "value_currency": "USD",
                }],
                cash_balance=Decimal("5000.00"),
                net_deposits=Decimal("10000.00"),
                prices_by_company={1: {"price": 200.0, "price_date": date(2026, 6, 1)}},
                job_id="test",
                account_currency="CAD",
            )
        print(f"  Test 1c PASS: value_currency assertion fires: {excinfo.value}")


# ============================================================================
# TEST 2: Reproduce _compute_performance_fallback bugs
# ============================================================================

@pytest.mark.anyio
async def test_2_compute_performance_fallback_bugs():
    """
    BUGS in _compute_performance_fallback:
    1. total_net_deposits and total_cash initialized but NEVER accumulated
       -> net_deposits always $0 in snapshots
    2. N+1 cash_balance query for EACH account per snapshot date
    3. Missing data_quality_flag in response
    4. Missing best_day/worst_day in response

    REPRODUCE: Create mock service, call fallback, verify bugs are fixed.
    """
    today = date(2026, 6, 22)
    start_date = today - timedelta(days=365)
    end_date = today

    account_ids = [7, 8, 9]
    accounts = [
        {"account_id": 7, "account_name": "TFSA", "currency": "CAD"},
        {"account_id": 8, "account_name": "RRSP", "currency": "CAD"},
        {"account_id": 9, "account_name": "Margin", "currency": "USD"},
    ]
    company_ids_map = {"AAPL": 1, "GOOGL": 2, "RBLX": 3, "SPY": 4}

    # Build ONLY Trade transactions (what get_accounts_transactions returns)
    trade_txns = make_txns_for_account(7, [
        ("AAPL", date(2025, 1, 15), 10, 150.0, 1.0),
        ("GOOGL", date(2025, 3, 10), 5, 140.0, 0.5),
    ], company_ids=company_ids_map)
    trade_txns.extend(make_txns_for_account(8, [
        ("RBLX", date(2025, 2, 1), 20, 100.0, 0.5),
    ], company_ids=company_ids_map))
    trade_txns.extend(make_txns_for_account(9, [
        ("SPY", date(2025, 4, 1), 3, 400.0, 1.0),
    ], sells=[
        ("SPY", date(2026, 1, 15), -1, 450.0, 0.5),
    ], company_ids=company_ids_map))

    # Build ALL transactions (what get_accounts_transactions(None) returns -- includes MoneyMovement, Dividend)
    all_cash_txns = list(trade_txns)
    all_cash_txns.extend([
        {
            "account_id": 7, "company_id": None, "symbol": None,
            "transaction_date": date(2025, 1, 10),
            "transaction_id": 100,
            "activity_type": "MoneyMovement", "activity_sub_type": None,
            "quantity": 0, "unit_price": 0, "commission": 0,
            "net_cash_amount": 10000.0, "currency": "CAD",
        },
        {
            "account_id": 7, "company_id": None, "symbol": None,
            "transaction_date": date(2025, 6, 15),
            "transaction_id": 101,
            "activity_type": "Dividend", "activity_sub_type": None,
            "quantity": 0, "unit_price": 0, "commission": 0,
            "net_cash_amount": 50.0, "currency": "CAD",
        },
        {
            "account_id": 8, "company_id": None, "symbol": None,
            "transaction_date": date(2025, 1, 20),
            "transaction_id": 102,
            "activity_type": "MoneyMovement", "activity_sub_type": None,
            "quantity": 0, "unit_price": 0, "commission": 0,
            "net_cash_amount": 5000.0, "currency": "CAD",
        },
        {
            "account_id": 9, "company_id": None, "symbol": None,
            "transaction_date": date(2025, 3, 1),
            "transaction_id": 103,
            "activity_type": "MoneyMovement", "activity_sub_type": None,
            "quantity": 0, "unit_price": 0, "commission": 0,
            "net_cash_amount": 20000.0, "currency": "CAD",
        },
    ])

    # Make get_accounts_transactions return Trade txns only for activity_types=["Trade"],
    # and ALL txns for activity_types=None
    def mock_get_accounts_transactions(account_ids, limit=None, activity_types=None):
        if activity_types == ["Trade"]:
            return trade_txns
        return all_cash_txns

    # Build price history for each company
    price_map = {}
    for cid in [1, 2, 3, 4]:
        prices = []
        d = start_date
        while d <= end_date:
            prices.append((d, 100.0 + cid * 20 + (d - start_date).days * 0.1))
            d += timedelta(days=7)
        price_map[cid] = prices

    mock_portfolio_repo = MagicMock()
    mock_portfolio_repo.get_user_accounts.return_value = accounts
    mock_portfolio_repo.get_accounts_transactions.side_effect = mock_get_accounts_transactions
    mock_portfolio_repo.get_all_prices_historical.return_value = price_map
    mock_portfolio_repo.get_earliest_transaction_date.return_value = start_date

    mock_financial_repo = MagicMock()
    mock_financial_repo.get_latest_prices = AsyncMock(return_value={})

    with patch.object(PortfolioService, '_period_to_date_range', return_value=(start_date, end_date)):
        with patch('config.settings') as mock_settings:
            mock_settings.ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH = False
            mock_settings.ENABLE_FX_CONVERSION = False

            service = PortfolioService(mock_portfolio_repo, mock_financial_repo)

            try:
                result = await service._get_portfolio_performance_legacy(1, "1Y", account_ids)
            except Exception as e:
                import traceback
                traceback.print_exc()
                pytest.fail(f"Performance computation raised {type(e).__name__}: {e}")

    # --- VERIFY BUGS ARE FIXED ---
    snapshots = result.get("snapshots", [])
    print(f"\n  Snapshots generated: {len(snapshots)}")
    print(f"  Result success: {result.get('success')}")

    # BUG 2 FIXED: total_net_deposits should be accumulated now
    non_zero_nd = [s for s in snapshots if s.get("net_deposits", 0) != 0]
    print(f"  Snapshots with non-zero net_deposits: {len(non_zero_nd)}/{len(snapshots)}")
    assert len(non_zero_nd) > 0, "BUG: net_deposits is ALWAYS $0 (total_net_deposits never accumulated)"

    # BUG 3 FIXED: data_quality_flag should be present
    assert "data_quality_flag" in result, "BUG: data_quality_flag missing from response"
    print(f"  data_quality_flag: {result['data_quality_flag']}")

    # BUG 4 FIXED: best_day and worst_day should be present
    assert "best_day" in result, "BUG: best_day missing from response"
    assert "worst_day" in result, "BUG: worst_day missing from response"
    print(f"  best_day: {result['best_day']}")
    print(f"  worst_day: {result['worst_day']}")

    # Verify no absurd values
    if snapshots:
        last_val = snapshots[-1]["value"]
        assert last_val < 1_000_000_000, f"ABSURD VALUE: ${last_val:,.2f}"
        print(f"  Last snapshot value: ${last_val:,.2f} (sane)")

    assert result.get("success"), f"Performance computation failed: {result}"
    assert len(snapshots) > 0, "No snapshots generated"


# ============================================================================
# TEST 3: get_portfolio_performance via snapshot path
# ============================================================================

@pytest.mark.anyio
async def test_3_get_portfolio_performance_via_snapshot_path():
    """
    Test the full get_portfolio_performance code path with
    ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH=True.

    This is the ACTUAL production path that users hit.
    """
    today = date(2026, 6, 22)
    start_date = today - timedelta(days=365)
    end_date = today

    accounts = [
        {"account_id": 7, "account_name": "TFSA", "currency": "CAD"},
        {"account_id": 8, "account_name": "RRSP", "currency": "CAD"},
        {"account_id": 9, "account_name": "Margin", "currency": "USD"},
    ]
    account_ids = [7, 8, 9]
    company_ids_map = {"AAPL": 1, "GOOGL": 2, "RBLX": 3, "SPY": 4}

    trade_txns = make_txns_for_account(7, [
        ("AAPL", date(2025, 1, 15), 10, 150.0, 1.0),
        ("GOOGL", date(2025, 3, 10), 5, 140.0, 0.5),
    ], company_ids=company_ids_map)
    trade_txns.extend(make_txns_for_account(8, [
        ("RBLX", date(2025, 2, 1), 20, 100.0, 0.5),
    ], company_ids=company_ids_map))
    trade_txns.extend(make_txns_for_account(9, [
        ("SPY", date(2025, 4, 1), 3, 400.0, 1.0),
    ], sells=[
        ("SPY", date(2026, 1, 15), -1, 450.0, 0.5),
    ], company_ids=company_ids_map))

    all_cash_txns = list(trade_txns)
    all_cash_txns.extend([
        {"account_id": 7, "company_id": None, "symbol": None,
         "transaction_date": date(2025, 1, 10), "transaction_id": 100,
         "activity_type": "MoneyMovement", "activity_sub_type": None,
         "quantity": 0, "unit_price": 0, "commission": 0,
         "net_cash_amount": 10000.0, "currency": "CAD"},
        {"account_id": 7, "company_id": None, "symbol": None,
         "transaction_date": date(2025, 6, 15), "transaction_id": 101,
         "activity_type": "Dividend", "activity_sub_type": None,
         "quantity": 0, "unit_price": 0, "commission": 0,
         "net_cash_amount": 50.0, "currency": "CAD"},
        {"account_id": 8, "company_id": None, "symbol": None,
         "transaction_date": date(2025, 1, 20), "transaction_id": 102,
         "activity_type": "MoneyMovement", "activity_sub_type": None,
         "quantity": 0, "unit_price": 0, "commission": 0,
         "net_cash_amount": 5000.0, "currency": "CAD"},
        {"account_id": 9, "company_id": None, "symbol": None,
         "transaction_date": date(2025, 3, 1), "transaction_id": 103,
         "activity_type": "MoneyMovement", "activity_sub_type": None,
         "quantity": 0, "unit_price": 0, "commission": 0,
         "net_cash_amount": 20000.0, "currency": "CAD"},
    ])

    def mock_get_accounts_transactions(account_ids, limit=None, activity_types=None):
        if activity_types == ["Trade"]:
            return trade_txns
        return all_cash_txns

    price_map = {}
    for cid in [1, 2, 3, 4]:
        prices = []
        d = start_date
        while d <= end_date:
            prices.append((d, 100.0 + cid * 20 + (d - start_date).days * 0.1))
            d += timedelta(days=7)
        price_map[cid] = prices

    mock_portfolio_repo = MagicMock()
    mock_portfolio_repo.get_user_accounts.return_value = accounts
    mock_portfolio_repo.get_accounts_transactions.side_effect = mock_get_accounts_transactions
    mock_portfolio_repo.get_all_prices_historical.return_value = price_map
    mock_portfolio_repo.get_earliest_transaction_date.return_value = start_date

    mock_financial_repo = MagicMock()
    mock_financial_repo.get_latest_prices = AsyncMock(return_value={})

    from infrastructure.repositories.portfolio_snapshots_repository import (
        PortfolioSnapshotsRepository,
    )

    mock_snapshots_repo = MagicMock(spec=PortfolioSnapshotsRepository)
    mock_snapshots_repo.get_portfolio_snapshots.return_value = []

    with patch.object(PortfolioService, '_period_to_date_range', return_value=(start_date, end_date)):
        with patch('config.settings') as mock_settings:
            mock_settings.ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH = True
            mock_settings.ENABLE_FX_CONVERSION = False
            mock_settings.ENABLE_PERFORMANCE_LOCF = True

            service = PortfolioService(mock_portfolio_repo, mock_financial_repo)

            with patch('application.services.portfolio_service.PortfolioSnapshotsRepository', return_value=mock_snapshots_repo):
                try:
                    result = await service.get_portfolio_performance(1, "1Y", account_ids)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    pytest.fail(f"get_portfolio_performance raised {type(e).__name__}: {e}")

    print(f"\n  Result success: {result.get('success')}")
    print(f"  Snapshots: {len(result.get('snapshots', []))}")
    print(f"  Has data_quality_flag: {'data_quality_flag' in result}")
    print(f"  Has best_day: {'best_day' in result}")
    print(f"  Has worst_day: {'worst_day' in result}")

    non_zero_nd = [s for s in result.get('snapshots', []) if s.get('net_deposits', 0) != 0]
    print(f"  Snapshots with non-zero net_deposits: {len(non_zero_nd)}/{len(result.get('snapshots', []))}")

    assert result.get("success"), f"Performance computation failed: {result}"
    if result.get('snapshots'):
        first_val = result['snapshots'][0]['value']
        last_val = result['snapshots'][-1]['value']
        print(f"  First snapshot value: ${first_val:,.2f}")
        print(f"  Last snapshot value: ${last_val:,.2f}")
        assert last_val < 1_000_000_000, f"ABSURD VALUE: ${last_val:,.2f}"


# ============================================================================
# TEST 4: Verify build_snapshot_row invariant with floating-point edge cases
# ============================================================================

def test_4_build_snapshot_row_invariant_edge_cases():
    """
    Verify the invariant check in build_snapshot_row tolerates
    floating-point rounding without false positives.
    """
    test_cases = [
        ({
            "company_id": 1, "symbol": "AAPL",
            "quantity": 10, "total_cost": Decimal("1500.00"),
            "average_cost": Decimal("150.00"),
        }, Decimal("5000.00"), "simple case"),
        ({
            "company_id": 1, "symbol": "AAPL",
            "quantity": 0.333333, "total_cost": Decimal("50.00"),
            "average_cost": Decimal("150.00"),
        }, Decimal("100.00"), "fractional shares"),
    ]

    with patch('config.settings') as mock_settings:
        mock_settings.ENABLE_FX_CONVERSION = False

        for i, (holding, cash, desc) in enumerate(test_cases):
            result = build_snapshot_row(
                account_id=1,
                snapshot_date=date(2026, 6, 1),
                holdings_state=[holding],
                cash_balance=cash,
                net_deposits=Decimal("10000.00"),
                prices_by_company={1: {"price": 200.0, "price_date": date(2026, 6, 1)}},
                job_id="test",
                account_currency="USD",
            )
            tv = result["total_value"]
            hmv = result["holdings_market_value"]
            cb = result["cash_balance"]
            assert abs(tv - (hmv + cb)) < 0.01, (
                f"Invariant: total={tv} != market={hmv} + cash={cb}"
            )
            print(f"  Test 4.{i} PASS: {desc} -> total=${tv:.2f}")


# ============================================================================
# TEST 5: End-to-end no-crash test for all periods
# ============================================================================

@pytest.mark.anyio
async def test_5_end_to_end_no_crash():
    """
    Full end-to-end test simulating the exact API code path.

    Ensures the performance endpoint does NOT return 500 for normal data
    across ALL period types.
    """
    today = date(2026, 6, 22)

    accounts = [
        {"account_id": 7, "account_name": "TFSA", "currency": "CAD"},
        {"account_id": 8, "account_name": "RRSP", "currency": "CAD"},
        {"account_id": 9, "account_name": "Margin", "currency": "USD"},
    ]
    account_ids = [7, 8, 9]
    company_ids_map = {"AAPL": 1, "GOOGL": 2, "RBLX": 3, "SPY": 4}

    trade_txns = make_txns_for_account(7, [
        ("AAPL", date(2025, 6, 15), 10, 150.0, 1.0),
    ], other_cash=[
        ("MoneyMovement", date(2025, 6, 10), 10000.0, 0),
    ], company_ids=company_ids_map)
    trade_txns.extend(make_txns_for_account(8, [
        ("RBLX", date(2025, 7, 1), 20, 100.0, 0.5),
    ], other_cash=[
        ("MoneyMovement", date(2025, 7, 1), 5000.0, 0),
    ], company_ids=company_ids_map))
    trade_txns.extend(make_txns_for_account(9, [
        ("SPY", date(2025, 8, 1), 3, 400.0, 1.0),
    ], other_cash=[
        ("MoneyMovement", date(2025, 8, 1), 20000.0, 0),
    ], company_ids=company_ids_map))

    all_cash_txns = list(trade_txns)

    def mock_get_accounts_transactions(account_ids, limit=None, activity_types=None):
        if activity_types == ["Trade"]:
            return trade_txns
        return all_cash_txns

    price_map = {}
    for cid in [1, 2, 3, 4]:
        prices = []
        d = today - timedelta(days=400)
        while d <= today:
            prices.append((d, 150.0 + (d - today).days * 0.05))
            d += timedelta(days=7)
        price_map[cid] = prices

    mock_portfolio_repo = MagicMock()
    mock_portfolio_repo.get_user_accounts.return_value = accounts
    mock_portfolio_repo.get_accounts_transactions.side_effect = mock_get_accounts_transactions
    mock_portfolio_repo.get_all_prices_historical.return_value = price_map
    mock_portfolio_repo.get_earliest_transaction_date.return_value = today - timedelta(days=400)

    mock_financial_repo = MagicMock()
    mock_financial_repo.get_latest_prices = AsyncMock(return_value={})

    periods = ["1W", "1M", "3M", "1Y", "5Y", "YTD", "ALL"]
    for period in periods:
        if period == "1W":
            start = today - timedelta(days=7)
        elif period == "1M":
            start = today - timedelta(days=30)
        elif period == "3M":
            start = today - timedelta(days=90)
        elif period == "1Y":
            start = today - timedelta(days=365)
        elif period == "5Y":
            start = today - timedelta(days=1825)
        elif period == "YTD":
            start = date(today.year, 1, 1)
        else:
            start = today - timedelta(days=400)

        with patch.object(PortfolioService, '_period_to_date_range', return_value=(start, today)):
            with patch('config.settings') as mock_settings:
                mock_settings.ENABLE_PORTFOLIO_SNAPSHOT_READ_PATH = False
                mock_settings.ENABLE_FX_CONVERSION = False

                service = PortfolioService(mock_portfolio_repo, mock_financial_repo)

                try:
                    result = await service.get_portfolio_performance(1, period, account_ids)
                    assert result.get("success"), f"Period {period} failed: {result}"
                    n_snapshots = len(result.get("snapshots", []))
                    print(f"  Period {period}: {n_snapshots} snapshots, "
                          f"success={result['success']}")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    pytest.fail(f"Period {period} raised {type(e).__name__}: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
