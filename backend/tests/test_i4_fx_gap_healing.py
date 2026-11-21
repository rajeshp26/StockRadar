"""I4 -- a stale FX close must trigger a bounded gap heal, not be reused forever.

Local reproduction: USD->CAD rate coverage stopped at 2026-09-22 while snapshots
continued to 2026-11-18, so 48 snapshot dates resolved a rate up to 57 days old.
The old FXService returned the first past rate immediately, short-circuiting
every gap-healing path. These tests pin the new behaviour with a fake table.
"""

import logging
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from shared.fx_service import FXService

TODAY = date(2026, 11, 18)
STALE_DATE = date(2026, 9, 22)
STALE_RATE = Decimal("1.40328002")
FRESH_DATE = date(2026, 11, 17)
FRESH_RATE = Decimal("1.39876543")


class FakeRatesTable:
    """Minimal chainable stand-in for the exchange_rates PostgREST table."""

    def __init__(self, rows):
        self.rows = list(rows)  # (base, target, rate_date, rate)
        self.upserts = []

    # query chain
    def table(self, _name): return self
    def select(self, _cols): return self
    def eq(self, col, value):
        if col == "base_currency":
            self._base = value
        elif col == "target_currency":
            self._target = value
        return self
    def lte(self, _col, value):
        self._as_of = date.fromisoformat(value)
        return self
    def order(self, _col, **_kw): return self
    def limit(self, _n): return self
    def execute(self):
        matches = [
            r for r in self.rows
            if r[0] == self._base and r[1] == self._target and r[2] <= self._as_of
        ]
        matches.sort(key=lambda r: r[2], reverse=True)
        data = [
            {"rate": str(r[3]), "rate_date": r[2].isoformat()}
            for r in matches[:1]
        ]
        return MagicMock(data=data)

    # write side (used by _cache_rate if a provider is wired in)
    def upsert(self, payload, on_conflict=None):
        self.upserts.append(payload)
        return self


def _now():
    return datetime(TODAY.year, TODAY.month, TODAY.day, tzinfo=UTC)


class TestStaleRateHeals:
    def test_stale_rate_triggers_gap_heal_and_returns_fresher_rate(self):
        table = FakeRatesTable([("USD", "CAD", STALE_DATE, STALE_RATE)])
        svc = FXService(table)

        def fake_fetch(base, target, start, end):
            assert (base, target) == ("USD", "CAD")
            assert start == STALE_DATE + timedelta(days=1)
            assert end == TODAY
            # Simulate the provider persisting the missing closes.
            table.rows.append(("USD", "CAD", FRESH_DATE, FRESH_RATE))
            return [(FRESH_DATE, FRESH_RATE)]

        with patch("shared.fx_service.now_utc", side_effect=_now), \
             patch.object(svc, "_fetch_and_persist_history", side_effect=fake_fetch) as fetch:
            rate = svc.get_rate("USD", "CAD", as_of=TODAY)

        assert rate == FRESH_RATE
        fetch.assert_called_once()

    def test_heal_happens_once_per_pair_per_service(self):
        table = FakeRatesTable([("USD", "CAD", STALE_DATE, STALE_RATE)])
        svc = FXService(table)

        def fake_fetch(base, target, start, end):
            table.rows.append(("USD", "CAD", FRESH_DATE, FRESH_RATE))
            return [(FRESH_DATE, FRESH_RATE)]

        with patch("shared.fx_service.now_utc", side_effect=_now), \
             patch.object(svc, "_fetch_and_persist_history", side_effect=fake_fetch) as fetch:
            svc.get_rate("USD", "CAD", as_of=TODAY)
            svc._cache.clear()  # force a fresh resolution path
            svc.get_rate("USD", "CAD", as_of=TODAY - timedelta(days=1))

        assert fetch.call_count == 1

    def test_failed_heal_falls_back_to_stale_rate_with_warning(self, caplog):
        table = FakeRatesTable([("USD", "CAD", STALE_DATE, STALE_RATE)])
        svc = FXService(table)
        with caplog.at_level(logging.WARNING, logger="shared.fx_service"), \
             patch("shared.fx_service.now_utc", side_effect=_now), \
             patch.object(svc, "_fetch_and_persist_history", return_value=0):
            rate = svc.get_rate("USD", "CAD", as_of=TODAY)

        assert rate == STALE_RATE
        assert "forward-filling" in caplog.text
        assert "57 days old" in caplog.text

    def test_fresh_rate_never_fetches(self):
        table = FakeRatesTable([("USD", "CAD", FRESH_DATE, FRESH_RATE)])
        svc = FXService(table)
        with patch("shared.fx_service.now_utc", side_effect=_now), \
             patch.object(svc, "_fetch_and_persist_history") as fetch:
            rate = svc.get_rate("USD", "CAD", as_of=TODAY)

        assert rate == FRESH_RATE
        fetch.assert_not_called()

    def test_historical_rebuild_stays_offline(self):
        table = FakeRatesTable([("USD", "CAD", date(2021, 1, 1), Decimal("1.2"))])
        svc = FXService(table)
        with patch("shared.fx_service.now_utc", side_effect=_now), \
             patch.object(svc, "_fetch_and_persist_history") as fetch:
            rate = svc.get_rate("USD", "CAD", as_of=date(2021, 3, 1))

        assert rate == Decimal("1.2")
        fetch.assert_not_called()

    def test_stale_warning_still_logged_for_direct_query_callers(self, caplog):
        """Preserve the old _query_cached_rate contract exactly."""
        table = FakeRatesTable([("USD", "CAD", STALE_DATE, STALE_RATE)])
        svc = FXService(table)
        with caplog.at_level(logging.WARNING, logger="shared.fx_service"):
            rate = svc._query_cached_rate("USD", "CAD", TODAY)
        assert rate == STALE_RATE
        assert "forward-filling" in caplog.text
