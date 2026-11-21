"""I24 -- the valuation planner must not enqueue jobs for delisted symbols.

Observed log: ``market_data: 166 jobs`` vs ``valuation_computation: 172 jobs``.
Both planners enumerate the same active-company set via
``get_active_companies_for_market_data()``, but only the market-data planner
filters ``get_effective_skipped_symbols()`` (the 6 hardcoded DELISTED_SYMBOLS
plus any env-configured ones). The valuation planner was never wired to that
shared filter, so it enqueues exactly those 6 dead tickers -> the 172-166 gap.

Contract: valuation ``plan()`` excludes every effective skipped symbol and
produces the same count as the market-data ``plan()`` for the same input.
RED today.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
from application.schedulers.valuation_computation_scheduler import ValuationComputationScheduler
from shared.constants import DELISTED_SYMBOLS, get_effective_skipped_symbols

LIVE = ["AAPL", "MSFT", "GOOGL", "AMZN"]


def _companies():
    symbols = list(DELISTED_SYMBOLS) + LIVE
    return [
        {"company_id": i, "ticker_symbol": s, "security_type": "stock"}
        for i, s in enumerate(symbols, 1)
    ]


def _fake_repo():
    repo = MagicMock()
    repo.get_active_companies_for_market_data = AsyncMock(return_value=_companies())
    return repo


async def _valuation_jobs(repo):
    sched = ValuationComputationScheduler()
    with patch(
        "infrastructure.repositories.financial_repository.SupabaseFinancialRepository",
        return_value=repo,
    ):
        return await sched.plan()


async def test_valuation_plan_excludes_hardcoded_delisted_symbols():
    jobs = await _valuation_jobs(_fake_repo())
    symbols = {j["payload"]["symbol"] for j in jobs}
    assert not (symbols & DELISTED_SYMBOLS), (
        f"delisted symbols leaked into valuation plan: {symbols & DELISTED_SYMBOLS}"
    )
    assert {j["payload"]["symbol"] for j in jobs} == set(LIVE)


async def test_valuation_and_market_data_planners_agree_on_count():
    repo = _fake_repo()
    valuation_jobs = await _valuation_jobs(repo)

    md = MarketDataRefreshScheduler.__new__(MarketDataRefreshScheduler)
    md.financial_repo = repo
    md.skipped_symbols = get_effective_skipped_symbols()
    market_jobs = await md.plan()

    assert len(valuation_jobs) == len(market_jobs) == len(LIVE)


async def test_effective_skip_set_from_helper_is_honoured():
    # get_effective_skipped_symbols() is the single source of truth (hardcoded
    # set + any env-configured symbols). Patch the helper itself: this proves
    # valuation plan() consumes that shared set, whatever it contains.
    # NOTE: the Settings model has no SKIPPED_TICKER_SYMBOLS field (extra=forbid),
    # so that env overlay is latent/dead today -- recorded as a scope limit, not
    # fixed here (one issue at a time).
    effective = get_effective_skipped_symbols() | {"ZZZZ", "MSFT"}
    with patch("shared.constants.get_effective_skipped_symbols", return_value=effective):
        jobs = await _valuation_jobs(_fake_repo())
    symbols = {j["payload"]["symbol"] for j in jobs}
    assert "ZZZZ" not in symbols
    assert "MSFT" not in symbols
    assert "AAPL" in symbols
