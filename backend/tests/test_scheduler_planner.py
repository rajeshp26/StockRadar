import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.get_scheduler_state = MagicMock()
    repo.upsert_scheduler_state = MagicMock()
    repo.enqueue_job = MagicMock(return_value=True)
    repo.record_planner_run = MagicMock()
    repo.reclaim_expired_leases = MagicMock(return_value=0)
    repo.prune_old_records = MagicMock(return_value={})
    repo.get_stale_lock_count = MagicMock(return_value=0)
    return repo


class TestSchedulerPlannerRegister:
    @pytest.fixture
    def planner(self, mock_repo):
        from application.schedulers.planner import SchedulerPlanner
        return SchedulerPlanner(scheduler_repo=mock_repo)

    def test_register_adds_scheduler_in_memory(self, planner, mock_repo):
        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:1"}]

        planner.register("test_scheduler", plan_fn, interval_hours=12, enabled=True)
        assert "test_scheduler" in planner._schedulers
        cfg = planner._schedulers["test_scheduler"]
        assert cfg["name"] == "test_scheduler"
        assert cfg["interval_hours"] == 12
        assert cfg["enabled"] is True
        assert cfg["plan_fn"] is plan_fn

    def test_register_does_not_write_to_db(self, planner, mock_repo):
        async def plan_fn():
            return []

        planner.register("no_db_sched", plan_fn, interval_hours=6, enabled=True)
        mock_repo.upsert_scheduler_state.assert_not_called()

    def test_register_default_enabled(self, planner, mock_repo):
        async def plan_fn():
            return []

        planner.register("default_sched", plan_fn, interval_hours=24)
        assert planner._schedulers["default_sched"]["enabled"] is True

    def test_register_disabled(self, planner, mock_repo):
        async def plan_fn():
            return []

        planner.register("disabled_sched", plan_fn, interval_hours=24, enabled=False)
        assert planner._schedulers["disabled_sched"]["enabled"] is False

    def test_register_multiple_schedulers(self, planner, mock_repo):
        async def plan_fn():
            return []

        planner.register("sched_a", plan_fn, interval_hours=24, enabled=True)
        planner.register("sched_b", plan_fn, interval_hours=12, enabled=False)
        planner.register("sched_c", plan_fn, interval_hours=6, enabled=True)
        assert len(planner._schedulers) == 3
        mock_repo.upsert_scheduler_state.assert_not_called()

    def test_register_overwrites_existing(self, planner, mock_repo):
        async def plan_fn_a():
            return []

        async def plan_fn_b():
            return [{"job_type": "test", "dedupe_key": "test:1"}]

        planner.register("same_name", plan_fn_a, interval_hours=24, enabled=False)
        planner.register("same_name", plan_fn_b, interval_hours=12, enabled=True)
        cfg = planner._schedulers["same_name"]
        assert cfg["plan_fn"] is plan_fn_b
        assert cfg["interval_hours"] == 12
        assert cfg["enabled"] is True


