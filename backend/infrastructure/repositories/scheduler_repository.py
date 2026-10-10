"""Scheduler Repository — manages v3 control-plane tables."""

import logging
import time as _time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from database import supabase
from shared.time_utils import iso_minus, iso_plus, now_iso, now_utc, parse_db_timestamp

logger = logging.getLogger(__name__)

_RETRYABLE_ERR_SUBSTRINGS = [
    "timeout", "timed out", "connection reset", "connection refused",
    "connection aborted", "broken pipe", "service unavailable",
    "temporarily unavailable", "too many requests",
    "server error", "internal server error",
]

MAX_DB_RETRIES = 3
DB_BACKOFF_BASE_SECONDS = 0.5


def _is_retryable(err: Exception) -> bool:
    msg = str(err).lower()
    for substr in _RETRYABLE_ERR_SUBSTRINGS:
        if substr in msg:
            return True
    return False


@dataclass
class JobRow:
    id: str
    job_type: str
    resource_type: str | None
    resource_id: str | None
    dedupe_key: str
    priority: int
    status: str
    payload: dict[str, Any] | None
    not_before: str | None
    available_at: str | None
    lease_owner: str | None
    lease_token: str | None
    leased_until: str | None
    attempts: int
    max_attempts: int
    last_error: str | None
    last_error_at: str | None
    created_at: str
    updated_at: str


@dataclass
class SchedulerStateRow:
    scheduler_name: str
    enabled: bool = True
    interval_hours: float = 24.0
    last_planned_at: str | None = None
    last_status: str | None = None
    last_error: str | None = None
    next_due_at: str | None = None
    updated_at: str | None = None


