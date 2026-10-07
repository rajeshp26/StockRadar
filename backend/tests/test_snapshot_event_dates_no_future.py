"""Regression: get_event_dates must never emit a future snapshot_date.

`shared/snapshot_builder.build_snapshot_row` enforces a data-integrity invariant --
a snapshot cannot describe a day that has not happened -- and raises
ValueError("...refusing future snapshot_date ...").

`PortfolioRepository.get_event_dates` synthesises month-end dates so snapshots exist
at month boundaries. It must therefore never synthesise a month-end that is still in
the future, or every rebuild aborts on the first incomplete month.

Bug: the month_end loop guard compared *first-of-month* against today while appending
*month-end*, so on any day before month-end it appended the upcoming month-end.
"""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from infrastructure.repositories import portfolio_repository as pr_mod
from infrastructure.repositories.portfolio_repository import PortfolioRepository


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *args, **kwargs):
        return self

    def eq(self, *args, **kwargs):
        return self

    def in_(self, *args, **kwargs):
        return self

    def execute(self):
        return _FakeResult(self._rows)


class _FakeClient:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        return _FakeTable(self._rows)


def _repo_with_first_transaction_on(day: str) -> PortfolioRepository:
    rows = [{"transaction_date": day, "activity_type": "Trade"}]
    return PortfolioRepository(client=_FakeClient(rows))


def _event_dates_as_of(today: date, first_txn: str = "2024-01-15") -> list[date]:
    repo = _repo_with_first_transaction_on(first_txn)
    frozen = datetime(today.year, today.month, today.day, tzinfo=UTC)
    with patch.object(pr_mod, "now_utc", return_value=frozen):
        return repo.get_event_dates(9)


@pytest.mark.parametrize(
    "today",
    [
        date(2026, 10, 1),  # first of month
        date(2026, 10, 15),  # mid-month
        date(2026, 10, 31),  # month end itself
        date(2026, 11, 1),  # first of the following month
        date(2026, 2, 10),  # short month boundary
    ],
)
def test_get_event_dates_never_returns_a_future_date(today):
    dates = _event_dates_as_of(today)
    future = [d for d in dates if d > today]
    assert future == [], f"get_event_dates emitted future dates {future} as of {today}"


def test_completed_month_ends_are_still_synthesised():
    """The fix must not silently drop legitimate past month-end dates."""
    dates = _event_dates_as_of(date(2026, 10, 1))
    # September 2026 is complete, so its month-end must still be present.
    assert date(2026, 9, 30) in dates
    # October is incomplete, so its month-end must be absent.
    assert date(2026, 10, 31) not in dates