class TestSchedulerPlannerCheckAndPlan:
    @pytest.fixture
    def planner(self, mock_repo):
        from application.schedulers.planner import SchedulerPlanner
        return SchedulerPlanner(scheduler_repo=mock_repo)

    async def test_due_scheduler_enqueues_jobs(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()

        async def plan_fn():
            return [
                {"job_type": "test", "dedupe_key": "test:1", "priority": 50},
                {"job_type": "test", "dedupe_key": "test:2", "priority": 50},
            ]

        mock_repo.get_scheduler_state.return_value = {
            "next_due_at": past,
            "enabled": True,
        }

        planner.register("test_sched", plan_fn, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        assert mock_repo.enqueue_job.call_count == 2
        mock_repo.upsert_scheduler_state.assert_called()
        state_update = mock_repo.upsert_scheduler_state.call_args[0][0]
        assert state_update["scheduler_name"] == "test_sched"
        assert state_update["last_status"] == "succeeded"
        mock_repo.record_planner_run.assert_called_once()

    async def test_not_due_skips(self, planner, mock_repo):
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:1"}]

        mock_repo.get_scheduler_state.return_value = {
            "next_due_at": future,
        }

        planner.register("test_sched", plan_fn, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        mock_repo.enqueue_job.assert_not_called()
        mock_repo.upsert_scheduler_state.assert_not_called()
        mock_repo.record_planner_run.assert_not_called()

    async def test_disabled_skips(self, planner, mock_repo):
        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:1"}]

        planner.register("disabled_sched", plan_fn, interval_hours=12, enabled=False)
        await planner._check_and_plan()
        mock_repo.enqueue_job.assert_not_called()
        mock_repo.get_scheduler_state.assert_not_called()

    async def test_no_state_runs_immediately_and_writes_state(self, planner, mock_repo):
        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:first_run"}]

        mock_repo.get_scheduler_state.return_value = None
        planner.register("new_sched", plan_fn, interval_hours=6, enabled=True)

        assert not mock_repo.upsert_scheduler_state.called

        await planner._check_and_plan()

        mock_repo.enqueue_job.assert_called_once()
        mock_repo.upsert_scheduler_state.assert_called()
        state_update = mock_repo.upsert_scheduler_state.call_args[0][0]
        assert state_update["scheduler_name"] == "new_sched"
        assert state_update["last_status"] == "succeeded"
        assert "next_due_at" in state_update
        mock_repo.record_planner_run.assert_called_once()

    async def test_no_next_due_at_runs_immediately(self, planner, mock_repo):
        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:no_next"}]

        mock_repo.get_scheduler_state.return_value = {
            "scheduler_name": "partial_sched",
            "enabled": True,
        }
        planner.register("partial_sched", plan_fn, interval_hours=6, enabled=True)
        await planner._check_and_plan()
        mock_repo.enqueue_job.assert_called_once()

    async def test_failure_records_error_and_retries(self, planner, mock_repo):
        mock_repo.get_scheduler_state.return_value = {
            "next_due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }

        async def failing_plan():
            raise ValueError("provider unavailable")

        planner.register("failing_sched", failing_plan, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        mock_repo.update_scheduler_state.assert_called_with(
            "failing_sched",
            {"last_status": "failed", "last_error": "provider unavailable"},
        )
        mock_repo.record_planner_run.assert_called_once_with(
            scheduler_name="failing_sched", jobs_enqueued=0,
            status="failed", error="provider unavailable"
        )

    async def test_missed_intervals_no_catchup(self, planner, mock_repo):
        old_next = (datetime.now(UTC) - timedelta(hours=48)).isoformat()

        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:1"}]

        mock_repo.get_scheduler_state.return_value = {
            "next_due_at": old_next,
            "enabled": True,
        }

        planner.register("missed_sched", plan_fn, interval_hours=6, enabled=True)
        await planner._check_and_plan()

        state_update = mock_repo.upsert_scheduler_state.call_args[0][0]
        next_due = datetime.fromisoformat(state_update["next_due_at"])
        expected = datetime.now(UTC) + timedelta(hours=6)
        assert abs((next_due - expected).total_seconds()) < 10

    async def test_invalid_timestamp_treated_as_due(self, planner, mock_repo):
        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:bad_ts"}]

        mock_repo.get_scheduler_state.return_value = {
            "next_due_at": "not-a-timestamp",
            "enabled": True,
        }

        planner.register("bad_ts_sched", plan_fn, interval_hours=24, enabled=True)
        await planner._check_and_plan()

        mock_repo.enqueue_job.assert_called_once()
        mock_repo.upsert_scheduler_state.assert_called()

    async def test_multiple_schedulers_all_due(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        async def plan_fn_a():
            return [{"job_type": "test", "dedupe_key": "test:a"}]

        async def plan_fn_b():
            return [{"job_type": "test", "dedupe_key": "test:b"}]

        mock_repo.get_scheduler_state.return_value = {"next_due_at": past}

        planner.register("sched_a", plan_fn_a, interval_hours=24, enabled=True)
        planner.register("sched_b", plan_fn_b, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        assert mock_repo.enqueue_job.call_count == 2
        assert mock_repo.record_planner_run.call_count == 2

    async def test_second_scheduler_not_due_first_runs(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()

        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:due"}]

        def get_state_side_effect(name):
            if name == "due_sched":
                return {"next_due_at": past}
            return {"next_due_at": future}

        mock_repo.get_scheduler_state.side_effect = get_state_side_effect

        planner.register("due_sched", plan_fn, interval_hours=6, enabled=True)
        planner.register("not_due_sched", plan_fn, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        assert mock_repo.enqueue_job.call_count == 1
        assert mock_repo.record_planner_run.call_count == 1

    async def test_enqueue_failure_does_not_block_other_jobs(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        async def plan_fn():
            return [
                {"job_type": "test", "dedupe_key": "test:first"},
                {"job_type": "test", "dedupe_key": "test:second"},
            ]

        mock_repo.get_scheduler_state.return_value = {"next_due_at": past}
        mock_repo.enqueue_job.side_effect = [True, False]

        planner.register("partial_sched", plan_fn, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        assert mock_repo.enqueue_job.call_count == 2
        mock_repo.upsert_scheduler_state.assert_called()
        state_update = mock_repo.upsert_scheduler_state.call_args[0][0]
        assert state_update["last_status"] == "succeeded"

    async def test_state_upsert_failure_after_plan_still_records_run(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        async def plan_fn():
            return [{"job_type": "test", "dedupe_key": "test:state_fail"}]

        mock_repo.get_scheduler_state.return_value = {"next_due_at": past}
        mock_repo.upsert_scheduler_state.side_effect = Exception("db error")

        planner.register("state_fail_sched", plan_fn, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        mock_repo.record_planner_run.assert_called_once()
        mock_repo.upsert_scheduler_state.assert_called_once()
        mock_repo.update_scheduler_state.assert_called_once()

    async def test_multiple_schedulers_one_fails_other_runs(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        async def good_plan():
            return [{"job_type": "test", "dedupe_key": "test:good"}]

        async def bad_plan():
            raise RuntimeError("planning failed")

        mock_repo.get_scheduler_state.return_value = {"next_due_at": past}

        planner.register("good_sched", good_plan, interval_hours=6, enabled=True)
        planner.register("bad_sched", bad_plan, interval_hours=12, enabled=True)
        await planner._check_and_plan()

        assert mock_repo.enqueue_job.call_count == 1
        assert mock_repo.record_planner_run.call_count == 2

    async def test_empty_plan_does_not_enqueue(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        async def plan_fn():
            return []

        mock_repo.get_scheduler_state.return_value = {"next_due_at": past}
        planner.register("empty_sched", plan_fn, interval_hours=24, enabled=True)
        await planner._check_and_plan()

        mock_repo.enqueue_job.assert_not_called()
        mock_repo.upsert_scheduler_state.assert_called()
        mock_repo.record_planner_run.assert_called_once()

    async def test_plan_returns_none_handled_gracefully(self, planner, mock_repo):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

        async def plan_fn():
            return None

        mock_repo.get_scheduler_state.return_value = {"next_due_at": past}
        planner.register("none_sched", plan_fn, interval_hours=24, enabled=True)
        await planner._check_and_plan()

        mock_repo.enqueue_job.assert_not_called()


class TestPlannerLoopLifecycle:
    @pytest.fixture
    def planner(self, mock_repo):
        from application.schedulers.planner import SchedulerPlanner
        return SchedulerPlanner(scheduler_repo=mock_repo)

    async def test_run_planner_loop_completes_cleanly_on_cancel(self, planner, mock_repo):
        async def plan_fn():
            return []

        mock_repo.get_scheduler_state.return_value = None
        planner.register("test", plan_fn, interval_hours=24, enabled=True)

        loop_task = asyncio.create_task(planner.run_planner_loop())
        await asyncio.sleep(0.05)
        loop_task.cancel()
        try:
            await asyncio.wait_for(loop_task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

        assert loop_task.done()

    async def test_run_planner_loop_continues_on_plan_failure(self, planner, mock_repo):
        call_count = [0]

        async def plan_fn():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("transient error")
            return [{"job_type": "test", "dedupe_key": f"test:{call_count[0]}"}]

        planner._planner_interval = 0.01
        planner.register("erratic_sched", plan_fn, interval_hours=0, enabled=True)
        mock_repo.get_scheduler_state.side_effect = [
            None,
            {"next_due_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat()},
        ]

        loop_task = asyncio.create_task(planner.run_planner_loop())
        await asyncio.sleep(0.15)
        loop_task.cancel()
        try:
            await asyncio.wait_for(loop_task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

        assert call_count[0] >= 2

    async def test_run_janitor_loop_completes_cleanly_on_cancel(self, planner, mock_repo):
        loop_task = asyncio.create_task(planner.run_janitor_loop())
        await asyncio.sleep(0.05)
        loop_task.cancel()
        try:
            await asyncio.wait_for(loop_task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

        assert loop_task.done()

    async def test_run_janitor_loop_does_not_run_cycle_before_first_sleep(self, planner, mock_repo):
        """Janitor loop sleeps 300s before first cycle; cancel during sleep is clean."""
        loop_task = asyncio.create_task(planner.run_janitor_loop())
        await asyncio.sleep(0.05)
        loop_task.cancel()
        try:
            await asyncio.wait_for(loop_task, timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass

        assert loop_task.done()
        mock_repo.reclaim_expired_leases.assert_not_called()


class TestJanitor:
    @pytest.fixture
    def planner(self, mock_repo):
        from application.schedulers.planner import SchedulerPlanner
        return SchedulerPlanner(scheduler_repo=mock_repo)

    async def test_janitor_reclaims_leases(self, planner, mock_repo):
        mock_repo.reclaim_expired_leases.return_value = 3
        mock_repo.prune_zombie_heartbeats.return_value = 0
        mock_repo.release_expired_scheduler_locks.return_value = 0
        await planner._janitor_cycle()
        mock_repo.reclaim_expired_leases.assert_called_once()

    async def test_janitor_reclaims_logs_on_reclaim(self, planner, mock_repo, caplog):
        caplog.set_level("INFO")
        mock_repo.reclaim_expired_leases.return_value = 5
        mock_repo.prune_zombie_heartbeats.return_value = 0
        mock_repo.release_expired_scheduler_locks.return_value = 0
        await planner._janitor_cycle()
        assert "Reclaimed 5 expired job leases" in caplog.text

    async def test_janitor_prunes_records(self, planner, mock_repo):
        mock_repo.prune_old_records.return_value = {"jobs": 5, "attempts": 10}
        mock_repo.prune_zombie_heartbeats.return_value = 0
        mock_repo.release_expired_scheduler_locks.return_value = 0
        await planner._janitor_cycle()
        mock_repo.prune_old_records.assert_called_once()

    async def test_janitor_detects_stale_locks(self, planner, mock_repo):
        mock_repo.release_expired_scheduler_locks.return_value = 2
        mock_repo.prune_zombie_heartbeats.return_value = 0
        await planner._janitor_cycle()
        mock_repo.release_expired_scheduler_locks.assert_called_once()

    async def test_janitor_logs_stale_locks_warning(self, planner, mock_repo, caplog):
        caplog.set_level("INFO")
        mock_repo.release_expired_scheduler_locks.return_value = 3
        mock_repo.prune_zombie_heartbeats.return_value = 0
        await planner._janitor_cycle()
        assert "Released 3 expired scheduler locks" in caplog.text

    async def test_janitor_handles_exceptions_gracefully(self, planner, mock_repo):
        mock_repo.reclaim_expired_leases.side_effect = Exception("db error")
        mock_repo.prune_zombie_heartbeats.return_value = 0
        mock_repo.release_expired_scheduler_locks.return_value = 0
        await planner._janitor_cycle()

    async def test_janitor_handles_all_three_operations(self, planner, mock_repo):
        mock_repo.reclaim_expired_leases.return_value = 2
        mock_repo.prune_old_records.return_value = {"jobs_succeeded": 3}
        mock_repo.release_expired_scheduler_locks.return_value = 1
        mock_repo.prune_zombie_heartbeats.return_value = 0

        await planner._janitor_cycle()

        mock_repo.reclaim_expired_leases.assert_called_once()
        mock_repo.prune_old_records.assert_called_once()
        mock_repo.release_expired_scheduler_locks.assert_called_once()

    async def test_janitor_prune_failure_logs_and_continues(self, planner, mock_repo, caplog):
        caplog.set_level("ERROR")
        mock_repo.reclaim_expired_leases.return_value = 0
        mock_repo.prune_old_records.side_effect = Exception("prune error")
        mock_repo.release_expired_scheduler_locks.return_value = 0
        mock_repo.prune_zombie_heartbeats.return_value = 0

        await planner._janitor_cycle()

        assert "Cycle failed: prune error" in caplog.text
