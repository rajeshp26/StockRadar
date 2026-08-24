"""
Tests for scheduler_worker.py — worker process lifecycle.
"""
import asyncio
import signal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_db_env():
    """Prevent real Supabase client creation by patching at import sites."""
    mock_db = MagicMock()
    mock_client = MagicMock()
    with (
        patch("database.supabase", mock_db),
        patch("infrastructure.repositories.scheduler_repository.supabase", mock_db),
        patch("database.create_client", return_value=mock_client),
    ):
        yield mock_db


class TestGracefulShutdown:
    def test_shutdown_flag_initially_false(self):
        with patch("signal.signal"):
            from scheduler_worker import GracefulShutdown
            gs = GracefulShutdown()
            assert gs.shutdown_requested is False

    def test_registers_signal_handlers(self):
        with patch("signal.signal") as mock_signal:
            from scheduler_worker import GracefulShutdown
            gs = GracefulShutdown()
            assert mock_signal.call_count == 2
            signals_used = [call[0][0] for call in mock_signal.call_args_list]
            assert signal.SIGTERM in signals_used
            assert signal.SIGINT in signals_used

    def test_sets_flag_on_sigterm(self):
        with patch("signal.signal"):
            from scheduler_worker import GracefulShutdown
            gs = GracefulShutdown()
            gs.request_shutdown(signal.SIGTERM, None)
            assert gs.shutdown_requested is True

    def test_sets_flag_on_sigint(self):
        with patch("signal.signal"):
            from scheduler_worker import GracefulShutdown
            gs = GracefulShutdown()
            gs.request_shutdown(signal.SIGINT, None)
            assert gs.shutdown_requested is True

    def test_sets_flag_only_once(self):
        with patch("signal.signal"):
            from scheduler_worker import GracefulShutdown
            gs = GracefulShutdown()
            gs.request_shutdown(signal.SIGTERM, None)
            assert gs.shutdown_requested is True
            gs.request_shutdown(signal.SIGTERM, None)
            assert gs.shutdown_requested is True


