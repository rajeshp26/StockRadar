#!/usr/bin/env python3
"""
StockerPro Background Worker Process (v3 — DB-backed Job Queue)
================================================================

Architecture
------------
- SchedulerPlanner:  polls each scheduler's plan() and enqueues jobs
- JobEngine + WorkerPool: claims and executes jobs concurrently
- Janitor: reclaims expired leases, prunes old records

Backward Compatibility
----------------------
The v2 scheduler objects (SuperInvestorsRefreshScheduler, etc.) still exist
with their start()/stop() methods.  In v3 mode they are instantiated only for
their plan() method and data-fetching logic; the planner loop replaces their
inline sleep loops.

Usage
-----
    python scheduler_worker.py

Deployment
----------
    - systemd: See systemd/stockerpro-worker.service
    - Docker:  See docker-compose.yml worker service
"""

import asyncio
import logging
import os
import signal
import sys
from datetime import date
from typing import Any

# v3 infrastructure
from application.jobs.job_engine import JobEngine
from application.jobs.portfolio_snapshot_job import handle_portfolio_snapshot
from application.jobs.price_ingestion_job import handle_price_ingestion
from application.schedulers.aggregation_scheduler import AggregationScheduler
from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
from application.schedulers.freshness_monitor_scheduler import FreshnessMonitorScheduler, SNAPSHOT_INTERVAL_HOURS
from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
from application.schedulers.planner import SchedulerPlanner
from application.schedulers.portfolio_snapshot_scheduler import PortfolioSnapshotScheduler
from application.schedulers.price_ingestion_scheduler import PriceIngestionScheduler
from application.schedulers.reconciliation_scheduler import ReconciliationScheduler

# v2 scheduler classes (used for plan() + data logic)
from application.schedulers.super_investors_scheduler import SuperInvestorsRefreshScheduler
from application.schedulers.valuation_computation_scheduler import ValuationComputationScheduler
from application.services.super_investors_cache import invalidate_super_investors_cache

# Config
from config import settings
from infrastructure.repositories.scheduler_repository import SchedulerRepository

# Providers & Repos
# Event projection handler
from services.event_projection_handler import EventProjectionHandler

