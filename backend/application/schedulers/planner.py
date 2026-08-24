"""Planner Loop — Periodically checks each scheduler and enqueues jobs."""

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from infrastructure.repositories.scheduler_repository import SchedulerRepository
from shared.time_utils import now_utc, parse_db_timestamp

logger = logging.getLogger(__name__)

PlanFunction = Callable[[], Coroutine[Any, Any, list[dict[str, Any]]]]

PLAN_TIMEOUT_SECONDS = 300  # 5 minutes max for a plan() call


def to_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class SchedulerPlanner:
    def __init__(self, scheduler_repo: SchedulerRepository | None = None):
        self._repo = scheduler_repo or SchedulerRepository()
        self._schedulers: dict[str, dict[str, Any]] = {}
        self._planner_interval = 60
        self._plan_timeout = PLAN_TIMEOUT_SECONDS

    def register(
        self,
        name: str,
        plan_fn: PlanFunction,
        interval_hours: float | None = None,
        interval_minutes: float | None = None,
        enabled: bool = True,
    ) -> None:
        if interval_hours is None and interval_minutes is None:
            raise ValueError("Either interval_hours or interval_minutes is required")
        if interval_hours is not None and interval_minutes is not None:
            raise ValueError("Only one of interval_hours or interval_minutes should be provided")

        if interval_minutes is not None:
            interval_hours = interval_minutes / 60.0

        self._schedulers[name] = {
            "name": name,
            "plan_fn": plan_fn,
            "interval_hours": interval_hours,
            "enabled": enabled,
        }

        if interval_hours >= 1:
            logger.info(
                "[PLANNER] Registered scheduler '%s' (interval=%dh, enabled=%s)",
                name, int(interval_hours), enabled,
            )
        else:
            logger.info(
                "[PLANNER] Registered scheduler '%s' (interval=%.0fmin, enabled=%s)",
                name, interval_hours * 60, enabled,
            )

    async def run_planner_loop(self) -> None:
        logger.info("[PLANNER] Starting planner loop (check interval=%ds)", self._planner_interval)
        try:
            while True:
                await self._check_and_plan()
                await asyncio.sleep(self._planner_interval)
        except asyncio.CancelledError:
            logger.info("[PLANNER] Planner loop stopped")

    async def _check_and_plan(self) -> None:
        now = now_utc()

        for name, config in self._schedulers.items():
            if not config["enabled"]:
                continue

            try:
                state = self._repo.get_scheduler_state(name)
                next_due = None
                if state and state.get("next_due_at"):
                    try:
                        next_due = parse_db_timestamp(state["next_due_at"])
                    except (ValueError, TypeError):
                        next_due = None

                if next_due is not None:
                    next_due = to_utc(next_due)
                    if now < next_due:
                        continue

                plan_start = time.monotonic()
                jobs = await asyncio.wait_for(
                    config["plan_fn"](),
                    timeout=self._plan_timeout,
                )
                duration_ms = int((time.monotonic() - plan_start) * 1000)

                enqueued = 0
                for job in jobs:
                    if self._repo.enqueue_job(**job):
                        enqueued += 1

                next_due_at = (now + timedelta(hours=config["interval_hours"])).isoformat()
                self._repo.upsert_scheduler_state({
                    "scheduler_name": name,
                    "last_planned_at": now.isoformat(),
                    "last_status": "succeeded",
                    "last_error": None,
                    "next_due_at": next_due_at,
                    "interval_hours": config["interval_hours"],
                    "enabled": config["enabled"],
                })

                self._repo.record_planner_run(
                    scheduler_name=name,
                    jobs_enqueued=enqueued,
                    status="succeeded",
                    duration_ms=duration_ms,
                )

                if enqueued > 0:
                    logger.info("[PLANNER] %s: planned %d jobs in %dms", name, enqueued, duration_ms)

            except Exception as e:
                logger.error("[PLANNER] Failed to plan scheduler '%s': %s", name, e, exc_info=True)
                self._repo.update_scheduler_state(name, {
                    "last_status": "failed",
                    "last_error": str(e)[:500],
                })
                self._repo.record_planner_run(
                    scheduler_name=name,
                    jobs_enqueued=0,
                    status="failed",
                    error=str(e)[:500],
                )

    async def run_janitor_loop(self) -> None:
        logger.info("[JANITOR] Starting janitor loop (interval=5min)")
        try:
            while True:
                await asyncio.sleep(300)
                await self._janitor_cycle()
        except asyncio.CancelledError:
            logger.info("[JANITOR] Janitor loop stopped")

    async def _janitor_cycle(self) -> None:
        try:
            reclaimed = self._repo.reclaim_expired_leases()
            if reclaimed > 0:
                logger.info("[JANITOR] Reclaimed %d expired job leases", reclaimed)

            pruned = self._repo.prune_old_records()
            total_pruned = sum(pruned.values())
            if total_pruned > 0:
                logger.debug("[JANITOR] Pruned records: %s", pruned)

            zombie_count = self._repo.prune_zombie_heartbeats()
            if zombie_count > 0:
                logger.info("[JANITOR] Pruned %d zombie heartbeats (hostname=shutdown)", zombie_count)

            expired_locks = self._repo.release_expired_scheduler_locks()
            if expired_locks > 0:
                logger.info("[JANITOR] Released %d expired scheduler locks", expired_locks)

        except Exception as e:
            logger.error("[JANITOR] Cycle failed: %s", e, exc_info=True)
