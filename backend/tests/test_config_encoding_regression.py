"""REG-006-ENC: startup config output must be ASCII-safe on Windows consoles.

Observed symptom: `Earnings Buffer : ?10 days` — the `±` glyph was replaced by
`?` under a cp1252/cp437 console. Startup output must not depend on the terminal
code page.
"""
from __future__ import annotations

from types import SimpleNamespace

from config import config_summary_lines


def _settings():
    return SimpleNamespace(
        ENVIRONMENT="local",
        API_HOST="127.0.0.1",
        API_PORT=8000,
        SUPABASE_URL="http://localhost",
        SUPABASE_SERVICE_ROLE_KEY="eyJtest",
        OPEN_ROUTER_KEY="",
        ENABLE_EARNINGS_SCHEDULER=True,
        ENABLE_MARKET_DATA_SCHEDULER=False,
        EARNINGS_REFRESH_CHECK_INTERVAL_HOURS=24,
        EARNINGS_REFRESH_BUFFER_DAYS=10,
        RETRY_MAX_ATTEMPTS=3,
        RETRY_BACKOFF_SECONDS=2,
        ENABLE_YFINANCE_FALLBACK=True,
        ENABLE_DEDUPLICATION_OPTIMIZATION=True,
    )


def test_earnings_buffer_line_is_ascii_and_readable():
    lines = config_summary_lines(_settings())
    line = next(line for line in lines if "Earnings Buffer" in line)

    assert line.isascii(), f"non-ASCII glyph in startup output: {line!r}"
    assert "+/-10 days" in line