class SchedulerRepository:

    JOBS_TABLE = "jobs"
    JOB_ATTEMPTS_TABLE = "job_attempts"
    SCHEDULER_STATE_TABLE = "scheduler_state"
    SCHEDULER_RUN_HISTORY_TABLE = "scheduler_run_history"
    WORKER_HEARTBEATS_TABLE = "worker_heartbeats"
    RESOURCE_LOCKS_TABLE = "resource_locks"
    COMPANY_REFRESH_REQUESTS_TABLE = "company_refresh_requests"

    # ====================================================================
    # Retry wrapper for DB calls
    # ====================================================================

    def _db_call(self, label: str, fn: Callable, retries: int = MAX_DB_RETRIES):
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                return fn()
            except Exception as e:
                last_exc = e
                if attempt < retries and _is_retryable(e):
                    backoff = DB_BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                    logger.warning(
                        "[RETRY] %s failed (attempt %d/%d): %s — retrying in %.1fs",
                        label, attempt, retries, e, backoff,
                    )
                    _time.sleep(backoff)
                else:
                    break
        raise last_exc

    # ====================================================================
    # JOBS
    # ====================================================================

    def enqueue_job(
        self,
        job_type: str,
        dedupe_key: str,
        payload: dict[str, Any] | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        priority: int = 50,
        max_attempts: int = 3,
        not_before: str | None = None,
    ) -> bool:
        new_payload = payload or {}
        new_scopes = set(new_payload.get("scopes", []))
        new_reasons = set(new_payload.get("reasons", ["routine"]))

        # Check for existing active job with same dedupe key
        try:
            existing = (
                supabase.table(self.JOBS_TABLE)
                .select("id, status, priority, payload")
                .eq("dedupe_key", dedupe_key)
                .in_("status", ["pending", "running"])
                .limit(1)
                .execute()
            )
        except Exception:
            existing = None

        if existing and existing.data:
            ex = existing.data[0]
            ex_payload = ex.get("payload", {})
            ex_scopes = set(ex_payload.get("scopes", []))
            ex_reasons = set(ex_payload.get("reasons", []))

            merged_priority = max(priority, ex.get("priority", 50))
            merged_scopes = sorted(ex_scopes | new_scopes)
            merged_reasons = sorted(ex_reasons | new_reasons)

            if ex["status"] == "pending":
                update = {
                    "priority": merged_priority,
                    "payload": {
                        **ex_payload,
                        "scopes": merged_scopes,
                        "reasons": merged_reasons,
                    },
                    "updated_at": now_iso(),
                }
                try:
                    supabase.table(self.JOBS_TABLE).update(update).eq("id", ex["id"]).execute()
                    return True
                except Exception:
                    return False

            # Running job — record in accumulator for follow-up
            try:
                supabase.table(self.COMPANY_REFRESH_REQUESTS_TABLE).insert({
                    "company_id": resource_id,
                    "scopes": list(new_scopes - ex_scopes),
                    "reasons": list(new_reasons - ex_reasons),
                    "priority": priority,
                    "requested_at": now_iso(),
                    "processed": False,
                }).execute()
            except Exception:
                pass
            return True

        # No existing active job — fresh insert
        row = {
            "job_type": job_type,
            "dedupe_key": dedupe_key,
            "payload": new_payload,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "priority": priority,
            "max_attempts": max_attempts,
            "status": "pending",
            "available_at": not_before or now_iso(),
        }
        if not_before:
            row["not_before"] = not_before
        try:
            supabase.table(self.JOBS_TABLE).insert(row).execute()
            return True
        except Exception:
            return False

    def enqueue_job_batch(self, jobs: list[dict[str, Any]]) -> int:
        count = 0
        for j in jobs:
            if self.enqueue_job(**j):
                count += 1
        return count

    def claim_job(self, worker_id: str, lease_ttl_minutes: int = 30) -> dict[str, Any] | None:
        now = now_iso()
        leased_until = iso_plus(minutes=lease_ttl_minutes)
        lease_token = str(uuid.uuid4())

        try:
            candidates = (
                supabase.table(self.JOBS_TABLE)
                .select("id, attempts")
                .eq("status", "pending")
                .lte("available_at", now)
                .order("priority", desc=True)
                .order("available_at")
                .order("created_at")
                .limit(1)
                .execute()
            )
            if not candidates.data:
                return None

            job_id = candidates.data[0]["id"]
            next_attempt = (candidates.data[0].get("attempts") or 0) + 1

            result = (
                supabase.table(self.JOBS_TABLE)
                .update({
                    "status": "running",
                    "lease_owner": worker_id,
                    "lease_token": lease_token,
                    "leased_until": leased_until,
                    "attempts": next_attempt,
                    "updated_at": now,
                })
                .eq("id", job_id)
                .eq("status", "pending")
                .execute()
            )
            if result.data:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[CLAIM] Failed to claim job: {e}")
            return None

    def renew_job_lease(self, job_id: str, worker_id: str, lease_token: str, ttl_minutes: int = 30) -> bool:
        now = now_utc()
        leased_until = (now + timedelta(minutes=ttl_minutes)).isoformat()
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .update({"leased_until": leased_until, "updated_at": now.isoformat()})
                .eq("id", job_id)
                .eq("lease_owner", worker_id)
                .eq("lease_token", lease_token)
                .eq("status", "running")
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"[RENEW] Failed to renew lease for job {job_id}: {e}")
            return False

    def complete_job(self, job_id: str, worker_id: str, lease_token: str) -> bool:
        now = now_iso()
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .update({
                    "status": "succeeded",
                    "lease_owner": None,
                    "lease_token": None,
                    "leased_until": None,
                    "updated_at": now,
                })
                .eq("id", job_id)
                .eq("lease_owner", worker_id)
                .eq("lease_token", lease_token)
                .eq("status", "running")
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"[COMPLETE] Failed to complete job {job_id}: {e}")
            return False

    def fail_job(
        self,
        job_id: str,
        worker_id: str,
        lease_token: str,
        error: str,
        backoff_minutes: int = 5,
    ) -> str:
        now = now_utc()
        try:
            job = (
                supabase.table(self.JOBS_TABLE)
                .select("attempts, max_attempts")
                .eq("id", job_id)
                .single()
                .execute()
            )
            if not job.data:
                return "unknown"

            attempts = (job.data.get("attempts") or 0) + 1
            max_attempts = job.data.get("max_attempts") or 3

            if attempts >= max_attempts or "DEFEAT_BETA_NO_DATA" in (error or ""):
                new_status = "dead_letter"
                update = {
                    "status": new_status,
                    "last_error": error,
                    "last_error_at": now.isoformat(),
                    "lease_owner": None,
                    "lease_token": None,
                    "leased_until": None,
                    "updated_at": now.isoformat(),
                }
            else:
                new_status = "pending"
                available_at = (now + timedelta(minutes=backoff_minutes)).isoformat()
                update = {
                    "status": new_status,
                    "available_at": available_at,
                    "last_error": error,
                    "last_error_at": now.isoformat(),
                    "lease_owner": None,
                    "lease_token": None,
                    "leased_until": None,
                    "updated_at": now.isoformat(),
                }

            result = (
                supabase.table(self.JOBS_TABLE)
                .update(update)
                .eq("id", job_id)
                .eq("lease_owner", worker_id)
                .eq("lease_token", lease_token)
                .execute()
            )
            if not result.data:
                logger.warning(f"[FAIL] No rows updated for {job_id} — owner/token mismatch")
                return "error"
            return new_status
        except Exception as e:
            logger.error(f"[FAIL] Failed to fail job {job_id}: {e}")
            return "error"

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .select("*")
                .eq("id", job_id)
                .limit(1)
                .execute()
            )
            return result.data[0] if result.data else None
        except Exception as e:
            logger.error(f"[GET_JOB] Failed: {e}")
            return None

    def get_jobs_by_status(self, status: str, limit: int = 100) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .select("*")
                .eq("status", status)
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"[GET_JOBS] Failed: {e}")
            return []

    def get_queue_depth(self) -> dict[str, int]:
        counts = {"pending": 0, "running": 0, "succeeded": 0, "dead_letter": 0, "cancelled": 0}
        for status in counts:
            try:
                result = (
                    supabase.table(self.JOBS_TABLE)
                    .select("id", count="exact")
                    .eq("status", status)
                    .limit(0)
                    .execute()
                )
                counts[status] = getattr(result, "count", 0) or 0
            except Exception:
                pass
        return counts

    def get_oldest_pending_age_seconds(self) -> float | None:
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .select("created_at")
                .eq("status", "pending")
                .order("created_at")
                .limit(1)
                .execute()
            )
            if result.data:
                created = parse_db_timestamp(result.data[0]["created_at"])
                return (now_utc() - created).total_seconds()
            return None
        except Exception:
            return None

    def requeue_job(self, job_id: str) -> bool:
        now = now_iso()
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .update({
                    "status": "pending",
                    "attempts": 0,
                    "last_error": None,
                    "last_error_at": None,
                    "available_at": now,
                    "lease_owner": None,
                    "lease_token": None,
                    "leased_until": None,
                    "updated_at": now,
                })
                .eq("id", job_id)
                .eq("status", "dead_letter")
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"[REQUEUE] Failed for job {job_id}: {e}")
            return False

    def cancel_job(self, job_id: str) -> bool:
        now = now_iso()
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .update({
                    "status": "cancelled",
                    "lease_owner": None,
                    "lease_token": None,
                    "leased_until": None,
                    "updated_at": now,
                })
                .eq("id", job_id)
                .in_("status", ("pending", "running"))
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    # ====================================================================
    # JOB ATTEMPTS
    # ====================================================================

    def record_attempt(
        self,
        job_id: str,
        attempt: int,
        status: str,
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        try:
            supabase.table(self.JOB_ATTEMPTS_TABLE).upsert({
                "job_id": job_id,
                "attempt": attempt,
                "status": status,
                "started_at": now_iso() if status == "running" else None,
                "finished_at": now_iso() if status in ("succeeded", "failed") else None,
                "error": error,
                "duration_ms": duration_ms,
            }, on_conflict="job_id,attempt").execute()
        except Exception as e:
            logger.error(f"[ATTEMPT] Failed to record attempt for job {job_id}: {e}")

    def get_attempts(self, job_id: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table(self.JOB_ATTEMPTS_TABLE)
                .select("*")
                .eq("job_id", job_id)
                .order("attempt", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    # ====================================================================
    # SCHEDULER STATE
    # ====================================================================

    def get_scheduler_state(self, scheduler_name: str) -> dict[str, Any] | None:
        try:
            result = self._db_call(
                f"get_scheduler_state({scheduler_name})",
                lambda: (
                    supabase.table(self.SCHEDULER_STATE_TABLE)
                    .select("*")
                    .eq("scheduler_name", scheduler_name)
                    .limit(1)
                    .execute()
                ),
            )
            return result.data[0] if result.data else None
        except Exception:
            return None

    def get_all_scheduler_states(self) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table(self.SCHEDULER_STATE_TABLE)
                .select("*")
                .order("scheduler_name")
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def upsert_scheduler_state(self, state: dict[str, Any]) -> None:
        state["updated_at"] = now_iso()
        try:
            self._db_call(
                "upsert_scheduler_state",
                lambda: supabase.table(self.SCHEDULER_STATE_TABLE).upsert(
                    state, on_conflict="scheduler_name",
                ).execute(),
            )
        except Exception as e:
            logger.error(f"[STATE] Failed to upsert scheduler state: {e}")

    def update_scheduler_state(self, scheduler_name: str, updates: dict[str, Any]) -> None:
        updates["updated_at"] = now_iso()
        try:
            supabase.table(self.SCHEDULER_STATE_TABLE).update(updates).eq(
                "scheduler_name", scheduler_name
            ).execute()
        except Exception as e:
            logger.error(f"[STATE] Failed to update scheduler state for '{scheduler_name}': {e}")

    # ====================================================================
    # SCHEDULER RUN HISTORY
    # ====================================================================

    def record_planner_run(
        self,
        scheduler_name: str,
        jobs_enqueued: int = 0,
        status: str = "succeeded",
        error: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        try:
            self._db_call(
                f"record_planner_run({scheduler_name})",
                lambda: supabase.table(self.SCHEDULER_RUN_HISTORY_TABLE).insert({
                    "scheduler_name": scheduler_name,
                    "planned_at": now_iso(),
                    "jobs_enqueued": jobs_enqueued,
                    "status": status,
                    "error": error,
                    "duration_ms": duration_ms,
                }).execute(),
            )
        except Exception as e:
            logger.error(f"[RUN_HISTORY] Failed to record run: {e}")

    def get_recent_runs(self, scheduler_name: str, limit: int = 10) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table(self.SCHEDULER_RUN_HISTORY_TABLE)
                .select("*")
                .eq("scheduler_name", scheduler_name)
                .order("planned_at", desc=True)
                .limit(limit)
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    # ====================================================================
    # WORKER HEARTBEATS
    # ====================================================================

    def record_heartbeat(
        self,
        worker_id: str,
        hostname: str | None = None,
        pid: int | None = None,
        active_jobs: int = 0,
    ) -> None:
        try:
            supabase.table(self.WORKER_HEARTBEATS_TABLE).upsert({
                "worker_id": worker_id,
                "hostname": hostname,
                "pid": pid,
                "last_hb_at": now_iso(),
                "active_jobs": active_jobs,
            }, on_conflict="worker_id").execute()
        except Exception as e:
            logger.error(f"[HB] Failed to record heartbeat: {e}")

    def release_worker_leases(self, worker_id: str) -> int:
        now = now_iso()
        try:
            result = (
                supabase.table(self.JOBS_TABLE)
                .update({
                    "status": "pending",
                    "lease_owner": None,
                    "lease_token": None,
                    "leased_until": None,
                    "last_error": f"worker shutdown: owner={worker_id}",
                    "last_error_at": now,
                    "updated_at": now,
                })
                .eq("lease_owner", worker_id)
                .eq("status", "running")
                .execute()
            )
            return len(result.data or [])
        except Exception as e:
            logger.error(f"[SHUTDOWN] Failed to release leases for {worker_id}: {e}")
            return 0

    def get_worker_heartbeats(self, stale_threshold_minutes: int = 2) -> list[dict[str, Any]]:
        cutoff = now_utc() - timedelta(minutes=stale_threshold_minutes)
        try:
            result = (
                supabase.table(self.WORKER_HEARTBEATS_TABLE)
                .select("*")
                .execute()
            )
            alive = []
            for w in (result.data or []):
                try:
                    hb = parse_db_timestamp(w.get("last_hb_at", ""))
                    if hb >= cutoff:
                        alive.append(w)
                except Exception:
                    pass
            return alive
        except Exception:
            return []

    def prune_stale_heartbeats(self, retention_days: int = 7) -> int:
        cutoff = iso_minus(days=retention_days)
        try:
            result = (
                supabase.table(self.WORKER_HEARTBEATS_TABLE)
                .delete()
                .lt("last_hb_at", cutoff)
                .execute()
            )
            return len(result.data or [])
        except Exception as e:
            logger.error(f"[PRUNE_HB] Failed: {e}")
            return 0

    def prune_zombie_heartbeats(self) -> int:
        try:
            result = (
                supabase.table(self.WORKER_HEARTBEATS_TABLE)
                .delete()
                .eq("hostname", "shutdown")
                .execute()
            )
            return len(result.data or [])
        except Exception as e:
            logger.error(f"[ZOMBIE_HB] Failed to prune zombie heartbeats: {e}")
            return 0

    def release_expired_scheduler_locks(self) -> int:
        now = now_iso()
        try:
            result = (
                supabase.table("scheduler_locks")
                .delete()
                .lt("expires_at", now)
                .execute()
            )
            return len(result.data or [])
        except Exception as e:
            logger.error(f"[LOCK] Failed to release expired scheduler locks: {e}")
            return 0

    # ====================================================================
    # RESOURCE LOCKS
    # ====================================================================

    def acquire_resource_lock(
        self,
        resource_type: str,
        resource_id: str,
        lock_type: str,
        owner_id: str,
        ttl_seconds: int = 1800,
    ) -> str | None:
        lease_token = str(uuid.uuid4())
        now = now_utc()
        leased_until = (now + timedelta(seconds=ttl_seconds)).isoformat()

        try:
            result = (
                supabase.table(self.RESOURCE_LOCKS_TABLE)
                .update({
                    "owner_id": owner_id,
                    "lease_token": lease_token,
                    "leased_until": leased_until,
                    "heartbeat_at": now.isoformat(),
                })
                .eq("resource_type", resource_type)
                .eq("resource_id", resource_id)
                .eq("lock_type", lock_type)
                .lt("leased_until", now.isoformat())
                .execute()
            )
            if result.data:
                return lease_token

            supabase.table(self.RESOURCE_LOCKS_TABLE).insert({
                "resource_type": resource_type,
                "resource_id": resource_id,
                "lock_type": lock_type,
                "owner_id": owner_id,
                "lease_token": lease_token,
                "leased_until": leased_until,
                "heartbeat_at": now.isoformat(),
            }).execute()
            return lease_token

        except Exception:
            return None

    def release_resource_lock(
        self,
        resource_type: str,
        resource_id: str,
        lock_type: str,
        owner_id: str,
        lease_token: str,
    ) -> bool:
        try:
            result = (
                supabase.table(self.RESOURCE_LOCKS_TABLE)
                .delete()
                .eq("resource_type", resource_type)
                .eq("resource_id", resource_id)
                .eq("lock_type", lock_type)
                .eq("owner_id", owner_id)
                .eq("lease_token", lease_token)
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    def renew_resource_lock(
        self,
        resource_type: str,
        resource_id: str,
        lock_type: str,
        owner_id: str,
        lease_token: str,
        ttl_seconds: int = 1800,
    ) -> bool:
        now = now_utc()
        leased_until = (now + timedelta(seconds=ttl_seconds)).isoformat()
        try:
            result = (
                supabase.table(self.RESOURCE_LOCKS_TABLE)
                .update({
                    "leased_until": leased_until,
                    "heartbeat_at": now.isoformat(),
                })
                .eq("resource_type", resource_type)
                .eq("resource_id", resource_id)
                .eq("lock_type", lock_type)
                .eq("owner_id", owner_id)
                .eq("lease_token", lease_token)
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    def get_stale_lock_count(self) -> int:
        now = now_iso()
        try:
            result = (
                supabase.table(self.RESOURCE_LOCKS_TABLE)
                .select("resource_type", count="exact")
                .lt("leased_until", now)
                .limit(0)
                .execute()
            )
            return getattr(result, "count", 0) or 0
        except Exception:
            return 0

    # ====================================================================
    # COMPANY REFRESH REQUESTS
    # ====================================================================

    def record_refresh_request(
        self,
        company_id: int,
        scopes: list[str],
        reasons: list[str] | None = None,
        priority: int = 50,
    ) -> None:
        try:
            supabase.table(self.COMPANY_REFRESH_REQUESTS_TABLE).insert({
                "company_id": company_id,
                "scopes": scopes,
                "reasons": reasons or ["routine"],
                "priority": priority,
                "requested_at": now_iso(),
                "processed": False,
            }).execute()
        except Exception as e:
            logger.error(f"[REFRESH_REQ] Failed for company {company_id}: {e}")

    def get_unprocessed_refresh_requests(self, company_id: int) -> list[dict[str, Any]]:
        try:
            result = (
                supabase.table(self.COMPANY_REFRESH_REQUESTS_TABLE)
                .select("*")
                .eq("company_id", company_id)
                .eq("processed", False)
                .order("requested_at")
                .execute()
            )
            return result.data or []
        except Exception:
            return []

    def mark_refresh_requests_processed(self, company_id: int) -> None:
        try:
            supabase.table(self.COMPANY_REFRESH_REQUESTS_TABLE).update({
                "processed": True,
            }).eq("company_id", company_id).eq("processed", False).execute()
        except Exception as e:
            logger.error(f"[REFRESH_REQ] Failed to mark processed for company {company_id}: {e}")

    # ====================================================================
    # JANITOR
    # ====================================================================

    def reclaim_expired_leases(self) -> int:
        now = now_utc()
        now_iso_str = now.isoformat()
        reclaimed = 0
        try:
            expired = (
                supabase.table(self.JOBS_TABLE)
                .select("id, lease_owner, lease_token, leased_until")
                .eq("status", "running")
                .lt("leased_until", now_iso_str)
                .execute()
            )
            for job in (expired.data or []):
                job_id = job.get("id")
                old_owner = job.get("lease_owner", "unknown")
                try:
                    supabase.table(self.JOBS_TABLE).update({
                        "status": "pending",
                        "lease_owner": None,
                        "lease_token": None,
                        "leased_until": None,
                        "last_error": f"lease expired: owner={old_owner}",
                        "last_error_at": now_iso_str,
                        "updated_at": now_iso_str,
                    }).eq("id", job_id).eq("status", "running").execute()
                    reclaimed += 1
                except Exception:
                    pass
            return reclaimed
        except Exception as e:
            logger.error(f"[JANITOR] Failed to reclaim leases: {e}")
            return 0

    def _delete_prunable_jobs(self, status: str, cutoff_days: int) -> int:
        """
        Delete old jobs of a given status FK-safely: attempt rows first, then
        the jobs themselves.

        Supabase enforces ``job_attempts_job_id_fkey`` — a job cannot be
        deleted while its ``job_attempts`` rows still exist. The generic
        attempt prune only removes rows whose ``finished_at`` is older than
        the window, so a job that is old but whose attempts are newer (or
        have NULL ``finished_at``) used to violate the FK on every prune cycle.
        """
        cutoff = (now_utc() - timedelta(days=cutoff_days)).isoformat()
        r = supabase.table(self.JOBS_TABLE) \
            .select("id") \
            .eq("status", status) \
            .lt("updated_at", cutoff) \
            .execute()
        job_ids = [row["id"] for row in (r.data or [])]
        if not job_ids:
            return 0

        supabase.table(self.JOB_ATTEMPTS_TABLE) \
            .delete() \
            .in_("job_id", job_ids) \
            .execute()
        r = supabase.table(self.JOBS_TABLE) \
            .delete() \
            .in_("id", job_ids) \
            .execute()
        return len(r.data or [])

    def prune_old_records(self) -> dict[str, int]:
        results = {}
        now = now_utc()

        try:
            results["jobs_succeeded"] = self._delete_prunable_jobs("succeeded", 90)
        except Exception as e:
            logger.error(f"[PRUNE] jobs_succeeded: {e}")

        try:
            results["jobs_dead_letter"] = self._delete_prunable_jobs("dead_letter", 180)
        except Exception as e:
            logger.error(f"[PRUNE] jobs_dead_letter: {e}")

        try:
            cutoff = (now - timedelta(days=90)).isoformat()
            r = supabase.table(self.JOB_ATTEMPTS_TABLE).delete().lt("finished_at", cutoff).execute()
            results["job_attempts"] = len(r.data or [])
        except Exception as e:
            logger.error(f"[PRUNE] job_attempts: {e}")

        try:
            cutoff = (now - timedelta(days=90)).isoformat()
            r = supabase.table(self.SCHEDULER_RUN_HISTORY_TABLE).delete().lt("planned_at", cutoff).execute()
            results["run_history"] = len(r.data or [])
        except Exception as e:
            logger.error(f"[PRUNE] run_history: {e}")

        try:
            self.prune_stale_heartbeats(retention_days=7)
        except Exception as e:
            logger.error(f"[PRUNE] heartbeats: {e}")

        return results
