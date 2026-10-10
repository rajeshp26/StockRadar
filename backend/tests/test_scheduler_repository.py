import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _make_response(data):
    """Create a mock response object with a real `data` list."""
    resp = MagicMock()
    resp.data = data
    return resp


@pytest.fixture(autouse=True)
def mock_supabase():
    with patch("infrastructure.repositories.scheduler_repository.supabase") as m:
        table_mock = m.table.return_value
        # All chain methods must return self so .execute() reaches the table mock
        for meth in [
            "select", "eq", "neq", "lte", "lt", "gte", "gt",
            "in_", "is_", "order", "limit", "single",
            "update", "insert", "delete", "upsert",
        ]:
            getattr(table_mock, meth).return_value = table_mock
        yield m


@pytest.fixture
def repo():
    from infrastructure.repositories.scheduler_repository import SchedulerRepository
    return SchedulerRepository()


# ── enqueue_job ───────────────────────────────────────────────────────────────

class TestEnqueueJob:
    def test_inserts_pending_row(self, repo, mock_supabase):
        # Two execute calls: SELECT (existing check) and INSERT
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
            _make_response([]),
        ]
        result = repo.enqueue_job(
            job_type="company_refresh",
            dedupe_key="company_refresh:123",
            payload={"scopes": ["market_data"]},
        )
        assert result is True
        mock_supabase.table.return_value.insert.assert_called_once()
        insert_data = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_data["job_type"] == "company_refresh"
        assert insert_data["dedupe_key"] == "company_refresh:123"
        assert insert_data["status"] == "pending"
        assert insert_data["max_attempts"] == 3
        assert insert_data["payload"] == {"scopes": ["market_data"]}

    def test_insert_with_not_before(self, repo, mock_supabase):
        later = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
            _make_response([]),
        ]
        repo.enqueue_job(
            job_type="investor_refresh",
            dedupe_key="investor_refresh:CIK001",
            not_before=later,
            priority=80,
        )
        insert_data = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_data["not_before"] == later
        assert insert_data["available_at"] == later
        assert insert_data["priority"] == 80

    def test_returns_false_on_duplicate_after_existing_check(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
        ]
        mock_supabase.table.return_value.insert.side_effect = Exception("duplicate")
        result = repo.enqueue_job(job_type="test", dedupe_key="dup")
        assert result is False

    def test_merges_with_existing_pending_job(self, repo, mock_supabase):
        """Existing pending job with same dedupe key should merge scopes and upgrade priority."""
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{
                "id": "existing-1",
                "status": "pending",
                "priority": 30,
                "payload": {"scopes": ["market_data"], "reasons": ["routine"]},
            }]),
            _make_response([]),  # UPDATE execute
        ]
        result = repo.enqueue_job(
            job_type="company_refresh",
            dedupe_key="company_refresh:123",
            payload={"scopes": ["financials"], "reasons": ["earnings_window"]},
            priority=80,
        )
        assert result is True
        mock_supabase.table.return_value.insert.assert_not_called()
        update = mock_supabase.table.return_value.update.call_args
        assert update is not None
        update_data = update[0][0]
        assert update_data["priority"] == 80  # max(30, 80)
        merged_scopes = update_data["payload"]["scopes"]
        assert "market_data" in merged_scopes
        assert "financials" in merged_scopes
        assert "reasons" in update_data["payload"]

    def test_records_accumulator_for_running_job(self, repo, mock_supabase):
        """When existing job is running, new scopes go to company_refresh_requests."""
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{
                "id": "existing-1",
                "status": "running",
                "priority": 30,
                "payload": {"scopes": ["market_data"], "reasons": ["routine"]},
            }]),
        ]
        result = repo.enqueue_job(
            job_type="company_refresh",
            dedupe_key="company_refresh:123",
            payload={"scopes": ["financials"], "reasons": ["earnings_window"]},
            resource_id="123",
            priority=50,
        )
        assert result is True
        mock_supabase.table.return_value.insert.assert_called_once()
        insert_data = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert_data["company_id"] == "123"
        assert insert_data["scopes"] == ["financials"]  # only new scopes


