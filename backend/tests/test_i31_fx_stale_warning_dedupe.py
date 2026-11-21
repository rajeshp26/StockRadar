"""I31 -- repeated FX-staleness warnings must be deduped.

A snapshot rebuild resolves hundreds of dates against the same stale close.
``FXService._warn_stale_rate`` logged a full WARNING on every one, producing the
"FX rate USD->CAD is N days old ..." line 8+ times per run. The heal *fetch* was
already deduped in I4 (``_healed_pairs``); the warning was not.

Contract: warn once per (pair, stale close date) per service instance. A new
stale close (ingestion landed a different rate) warns again, and distinct pairs
warn independently. The message text is unchanged (I4 asserts on it).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from shared.fx_service import FXService

LOGGER = "shared.fx_service"
STALE_CLOSE = date(2026, 9, 22)


@pytest.fixture
def service():
    return FXService(MagicMock())


def _stale_warnings(caplog):
    return [r for r in caplog.records if "FX rate " in r.getMessage()]


def test_same_stale_close_warns_once(service, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for i in range(8):
            service._warn_stale_rate(
                "USD", "CAD", STALE_CLOSE + timedelta(days=40 + i), STALE_CLOSE
            )

    assert len(_stale_warnings(caplog)) == 1, caplog.text
    assert "forward-filling" in caplog.text


def test_new_stale_close_warns_again(service, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        service._warn_stale_rate("USD", "CAD", STALE_CLOSE + timedelta(days=40), STALE_CLOSE)
        service._warn_stale_rate(
            "USD", "CAD", STALE_CLOSE + timedelta(days=60), date(2026, 10, 20)
        )

    assert len(_stale_warnings(caplog)) == 2, caplog.text


def test_each_pair_warns_independently(service, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        service._warn_stale_rate("USD", "CAD", STALE_CLOSE + timedelta(days=40), STALE_CLOSE)
        service._warn_stale_rate("EUR", "USD", STALE_CLOSE + timedelta(days=40), STALE_CLOSE)

    assert len(_stale_warnings(caplog)) == 2, caplog.text
    assert "USD->CAD" in caplog.text
    assert "EUR->USD" in caplog.text


def test_fresh_rate_never_warns(service, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for i in range(service.MAX_STALE_DAYS):
            service._warn_stale_rate(
                "USD", "CAD", STALE_CLOSE + timedelta(days=i), STALE_CLOSE
            )

    assert _stale_warnings(caplog) == []


def test_suppressed_count_is_tracked(service, caplog):
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        for i in range(8):
            service._warn_stale_rate(
                "USD", "CAD", STALE_CLOSE + timedelta(days=40 + i), STALE_CLOSE
            )

    assert service.stale_warning_suppressed == 7, service.stale_warning_suppressed
