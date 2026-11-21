"""I20 -- earnings planner DB I/O must not block the event loop.

The planner log showed `[PLANNER] earnings: planned 5 jobs in 15612 ms` inside a
60 s loop. The duration is `plan_fn()` wall time; `plan()` awaits
`_sync_earnings_calendar()`, whose repository calls are declared ``async def``
but execute the *synchronous* Supabase client on the event loop. With ~150
tracked companies that serialises into seconds of blocked loop time.

A heartbeat coroutine can only tick while the loop is free. These tests drive
the two methods in the calendar-sync path with a client whose ``.execute()``
blocks; today the heartbeat is starved (RED). The fix moves the sync call to a
worker thread with ``asyncio.to_thread`` (the pattern already used in
``valuation_repository.py``), so the heartbeat keeps ticking (GREEN).
"""
from __future__ import annotations

import asyncio
import time
from datetime import date

from infrastructure.repositories.financial_repository import (
    SupabaseFinancialRepository,
)


class _BlockingResult:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _BlockingQuery:
    """Chainable fake; only .execute() blocks, like a real sync HTTP client."""

    def __init__(self, client: _BlockingClient, data: list[dict]) -> None:
        self._client = client
        self._data = data

    def execute(self) -> _BlockingResult:
        time.sleep(self._client.delay)
        return _BlockingResult(self._data)

    def __getattr__(self, _name: str) -> _BlockingQuery:
        return self  # select / eq / in_ / range / update / ... are all chainable

    def __call__(self, *_args, **_kwargs) -> _BlockingQuery:
        return self  # the chained methods are invoked with arguments


class _BlockingClient:
    def __init__(self, delay: float, data: list[dict]) -> None:
        self.delay = delay
        self.data = data

    def table(self, _name: str) -> _BlockingQuery:
        return _BlockingQuery(self, self.data)


async def _heartbeat_ticks(coro_factory) -> int:
    ticks = 0
    stop = False

    async def heartbeat() -> None:
        nonlocal ticks
        while not stop:
            ticks += 1
            await asyncio.sleep(0.002)

    task = asyncio.create_task(heartbeat())
    await asyncio.sleep(0)  # let the heartbeat start before the blocking call
    await coro_factory()
    stop = True
    await task
    return ticks


def test_get_companies_with_financial_data_does_not_block_event_loop():
    client = _BlockingClient(0.15, [{"company_id": 69, "ticker_symbol": "AAPL"}])
    repo = SupabaseFinancialRepository(client=client)  # type: ignore[arg-type]

    ticks = asyncio.run(
        _heartbeat_ticks(lambda: repo.get_companies_with_financial_data())
    )
    assert ticks > 5, f"event loop was blocked (heartbeat ticks={ticks})"


def test_update_next_earnings_date_does_not_block_event_loop():
    client = _BlockingClient(0.15, [])
    repo = SupabaseFinancialRepository(client=client)  # type: ignore[arg-type]

    ticks = asyncio.run(
        _heartbeat_ticks(lambda: repo.update_next_earnings_date(69, date.today()))
    )
    assert ticks > 5, f"event loop was blocked (heartbeat ticks={ticks})"


def test_get_companies_with_upcoming_earnings_does_not_block_event_loop():
    client = _BlockingClient(0.15, [{"company_id": 69, "ticker_symbol": "AAPL"}])
    repo = SupabaseFinancialRepository(client=client)  # type: ignore[arg-type]

    ticks = asyncio.run(
        _heartbeat_ticks(
            lambda: repo.get_companies_with_upcoming_earnings(
                date(2026, 11, 1), date(2026, 11, 30)
            )
        )
    )
    assert ticks > 5, f"event loop was blocked (heartbeat ticks={ticks})"


def test_get_stale_financial_companies_does_not_block_event_loop():
    client = _BlockingClient(0.15, [{"company_id": 69, "ticker_symbol": "AAPL"}])
    repo = SupabaseFinancialRepository(client=client)  # type: ignore[arg-type]

    ticks = asyncio.run(
        _heartbeat_ticks(
            lambda: repo.get_stale_financial_companies(
                fresh_cutoff=date(2026, 9, 30),
                consult_cutoff=date(2026, 11, 1),
            )
        )
    )
    assert ticks > 5, f"event loop was blocked (heartbeat ticks={ticks})"


class _BlockingRepo:
    """Control-plane repo whose sync methods block like the real HTTP client."""

    def __init__(self, delay: float) -> None:
        self.delay = delay

    def _block(self) -> None:
        time.sleep(self.delay)

    def get_scheduler_state(self, _name):
        self._block()
        return None  # no stored state -> plan_fn is always due

    def enqueue_job(self, **_job):
        self._block()
        return True

    def upsert_scheduler_state(self, *_args, **_kwargs):
        self._block()

    def record_planner_run(self, *_args, **_kwargs):
        self._block()

    def update_scheduler_state(self, *_args, **_kwargs):
        self._block()


def test_planner_tick_control_plane_io_does_not_block_event_loop():
    from application.schedulers.planner import SchedulerPlanner

    async def fast_plan():
        return []

    planner = SchedulerPlanner(scheduler_repo=_BlockingRepo(0.05))  # type: ignore[arg-type]
    planner.register("earnings", fast_plan, interval_hours=1)

    ticks = asyncio.run(_heartbeat_ticks(planner._check_and_plan))
    # Several blocking repo calls. If any ran on the loop directly the
    # heartbeat would be starved to ~1 tick (as the RED cases above showed);
    # with to_thread it keeps ticking. Windows timer granularity (~15 ms) means
    # sleep(0.002) yields far fewer than the theoretical count.
    assert ticks > 5, f"planner tick blocked the event loop (heartbeat ticks={ticks})"