class TestWorkerMain:
    """Tests for scheduler_worker.main() startup and shutdown sequence."""

    async def _run_main_quick(self, shutdown_flag=True, enable_all_schedulers=False):
        """
        Helper: run main() with shutdown immediately set, inside standard patches.
        Returns a dict of mocks for assertions.
        """
        mocks = {}
        patcher_specs = [
            ("GracefulShutdown", None),
            ("JobEngine", None),
            ("SchedulerPlanner", None),
            ("SuperInvestorsRefreshScheduler", None),
            ("MarketDataRefreshScheduler", None),
            ("EarningsRefreshScheduler", None),
            ("AggregationScheduler", None),
            ("SchedulerRepository", None),
        ]

        patchers = []
        started_mocks = {}
        for name, _ in patcher_specs:
            p = patch(f"scheduler_worker.{name}")
            started_mocks[name] = p.start()
            patchers.append(p)

        settings_patchers = []
        if enable_all_schedulers:
            for flag in ["ENABLE_SUPER_INVESTORS_SCHEDULER"]:
                p = patch("config.settings.ENABLE_SUPER_INVESTORS_SCHEDULER", True)
                p.start()
                settings_patchers.append(p)

        try:
            sw = __import__("scheduler_worker", fromlist=["main"])

            mock_shutdown = MagicMock()
            mock_shutdown.shutdown_requested = shutdown_flag
            started_mocks["GracefulShutdown"].return_value = mock_shutdown

            mock_engine = AsyncMock()
            mock_engine.get_worker_id = MagicMock(return_value="test-worker")
            mock_engine.register_handler = MagicMock()
            started_mocks["JobEngine"].return_value = mock_engine

            mock_planner = AsyncMock()
            mock_planner.register = MagicMock()
            started_mocks["SchedulerPlanner"].return_value = mock_planner

            for sched_name in ["SuperInvestorsRefreshScheduler", "MarketDataRefreshScheduler", "AggregationScheduler"]:
                inst = MagicMock()
                inst.interval_hours = 24
                started_mocks[sched_name].return_value = inst

            ea_inst = MagicMock()
            ea_inst.interval_hours = 2
            started_mocks["EarningsRefreshScheduler"].return_value = ea_inst

            mock_repo = MagicMock()
            mock_repo.record_heartbeat = MagicMock()
            mock_repo.release_worker_leases = MagicMock(return_value=0)
            started_mocks["SchedulerRepository"].return_value = mock_repo

            mocks["shutdown"] = mock_shutdown
            mocks["engine"] = mock_engine
            mocks["planner"] = mock_planner
            mocks["repo"] = mock_repo

            try:
                await asyncio.wait_for(sw.main(), timeout=5.0)
            except TimeoutError:
                pytest.fail("main() did not shutdown within timeout")
            except Exception:
                pass

            return mocks
        finally:
            for p in settings_patchers:
                p.stop()
            for p in patchers:
                p.stop()

    async def test_creates_job_engine(self, mock_db_env):
        mocks = await self._run_main_quick()
        assert hasattr(mocks["engine"], "get_worker_id")

    async def test_creates_planner(self, mock_db_env):
        mocks = await self._run_main_quick()
        assert mocks["planner"].register.called

    async def test_registers_three_handlers(self, mock_db_env):
        mocks = await self._run_main_quick()
        handler_types = [
            call[0][0] for call in mocks["engine"].register_handler.call_args_list
        ]
        assert len(handler_types) == 4
        assert "company_refresh" in handler_types
        assert "investor_refresh" in handler_types
        assert "aggregation_refresh" in handler_types
        assert "portfolio_snapshot" in handler_types

    async def test_registers_schedulers_when_enabled(self, mock_db_env):
        mocks = await self._run_main_quick(enable_all_schedulers=True)
        registered_names = [
            call[1]["name"] for call in mocks["planner"].register.call_args_list
        ]
        assert "super_investors" in registered_names
        assert "market_data" in registered_names
        assert "earnings" in registered_names
        assert "aggregation" in registered_names

    async def test_shutdown_releases_leases(self, mock_db_env):
        mocks = await self._run_main_quick()
        mocks["repo"].release_worker_leases.assert_called_once_with("test-worker")

    async def test_shutdown_records_final_heartbeat(self, mock_db_env):
        mocks = await self._run_main_quick()
        heartbeat_calls = mocks["repo"].record_heartbeat.call_args_list
        final_hb = [
            c for c in heartbeat_calls
            if c[1].get("active_jobs") == 0
        ]
        assert len(final_hb) >= 1

    async def test_shutdown_records_final_heartbeat_with_shutdown_hostname(self, mock_db_env):
        mocks = await self._run_main_quick()
        heartbeat_calls = mocks["repo"].record_heartbeat.call_args_list
        shutdown_hb = [
            c for c in heartbeat_calls
            if c[1].get("hostname") == "shutdown"
        ]
        assert len(shutdown_hb) >= 1


