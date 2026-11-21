"""I9 -- a single symbol's retry must not wipe the shared DuckDB httpfs cache.

``defeatbeta_api.client.duckdb_client.get_duckdb_client()`` returns a module-level
singleton whose ``_clear_cache()`` runs ``SELECT cache_httpfs_clear_cache()`` --
a global wipe of the on-disk cache shared by every worker. Under concurrency=5,
one symbol's transient retry evicted every other worker's cached downloads
(certain wasted re-download; plus a cross-process file-lock race). Cache
freshness is already validated by the SDK at client init, and a genuinely failed
fetch still falls back to yfinance, so the retry-time global clear is unnecessary.

The test patches the SDK import at source so it is valid both before and after
the fix (the provider helper may be removed entirely).
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from domain.exceptions import DefeatBetaException
from domain.model_types import (
    BalanceSheetRows,
    CashFlowRows,
    CompleteFundamentals,
    DividendRows,
    EarningsRows,
    IncomeStatementRows,
)
from providers.defeat_beta_provider import DefeatBetaProvider


def _empty_fundamentals() -> CompleteFundamentals:
    return CompleteFundamentals(
        company_id=1,
        symbol="AAPL",
        income_statements=IncomeStatementRows(rows=[]),
        balance_sheets=BalanceSheetRows(rows=[]),
        cash_flows=CashFlowRows(rows=[]),
        earnings=EarningsRows(rows=[]),
        dividends=DividendRows(rows=[]),
    )


@pytest.mark.anyio
async def test_transient_retry_does_not_clear_shared_cache():
    """RED: retried transient errors must not call the SDK's global cache clear."""
    provider = DefeatBetaProvider(yfinance_provider=MagicMock())
    provider._fetch_all_financials_internal = AsyncMock(
        side_effect=DefeatBetaException("timeout", error_code="DEFEAT_BETA_FETCH_ERROR")
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
        await provider.get_all_financials_optimized("AAPL", 1)

    # Transient errors still retried the configured number of times ...
    assert provider._fetch_all_financials_internal.await_count == provider.settings.RETRY_MAX_ATTEMPTS
    assert sleep.await_count == provider.settings.RETRY_MAX_ATTEMPTS - 1
    # ... but the shared cache was never wiped.
    fake_client._clear_cache.assert_not_called()
    provider._fallback_to_yfinance.assert_awaited_once()
