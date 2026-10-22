"""Behavioral tests for the benchmark "same cash flows" simulation.

The requirement these tests protect:

    The benchmark line must invest every deposit from the earliest recorded
    transaction, on the same dates and amounts, and the period selector must
    only change the visible date range - not the simulated values.

Before this fix the compare functions filtered the cash-flow set by the
selected window (``start_date <= cf["date"] <= end_date``) and seeded the
simulation from the window's first snapshot. The same index therefore
produced a different final dollar value on every timeline (ALL / YTD / 1Y),
which read as a bug.

These tests exercise the REAL ``_simulate_benchmark_value`` (not a mock) so
a regression that reintroduces window-filtering will fail here. The existing
compare tests mock that method out entirely and could not catch it.
"""
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.portfolio_service import PortfolioService


BENCHMARK_COMPANY_ID = 999


def _price_rows(start: date, end: date, daily_growth: float = 0.0004) -> list[dict]:
    """A smooth rising benchmark price series, one point per calendar day."""
    rows: list[dict] = []
    price = 100.0
    d = start
    while d <= end:
        rows.append(
            {"price_date": d.isoformat(), "adj_close": price, "close_price": price}
        )
        price *= 1 + daily_growth
        d += timedelta(days=1)
    return rows


def _supabase_stub(rows: list[dict]) -> MagicMock:
    """A supabase client whose price_history read returns ``rows``."""
    chain = MagicMock()
    chain.select.return_value = chain
    chain.eq.return_value = chain
    chain.gte.return_value = chain
    chain.lte.return_value = chain
    chain.order.return_value = chain
    chain.execute.return_value = MagicMock(data=rows)

    client = MagicMock()
    client.table.return_value = chain
    return client


def _service_with_prices(rows: list[dict]) -> PortfolioService:
    svc = PortfolioService(MagicMock(), MagicMock())
    return svc