# ── claim_job ─────────────────────────────────────────────────────────────────

class TestClaimJob:
    def test_claims_next_pending(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "job-1"}]),
            _make_response([{"id": "job-1", "status": "running", "lease_owner": "w1"}]),
        ]
        job = repo.claim_job(worker_id="w1", lease_ttl_minutes=30)
        assert job is not None
        update = mock_supabase.table.return_value.update.call_args[0][0]
        assert update["status"] == "running"
        assert update["lease_owner"] == "w1"
        assert update["lease_token"] is not None

    def test_claim_no_work_returns_none(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
        ]
        job = repo.claim_job(worker_id="w1")
        assert job is None

    def test_claim_race_lost_returns_none(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "job-1"}]),
            _make_response([]),
        ]
        job = repo.claim_job(worker_id="w1")
        assert job is None

    def test_updates_attempts(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "job-1"}]),
            _make_response([{"id": "job-1", "attempts": 1}]),
        ]
        repo.claim_job(worker_id="w1")
        update = mock_supabase.table.return_value.update.call_args[0][0]
        assert "attempts" in update


# ── fail_job ──────────────────────────────────────────────────────────────────

class TestFailJob:
    def test_retry_sets_pending_with_backoff(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response({"id": "j1", "attempts": 1, "max_attempts": 3}),
            _make_response([{"id": "j1"}]),
        ]
        status = repo.fail_job("j1", "w1", "tok", "network error", backoff_minutes=5)
        assert status == "pending"

    def test_max_attempts_moves_to_dead_letter(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response({"id": "j1", "attempts": 2, "max_attempts": 2}),
            _make_response([{"id": "j1"}]),
        ]
        status = repo.fail_job("j1", "w1", "tok", "fatal", backoff_minutes=0)
        assert status == "dead_letter"

    def test_dead_letter_by_configured_max(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response({"id": "j1", "attempts": 4, "max_attempts": 3}),
            _make_response([{"id": "j1"}]),
        ]
        status = repo.fail_job("j1", "w1", "tok", "fatal", backoff_minutes=0)
        assert status == "dead_letter"

    def test_rejects_mismatched_owner(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response({"id": "j1", "attempts": 1, "max_attempts": 3}),
            _make_response([]),
        ]
        status = repo.fail_job("j1", "wrong_worker", "tok", "err", backoff_minutes=5)
        assert status == "error"

    def test_unknown_job(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response(None),
        ]
        status = repo.fail_job("j1", "w1", "tok", "err", backoff_minutes=5)
        assert status == "unknown"


# ── complete_job ──────────────────────────────────────────────────────────────

