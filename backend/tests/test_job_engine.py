from unittest.mock import AsyncMock, MagicMock

import pytest

# ── classify_failure ──────────────────────────────────────────────────────────

class TestClassifyFailure:
    def test_network_timeout(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("connection timed out") == "network_timeout"
        assert classify_failure("timeout after 30s") == "network_timeout"

    def test_rate_limited(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("rate limit exceeded") == "rate_limited"
        assert classify_failure("", status_code=429) == "rate_limited"

    def test_provider_5xx(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("503 Service Unavailable") == "provider_5xx"
        assert classify_failure("", status_code=502) == "provider_5xx"
        assert classify_failure("server error") == "provider_5xx"

    def test_data_validation(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("validation failed: invalid field") == "data_validation"
        assert classify_failure("invalid ticker symbol") == "data_validation"

    def test_not_found(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("404 Not Found") == "not_found"
        assert classify_failure("resource not found") == "not_found"
        assert classify_failure("", status_code=404) == "not_found"

    def test_bad_request(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("400 Bad Request") == "bad_request"
        assert classify_failure("", status_code=400) == "bad_request"

    def test_fallback_code_exception(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("some unknown python error") == "code_exception"
        assert classify_failure("") == "code_exception"

    def test_status_code_overrides_message(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure("some random text", status_code=429) == "rate_limited"
        assert classify_failure("", status_code=503) == "provider_5xx"

    def test_postgres_constraint_errors_not_provider_5xx(self):
        from application.jobs.job_engine import classify_failure
        assert classify_failure(
            'null value in column "company_id" violates not-null constraint '
            '(23502)'
        ) == "code_exception"
        assert classify_failure(
            'new row violates check constraint "check_conflict_values" (23514)'
        ) == "code_exception"
        assert classify_failure(
            'insert or update on table "splits" violates foreign key constraint '
            '(23503)'
        ) == "code_exception"
        assert classify_failure(
            'duplicate key value violates unique constraint "splits_pkey" (23505)'
        ) == "code_exception"


# ── Backoff Rules ─────────────────────────────────────────────────────────────

class TestBackoffRules:
    def test_all_rules_have_keys(self):
        from application.jobs.job_engine import BACKOFF_RULES
        for category, rules in BACKOFF_RULES.items():
            assert "backoff_minutes" in rules
            assert "max_attempts" in rules


# ── JobEngine ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.claim_job = MagicMock(return_value=None)
    repo.complete_job = MagicMock(return_value=True)
    repo.fail_job = MagicMock(return_value="pending")
    repo.renew_job_lease = MagicMock(return_value=True)
    repo.record_attempt = MagicMock()
    repo.get_job = MagicMock()
    return repo


@pytest.fixture
def engine(mock_repo):
    from application.jobs.job_engine import JobEngine
    eng = JobEngine(scheduler_repo=mock_repo, worker_id="test_worker")
    eng._claim_poll_interval = 0.01
    eng._lease_renewal_interval = 0.05
    return eng


class TestJobEngineExecuteJob:
    async def test_executes_handler_and_completes(self, engine, mock_repo):
        handler = AsyncMock(return_value={"status": "ok"})
        engine.register_handler("test_type", handler)
        job = {
            "id": "job-1",
            "job_type": "test_type",
            "lease_token": "tok",
            "attempts": 0,
        }
        await engine.execute_job(job)
        handler.assert_awaited_once_with(job)
        mock_repo.complete_job.assert_called_once_with("job-1", "test_worker", "tok")
        mock_repo.record_attempt.assert_called()

    async def test_no_handler_moves_to_dead_letter(self, engine, mock_repo):
        job = {
            "id": "job-1",
            "job_type": "unknown",
            "lease_token": "tok",
            "attempts": 0,
        }
        await engine.execute_job(job)
        mock_repo.fail_job.assert_called_once()
        args = mock_repo.fail_job.call_args[1]
        assert "No handler" in args["error"]
        assert args["backoff_minutes"] == 0

    async def test_handler_exception_triggers_retry(self, engine, mock_repo):
        handler = AsyncMock(side_effect=Exception("timeout error"))
        engine.register_handler("test_type", handler)
        mock_repo.fail_job.return_value = "pending"
        job = {
            "id": "job-1",
            "job_type": "test_type",
            "lease_token": "tok",
            "attempts": 0,
        }
        await engine.execute_job(job)
        mock_repo.fail_job.assert_called_once()
        call_args = mock_repo.fail_job.call_args[1]
        assert "network_timeout" in call_args["error"]
        assert call_args["backoff_minutes"] == 5

    async def test_handler_exception_dead_letter(self, engine, mock_repo):
        handler = AsyncMock(side_effect=Exception("bad request"))
        engine.register_handler("test_type", handler)
        mock_repo.fail_job.return_value = "dead_letter"
        job = {
            "id": "job-1",
            "job_type": "test_type",
            "lease_token": "tok",
            "attempts": 0,
        }
        await engine.execute_job(job)
        mock_repo.fail_job.assert_called_once()
        call_args = mock_repo.fail_job.call_args[1]
        assert "bad_request" in call_args["error"]
        assert call_args["backoff_minutes"] == 0

    async def test_lease_renewal_during_execution(self, engine, mock_repo):
        calls = []

        async def slow_handler(job):
            calls.append("started")
            await asyncio.sleep(1)
            calls.append("finished")
            return {"ok": True}

        import asyncio
        engine._lease_renewal_interval = 0.05  # fast renewal for test
        engine.register_handler("slow_type", slow_handler)
        job = {
            "id": "job-1",
            "job_type": "slow_type",
            "lease_token": "tok",
            "attempts": 0,
        }
        await engine.execute_job(job)
        assert mock_repo.renew_job_lease.called
        assert len(calls) == 2

    async def test_stale_renewal_doesnt_block_completion(self, engine, mock_repo):
        mock_repo.renew_job_lease.return_value = True

        async def fast_handler(job):
            return {"ok": True}

        engine.register_handler("fast_type", fast_handler)
        job = {
            "id": "job-1",
            "job_type": "fast_type",
            "lease_token": "tok",
            "attempts": 0,
        }
        await engine.execute_job(job)
        mock_repo.complete_job.assert_called_once()


class TestJobEngineWorkerPool:
    async def test_worker_loop_claims_and_executes(self, engine, mock_repo):
        import asyncio
        handler = AsyncMock(return_value={"ok": True})
        engine.register_handler("test", handler)
        job = {
            "id": "job-1",
            "job_type": "test",
            "lease_token": "tok",
            "attempts": 0,
        }
        mock_repo.claim_job.side_effect = [job]

        task = asyncio.create_task(engine._worker_loop(0))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        handler.assert_awaited_once_with(job)
        mock_repo.complete_job.assert_called_once_with("job-1", "test_worker", "tok")

    async def test_worker_loop_empty_sleeps(self, engine, mock_repo):
        import asyncio
        mock_repo.claim_job.return_value = None
        task = asyncio.create_task(engine._worker_loop(0))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        assert mock_repo.claim_job.called

    async def test_worker_loop_error_continues(self, engine, mock_repo):
        import asyncio
        mock_repo.claim_job.side_effect = [Exception("boom")]
        task = asyncio.create_task(engine._worker_loop(0))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        assert mock_repo.claim_job.call_count >= 1

    async def test_run_worker_pool_starts_multiple_workers(self, engine, mock_repo):
        import asyncio
        mock_repo.claim_job.side_effect = [Exception("stop")]
        engine._claim_poll_interval = 0.01

        task = asyncio.create_task(engine.run_worker_pool(concurrency=3))
        await asyncio.sleep(0.05)
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        # Each worker should have polled at least once
        assert mock_repo.claim_job.call_count >= 3


@pytest.fixture(autouse=True)
def ensure_asyncio():
    import asyncio
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
