"""Super-investors read-path: view-first read model, TTL cache, empty-miss path."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Response

import api.super_investors as si
from application.services.super_investors_cache import invalidate_super_investors_cache


def _view_row(
    investor_id=1,
    name="Terry Smith",
    firm="Fundsmith LLP",
    tag="FUNDSMITH",
    style="Long-Term Compounder",
    shares=1_000_000,
    value=500_000_000.0,
    weight=0.05,
    change_pct=0.0,
    change_type="new",
    quarter="2026-06-30",
    filing="2026-08-14",
):
    return {
        "investor_id": investor_id,
        "investor_name": name,
        "firm_name": firm,
        "investor_tag": tag,
        "investment_style": style,
        "shares_held": shares,
        "position_value": value,
        "portfolio_weight": weight,
        "shares_change_pct": change_pct,
        "change_type": change_type,
        "quarter_end_date": quarter,
        "filing_date": filing,
        "company_id": 1,
        "ticker_symbol": "MSFT",
        "company_name": "Microsoft Corporation",
    }


class _FakeQuery:
    def __init__(self, table, rows):
        self._table = table
        self._rows = rows

    def select(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        return SimpleNamespace(data=self._rows, count=len(self._rows))


class _FakeClient:
    def __init__(self, tables):
        self._tables = tables
        self.table_calls = []

    def table(self, name):
        self.table_calls.append(name)
        if name not in self._tables:
            raise Exception(f'relation "{name}" does not exist (test 42P01)')
        return _FakeQuery(name, self._tables[name])


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_super_investors_cache()
    yield
    invalidate_super_investors_cache()


async def test_view_hit_builds_payload_and_sets_cache_control():
    client = _FakeClient({"super_investor_current_holdings": [_view_row()]})
    with patch("api.super_investors.supabase", client):
        resp = await si.get_super_investors("MSFT", Response())

    assert resp["ticker"] == "MSFT"
    assert resp["overlap_count"] == 1
    assert resp["as_of"] == "2026-06-30"
    assert resp["data_updated_at"] == "2026-08-14"
    assert resp["source"] == "database"

    holder = resp["holders"][0]
    assert holder["investor_name"] == "Terry Smith"
    assert holder["firm"] == "Fundsmith LLP"
    assert holder["tag"] == "FUNDSMITH"
    assert holder["style"] == "Long-Term Compounder"
    assert holder["shares"] == 1_000_000
    assert holder["value"] == 500_000_000.0
    assert holder["change_pct"] == 0.0
    assert holder["quarter_date"] == "2026-06-30"

    # Single query against the view — no SEC fallback, no tracking queries.
    assert client.table_calls == ["super_investor_current_holdings"]


async def test_cache_serves_second_call_without_db():
    client = _FakeClient({"super_investor_current_holdings": [_view_row()]})
    with patch("api.super_investors.supabase", client):
        first = await si.get_super_investors("MSFT", Response())
        second = await si.get_super_investors("MSFT", Response())

    assert first == second
    assert len(client.table_calls) == 1


async def test_empty_miss_returns_empty_and_triggers_background_refresh():
    client = _FakeClient({"super_investor_current_holdings": []})
    with (
        patch("api.super_investors.supabase", client),
        patch("api.super_investors._trigger_investor_refresh_background") as trigger,
    ):
        resp = await si.get_super_investors("TSLA", Response())

    assert resp["overlap_count"] == 0
    assert resp["holders"] == []
    assert resp["as_of"] is None
    assert resp["source"] == "database"
    assert "queued" in resp["message"]
    trigger.assert_called_once_with("TSLA")


async def test_legacy_join_fallback_when_view_missing():
    holdings = [
        {
            "holding_id": 1, "shares_held": 1_000_000, "position_value": 5e8,
            "portfolio_weight": 0.05, "shares_change_pct": 0.0, "change_type": "new",
            "quarter_end_date": "2026-06-30", "filing_date": "2026-08-14", "investor_id": 1,
        },
        {
            "holding_id": 2, "shares_held": 900_000, "position_value": 4e8,
            "portfolio_weight": 0.04, "shares_change_pct": -0.1, "change_type": "decreased",
            "quarter_end_date": "2026-03-31", "filing_date": "2026-05-15", "investor_id": 1,
        },
    ]
    investors = [
        {
            "investor_id": 1, "investor_name": "Terry Smith", "firm_name": "Fundsmith LLP",
            "investor_tag": "FUNDSMITH", "investment_style": "Long-Term Compounder",
        }
    ]
    tables = {
        "companies": [{"company_id": 1, "ticker_symbol": "MSFT"}],
        "institutional_holdings": holdings,
        "institutional_investors": investors,
    }
    client = _FakeClient(tables)
    with patch("api.super_investors.supabase", client):
        resp = await si.get_super_investors("MSFT", Response())

    assert resp["overlap_count"] == 1
    assert resp["as_of"] == "2026-06-30"
    # Latest quarter per investor wins (view parity) — old quarter must not leak.
    assert resp["holders"][0]["quarter_date"] == "2026-06-30"
    assert resp["holders"][0]["change_pct"] == 0.0
    assert client.table_calls[:1] == ["super_investor_current_holdings"]


async def test_trigger_enqueues_plan_jobs_after_miss():
    jobs = [{"job_type": "investor_refresh", "dedupe_key": "investor_refresh:0001"}]
    sched_cls = MagicMock()
    sched_cls.return_value.plan = AsyncMock(return_value=jobs)
    repo_cls = MagicMock()
    repo_cls.return_value.enqueue_job_batch.return_value = 1

    with (
        patch("application.schedulers.super_investors_scheduler.SuperInvestorsRefreshScheduler", sched_cls),
        patch("infrastructure.repositories.scheduler_repository.SchedulerRepository", repo_cls),
    ):
        si._trigger_investor_refresh_background("TSLA")
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    sched_cls.return_value.plan.assert_awaited_once()
    repo_cls.return_value.enqueue_job_batch.assert_called_once_with(jobs)