"""I23 -- an empty EDGAR result must not be reported as a clean 'completed'.

Observed: ``No filings found for David Einhorn`` followed by a `completed` job.
Two distinct things were collapsed: (a) ``get_filings`` raised (a failure) and
(b) it returned nothing (an empty result). Both were swallowed into ``False``,
which the handler mapped to ``skipped`` -> the job engine's ``completed``.

The fix gives the refresh path an explicit outcome so a failure is distinguishable
from an empty result and from a benign "not due yet" skip:
  * fetch exception -> ERROR (logged with the real cause, not "No filings found")
  * genuinely empty -> NO_FILINGS
  * not due yet     -> SKIPPED_NOT_DUE
  * new rows saved  -> REFRESHED
and the job handler surfaces these distinctly (ERROR raises so the engine fails
the job instead of reporting completed). RED today.
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from application.schedulers.super_investors_scheduler import (
    InvestorRefreshStatus,
    SuperInvestorsRefreshScheduler,
)

INFO = {"name": "David Einhorn", "firm": "Greenlight", "tag": "einhorn", "style": ""}


class _EmptyFilings:
    def filter(self, cik=None):
        return self

    def __len__(self):
        return 0

    def __iter__(self):
        return iter([])


def _scheduler(mock_financial_repo):
    sched = SuperInvestorsRefreshScheduler.__new__(SuperInvestorsRefreshScheduler)
    sched.financial_repo = mock_financial_repo
    sched._update_investor_tracking = AsyncMock()
    sched._ensure_edgar_identity = lambda: None
    return sched


async def test_fetch_exception_is_error_not_no_filings(mock_financial_repo, caplog):
    sched = _scheduler(mock_financial_repo)
    with (
        patch("edgar.get_filings", side_effect=RuntimeError("SEC 429 rate limited")),
        caplog.at_level(logging.WARNING, logger="application.schedulers.super_investors_scheduler"),
    ):
        outcome = await sched._fetch_new_filing("0001", INFO, None)

    assert outcome == InvestorRefreshStatus.ERROR
    assert not any("No filings found" in r.getMessage() for r in caplog.records)
    assert any("429" in r.getMessage() for r in caplog.records)


async def test_genuinely_empty_result_is_no_filings(mock_financial_repo, caplog):
    sched = _scheduler(mock_financial_repo)
    with (
        patch("edgar.get_filings", return_value=_EmptyFilings()),
        caplog.at_level(logging.WARNING, logger="application.schedulers.super_investors_scheduler"),
    ):
        outcome = await sched._fetch_new_filing("0001", INFO, None)

    assert outcome == InvestorRefreshStatus.NO_FILINGS
    assert any("No filings found" in r.getMessage() for r in caplog.records)


async def test_not_due_is_distinct_from_no_filings(mock_financial_repo):
    sched = _scheduler(mock_financial_repo)
    # Stored period in the future -> not due yet.
    sched.financial_repo.client.table.return_value.select.return_value.eq.return_value.execute.return_value = SimpleNamespace(
        data=[{"investor_id": 1, "last_filed_period": "2099-03-31", "last_filed_date": "2099-05-15"}]
    )
    outcome = await sched._refresh_single_investor("0001", INFO)
    assert outcome == InvestorRefreshStatus.SKIPPED_NOT_DUE


def test_handler_maps_no_filings_to_distinct_status(monkeypatch):
    import scheduler_worker

    inst = SuperInvestorsRefreshScheduler.__new__(SuperInvestorsRefreshScheduler)
    inst._refresh_single_investor = AsyncMock(return_value=InvestorRefreshStatus.NO_FILINGS)
    monkeypatch.setattr(scheduler_worker, "SuperInvestorsRefreshScheduler", lambda: inst)

    result = pytest_run_async(
        scheduler_worker.handle_investor_refresh, {"payload": {"cik": "0001", "name": "David Einhorn"}}
    )
    assert result["status"] == "no_filings"
    assert result["status"] != "skipped"


def test_handler_raises_on_error(monkeypatch):
    import scheduler_worker

    inst = SuperInvestorsRefreshScheduler.__new__(SuperInvestorsRefreshScheduler)
    inst._refresh_single_investor = AsyncMock(return_value=InvestorRefreshStatus.ERROR)
    monkeypatch.setattr(scheduler_worker, "SuperInvestorsRefreshScheduler", lambda: inst)

    with pytest.raises(RuntimeError, match="investor_refresh failed"):
        pytest_run_async(
            scheduler_worker.handle_investor_refresh,
            {"payload": {"cik": "0001", "name": "David Einhorn"}},
        )


def pytest_run_async(coro_fn, *args):
    import asyncio

    return asyncio.run(coro_fn(*args))