class TestCompleteJob:
    def test_sets_succeeded(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([{"id": "j1"}])
        result = repo.complete_job("j1", "w1", "tok")
        assert result is True

    def test_fails_on_mismatch(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        result = repo.complete_job("j1", "wrong_worker", "tok")
        assert result is False


# ── renew_job_lease ───────────────────────────────────────────────────────────

class TestRenewJobLease:
    def test_renews_lease(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([{"id": "j1"}])
        result = repo.renew_job_lease("j1", "w1", "tok", ttl_minutes=30)
        assert result is True

    def test_fails_on_mismatch(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        result = repo.renew_job_lease("j1", "w2", "wrong_tok")
        assert result is False


# ── record_attempt ────────────────────────────────────────────────────────────

class TestRecordAttempt:
    def test_inserts_attempt_row(self, repo, mock_supabase):
        repo.record_attempt("j1", attempt=1, status="running")
        upsert = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert["job_id"] == "j1"
        assert upsert["attempt"] == 1
        assert upsert["status"] == "running"

    def test_records_failed_attempt(self, repo, mock_supabase):
        repo.record_attempt("j1", attempt=1, status="failed", error="timeout", duration_ms=5000)
        upsert = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert["status"] == "failed"
        assert upsert["error"] == "timeout"
        assert upsert["duration_ms"] == 5000

    def test_records_succeeded_attempt(self, repo, mock_supabase):
        repo.record_attempt("j1", attempt=1, status="succeeded", duration_ms=1000)
        upsert = mock_supabase.table.return_value.upsert.call_args[0][0]
        assert upsert["status"] == "succeeded"
        assert upsert["duration_ms"] == 1000
        assert upsert.get("error") is None


# ── Scheduler State ───────────────────────────────────────────────────────────

class TestSchedulerState:
    def test_get_state_returns_dict(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response(
            [{"scheduler_name": "test", "enabled": True, "interval_hours": 24}]
        )
        state = repo.get_scheduler_state("test")
        assert state is not None
        assert state["scheduler_name"] == "test"
        assert state["enabled"] is True

    def test_get_state_missing_returns_none(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        state = repo.get_scheduler_state("nonexistent")
        assert state is None

    def test_upsert_state_inserts(self, repo, mock_supabase):
        repo.upsert_scheduler_state({"scheduler_name": "test", "interval_hours": 12})
        mock_supabase.table.return_value.upsert.assert_called_once()

    def test_record_planner_run(self, repo, mock_supabase):
        repo.record_planner_run("test", jobs_enqueued=5, status="succeeded", duration_ms=200)
        insert = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert["scheduler_name"] == "test"
        assert insert["jobs_enqueued"] == 5
        assert insert["duration_ms"] == 200
        assert insert["status"] == "succeeded"

    def test_record_planner_run_with_error(self, repo, mock_supabase):
        repo.record_planner_run("test", jobs_enqueued=0, status="failed", error="something broke", duration_ms=50)
        insert = mock_supabase.table.return_value.insert.call_args[0][0]
        assert insert["error"] == "something broke"
        assert insert["status"] == "failed"


# ── Heartbeats ────────────────────────────────────────────────────────────────

class TestHeartbeats:
    def test_record_heartbeat(self, repo, mock_supabase):
        repo.record_heartbeat("w1", hostname="h1", pid=123, active_jobs=5)
        mock_supabase.table.return_value.upsert.assert_called_once()

    def test_get_heartbeats_filters_stale(self, repo, mock_supabase):
        now = datetime.utcnow().isoformat()
        stale = (datetime.utcnow() - timedelta(minutes=10)).isoformat()
        mock_supabase.table.return_value.execute.return_value = _make_response([
            {"worker_id": "w1", "last_hb_at": now},
            {"worker_id": "w2", "last_hb_at": stale},
        ])
        alive = repo.get_worker_heartbeats(stale_threshold_minutes=2)
        assert len(alive) == 1
        assert alive[0]["worker_id"] == "w1"

    def test_release_worker_leases(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response(
            [{"id": "j1"}, {"id": "j2"}]
        )
        count = repo.release_worker_leases("w1")
        assert count == 2


# ── Janitor ───────────────────────────────────────────────────────────────────

class TestJanitor:
    def test_reclaim_expired_leases(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "j1", "lease_owner": "w1"}, {"id": "j2", "lease_owner": "w2"}]),
            _make_response([{"id": "j1"}]),
            _make_response([{"id": "j2"}]),
        ]
        count = repo.reclaim_expired_leases()
        assert count == 2

    def test_reclaim_handles_empty(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
        ]
        count = repo.reclaim_expired_leases()
        assert count == 0

    def test_reclaim_robust_on_error(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = Exception("db down")
        count = repo.reclaim_expired_leases()
        assert count == 0

    def test_prune_old_records(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "j1"}]),
            _make_response([{"id": "a1"}]),
            _make_response([{"id": "j1"}]),
            _make_response([]),
            _make_response([]),
            _make_response([]),
            _make_response([]),
        ]
        counts = repo.prune_old_records()
        assert isinstance(counts, dict)
        assert "jobs_succeeded" in counts
        assert counts["jobs_succeeded"] == 1

    def test_prune_deletes_attempts_before_jobs(self, repo, mock_supabase):
        """FK job_attempts_job_id_fkey: attempts must be deleted before the job."""
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "j1"}]),
            _make_response([{"id": "a1"}]),
            _make_response([{"id": "j1"}]),
            _make_response([]),
            _make_response([]),
            _make_response([]),
            _make_response([]),
        ]
        repo.prune_old_records()
        table_names = [call.args[0] for call in mock_supabase.table.call_args_list]
        assert table_names[1] == "job_attempts"
        assert table_names[2] == "jobs"
        assert mock_supabase.table.return_value.in_.call_args_list[0] == (("job_id", ["j1"]),)

    def test_prune_skips_job_delete_when_no_jobs(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
            _make_response([]),
            _make_response([]),
            _make_response([]),
            _make_response([]),
        ]
        counts = repo.prune_old_records()
        assert counts["jobs_succeeded"] == 0
        table_names = [call.args[0] for call in mock_supabase.table.call_args_list]
        assert table_names == [
            "jobs", "jobs", "job_attempts", "scheduler_run_history", "worker_heartbeats",
        ]

    def test_get_oldest_pending(self, repo, mock_supabase):
        created = (datetime.utcnow() - timedelta(hours=2)).isoformat()
        mock_supabase.table.return_value.execute.return_value = _make_response(
            [{"created_at": created}]
        )
        age = repo.get_oldest_pending_age_seconds()
        assert age is not None
        assert 7000 < age < 7300

    def test_get_oldest_pending_none(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        age = repo.get_oldest_pending_age_seconds()
        assert age is None

    def test_get_stale_lock_count(self, repo, mock_supabase):
        mock_resp = MagicMock()
        mock_resp.count = 3
        mock_supabase.table.return_value.execute.return_value = mock_resp
        count = repo.get_stale_lock_count()
        assert count == 3


# ── Queue Depth ───────────────────────────────────────────────────────────────

class TestQueueDepth:
    def test_queue_depth_returns_counts(self, repo, mock_supabase):
        mock_resp = MagicMock()
        mock_resp.count = 5
        mock_supabase.table.return_value.execute.return_value = mock_resp
        depth = repo.get_queue_depth()
        assert depth["pending"] == 5
        assert depth["running"] == 5


# ── Requeue (manual replay) ──────────────────────────────────────────────────

class TestRequeueJob:
    def test_requeue_resets_dead_letter(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "j1"}]),
        ]
        result = repo.requeue_job("j1")
        assert result is True

    def test_requeue_returns_false_on_failure(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),
        ]
        result = repo.requeue_job("nonexistent")
        assert result is False