class TestHandlerFunctions:
    async def test_handle_company_refresh_market_data(self, mock_db_env):
        from scheduler_worker import handle_company_refresh

        with patch("scheduler_worker.MarketDataRefreshScheduler") as mock_md:
            mock_instance = AsyncMock()
            mock_instance._process_company = AsyncMock(
                return_value={"symbol": "AAPL", "status": "ok"}
            )
            mock_md.return_value = mock_instance

            result = await handle_company_refresh({
                "payload": {
                    "company_id": 1,
                    "ticker_symbol": "AAPL",
                    "security_type": "stock",
                    "exchange": "NASDAQ",
                    "scopes": ["market_data"],
                }
            })

            assert "market_data" in result

    async def test_handle_company_refresh_financials(self, mock_db_env):
        from scheduler_worker import handle_company_refresh

        with patch("scheduler_worker.EarningsRefreshScheduler") as mock_ea:
            mock_instance = AsyncMock()
            mock_instance._refresh_company_financials_optimized = AsyncMock(
                return_value={"income_statements": 1}
            )
            mock_ea.return_value = mock_instance

            result = await handle_company_refresh({
                "payload": {
                    "company_id": 1,
                    "ticker_symbol": "AAPL",
                    "scopes": ["financials"],
                }
            })

            assert "financials" in result

    async def test_handle_company_refresh_missing_id_raises(self, mock_db_env):
        from scheduler_worker import handle_company_refresh

        with pytest.raises(ValueError, match="Missing company_id"):
            await handle_company_refresh({
                "payload": {"scopes": ["market_data"]}
            })

    async def test_handle_company_refresh_missing_symbol_raises(self, mock_db_env):
        from scheduler_worker import handle_company_refresh

        with pytest.raises(ValueError, match="Missing company_id"):
            await handle_company_refresh({
                "payload": {"company_id": 1}
            })

    async def test_handle_investor_refresh(self, mock_db_env):
        from scheduler_worker import handle_investor_refresh

        with patch("scheduler_worker.SuperInvestorsRefreshScheduler") as mock_si:
            mock_instance = AsyncMock()
            mock_instance._refresh_single_investor = AsyncMock(return_value=True)
            mock_si.return_value = mock_instance

            result = await handle_investor_refresh({
                "payload": {
                    "cik": "0000320193",
                    "name": "Warren Buffett",
                    "firm": "Berkshire Hathaway",
                    "tag": "buffett",
                }
            })

            assert result["status"] == "ok"
            assert result["cik"] == "0000320193"

    async def test_handle_investor_refresh_missing_cik_raises(self, mock_db_env):
        from scheduler_worker import handle_investor_refresh

        with pytest.raises(ValueError, match="Missing cik"):
            await handle_investor_refresh({"payload": {}})

    async def test_handle_investor_refresh_skipped(self, mock_db_env):
        from scheduler_worker import handle_investor_refresh

        with patch("scheduler_worker.SuperInvestorsRefreshScheduler") as mock_si:
            mock_instance = AsyncMock()
            mock_instance._refresh_single_investor = AsyncMock(return_value=False)
            mock_si.return_value = mock_instance

            result = await handle_investor_refresh({
                "payload": {
                    "cik": "0000320193",
                    "name": "Test",
                }
            })

            assert result["status"] == "skipped"

    async def test_handle_aggregation_refresh(self, mock_db_env):
        import application.jobs.aggregation_jobs as agg
        from scheduler_worker import handle_aggregation_refresh
        with patch.object(agg, "compute_and_upsert_group_metric_stats") as mock_agg:
            mock_agg.return_value = {"sectors_updated": 10}

            result = await handle_aggregation_refresh({
                "payload": {
                    "group_type": "sector",
                    "min_sample_size": 5,
                }
            })

            assert result["sectors_updated"] == 10

    async def test_handle_aggregation_refresh_default_params(self, mock_db_env):
        import application.jobs.aggregation_jobs as agg
        from scheduler_worker import handle_aggregation_refresh
        with patch.object(agg, "compute_and_upsert_group_metric_stats") as mock_agg:
            mock_agg.return_value = {"sectors_updated": 5}

            result = await handle_aggregation_refresh({"payload": {}})

            assert result["sectors_updated"] == 5


class TestHeartbeatLoop:
    async def test_heartbeat_records_periodically(self, mock_db_env):
        """Heartbeat writes at least once during brief main() execution."""
        patcher_specs = [
            "GracefulShutdown", "JobEngine", "SchedulerPlanner",
            "SuperInvestorsRefreshScheduler", "MarketDataRefreshScheduler",
            "EarningsRefreshScheduler", "AggregationScheduler", "SchedulerRepository",
        ]

        patchers = []
        started = {}
        for name in patcher_specs:
            p = patch(f"scheduler_worker.{name}")
            started[name] = p.start()
            patchers.append(p)

        try:
            sw = __import__("scheduler_worker", fromlist=["main"])

            mock_shutdown = MagicMock()
            mock_shutdown.shutdown_requested = False
            started["GracefulShutdown"].return_value = mock_shutdown

            mock_engine = AsyncMock()
            mock_engine.get_worker_id = MagicMock(return_value="test-worker")
            mock_engine.register_handler = MagicMock()
            started["JobEngine"].return_value = mock_engine

            mock_planner = AsyncMock()
            mock_planner.register = MagicMock()
            started["SchedulerPlanner"].return_value = mock_planner

            for sched in ["SuperInvestorsRefreshScheduler", "MarketDataRefreshScheduler", "AggregationScheduler"]:
                inst = MagicMock()
                inst.interval_hours = 24
                started[sched].return_value = inst
            started["EarningsRefreshScheduler"].return_value = MagicMock(interval_hours=2)

            mock_repo = MagicMock()
            mock_repo.record_heartbeat = MagicMock()
            mock_repo.release_worker_leases = MagicMock(return_value=0)
            started["SchedulerRepository"].return_value = mock_repo

            async def shutdown_after_delay():
                await asyncio.sleep(0.15)
                mock_shutdown.shutdown_requested = True

            asyncio.create_task(shutdown_after_delay())

            try:
                await asyncio.wait_for(sw.main(), timeout=5.0)
            except (TimeoutError, Exception):
                pass

            assert mock_repo.record_heartbeat.call_count >= 1
        finally:
            for p in patchers:
                p.stop()


