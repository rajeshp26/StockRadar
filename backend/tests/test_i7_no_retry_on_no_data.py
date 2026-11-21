"""I7 -- deterministic NO_DATA is not retried; only transient faults are.

DefeatBeta's dataset has no Canadian ``.TO`` tickers. ``Ticker("T.TO")`` raises
``NoDataError`` (``DEFEAT_BETA_NO_DATA``) on every attempt: a mapping gap, not a
transient fault. The retry loop must not sleep/backoff for a result that cannot
change -- it should go straight to the yfinance fallback. The job layer already
treats this error as terminal (``SchedulerRepository.fail_job``); the provider
must be consistent.

(The shared-cache-clear assertion that used to live here moved to
``test_i9_no_shared_cache_clear.py`` after I9 removed the clear entirely.)
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.exceptions import DefeatBetaException, NoDataError
from domain.model_types import (
    BalanceSheetRows,
    CashFlowRows,
    CompleteFundamentals,
    DividendRows,
    EarningsRows,
    IncomeStatementRows,
)
from providers.defeat_beta_provider import DefeatBetaProvider


def _empty_fundamentals(symbol="T.TO") -> CompleteFundamentals:
    return CompleteFundamentals(
        company_id=60,
        symbol=symbol,
        income_statements=IncomeStatementRows(rows=[]),
        balance_sheets=BalanceSheetRows(rows=[]),
        cash_flows=CashFlowRows(rows=[]),
        earnings=EarningsRows(rows=[]),
        dividends=DividendRows(rows=[]),
    )


def _provider() -> DefeatBetaProvider:
    # yfinance fallback configured so the no-data path has somewhere to go.
    return DefeatBetaProvider(yfinance_provider=MagicMock())


@pytest.mark.anyio
async def test_no_data_error_does_not_retry():
    """A deterministic NO_DATA should hit the provider once, not 3 times."""
    provider = _provider()
    provider._fetch_all_financials_internal = AsyncMock(
        side_effect=NoDataError("T.TO", ["income_statements"])
    )
    provider._fallback_to_yfinance = AsyncMock(return_value=_empty_fundamentals())

    fake_client = MagicMock()
    fake_get_client = MagicMock(return_value=fake_client)
    with patch(
        "providers.defeatbeta_runtime.import_get_duckdb_client",
        return_value=fake_get_client,
    ), patch(
        "providers.defeat_beta_provider.asyncio.sleep", new=AsyncMock()
    ) as sleep:
        result = await provider.get_all_financials_optimized("T.TO", 60)

    assert provider._fetch_all_financials_internal.await_count == 1
    assert sleep.await_count == 0
    fake_client._clear_cache.assert_not_called()
    provider._fallback_to_yfinance.assert_awaited_once()
    assert result.symbol == "T.TO"


@pytest.mark.anyio
async def test_transient_error_still_retries():
    """Guard against over-correction: real transient faults keep the retry policy."""
    provider = _provider()
    provider._fetch_all_financials_internal = AsyncMock(
        side_effect=DefeatBetaException("timeout", error_code="DEFEAT_BETA_FETCH_ERROR")
    )
    provider._fallback_to_yfinance = AsyncMock(return_value=_empty_fundamentals())

    with patch("providers.defeat_beta_provider.asyncio.sleep", new=AsyncMock()) as sleep:
        await provider.get_all_financials_optimized("T.TO", 60)

    assert provider._fetch_all_financials_internal.await_count == provider.settings.RETRY_MAX_ATTEMPTS
    assert sleep.await_count == provider.settings.RETRY_MAX_ATTEMPTS - 1
    provider._fallback_to_yfinance.assert_awaited_once()
