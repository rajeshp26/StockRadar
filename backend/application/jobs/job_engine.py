"""
Job Engine
Core runtime for the DB-backed job queue:
- Atomic job claiming with leases
- Execution dispatch to handler functions
- Lease renewal for long-running jobs
- Retry with classification-based backoff
- Dead letter handling
"""

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from infrastructure.repositories.scheduler_repository import SchedulerRepository
from shared import debug_trace

logger = logging.getLogger(__name__)

# Type alias for a job handler — receives job dict, returns result dict
JobHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


# ── Backoff classification ────────────────────────────────────────────────────

BACKOFF_RULES: dict[str, dict[str, Any]] = {
    "network_timeout": {"backoff_minutes": 5, "max_attempts": 3},
    "rate_limited": {"backoff_minutes": 15, "max_attempts": 3},
    "provider_5xx": {"backoff_minutes": 60, "max_attempts": 3},
    "data_validation": {"backoff_minutes": None, "max_attempts": 1},  # dead letter
    "code_exception": {"backoff_minutes": 5, "max_attempts": 3},
    "not_found": {"backoff_minutes": None, "max_attempts": 1},  # dead letter
    "bad_request": {"backoff_minutes": None, "max_attempts": 1},  # dead letter
}


def classify_failure(error: str, status_code: int | None = None) -> str:
    """Classify a failure into a backoff category based on error message and status code."""
    import re

    if status_code:
        if status_code == 429:
            return "rate_limited"
        if status_code == 404:
            return "not_found"
        if status_code == 400:
            return "bad_request"
        if 500 <= status_code < 600:
            return "provider_5xx"

    error_lower = error.lower()
    if "timeout" in error_lower or "timed out" in error_lower:
        return "network_timeout"
    if "429" in error_lower or "rate limit" in error_lower:
        return "rate_limited"
    # Match standalone 5xx status codes (e.g. "503 Service Unavailable") but NOT
    # Postgres error codes like "23502" which contain "50" as a substring.
    if re.search(r'\b5\d{2}\b', error_lower) or "server error" in error_lower or "unavailable" in error_lower:
        return "provider_5xx"
    if "validation" in error_lower or "invalid" in error_lower:
        return "data_validation"
    if "404" in error_lower or "not found" in error_lower:
        return "not_found"
    if "400" in error_lower or "bad request" in error_lower:
        return "bad_request"
    return "code_exception"


# ── Job Engine ────────────────────────────────────────────────────────────────

