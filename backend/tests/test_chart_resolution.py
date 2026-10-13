"""Chart resolution policy: the served series is bucketed, the metrics are not.

The A6 defect was compression applied *before* the return metrics were computed, so
best_day/worst_day/TWR came from rows a month apart. The fix keeps the daily series
authoritative for metrics and buckets only what the chart renders. The ordering test
below is the guard that keeps that fix from silently regressing.
"""

import inspect
import re
from datetime import date
from pathlib import Path

import pytest

from application.services.portfolio_service import PortfolioService


def _series(dates: list[str]) -> list[dict]:
    return [{"date": d, "value": float(i + 1)} for i, d in enumerate(dates)]


def _dates(snapshots: list[dict]) -> list[str]:
    return [s["date"] for s in snapshots]


def _method_source(name: str) -> str:
    """Source of one class method. Decorated methods (@timed) hide their body from
    inspect.getsource, so slice the file between this def and the next class-level def."""
    path = inspect.getsourcefile(PortfolioService)
    assert path is not None
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    start = next(
        i
        for i, line in enumerate(lines)
        if re.match(rf"^    (async )?def {re.escape(name)}\(", line)
    )
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if re.match(r"^    (async )?def ", lines[i]) or re.match(r"^class ", lines[i])
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("1D", "day"),
        ("1W", "day"),
        ("1M", "day"),
        ("3M", "day"),
        ("1Y", "month"),
        ("YTD", "month"),
        ("5Y", "quarter"),
        ("ALL", "quarter"),
        ("all", "quarter"),
        ("1d", "day"),
        ("BOGUS", "day"),
    ],
)
def test_resolution_for_period(period: str, expected: str) -> None:
    assert PortfolioService._resolution_for_period(period) == expected


def test_day_resolution_returns_daily_series_untouched() -> None:
    daily = _series(["2024-01-01", "2024-01-02", "2024-01-03"])
    assert PortfolioService._downsample_snapshots(daily, "day") is daily


def test_buckets_hold_one_point_per_period() -> None:
    daily = _series(
        ["2024-01-01", "2024-01-15", "2024-01-31", "2024-02-01", "2024-02-29", "2024-03-01"]
    )
    bucketed = PortfolioService._downsample_snapshots(daily, "month")
    # Jan = range start (one point), Feb = month-end close, Mar = range end.
    # The old output carried BOTH 2024-01-01 and 2024-01-31 — the duplicate
    # window-start entry the user saw rendered twice on the chart.
    assert _dates(bucketed) == ["2024-01-01", "2024-02-29", "2024-03-01"]


def test_quarter_buckets_hold_one_point_per_period() -> None:
    daily = _series(
        ["2024-01-15", "2024-02-15", "2024-03-20", "2024-04-02", "2024-05-10", "2024-06-30"]
    )
    bucketed = PortfolioService._downsample_snapshots(daily, "quarter")
    # Q1 = range start, Q2 = quarter-end close — one point each, never two.
    assert _dates(bucketed) == ["2024-01-15", "2024-06-30"]


@pytest.mark.parametrize("resolution", ["month", "quarter"])
def test_no_calendar_period_contributes_two_points(resolution: str) -> None:
    """Regression: the window-start period used to carry two entries.

    The first bucket kept both its first observation *and* its period-end close,
    so the leftmost month/quarter appeared twice on the chart."""
    daily = _series(
        [
            "2024-01-01", "2024-01-15", "2024-01-31",
            "2024-02-01", "2024-02-15", "2024-02-29",
            "2024-03-01", "2024-03-15", "2024-03-31",
            "2024-04-01", "2024-04-15",
        ]
    )
    bucketed = PortfolioService._downsample_snapshots(daily, resolution)

    def bucket_key(iso: str) -> tuple[int, int]:
        d = date.fromisoformat(iso)
        divisor = 3 if resolution == "quarter" else 1
        return (d.year, (d.month - 1) // divisor)

    keys = [bucket_key(s["date"]) for s in bucketed]
    assert len(keys) == len(set(keys)), (
        f"a {resolution} bucket carried two points: {_dates(bucketed)}"
    )


@pytest.mark.parametrize("resolution", ["month", "quarter"])
def test_buckets_only_contain_measured_observations(resolution: str) -> None:
    daily = _series(
        [
            "2024-01-01", "2024-01-09", "2024-01-15", "2024-01-22", "2024-01-28",
            "2024-02-01", "2024-02-09", "2024-02-15", "2024-02-22", "2024-02-28",
            "2024-03-01", "2024-03-09", "2024-03-15", "2024-03-22", "2024-03-28",
        ]
    )
    bucketed = PortfolioService._downsample_snapshots(daily, resolution)
    assert len(bucketed) < len(daily)
    assert all(s in daily for s in bucketed)


@pytest.mark.parametrize("resolution", ["month", "quarter"])
def test_first_and_last_observations_are_preserved(resolution: str) -> None:
    daily = _series(["2024-01-05", "2024-04-11", "2024-07-19", "2024-10-25"])
    bucketed = PortfolioService._downsample_snapshots(daily, resolution)
    assert bucketed[0] is daily[0]
    assert bucketed[-1] is daily[-1]


@pytest.mark.parametrize("resolution", ["day", "month", "quarter"])
def test_no_duplicate_dates(resolution: str) -> None:
    daily = _series(
        ["2024-01-31", "2024-02-01", "2024-03-31", "2024-04-01", "2024-06-30", "2024-07-01"]
    )
    bucketed = PortfolioService._downsample_snapshots(daily, resolution)
    assert len(_dates(bucketed)) == len(set(_dates(bucketed)))


@pytest.mark.parametrize("resolution", ["day", "month", "quarter"])
def test_series_of_one_point_is_unchanged(resolution: str) -> None:
    single = _series(["2024-01-31"])
    assert PortfolioService._downsample_snapshots(single, resolution) is single


def test_bucketing_never_increases_point_count() -> None:
    daily = _series(
        ["2024-01-05", "2024-02-11", "2024-03-19", "2024-04-25", "2024-05-30", "2024-06-14"]
    )
    for resolution in ("day", "month", "quarter"):
        assert len(PortfolioService._downsample_snapshots(daily, resolution)) <= len(daily)


def test_metrics_are_computed_before_the_series_is_bucketed() -> None:
    source = _method_source("get_portfolio_performance")
    # rindex: the region has earlier _compute_returns_from_snapshots calls on its
    # empty/no-snapshot early returns, so only the final call carries the invariant.
    compute = source.rindex("_compute_returns_from_snapshots")
    downsample = source.index("_downsample_snapshots")
    assert compute < downsample, (
        "return metrics must be computed from the full daily series before the "
        "served series is bucketed, or TWR/best_day regress to sampled rows (A6)"
    )
