"""
Timezone-safe datetime utilities for StockerPro.

All datetimes interacting with Supabase TIMESTAMPTZ columns must be
timezone-aware (UTC).  This module is the single source of truth for
"what time is it now" and for serialization to/from the database.

Python 3.12 deprecated datetime.utcnow() — use now_utc() instead.
"""

from datetime import UTC, datetime, timedelta


def now_utc() -> datetime:
    """Return the current UTC time as an aware datetime (tzinfo=UTC)."""
    return datetime.now(UTC)


def now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string with timezone offset.

    Example: "2026-06-20T17:01:02.398383+00:00"
    """
    return now_utc().isoformat()


def parse_db_timestamp(value: str) -> datetime:
    """Parse a TIMESTAMPTZ value returned by Supabase into an aware datetime.

    Handles both:
      - "2026-06-20T17:01:02+00:00"  (with offset)
      - "2026-06-20T17:01:02"         (without offset — treated as UTC)
    """
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def ensure_aware(dt: datetime) -> datetime:
    """If `dt` is naive, treat it as UTC and add timezone info."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def age_seconds(dt: datetime) -> float:
    """Compute the age of `dt` (must be aware) relative to now_utc()."""
    return (now_utc() - ensure_aware(dt)).total_seconds()


def age_days(dt: datetime) -> float:
    """Compute the age of `dt` in days."""
    return age_seconds(dt) / 86400.0


def iso_minus(days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    """Return an ISO-8601 UTC timestamp offset backwards from now."""
    return (now_utc() - timedelta(days=days, hours=hours, minutes=minutes)).isoformat()


def iso_plus(days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    """Return an ISO-8601 UTC timestamp offset forwards from now."""
    return (now_utc() + timedelta(days=days, hours=hours, minutes=minutes)).isoformat()
