"""
Lock Manager
Provides lease-token-based distributed locking for schedulers.

Wraps the existing company lock methods from SupabaseFinancialRepository
and adds enhanced contract: owner_id + lease_token matching on release,
periodic lease renewal, and stale lock detection.
"""

import logging
import uuid
from datetime import timedelta

from infrastructure.repositories.scheduler_repository import SchedulerRepository
from shared.time_utils import now_utc

logger = logging.getLogger(__name__)


class LockManager:
    """
    Distributed locking with lease tokens.

    Two lock tiers:
      1. Company-level locks (via financial_repo's scheduler_locks table)
         Enhanced with lease_token for safe release.
      2. Resource-level locks (via scheduler_repository's resource_locks table)
         For cross-job serialization.

    Usage:
        lock_mgr = LockManager(financial_repo, scheduler_repo)
        token = await lock_mgr.acquire_company_lock(company_id=123, owner_id="worker1")
        if token:
            try:
                # do work
                await lock_mgr.renew_company_lock(company_id=123, owner_id="worker1", lease_token=token)
            finally:
                await lock_mgr.release_company_lock(company_id=123, owner_id="worker1", lease_token=token)
    """

    def __init__(self, financial_repo, scheduler_repo: SchedulerRepository | None = None):
        self._financial_repo = financial_repo
        self._scheduler_repo = scheduler_repo or SchedulerRepository()

    # ========================================================================
    # COMPANY LOCKS (via scheduler_locks table, enhanced)
    # ========================================================================

    async def acquire_company_lock(
        self,
        company_id: int,
        owner_id: str,
        lock_type: str = "financial_refresh",
        ttl_seconds: int = 1800,
    ) -> str | None:
        """
        Acquire a per-company lock.  Returns lease_token on success, None on failure.

        Enhancement over v2: returns a unique lease token that must be
        provided on release to prevent unsafe cross-worker releases.
        """
        lease_token = str(uuid.uuid4())
        now = now_utc()
        expires = now + timedelta(seconds=ttl_seconds)

        try:
            client = self._financial_repo.client

            # 1) Try take over expired lock
            update_resp = (
                client.table("scheduler_locks")
                .update({
                    "lock_id": f"{owner_id}:{lease_token}",
                    "lease_token": lease_token,
                    "acquired_at": now.isoformat(),
                    "expires_at": expires.isoformat(),
                    "lock_type": lock_type,
                })
                .eq("company_id", company_id)
                .lte("expires_at", now.isoformat())
                .execute()
            )
            if update_resp.data and len(update_resp.data) > 0:
                return lease_token

            # 2) Try insert new lock (unique on company_id prevents duplicates)
            client.table("scheduler_locks").insert({
                "lock_id": f"{owner_id}:{lease_token}",
                "company_id": company_id,
                "lease_token": lease_token,
                "lock_type": lock_type,
                "acquired_at": now.isoformat(),
                "expires_at": expires.isoformat(),
            }).execute()
            return lease_token

        except Exception as e:
            logger.debug(f"[LOCK] Acquire failed for company_id={company_id}: {e}")
            return None

    async def release_company_lock(
        self,
        company_id: int,
        owner_id: str,
        lease_token: str,
    ) -> bool:
        """
        Release a company lock.  Only succeeds if owner_id AND lease_token match.
        Prevents one worker from releasing another worker's lock.
        """
        lock_id = f"{owner_id}:{lease_token}"
        try:
            result = (
                self._financial_repo.client.table("scheduler_locks")
                .delete()
                .eq("company_id", company_id)
                .eq("lock_id", lock_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"[LOCK] Release failed for company_id={company_id}: {e}")
            return False

    async def renew_company_lock(
        self,
        company_id: int,
        owner_id: str,
        lease_token: str,
        ttl_seconds: int = 1800,
    ) -> bool:
        """Extend company lock expiration (owner + token must match)."""
        lock_id = f"{owner_id}:{lease_token}"
        now = now_utc()
        expires = (now + timedelta(seconds=ttl_seconds)).isoformat()
        try:
            result = (
                self._financial_repo.client.table("scheduler_locks")
                .update({"expires_at": expires, "acquired_at": now.isoformat()})
                .eq("company_id", company_id)
                .eq("lock_id", lock_id)
                .execute()
            )
            return bool(result.data)
        except Exception as e:
            logger.error(f"[LOCK] Renew failed for company_id={company_id}: {e}")
            return False

    # ========================================================================
    # RESOURCE LOCKS (cross-job serialization)
    # ========================================================================

    def acquire_resource_lock(
        self,
        resource_type: str,
        resource_id: str,
        lock_type: str,
        owner_id: str,
        ttl_seconds: int = 1800,
    ) -> str | None:
        return self._scheduler_repo.acquire_resource_lock(
            resource_type=resource_type,
            resource_id=resource_id,
            lock_type=lock_type,
            owner_id=owner_id,
            ttl_seconds=ttl_seconds,
        )

    def release_resource_lock(
        self,
        resource_type: str,
        resource_id: str,
        lock_type: str,
        owner_id: str,
        lease_token: str,
    ) -> bool:
        return self._scheduler_repo.release_resource_lock(
            resource_type=resource_type,
            resource_id=resource_id,
            lock_type=lock_type,
            owner_id=owner_id,
            lease_token=lease_token,
        )

    def renew_resource_lock(
        self,
        resource_type: str,
        resource_id: str,
        lock_type: str,
        owner_id: str,
        lease_token: str,
        ttl_seconds: int = 1800,
    ) -> bool:
        return self._scheduler_repo.renew_resource_lock(
            resource_type=resource_type,
            resource_id=resource_id,
            lock_type=lock_type,
            owner_id=owner_id,
            lease_token=lease_token,
            ttl_seconds=ttl_seconds,
        )
