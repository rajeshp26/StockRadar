"""
Tests for FreshnessMonitorScheduler - plan() job shape and snapshot() coverage
math across both domains using deterministic dates (today=2026-09-05).
"""

import logging
from datetime import date
from unittest.mock import AsyncMock, patch


class TestFreshnessMonitor:
    """FreshnessMonitorScheduler plan() emits a single snapshot job per day."""

    def _make_scheduler(self, repo=None, **kwargs):
        if repo is None:
            repo = AsyncMock()
            repo.append_freshness_snapshot = AsyncMock()
        with (
            patch("infrastructure.repositories.financial_repository.SupabaseFinancialRepository"),
            patch("providers.defeat_beta_provider.DefeatBetaProvider"),
            patch("providers.yfinance_provider.YFinanceProvider"),
            patch("providers.stockdex_provider.StockdexMacrotrendsProvider"),
            patch("providers.edgar_provider.EdgarToolsProvider"),
        ):
            import importlib
            mod = importlib.import_module(
                "application.schedulers.freshness_monitor_scheduler"
            )
            cls = getattr(mod, "FreshnessMonitorScheduler")
            return cls(financial_repo=repo, **kwargs)

    async def test_plan_returns_single_snapshot_job(self):
        scheduler = self._make_scheduler()
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_type"] == "freshness_snapshot"
        assert job["dedupe_key"] == "freshness_snapshot:2026-09-05"
        assert job["resource_type"] == "system"
        assert job["resource_id"] == "2026-09-05"
        assert job["payload"]["as_of"] == "2026-09-05"
        assert job["payload"]["reasons"] == ["routine"]
        assert job["priority"] == 20

    async def test_plan_dedupe_key_unique_per_day(self):
        scheduler = self._make_scheduler()
        jobs_a = await scheduler.plan(today=date(2026, 9, 5))
        jobs_b = await scheduler.plan(today=date(2026, 9, 6))
        assert jobs_a[0]["dedupe_key"] != jobs_b[0]["dedupe_key"]

    async def test_snapshot_persists_both_domains_at_100_percent(self):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = []
        repo.get_tracked_investors.return_value = []
        repo.append_freshness_snapshot = AsyncMock()
        scheduler = self._make_scheduler(repo)
        result = await scheduler.snapshot(today=date(2026, 9, 5))
        assert repo.append_freshness_snapshot.call_count == 2
        domains = result["domains"]
        assert domains["financial_statements"]["coverage"] == 100.0
        assert domains["institutional_holdings"]["coverage"] == 100.0
        rows = [c.args[0] for c in repo.append_freshness_snapshot.call_args_list]
        rows_by_domain = {r["domain"]: r for r in rows}
        assert set(rows_by_domain) == {
            "financial_statements", "institutional_holdings",
        }
        for r in rows:
            assert r["as_of"] == "2026-09-05"
            assert r["pct"] == 100.0
            assert r["total"] == 0
            assert r["covered"] == 0
        # expected_period is the per-domain watermark (doc §2.2), not as_of:
        # financial = last completed quarter start; investors = prior quarter end.
        assert rows_by_domain["financial_statements"]["expected_period"] == "2026-04-01"
        assert rows_by_domain["institutional_holdings"]["expected_period"] == "2026-06-30"

    async def test_snapshot_coverage_math_full(self):
        repo = AsyncMock()
        # Candidates loaded across Q1+Q2 2026 => expected {03-31, 06-30};
        # rows cover both => 100% coverage.
        repo.get_financial_candidates.return_value = [
            {"company_id": 1, "first_financial_data_loaded_at": "2026-01-10", "data_completeness_status": "COMPLETE"},
            {"company_id": 2, "first_financial_data_loaded_at": "2026-04-12", "data_completeness_status": "COMPLETE"},
        ]
        repo.get_financial_periods_in_range.return_value = [
            {"company_id": 1, "period_end_date": "2026-03-31"},
            {"company_id": 2, "period_end_date": "2026-06-30"},
        ]
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        repo.append_freshness_snapshot = AsyncMock()
        scheduler = self._make_scheduler(repo)
        result = await scheduler.snapshot(today=date(2026, 9, 5))
        fin = result["domains"]["financial_statements"]
        assert fin["covered"] == 2
        assert fin["total"] == 2
        assert fin["coverage"] == 100.0

    async def test_snapshot_coverage_math_half(self):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = [
            {"company_id": 1, "first_financial_data_loaded_at": "2026-01-10", "data_completeness_status": "COMPLETE"},
        ]
        repo.get_financial_periods_in_range.return_value = []
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        repo.append_freshness_snapshot = AsyncMock()
        scheduler = self._make_scheduler(repo)
        result = await scheduler.snapshot(today=date(2026, 9, 5))
        fin = result["domains"]["financial_statements"]
        assert fin["total"] == 2
        assert fin["covered"] == 0
        assert fin["coverage"] == 0.0

    async def test_snapshot_alerts_below_threshold(self, caplog):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = [
            {"company_id": 1, "first_financial_data_loaded_at": "2026-01-10", "data_completeness_status": "COMPLETE"},
        ]
        repo.get_financial_periods_in_range.return_value = []
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        repo.append_freshness_snapshot = AsyncMock()
        scheduler = self._make_scheduler(repo)
        with caplog.at_level(
            logging.ERROR, logger="application.schedulers.freshness_monitor_scheduler"
        ):
            await scheduler.snapshot(today=date(2026, 9, 5))
        # Alert carries domain, expected period, and the bounded missing list.
        assert "FRESHNESS ALERT: financial_statements coverage" in caplog.text
        assert "expected_period 2026-04-01" in caplog.text
        assert "missing 1" in caplog.text

    async def test_snapshot_empty_population_is_fresh_no_alert(self, caplog):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = []
        repo.get_tracked_investors.return_value = []
        repo.append_freshness_snapshot = AsyncMock()
        scheduler = self._make_scheduler(repo)
        with caplog.at_level(
            logging.ERROR, logger="application.schedulers.freshness_monitor_scheduler"
        ):
            result = await scheduler.snapshot(today=date(2026, 9, 5))
        assert "FRESHNESS ALERT" not in caplog.text
        assert result["domains"]["financial_statements"]["coverage"] == 100.0
