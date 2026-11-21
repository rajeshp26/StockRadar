"""
Valuation Computation Scheduler
Runs on-demand when stocks are added to watchlists or via scheduled refresh.
Pre-computes all 5 valuation methods for a given symbol.

Deduplication:
- In-memory in-flight set prevents concurrent duplicate computations for the same symbol.
- RecomputeGuard (3-gate freshness check) prevents recomputation when data is fresh.
- force=False by default so the guard decides based on data staleness.

v3 Planner integration:
- plan() enumerates every active company (in any user's watchlist or portfolio)
  and returns valuation_computation job dicts for the SchedulerPlanner to enqueue.
- Applicability pre-checks skip methods that can never produce a meaningful
  result for a company (rule1 with non-positive EPS, DDM without dividends),
  so the job queue is not flooded with doomed computations.
"""

import asyncio
import logging
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from application.services.valuation_service import ValuationService
    from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

VALUATION_METHODS = [
    "rule1",
    "dcf",
    "ddm_gordon",
    "owner_earnings",
    "residual_income",
]


class ValuationComputationScheduler:
    _in_flight: ClassVar[set[str]] = set()

    def __init__(self):
        self.is_running = False
        self.task: asyncio.Task | None = None

    @property
    def interval_hours(self) -> int:
        from config import settings
        return int(getattr(settings, "VALUATION_REFRESH_INTERVAL_HOURS", 24))

    # -------------------------------------------------------------------------
    # v3 Planner Integration
    # -------------------------------------------------------------------------

    async def plan(self) -> list[dict[str, Any]]:
        """
        v3 planner integration — returns valuation_computation job dicts for
        every active company (in any user's watchlist or portfolio).

        Handler (registered in scheduler_worker.py):
          - 'valuation_computation' runs compute_all() → all 5 methods for the
            symbol. force=False so the RecomputeGuard decides on staleness.

        Returns list of dicts, each suitable for SchedulerRepository.enqueue_job:
            job_type: 'valuation_computation'
            dedupe_key: 'valuation_computation:{symbol}'
            resource_type: 'company'
            resource_id: company_id (as str)
            payload: { symbol, user_id, force }
            priority: 20 (background pre-compute, below market data @30 / price @40)
        """
        from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
        from shared.constants import get_effective_skipped_symbols
        try:
            financial_repo = SupabaseFinancialRepository()
            companies = await financial_repo.get_active_companies_for_market_data()
        except Exception as e:
            logger.error("plan() failed to enumerate active companies: %s", e)
            companies = []

        # I24: apply the same shared delisted/renamed-symbol filter the
        # market-data planner and the price-ingestion job use. Previously this
        # planner was the one consumer missing from that single source of truth,
        # so it enqueued jobs for dead tickers (the 172-vs-166 market_data gap).
        before = len(companies or [])
        skipped = get_effective_skipped_symbols()
        companies = [
            c for c in (companies or [])
            if (c.get("ticker_symbol") or "").upper() not in skipped
        ]
        if len(companies) < before:
            logger.debug(
                "[VALUATION] plan skipped %d delisted/renamed symbol(s)",
                before - len(companies),
            )

        jobs = []
        for c in companies or []:
            symbol = c.get("ticker_symbol")
            company_id = c.get("company_id")
            if not symbol:
                continue
            jobs.append({
                "job_type": "valuation_computation",
                "dedupe_key": f"valuation_computation:{symbol}",
                "resource_type": "company",
                "resource_id": str(company_id or ""),
                "payload": {
                    "symbol": symbol,
                    "user_id": None,
                    "force": False,
                },
                "priority": 20,
                "max_attempts": 3,
            })
        return jobs

    async def compute_all(
        self,
        symbol: str,
        user_id: int | None = None,
        force: bool = False,
    ) -> dict[str, Any]:

        symbol = symbol.upper()

        if symbol in self._in_flight:
            logger.info("Skipping %s — already computing", symbol)
            return {m: {"status": "skipped", "reason": "already_in_flight"} for m in VALUATION_METHODS}

        self._in_flight.add(symbol)
        try:
            return await self._run_all(symbol, user_id, force)
        finally:
            self._in_flight.discard(symbol)

    async def _run_all(
        self,
        symbol: str,
        user_id: int | None,
        force: bool,
    ) -> dict[str, Any]:
        from application.services.recompute_guard import RecomputeGuard
        from application.services.valuation_service import ValuationService
        from infrastructure.repositories.valuation_repository import ValuationRepository

        results: dict[str, Any] = {}
        repo = ValuationRepository()
        guard = RecomputeGuard(repo)
        service = ValuationService(repo=repo, guard=guard)

        context = await repo.get_company_context(symbol)
        company_id = (context or {}).get("company_id")

        for method in VALUATION_METHODS:
            skip_reason = await self._applicability_skip(repo, company_id, method)
            if skip_reason:
                logger.info(
                    "Skipping %s/%s — not applicable (%s)", symbol, method, skip_reason
                )
                results[method] = {
                    "status": "skipped",
                    "symbol": symbol,
                    "reason": skip_reason,
                }
                continue
            try:
                await self._compute_method(service, method, symbol, user_id, force)
                results[method] = {"status": "computed", "symbol": symbol}
            except Exception as e:
                logger.error("Valuation failed for %s/%s: %s", symbol, method, e, exc_info=True)
                results[method] = {"status": "error", "symbol": symbol, "error": str(e)}

        computed = sum(1 for r in results.values() if r["status"] == "computed")
        skipped = sum(1 for r in results.values() if r["status"] == "skipped")
        errors = sum(1 for r in results.values() if r["status"] == "error")
        logger.info(
            "Valuation for %s: %d computed, %d skipped, %d errors",
            symbol, computed, skipped, errors,
        )
        return results

    @staticmethod
    async def _applicability_skip(
        repo: "ValuationRepository",
        company_id: int | None,
        method: str,
    ) -> str | None:
        """
        Cheap DB pre-checks that skip methods which can never produce a
        meaningful result for this company. Returns a reason code, or None
        when the method should be attempted.
        """
        if company_id is None:
            return None

        try:
            if method == "rule1":
                eps_row = await repo.get_trailing_eps(company_id)
                eps = (eps_row or {}).get("trailing_eps")
                if eps is not None and eps <= 0:
                    return "NEGATIVE_EPS"
            elif method == "ddm_gordon":
                dps = await repo.get_dividend_ttm_dps(company_id)
                if dps is None or dps <= 0:
                    return "NO_DIVIDEND_HISTORY"
        except Exception as e:
            logger.debug("Applicability pre-check failed for %s/%s: %s", company_id, method, e)
        return None


    async def _compute_method(
        self,
        service: "ValuationService",
        method: str,
        symbol: str,
        user_id: int | None,
        force: bool,
    ) -> Any:
        if method == "rule1":
            return await service.compute_rule1_if_stale(symbol=symbol, user_id=user_id, force=force)
        elif method == "dcf":
            return await service.compute_dcf_if_stale(symbol=symbol, user_id=user_id, force=force)
        elif method == "ddm_gordon":
            return await service.compute_ddm_if_stale(symbol=symbol, user_id=user_id, variant="gordon", force=force)
        elif method == "owner_earnings":
            return await service.compute_owner_earnings_if_stale(symbol=symbol, user_id=user_id, force=force)
        elif method == "residual_income":
            return await service.compute_residual_income_if_stale(symbol=symbol, user_id=user_id, force=force)
        else:
            raise ValueError(f"Unknown valuation method: {method}")

    async def compute_batch(
        self,
        symbols: list[str],
        user_id: int | None = None,
        force: bool = False,
        max_concurrent: int = 3,
    ) -> dict[str, dict[str, Any]]:
        semaphore = asyncio.Semaphore(max_concurrent)
        all_results: dict[str, dict[str, Any]] = {}

        async def _compute_with_semaphore(sym: str):
            async with semaphore:
                return sym, await self.compute_all(sym, user_id=user_id, force=force)

        tasks = [_compute_with_semaphore(sym) for sym in symbols]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for result in completed:
            if isinstance(result, Exception):
                logger.error("Batch computation failed: %s", result)
            else:
                sym, res = result
                all_results[sym] = res

        return all_results
