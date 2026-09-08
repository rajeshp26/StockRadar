"""
Calendar-quarter date helpers shared by the reconciliation and freshness
monitor schedulers.

Kept dependency-free (stdlib only) so both planners and their tests can import
the helpers without pulling in repository or config layers.
"""

from datetime import date, datetime, timedelta
from typing import Any


def quarter_start(d: date) -> date:
    """First day of the calendar quarter containing d."""
    return date(d.year, ((d.month - 1) // 3) * 3 + 1, 1)


def quarter_end(d: date) -> date:
    """Last day of the calendar quarter containing d."""
    if d.month >= 10:
        return date(d.year, 12, 31)
    return date(d.year, ((d.month - 1) // 3) * 3 + 4, 1) - timedelta(days=1)


def quarter_ends_between(start: date, end: date) -> set[date]:
    """Quarter-end dates of every quarter from start through end (inclusive)."""
    out: set[date] = set()
    cur = quarter_start(start)
    limit = quarter_start(end)
    while cur <= limit:
        out.add(quarter_end(cur))
        if cur.month == 10:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 3, 1)
    return out


def shift_quarters(d: date, n: int) -> date:
    """Shift by n whole quarters (n < 0 = backward), returning the quarter start."""
    start = quarter_start(d)
    total = start.year * 12 + (start.month - 1) + n * 3
    year, zero_month = divmod(total, 12)
    return date(year, zero_month + 1, 1)


def as_date(value: Any, default: date | None = None) -> date | None:
    """Coerce a DB value (date / datetime / ISO string) to a date; else default."""
    if value is None:
        return default
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return default
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return default