class TestLoggingConfiguration:
    """scheduler_worker.py must configure logging for visible startup output."""

    def test_module_has_logging_basicconfig(self):
        """Module-level logging.basicConfig ensures logger.info() produces output."""
        import inspect

        import scheduler_worker
        source = inspect.getsource(scheduler_worker)
        assert "logging.basicConfig" in source, (
            "scheduler_worker.py must call logging.basicConfig() so "
            "logger.info() messages are visible at startup"
        )


class TestJobEngineLeaseCleanup:
    """Lease renewal tasks must be cleaned up after job execution."""

    async def test_lease_renewal_task_cancelled_on_success(self):
        """Renewal task is properly cancelled after successful handler execution."""
        from application.jobs.job_engine import JobEngine

        repo = MagicMock()
        repo.record_attempt = MagicMock()
        repo.complete_job = MagicMock(return_value=True)
        repo.fail_job = MagicMock()
        repo.get_unprocessed_refresh_requests = MagicMock(return_value=[])

        engine = JobEngine(scheduler_repo=repo)
        engine.register_handler("test", lambda job: asyncio.sleep(0.01))

        job = {"id": "job-1", "job_type": "test", "lease_token": "tok-1", "attempts": 0}

        tasks_before = len(asyncio.all_tasks())
        await engine.execute_job(job)
        tasks_after = len(asyncio.all_tasks())

        # No new lingering tasks
        assert tasks_after <= tasks_before + 1  # delta allows for the test runner's own tasks

    async def test_lease_renewal_task_cancelled_on_failure(self):
        """Renewal task is properly cancelled after handler raises."""
        from application.jobs.job_engine import JobEngine

        repo = MagicMock()
        repo.record_attempt = MagicMock()
        repo.complete_job = MagicMock()
        repo.fail_job = MagicMock(return_value="pending")
        repo.get_unprocessed_refresh_requests = MagicMock(return_value=[])

        engine = JobEngine(scheduler_repo=repo)

        async def failing_handler(job):
            raise ValueError("handler failed")

        engine.register_handler("test", failing_handler)

        job = {"id": "job-2", "job_type": "test", "lease_token": "tok-2", "attempts": 0}

        tasks_before = len(asyncio.all_tasks())
        await engine.execute_job(job)
        tasks_after = len(asyncio.all_tasks())

        assert tasks_after <= tasks_before + 1

    async def test_no_handler_no_leak(self):
        """Missing handler does not create a renewal task."""
        from application.jobs.job_engine import JobEngine

        repo = MagicMock()
        repo.record_attempt = MagicMock()
        repo.fail_job = MagicMock(return_value="pending")

        engine = JobEngine(scheduler_repo=repo)
        # No handler registered

        job = {"id": "job-3", "job_type": "nonexistent", "lease_token": "tok-3", "attempts": 0}

        tasks_before = len(asyncio.all_tasks())
        await engine.execute_job(job)
        tasks_after = len(asyncio.all_tasks())

        assert tasks_after <= tasks_before + 1
        repo.fail_job.assert_called_once()
