"""
Financial Data Repository - Refactored
Handles all database operations with improved error handling and type safety.

Additions in this version:
  - Per-company scheduler locks for multi-replica safety (scheduler_locks)
  - Conflict detection logging to data_conflicts (config-gated)
  - Upserts for market-data tables (price_history, splits, revenue_forecast, earnings_forecast, company_summary)
  - Optional price history pruning helper (disabled by default at scheduler level)
  - Restored helper: company_exists(company_id) -> bool
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal
from itertools import islice
import hashlib
from typing import Any

from application.validators.financial_data_validator import (
    verify_database_write,
)
from config import settings
from database import supabase
from domain.model_types import (
    BalanceSheetRow,
    CashFlowRow,
    CompanyRefreshInfo,
    CompleteFundamentals,
    DividendRow,
    EarningsRow,
    IncomeStatementRow,
)
from shared.time_utils import now_iso, now_utc, parse_db_timestamp
from supabase import Client

logger = logging.getLogger(__name__)


# ============================================================================
# SERIALIZATION UTILITY
# ============================================================================
class DatabaseSerializer:
    """Handles conversion of Python types to database-compatible formats."""

    @staticmethod
    def serialize(data: dict) -> dict:
        """
        Convert non-JSON-serializable types to database-compatible formats.

        Handles:
        - date → ISO format string
        - datetime → ISO format string
        - Decimal → float
        - None → None (preserved)
        """
        result = {}
        for key, value in data.items():
            if value is None:
                result[key] = None
            elif isinstance(value, datetime) or isinstance(value, date):
                result[key] = value.isoformat()
            elif isinstance(value, Decimal):
                if value == value.to_integral_value():
                    result[key] = int(value)
                else:
                    result[key] = float(value)
            else:
                result[key] = value
        return result


# ============================================================================
# FINANCIAL REPOSITORY
# ============================================================================
def _deterministic_id(*parts: Any) -> int:
    """Generate a deterministic positive integer ID from composite key parts."""
    key = "|".join(str(p) for p in parts)
    return int(hashlib.sha256(key.encode()).hexdigest()[:15], 16)


class SupabaseFinancialRepository:
    """
    Repository for all financial data operations with Supabase.
    Uses unconditional unique constraints for reliable UPSERT operations.
    """

    def __init__(self, client: Client = supabase):
        self.client = client

    # ========================================================================
    # INTERNAL HELPER: CHUNKED UPSERT
    # ========================================================================
    async def _chunked_upsert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        on_conflict: str,
        chunk_size: int = 1000,
    ) -> int:
        """
        Break large payloads into chunks to avoid exceeding Supabase limits.
        """
        if not rows:
            return 0

        def _chunks(iterable, size):
            it = iter(iterable)
            while True:
                chunk = list(islice(it, size))
                if not chunk:
                    break
                yield chunk

        total = 0
        for chunk in _chunks(rows, chunk_size):
            serialized = [DatabaseSerializer.serialize(r) for r in chunk]
            self.client.table(table).upsert(
                serialized,
                on_conflict=on_conflict
            ).execute()
            total += len(chunk)

        return total

    # ========================================================================
    # SCHEDULER LOCKS (Multi-Replica Safety) - Per-company locking
    # ========================================================================
    async def acquire_company_lock(
        self,
        company_id: int,
        owner_id: str,
        ttl_seconds: int = 1800,
        lock_type: str = "financial_refresh",
    ) -> bool:
        """
        Acquire a distributed lock for a given company_id.
        - If a lock exists and is not expired -> return False
        - If expired, take it over
        - Else insert a new lock row

        Schema assumptions (from your DDL):
          scheduler_locks (
            lock_id varchar PK,
            company_id int UNIQUE,
            acquired_at timestamptz,
            expires_at timestamptz,
            lock_type varchar
          )
        """
        now = now_utc()
        expires = now + timedelta(seconds=ttl_seconds)

        try:
            # 1) Try to take over an expired lock
            update_resp = (
                self.client.table("scheduler_locks")
                .update(
                    {
                        "lock_id": owner_id,
                        "acquired_at": now.isoformat(),
                        "expires_at": expires.isoformat(),
                        "lock_type": lock_type,
                    }
                )
                .eq("company_id", company_id)
                .lte("expires_at", now.isoformat())
                .execute()
            )
            if update_resp.data and len(update_resp.data) > 0:
                return True  # acquired

            # 2) Try to insert a new lock (succeeds if none exists)
            insert_payload = {
                "lock_id": owner_id,
                "company_id": company_id,
                "acquired_at": now.isoformat(),
                "expires_at": expires.isoformat(),
                "lock_type": lock_type,
            }
            self.client.table("scheduler_locks").insert(insert_payload).execute()
            return True

        except Exception as e:
            # Insert likely failed due to uniqueness (another owner holds it)
            logger.debug(f"[LOCK] Acquire failed for company_id={company_id}: {e}")
            return False

    async def refresh_company_lock(self, company_id: int, owner_id: str, ttl_seconds: int = 1800) -> bool:
        """Extend lock expiration (owner-only)."""
        now = now_utc()
        expires = now + timedelta(seconds=ttl_seconds)
        try:
            resp = (
                self.client.table("scheduler_locks")
                .update({"expires_at": expires.isoformat()})
                .eq("company_id", company_id)
                .eq("lock_id", owner_id)
                .execute()
            )
            return bool(resp.data)
        except Exception as e:
            logger.error(f"[LOCK] Failed to refresh lock for company_id={company_id}: {e}")
            return False

    async def release_company_lock(self, company_id: int, owner_id: str) -> None:
        """Release lock so another replica can process this company."""
        try:
            (
                self.client.table("scheduler_locks")
                .delete()
                .eq("company_id", company_id)
                .eq("lock_id", owner_id)
                .execute()
            )
        except Exception as e:
            logger.error(f"[LOCK] Failed to release lock for company_id={company_id}: {e}")

    # ========================================================================
    # DATA CONFLICT LOGGING
    # ========================================================================
    async def log_conflict(
        self,
        company_id: int,
        fiscal_year: int | None,
        fiscal_quarter: int | None,
        field: str,
        existing_value: float | None,
        existing_source: str,
        new_value: float | None,
        new_source: str,
        pct_diff: float,
    ) -> None:
        """
        Insert a conflict record into data_conflicts table.
        Designed for numeric fields; but can be used for categorical by passing pct_diff=100.0 when values differ.
        """
        if not getattr(settings, "ENABLE_CONFLICT_DETECTION", True):
            return
        try:
            now = now_iso()
            payload = {
                "company_id": company_id,
                "fiscal_year": fiscal_year if fiscal_year is not None else 0,
                "fiscal_quarter": fiscal_quarter,
                "field_name": field,
                "existing_value": existing_value,
                "existing_source": existing_source or "unknown",
                "new_value": new_value,
                "new_source": new_source or "unknown",
                "percent_diff": float(pct_diff),
                "detected_at": now,
                "resolved": False,
            }
            self.client.table("data_conflicts").insert(payload).execute()
        except Exception as e:
            logger.error(f"[CONFLICT] Failed to log conflict: {e}")

    @staticmethod
    def _pct_diff(a: float | None, b: float | None) -> float | None:
        """Return absolute percent difference between two numbers (or None)."""
        if a is None or b is None:
            return None
        try:
            a_f, b_f = float(a), float(b)
            if a_f == b_f == 0:
                return 0.0
            denom = max(abs(a_f), 1e-9)
            return abs(a_f - b_f) / denom * 100.0
        except Exception:
            return None

    # ========================================================================
    # OPTIONAL RETENTION: PRICE HISTORY PRUNING (disabled by default)
    # ========================================================================
    async def prune_price_history(self, retention_years: int = 10) -> int:
        """
        Delete price_history rows older than CURRENT_DATE - retention_years.
        NOTE: Not called automatically; enable from the scheduler when desired.
        Returns number of rows affected if the driver returns it, else 0.
        """
        today = now_utc().date()
        cutoff_year = today.year - int(retention_years)
        # Handle Feb 29 etc. by using March 1 - 1 day trick for safety
        try:
            cutoff = date(cutoff_year, today.month, today.day)
        except ValueError:
            cutoff = (date(cutoff_year, 3, 1) - timedelta(days=1))

        try:
            resp = (
                self.client.table("price_history")
                .delete()
                .lt("price_date", cutoff.isoformat())
                .execute()
            )
            # supabase-py may not return affected row count reliably; return 0 if absent
            count = getattr(resp, "count", None)
            if count is not None:
                logger.info(f"🧹 Pruned {count} price_history rows older than {cutoff}")
                return count
            logger.info(f"🧹 Pruned price_history older than {cutoff}")
            return 0
        except Exception as e:
            logger.error(f"Failed to prune price_history: {e}")
            return 0

    # ========================================================================
    # UPSERT METHODS - Financial Statements
    # ========================================================================
    async def upsert_income_statements(
        self, rows: list[IncomeStatementRow]
    ) -> dict[str, Any]:
        if not rows:
            logger.debug("No income statements to upsert")
            return {"count": 0}
        try:
            # Deduplicate by key
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            dedup = list(seen.values())

            data = [DatabaseSerializer.serialize(r.model_dump()) for r in dedup]
            response = self.client.table('income_statements').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()
            # Post-write verification (sample first + last rows)
            if dedup:
                # Verify first row
                first_row = dedup[0]
                verify_issues = verify_database_write(
                    supabase=self.client,
                    table="income_statements",
                    company_id=first_row.company_id,
                    fiscal_year=first_row.fiscal_year,
                    fiscal_quarter=first_row.fiscal_quarter,
                    expected_values={
                        "revenue": first_row.revenue,
                        "net_income": first_row.net_income,
                        "gross_profit": first_row.gross_profit,
                    },
                    symbol="(upsert)"
                )

                if verify_issues:
                    logger.error(
                        "[DQ] Income statement post-write verification failed: %d issues",
                        len(verify_issues)
                    )
            # Zero rows back when we sent rows in = constraint violation.
            returned = len(response.data) if response.data is not None else -1
            if returned == 0 and len(data) > 0:
                logger.error(
                    "[UPSERT][income_statements] Sent %d rows, got 0 back. "
                    "Likely CHECK constraint failure — data_source='%s' may be invalid.",
                    len(data), data[0].get("data_source", "MISSING") if data else "N/A",
                )
            else:
                logger.info("✅ Upserted %d income statement rows", len(dedup))
            return response.data or {"count": len(dedup)}
        except Exception as e:
            logger.error(f"Failed to upsert income statements: {e!s}")
            raise

    async def upsert_balance_sheets(
        self, rows: list[BalanceSheetRow]
    ) -> dict[str, Any]:
        if not rows:
            logger.debug("No balance sheets to upsert")
            return {"count": 0}
        try:
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            dedup = list(seen.values())

            data = [DatabaseSerializer.serialize(r.model_dump()) for r in dedup]
            response = self.client.table('balance_sheets').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()

            # Post-write verification (sample first row)
            if dedup:
                first_row = dedup[0]
                verify_issues = verify_database_write(
                    supabase=self.client,
                    table="balance_sheets",
                    company_id=first_row.company_id,
                    fiscal_year=first_row.fiscal_year,
                    fiscal_quarter=first_row.fiscal_quarter,
                    expected_values={
                        "total_assets": first_row.total_assets,
                        "total_liabilities": first_row.total_liabilities,
                        "shareholders_equity": first_row.shareholders_equity,
                    },
                    symbol="(upsert)"
                )

                if verify_issues:
                    logger.error(
                        "[DQ] Balance sheet post-write verification failed: %d issues",
                        len(verify_issues)
                    )

            returned = len(response.data) if response.data is not None else -1
            if returned == 0 and len(data) > 0:
                logger.error(
                    "[UPSERT][balance_sheets] Sent %d rows, got 0 back. "
                    "Likely CHECK constraint failure — data_source='%s' may be invalid.",
                    len(data), data[0].get("data_source", "MISSING") if data else "N/A",
                )
            else:
                logger.info("✅ Upserted %d balance sheet rows", len(dedup))
            return response.data or {"count": len(dedup)}
        except Exception as e:
            logger.error(f"Failed to upsert balance sheets: {e!s}")
            raise

    async def upsert_cash_flows(
        self, rows: list[CashFlowRow]
    ) -> dict[str, Any]:
        if not rows:
            logger.debug("No cash flows to upsert")
            return {"count": 0}
        try:
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            dedup = list(seen.values())

            data = [DatabaseSerializer.serialize(r.model_dump()) for r in dedup]
            response = self.client.table('cash_flow_statements').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()

            # Post-write verification (sample first row)
            if dedup:
                first_row = dedup[0]
                verify_issues = verify_database_write(
                    supabase=self.client,
                    table="cash_flow_statements",
                    company_id=first_row.company_id,
                    fiscal_year=first_row.fiscal_year,
                    fiscal_quarter=first_row.fiscal_quarter,
                    expected_values={
                        "cash_from_operating_activities": first_row.cash_from_operating_activities,
                        "cash_from_investing_activities": first_row.cash_from_investing_activities,
                        "capital_expenditures": first_row.capital_expenditures,
                    },
                    symbol="(upsert)"
                )

                if verify_issues:
                    logger.error(
                        "[DQ] Cash flow post-write verification failed: %d issues",
                        len(verify_issues)
                    )

            returned = len(response.data) if response.data is not None else -1
            if returned == 0 and len(data) > 0:
                logger.error(
                    "[UPSERT][cash_flow_statements] Sent %d rows, got 0 back. "
                    "Likely CHECK constraint failure — data_source='%s' may be invalid.",
                    len(data), data[0].get("data_source", "MISSING") if data else "N/A",
                )
            else:
                logger.info("✅ Upserted %d cash flow rows", len(dedup))
            return response.data or {"count": len(dedup)}
        except Exception as e:
            logger.error(f"Failed to upsert cash flows: {e!s}")
            raise

    async def upsert_earnings(
        self, rows: list[EarningsRow]
    ) -> dict[str, Any]:
        if not rows:
            logger.debug("No earnings to upsert")
            return {"count": 0}
        try:
            seen = {}
            for row in rows:
                key = (row.company_id, row.fiscal_year, row.fiscal_quarter)
                seen[key] = row
            dedup = list(seen.values())

            data = [DatabaseSerializer.serialize(r.model_dump()) for r in dedup]
            response = self.client.table('earnings').upsert(
                data,
                on_conflict='company_id,fiscal_year,fiscal_quarter'
            ).execute()
            logger.info(f"✅ Upserted {len(dedup)} earnings rows")
            return response.data or {"count": len(dedup)}
        except Exception as e:
            logger.error(f"Failed to upsert earnings: {e!s}")
            raise

    async def upsert_dividends(
        self, rows: list[DividendRow]
    ) -> dict[str, Any]:
        if not rows:
            logger.debug("No dividends to upsert")
            return {"count": 0}
        try:
            # Deduplicate by (company_id, ex_dividend_date)
            seen = {}
            for row in rows:
                key = (row.company_id, row.ex_dividend_date)
                seen[key] = row
            dedup = list(seen.values())

            data = [DatabaseSerializer.serialize(r.model_dump()) for r in dedup]
            response = self.client.table('dividend_history').upsert(
                data,
                on_conflict='company_id,ex_dividend_date'
            ).execute()
            logger.info(f"✅ Upserted {len(dedup)} dividend rows")
            return response.data or {"count": len(dedup)}
        except Exception as e:
            logger.error(f"Failed to upsert dividends: {e!s}")
            raise

    # ========================================================================
    # UPSERT METHODS (Market Data Scheduler) + Conflict Detection
    # ========================================================================
    async def upsert_price_history(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upsert monthly OHLCV rows (unique by company_id, price_date)."""
        if not rows:
            return {"count": 0}
        # Defensive: close_price is NOT NULL; null-OHLC rows are provider garbage
        # (delisted/suspended days) and must not reach the database.
        valid_rows = [r for r in rows if r.get("close_price") is not None]
        dropped = len(rows) - len(valid_rows)
        if dropped:
            logger.warning(
                "[PRICE] Dropping %d/%d price_history rows with null close_price",
                dropped, len(rows),
            )
        if not valid_rows:
            return {"count": 0}
        rows = valid_rows

        # Defensive clamp: numeric(12,4) limit is 99,999,999.9999
        _PRICE_MAX = 99_999_999.9999
        _PRICE_FIELDS = ("open_price", "close_price", "high_price", "low_price")
        clamped = 0
        for r in rows:
            for f in _PRICE_FIELDS:
                val = r.get(f)
                if val is not None:
                    try:
                        fval = float(val)
                        if abs(fval) >= _PRICE_MAX:
                            r[f] = round(_PRICE_MAX if fval > 0 else -_PRICE_MAX, 4)
                            clamped += 1
                    except (TypeError, ValueError):
                        pass
        if clamped:
            logger.warning("[PRICE] Clamped %d overflow price values to numeric(12,4) limit", clamped)

        try:
            # Optional conflict detection (row-by-row check)
            if getattr(settings, "ENABLE_CONFLICT_DETECTION", True):
                threshold = float(getattr(settings, "CONFLICT_DETECTION_THRESHOLD_PCT", 1.0))
                for r in rows:
                    cid, pdate = r.get("company_id"), r.get("price_date")
                    existing = None
                    try:
                        existing = (
                            self.client.table("price_history")
                            .select("open_price, close_price, high_price, low_price, volume, data_source")
                            .eq("company_id", cid)
                            .eq("price_date", pdate)
                            .single()
                            .execute()
                        ).data
                    except Exception:
                        existing = None

                    if existing:
                        for field in ["open_price", "close_price", "high_price", "low_price"]:
                            pct = self._pct_diff(existing.get(field), r.get(field))
                            if pct is not None and pct >= threshold:
                                await self.log_conflict(
                                    company_id=cid,
                                    fiscal_year=None,
                                    fiscal_quarter=None,
                                    field=field,
                                    existing_value=existing.get(field),
                                    existing_source=existing.get("data_source") or "unknown",
                                    new_value=r.get(field),
                                    new_source=r.get("data_source") or "unknown",
                                    pct_diff=pct,
                                )
                        if existing.get("volume") and r.get("volume"):
                            pct_vol = self._pct_diff(existing.get("volume"), r.get("volume"))
                            if pct_vol is not None and pct_vol >= threshold:
                                await self.log_conflict(
                                    company_id=cid,
                                    fiscal_year=None,
                                    fiscal_quarter=None,
                                    field="volume",
                                    existing_value=existing.get("volume"),
                                    existing_source=existing.get("data_source") or "unknown",
                                    new_value=r.get("volume"),
                                    new_source=r.get("data_source") or "unknown",
                                    pct_diff=pct_vol,
                                )

            # Upsert (dedupe client-side by key)
            seen = {}
            for r in rows:
                key = (r.get("company_id"), r.get("price_date"))
                seen[key] = r
            dedup = list(seen.values())

            count = await self._chunked_upsert(
                table="price_history",
                rows=dedup,
                on_conflict="company_id,price_date",
            )
            return {"count": count}

        except Exception as e:
            logger.error(f"Failed to upsert price_history: {e}")
            raise

    async def upsert_splits(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upsert split events (unique by company_id, report_date)."""
        if not rows:
            return {"count": 0}
        try:
            if getattr(settings, "ENABLE_CONFLICT_DETECTION", True):
                for r in rows:
                    cid, rdate = r.get("company_id"), r.get("report_date")
                    existing = None
                    try:
                        existing = (
                            self.client.table("splits")
                            .select("split_factor, reverse_split, data_source")
                            .eq("company_id", cid)
                            .eq("report_date", rdate)
                            .single()
                            .execute()
                        ).data
                    except Exception:
                        existing = None
                    if existing:
                        # Categorical fields (split_factor is VARCHAR, reverse_split is
                        # BOOLEAN) cannot be stored in data_conflicts' numeric columns
                        # without violating check_conflict_values (both values NULL).
                        # Log these as informational mismatches only when values differ;
                        # skip the numeric conflict table for non-numeric fields.
                        if (existing.get("split_factor") or "") != (r.get("split_factor") or ""):
                            logger.info(
                                "[SPLIT] split_factor mismatch for company_id=%s "
                                "report_date=%s: existing=%r new=%r source=%s→%s",
                                cid, rdate,
                                existing.get("split_factor"),
                                r.get("split_factor"),
                                existing.get("data_source"),
                                r.get("data_source"),
                            )
                        if bool(existing.get("reverse_split")) != bool(r.get("reverse_split")):
                            logger.info(
                                "[SPLIT] reverse_split mismatch for company_id=%s "
                                "report_date=%s: existing=%r new=%r source=%s→%s",
                                cid, rdate,
                                existing.get("reverse_split"),
                                r.get("reverse_split"),
                                existing.get("data_source"),
                                r.get("data_source"),
                            )

            seen = {}
            for r in rows:
                key = (r.get("company_id"), r.get("report_date"))
                seen[key] = r
            dedup = list(seen.values())

            count = await self._chunked_upsert(
                table="splits",
                rows=dedup,
                on_conflict="company_id,report_date",
            )
            return {"count": count}

        except Exception as e:
            logger.error(f"Failed to upsert splits: {e}")
            raise

    async def upsert_revenue_forecast(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upsert revenue forecasts (unique by company_id, report_date, period_type, provider)."""
        if not rows:
            return {"count": 0}
        try:
            if getattr(settings, "ENABLE_CONFLICT_DETECTION", True):
                threshold = float(getattr(settings, "CONFLICT_DETECTION_THRESHOLD_PCT", 1.0))
                for r in rows:
                    cid, rdate = r.get("company_id"), r.get("report_date")
                    ptype, provider = r.get("period_type"), r.get("provider") or "defeatbeta"
                    existing = None
                    try:
                        existing = (
                            self.client.table("revenue_forecast")
                            .select(
                                "estimate_revenue_growth, number_of_analysts, estimate_avg_revenue, "
                                "estimate_high_revenue, estimate_low_revenue, year_ago_estimate_avg_revenue, "
                                "data_source, provider, period_type"
                            )
                            .eq("company_id", cid)
                            .eq("report_date", rdate)
                            .eq("period_type", ptype)
                            .eq("provider", provider)
                            .single()
                            .execute()
                        ).data
                    except Exception:
                        existing = None

                    if existing:
                        for field in [
                            "estimate_revenue_growth",
                            "estimate_avg_revenue",
                            "estimate_high_revenue",
                            "estimate_low_revenue",
                            "year_ago_estimate_avg_revenue",
                        ]:
                            pct = self._pct_diff(existing.get(field), r.get(field))
                            if pct is not None and pct >= threshold:
                                await self.log_conflict(
                                    company_id=cid,
                                    fiscal_year=None,
                                    fiscal_quarter=None,
                                    field=field,
                                    existing_value=existing.get(field),
                                    existing_source=existing.get("data_source") or existing.get("provider") or "unknown",
                                    new_value=r.get(field),
                                    new_source=r.get("provider") or "unknown",
                                    pct_diff=pct,
                                )

            for r in rows:
                if r.get("forecast_id") is None:
                    r["forecast_id"] = _deterministic_id(
                        r.get("company_id"), r.get("report_date"),
                        r.get("period_type"), r.get("provider") or "defeatbeta",
                    )

            seen = {}
            for r in rows:
                key = (r.get("company_id"), r.get("report_date"), r.get("period_type"), r.get("provider") or "defeatbeta")
                seen[key] = r
            dedup = list(seen.values())

            count = await self._chunked_upsert(
                table="revenue_forecast",
                rows=dedup,
                on_conflict="company_id,report_date,period_type,provider",
            )
            return {"count": count}

        except Exception as e:
            logger.error(f"Failed to upsert revenue_forecast: {e}")
            raise

    async def upsert_earnings_forecast(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upsert earnings forecasts (unique by company_id, report_date, period_type, provider)."""
        if not rows:
            return {"count": 0}
        try:
            if getattr(settings, "ENABLE_CONFLICT_DETECTION", True):
                threshold = float(getattr(settings, "CONFLICT_DETECTION_THRESHOLD_PCT", 1.0))
                for r in rows:
                    cid, rdate = r.get("company_id"), r.get("report_date")
                    ptype, provider = r.get("period_type"), r.get("provider") or "defeatbeta"
                    existing = None
                    try:
                        existing = (
                            self.client.table("earnings_forecast")
                            .select(
                                "estimate_eps_growth, estimate_avg_eps, estimate_high_eps, estimate_low_eps, "
                                "number_of_analysts, data_source, provider, period_type"
                            )
                            .eq("company_id", cid)
                            .eq("report_date", rdate)
                            .eq("period_type", ptype)
                            .eq("provider", provider)
                            .single()
                            .execute()
                        ).data
                    except Exception:
                        existing = None

                    if existing:
                        for field in [
                            "estimate_eps_growth",
                            "estimate_avg_eps",
                            "estimate_high_eps",
                            "estimate_low_eps",
                        ]:
                            pct = self._pct_diff(existing.get(field), r.get(field))
                            if pct is not None and pct >= threshold:
                                await self.log_conflict(
                                    company_id=cid,
                                    fiscal_year=None,
                                    fiscal_quarter=None,
                                    field=field,
                                    existing_value=existing.get(field),
                                    existing_source=existing.get("data_source") or existing.get("provider") or "unknown",
                                    new_value=r.get(field),
                                    new_source=r.get("provider") or "unknown",
                                    pct_diff=pct,
                                )

            for r in rows:
                if r.get("earnings_forecast_id") is None:
                    r["earnings_forecast_id"] = _deterministic_id(
                        r.get("company_id"), r.get("report_date"),
                        r.get("period_type"), r.get("provider") or "defeatbeta",
                    )

            seen = {}
            for r in rows:
                key = (r.get("company_id"), r.get("report_date"), r.get("period_type"), r.get("provider") or "defeatbeta")
                seen[key] = r
            dedup = list(seen.values())

            count = await self._chunked_upsert(
                table="earnings_forecast",
                rows=dedup,
                on_conflict="company_id,report_date,period_type,provider",
            )
            return {"count": count}

        except Exception as e:
            logger.error(f"Failed to upsert earnings_forecast: {e}")
            raise

    async def upsert_company_summary(
        self, snapshot: dict[str, Any]
    ) -> dict[str, Any]:
        """Daily company summary snapshot (unique by company_id, snapshot_date, provider)."""
        if not snapshot:
            return {"count": 0}
        try:
            if getattr(settings, "ENABLE_CONFLICT_DETECTION", True):
                threshold = float(getattr(settings, "CONFLICT_DETECTION_THRESHOLD_PCT", 1.0))
                cid = snapshot.get("company_id")
                snap_date = snapshot.get("snapshot_date")
                provider = snapshot.get("provider") or "defeatbeta"
                existing = None
                try:
                    resp = (
                        self.client.table("company_summary")
                        .select(
                            "market_cap, enterprise_value, shares_outstanding, implied_shares_outstanding, "
                            "beta, trailing_pe, forward_pe, trailing_eps, forward_eps, "
                            "enterprise_to_ebitda, enterprise_to_revenue, peg_ratio, currency, provider"
                        )
                        .eq("company_id", cid)
                        .eq("snapshot_date", snap_date)
                        .eq("provider", provider)
                        .limit(1)
                        .execute()
                    )
                    existing = resp.data[0] if resp.data else None
                except Exception:
                    existing = None

                if existing:
                    for field in [
                        "market_cap", "enterprise_value", "shares_outstanding", "implied_shares_outstanding",
                        "beta", "trailing_pe", "forward_pe", "trailing_eps", "forward_eps",
                        "enterprise_to_ebitda", "enterprise_to_revenue", "peg_ratio",
                    ]:
                        pct = self._pct_diff(existing.get(field), snapshot.get(field))
                        if pct is not None and pct >= threshold:
                            await self.log_conflict(
                                company_id=cid,
                                fiscal_year=None,
                                fiscal_quarter=None,
                                field=field,
                                existing_value=existing.get(field),
                                existing_source=existing.get("provider") or "unknown",
                                new_value=snapshot.get(field),
                                new_source=provider,
                                pct_diff=pct,
                            )

            payload = [DatabaseSerializer.serialize(snapshot)]
            self.client.table("company_summary").upsert(
                payload,
                on_conflict="company_id,snapshot_date,provider",
            ).execute()
            return {"count": 1}

        except Exception as e:
            logger.error(f"Failed to upsert company_summary: {e}")
            raise


    # ========================================================================
    # DERIVED METRICS (Phase 4)
    # ========================================================================
    async def upsert_derived_financial_metrics(
        self, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Upsert derived metrics (unique by company_id, fiscal_year, fiscal_quarter).

        Supports both annual (fiscal_quarter=None) and quarterly (fiscal_quarter=1..4) rows.
        The 3-column conflict key allows annual and quarterly rows to coexist.
        """
        if not rows:
            return {"count": 0}
        try:
            seen = {}
            for r in rows:
                key = (r.get("company_id"), r.get("fiscal_year"), r.get("fiscal_quarter"))
                seen[key] = r
            dedup = list(seen.values())

            count = await self._chunked_upsert(
                table="financial_ratios",
                rows=dedup,
                on_conflict="company_id,fiscal_year,fiscal_quarter",
            )
            return {"count": count}
        except Exception as e:
            logger.error(f"Failed to upsert financial_ratios: {e}")
            raise

    # ========================================================================
    # COMPANY METADATA UPDATES / QUERIES
    # ========================================================================
    async def get_companies_for_market_data(
        self,
        statuses: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        statuses = statuses or ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"]
        try:
            resp = (
                self.client.table("companies")
                .select("company_id, ticker_symbol, data_completeness_status, security_type")
                .in_("data_completeness_status", statuses)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to fetch companies for market data: {e}")
            raise

    async def get_active_companies_for_market_data(self) -> list[dict[str, Any]]:
        """
        Returns companies that are in ANY user's portfolio or watchlist.
        This is the active set — only ~150 companies instead of all 3,114.

        Two-step approach:
        1. Get distinct symbols from portfolio_holdings across all users
        2. Get distinct company_ids from watchlist_items across all users
        3. Deduplicate and return company rows

        Market data refresh only needs to process this subset.
        """
        try:
            active_ids: set = set()

            # Step 1: symbols from portfolio_holdings
            ph = self.client.table("portfolio_holdings").select("symbol").execute()
            portfolio_symbols = list(set(h["symbol"] for h in (ph.data or [])))
            if portfolio_symbols:
                ph_comps = (
                    self.client.table("companies")
                    .select("company_id")
                    .in_("ticker_symbol", portfolio_symbols)
                    .execute()
                )
                for c in (ph_comps.data or []):
                    if c.get("company_id"):
                        active_ids.add(c["company_id"])

            # Step 2: company_ids from watchlist_items
            wl = self.client.table("watchlist_items").select("company_id").execute()
            for w in (wl.data or []):
                if w.get("company_id"):
                    active_ids.add(w["company_id"])

            if not active_ids:
                return []

            # Step 3: Fetch full company rows for active IDs
            resp = (
                self.client.table("companies")
                .select("company_id, ticker_symbol, data_completeness_status, security_type, next_earnings_date, exchange")
                .in_("company_id", list(active_ids))
                .execute()
            )
            return resp.data or []

        except Exception as e:
            logger.error(f"Failed to fetch active companies for market data: {e}")
            return []

    async def update_company_refresh_metadata(
        self,
        company_id: int,
        last_fiscal_year: int,
        last_fiscal_quarter: int | None,
        is_first_load: bool = False,
        next_earnings_date: date | None = None,
    ) -> dict[str, Any]:
        try:
            now = now_utc()
            status = "COMPLETE" if is_first_load else "CURRENT"
            update_data = {
                'last_financial_refresh_at': now.isoformat(),
                'last_refreshed_fiscal_year': last_fiscal_year,
                'last_refreshed_fiscal_quarter': last_fiscal_quarter,
                'data_completeness_status': status,
            }
            if is_first_load:
                update_data['first_financial_data_loaded_at'] = now.isoformat()
            if next_earnings_date:
                update_data['next_earnings_date'] = next_earnings_date.isoformat()

            response = self.client.table('companies').update(update_data).eq(
                'company_id', company_id
            ).execute()
            logger.info(
                f"✅ Updated metadata for company {company_id}: "
                f"FY{last_fiscal_year}Q{last_fiscal_quarter or 'Annual'} | Status: {status}"
            )
            return response.data[0] if response.data else {}

        except Exception as e:
            logger.error(f"Failed to update metadata for company {company_id}: {e!s}")
            raise

    async def update_next_earnings_date(self, company_id: int, earnings_date: date) -> None:
        """Lightweight update of next_earnings_date only (no fiscal year/quarter churn)."""
        try:
            self.client.table("companies").update({
                "next_earnings_date": earnings_date.isoformat(),
                "data_completeness_status": "CURRENT",
            }).eq("company_id", company_id).execute()
        except Exception as e:
            logger.warning("Failed to update next_earnings_date for company %d: %s", company_id, e)

    async def get_companies_with_upcoming_earnings(
        self,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        try:
            response = self.client.table('companies').select(
                'company_id, ticker_symbol, next_earnings_date, '
                'last_refreshed_fiscal_year, last_refreshed_fiscal_quarter, '
                'data_completeness_status, first_financial_data_loaded_at'
            ).gte(
                'next_earnings_date', start_date.isoformat()
            ).lte(
                'next_earnings_date', end_date.isoformat()
            ).in_(
                'data_completeness_status',
                ['INITIAL', 'PARTIAL', 'COMPLETE', 'CURRENT']
            ).or_(
                'security_type.eq.stock,security_type.is.null'
            ).execute()

            count = len(response.data or [])
            logger.info(
                f"Found {count} companies with earnings between {start_date} and {end_date}"
            )
            return response.data or []

        except Exception as e:
            logger.error(f"Failed to query companies with upcoming earnings: {e!s}")
            raise

    async def get_stale_financial_companies(
        self,
        fresh_cutoff: date,
        consult_cutoff: date,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Companies that have financial data loaded but whose latest income
        statement predates fresh_cutoff (i.e. they missed the earnings-window
        refresh because next_earnings_date was NULL/out-of-window), gated by
        consult_cutoff so a company consulted very recently is not retried.

        Freshness is judged on income_statements.period_end_date: a company is
        "fresh" when it has at least one statement row with
        period_end_date >= fresh_cutoff.

        Two-step approach (income_statements is large; PostgREST caps response
        size, so the fresh-ID query is paginated):
          1. Candidates = companies with first_financial_data_loaded_at set,
             status in (INITIAL, PARTIAL, COMPLETE, CURRENT), and a stock or
             unspecified security type.
          2. Fresh IDs  = distinct company_ids in income_statements with
             period_end_date >= fresh_cutoff (paginated pages of 1000).
          3. Stale      = candidates minus fresh, where last_financial_refresh_at
             is NULL or < consult_cutoff. Sorted so never-refreshed companies
             come first, then oldest refresh, capped at `limit`.
        """
        try:
            # Step 1: candidates with financial data loaded
            resp = (
                self.client.table("companies")
                .select(
                    "company_id, ticker_symbol, data_completeness_status, "
                    "first_financial_data_loaded_at, last_financial_refresh_at"
                )
                .in_(
                    "data_completeness_status",
                    ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"],
                )
                .not_.is_("first_financial_data_loaded_at", "null")
                .or_("security_type.eq.stock,security_type.is.null")
                .execute()
            )
            candidates = resp.data or []
            if not candidates:
                return []

            # Step 2: paginate income_statements for fresh company_ids
            fresh_ids: set = set()
            page_size = 1000
            offset = 0
            while True:
                page = (
                    self.client.table("income_statements")
                    .select("company_id")
                    .gte("period_end_date", fresh_cutoff.isoformat())
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = page.data or []
                for r in rows:
                    cid = r.get("company_id")
                    if cid is not None:
                        fresh_ids.add(cid)
                if len(rows) < page_size:
                    break
                offset += page_size

            # Step 3: candidates minus fresh, with consult gate
            consult_cutoff_str = consult_cutoff.isoformat()
            stale = []
            for c in candidates:
                cid = c.get("company_id")
                if cid is None or cid in fresh_ids:
                    continue
                last_refresh = c.get("last_financial_refresh_at")
                if last_refresh and str(last_refresh) >= consult_cutoff_str:
                    continue  # consulted very recently; give it more time
                stale.append(c)

            # Never-refreshed (NULL) first, then oldest refresh — deterministic
            stale.sort(
                key=lambda c: (
                    c.get("last_financial_refresh_at") is not None,
                    c.get("last_financial_refresh_at") or "",
                )
            )
            return stale[:limit]

        except Exception as e:
            logger.error(f"Failed to query stale financial companies: {e!s}")
            raise

    async def get_financial_candidates(self) -> list[dict[str, Any]]:
        """
        Companies eligible for the freshness coverage snapshot: financial data
        loaded (first_financial_data_loaded_at set), status in (INITIAL, PARTIAL,
        COMPLETE, CURRENT), and a stock or unspecified security type.

        Same candidate predicate as get_stale_financial_companies step 1.
        """
        try:
            resp = (
                self.client.table("companies")
                .select("company_id, first_financial_data_loaded_at, data_completeness_status")
                .in_(
                    "data_completeness_status",
                    ["INITIAL", "PARTIAL", "COMPLETE", "CURRENT"],
                )
                .not_.is_("first_financial_data_loaded_at", "null")
                .or_("security_type.eq.stock,security_type.is.null")
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to query financial candidates: {e!s}")
            raise

    async def get_fresh_financial_company_ids(self, fresh_cutoff: date) -> set:
        """
        Distinct company_ids in income_statements with a period_end_date >=
        fresh_cutoff (paginated: income_statements is large and PostgREST caps
        response size). Used by the freshness monitor financial domain.
        """
        try:
            fresh_ids: set = set()
            page_size = 1000
            offset = 0
            while True:
                page = (
                    self.client.table("income_statements")
                    .select("company_id")
                    .gte("period_end_date", fresh_cutoff.isoformat())
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = page.data or []
                for r in rows:
                    cid = r.get("company_id")
                    if cid is not None:
                        fresh_ids.add(cid)
                if len(rows) < page_size:
                    break
                offset += page_size
            return fresh_ids
        except Exception as e:
            logger.error(f"Failed to query fresh financial company ids: {e!s}")
            raise

    async def get_financial_periods_in_range(
        self, start: date, end: date
    ) -> list[dict[str, Any]]:
        """
        (company_id, period_end_date) statement rows within [start, end];
        used by the reconciliation planner to detect missing periods.
        """
        try:
            rows_out: list[dict[str, Any]] = []
            page_size = 1000
            offset = 0
            while True:
                page = (
                    self.client.table("income_statements")
                    .select("company_id, period_end_date")
                    .gte("period_end_date", start.isoformat())
                    .lte("period_end_date", end.isoformat())
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = page.data or []
                rows_out.extend(rows)
                if len(rows) < page_size:
                    break
                offset += page_size
            return rows_out
        except Exception as e:
            logger.error(f"Failed to query financial periods in range: {e!s}")
            raise

    async def get_tracked_investors(self) -> list[dict[str, Any]]:
        """Super-investor rows (is_super_investor = true) for coverage + reconciliation."""
        try:
            resp = (
                self.client.table("institutional_investors")
                .select("investor_id, cik, investor_name, firm_name, investor_tag")
                .eq("is_super_investor", True)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(f"Failed to query tracked investors: {e!s}")
            raise

    async def get_investor_periods_in_range(
        self, start: date, end: date
    ) -> list[dict[str, Any]]:
        """
        (investor_id, quarter_end_date) holding rows within [start, end];
        used by the freshness monitor and reconciliation planner.
        """
        try:
            rows_out: list[dict[str, Any]] = []
            page_size = 1000
            offset = 0
            while True:
                page = (
                    self.client.table("institutional_holdings")
                    .select("investor_id, quarter_end_date")
                    .gte("quarter_end_date", start.isoformat())
                    .lte("quarter_end_date", end.isoformat())
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = page.data or []
                rows_out.extend(rows)
                if len(rows) < page_size:
                    break
                offset += page_size
            return rows_out
        except Exception as e:
            logger.error(f"Failed to query investor periods in range: {e!s}")
            raise

    async def append_freshness_snapshot(self, snapshot: dict[str, Any]) -> None:
        """Upsert one freshness coverage snapshot row (idempotent per domain+as_of)."""
        try:
            self.client.table("freshness_snapshot").upsert(
                snapshot, on_conflict="domain,as_of"
            ).execute()
        except Exception as e:
            logger.error(f"Failed to upsert freshness snapshot: {e!s}")
            raise

    async def get_companies_with_financial_data(self) -> list[dict[str, Any]]:
        """
        Return companies that have at least one income statement row.

        This is the "tracked" set for earnings-calendar syncing: the active
        portfolio/watchlist set (~150) misses companies that are tracked for
        financials but not in any user's portfolio. Every company with loaded
        financial data needs its next_earnings_date maintained, otherwise it
        stays invisible to the earnings-window refresh.

        Paginates income_statements (PostgREST caps responses at 1000 rows),
        then fetches the matching company rows.
        """
        try:
            ids: set = set()
            page_size = 1000
            offset = 0
            while True:
                page = (
                    self.client.table("income_statements")
                    .select("company_id")
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = page.data or []
                for r in rows:
                    cid = r.get("company_id")
                    if cid is not None:
                        ids.add(cid)
                if len(rows) < page_size:
                    break
                offset += page_size

            if not ids:
                return []

            resp = (
                self.client.table("companies")
                .select(
                    "company_id, ticker_symbol, data_completeness_status, "
                    "security_type, next_earnings_date, exchange"
                )
                .in_("company_id", list(ids))
                .execute()
            )
            return resp.data or []

        except Exception as e:
            logger.error(f"Failed to fetch companies with financial data: {e!s}")
            raise

    async def get_company_refresh_info(
        self, company_id: int
    ) -> CompanyRefreshInfo | None:
        """Get company's refresh metadata for smart filtering."""
        try:
            response = self.client.table('companies').select(
                'company_id, ticker_symbol, exchange, '
                'first_financial_data_loaded_at, last_financial_refresh_at, '
                'last_refreshed_fiscal_year, last_refreshed_fiscal_quarter, '
                'data_completeness_status, next_earnings_date, '
                'last_price_refresh_at'
            ).eq('company_id', company_id).limit(1).execute()

            if not response.data:
                logger.warning(f"Company {company_id} not found")
                return None

            data = response.data[0]
            return CompanyRefreshInfo(
                company_id=data['company_id'],
                ticker_symbol=data['ticker_symbol'],
                exchange=data.get('exchange'),
                first_financial_data_loaded_at=(
                    parse_db_timestamp(data['first_financial_data_loaded_at'])
                    if data.get('first_financial_data_loaded_at')
                    else None
                ),
                last_financial_refresh_at=(
                    parse_db_timestamp(data['last_financial_refresh_at'])
                    if data.get('last_financial_refresh_at')
                    else None
                ),
                last_refreshed_fiscal_year=data.get('last_refreshed_fiscal_year'),
                last_refreshed_fiscal_quarter=data.get('last_refreshed_fiscal_quarter'),
                data_completeness_status=data.get('data_completeness_status', 'INITIAL'),
                next_earnings_date=(
                    parse_db_timestamp(data['next_earnings_date']).date()
                    if data.get('next_earnings_date')
                    else None
                ),
                last_price_refresh_at=(
                    parse_db_timestamp(data['last_price_refresh_at'])
                    if data.get('last_price_refresh_at')
                    else None
                ),
            )

        except Exception as e:
            logger.error(f"Failed to get refresh info for company {company_id}: {e!s}")
            raise

    async def update_price_refresh_marker(self, company_id: int) -> None:
        """Update last_price_refresh_at to now() for incremental tracking."""
        try:
            update_data = DatabaseSerializer.serialize(
                {'last_price_refresh_at': now_utc()}
            )
            self.client.table('companies').update(update_data).eq(
                'company_id', company_id
            ).execute()
            logger.debug(f"Updated last_price_refresh_at for company_id={company_id}")
        except Exception as e:
            logger.error(f"Failed to update price refresh marker for {company_id}: {e!s}")

    async def update_price_attempt_marker(self, company_id: int) -> None:
        try:
            self.client.table('companies').update({
                'last_price_attempt_at': now_utc().isoformat(),
            }).eq('company_id', company_id).execute()
        except Exception:
            pass

    async def update_price_success_marker(self, company_id: int) -> None:
        try:
            self.client.table('companies').update({
                'last_price_success_at': now_utc().isoformat(),
                'consecutive_price_failures': 0,
            }).eq('company_id', company_id).execute()
        except Exception:
            pass

    async def increment_price_failures(self, company_id: int) -> None:
        try:
            self.client.table('companies').update({
                'consecutive_price_failures': 1,
            }).eq('company_id', company_id).execute()
        except Exception:
            pass

    # ========================================================================
    # BATCH OPERATIONS
    # ========================================================================
    async def upsert_all_financials(
        self, financials: CompleteFundamentals
    ) -> dict[str, int]:
        logger.info(
            f"Upserting all financials for {financials.symbol}: "
            f"{financials.total_rows_fetched} total rows"
        )

        results = {
            'income_statements': 0,
            'balance_sheets': 0,
            'cash_flows': 0,
            'earnings': 0,
            'dividends': 0,
        }

        try:
            if financials.income_statements.rows:
                await self.upsert_income_statements(
                    financials.income_statements.rows
                )
                results['income_statements'] = len(financials.income_statements.rows)

            if financials.balance_sheets.rows:
                await self.upsert_balance_sheets(
                    financials.balance_sheets.rows
                )
                results['balance_sheets'] = len(financials.balance_sheets.rows)

            if financials.cash_flows.rows:
                await self.upsert_cash_flows(
                    financials.cash_flows.rows
                )
                results['cash_flows'] = len(financials.cash_flows.rows)

            if financials.earnings.rows:
                await self.upsert_earnings(
                    financials.earnings.rows
                )
                results['earnings'] = len(financials.earnings.rows)

            if financials.dividends.rows:
                await self.upsert_dividends(
                    financials.dividends.rows
                )
                results['dividends'] = len(financials.dividends.rows)

            total = sum(results.values())
            logger.info(
                f"✅ Upserted all financials for {financials.symbol}: "
                f"{total} rows across all tables"
            )

            return results

        except Exception as e:
            logger.error(f"Failed to upsert all financials: {e!s}")
            raise

    # ========================================================================
    # BASIC HELPERS
    # ========================================================================
    async def company_exists(self, company_id: int) -> bool:
        """Check if company exists in database."""
        try:
            response = (
                self.client.table('companies')
                .select('company_id')
                .eq('company_id', company_id)
                .limit(1)
                .execute()
            )
            return bool(response.data)
        except Exception:
            return False

    async def get_company_by_id(self, company_id: int) -> dict[str, Any] | None:
        """Get full company record."""
        try:
            response = (
                self.client.table('companies')
                .select('*')
                .eq('company_id', company_id)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception:
            return None

    async def get_company_by_symbol(
        self, symbol: str
    ) -> dict[str, Any] | None:
        """Get company by ticker symbol."""
        try:
            response = (
                self.client.table('companies')
                .select('*')
                .eq('ticker_symbol', symbol)
                .limit(1)
                .execute()
            )
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error("[get_company_by_symbol] symbol=%s error=%s", symbol, e)
            return None

    async def get_shares_history(
        self, company_id: int
    ) -> list[dict[str, Any]]:
        """
        Return annual share count rows, oldest-to-newest.

        Priority order:
          1. balance_sheets.shares_outstanding   — period-end count; correct BV/share denominator
          2. income_statements.shares_outstanding_diluted — weighted avg; acceptable fallback

        Always returns dicts with keys:
          fiscal_year, shares_outstanding_diluted, shares_outstanding_basic, _source
        so all callers remain unchanged regardless of which table provided the data.
        """
        # 1. Period-end shares from balance sheet (preferred for BV/share)
        try:
            resp = (
                self.client.table("balance_sheets")
                .select("fiscal_year, shares_outstanding")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .not_.is_("shares_outstanding", "null")
                .order("fiscal_year", desc=False)
                .execute()
            )
            if resp.data:
                logger.debug(
                    "[SHARES] company_id=%s: %d annual rows from balance_sheets (period-end)",
                    company_id, len(resp.data),
                )
                return [
                    {
                        "fiscal_year": r["fiscal_year"],
                        "shares_outstanding_diluted": r["shares_outstanding"],
                        "shares_outstanding_basic": r["shares_outstanding"],
                        "_source": "balance_sheets",
                    }
                    for r in resp.data
                ]
            logger.debug(
                "[SHARES] company_id=%s: balance_sheets.shares_outstanding empty, "
                "falling back to income_statements",
                company_id,
            )
        except Exception as e:
            logger.error(
                "[SHARES] company_id=%s: balance_sheets query failed (%s), "
                "falling back to income_statements",
                company_id, e,
            )

        # 2. Weighted-average shares from income statement (fallback)
        try:
            resp = (
                self.client.table("income_statements")
                .select("fiscal_year, shares_outstanding_diluted, shares_outstanding_basic")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .not_.is_("shares_outstanding_diluted", "null")
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            for r in rows:
                r.setdefault("_source", "income_statements")
            if rows:
                logger.debug(
                    "[SHARES] company_id=%s: %d annual rows from income_statements (weighted avg)",
                    company_id, len(rows),
                )
            return rows
        except Exception as e:
            logger.error(
                "[SHARES] company_id=%s: income_statements query also failed: %s",
                company_id, e,
            )
            return []

    async def get_company_summary_latest(
        self, company_id: int
    ) -> dict[str, Any] | None:
        """
        Return the most recent company_summary row for a company.
        Used as a fallback shares source when income_statements.shares_outstanding_diluted
        is null for all rows (e.g. defeatbeta omits share counts for some tickers).

        company_summary.shares_outstanding is reliably populated by the
        defeat_beta_provider / yfinance summary pipeline (confirmed for SIRI: 334,772,877).
        """
        try:
            resp = (
                self.client.table("company_summary")
                .select(
                    "company_id, shares_outstanding, implied_shares_outstanding, "
                    "snapshot_date, provider"
                )
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(
                "Failed to get company_summary_latest for company_id=%s: %s", company_id, e
            )
            return None

    # ========================================================================
    # UPCOMING DIVIDEND EVENTS (forward-looking predictions)
    # ========================================================================

    async def upsert_upcoming_dividend(
        self,
        company_id: int,
        ex_dividend_date: date,
        data_source: str,
        trust_score: float = 0.50,
        status: str = "predicted",
    ) -> None:
        """Upsert a forward-looking ex-dividend date into upcoming_dividend_events.
        
        UNIQUE(company_id, data_source) ensures each source has exactly one
        opinion per company.  When a provider updates its prediction, the
        old row is replaced atomically — no delete needed.
        """
        try:
            trust_scores = {"yfinance": 0.95, "finviz": 0.80, "predicted": 0.50}
            score = trust_scores.get(data_source, trust_score)

            source_status = "provider_reported" if data_source in ("yfinance", "finviz") else status

            payload = DatabaseSerializer.serialize({
                "company_id": company_id,
                "data_source": data_source,
                "ex_dividend_date": ex_dividend_date,
                "trust_score": score,
                "status": source_status,
                "source_observed_at": now_utc(),
                "updated_at": now_utc(),
            })

            self.client.table("upcoming_dividend_events").upsert(
                payload,
                on_conflict="company_id,data_source",
            ).execute()
            logger.debug(
                "[UPCOMING_DIV] Upserted %s for company_id=%s: %s (trust=%.2f, status=%s)",
                data_source, company_id, ex_dividend_date, score, source_status,
            )
        except Exception as e:
            logger.error(
                "[UPCOMING_DIV] Failed to upsert %s for company_id=%s: %s",
                data_source, company_id, e,
            )

    async def cleanup_stale_events(self, company_id: int) -> None:
        """Remove past-due upcoming events with a 14-day grace period.
        
        The grace period prevents gaps when a provider hasn't refreshed yet.
        Only affects upcoming_dividend_events — never touches dividend_history.
        """
        try:
            cutoff = (now_utc().date() - timedelta(days=14)).isoformat()
            self.client.table("upcoming_dividend_events")\
                .delete()\
                .eq("company_id", company_id)\
                .lt("ex_dividend_date", cutoff)\
                .execute()
        except Exception as e:
            logger.error(
                "[UPCOMING_DIV] Failed to cleanup stale events for company_id=%s: %s",
                company_id, e,
            )

    # ========================================================================
    # PORTFOLIO SNAPSHOT PRICE METHODS
    # ========================================================================

    async def get_latest_prices(
        self, company_ids: list[int], target_date: date,
        include_current_fallback: bool = True,
    ) -> dict[int, dict]:
        if not company_ids:
            return {}

        from shared.split_utils import get_split_factors_from_rows
        try:
            splits_res = (
                self.client.table("splits")
                .select("company_id, report_date, split_factor")
                .in_("company_id", company_ids)
                .execute()
            )
            split_factors = get_split_factors_from_rows(splits_res.data or [])
        except Exception:
            split_factors = {}

        result = (
            self.client.table("price_history")
            .select("company_id, price_date, close_price")
            .in_("company_id", company_ids)
            .lte("price_date", target_date.isoformat())
            .execute()
        )

        latest_by_company: dict[int, dict] = {}
        for row in result.data or []:
            cid = row["company_id"]
            pd = row["price_date"]
            if isinstance(pd, str):
                pd = date.fromisoformat(pd)
            elif isinstance(pd, datetime):
                pd = pd.date()

            existing = latest_by_company.get(cid)
            if existing is None or pd > existing["price_date"]:
                px = float(row["close_price"])
                if cid in split_factors:
                    cumulative_factor = 1.0
                    for sd, adj in split_factors[cid]:
                        if pd < sd:
                            cumulative_factor *= adj
                    px *= cumulative_factor
                latest_by_company[cid] = {
                    "price": px,
                    "price_date": pd,
                }

        # Fall back to current_market_data ONLY when explicitly requested
        # (daily job uses today's prices). For historical backfill, never inject
        # today's price for a past date — callers should handle missing prices.
        if include_current_fallback:
            missing = [cid for cid in company_ids if cid not in latest_by_company]
            if missing:
                cmr = (
                    self.client.table("current_market_data")
                    .select("company_id, current_price")
                    .in_("company_id", missing)
                    .execute()
                )
                for row in cmr.data or []:
                    cid = row["company_id"]
                    px = float(row["current_price"])
                    latest_by_company[cid] = {
                        "price": px,
                        "price_date": target_date,
                    }

        return latest_by_company
