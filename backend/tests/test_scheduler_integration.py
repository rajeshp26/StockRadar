"""
Integration smoke test for the v3 scheduler control-plane tables.

Requires a real Supabase connection (SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY).

Run with:
    RUN_INTEGRATION_TESTS=1 python -m pytest tests/test_scheduler_integration.py -v

These tests create and clean up real rows in the database.
They are skipped by default to avoid accidental production writes.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run against real Supabase",
)


@pytest.fixture
def repo():
    from infrastructure.repositories.scheduler_repository import SchedulerRepository
    return SchedulerRepository()


def _cleanup_job(repo, dedupe_key: str):
    """Remove a job by dedupe_key after the test."""
    from database import supabase
    try:
        supabase.table("jobs").delete().eq("dedupe_key", dedupe_key).execute()
    except Exception:
        pass


class TestJobsIntegration:
    """Smoke tests that exercise enqueue/claim/complete against real DB."""

    def test_enqueue_and_verify_write(self, repo):
        """Enqueue a job and verify it was written correctly by reading it back."""
        dedupe = f"int-test-{uuid.uuid4().hex[:8]}"
        try:
            ok = repo.enqueue_job(
                job_type="company_refresh",
                dedupe_key=dedupe,
                payload={"company_id": 999999, "ticker_symbol": "INTTEST"},
                priority=99,
            )
            assert ok is True, "enqueue_job should return True"

            # Read it back via direct query
            from database import supabase
            result = supabase.table("jobs").select("*").eq("dedupe_key", dedupe).execute()
            assert len(result.data) == 1
            row = result.data[0]
            assert row["job_type"] == "company_refresh"
            assert row["payload"]["company_id"] == 999999
            assert row["status"] == "pending"
            assert row["priority"] == 99
        finally:
            _cleanup_job(repo, dedupe)

    def test_enqueue_then_claim_by_direct_id(self, repo):
        """Enqueue a job and then claim it by matching ID directly."""
        dedupe = f"int-test-claim-{uuid.uuid4().hex[:8]}"
        try:
            ok = repo.enqueue_job(job_type="test", dedupe_key=dedupe, payload={}, priority=99)
            assert ok is True

            # Find our job directly (don't rely on claim ordering with existing jobs)
            from database import supabase
            result = supabase.table("jobs").select("id").eq("dedupe_key", dedupe).execute()
            assert len(result.data) == 1
            job_id = result.data[0]["id"]

            import uuid as _uuid
            lease_token = str(_uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            leased_until = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()

            update_result = supabase.table("jobs").update({
                "status": "running",
                "lease_owner": "int-test-runner",
                "lease_token": lease_token,
                "leased_until": leased_until,
                "attempts": 1,
                "updated_at": now,
            }).eq("id", job_id).eq("status", "pending").execute()

            assert len(update_result.data) == 1
            assert update_result.data[0]["status"] == "running"

            complete_result = supabase.table("jobs").update({
                "status": "succeeded",
                "lease_owner": None,
                "lease_token": None,
                "leased_until": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", job_id).eq("lease_owner", "int-test-runner").eq("lease_token", lease_token).execute()

            assert len(complete_result.data) == 1
            stored = repo.get_job(job_id)
            assert stored["status"] == "succeeded"
        finally:
            _cleanup_job(repo, dedupe)

    def test_enqueue_dedup(self, repo):
        """Same dedupe_key should not create duplicate pending jobs."""
        dedupe = f"int-test-dedup-{uuid.uuid4().hex[:8]}"
        try:
            ok1 = repo.enqueue_job(job_type="test", dedupe_key=dedupe, payload={})
            ok2 = repo.enqueue_job(job_type="test", dedupe_key=dedupe, payload={})
            assert ok1 is True
            assert ok2 is False, "duplicate enqueue should return False"
        finally:
            _cleanup_job(repo, dedupe)

    def test_fail_manually(self, repo):
        """Manually test fail_job by creating and claiming a known job."""
        dedupe = f"int-test-fail-{uuid.uuid4().hex[:8]}"
        try:
            repo.enqueue_job(job_type="test", dedupe_key=dedupe, payload={})
            from database import supabase
            result = supabase.table("jobs").select("id").eq("dedupe_key", dedupe).execute()
            assert len(result.data) == 1
            job_id = result.data[0]["id"]

            import uuid as _uuid
            lease_token = str(_uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            supabase.table("jobs").update({
                "status": "running", "lease_owner": "int-test-runner",
                "lease_token": lease_token, "leased_until": now,
                "attempts": 1, "updated_at": now,
            }).eq("id", job_id).eq("status", "pending").execute()

            status = repo.fail_job(job_id, "int-test-runner", lease_token,
                                   "network timeout", backoff_minutes=1)
            assert status == "pending", "should be returned to pending"
            stored = repo.get_job(job_id)
            assert stored["status"] == "pending"
            assert stored["last_error"] == "network timeout"
        finally:
            _cleanup_job(repo, dedupe)


class TestSchedulerStateIntegration:
    """Smoke tests for scheduler_state CRUD."""

    def test_upsert_and_read(self, repo):
        name = f"int-test-sched-{uuid.uuid4().hex[:8]}"
        try:
            repo.upsert_scheduler_state({
                "scheduler_name": name,
                "interval_hours": 24,
                "enabled": True,
            })
            state = repo.get_scheduler_state(name)
            assert state is not None
            assert state["scheduler_name"] == name
            assert state["interval_hours"] == 24
            assert state["enabled"] is True

            # Upsert again with different values
            repo.upsert_scheduler_state({
                "scheduler_name": name,
                "interval_hours": 12,
                "enabled": False,
            })
            state = repo.get_scheduler_state(name)
            assert state["interval_hours"] == 12
            assert state["enabled"] is False
        finally:
            from database import supabase
            supabase.table("scheduler_state").delete().eq("scheduler_name", name).execute()

    def test_get_all_states(self, repo):
        states = repo.get_all_scheduler_states()
        assert isinstance(states, list)


class TestHeartbeatsIntegration:
    """Smoke tests for worker heartbeats."""

    def test_heartbeat_lifecycle(self, repo):
        wid = f"int-test-hb-{uuid.uuid4().hex[:8]}"
        try:
            repo.record_heartbeat(wid, hostname="test", pid=9999, active_jobs=3)
            repo.record_heartbeat(wid, hostname="test", pid=9999, active_jobs=5)
            alive = repo.get_worker_heartbeats(stale_threshold_minutes=10)
            ids = [w["worker_id"] for w in alive]
            assert wid in ids
        finally:
            from database import supabase
            supabase.table("worker_heartbeats").delete().eq("worker_id", wid).execute()


class TestResourceLocksIntegration:
    """Smoke tests for resource locks."""

    def test_acquire_release(self, repo):
        token = repo.acquire_resource_lock(
            resource_type="company",
            resource_id="999999",
            lock_type="market_data_refresh",
            owner_id="int-test",
            ttl_seconds=60,
        )
        assert token is not None, "acquire should return a lease token"

        # Second acquire on same resource should fail
        token2 = repo.acquire_resource_lock(
            resource_type="company",
            resource_id="999999",
            lock_type="market_data_refresh",
            owner_id="int-test-2",
            ttl_seconds=60,
        )
        assert token2 is None, "second acquire should fail"

        # Release
        ok = repo.release_resource_lock(
            resource_type="company",
            resource_id="999999",
            lock_type="market_data_refresh",
            owner_id="int-test",
            lease_token=token,
        )
        assert ok is True

        # Now should acquire again
        token3 = repo.acquire_resource_lock(
            resource_type="company",
            resource_id="999999",
            lock_type="market_data_refresh",
            owner_id="int-test-3",
            ttl_seconds=60,
        )
        assert token3 is not None, "should acquire after release"
        repo.release_resource_lock("company", "999999", "market_data_refresh",
                                   "int-test-3", token3)
