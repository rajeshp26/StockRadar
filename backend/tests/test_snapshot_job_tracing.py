"""Tests for the snapshot job's trace-id lifecycle.

The worker that owns the seam-drop defect runs in a separate process with no
incoming HTTP request, so ``CorrelationIdMiddleware`` never fires for it. Before
this change every repository call made by the job was uncorrelatable with every
other: two runs that produced different snapshots left logs that could not be
told apart.

These tests assert the property the job depends on -- an id exists for the whole
duration of the run, and it does not leak into whatever ran next.
"""

import pytest

from application.jobs import portfolio_snapshot_job as job_mod
from shared import debug_trace


@pytest.fixture(autouse=True)
def _clean_trace_state():
    """Never let a leaked id from one test reach the next."""
    debug_trace.clear_trace_id()
    yield
    debug_trace.clear_trace_id()


@pytest.fixture
def probe(monkeypatch):
    """Replace the job body, recording the trace id visible from inside it."""
    seen: list[str | None] = []

    async def _fake_compute(target_date=None):
        seen.append(debug_trace.current_trace_id())
        return 0

    monkeypatch.setattr(job_mod, "compute_daily_snapshots", _fake_compute)
    return seen


class TestJobTraceIdLifecycle:
    @pytest.mark.asyncio
    async def test_job_has_a_trace_id_while_running(self, probe):
        """The core guarantee: the job body can always read an ambient id."""
        await job_mod.handle_portfolio_snapshot({})

        assert len(probe) == 1
        assert probe[0] is not None, "job ran with no trace id"
        assert probe[0].startswith("snapshot-")

    @pytest.mark.asyncio
    async def test_trace_id_does_not_leak_afterwards(self, probe):
        """A leaked id would mislabel the next unrelated record."""
        await job_mod.handle_portfolio_snapshot({})

        assert debug_trace.current_trace_id() is None

    @pytest.mark.asyncio
    async def test_outer_trace_id_is_restored_not_clobbered(self, probe):
        """A job invoked under an existing trace keeps the outer id afterwards."""
        debug_trace.set_trace_id("outer-123")

        await job_mod.handle_portfolio_snapshot({})

        assert debug_trace.current_trace_id() == "outer-123"
        # The job's own id still differs, so nested runs stay distinguishable.
        assert probe[0] != "outer-123"

    @pytest.mark.asyncio
    async def test_each_run_gets_a_distinct_id(self, probe):
        """Two runs producing different snapshots must not share an id.

        If they did, every log line from both runs would interleave under one
        id and the defect would be undiagnosable again -- which is the situation
        this whole change exists to close.
        """
        await job_mod.handle_portfolio_snapshot({})
        await job_mod.handle_portfolio_snapshot({})

        assert len(probe) == 2
        assert probe[0] != probe[1]

    @pytest.mark.asyncio
    async def test_handler_returns_completed_status(self, probe):
        """The instrumentation must not change the job's contract.

        The JobEngine inspects this return value, so a signature or shape change
        here would break scheduling, not just logging.
        """
        result = await job_mod.handle_portfolio_snapshot({})

        assert result["status"] == "completed"

    @pytest.mark.asyncio
    async def test_id_is_released_even_when_the_job_raises(self, monkeypatch):
        """A crashed run must not pin its id for the rest of the process.

        The worker is long-lived and reuses the same context across jobs, so a
        leaked id would permanently mislabel everything that follows.
        """
        seen: list[str | None] = []

        async def _boom(target_date=None):
            seen.append(debug_trace.current_trace_id())
            raise RuntimeError("job failed")

        monkeypatch.setattr(job_mod, "compute_daily_snapshots", _boom)

        with pytest.raises(RuntimeError):
            await job_mod.handle_portfolio_snapshot({})

        assert seen and seen[0].startswith("snapshot-")
        assert debug_trace.current_trace_id() is None