logging.basicConfig(
    level=logging.INFO,
    format="%(name)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("stockerpro.worker")


# ============================================================================
# Graceful Shutdown
# ============================================================================

class GracefulShutdown:
    def __init__(self):
        self.shutdown_requested = False
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                signal.signal(sig, self.request_shutdown)
            except (ValueError, OSError):
                logger.warning("Cannot register handler for %s on this platform", signal.Signals(sig).name)
        logger.info("Shutdown handlers registered (SIGTERM, SIGINT)")

    def request_shutdown(self, signum, frame):
        sig_name = signal.Signals(signum).name
        logger.info("Shutdown signal received: %s", sig_name)
        self.shutdown_requested = True


# ============================================================================
# Job Handlers (the actual data-fetching work)
# ============================================================================

async def handle_company_refresh(job: dict[str, Any]) -> dict[str, Any]:
    """
    Handler for 'company_refresh' jobs.
    Runs all scopes in the payload's scopes list.
    """
    payload = job.get("payload", {})
    scopes = payload.get("scopes", ["market_data"])
    results = {}
    if "financials" in scopes:
        results["financials"] = await _handle_company_refresh_financials(job)
    if "market_data" in scopes:
        results["market_data"] = await _handle_company_refresh_market_data(job)
    return results


async def _handle_company_refresh_market_data(job: dict[str, Any]) -> dict[str, Any]:
    """Market data refresh for a single company (price, splits, forecasts, ratios)."""
    payload = job.get("payload", {})
    company_id = payload.get("company_id")
    symbol = payload.get("ticker_symbol")
    security_type = payload.get("security_type", "stock")
    exchange = payload.get("exchange")

    if not company_id or not symbol:
        raise ValueError(f"Missing company_id or ticker_symbol in job payload: {payload}")

    scheduler = MarketDataRefreshScheduler()
    detail = await scheduler._process_company(
        symbol=symbol,
        company_id=company_id,
        security_type=security_type,
        exchange=exchange,
    )
    return detail


async def _handle_company_refresh_financials(job: dict[str, Any]) -> dict[str, Any]:
    """Financial data refresh for a single company (IS/BS/CF, derived metrics)."""
    payload = job.get("payload", {})
    company_id = payload.get("company_id")
    symbol = payload.get("ticker_symbol")
    earnings_date = payload.get("earnings_date")

    if not company_id or not symbol:
        raise ValueError(f"Missing company_id or ticker_symbol in job payload: {payload}")

    if earnings_date and isinstance(earnings_date, str):
        try:
            earnings_date = date.fromisoformat(earnings_date)
        except ValueError:
            earnings_date = None

    scheduler = EarningsRefreshScheduler()
    from domain.exceptions import SchedulerRefreshError
    try:
        result = await scheduler._refresh_company_financials_optimized(
            company_id=company_id,
            symbol=symbol,
            earnings_date=earnings_date,
        )
        return result
    except SchedulerRefreshError as e:
        raise Exception(str(e)) from e


async def handle_investor_refresh(job: dict[str, Any]) -> dict[str, Any]:
    """Handler for 'investor_refresh' jobs — refresh a single super investor's portfolio."""
    payload = job.get("payload", {})
    cik = payload.get("cik")
    name = payload.get("name")

    if not cik:
        raise ValueError(f"Missing cik in investor_refresh payload: {payload}")

    scheduler = SuperInvestorsRefreshScheduler()
    info = {"name": name, "firm": payload.get("firm"), "tag": payload.get("tag")}
    result = await scheduler._refresh_single_investor(cik, info)
    if result:
        invalidate_super_investors_cache()
    return {"cik": cik, "status": "ok" if result else "skipped"}


async def handle_freshness_snapshot(job: dict[str, Any]) -> dict[str, Any]:
    """Handler for 'freshness_snapshot' jobs - measure + persist coverage snapshot."""
    payload = job.get("payload", {})
    as_of_value = payload.get("as_of")
    today = None
    if as_of_value:
        try:
            today = date.fromisoformat(as_of_value)
        except ValueError:
            today = None
    scheduler = FreshnessMonitorScheduler()
    result = await scheduler.snapshot(today=today)
    logger.info(
        "Freshness snapshot complete for %s: %s",
        result.get("as_of"),
        result.get("domains"),
    )
    return result

async def handle_aggregation_refresh(job: dict[str, Any]) -> dict[str, Any]:
    """Handler for 'aggregation_refresh' jobs — compute sector/industry percentile stats."""
    payload = job.get("payload", {})
    group_type = payload.get("group_type", "sector")
    min_sample_size = payload.get("min_sample_size", 5)

    from application.jobs.aggregation_jobs import compute_and_upsert_group_metric_stats
    result = await compute_and_upsert_group_metric_stats(
        group_type=group_type,
        min_sample_size=min_sample_size,
    )
    return result


async def handle_valuation_computation(job: dict[str, Any]) -> dict[str, Any]:
    """Handler for 'valuation_computation' jobs — pre-compute all valuation methods for a symbol."""
    payload = job.get("payload", {})
    symbol = payload.get("symbol")
    user_id = payload.get("user_id")
    force = payload.get("force", True)

    if not symbol:
        raise ValueError(f"Missing symbol in valuation_computation payload: {payload}")

    scheduler = ValuationComputationScheduler()
    result = await scheduler.compute_all(
        symbol=symbol,
        user_id=user_id,
        force=force,
    )
    return result


# ============================================================================
# Main
# ============================================================================

async def main():
    shutdown = GracefulShutdown()

    logger.info("=" * 60)
    logger.info("StockerPro Background Worker (v3)")
    logger.info("=" * 60)
    logger.info("Environment: %s", settings.ENVIRONMENT)
    logger.info("=" * 60)

    # ── Initialize components ──────────────────────────────────────────────

    # 1. Job Engine
    engine = JobEngine()
    engine.register_handler("company_refresh", handle_company_refresh)
    engine.register_handler("investor_refresh", handle_investor_refresh)
    engine.register_handler("aggregation_refresh", handle_aggregation_refresh)
    engine.register_handler("portfolio_snapshot", handle_portfolio_snapshot)
    engine.register_handler("price_ingestion", handle_price_ingestion)
    engine.register_handler("valuation_computation", handle_valuation_computation)
    engine.register_handler("freshness_snapshot", handle_freshness_snapshot)

    # 2. Planner
    planner = SchedulerPlanner()

    # ── Register Schedulers ────────────────────────────────────────────────

    # Super Investors (every 24h)
    if getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", True):
        si_scheduler = SuperInvestorsRefreshScheduler()
        planner.register(
            name="super_investors",
            plan_fn=si_scheduler.plan,
            interval_hours=si_scheduler.interval_hours,
            enabled=True,
        )
        logger.info("Registered super_investors planner (interval=%dh)", si_scheduler.interval_hours)
    else:
        logger.info("Super Investors scheduler disabled")

    # Market Data (every 24h)
    if getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", True):
        md_scheduler = MarketDataRefreshScheduler()
        planner.register(
            name="market_data",
            plan_fn=md_scheduler.plan,
            interval_hours=md_scheduler.interval_hours,
            enabled=True,
        )
        logger.info("Registered market_data planner (interval=%dh)", md_scheduler.interval_hours)
    else:
        logger.info("Market Data scheduler disabled")

    # Earnings (every 2h)
    if getattr(settings, "ENABLE_EARNINGS_SCHEDULER", False):
        ea_scheduler = EarningsRefreshScheduler()
        planner.register(
            name="earnings",
            plan_fn=ea_scheduler.plan,
            interval_hours=int(getattr(settings, "EARNINGS_REFRESH_CHECK_INTERVAL_HOURS", 2)),
            enabled=True,
        )
        logger.info("Registered earnings planner (interval=%dh)", settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS)
    else:
        logger.info("Earnings scheduler disabled")

    # Reconciliation (weekly gap detection)
    if getattr(settings, "ENABLE_RECONCILIATION_SCHEDULER", True):
        rec_scheduler = ReconciliationScheduler()
        planner.register(
            name="reconciliation",
            plan_fn=rec_scheduler.plan,
            interval_hours=int(getattr(settings, "RECONCILIATION_INTERVAL_HOURS", 168)),
            enabled=True,
        )
        logger.info(
            "Registered reconciliation planner (interval=%dh)",
            settings.RECONCILIATION_INTERVAL_HOURS,
        )
    else:
        logger.info("Reconciliation scheduler disabled")

    # Freshness Monitor (daily coverage snapshot)
    if getattr(settings, "ENABLE_FRESHNESS_MONITOR_SCHEDULER", True):
        fm_scheduler = FreshnessMonitorScheduler()
        planner.register(
            name="freshness_monitor",
            plan_fn=fm_scheduler.plan,
            interval_hours=SNAPSHOT_INTERVAL_HOURS,
            enabled=True,
        )
        logger.info("Registered freshness_monitor planner (interval=%dh)", SNAPSHOT_INTERVAL_HOURS)
    else:
        logger.info("Freshness Monitor scheduler disabled")
    # Portfolio Snapshots (daily at 23:00 UTC)
    if getattr(settings, "ENABLE_PORTFOLIO_SNAPSHOT_SCHEDULER", True):
        ps_scheduler = PortfolioSnapshotScheduler()
        planner.register(
            name="portfolio_snapshot",
            plan_fn=ps_scheduler.plan,
            interval_hours=ps_scheduler.interval_hours,
            enabled=True,
        )
        logger.info("Registered portfolio_snapshot planner (interval=%dh)", ps_scheduler.interval_hours)
    else:
        logger.info("Portfolio Snapshot scheduler disabled")

    # Aggregation (every 24h)
    if getattr(settings, "ENABLE_AGGREGATION_SCHEDULER", True):
        agg_scheduler = AggregationScheduler()
        planner.register(
            name="aggregation",
            plan_fn=agg_scheduler.plan,
            interval_hours=agg_scheduler.interval_hours,
            enabled=True,
        )
        logger.info("Registered aggregation planner (interval=%dh)", agg_scheduler.interval_hours)
    else:
        logger.info("Aggregation scheduler disabled")

    # Price Ingestion (market-hours-aware, every 5-30 min)
    if getattr(settings, "ENABLE_PRICE_INGESTION_SCHEDULER", True):
        pi_scheduler = PriceIngestionScheduler()
        planner.register(
            name="price_ingestion",
            plan_fn=pi_scheduler.plan,
            interval_minutes=1,
            enabled=True,
        )
        logger.info("Registered price_ingestion planner (market-hours-aware)")
    else:
        logger.info("Price Ingestion scheduler disabled")

    # Valuation Computation (every 24h)
    if getattr(settings, "ENABLE_VALUATION_SCHEDULER", True):
        vc_scheduler = ValuationComputationScheduler()
        planner.register(
            name="valuation_computation",
            plan_fn=vc_scheduler.plan,
            interval_hours=vc_scheduler.interval_hours,
            enabled=True,
        )
        logger.info(
            "Registered valuation_computation planner (interval=%dh)",
            vc_scheduler.interval_hours,
        )
    else:
        logger.info("Valuation Computation scheduler disabled")

    # ── Launch all loops ───────────────────────────────────────────────────

    worker_pool_task = asyncio.create_task(
        engine.run_worker_pool(concurrency=5),
        name="worker_pool",
    )
    planner_task = asyncio.create_task(
        planner.run_planner_loop(),
        name="planner",
    )
    janitor_task = asyncio.create_task(
        planner.run_janitor_loop(),
        name="janitor",
    )
    projection_task = asyncio.create_task(
        EventProjectionHandler().start_polling(interval_ms=1000),
        name="event_projection",
    )

    logger.info("=" * 60)
    logger.info("Worker running — planner + 5 workers + janitor + event projection")
    logger.info("=" * 60)

    # ── Heartbeat loop ─────────────────────────────────────────────────────
    repo = SchedulerRepository()
    async def heartbeat_loop():
        hostname = os.uname().nodename if hasattr(os, 'uname') else 'unknown'
        pid = os.getpid()
        while not shutdown.shutdown_requested:
            repo.record_heartbeat(
                worker_id=engine.get_worker_id(),
                hostname=hostname,
                pid=pid,
                active_jobs=5,
            )
            await asyncio.sleep(60)

    heartbeat_task = asyncio.create_task(heartbeat_loop(), name="heartbeat")

    # ── Wait for shutdown ──────────────────────────────────────────────────
    try:
        while not shutdown.shutdown_requested:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

    # ── Graceful Shutdown ──────────────────────────────────────────────────
    logger.info("Shutting down...")

    # 1. Stop planner (no more enqueueing)
    planner_task.cancel()
    janitor_task.cancel()
    projection_task.cancel()

    # 2. Stop heartbeat
    heartbeat_task.cancel()

    # 3. Stop worker pool (no new claims)
    worker_pool_task.cancel()

    await asyncio.gather(
        planner_task,
        janitor_task,
        projection_task,
        heartbeat_task,
        worker_pool_task,
        return_exceptions=True,
    )

    # 4. Release leases on all jobs claimed by this worker
    released = repo.release_worker_leases(engine.get_worker_id())
    if released > 0:
        logger.info("Released %d leases during shutdown", released)

    # 5. Final heartbeat marking stopped
    repo.record_heartbeat(
        worker_id=engine.get_worker_id(),
        hostname="shutdown",
        pid=0,
        active_jobs=0,
    )

    logger.info("=" * 60)
    logger.info("Worker shutdown complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error("Worker process crashed: %s", e, exc_info=True)
        sys.exit(1)
