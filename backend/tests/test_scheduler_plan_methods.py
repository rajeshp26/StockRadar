"""
Tests for actual scheduler plan() methods — verifies job dict format
and edge cases for each scheduler's v3 planner integration.
"""
from unittest.mock import AsyncMock, MagicMock, patch


class TestSuperInvestorsPlan:
    """SuperInvestorsRefreshScheduler.plan() reads SUPER_INVESTORS dict, no DB."""

    def _make_scheduler(self, **kwargs):
        if "service" not in kwargs:
            kwargs["service"] = MagicMock()
        return _import_and_construct(
            "application.schedulers.super_investors_scheduler",
            "SuperInvestorsRefreshScheduler",
            **kwargs,
        )

    async def test_plan_returns_correct_format(self):
        import application.schedulers.super_investors_scheduler as mod
        original = dict(mod.SUPER_INVESTORS)
        mod.SUPER_INVESTORS = {
            "0001": {"name": "A", "firm": "F", "tag": "v"},
        }
        try:
            scheduler = self._make_scheduler()
            jobs = await scheduler.plan()
            assert len(jobs) == 1
            job = jobs[0]
            assert job["job_type"] == "investor_refresh"
            assert job["dedupe_key"] == "investor_refresh:0001"
            assert job["resource_type"] == "investor"
            assert job["payload"]["cik"] == "0001"
            assert job["payload"]["name"] == "A"
            assert job["priority"] == 50
        finally:
            mod.SUPER_INVESTORS = original

    async def test_plan_handles_empty_investors(self):
        import application.schedulers.super_investors_scheduler as mod
        original = dict(mod.SUPER_INVESTORS)
        mod.SUPER_INVESTORS = {}
        try:
            scheduler = self._make_scheduler()
            jobs = await scheduler.plan()
            assert jobs == []
        finally:
            mod.SUPER_INVESTORS = original

    def test_interval_hours_from_settings(self):
        scheduler = self._make_scheduler()
        assert isinstance(scheduler.interval_hours, int)
        assert scheduler.interval_hours > 0


class TestMarketDataPlan:
    """MarketDataRefreshScheduler.plan() queries financial_repo for active companies."""

    def _make_scheduler(self, repo=None, **kwargs):
        if repo is None:
            repo = AsyncMock()
            repo.get_active_companies_for_market_data.return_value = []
        return _import_and_construct(
            "application.schedulers.market_data_scheduler",
            "MarketDataRefreshScheduler",
            financial_repo=repo,
            defeat_beta_provider=MagicMock(),
            **kwargs,
        )

    async def test_plan_returns_jobs_for_each_company(self):
        repo = AsyncMock()
        repo.get_active_companies_for_market_data.return_value = [
            {"company_id": 1, "ticker_symbol": "AAPL", "security_type": "stock", "exchange": "NASDAQ"},
        ]
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_type"] == "company_refresh"
        assert job["dedupe_key"] == "company_refresh:1:market_data"
        assert job["resource_type"] == "company"
        assert job["payload"]["company_id"] == 1
        assert job["payload"]["ticker_symbol"] == "AAPL"
        assert "market_data" in job["payload"]["scopes"]
        assert job["priority"] == 30

    async def test_plan_handles_db_failure(self):
        repo = AsyncMock()
        repo.get_active_companies_for_market_data.side_effect = Exception("DB timeout")
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert jobs == []

    async def test_plan_handles_empty_companies(self):
        repo = AsyncMock()
        repo.get_active_companies_for_market_data.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert jobs == []

    async def test_plan_handles_none_companies(self):
        repo = AsyncMock()
        repo.get_active_companies_for_market_data.return_value = None
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert jobs == []

    def test_interval_hours_from_settings(self):
        scheduler = self._make_scheduler()
        assert isinstance(scheduler.interval_hours, int)
        assert scheduler.interval_hours > 0


class TestEarningsPlan:
    """EarningsRefreshScheduler.plan() queries financial_repo for upcoming earnings."""

    def _make_scheduler(self, repo=None, **kwargs):
        if repo is None:
            repo = AsyncMock()
            repo.get_companies_with_upcoming_earnings.return_value = []
        return _import_and_construct(
            "application.schedulers.earnings_scheduler",
            "EarningsRefreshScheduler",
            financial_repo=repo,
            defeat_beta_provider=MagicMock(),
            **kwargs,
        )

    async def test_plan_returns_jobs_with_financials_scope(self):
        repo = AsyncMock()
        repo.get_companies_with_upcoming_earnings.return_value = [
            {"company_id": 10, "ticker_symbol": "TSLA", "next_earnings_date": "2026-07-20"},
        ]
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_type"] == "company_refresh"
        assert job["dedupe_key"] == "company_refresh:10:financials"
        assert "financials" in job["payload"]["scopes"]
        assert job["payload"]["earnings_date"] == "2026-07-20"
        assert job["priority"] == 40

    async def test_plan_handles_db_failure(self):
        repo = AsyncMock()
        repo.get_companies_with_upcoming_earnings.side_effect = Exception("DB timeout")
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert jobs == []

    async def test_plan_handles_empty_companies(self):
        repo = AsyncMock()
        repo.get_companies_with_upcoming_earnings.return_value = []
        scheduler = self._make_scheduler(repo)
        jobs = await scheduler.plan()
        assert jobs == []


class TestAggregationPlan:
    """AggregationScheduler.plan() has no DB or provider dependencies."""

    def _make_scheduler(self):
        from application.schedulers.aggregation_scheduler import AggregationScheduler
        return AggregationScheduler()

    async def test_plan_returns_single_job(self):
        scheduler = self._make_scheduler()
        jobs = await scheduler.plan()
        assert len(jobs) == 1
        job = jobs[0]
        assert job["job_type"] == "aggregation_refresh"
        assert job["dedupe_key"] == "aggregation_refresh:sector"
        assert job["resource_type"] == "system"
        assert job["payload"]["group_type"] == "sector"
        assert job["priority"] == 10

    async def test_plan_always_succeeds_no_deps(self):
        scheduler = self._make_scheduler()
        for _ in range(5):
            jobs = await scheduler.plan()
            assert len(jobs) == 1

    def test_interval_hours_default(self):
        scheduler = self._make_scheduler()
        assert scheduler.interval_hours == 24


# ---------------------------------------------------------------------------
# Helper: import a scheduler class and construct it with given kwargs,
# patching any heavy provider imports that would be triggered by __init__.
# ---------------------------------------------------------------------------

def _import_and_construct(module_path, class_name, **kwargs):
    with (
        patch("infrastructure.repositories.financial_repository.SupabaseFinancialRepository"),
        patch("providers.defeat_beta_provider.DefeatBetaProvider"),
        patch("providers.yfinance_provider.YFinanceProvider"),
        patch("providers.stockdex_provider.StockdexMacrotrendsProvider"),
        patch("providers.edgar_provider.EdgarToolsProvider"),
    ):
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls(**kwargs)
