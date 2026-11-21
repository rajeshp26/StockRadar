"""I8 -- the earnings financials path must skip ETF/index/fund fundamentals.

``market_data_scheduler._process_company`` enforces the contract with an
``is_stock`` guard (steps 3-7 are stock-only). ``earnings_scheduler``'s
``_refresh_company_financials_optimized`` had no equivalent guard: every call
path (worker handler, immediate check, reconciliation follow-up) relied solely
on the repository's ``security_type eq stock OR null`` query filter. A
mislabeled or manually-enqueued ETF therefore reached IS/BS/CF refresh (and,
per I7, a DEFEAT_BETA_NO_DATA retry storm).

The guard reads the authoritative ``companies.security_type`` at execution
time from ``refresh_info`` and skips only when the value is explicitly a
non-stock type -- ``stock``, NULL, and unknown/missing values stay admitted,
matching the repository filter and preserving the no-data-for-tests behaviour.
"""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from application.schedulers.earnings_scheduler import EarningsRefreshScheduler


def _refresh_info(security_type):
    ns = SimpleNamespace(
        company_id=1,
        ticker_symbol="SPY",
        exchange=None,
        first_financial_data_loaded_at=datetime(2024, 1, 1),
        last_refreshed_fiscal_year=2024,
        last_refreshed_fiscal_quarter=None,
        data_completeness_status="COMPLETE",
    )
    if security_type is not None:
        ns.security_type = security_type
    return ns


def _financials():
    return SimpleNamespace(
        income_statements=SimpleNamespace(rows=[]),
        balance_sheets=SimpleNamespace(),
        cash_flows=SimpleNamespace(),
        earnings=SimpleNamespace(),
        dividends=SimpleNamespace(),
        next_earnings_date=None,
    )


@pytest.fixture
def scheduler(mock_financial_repo, mock_defeat_beta_provider):
    return EarningsRefreshScheduler(
        financial_repo=mock_financial_repo,
        defeat_beta_provider=mock_defeat_beta_provider,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["etf", "ETF", "index", "fund"])
async def test_non_stock_security_type_skips_fundamentals(scheduler, kind):
    """RED: an ETF/index/fund reaches the financials path -> must not fetch."""
    scheduler.financial_repo.get_company_refresh_info.return_value = _refresh_info(kind)
    scheduler.defeat_beta_provider.get_all_financials_optimized.return_value = _financials()

    with patch(
        "application.schedulers.earnings_scheduler.compute_and_upsert_derived_financial_metrics"
    ) as derived:
        result = await scheduler._refresh_company_financials_optimized(
            company_id=1, symbol="SPY",
        )

    scheduler.defeat_beta_provider.get_all_financials_optimized.assert_not_called()
    scheduler.financial_repo.upsert_all_financials.assert_not_called()
    derived.assert_not_called()
    assert result["skipped_non_stock"] is True
    assert result["security_type"] == kind
    assert result["total_rows"] == 0


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["stock", None, "MISSING"])
async def test_stock_or_unknown_security_type_still_refreshes(scheduler, kind):
    """Guard must not over-block stock, null-typed, or legacy companies."""
    info = _refresh_info(None if kind == "MISSING" else kind)
    scheduler.financial_repo.get_company_refresh_info.return_value = info
    scheduler.defeat_beta_provider.get_all_financials_optimized.return_value = _financials()
    scheduler.financial_repo.upsert_all_financials.return_value = {}

    await scheduler._refresh_company_financials_optimized(company_id=1, symbol="AAPL")

    scheduler.defeat_beta_provider.get_all_financials_optimized.assert_awaited_once()
    scheduler.financial_repo.upsert_all_financials.assert_awaited_once()
