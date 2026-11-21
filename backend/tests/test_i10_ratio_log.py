"""I10 -- a version-gated no-op must not read as a ratios failure.

``compute_and_upsert_derived_financial_metrics`` returns
``{"count": years_evaluated, "rows_changed": rows_actually_written}``. When the
source data is unchanged the version gate legitimately writes 0 rows. The old
log line ``[RATIOS] SYM: 0/5 rows written`` reads as "only 0 of 5 expected rows
made it", i.e. a failure, when it is the healthy no-op path.
"""
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def scheduler(mock_financial_repo, mock_defeat_beta_provider):
    s = MarketDataRefreshScheduler(
        financial_repo=mock_financial_repo,
        defeat_beta_provider=mock_defeat_beta_provider,
        yfinance_provider=SimpleNamespace(
            fetch_revenue_forecast=AsyncMock(return_value=[]),
            fetch_earnings_forecast=AsyncMock(return_value=[]),
        ),
    )
    mock_financial_repo.get_company_refresh_info.return_value = SimpleNamespace(
        company_id=1,
        ticker_symbol="AAPL",
        exchange=None,
        security_type="stock",
        first_financial_data_loaded_at=None,
        last_refreshed_fiscal_year=2024,
        last_refreshed_fiscal_quarter=None,
        data_completeness_status="COMPLETE",
    )
    with patch.object(s, "_upsert_daily_price_history", return_value=0), \
         patch.object(s, "_has_any_financials", return_value=True):
        yield s


@pytest.mark.anyio
async def test_noop_ratios_log_is_not_a_bare_failure(scheduler):
    """RED: 0 changes must be identified as an expected version-gated no-op."""
    capture = _Capture()
    log = logging.getLogger("application.schedulers.market_data_scheduler")
    log.addHandler(capture)
    log.setLevel(logging.INFO)
    try:
        with patch(
            "application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics",
            new=AsyncMock(return_value={"count": 5, "rows_changed": 0, "upserted": False}),
        ), patch(
            "application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics",
            new=AsyncMock(return_value={"upserted": 0}),
        ), patch(
            "application.services.valuation_service.ValuationService"
        ) as mock_vs:
            mock_vs.return_value = AsyncMock()
            await scheduler._process_company("AAPL", 1)
    finally:
        log.removeHandler(capture)

    ratio_lines = [m for m in capture.messages if m.startswith("[RATIOS]")]
    assert len(ratio_lines) == 1
    line = ratio_lines[0]
    assert "0/5" in line
    assert "no-op" in line or "unchanged" in line or "no source changes" in line, line
    assert "version" in line.lower(), line


@pytest.mark.anyio
async def test_changed_ratios_log_reports_writes(scheduler):
    """Guard: a real write is still reported as rows written/changed."""
    capture = _Capture()
    log = logging.getLogger("application.schedulers.market_data_scheduler")
    log.addHandler(capture)
    log.setLevel(logging.INFO)
    try:
        with patch(
            "application.schedulers.market_data_scheduler.compute_and_upsert_derived_financial_metrics",
            new=AsyncMock(return_value={"count": 5, "rows_changed": 3, "upserted": True}),
        ), patch(
            "application.schedulers.market_data_scheduler.compute_and_upsert_dividend_metrics",
            new=AsyncMock(return_value={"upserted": 0}),
        ), patch(
            "application.services.valuation_service.ValuationService"
        ) as mock_vs:
            mock_vs.return_value = AsyncMock()
            await scheduler._process_company("AAPL", 1)
    finally:
        log.removeHandler(capture)

    ratio_lines = [m for m in capture.messages if m.startswith("[RATIOS]")]
    assert len(ratio_lines) == 1
    assert "3/5" in ratio_lines[0]
