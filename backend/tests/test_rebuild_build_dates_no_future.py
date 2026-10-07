"""Regression: rebuild_account_snapshots.build_dates must not emit a future date.

`shared/snapshot_builder.build_snapshot_row` refuses to build a snapshot dated in the
future ("refusing future snapshot_date ..."), because such a row prices holdings with
information that does not exist yet.

`build_dates` unions stored snapshot dates with event dates, then adds a first-of-month
and a month-end anchor for every date it collected. The month-end anchor was unbounded,
so any account holding a date inside the current open month gained a month-end that is
still in the future. That is a second, independent source of the same defect already
guarded in `PortfolioRepository.get_event_dates`, and it aborted every dry-run.

The clock is patched to `now_utc` for the same reason the fix uses it: a local/UTC date
split between this module and the builder guard reintroduces the refusal.
"""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

import scripts.rebuild_account_snapshots as ras


def _build_dates_as_of(today: date, stored: list, events: list | None = None) -> list[str]:
    frozen = datetime(today.year, today.month, today.day, tzinfo=UTC)
    with (
        patch.object(ras, "now_utc", return_value=frozen),
        patch.object(ras, "fetch_all_rows", return_value=stored),
    ):
        return ras.build_dates(9, events or [])


@pytest.mark.parametrize(
    "today",
    [
        date(2026, 10, 1),  # first of month: October month-end is 30 days away
        date(2026, 10, 15),  # mid-month
        date(2026, 2, 10),  # short month boundary
        date(2026, 4, 2),  # month with 30 days
    ],
)
def test_build_dates_never_returns_a_future_date(today):
    stored = [{"snapshot_date": today.isoformat()}]
    dates = _build_dates_as_of(today, stored)
    future = [d for d in dates if date.fromisoformat(d) > today]
    assert future == [], f"build_dates emitted future dates {future} as of {today}"


def test_open_month_end_is_dropped_but_completed_month_end_is_kept():
    # Anchors are only added for months the account already touches.
    stored = [{"snapshot_date": "2026-09-15"}, {"snapshot_date": "2026-10-01"}]
    dates = _build_dates_as_of(date(2026, 10, 1), stored)
    assert "2026-10-31" not in dates, "October is incomplete, its month-end must be absent"
    assert "2026-09-30" in dates, "September is complete, its month-end must be present"


def test_month_end_is_kept_once_it_has_arrived():
    """On the month end itself the anchor is not in the future, so it must survive."""
    stored = [{"snapshot_date": "2026-10-01"}]
    assert "2026-10-31" in _build_dates_as_of(date(2026, 10, 31), stored)
    assert "2026-10-31" in _build_dates_as_of(date(2026, 11, 1), stored)


def test_event_dates_still_feed_the_date_set():
    """The bound must not disturb dates sourced from account events."""
    events = [{"data": {"transaction_date": "2024-03-11"}, "created_at": "2024-03-11"}]
    stored = [{"snapshot_date": "2026-10-01"}]
    dates = _build_dates_as_of(date(2026, 10, 1), stored, events)
    assert "2024-03-11" in dates
    assert "2024-03-31" in dates, "March 2024 is complete, so its month-end is legitimate"
