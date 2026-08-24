import json as _json
import logging
from datetime import date, timedelta
from typing import Any

from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)


class PortfolioSnapshotsRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def get_portfolio_snapshots(
        self,
        account_ids: list[int],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
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

    def upsert_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        # Strip field that may not exist in DB schema yet
        safe = {k: v for k, v in snapshot.items() if k != "validation_warnings"}
        self._validate_holdings_consistency(safe)
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

    def upsert_snapshots_batch(self, snapshots: list[dict[str, Any]], batch_size: int = 500) -> int:
        """Upsert multiple snapshots in batches for better performance.

        Validates holdings_json consistency before writing: the sum of
        current_value fields in holdings_json must equal holdings_market_value.
        Inconsistent snapshots are logged as warnings and the holdings_json
        is set to None to prevent silent data corruption.
        """
        if not snapshots:
            return 0
        safe = []
        for s in snapshots:
            row = {k: v for k, v in s.items() if k != "validation_warnings"}
            self._validate_holdings_consistency(row)
            safe.append(row)
        total = 0
        for i in range(0, len(safe), batch_size):
            chunk = safe[i:i + batch_size]
            try:
                res = (
                    self.client.table("portfolio_snapshots")
                    .upsert(chunk, on_conflict="account_id,snapshot_date")
                    .execute()
                )
                total += len(res.data or chunk)
            except Exception as e:
                logger.error(f"Batch upsert failed for chunk {i}: {e}")
                raise
        return total

    @staticmethod
    def _validate_holdings_consistency(snapshot: dict[str, Any]) -> None:
        """Ensure holdings_json sum matches holdings_market_value.

        If mismatch detected, logs a warning and nullifies holdings_json
        to prevent the UI from displaying inflated/deflated individual
        holdings that don't agree with the scalar total.
        """
        holdings_raw = snapshot.get("holdings_json")
        if holdings_raw is None:
            return
        holdings = _json.loads(holdings_raw) if isinstance(holdings_raw, str) else holdings_raw
        if not holdings:
            return
        json_sum = sum(h.get("current_value", 0) or 0 for h in holdings)
        db_val = float(snapshot.get("holdings_market_value") or 0)
        diff = abs(db_val - json_sum)
        if diff > 0.01:
            acct = snapshot.get("account_id", "?")
            dt = snapshot.get("snapshot_date", "?")
            flag = snapshot.get("data_quality_flag", "?")
            logger.warning(
                f"HOLDINGS_INTEGRITY: account={acct} date={dt} flag={flag} "
                f"holdings_market_value={db_val:.2f} != sum(holdings_json)={json_sum:.2f} "
                f"diff={db_val - json_sum:+.2f} — nullifying holdings_json"
            )
            snapshot["holdings_json"] = None

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

    def get_latest_snapshot(self, account_id: int) -> dict[str, Any] | None:
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

    def get_account_snapshots(self, account_id: int) -> list[dict[str, Any]]:
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

    def get_previous_snapshot(
        self, account_id: int, before_date: date
    ) -> dict[str, Any] | None:
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .select("account_id, snapshot_date, total_value, "
                        "holdings_market_value, cost_basis, cash_balance, "
                        "net_deposits, data_quality_flag, holdings_json")
                .eq("account_id", account_id)
                .lt("snapshot_date", before_date.isoformat())
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(
                f"Failed to get previous snapshot for account {account_id}: {e}"
            )
            return None

    def get_last_snapshot_date(self, account_id: int) -> date | None:
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .select("snapshot_date")
                .eq("account_id", account_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                d = res.data[0]["snapshot_date"]
                if isinstance(d, str):
                    return date.fromisoformat(d)
                return d
            return None
        except Exception as e:
            logger.error(
                f"Failed to get last snapshot date for account {account_id}: {e}"
            )
            return None

    def get_missing_dates(
        self, account_id: int, start_date: date, end_date: date
    ) -> list[date]:
        try:
            res = (
                self.client.table("portfolio_snapshots")
                .select("snapshot_date")
                .eq("account_id", account_id)
                .gte("snapshot_date", start_date.isoformat())
                .lte("snapshot_date", end_date.isoformat())
                .execute()
            )
            existing = set()
            for row in (res.data or []):
                d = row["snapshot_date"]
                if isinstance(d, str):
                    d = date.fromisoformat(d)
                existing.add(d)

            all_dates = set()
            current = start_date
            while current <= end_date:
                if current.weekday() < 5:
                    all_dates.add(current)
                current += timedelta(days=1)

            return sorted(all_dates - existing)
        except Exception as e:
            logger.error(
                f"Failed to get missing dates for account {account_id}: {e}"
            )
            return []

    def validate_snapshot_invariants(self, account_id: int) -> list[str]:
        errors: list[str] = []
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
