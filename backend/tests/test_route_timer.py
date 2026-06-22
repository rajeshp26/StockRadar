"""Unit tests for RouteTimer instrumentation."""

import io
import logging
from shared.metrics import RouteTimer


def test_route_timer_logs_duration(caplog):
    """Context manager logs expected fields."""
    caplog.set_level(logging.INFO, logger="perf.portfolio")
    with RouteTimer("/test/endpoint", 42, account_count=3, holdings_count=10):
        pass

    assert any("[PERF]" in record.message for record in caplog.records)
    assert any("/test/endpoint" in record.message for record in caplog.records)
    assert any("user=42" in record.message for record in caplog.records)
    assert any("accounts=3" in record.message for record in caplog.records)
    assert any("holdings=10" in record.message for record in caplog.records)


def test_route_timer_zero_holdings(caplog):
    """Logs correctly with zero counts."""
    caplog.set_level(logging.INFO, logger="perf.portfolio")
    with RouteTimer("/test/empty", 1, account_count=0, holdings_count=0):
        pass

    assert any("accounts=0" in record.message for record in caplog.records)
    assert any("holdings=0" in record.message for record in caplog.records)


def test_route_timer_cache_hit_flag(caplog):
    """cache_hit=True appears in log output."""
    caplog.set_level(logging.INFO, logger="perf.portfolio")
    with RouteTimer("/test/cached", 1, cache_hit=True):
        pass

    assert any("cache_hit=True" in record.message for record in caplog.records)


def test_route_timer_cache_miss_flag(caplog):
    """cache_hit=False appears in log output."""
    caplog.set_level(logging.INFO, logger="perf.portfolio")
    with RouteTimer("/test/miss", 1, cache_hit=False):
        pass

    assert any("cache_hit=False" in record.message for record in caplog.records)