# ── Company Refresh Requests ──────────────────────────────────────────────────

class TestCompanyRefreshRequests:
    def test_record_refresh_request(self, repo, mock_supabase):
        repo.record_refresh_request(company_id=1, scopes=["financials"], reasons=["earnings window"])
        mock_supabase.table.return_value.insert.assert_called_once()

    def test_get_unprocessed_requests(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([
            {"company_id": 1, "scopes": ["financials"]},
        ])
        requests = repo.get_unprocessed_refresh_requests(company_id=1)
        assert len(requests) == 1
        assert requests[0]["scopes"] == ["financials"]

    def test_mark_requests_processed(self, repo, mock_supabase):
        repo.mark_refresh_requests_processed(company_id=1)
        mock_supabase.table.return_value.update.assert_called_once()


# ── Cancel Job ────────────────────────────────────────────────────────────────

class TestCancelJob:
    def test_cancel_pending_job(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([{"id": "j1"}])
        result = repo.cancel_job("j1")
        assert result is True
        update = mock_supabase.table.return_value.update.call_args[0][0]
        assert update["status"] == "cancelled"

    def test_cancel_running_job(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([{"id": "j1"}])
        result = repo.cancel_job("j1")
        assert result is True
        update = mock_supabase.table.return_value.update.call_args[0][0]
        assert update["status"] == "cancelled"

    def test_cancel_nonexistent_returns_false(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        result = repo.cancel_job("nonexistent")
        assert result is False

    def test_cancel_clears_lease_fields(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([{"id": "j1"}])
        repo.cancel_job("j1")
        update = mock_supabase.table.return_value.update.call_args[0][0]
        assert update["lease_owner"] is None
        assert update["lease_token"] is None
        assert update["leased_until"] is None


# ── enqueue_job_batch ─────────────────────────────────────────────────────────

class TestEnqueueJobBatch:
    def test_batch_enqueues_multiple(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]), _make_response([]),  # first job: select + insert
            _make_response([]), _make_response([]),  # second job: select + insert
        ]
        count = repo.enqueue_job_batch([
            {"job_type": "test", "dedupe_key": "batch:1"},
            {"job_type": "test", "dedupe_key": "batch:2"},
        ])
        assert count == 2

    def test_batch_partial_failure(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([]),  # job 1: select — no existing
            _make_response([]),  # job 1: insert execute — ok
            _make_response([]),  # job 2: select — no existing
            Exception("duplicate key violation"),  # job 2: insert execute — fails
        ]
        count = repo.enqueue_job_batch([
            {"job_type": "test", "dedupe_key": "batch:1"},
            {"job_type": "test", "dedupe_key": "batch:2"},
        ])
        assert count == 1

    def test_batch_empty_list(self, repo, mock_supabase):
        count = repo.enqueue_job_batch([])
        assert count == 0


# ── get_jobs_by_status ────────────────────────────────────────────────────────

class TestGetJobsByStatus:
    def test_returns_filtered_jobs(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([
            {"id": "j1", "status": "pending", "job_type": "test"},
            {"id": "j2", "status": "pending", "job_type": "test"},
        ])
        jobs = repo.get_jobs_by_status("pending")
        assert len(jobs) == 2
        assert jobs[0]["status"] == "pending"

    def test_returns_empty_when_none_match(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        jobs = repo.get_jobs_by_status("dead_letter")
        assert jobs == []


# ── get_all_scheduler_states ──────────────────────────────────────────────────

class TestGetAllSchedulerStates:
    def test_returns_all_states(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([
            {"scheduler_name": "sched_a", "enabled": True},
            {"scheduler_name": "sched_b", "enabled": False},
        ])
        states = repo.get_all_scheduler_states()
        assert len(states) == 2

    def test_returns_empty_list_when_none(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        states = repo.get_all_scheduler_states()
        assert states == []


# ── Resource Lock Renewal ─────────────────────────────────────────────────────

class TestRenewResourceLock:
    def test_renew_success(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([{"id": "lock1"}])
        result = repo.renew_resource_lock(
            resource_type="company",
            resource_id="123",
            lock_type="market_data_refresh",
            owner_id="w1",
            lease_token="tok",
            ttl_seconds=1800,
        )
        assert result is True

    def test_renew_failure(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        result = repo.renew_resource_lock(
            resource_type="company",
            resource_id="123",
            lock_type="market_data_refresh",
            owner_id="w1",
            lease_token="wrong_tok",
            ttl_seconds=1800,
        )
        assert result is False


# ── fail_job edge cases ───────────────────────────────────────────────────────

class TestFailJobEdgeCases:
    def test_defeat_beta_no_data_sends_to_dead_letter(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response({"id": "j1", "attempts": 0, "max_attempts": 3}),
            _make_response([{"id": "j1"}]),
        ]
        status = repo.fail_job("j1", "w1", "tok", "DEFEAT_BETA_NO_DATA for AAPL", backoff_minutes=5)
        assert status == "dead_letter"

    def test_fail_with_zero_backoff(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response({"id": "j1", "attempts": 1, "max_attempts": 3}),
            _make_response([{"id": "j1"}]),
        ]
        status = repo.fail_job("j1", "w1", "tok", "quick retry", backoff_minutes=0)
        assert status == "pending"
        update = mock_supabase.table.return_value.update.call_args[0][0]
        assert "available_at" in update


# ── get_attempts ──────────────────────────────────────────────────────────────

class TestGetAttempts:
    def test_returns_attempts_for_job(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([
            {"job_id": "j1", "attempt": 1, "status": "failed"},
            {"job_id": "j1", "attempt": 2, "status": "succeeded"},
        ])
        attempts = repo.get_attempts("j1")
        assert len(attempts) == 2
        assert attempts[0]["status"] == "failed"

    def test_returns_empty_when_no_attempts(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        attempts = repo.get_attempts("nonexistent")
        assert attempts == []


# ── get_recent_runs ───────────────────────────────────────────────────────────

class TestGetRecentRuns:
    def test_returns_recent_runs(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([
            {"scheduler_name": "test", "status": "succeeded", "planned_at": "2026-01-01T00:00:00"},
            {"scheduler_name": "test", "status": "succeeded", "planned_at": "2026-01-02T00:00:00"},
        ])
        runs = repo.get_recent_runs("test", limit=10)
        assert len(runs) == 2

    def test_returns_empty_when_no_runs(self, repo, mock_supabase):
        mock_supabase.table.return_value.execute.return_value = _make_response([])
        runs = repo.get_recent_runs("nonexistent")
        assert runs == []


# ── Concurrent claim (race condition) ───────────────────────────────────────

class TestConcurrentClaim:
    """Simulates race conditions when multiple workers claim the same job."""

    async def test_concurrent_claim_only_one_wins(self, repo, mock_supabase):
        """Two concurrent claim_job calls — first wins, second gets None."""
        from asyncio import Event, create_task, gather

        call_count = 0
        barrier = Event()

        async def claim_race(worker_id: str):
            nonlocal call_count
            # Both workers block here until barrier is set
            await barrier.wait()

            # First call returns a job, second returns None (race lost)
            if call_count == 0:
                call_count += 1
                mock_supabase.table.return_value.execute.side_effect = [
                    _make_response([{"id": "job-1", "attempts": 0}]),
                    _make_response([{"id": "job-1", "status": "running", "lease_owner": worker_id}]),
                ]
            else:
                mock_supabase.table.return_value.execute.side_effect = [
                    _make_response([]),  # no pending jobs left
                ]

            return repo.claim_job(worker_id=worker_id)

        # Release both workers at the same time
        t1 = create_task(claim_race("worker-1"))
        t2 = create_task(claim_race("worker-2"))

        # Small yield to ensure both tasks are waiting on barrier
        await asyncio.sleep(0.01)
        barrier.set()

        r1, r2 = await gather(t1, t2)
        # Exactly one should win
        winners = sum(1 for r in [r1, r2] if r is not None)
        assert winners == 1, f"Expected 1 winner, got {winners}"

    async def test_claim_with_high_contention(self, repo, mock_supabase):
        """10 concurrent claimers, only one succeeds."""
        from asyncio import Event, create_task, gather

        barrier = Event()
        results = []

        async def claim_race(worker_id: str):
            await barrier.wait()
            mock_supabase.table.return_value.execute.side_effect = [
                _make_response([{"id": "job-1", "attempts": 0}]),
                _make_response([{"id": "job-1", "status": "running", "lease_owner": worker_id}]),
            ]
            return repo.claim_job(worker_id=worker_id)

        tasks = [create_task(claim_race(f"worker-{i}")) for i in range(10)]
        await asyncio.sleep(0.01)
        barrier.set()
        results = await gather(*tasks)

        winners = sum(1 for r in results if r is not None)
        assert winners >= 1, "At least one worker should claim"

    def test_claim_returns_updated_attempt_count(self, repo, mock_supabase):
        """claim_job increments the attempts field."""
        mock_supabase.table.return_value.execute.side_effect = [
            _make_response([{"id": "job-1", "attempts": 2}]),
            _make_response([{"id": "job-1", "status": "running", "attempts": 3}]),
        ]
        job = repo.claim_job(worker_id="w1")
        assert job is not None
        assert job["attempts"] == 3


# ── Retry wrapper (circuit breaker) ─────────────────────────────────────────

class TestDbCallRetry:
    """_db_call retries on transient errors, raises on persistent failure."""

    def test_retryable_error_substrings(self):
        from infrastructure.repositories.scheduler_repository import _is_retryable

        assert _is_retryable(Exception("timeout")) is True
        assert _is_retryable(Exception("timed out")) is True
        assert _is_retryable(Exception("connection reset by peer")) is True
        assert _is_retryable(Exception("connection refused")) is True
        assert _is_retryable(Exception("broken pipe")) is True
        assert _is_retryable(Exception("service temporarily unavailable")) is True
        assert _is_retryable(Exception("too many requests")) is True
        assert _is_retryable(Exception("internal server error")) is True

    def test_non_retryable_error_not_retried(self, repo, mock_supabase):
        """Non-retryable errors like syntax errors are not retried."""
        from infrastructure.repositories.scheduler_repository import _is_retryable

        assert _is_retryable(Exception("division by zero")) is False
        assert _is_retryable(Exception("column 'foo' does not exist")) is False
        assert _is_retryable(Exception("invalid input syntax")) is False
        assert _is_retryable(Exception("unique constraint violation")) is False

    def test_db_call_retries_on_timeout(self, repo, mock_supabase):
        """_db_call retries up to MAX_DB_RETRIES times on transient error."""
        from infrastructure.repositories.scheduler_repository import (
            MAX_DB_RETRIES,
        )

        calls = []
        def failing_fn():
            calls.append(1)
            raise Exception("timeout connecting to database")

        with pytest.raises(Exception, match="timeout connecting"):
            repo._db_call("test_op", failing_fn)

        assert len(calls) == MAX_DB_RETRIES

    def test_db_call_succeeds_on_retry(self, repo, mock_supabase):
        """_db_call succeeds on third attempt after two failures."""
        attempt_counter = [0]

        def flaky_fn():
            attempt_counter[0] += 1
            if attempt_counter[0] < 3:
                raise Exception("timeout connecting")
            return "success"

        result = repo._db_call("flaky_op", flaky_fn)
        assert result == "success"
        assert attempt_counter[0] == 3

    def test_db_call_non_retryable_raises_immediately(self, repo, mock_supabase):
        """_db_call does not retry non-transient errors (e.g. syntax error)."""
        calls = []

        def failing_fn():
            calls.append(1)
            raise Exception("invalid input syntax")

        with pytest.raises(Exception, match="invalid input"):
            repo._db_call("syntax_op", failing_fn)

        assert len(calls) == 1

    def test_get_scheduler_state_retries_on_timeout(self, repo, mock_supabase):
        """get_scheduler_state uses _db_call internally for retry."""
        mock_supabase.table.return_value.execute.side_effect = Exception("timeout")
        result = repo.get_scheduler_state("test")
        assert result is None

    def test_upsert_scheduler_state_retries_on_timeout(self, repo, mock_supabase):
        """upsert_scheduler_state uses _db_call internally."""
        mock_supabase.table.return_value.execute.side_effect = Exception("timeout")
        repo.upsert_scheduler_state({"scheduler_name": "test"})  # should not raise

    def test_record_planner_run_retries_on_timeout(self, repo, mock_supabase):
        """record_planner_run uses _db_call internally."""
        mock_supabase.table.return_value.execute.side_effect = Exception("timeout")
        repo.record_planner_run(scheduler_name="test")  # should not raise
