#!/usr/bin/env python3
"""
StockerPro Background Worker Process
Runs all schedulers independently from FastAPI.

This process handles:
- Super Investors refresh (every 24 hours)
- Market Data refresh (every 24 hours)  
- Earnings refresh (every 2 hours)

Usage:
    python scheduler_worker.py

Deployment:
    - systemd: See systemd/stockerpro-worker.service
    - Docker: See docker-compose.yml worker service
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from typing import Dict, Any, Optional

# Import schedulers
from application.schedulers.super_investors_scheduler import SuperInvestorsRefreshScheduler
from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler
from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
from application.schedulers.aggregation_scheduler import AggregationScheduler

# Import config
from config import settings

# ============================================================================
# Logging Setup
# ============================================================================

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("stockerpro.worker")

# ============================================================================
# Graceful Shutdown Handler
# ============================================================================

class GracefulShutdown:
    """
    Handles SIGTERM/SIGINT for clean scheduler shutdown.
    Allows in-progress tasks to complete before exit.
    """
    def __init__(self):
        self.shutdown_requested = False
        signal.signal(signal.SIGTERM, self.request_shutdown)
        signal.signal(signal.SIGINT, self.request_shutdown)
        logger.info("Shutdown handlers registered (SIGTERM, SIGINT)")
    
    def request_shutdown(self, signum, frame):
        """Signal handler - sets flag for graceful shutdown"""
        sig_name = signal.Signals(signum).name
        logger.info(f"📥 Shutdown signal received: {sig_name}")
        self.shutdown_requested = True

# ============================================================================
# Main Worker Process
# ============================================================================

async def main():
    """
    Initialize and run all schedulers.
    
    Architecture:
    - Each scheduler is a separate async task
    - All run in same event loop (no blocking between them)
    - Distributed locks prevent conflicts with other workers
    - Graceful shutdown waits for current cycles to complete
    """
    shutdown = GracefulShutdown()
    
    logger.info("=" * 60)
    logger.info("🚀 StockerPro Background Worker Starting")
    logger.info("=" * 60)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Log Level: {settings.LOG_LEVEL}")
    logger.info(f"Supabase URL: {settings.SUPABASE_URL}")
    logger.info("=" * 60)
    
    # Initialize schedulers
    schedulers: Dict[str, Any] = {}
    scheduler_tasks: Dict[str, asyncio.Task] = {}
    
    # ── Super Investors Scheduler ────────────────────────────────────────
    if getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", True):
        try:
            logger.info("Initializing Super Investors scheduler...")
            schedulers["super_investors"] = SuperInvestorsRefreshScheduler()
            await schedulers["super_investors"].start()
            logger.info(
                f"✅ Super Investors scheduler started "
                f"(interval: {schedulers['super_investors'].interval_hours}h)"
            )
        except Exception as e:
            logger.error(f"❌ Failed to start Super Investors scheduler: {e}", exc_info=True)
            sys.exit(1)
    else:
        logger.info("⏭️  Super Investors scheduler disabled (ENABLE_SUPER_INVESTORS_SCHEDULER=false)")
    
    # ── Market Data Scheduler ─────────────────────────────────────────────
    if getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", True):
        try:
            logger.info("Initializing Market Data scheduler...")
            schedulers["market_data"] = MarketDataRefreshScheduler()
            await schedulers["market_data"].start()
            logger.info(
                f"✅ Market Data scheduler started "
                f"(interval: {schedulers['market_data'].interval_hours}h)"
            )
        except Exception as e:
            logger.error(f"❌ Failed to start Market Data scheduler: {e}", exc_info=True)
            sys.exit(1)
    else:
        logger.info("⏭️  Market Data scheduler disabled (ENABLE_MARKET_DATA_SCHEDULER=false)")
    
    # ── Earnings Scheduler ────────────────────────────────────────────────
    if getattr(settings, "ENABLE_EARNINGS_SCHEDULER", False):
        try:
            logger.info("Initializing Earnings scheduler...")
            schedulers["earnings"] = EarningsRefreshScheduler()
            await schedulers["earnings"].start()
            logger.info(
                f"✅ Earnings scheduler started "
                f"(interval: {settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS}h)"
            )
        except Exception as e:
            logger.error(f"❌ Failed to start Earnings scheduler: {e}", exc_info=True)
            sys.exit(1)
    else:
        logger.info("⏭️  Earnings scheduler disabled (ENABLE_EARNINGS_SCHEDULER=false)")
    
    # ── Aggregation Scheduler ─────────────────────────────────────────────
    if getattr(settings, "ENABLE_AGGREGATION_SCHEDULER", True):
        try:
            logger.info("Initializing Aggregation scheduler...")
            schedulers["aggregation"] = AggregationScheduler()
            await schedulers["aggregation"].start()
            logger.info(
                f"✅ Aggregation scheduler started "
                f"(interval: {schedulers['aggregation'].interval_hours}h)"
            )
        except Exception as e:
            logger.error(f"❌ Failed to start Aggregation scheduler: {e}", exc_info=True)
            sys.exit(1)
    else:
        logger.info("⏭️  Aggregation scheduler disabled (ENABLE_AGGREGATION_SCHEDULER=false)")

    # ── Validation ─────────────────────────────────────────────────────────
    if not schedulers:
        logger.error("❌ No schedulers enabled. Check config settings.")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info(f"✅ Worker process running with {len(schedulers)} active schedulers")
    logger.info("=" * 60)
    
    # ── Keep Running Until Shutdown ───────────────────────────────────────
    try:
        while not shutdown.shutdown_requested:
            # Heartbeat every 60 seconds
            await asyncio.sleep(60)
            
            # Optional: Log scheduler status
            if logger.isEnabledFor(logging.DEBUG):
                for name, sched in schedulers.items():
                    is_running = getattr(sched, "is_running", None) or getattr(sched, "_is_running", None)
                    next_run = getattr(sched, "next_run_at", None)
                    logger.debug(
                        f"[{name}] running={is_running}, next_run={next_run}"
                    )
    
    except KeyboardInterrupt:
        logger.info("⌨️  Keyboard interrupt received")
    
    # ── Graceful Shutdown ──────────────────────────────────────────────────
    logger.info("🛑 Initiating graceful shutdown...")
    
    for name, scheduler in schedulers.items():
        try:
            logger.info(f"Stopping {name} scheduler...")
            await scheduler.stop()
            logger.info(f"✅ {name} scheduler stopped")
        except Exception as e:
            logger.error(f"⚠️  Error stopping {name} scheduler: {e}", exc_info=True)
    
    logger.info("=" * 60)
    logger.info("✅ Worker process shutdown complete")
    logger.info("=" * 60)

# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"💥 Worker process crashed: {e}", exc_info=True)
        sys.exit(1)