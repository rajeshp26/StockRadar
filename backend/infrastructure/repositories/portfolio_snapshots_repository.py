import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)


class PortfolioSnapshotsRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def get_portfolio_snapshots(
        self,
        account_ids: List[int],
        start_date: date,
        end_date: date,
    ) -> List[Dict[str, Any]]:
        if not account_ids:
            return []
        PAGE_SIZE = 1000
        all_data = []
        try:
            offset = 0
            while True:
                res = (
                    self.client.table("portfolio_snapshots")
                    .select("account_id, snapshot_date, total_value, holdings_market_value, cost_basis, "
                            "cash_balance, net_deposits, data_quality_flag")
                    .in_("account_id", account_ids)
                    .gte("snapshot_date", start_date.isoformat())
                    .lte("snapshot_date", end_date.isoformat())
                    .order("snapshot_date", desc=False)
                    .order("account_id", desc=False)
                    .order("id", desc=False)
                    .range(offset, offset + PAGE_SIZE - 1)
                    .execute()
                )
                chunk = res.data or []
                if not chunk:
                    break
                all_data.extend(chunk)
                if len(chunk) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
            return all_data
        except Exception as e:
            logger.error(f"Failed to fetch portfolio snapshots: {e}")
            return []

    def upsert_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        # Strip field that may not exist in DB schema yet
        safe = {k: v for k, v in snapshot.items() if k != "validation_warnings"}
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .upsert(safe, on_conflict="account_id,snapshot_date")
                .execute()
            )
            if not res.data:
                raise Exception("Snapshot upsert returned no data")
            return res.data[0]
        except Exception as e:
            logger.error(f"Failed to upsert snapshot: {e}")
            raise

    def has_snapshots(self, account_id: int) -> bool:
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .select("id")
                .eq("account_id", account_id)
                .limit(1)
                .execute()
            )
            return len(res.data or []) > 0
        except Exception as e:
            logger.error(f"Failed to check snapshots for account {account_id}: {e}")
            return False

    def get_latest_snapshot(self, account_id: int) -> Optional[Dict[str, Any]]:
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .select("*")
                .eq("account_id", account_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"Failed to get latest snapshot for account {account_id}: {e}")
            return None

    def get_account_snapshots(self, account_id: int) -> List[Dict[str, Any]]:
        PAGE_SIZE = 1000
        all_data = []
        try:
            offset = 0
            while True:
                res = (
                    self.client.table("portfolio_snapshots")
                    .select("*")
                    .eq("account_id", account_id)
                    .order("snapshot_date", desc=False)
                    .order("id", desc=False)
                    .range(offset, offset + PAGE_SIZE - 1)
                    .execute()
                )
                chunk = res.data or []
                if not chunk:
                    break
                all_data.extend(chunk)
                if len(chunk) < PAGE_SIZE:
                    break
                offset += PAGE_SIZE
            return all_data
        except Exception as e:
            logger.error(f"Failed to get snapshots for account {account_id}: {e}")
            return []

    def validate_snapshot_invariants(self, account_id: int) -> List[str]:
        errors: List[str] = []
        rows = self.get_account_snapshots(account_id)
        for row in rows:
            tv = float(row["total_value"])
            hmv = float(row.get("holdings_market_value", 0))
            cb = float(row.get("cash_balance", 0))
            if abs(tv - (hmv + cb)) > 0.01:
                errors.append(
                    f"INVARIANT: account {account_id} on {row['snapshot_date']}: "
                    f"total={tv} != market={hmv} + cash={cb}"
                )
            if tv > 1_000_000_000:
                errors.append(f"ABSURD: account {account_id} on {row['snapshot_date']}: ${tv:,.2f}")
        return errors

    def delete_account_snapshots(self, account_id: int) -> int:
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .delete()
                .eq("account_id", account_id)
                .execute()
            )
            deleted = len(res.data) if res.data else 0
            logger.info(f"Deleted {deleted} snapshots for account {account_id}")
            return deleted
        except Exception as e:
            logger.error(f"Failed to delete snapshots for account {account_id}: {e}")
            return 0
