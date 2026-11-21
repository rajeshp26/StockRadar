"""I22 -- ``Synced N/M earnings dates`` must name the failing symbol(s).

Observed in the worker log: ``[EARNINGS_CALENDAR] Synced 19/20 earnings dates``
with no indication of which symbol failed or why. The sync helper swallows every
failure into a bare ``return False`` and the summary log counts only successes,
so an operator cannot act on the one missing earnings date.

These tests drive ``_sync_earnings_calendar`` with a fake provider/repo where one
symbol yields no date and another raises on the update, and assert the summary
log names each failing symbol with a reason. Today it does not (RED).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta

from application.schedulers.earnings_scheduler import EarningsRefreshScheduler


class _FakeRepo:
    def __init__(self, companies: list[dict]) -> None:
        self._companies = companies
        self.updated: list[int] = []

    async def get_companies_with_financial_data(self) -> list[dict]:
        return self._companies

    async def update_next_earnings_date(self, company_id: int, earnings_date: date) -> None:
        self.updated.append(company_id)
        if company_id == 102:
            raise RuntimeError("db write rejected")


class _FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def fetch_next_earnings_date(self, symbol: str) -> date | None:
        self.calls.append(symbol)
        if symbol == "NODATE":
            return None
        return date.today() + timedelta(days=7)


def _scheduler(monkeypatch) -> EarningsRefreshScheduler:
    # Bypass DI so no real provider/DB is constructed.
    monkeypatch.setattr(
        "application.schedulers.earnings_scheduler.SupabaseFinancialRepository",
        lambda: None,
    )
    return EarningsRefreshScheduler(
        financial_repo=_FakeRepo([]),  # type: ignore[arg-type]
        defeat_beta_provider=_FakeProvider(),  # type: ignore[arg-type]
    )


def test_summary_log_names_symbol_with_no_date(monkeypatch, caplog):
    companies = [
        {"company_id": 101, "ticker_symbol": "GOOD"},
        {"company_id": 102, "ticker_symbol": "NODATE"},
    ]
    sched = _scheduler(monkeypatch)
    sched.financial_repo = _FakeRepo(companies)  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="application.schedulers.earnings_scheduler"):
        asyncio.run(sched._sync_earnings_calendar())

    summary = [r.message for r in caplog.records if "EARNINGS_CALENDAR" in r.message]
    assert summary, "no EARNINGS_CALENDAR summary logged"
    assert "NODATE" in summary[-1], f"failing symbol not named: {summary[-1]}"


def test_summary_log_names_symbol_whose_update_failed(monkeypatch, caplog):
    companies = [
        {"company_id": 101, "ticker_symbol": "GOOD"},
        {"company_id": 102, "ticker_symbol": "WRFAIL"},
    ]
    sched = _scheduler(monkeypatch)
    sched.financial_repo = _FakeRepo(companies)  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="application.schedulers.earnings_scheduler"):
        asyncio.run(sched._sync_earnings_calendar())

    summary = [r.message for r in caplog.records if "EARNINGS_CALENDAR" in r.message]
    assert summary, "no EARNINGS_CALENDAR summary logged"
    assert "WRFAIL" in summary[-1], f"failing symbol not named: {summary[-1]}"


def test_successes_still_counted(monkeypatch, caplog):
    companies = [
        {"company_id": 101, "ticker_symbol": "GOOD"},
        {"company_id": 102, "ticker_symbol": "NODATE"},
    ]
    sched = _scheduler(monkeypatch)
    sched.financial_repo = _FakeRepo(companies)  # type: ignore[assignment]

    with caplog.at_level(logging.INFO, logger="application.schedulers.earnings_scheduler"):
        asyncio.run(sched._sync_earnings_calendar())

    summary = [r.message for r in caplog.records if "EARNINGS_CALENDAR" in r.message]
    assert "1/2" in summary[-1], f"success count wrong: {summary[-1]}"
