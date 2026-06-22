# -*- coding: utf-8 -*-
"""
Aggregation Scheduler
Runs every 24 hours to compute sector/industry percentile stats for
valuation metrics. Uses distributed lock via `aggregation_state` table to
prevent concurrent runs across replicas.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from shared.time_utils import parse_db_timestamp

from config import settings
from database import supabase
from application.jobs.aggregation_jobs import compute_and_upsert_group_metric_stats

logger = logging.getLogger(__name__)


class AggregationScheduler:
    """Background scheduler for group-level metric aggregation.

    Runs every N hours (default: 24) to compute percentile stats for each
    valuation metric across sectors. Uses a distributed lock via the
    `aggregation_state` table to prevent concurrent runs.
    """

    def __init__(self, interval_hours: int = 24):
        self.interval_hours: int = int(
            getattr(settings, "AGGREGATION_REFRESH_INTERVAL_HOURS", interval_hours)
        )
        self.is_running = False
        self.task: Optional[asyncio.Task] = None
        self.lock_id: str = f"agg:{uuid.uuid4()}"

    async def plan(self) -> list:
        """
        v3 planner integration — returns a single aggregation_refresh job.

        Returns list of dicts, each suitable for SchedulerRepository.enqueue_job:
            job_type: 'aggregation_refresh'
            dedupe_key: 'aggregation_refresh:sector'
            resource_type: 'system'
            resource_id: 'sector_metric_agg'
            payload: { group_type: 'sector', min_sample_size: 5 }
            priority: 10
        """
        return [{
            "job_type": "aggregation_refresh",
            "dedupe_key": "aggregation_refresh:sector",
            "resource_type": "system",
            "resource_id": "sector_metric_agg",
            "payload": {"group_type": "sector", "min_sample_size": 5},
            "priority": 10,
            "max_attempts": 3,
        }]

    async def start(self) -> None:
        """Start the scheduler background task."""
        if self.is_running:
            logger.warning("AggregationScheduler already running")
            return

        self.is_running = True
        self.task = asyncio.create_task(self._run_scheduler_loop())
        logger.info(
            "🚀 AggregationScheduler started (interval: %sh)",
            self.interval_hours,
        )

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("⏹️  AggregationScheduler stopped")

    async def _run_scheduler_loop(self) -> None:
        """Main loop: run aggregation, then sleep for interval_hours."""
        while self.is_running:
            try:
                await self._try_acquire_and_run()
            except Exception as e:
                logger.error(
                    "Aggregation cycle failed: %s", e, exc_info=True,
                )

            sleep_seconds = self.interval_hours * 3600
            logger.debug(
                "AggregationScheduler sleeping for %dh...", self.interval_hours,
            )
            try:
                await asyncio.sleep(sleep_seconds)
            except asyncio.CancelledError:
                break

    async def _try_acquire_and_run(self) -> Dict[str, Any]:
        """Try to acquire the distributed lock; if successful, run aggregation.

        Lock logic:
        - If no row exists, insert with lock_owner.
        - If is_running is True and lock hasn't expired, skip.
        - If lock has expired, take over.
        """
        agg_id = "sector_metric_agg"
        now = datetime.now(timezone.utc)
        lock_ttl = timedelta(hours=2)

        try:
            resp = (
                supabase.table("aggregation_state")
                .select("*")
                .eq("aggregation_id", agg_id)
                .execute()
            )
            rows = resp.data or []
        except Exception as e:
            logger.error("Failed to check aggregation state: %s", e)
            return {"acquired": False, "error": str(e)}

        acquired = False

        if not rows:
            # No row exists — insert and acquire
            try:
                supabase.table("aggregation_state").insert(
                    {
                        "aggregation_id": agg_id,
                        "is_running": True,
                        "last_started_at": now.isoformat(),
                        "lock_owner": self.lock_id,
                        "lock_expires_at": (now + lock_ttl).isoformat(),
                    },
                ).execute()
                acquired = True
                logger.info("Lock acquired (new row): %s", self.lock_id)
            except Exception as e:
                logger.error("Failed to insert aggregation lock: %s", e)
                return {"acquired": False, "error": str(e)}
        else:
            state = rows[0]
            is_running = state.get("is_running", False)
            expires_at = state.get("lock_expires_at")
            owner = state.get("lock_owner")
            expires = (
                parse_db_timestamp(expires_at)
                if expires_at and isinstance(expires_at, str)
                else None
            )

            if is_running and expires and expires > now:
                logger.info(
                    "Lock held by %s (expires %s) — skipping",
                    owner, expires_at,
                )
                return {"acquired": False, "reason": "lock_held"}

            # Lock is stale or not held — take over
            try:
                supabase.table("aggregation_state").update(
                    {
                        "is_running": True,
                        "last_started_at": now.isoformat(),
                        "lock_owner": self.lock_id,
                        "lock_expires_at": (now + lock_ttl).isoformat(),
                    }
                ).eq("aggregation_id", agg_id).execute()
                acquired = True
                logger.info(
                    "Lock acquired (stale/expired, previous owner=%s): %s",
                    owner, self.lock_id,
                )
            except Exception as e:
                logger.error("Failed to update aggregation lock: %s", e)
                return {"acquired": False, "error": str(e)}

        if not acquired:
            return {"acquired": False}

        # Run the computation
        try:
            result = await compute_and_upsert_group_metric_stats(
                group_type="sector",
                min_sample_size=5,
            )
            logger.info(
                "[AGG] Cycle complete: %d groups, %d rows written",
                result.get("groups_found", 0),
                result.get("rows_written", 0),
            )
            return {"acquired": True, **result}
        except Exception as e:
            logger.error("Aggregation computation failed: %s", e, exc_info=True)
            raise
        finally:
            # Release lock regardless
            try:
                now_release = datetime.now(timezone.utc)
                supabase.table("aggregation_state").update(
                    {
                        "is_running": False,
                        "last_completed_at": now_release.isoformat(),
                        "lock_owner": None,
                        "lock_expires_at": None,
                    }
                ).eq("aggregation_id", agg_id).execute()
                logger.debug("Lock released: %s", self.lock_id)
            except Exception as e:
                logger.error("Failed to release aggregation lock: %s", e)

    async def trigger_immediate_run(self) -> Dict[str, Any]:
        """Manual trigger for testing / admin."""
        logger.info("🔄 Manual trigger: immediate aggregation run")
        return await self._try_acquire_and_run()