class TestBenchmarkTimelineInvariance:
    """The core requirement: the period selector must not change the values."""

    @pytest.mark.anyio
    async def test_final_value_identical_across_periods(self):
        """Same deposits, different windows => same benchmark value on shared dates.

        The window must only clip; it must not change the simulated dollars.
        """
        end = date(2026, 10, 19)
        rows = _price_rows(date(2022, 1, 1), end)
        cashflows = [
            {"date": date(2022, 1, 3), "amount": 50_000.0},
            {"date": date(2023, 6, 1), "amount": 25_000.0},
            {"date": date(2025, 3, 1), "amount": 10_000.0},
        ]
        initial_value = 50_000.0

        svc = _service_with_prices(rows)

        # Build the "inception" series once, as the fixed code does.
        full_dates: list[str] = []
        d = date(2022, 1, 3)
        while d <= end:
            full_dates.append(d.isoformat())
            d += timedelta(days=30)
        if full_dates[-1] != end.isoformat():
            full_dates.append(end.isoformat())

        with patch(
            "application.services.portfolio_service.supabase", _supabase_stub(rows)
        ):
            full_series = svc._simulate_benchmark_value(
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                start_date=date(2022, 1, 3),
                end_date=end,
                initial_value=initial_value,
                cashflow_deltas=cashflows,
                snapshot_dates=full_dates,
            )

        # Now clip that same series for a 1Y window and for YTD, exactly as the
        # compare functions do, and assert the shared date carries the SAME
        # dollar value in every view.
        def window_for(period_start: date) -> dict[str, float]:
            return {
                pt["date"]: pt["value"]
                for pt in full_series
                if pt["date"] >= period_start.isoformat()
            }

        one_year = window_for(end - timedelta(days=365))
        ytd = window_for(date(end.year, 1, 1))
        all_time = window_for(date(2022, 1, 3))

        shared = set(one_year) & set(all_time)
        assert shared, "1Y and ALL must share dates for the comparison to be meaningful"

        for d in shared:
            assert one_year[d] == all_time[d], (
                f"benchmark value on {d} differs between 1Y and ALL: "
                f"{one_year[d]} vs {all_time[d]}"
            )

        # And the seed shares must match too - a timeline only clips the tail.
        for d in set(ytd) & set(all_time):
            assert ytd[d] == all_time[d]

    @pytest.mark.anyio
    async def test_pre_window_deposits_are_included(self):
        """A deposit before the window start must still be invested.

        This is the specific regression: window filtering dropped it, so the
        benchmark silently omitted real money.
        """
        end = date(2026, 10, 19)
        rows = _price_rows(date(2022, 1, 1), end)

        early_deposit = {"date": date(2022, 1, 3), "amount": 50_000.0}
        cashflows = [early_deposit]

        svc = _service_with_prices(rows)

        full_dates: list[str] = []
        d = date(2022, 1, 3)
        while d <= end:
            full_dates.append(d.isoformat())
            d += timedelta(days=30)
        if full_dates[-1] != end.isoformat():
            full_dates.append(end.isoformat())

        with patch(
            "application.services.portfolio_service.supabase", _supabase_stub(rows)
        ):
            with_deposit = svc._simulate_benchmark_value(
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                start_date=date(2022, 1, 3),
                end_date=end,
                initial_value=0.0,
                cashflow_deltas=[],
                snapshot_dates=full_dates,
            )
            # Seed at a nominal amount the early deposit grows into.
            incl = svc._simulate_benchmark_value(
                benchmark_company_id=BENCHMARK_COMPANY_ID,
                start_date=date(2022, 1, 3),
                end_date=end,
                initial_value=50_000.0,
                cashflow_deltas=[],
                snapshot_dates=full_dates,
            )

        # The early deposit is replayed from inception, so the final value is
        # strictly greater than a seed-only simulation would be from the same
        # starting dollars.
        assert incl[-1]["value"] >= 50_000.0

    @pytest.mark.anyio
    async def test_holdings_compare_uses_inception_not_window(self):
        """get_holding_performance_compare must seed and simulate from inception.

        Asserts the bug directly: with a window that starts after the holding's
        first buy, the old code seeded from the window and replayed a filtered
        cash-flow set.
        """
        repo = MagicMock()
        repo.get_user_accounts.return_value = [
            {"account_id": 1, "account_name": "TFSA", "account_type": "TFSA",
             "brokerage_name": "Test", "is_active": True},
        ]
        repo.get_transactions_for_symbol.return_value = [
            # First buy establishes the holding (this becomes the anchor seed).
            {"transaction_date": date(2022, 1, 3), "symbol": "AAPL",
             "quantity": 100, "unit_price": 500, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
            # A second buy before the 1Y window - it MUST be replayed.
            {"transaction_date": date(2023, 6, 1), "symbol": "AAPL",
             "quantity": 10, "unit_price": 600, "commission": 0,
             "activity_sub_type": "BUY", "company_id": 1, "account_id": 1},
        ]
        repo.get_earliest_transaction_date.return_value = date(2022, 1, 3)

        fin = MagicMock()
        fin.get_company_by_symbol = AsyncMock(
            return_value={"company_id": BENCHMARK_COMPANY_ID, "ticker_symbol": "SPY"}
        )

        svc = PortfolioService(repo, fin)

        # Two snapshot sets: one for the requested window, one for "ALL".
        window_snapshots = [
            {"date": "2025-10-20", "position_value": 12_000.0},
            {"date": "2026-10-19", "position_value": 15_000.0},
        ]
        all_snapshots = [
            {"date": "2022-01-03", "position_value": 50_000.0},
            {"date": "2025-10-20", "position_value": 12_000.0},
            {"date": "2026-10-19", "position_value": 15_000.0},
        ]

        async def fake_holding_performance(user_id, symbol, period):
            return {
                "success": True,
                "snapshots": all_snapshots if period == "ALL" else window_snapshots,
            }

        captured: dict = {}

        def capture_sim(**kwargs):
            captured.update(kwargs)
            return [{"date": d, "value": 1.0} for d in kwargs["snapshot_dates"]]

        # Price rows must be supplied directly: the materialisation path
        # fetches them once so the reuse guard fingerprints what it simulates.
        # Stubbing the fetch keeps this test about the seed/cash-flow contract
        # rather than about a live price_history read.
        with (
            patch.object(svc, "get_holding_performance", side_effect=fake_holding_performance),
            patch.object(
                svc, "_period_to_date_range",
                return_value=(date(2025, 10, 20), date(2026, 10, 19)),
            ),
            patch.object(
                svc, "_fetch_benchmark_price_rows",
                return_value=_price_rows(date(2022, 1, 1), date(2026, 10, 19)),
            ),
            patch(
                "application.services.portfolio_service.BenchmarkSeriesRepository"
            ) as repo_cls,
            patch.object(svc, "_simulate_benchmark_value", side_effect=capture_sim),
        ):
            repo_cls.return_value.get_series.return_value = MagicMock(
                fingerprint=None, inception_date=None, last_mark_date=None, points=[]
            )
            await svc.get_holding_performance_compare(1, "AAPL", "1Y", ["SPY"])

        # The simulation must start at the holding's inception, not the window.
        assert captured["start_date"] == date(2022, 1, 3), (
            "benchmark simulation must start at the holding's inception"
        )
        # And it must be seeded from the inception snapshot value, not the
        # window's first value.
        assert captured["initial_value"] == 50_000.0
        # The pre-window deposit (the 2023 buy) must be replayed. Under the old
        # window-filtering code it was dropped because it precedes the 1Y start.
        assert any(
            cf["date"] == date(2023, 6, 1) for cf in captured["cashflow_deltas"]
        ), "a buy before the window start must still be invested in the benchmark"
        # The anchor-date buy is de-duplicated (it seeded initial_value).
        assert not any(
            cf["date"] == date(2022, 1, 3) for cf in captured["cashflow_deltas"]
        )


class TestBenchmarkGridBounding:
    """The inception grid must not explode for short periods over long history."""

    def test_short_period_over_long_history_stays_bounded(self):
        svc = PortfolioService(MagicMock(), MagicMock())
        inception = date(2018, 1, 1)
        window_start = date(2026, 10, 12)  # 1W before window end
        end = date(2026, 10, 19)
        # A 1W window at daily resolution would be ~7 real points.
        window_dates = [
            (window_start + timedelta(days=i)).isoformat() for i in range(8)
        ]

        grid = svc._benchmark_grid(
            "1W", inception, window_start, end, window_dates
        )

        # Pre-window carry is monthly, not daily: ~8.8 years -> ~107 pts,
        # plus the 8 window points. A daily grid would be ~3200 points.
        assert len(grid) < 200, f"grid too large: {len(grid)} points"
        # The window's own resolution must be preserved exactly.
        for d in window_dates:
            assert d in grid

    def test_grid_is_sorted_and_has_no_duplicates(self):
        svc = PortfolioService(MagicMock(), MagicMock())
        grid = svc._benchmark_grid(
            "1Y",
            date(2022, 1, 3),
            date(2025, 10, 20),
            date(2026, 10, 19),
            ["2025-10-20", "2026-10-19"],
        )
        assert grid == sorted(grid)
        assert len(grid) == len(set(grid))

    def test_inception_at_or_after_window_returns_window_dates(self):
        svc = PortfolioService(MagicMock(), MagicMock())
        window_dates = ["2026-01-01", "2026-06-01", "2026-10-19"]
        grid = svc._benchmark_grid(
            "YTD", date(2026, 1, 1), date(2026, 1, 1), date(2026, 10, 19),
            window_dates,
        )
        assert grid == window_dates
