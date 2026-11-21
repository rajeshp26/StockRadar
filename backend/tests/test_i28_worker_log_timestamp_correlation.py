"""I28 -- worker log lines need a timestamp and a per-job correlation id.

The 2026-11-14 worker log was produced by ``scheduler_worker.py``, which called
``logging.basicConfig(format="%(name)s %(message)s")``. Unlike the API process
(``main.py``), it installed neither ``CONSOLE_FORMAT`` nor the correlation record
factory, so every line lacked a timestamp, a level and a trace id. With
``concurrency=5`` jobs interleave in one stderr stream and no line can be
attributed to the job that emitted it.

Contract pinned here:

* the worker configures the SAME timestamped format as the API and installs the
  correlation stamping (source assertion, matching the existing
  ``test_module_has_logging_basicConfig`` pattern);
* ``CONSOLE_FORMAT`` renders a timestamp and the active correlation id;
* ``JobEngine.execute_job`` binds a stable ``job-<job_id>`` trace id for the
  whole job, so concurrent jobs get distinct ids and every record emitted inside
  a handler (including nested service/repository records) carries its job's id.

RED today on the worker-format and per-job-binding assertions.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import re
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
    """Capture records with the correlation factory installed, then restore."""
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


def test_worker_uses_the_shared_timestamped_format():
    import scheduler_worker

    source = inspect.getsource(scheduler_worker)
    assert "CONSOLE_FORMAT" in source, "worker must use the API's timestamped format"
    assert "install_correlation_stamping()" in source, (
        "worker must stamp correlation_id or CONSOLE_FORMAT raises KeyError"
    )
    assert 'format="%(name)s %(message)s"' not in source, (
        "the untimestamped worker format is I28's root cause"
    )


def test_console_format_renders_timestamp_and_active_trace_id(stamped):
    child = logging.getLogger("stockerpro.worker.test")
    child.propagate = True
    child.setLevel(logging.INFO)

    with debug_trace.bind_trace_id("job-abc123", prefix="job"):
        child.info("marker")

    formatted = logging.Formatter(CONSOLE_FORMAT).format(stamped.records[-1])
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", formatted), formatted
    assert "[job-abc123]" in formatted, formatted
    assert "INFO" in formatted, formatted


async def test_each_concurrent_job_gets_its_own_correlation_id(stamped):
    """Five overlapping jobs must not share one trace id (the concurrency=5 case)."""
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="test-worker")
    observed: dict[str, tuple[str | None, str | None]] = {}

    async def handler(job):
        before = debug_trace.current_trace_id()
        await asyncio.sleep(0)  # yield so the other jobs interleave here
        after = debug_trace.current_trace_id()
        observed[job["id"]] = (before, after)
        return {}

    engine.register_handler("probe", handler)
    jobs = [
        {"id": str(i), "job_type": "probe", "lease_token": "tok"}
        for i in range(5)
    ]
    await asyncio.gather(*(engine.execute_job(job) for job in jobs))

    assert len(observed) == 5
    for job_id, (before, after) in observed.items():
        assert before == f"job-{job_id}", (job_id, before)
        assert after == f"job-{job_id}", (job_id, after)  # survived the await
    assert len({pair[0] for pair in observed.values()}) == 5


async def test_handler_records_carry_the_job_correlation_id(stamped):
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="test-worker")

    async def handler(job):
        logging.getLogger("stockerpro.worker.handler").info(
            "inside %s", job["id"]
        )
        return {}

    engine.register_handler("probe", handler)
    await engine.execute_job({"id": "XYZ", "job_type": "probe", "lease_token": "tok"})

    markers = [r for r in stamped.records if r.getMessage() == "inside XYZ"]
    assert len(markers) == 1
    assert markers[0].correlation_id == "job-XYZ"


async def test_trace_id_is_restored_after_job_completes(stamped):
    """A job must not leak its trace id into the worker loop's next claim."""
    engine = JobEngine(scheduler_repo=MagicMock(), worker_id="test-worker")

    async def handler(job):
        return {}

    engine.register_handler("probe", handler)
    token = debug_trace.trace_id_var.set("outer")
    try:
        await engine.execute_job(
            {"id": "ONE", "job_type": "probe", "lease_token": "tok"}
        )
        assert debug_trace.current_trace_id() == "outer"
    finally:
        debug_trace.trace_id_var.reset(token)
