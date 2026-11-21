"""
Tests for ReconciliationScheduler.plan() - gap detection for the financial and
super-investor domains. Uses deterministic dates so watermark math is exact
(today=2026-09-05 => watermark = 2026-04-01 = start of Q3 2026).
"""

from datetime import date
from unittest.mock import AsyncMock, patch


class TestReconciliationPlan:
    """ReconciliationScheduler.plan() detects missing financial/investor periods."""

    def _make_scheduler(self, repo=None, **kwargs):
        if repo is None:
            repo = AsyncMock()
            repo.get_financial_candidates.return_value = []
            repo.get_financial_periods_in_range.return_value = []
            repo.get_tracked_investors.return_value = []
            repo.get_investor_periods_in_range.return_value = []
        with (
            patch("infrastructure.repositories.financial_repository.SupabaseFinancialRepository"),
            patch("providers.defeat_beta_provider.DefeatBetaProvider"),
            patch("providers.yfinance_provider.YFinanceProvider"),
            patch("providers.stockdex_provider.StockdexMacrotrendsProvider"),
            patch("providers.edgar_provider.EdgarToolsProvider"),
        ):
            import importlib
            mod = importlib.import_module(
                "application.schedulers.reconciliation_scheduler"
            )
            cls = mod.ReconciliationScheduler
            return cls(financial_repo=repo, **kwargs)

    async def test_plan_with_no_candidates_returns_no_jobs(self):
        scheduler = self._make_scheduler()
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert jobs == []

    async def test_financial_gap_enqueues_company_refresh_job(self):
        repo = AsyncMock()
        # Candidate loaded 2026-04-07 (in Q2 2026); with watermark 2026-04-01
        # the expected window is exactly {2026-06-30}. Zero rows => one gap.
        repo.get_financial_candidates.return_value = [
            {
                "company_id": 2,
                "ticker_symbol": "TEST",  # I1d: required since commit d5733a71
                "first_financial_data_loaded_at": "2026-04-07T10:00:00Z",
                "data_completeness_status": "PARTIAL",
            },
        ]
        repo.get_financial_periods_in_range.return_value = []
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_type"] == "company_refresh"
        assert job["dedupe_key"] == "company_refresh:2:financials"
        assert job["resource_type"] == "company"
        assert job["resource_id"] == "2"
        assert job["payload"]["scopes"] == ["financials"]
        assert job["payload"]["reasons"] == ["reconciliation"]
        assert job["priority"] == 20
        assert job["max_attempts"] == 3
        assert "not_before" in job

    async def test_financial_missing_last_completed_quarter(self):
        repo = AsyncMock()
        # Candidate loaded in Q1 2026 => expected {2026-03-31, 2026-06-30};
        # only Q1 present => gap at 2026-06-30 still enqueues a job.
        repo.get_financial_candidates.return_value = [
            {
                "company_id": 3,
                "ticker_symbol": "TEST",  # I1d: required since commit d5733a71
                "first_financial_data_loaded_at": "2026-01-15T10:00:00Z",
                "data_completeness_status": "COMPLETE",
            },
        ]
        repo.get_financial_periods_in_range.return_value = [
            {"company_id": 3, "period_end_date": "2026-03-31"},
        ]
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert len(jobs) == 1
        assert jobs[0]["dedupe_key"] == "company_refresh:3:financials"

    async def test_financial_no_gap_when_periods_present(self):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = [
            {
                "company_id": 4,
                "ticker_symbol": "TEST",  # I1d: required since commit d5733a71
                "first_financial_data_loaded_at": "2026-04-07T10:00:00Z",
                "data_completeness_status": "CURRENT",
            },
        ]
        repo.get_financial_periods_in_range.return_value = [
            {"company_id": 4, "period_end_date": "2026-06-30"},
        ]
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert jobs == []

    async def test_investor_shortfall_enqueues_investor_refresh(self):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = []
        repo.get_financial_periods_in_range.return_value = []
        repo.get_tracked_investors.return_value = [
            {
                "investor_id": 7,
                "cik": "0001234",
                "investor_name": "Buffett",
                "firm_name": "Berkshire",
                "investor_tag": "value",
            },
        ]
        repo.get_investor_periods_in_range.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_type"] == "investor_refresh"
        assert job["dedupe_key"] == "investor_refresh:0001234"
        assert job["resource_type"] == "investor"
        assert job["resource_id"] == "0001234"
        assert job["payload"]["cik"] == "0001234"
        assert job["payload"]["name"] == "Buffett"
        assert job["payload"]["firm"] == "Berkshire"
        assert job["payload"]["tag"] == "value"
        assert job["payload"]["reasons"] == ["reconciliation"]
        assert job["priority"] == 20

    async def test_investor_full_history_within_window_no_job(self):
        from application.schedulers.reconciliation_scheduler import settings as rec_settings
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = []
        repo.get_financial_periods_in_range.return_value = []
        repo.get_tracked_investors.return_value = [
            {"investor_id": 7, "cik": "0001234"},
        ]
        # SUPER_INVESTORS_INITIAL_QUARTERS=2 => expected window {2026-03-31,
        # 2026-06-30}; both present => no shortfall => no job.
        repo.get_investor_periods_in_range.return_value = [
            {"investor_id": 7, "quarter_end_date": "2026-03-31"},
            {"investor_id": 7, "quarter_end_date": "2026-06-30"},
        ]
        with patch.object(rec_settings, "SUPER_INVESTORS_INITIAL_QUARTERS", 2):
            scheduler = self._make_scheduler(repo)
            jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert jobs == []

    async def test_investor_default_window_shortfall_job(self):
        repo = AsyncMock()
        repo.get_financial_candidates.return_value = []
        repo.get_financial_periods_in_range.return_value = []
        repo.get_tracked_investors.return_value = [
            {"investor_id": 7, "cik": "0001234"},
        ]
        # Default window (20 quarters from Q1 2021) is far larger than two rows
        # => shortfall => job enqueued.
        repo.get_investor_periods_in_range.return_value = [
            {"investor_id": 7, "quarter_end_date": "2026-03-31"},
            {"investor_id": 7, "quarter_end_date": "2026-06-30"},
        ]
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert len(jobs) == 1
        assert jobs[0]["dedupe_key"] == "investor_refresh:0001234"

    async def test_financials_pass_failure_does_not_block_investors(self):
        repo = AsyncMock()
        repo.get_financial_candidates.side_effect = Exception("boom")
        repo.get_tracked_investors.return_value = []
        repo.get_investor_periods_in_range.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan(today=date(2026, 9, 5))
        assert jobs == []

    async def test_shared_quarter_helpers_pin_watermark(self):
        from application.schedulers.quarter_utils import quarter_ends_between
        # A candidate loaded 2026-04-07 opens its window at Q2 2026; the
        # watermark for today=2026-09-05 is 2026-04-01, closing at Q2 2026,
        # so exactly {2026-06-30} is expected.
        assert quarter_ends_between(date(2026, 4, 1), date(2026, 4, 1)) == {
            date(2026, 6, 30),
        }
        # A Q1-loaded company additionally expects 2026-03-31.
        assert quarter_ends_between(date(2026, 1, 1), date(2026, 4, 1)) == {
            date(2026, 3, 31),
            date(2026, 6, 30),
        }