class JobEngine:
    """
    Handles the job lifecycle: claim, execute, complete/fail/retry.

    Usage:
        engine = JobEngine(scheduler_repo)
        engine.register_handler("company_refresh", my_handler)
        await engine.run_worker_pool(concurrency=5)
    """

    def __init__(
        self,
        scheduler_repo: SchedulerRepository | None = None,
        worker_id: str | None = None,
    ):
        self._repo = scheduler_repo or SchedulerRepository()
        self._worker_id = worker_id or f"worker:{uuid.uuid4().hex[:8]}"
        self._handlers: dict[str, JobHandler] = {}
        self._lease_renewal_interval = 60  # seconds
        self._claim_poll_interval = 5  # seconds between poll cycles when queue empty

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a handler function for a job type."""
        self._handlers[job_type] = handler

    def get_worker_id(self) -> str:
        return self._worker_id

    # ========================================================================
    # Single Job Execution
    # ========================================================================

    async def execute_job(self, job: dict[str, Any]) -> None:
        """Execute one job with a stable trace id bound to all its log records.

        I28: five worker loops share one stderr stream, so interleaved lines
        were unattributable without a per-job correlation id. ``bind_trace_id``
        stores the id in a ContextVar: each async task keeps its own value across
        awaits, and the previous value is restored when the job ends. Binding by
        the DB job id makes the ``[job-<id>]`` field directly greppable against
        the ``[ENGINE] Job <id>`` lifecycle lines.
        """
        with debug_trace.bind_trace_id(f"job-{job.get('id', 'unknown')}", prefix="job"):
            await self._execute_job(job)

    async def _execute_job(self, job: dict[str, Any]) -> None:
        """
        Execute a single claimed job through its lifecycle:
        claim → execute (with lease renewal) → complete/fail
        """
        job_id = job["id"]
        job_type = job.get("job_type", "")
        lease_token = job.get("lease_token", "")
        handler = self._handlers.get(job_type)

        if not handler:
            logger.error(f"[ENGINE] No handler registered for job_type={job_type} (job_id={job_id})")
            self._repo.fail_job(
                job_id=job_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                error=f"No handler for job_type={job_type}",
                backoff_minutes=0,
            )
            return

        # Record attempt start
        attempt = (job.get("attempts") or 0) + 1
        self._repo.record_attempt(job_id, attempt, "running")
        start_time = time.monotonic()

        # Lease renewal task
        stop_renewal = asyncio.Event()
        renewal_task = asyncio.create_task(
            self._periodic_lease_renewal(job_id, lease_token, stop_renewal)
        )

        try:
            # Validate payload for company_refresh jobs
            if job_type == "company_refresh":
                payload = job.get("payload") or {}
                scopes = payload.get("scopes", [])
                if "financials" in scopes and (not payload.get("company_id") or not payload.get("ticker_symbol")):
                    raise ValueError(f"company_refresh with financials scope missing company_id or ticker_symbol: {payload}")
                if "market_data" in scopes and (not payload.get("company_id") or not payload.get("ticker_symbol")):
                    raise ValueError(f"company_refresh with market_data scope missing company_id or ticker_symbol: {payload}")

            await handler(job)
            duration_ms = int((time.monotonic() - start_time) * 1000)

            self._repo.complete_job(job_id, self._worker_id, lease_token)
            self._repo.record_attempt(
                job_id=job_id,
                attempt=attempt,
                status="succeeded",
                duration_ms=duration_ms,
            )
            logger.info(
                "[ENGINE] Job %s (%s) completed in %dms",
                job_id, job_type, duration_ms,
            )

            # Check for accumulated refresh requests (company_refresh jobs only)
            if job_type == "company_refresh":
                j_payload = job.get("payload", {})
                company_id = j_payload.get("company_id")
                if company_id:
                    pending = self._repo.get_unprocessed_refresh_requests(company_id)
                    if pending:
                        merged_scopes: set = set()
                        merged_reasons: set = set()
                        merged_priority = 0
                        for req in pending:
                            merged_scopes.update(req.get("scopes", []))
                            merged_reasons.update(req.get("reasons", []))
                            merged_priority = max(merged_priority, req.get("priority", 50))
                        self._repo.enqueue_job(
                            job_type="company_refresh",
                            dedupe_key=f"company_refresh:{company_id}",
                            resource_type="company",
                            resource_id=str(company_id),
                            payload={
                                "company_id": company_id,
                                "ticker_symbol": j_payload.get("ticker_symbol"),
                                "scopes": sorted(merged_scopes),
                                "reasons": sorted(merged_reasons),
                            },
                            priority=merged_priority,
                        )
                        self._repo.mark_refresh_requests_processed(company_id)
                        logger.info(
                            "[ENGINE] Emitted follow-up company_refresh job for %s "
                            "with scopes=%s",
                            company_id, sorted(merged_scopes),
                        )

        except Exception as e:
            duration_ms = int((time.monotonic() - start_time) * 1000)
            error_str = str(e)[:500]

            category = classify_failure(error_str)
            rules = BACKOFF_RULES.get(category, BACKOFF_RULES["code_exception"])
            backoff = rules["backoff_minutes"] or 0

            new_status = self._repo.fail_job(
                job_id=job_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                error=f"[{category}] {error_str}",
                backoff_minutes=backoff,
            )
            self._repo.record_attempt(
                job_id=job_id,
                attempt=attempt,
                status="failed",
                error=error_str,
                duration_ms=duration_ms,
            )
            logger.warning(
                "[ENGINE] Job %s (%s) failed after %dms: %s → %s",
                job_id, job_type, duration_ms, category, new_status,
            )
            if new_status == "dead_letter":
                logger.error(
                    "[ENGINE] Job %s (%s) moved to dead_letter after %d attempts",
                    job_id, job_type, attempt,
                )

        finally:
            stop_renewal.set()
            renewal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await renewal_task

    # ========================================================================
    # Worker Pool
    # ========================================================================

    async def run_worker_pool(self, concurrency: int = 5) -> None:
        """
        Run a pool of worker tasks that continuously claim and execute jobs.

        Runs until cancelled.  Designed to be launched as an asyncio task.
        """
        # I30: pool/loop lines live outside execute_job's job scope, so without
        # this they carried the "-" correlation placeholder. Each task copies
        # the current context at creation, so the worker loops inherit this id
        # and then bind their own per-index id on top.
        with debug_trace.bind_trace_id(f"pool-{self._worker_id}", prefix="pool"):
            logger.info(
                "[WORKER_POOL] Starting with concurrency=%d, worker_id=%s",
                concurrency, self._worker_id,
            )
            workers = [asyncio.create_task(self._worker_loop(i)) for i in range(concurrency)]
            try:
                await asyncio.gather(*workers)
            except asyncio.CancelledError:
                logger.info("[WORKER_POOL] Shutting down %d workers", concurrency)
                for w in workers:
                    w.cancel()
                await asyncio.gather(*workers, return_exceptions=True)

    async def _worker_loop(self, worker_index: int) -> None:
        """Individual worker: repeatedly claim and execute jobs."""
        # I30: the loop's claim/error lines are outside execute_job's job scope.
        # The index is the only per-worker discriminator (self._worker_id is
        # shared by all five loops of one engine), so it is the correlation id.
        with debug_trace.bind_trace_id(f"worker-{worker_index}", prefix="worker"):
            while True:
                try:
                    job = self._repo.claim_job(
                        worker_id=self._worker_id,
                        lease_ttl_minutes=30,
                    )
                    if job:
                        logger.debug(
                            "[WORKER:%d] Claimed job %s (%s)",
                            worker_index, job.get("id"), job.get("job_type"),
                        )
                        await self.execute_job(job)
                    else:
                        await asyncio.sleep(self._claim_poll_interval)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(
                        "[WORKER:%d] Error in worker loop: %s",
                        worker_index, e, exc_info=True,
                    )
                    await asyncio.sleep(self._claim_poll_interval)

    # ========================================================================
    # Lease Renewal
    # ========================================================================

    async def _periodic_lease_renewal(
        self,
        job_id: str,
        lease_token: str,
        stop_event: asyncio.Event,
        ttl_minutes: int = 30,
    ) -> None:
        """Renew the job lease periodically during execution."""
        try:
            while not stop_event.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(
                        asyncio.sleep(self._lease_renewal_interval),
                        timeout=self._lease_renewal_interval + 5,
                    )
                if stop_event.is_set():
                    break
                renewed = self._repo.renew_job_lease(
                    job_id=job_id,
                    worker_id=self._worker_id,
                    lease_token=lease_token,
                    ttl_minutes=ttl_minutes,
                )
                if not renewed:
                    logger.warning(
                        "[LEASE] Failed to renew lease for job %s — may be taken over",
                        job_id,
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[LEASE] Renewal error for job {job_id}: {e}")
