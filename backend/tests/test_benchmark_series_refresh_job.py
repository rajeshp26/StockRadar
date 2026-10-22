"""Tests for the benchmark-series refresh job.

The requirement these protect:

    Keeping the materialised store fresh must be a maintenance pass that can
    fail without failing the daily snapshot job that owns it, and without
    making the store worse than empty.

The job is exercised with fakes for the repository and service so the tests
assert the job's OWN contract (per-user isolation, failure accounting, grid
bounds, never raising) rather than re-testing the guard.
"""
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.jobs import benchmark_series_refresh_job as job_mod
from application.jobs.benchmark_series_refresh_job import (
    DEFAULT_BENCHMARK_SYMBOLS,
    _add_month,
    _monthly_grid,
    refresh_benchmark_series,
)


class TestMonthlyGrid:
    def test_includes_start_and_end_and_stays_bounded(self):
        grid = _monthly_grid(date(2022, 1, 3), date(2026, 10, 19))
        assert grid[0] == "2022-01-03"
        assert grid[-1] == "2026-10-19"
        # ~58 months + the explicit end; far below the daily count of ~1,750.
        assert len(grid) <= 62

    def test_single_day_span(self):
        grid = _monthly_grid(date(2026, 10, 19), date(2026, 10, 19))
        assert grid == ["2026-10-19"]

    def test_add_month_clamps_short_months(self):
        assert _add_month(date(2026, 1, 31)) == date(2026, 2, 28)
        assert _add_month(date(2026, 12, 15)) == date(2027, 1, 15)


class TestRefreshJob:
    @pytest.mark.anyio
    async def test_no_users_is_a_clean_noop(self):
        repo = MagicMock()
        repo.get_user_accounts_all.return_value = []
        with patch.object(job_mod, "PortfolioRepository", return_value=repo), \
             patch.object(job_mod, "PortfolioService", return_value=MagicMock()):
            result = await refresh_benchmark_series()
        assert result.account_sets == 0
        assert result.failures == 0

    @pytest.mark.anyio
    async def test_user_enumeration_failure_never_raises(self):
        repo = MagicMock()
        repo.get_user_accounts_all.side_effect = Exception("db down")
        with patch.object(job_mod, "PortfolioRepository", return_value=repo), \
             patch.object(job_mod, "PortfolioService", return_value=MagicMock()):
            result = await refresh_benchmark_series()
        assert result.failures == 1

    @pytest.mark.anyio
    async def test_one_users_failure_does_not_stop_the_next(self):
        """A failure for user 1 must not cost user 2 its refresh."""
        repo = MagicMock()
        repo.get_user_accounts_all.return_value = [{"user_id": 1}, {"user_id": 2}]

        def accounts(uid):
            if uid == 1:
                raise Exception("boom")
            return [{"account_id": 9}]

        repo.get_user_accounts.side_effect = accounts

        snaps = MagicMock()
        snaps.get_first_snapshot_date.return_value = date(2022, 1, 3)

        svc = MagicMock()
        svc.financial_repo.get_company_by_symbol = AsyncMock(
            return_value={"company_id": 5}
        )
        svc.get_portfolio_performance = AsyncMock(
            return_value={"snapshots": [{"date": "2022-01-03", "value": 1000.0}]}
        )
        svc._get_cashflow_deltas.return_value = []
        svc._benchmark_series_with_reuse = AsyncMock(
            return_value=[{"date": "2022-01-03", "value": 1000.0}]
        )

        with patch.object(job_mod, "PortfolioRepository", return_value=repo), \
             patch.object(job_mod, "PortfolioService", return_value=svc), \
             patch.object(job_mod, "_snapshots_repo", return_value=snaps):
            result = await refresh_benchmark_series(symbols=("SPY",))

        assert result.failures == 1, "user 1's failure is recorded"
        assert result.account_sets == 1, "user 2 was still refreshed"
        assert result.symbols_ok == 1

    @pytest.mark.anyio
    async def test_symbol_failure_is_counted_not_fatal(self):
        repo = MagicMock()
        repo.get_user_accounts_all.return_value = [{"user_id": 1}]
        repo.get_user_accounts.return_value = [{"account_id": 7}]

        snaps = MagicMock()
        snaps.get_first_snapshot_date.return_value = date(2022, 1, 3)

        svc = MagicMock()
        svc.financial_repo.get_company_by_symbol = AsyncMock(
            return_value={"company_id": 5}
        )
        svc.get_portfolio_performance = AsyncMock(
            return_value={"snapshots": [{"date": "2022-01-03", "value": 1000.0}]}
        )
        svc._get_cashflow_deltas.return_value = []
        svc._benchmark_series_with_reuse = AsyncMock(
            side_effect=[Exception("read fail"), [{"date": "x", "value": 1.0}]]
        )

        with patch.object(job_mod, "PortfolioRepository", return_value=repo), \
             patch.object(job_mod, "PortfolioService", return_value=svc), \
             patch.object(job_mod, "_snapshots_repo", return_value=snaps):
            result = await refresh_benchmark_series(symbols=("SPY", "QQQ"))

        assert result.failures == 1
        assert result.symbols_ok == 1

    @pytest.mark.anyio
    async def test_anchor_cashflow_is_excluded_before_handoff(self):
        """The job must apply the same anchor rule the read path applies."""
        from datetime import date as _date

        anchor = _date(2022, 1, 3)
        repo = MagicMock()
        repo.get_user_accounts_all.return_value = [{"user_id": 1}]
        repo.get_user_accounts.return_value = [{"account_id": 7}]

        snaps = MagicMock()
        snaps.get_first_snapshot_date.return_value = anchor

        svc = MagicMock()
        svc.financial_repo.get_company_by_symbol = AsyncMock(
            return_value={"company_id": 5}
        )
        svc.get_portfolio_performance = AsyncMock(
            return_value={"snapshots": [{"date": "2022-01-03", "value": 1000.0}]}
        )
        svc._get_cashflow_deltas.return_value = [
            {"date": anchor, "amount": 1000.0},          # anchor seed - drop
            {"date": _date(2023, 6, 1), "amount": 500.0},  # real deposit - keep
        ]
        svc._benchmark_series_with_reuse = AsyncMock(
            return_value=[{"date": "2022-01-03", "value": 1000.0}]
        )

        with patch.object(job_mod, "PortfolioRepository", return_value=repo), \
             patch.object(job_mod, "PortfolioService", return_value=svc), \
             patch.object(job_mod, "_snapshots_repo", return_value=snaps):
            await refresh_benchmark_series(symbols=("SPY",))

        passed = svc._benchmark_series_with_reuse.await_args.kwargs["cashflows"]
        assert [cf["date"] for cf in passed] == [_date(2023, 6, 1)]

    def test_default_symbols_are_the_configured_benchmarks(self):
        assert set(DEFAULT_BENCHMARK_SYMBOLS) == {"SPY", "QQQ"}
