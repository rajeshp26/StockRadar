"""
Tests for single-stock holding performance (exists, performance, dividends).

TEST COVERAGE GAP ANALYSIS (2026-06-06)
═════════════════════════════════════════

BUG-01 (total_return formula) was NOT caught because:
  - test_basic_1y_performance mocks _compute_fifo_snapshots with constant
    cost_basis (1800) across ALL snapshots. Since snapshots[0].cost_basis ==
    snapshots[-1].cost_basis, the buggy formula produces the same result as
    the correct formula. The test assertion passed by coincidence.
  - test_multiple_buys and test_buy_and_partial_sell only have ONE snapshot,
    so snapshots[0] == snapshots[-1], hiding the bug entirely.
  - No test asserted total_return using snapshots with VARYING cost_basis.

BUG-03 (YTD regex) was NOT caught because:
  - No test sends period="YTD" to the API route level.

BUG-04 (dividend_pct fallback) was NOT caught because:
  - No test provides dividends with zero cumulative_invested.

REGRESSION TESTS ADDED:
  - test_gain_loss_varying_cost_basis_exposes_bug: Uses 3 snapshots with
    different cost_basis values (simulating buys during period). Asserts
    correct expected values — will FAIL when run against current buggy code.
  - test_gain_loss_partial_sell_varying_cost_basis: Same for sell scenario.
  - test_zero_cumulative_invested_dividend_pct: Asserts 0% when denominator is 0.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from application.services.portfolio_service import PortfolioService


@pytest.fixture
def mock_portfolio_repo():
    repo = MagicMock()
    repo.get_user_accounts.return_value = [
        {"account_id": 1, "account_name": "TFSA", "account_type": "TFSA", "brokerage_name": "Test", "is_active": True},
        {"account_id": 2, "account_name": "RRSP", "account_type": "RRSP", "brokerage_name": "Test", "is_active": True},
    ]
    repo.get_account_transactions.return_value = []
    repo.get_transactions_for_symbol.return_value = []
    repo.get_dividends_for_symbol.return_value = []
    repo.get_user_all_holdings.return_value = [
        {"symbol": "AAPL", "company_id": 1, "quantity": 10, "total_cost": 1500},
        {"symbol": "MSFT", "company_id": 2, "quantity": 5, "total_cost": 2500},
    ]
    repo.get_earliest_transaction_date.return_value = None
    return repo


@pytest.fixture
def mock_financial_repo():
    repo = MagicMock()
    repo.get_company_by_symbol = AsyncMock(return_value=None)
    return repo


@pytest.fixture
def service(mock_portfolio_repo, mock_financial_repo):
    return PortfolioService(mock_portfolio_repo, mock_financial_repo)


class TestCheckHoldingExists:

    def test_exists_symbol_found(self, service, mock_portfolio_repo):
        result = service.check_holding_exists(1, "AAPL")
        assert result is True

    def test_exists_symbol_not_found(self, service, mock_portfolio_repo):
        result = service.check_holding_exists(1, "GOOGL")
        assert result is False

    def test_exists_no_holdings(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_user_all_holdings.return_value = []
        result = service.check_holding_exists(2, "AAPL")
        assert result is False

    def test_exists_case_insensitive(self, service, mock_portfolio_repo):
        result = service.check_holding_exists(1, "aapl")
        assert result is True


@pytest.mark.anyio
class TestGetHoldingPerformance:

    async def test_basic_1y_performance(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 180, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-01-15", "2024-07-15", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
        ):
            mock_fifo.return_value = [
                {"date": "2024-01-15", "value": 1800, "cost_basis": 1800, "net_deposits": 1800},
                {"date": "2024-07-15", "value": 2000, "cost_basis": 1800, "net_deposits": 1800},
                {"date": "2024-12-31", "value": 2200, "cost_basis": 1800, "net_deposits": 1800},
            ]

            with patch('application.services.portfolio_service.supabase') as mock_supa:
                mock_supa.table().select().gte().lte().order().execute.return_value.data = []

                result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        assert result["symbol"] == "AAPL"
        assert len(result["snapshots"]) == 3
        assert result["total_return"] == 400
        assert result["total_return_pct"] == 22.22
        assert result["snapshots"][0]["position_value"] == 1800
        assert result["snapshots"][0]["cost_basis"] == 1800

    async def test_multiple_buys(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 100, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
            {"transaction_date": date(2024, 6, 1), "symbol": "AAPL",
             "quantity": 5, "unit_price": 120, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
        ):
            mock_fifo.return_value = [
                {"date": "2024-12-31", "value": 3300, "cost_basis": 1600, "net_deposits": 1600},
            ]

            with patch('application.services.portfolio_service.supabase') as mock_supa:
                mock_supa.table().select().gte().lte().order().execute.return_value.data = []
                result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        # Cost basis = 10*100 + 5*120 = 1600
        assert result["snapshots"][0]["cost_basis"] == 1600

    async def test_buy_and_partial_sell(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 100, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
            {"transaction_date": date(2024, 6, 1), "symbol": "AAPL",
             "quantity": -3, "unit_price": 150, "commission": 0,
             "activity_sub_type": "SELL", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
        ):
            mock_fifo.return_value = [
                {"date": "2024-12-31", "value": 1750, "cost_basis": 700, "net_deposits": 1000},
            ]

            with patch('application.services.portfolio_service.supabase') as mock_supa:
                mock_supa.table().select().gte().lte().order().execute.return_value.data = []
                result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        assert result["snapshots"][0]["cost_basis"] == 700  # 7 shares * $100

    async def test_stock_not_held_no_transactions(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = []

        with patch('application.services.portfolio_service.supabase') as mock_supa:
            mock_supa.table().select().execute.return_value.data = []
            result = await service.get_holding_performance(1, "GOOGL", "1Y")

        assert result["success"] is True
        assert result["snapshots"] == []
        assert result["total_return"] == 0

    async def test_no_transactions_returns_empty(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = []
        result = await service.get_holding_performance(1, "AAPL", "1Y")
        assert result["success"] is True
        assert result["snapshots"] == []


# ═════════════════════════════════════════════════════════════════════
# REGRESSION TESTS — Expose BUG-01 (Gain/Loss formula) and BUG-04
# ═════════════════════════════════════════════════════════════════════
#
# Why existing tests didn't catch BUG-01:
#   - All existing tests mock _compute_fifo_snapshots with constant
#     cost_basis OR single snapshots, so snapshots[0].cost_basis ==
#     snapshots[-1].cost_basis. The buggy formula:
#       total_return = last_value - snapshots[0]["cost_basis"]
#     produces the same result as the correct formula:
#       total_return = last_value - snapshots[-1]["cost_basis"]
#     ONLY when cost_basis doesn't change across snapshots.
#
# These regression tests use mock data with VARYING cost_basis to
# expose the divergence, and assert the CORRECT expected values.
# ═════════════════════════════════════════════════════════════════════

@pytest.mark.anyio
class TestGetHoldingPerformanceRegression:
    """Regression tests that verify calculation correctness.

    These tests use mock FIFO snapshots with VARYING cost_basis across
    snapshots to verify that BUG-01 (wrong cost_basis index) and BUG-04
    (misleading or 1 fallback) stay fixed.

    The existing tests only use constant cost_basis which could not detect
    the bugs because snapshots[0].cost_basis == snapshots[-1].cost_basis.
    """

    async def test_gain_loss_varying_cost_basis_exposes_bug(self, service, mock_portfolio_repo):
        """
        BUG-01: total_return uses snapshots[0].cost_basis instead of
        snapshots[-1].cost_basis.

        Setup: 3 snapshots with increasing cost_basis (simulating
        additional purchases mid-period).
          - Snap 0: cost_basis = 1000 (position_value = 1500)
          - Snap 1: cost_basis = 1600 (bought more, position_value = 2000)
          - Snap 2: cost_basis = 1600 (position_value = 2500)

        Buggy result:  total_return = 2500 - 1000 = 1500  ← WRONG
        Correct result: total_return = 2500 - 1600 = 900
        """
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 100, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
            {"transaction_date": date(2024, 6, 1), "symbol": "AAPL",
             "quantity": 5, "unit_price": 120, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-01-15", "2024-07-15", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            mock_fifo.return_value = [
                # Snap 0: 10 shares @ $100, value = 10 * 150 = 1500
                {"date": "2024-01-15", "value": 1500, "cost_basis": 1000, "net_deposits": 1000},
                # Snap 1: bought 5 more @ $120, cost_basis changes
                {"date": "2024-07-15", "value": 2000, "cost_basis": 1600, "net_deposits": 1600},
                # Snap 2: end of period, value grew
                {"date": "2024-12-31", "value": 2500, "cost_basis": 1600, "net_deposits": 1600},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        # Buggy formula gives: 2500 - 1000 = 1500 (WRONG)
        # Correct formula:     2500 - 1600 = 900
        assert result["total_return"] == 900, (
            f"BUG-01: Expected total_return=900 (last_value=2500 - last_cost_basis=1600), "
            f"got {result['total_return']}. "
            f"Buggy formula gives {2500 - 1000}=1500 using snapshots[0].cost_basis"
        )

    async def test_gain_loss_partial_sell_varying_cost_basis(self, service, mock_portfolio_repo):
        """
        BUG-01: Same bug, different scenario — partial sell changes cost_basis.

        Setup: 3 snapshots with decreasing cost_basis (simulating partial sell).
          - Snap 0: cost_basis = 1000 (position_value = 1500)
          - Snap 1: cost_basis = 700  (sold 3 shares, position_value = 1050)
          - Snap 2: cost_basis = 700  (position_value = 1400)

        Buggy result:  total_return = 1400 - 1000 = 400   ← WRONG
        Correct result: total_return = 1400 - 700  = 700
        """
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 100, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
            {"transaction_date": date(2024, 6, 1), "symbol": "AAPL",
             "quantity": -3, "unit_price": 150, "commission": 0,
             "activity_sub_type": "SELL", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-01-15", "2024-07-15", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            mock_fifo.return_value = [
                {"date": "2024-01-15", "value": 1500, "cost_basis": 1000, "net_deposits": 1000},
                {"date": "2024-07-15", "value": 1050, "cost_basis": 700, "net_deposits": 1000},
                {"date": "2024-12-31", "value": 1400, "cost_basis": 700, "net_deposits": 1000},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        # Buggy formula gives: 1400 - 1000 = 400  (WRONG)
        # Correct formula:     1400 - 700  = 700
        assert result["total_return"] == 700, (
            f"BUG-01: Expected total_return=700 (last_value=1400 - last_cost_basis=700), "
            f"got {result['total_return']}. "
            f"Buggy formula gives {1400 - 1000}=400 using snapshots[0].cost_basis"
        )

    async def test_total_return_pct_uses_cost_basis_not_price(self, service, mock_portfolio_repo):
        """
        BUG-01: total_return_pct should be relative to cost basis, not
        the change in position value.

        Setup: Single buy, significant price growth.
          - Snap 0: position_value = 1500, cost_basis = 1000
          - Snap 1: position_value = 2500, cost_basis = 1000

        Correct total_return_pct = (2500 - 1000) / 1000 * 100 = 150%
        Buggy total_return_pct = (2500 - 1500) / 1500 * 100 = 66.67%  (price return only)
        """
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 100, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-01-15", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            # position_value = 2500, cost_basis = 1000
            # Gain = 2500 - 1000 = 1500
            # Gain% = 1500/1000 * 100 = 150%
            mock_fifo.return_value = [
                {"date": "2024-01-15", "value": 1500, "cost_basis": 1000, "net_deposits": 1000},
                {"date": "2024-12-31", "value": 2500, "cost_basis": 1000, "net_deposits": 1000},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        # Buggy formula: (2500 - 1500) / 1500 * 100 = 66.67%
        # Correct:       (2500 - 1000) / 1000 * 100 = 150.00%
        assert result["total_return_pct"] == 150.00, (
            f"BUG-01: Expected total_return_pct=150.00%, "
            f"got {result['total_return_pct']}%. "
            f"Buggy formula gives {((2500 - 1500) / 1500 * 100):.2f}% (price return, not cost return)"
        )

    async def test_zero_cumulative_invested_dividend_pct(self, service, mock_portfolio_repo):
        """
        BUG-04: total_dividends_pct uses `or 1` fallback when
        cumulative_invested is 0, producing wildly inflated percentage.
        Should return 0 when denominator is 0.
        """
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 100, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]
        mock_portfolio_repo.get_dividends_for_symbol.return_value = [
            {"symbol": "AAPL", "amount": 50.00, "payment_date": date(2024, 2, 15),
             "fiscal_year": 2024, "fiscal_month": 2, "shares_held": 10},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            # cumulative_invested (net_deposits) = 0 → should give 0%
            mock_fifo.return_value = [
                {"date": "2024-12-31", "value": 1500, "cost_basis": 1000, "net_deposits": 0},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        # Buggy formula: 50 / (0 or 1) * 100 = 5000%  ← WRONG
        # Correct:       0% when cumulative_invested = 0
        assert result["total_dividends_pct"] == 0.0, (
            f"BUG-04: Expected total_dividends_pct=0.0 when cumulative_invested=0, "
            f"got {result['total_dividends_pct']}. "
            f"Buggy formula gives {50 / 1 * 100}=5000% using `or 1` fallback"
        )


@pytest.mark.anyio
class TestGetHoldingDividends:

    async def test_quarterly_aggregation(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_dividends_for_symbol.return_value = [
            {"symbol": "AAPL", "amount": 22.50, "payment_date": date(2024, 2, 15),
             "fiscal_year": 2024, "fiscal_month": 2, "shares_held": 10},
            {"symbol": "AAPL", "amount": 23.00, "payment_date": date(2024, 5, 15),
             "fiscal_year": 2024, "fiscal_month": 5, "shares_held": 10},
            {"symbol": "AAPL", "amount": 23.50, "payment_date": date(2024, 8, 15),
             "fiscal_year": 2024, "fiscal_month": 8, "shares_held": 10},
            {"symbol": "AAPL", "amount": 24.00, "payment_date": date(2024, 11, 15),
             "fiscal_year": 2024, "fiscal_month": 11, "shares_held": 10},
        ]

        result = await service.get_holding_dividends(1, "AAPL")

        assert len(result) == 4
        assert result[0]["label"] == "Q1 2024"
        assert result[0]["total_amount"] == 22.50
        assert result[0]["payments_count"] == 1
        assert result[1]["label"] == "Q2 2024"
        assert result[1]["total_amount"] == 23.00

    async def test_no_dividends(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_dividends_for_symbol.return_value = []
        result = await service.get_holding_dividends(1, "GOOGL")
        assert result == []

    async def test_dividends_multiple_accounts(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_dividends_for_symbol.return_value = [
            {"symbol": "AAPL", "amount": 22.50, "payment_date": date(2024, 2, 15),
             "fiscal_year": 2024, "fiscal_month": 2, "shares_held": 10},
            {"symbol": "AAPL", "amount": 18.00, "payment_date": date(2024, 2, 15),
             "fiscal_year": 2024, "fiscal_month": 2, "shares_held": 8},
        ]

        result = await service.get_holding_dividends(1, "AAPL")

        assert len(result) == 1
        assert result[0]["label"] == "Q1 2024"
        assert result[0]["total_amount"] == 40.50
        assert result[0]["payments_count"] == 2


# ═════════════════════════════════════════════════════════════════════════════
# P-02: Holding performance start date uses symbol's first purchase
# ═════════════════════════════════════════════════════════════════════════════

@ pytest.mark.anyio
class TestGetHoldingPerformanceP02:

    async def test_period_all_starts_from_symbol_first_purchase(self, service, mock_portfolio_repo):
        """P-02: For 'ALL' period, start_date should be the symbol's
        earliest transaction, not the portfolio-wide earliest."""
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": "2024-06-01", "symbol": "AAPL",
             "quantity": 10, "unit_price": 150, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2022, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-06-01", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            mock_fifo.return_value = [
                {"date": "2024-06-01", "value": 1500, "cost_basis": 1500, "net_deposits": 1500},
                {"date": "2024-12-31", "value": 1800, "cost_basis": 1500, "net_deposits": 1500},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance(1, "AAPL", "ALL")

        assert result["success"] is True
        assert result["snapshots"][0]["date"] >= "2024-06-01"

    async def test_period_start_clamped_to_symbol_first_purchase(self, service, mock_portfolio_repo):
        """P-02: When period starts before symbol's first purchase, 
        start_date should be clamped to the first purchase date."""
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": "2024-06-01", "symbol": "AAPL",
             "quantity": 10, "unit_price": 150, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2023, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2023-06-01", "2024-01-01", "2024-06-01", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            mock_fifo.return_value = [
                {"date": "2023-06-01", "value": 0, "cost_basis": 0, "net_deposits": 0},
                {"date": "2024-01-01", "value": 0, "cost_basis": 0, "net_deposits": 0},
                {"date": "2024-06-01", "value": 1500, "cost_basis": 1500, "net_deposits": 1500},
                {"date": "2024-12-31", "value": 1800, "cost_basis": 1500, "net_deposits": 1500},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance(1, "AAPL", "1Y")

        assert result["success"] is True
        assert result["snapshots"][-1]["position_value"] == 1800


# ═════════════════════════════════════════════════════════════════════════════
# P-04: Holding transaction history
# ═════════════════════════════════════════════════════════════════════════════

@ pytest.mark.anyio
class TestGetHoldingTransactions:

    async def test_returns_all_buy_sell_transactions(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_id": 1, "transaction_date": date(2024, 1, 15),
             "symbol": "AAPL", "quantity": 10, "unit_price": 150,
             "commission": 0, "net_cash_amount": -1500,
             "activity_sub_type": "BUY", "account_id": 1},
            {"transaction_id": 2, "transaction_date": date(2024, 6, 1),
             "symbol": "AAPL", "quantity": -3, "unit_price": 200,
             "commission": 0, "net_cash_amount": 600,
             "activity_sub_type": "SELL", "account_id": 1},
        ]

        result = await service.get_holding_transactions(1, "AAPL")

        assert len(result) == 2
        assert result[0]["activity_sub_type"] == "SELL"  # sorted DESC
        assert result[1]["activity_sub_type"] == "BUY"
        assert result[0]["account_name"] == "TFSA"

    async def test_filters_non_trade_transactions(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_id": 1, "transaction_date": date(2024, 1, 15),
             "symbol": "AAPL", "quantity": 0, "unit_price": 0,
             "commission": 0, "net_cash_amount": 100,
             "activity_sub_type": "DIVIDEND", "account_id": 1},
        ]

        result = await service.get_holding_transactions(1, "AAPL")

        assert result == []

    async def test_empty_when_no_transactions(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = []
        result = await service.get_holding_transactions(1, "AAPL")
        assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# P-05: Per-account holding breakdown
# ═════════════════════════════════════════════════════════════════════════════

@ pytest.mark.anyio
class TestGetHoldingAccounts:

    async def test_returns_account_breakdown(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_user_all_holdings.return_value = [
            {"account_id": 1, "symbol": "AAPL", "company_id": 1,
             "quantity": 10, "total_cost": 1500,
             "account_name": "Main TFSA", "account_type": "TFSA"},
            {"account_id": 2, "symbol": "AAPL", "company_id": 1,
             "quantity": 5, "total_cost": 900,
             "account_name": "RRSP", "account_type": "RRSP"},
        ]
        mock_portfolio_repo.get_dividends_for_symbol.return_value = [
            {"account_id": 1, "amount": 45.00, "payment_date": date(2024, 2, 15),
             "symbol": "AAPL", "fiscal_year": 2024, "fiscal_month": 2},
        ]

        with patch.object(service, 'enrich_holdings_with_prices') as mock_enrich:
            mock_enrich.return_value = [
                {"account_id": 1, "symbol": "AAPL", "quantity": 10,
                 "total_cost": 1500, "current_value": 1800,
                 "account_name": "Main TFSA", "account_type": "TFSA"},
                {"account_id": 2, "symbol": "AAPL", "quantity": 5,
                 "total_cost": 900, "current_value": 900,
                 "account_name": "RRSP", "account_type": "RRSP"},
            ]

            result = await service.get_holding_accounts(1, "AAPL")

        assert len(result) == 2
        assert result[0]["account_name"] == "Main TFSA"
        assert result[0]["shares_held"] == 10
        assert result[0]["current_value"] == 1800
        assert result[0]["unrealized_gain_loss"] == 300
        assert result[0]["dividends_received"] == 45
        assert result[0]["unrealized_gain_loss_pct"] == 20.0

    async def test_empty_when_no_holdings(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_user_all_holdings.return_value = []
        result = await service.get_holding_accounts(1, "AAPL")
        assert result == []


# ═════════════════════════════════════════════════════════════════════════════
# P-03: Holding-level benchmark comparison
# ═════════════════════════════════════════════════════════════════════════════

@ pytest.mark.anyio
class TestGetHoldingPerformanceCompare:

    async def test_returns_benchmark_series(self, service, mock_portfolio_repo, mock_financial_repo):
        mock_financial_repo.get_company_by_symbol = AsyncMock(
            return_value={"company_id": 10, "ticker_symbol": "SPY"}
        )
        mock_portfolio_repo.get_transactions_for_symbol.return_value = [
            {"transaction_date": date(2024, 1, 15), "symbol": "AAPL",
             "quantity": 10, "unit_price": 150, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]

        with (
            patch.object(service, '_period_to_date_range', return_value=(date(2024, 1, 1), date(2024, 12, 31))),
            patch.object(service, '_generate_snapshot_dates', return_value=["2024-01-15", "2024-12-31"]),
            patch.object(service, '_compute_fifo_snapshots') as mock_fifo,
            patch.object(service, '_simulate_benchmark_value') as mock_sim,
            patch('application.services.portfolio_service.supabase') as mock_supa,
        ):
            mock_fifo.return_value = [
                {"date": "2024-01-15", "value": 1500, "cost_basis": 1500, "net_deposits": 1500},
                {"date": "2024-12-31", "value": 1800, "cost_basis": 1500, "net_deposits": 1500},
            ]
            mock_sim.return_value = [
                {"date": "2024-01-15", "value": 1500},
                {"date": "2024-12-31", "value": 1700},
            ]
            mock_supa.table().select().gte().lte().order().execute.return_value.data = []

            result = await service.get_holding_performance_compare(1, "AAPL", "1Y", ["SPY"])

        assert result["success"] is True
        assert len(result["benchmarks"]) == 1
        assert result["benchmarks"][0]["symbol"] == "SPY"
        assert len(result["portfolio"]) == 2

    async def test_empty_when_no_performance_data(self, service, mock_portfolio_repo):
        mock_portfolio_repo.get_transactions_for_symbol.return_value = []
        with patch('application.services.portfolio_service.supabase') as mock_supa:
            mock_supa.table().select().execute.return_value.data = []
            result = await service.get_holding_performance_compare(1, "AAPL", "1Y", ["SPY"])
        assert result["portfolio"] == []
        assert result["benchmarks"] == []


# ═════════════════════════════════════════════════════════════════════════════
# Repository: _flatten_joins — verifies the Supabase join flattening pipeline
# ═════════════════════════════════════════════════════════════════════════════

class TestFlattenJoins:
    """Tests that _flatten_joins correctly promotes nested Supabase join
    objects to top-level fields, matching the real PostgREST wire format."""

    def test_flattens_nested_account_fields(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        from unittest.mock import MagicMock

        repo = PortfolioRepository(client=MagicMock())
        nested = [
            {
                "holding_id": 1,
                "account_id": 1,
                "symbol": "AAPL",
                "portfolio_accounts": {"account_name": "RRSP", "account_type": "RRSP"},
            },
            {
                "holding_id": 2,
                "account_id": 2,
                "symbol": "MSFT",
                "portfolio_accounts": {"account_name": "Main TFSA", "account_type": "TFSA"},
            },
        ]

        result = repo._flatten_joins(nested)

        assert result[0]["account_name"] == "RRSP"
        assert result[0]["account_type"] == "RRSP"
        assert result[0]["holding_id"] == 1
        assert result[0]["symbol"] == "AAPL"
        # nested dict still present (not removed)
        assert result[0]["portfolio_accounts"] == {"account_name": "RRSP", "account_type": "RRSP"}

        assert result[1]["account_name"] == "Main TFSA"
        assert result[1]["account_type"] == "TFSA"
        assert len(result) == 2

    def test_skips_non_dict_join_values(self):
        """If the join value is None or a scalar, it should be skipped."""
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        from unittest.mock import MagicMock

        repo = PortfolioRepository(client=MagicMock())
        nested = [
            {
                "holding_id": 1,
                "account_id": 1,
                "symbol": "AAPL",
                "portfolio_accounts": None,
            },
        ]

        result = repo._flatten_joins(nested)

        # account_name should NOT be in the result since the join returned null
        assert "account_name" not in result[0]
        assert result[0]["holding_id"] == 1

    def test_preserves_existing_top_level_fields(self):
        """Top-level fields should not be overwritten by nested join fields."""
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        from unittest.mock import MagicMock

        repo = PortfolioRepository(client=MagicMock())
        nested = [
            {
                "holding_id": 1,
                "account_id": 1,
                "account_name": "EXPLICIT",  # already at top level
                "portfolio_accounts": {"account_name": "RRSP", "account_type": "RRSP"},
            },
        ]

        result = repo._flatten_joins(nested)

        # Existing top-level field is NOT overwritten
        assert result[0]["account_name"] == "EXPLICIT"


@ pytest.mark.anyio
class TestGetUserAllHoldingsPipeline:
    """Full-pipeline test: verifies that the Supabase nested join response
    correctly flows through _get_holdings → _flatten_joins → _enrich_holdings
    to produce flat account_name/account_type on every holding."""

    async def test_account_fields_are_flat_after_full_pipeline(self):
        from infrastructure.repositories.portfolio_repository import PortfolioRepository
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        repo = PortfolioRepository(client=mock_client)

        # Mock the supabase chain: table("portfolio_holdings").select(...).in_(...).order(...).execute()
        mock_data = [
            {
                "holding_id": 1, "account_id": 1, "symbol": "AAPL",
                "quantity": 10, "total_cost": 1500.0, "company_id": 100,
                "average_cost": 150.0,
                "portfolio_accounts": {"account_name": "RRSP", "account_type": "RRSP"},
            },
            {
                "holding_id": 2, "account_id": 2, "symbol": "MSFT",
                "quantity": 5, "total_cost": 2000.0, "company_id": 101,
                "average_cost": 400.0,
                "portfolio_accounts": {"account_name": "Main TFSA", "account_type": "TFSA"},
            },
        ]
        mock_exec = MagicMock(data=mock_data)
        mock_client.table.return_value.select.return_value.in_.return_value.order.return_value.execute.return_value = mock_exec

        # Mock get_user_accounts (called to resolve user_id → account_ids)
        with patch.object(repo, 'get_user_accounts', return_value=[
            {"account_id": 1}, {"account_id": 2},
        ]):
            # Mock _enrich_holdings to passthrough (avoids companies table mock)
            with patch.object(repo, '_enrich_holdings', side_effect=lambda x: x):
                result = repo.get_user_all_holdings(1)

        assert len(result) == 2
        assert result[0]["account_name"] == "RRSP"
        assert result[0]["account_type"] == "RRSP"
        assert result[1]["account_name"] == "Main TFSA"
        assert result[1]["account_type"] == "TFSA"
        # Original fields preserved
        assert result[0]["symbol"] == "AAPL"
        assert result[0]["holding_id"] == 1
