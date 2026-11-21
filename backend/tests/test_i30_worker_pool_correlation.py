"""I30 -- every worker-pool line needs a correlation id, not just job lines.

I28 bound ``job-<id>`` inside ``JobEngine.execute_job``. The surrounding
``run_worker_pool`` / ``_worker_loop`` lines were still emitted outside that
scope, so with concurrency=5 their correlation id was the ``-`` placeholder:

* ``[WORKER_POOL] Starting with concurrency=5, worker_id=...``
* ``[WORKER:%d] Claimed job ...`` and ``[WORKER:%d] Error in worker loop ...``

Contract: the pool binds ``pool-<worker_id>`` for its lifetime, each of the five
worker loops binds ``worker-<index>``, and a job's ``job-<id>`` nests inside the
worker id and is restored afterwards (I28's contract unchanged).
"""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock

import pytest

from application.jobs.job_engine import JobEngine
from shared import debug_trace
from shared.logging_setup import (
    CONSOLE_FORMAT,
    install_correlation_stamping,
    uninstall_correlation_stamping,
)


class _Recorder(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def stamped():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    uninstall_correlation_stamping()
    install_correlation_stamping()
    recorder = _Recorder()
    root.handlers = [recorder]
    root.setLevel(logging.DEBUG)
    try:
        yield recorder
    finally:
        root.handlers = saved_handlers
        root.setLevel(saved_level)
        uninstall_correlation_stamping()


async def _run_worker_loops(engine: JobEngine, concurrency: int) -> list[str | None]:
    """Run the real loops briefly and return the trace id seen at each claim."""
    ids: list[str | None] = []

    def claim_recording(**_kwargs):
        ids.append(debug_trace.current_trace_id())
        return None

    engine._repo.claim_job.side_effect = claim_recording
    engine._claim_poll_interval = 0
    workers = [asyncio.create_task(engine._worker_loop(i)) for i in range(concurrency)]
    for _ in range(3):
        await asyncio.sleep(0)
    for worker in workers:
        worker.cancel()
    await asyncio.gather(*workers, return_exceptions=True)
    return ids


async def test_worker_loop_binds_a_per_index_trace_id(stamped):
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="engine7")
    ids = await _run_worker_loops(engine, concurrency=1)

    assert ids, "worker loop never claimed"
    assert all(value == "worker-0" for value in ids), ids


async def test_five_workers_get_five_distinct_trace_ids(stamped):
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="engine7")
    ids = await _run_worker_loops(engine, concurrency=5)

    observed = {value for value in ids if value is not None}
    assert observed == {f"worker-{i}" for i in range(5)}, (ids, observed)


async def test_pool_startup_line_carries_pool_trace_id(stamped):
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="engine7")

    async def no_loop(_index):
        return None

    engine._worker_loop = no_loop
    await engine.run_worker_pool(concurrency=5)

    startup = [r for r in stamped.records if "Starting with concurrency" in r.getMessage()]
    assert len(startup) == 1
    assert startup[0].correlation_id == "pool-engine7"


async def test_job_id_nests_then_restores_worker_id(stamped):
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="engine7")

    async def handler(_job):
        assert debug_trace.current_trace_id() == "job-X"
        return {}

    engine.register_handler("probe", handler)
    with debug_trace.bind_trace_id("worker-2", prefix="worker"):
        await engine.execute_job({"id": "X", "job_type": "probe", "lease_token": "t"})
        assert debug_trace.current_trace_id() == "worker-2"


def test_pool_correlation_id_renders_in_console_format(stamped):
    with debug_trace.bind_trace_id("pool-engine7", prefix="pool"):
        logging.getLogger("stockerpro.worker").info("[WORKER_POOL] probe")

    rendered = logging.Formatter(CONSOLE_FORMAT).format(stamped.records[-1])
    assert "[pool-engine7]" in rendered, rendered
    assert "[WORKER_POOL] probe" in rendered, rendered
