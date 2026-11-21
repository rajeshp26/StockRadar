"""I12 -- zoneinfo must resolve IANA data via tzdata on Windows.

Windows has no system timezone database (``zoneinfo.TZPATH`` is empty), so the
declared ``tzdata`` distribution is the only source. Installation alone proves
nothing: these tests exercise actual resolution, a DST boundary, and the pandas
localisation path yfinance relies on for ex-dates.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from importlib import metadata
from zoneinfo import ZoneInfo

import pandas as pd

from config import settings


def test_tzdata_installed_and_zone_resolves():
    assert metadata.version("tzdata")
    zone = ZoneInfo(settings.DEFAULT_TIMEZONE)
    assert zone.key == settings.DEFAULT_TIMEZONE


def test_new_york_dst_boundary_offsets():
    zone = ZoneInfo("America/New_York")
    # Second Sunday in March 2026: EST (-05:00) -> EDT (-04:00).
    before = datetime(2026, 3, 8, 1, 59, tzinfo=zone).utcoffset()
    after = datetime(2026, 3, 8, 3, 0, tzinfo=zone).utcoffset()
    assert before == timedelta(hours=-5)
    assert after == timedelta(hours=-4)


def test_utc_round_trip_through_zone():
    zone = ZoneInfo("America/New_York")
    utc = datetime(2026, 7, 1, 16, 0, tzinfo=UTC)  # 12:00 EDT
    local = utc.astimezone(zone)
    assert local.hour == 12
    assert local.astimezone(UTC) == utc


def test_pandas_localizes_to_configured_zone():
    idx = pd.to_datetime(["2026-07-01 12:00:00"]).tz_localize(settings.DEFAULT_TIMEZONE)
    assert str(idx.tz) == settings.DEFAULT_TIMEZONE
