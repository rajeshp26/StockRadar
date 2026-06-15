# -*- coding: utf-8 -*-
# application/jobs/aggregation_jobs.py
#
# Group-level aggregation (sector/industry) for valuation metrics.
#
# Computes percentile distribution stats (p05, p25, p50, p75, p95, mean) for
# trailing_pe, ev_ebitda, and price_to_fcf across all companies grouped by
# sector. Results are written to `group_metric_stats` for use by the
# fundamentals gauge when benchmark="sector".

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import supabase
from config import settings

logger = logging.getLogger(__name__)

METRIC_IDS = ["pe", "ev_ebitda", "pfcf"]

# Map our metric_id to the actual column name in financial_ratios
COLUMN_MAP: Dict[str, str] = {
    "pe": "trailing_pe",
    "ev_ebitda": "ev_ebitda",
    "pfcf": "price_to_fcf",
}


async def compute_and_upsert_group_metric_stats(
    group_type: str = "sector",
    min_sample_size: int = 5,
) -> Dict[str, Any]:
    """Compute percentile stats for each metric per sector and upsert into
    `group_metric_stats`.

    Args:
        group_type: 'sector' or 'industry'. Defaults to 'sector'.
        min_sample_size: Minimum companies required to write a group row.

    Returns:
        Summary dict with rows_written and group count.
    """
    logger.info(
        "[AGG] Computing %s-level metric stats (min_sample_size=%d)...",
        group_type, min_sample_size,
    )

    # Step 1: Get the latest financial ratio for each company, joined with sector
    # Uses DISTINCT ON to get the most recent row per company.
    group_col = group_type  # 'sector' or 'industry'
    now_ts = datetime.now(timezone.utc).isoformat()

    result: Dict[str, Any] = {
        "started_at": now_ts,
        "groups_found": 0,
        "rows_written": 0,
        "errors": [],
    }

    try:
        # Fetch all companies with their latest positive ratios
        # We use supabase RPC or raw_sql because DISTINCT ON is complex.
        # Fallback: iterate groups.
        group_keys = await _fetch_distinct_groups(group_col)
        result["groups_found"] = len(group_keys)

        if not group_keys:
            logger.info("[AGG] No %s groups found.", group_type)
            return result

        logger.info("[AGG] Found %d %s groups. Computing per-group stats...", len(group_keys), group_type)

        for group_key in group_keys:
            try:
                await _compute_group_stats(
                    group_type=group_type,
                    group_key=group_key,
                    min_sample_size=min_sample_size,
                )
                result["rows_written"] += len(METRIC_IDS)
            except Exception as e:
                err_msg = f"Failed for {group_type}={group_key}: {e}"
                logger.error("[AGG] %s", err_msg)
                result["errors"].append(err_msg)

        logger.info(
            "[AGG] Done. %d groups processed, %d metric rows written.",
            len(group_keys), result["rows_written"],
        )
    except Exception as e:
        logger.error("[AGG] Fatal error: %s", e, exc_info=True)
        result["errors"].append(str(e))

    return result


async def _fetch_distinct_groups(group_col: str) -> List[str]:
    """Fetch distinct non-null group values from companies table."""
    col = group_col if group_col in ("sector", "industry") else "sector"
    try:
        resp = (
            supabase.table("companies")
            .select(col)
            .not_.is_(col, "null")
            .execute()
        )
        raw = resp.data or []
        seen: set = set()
        out: List[str] = []
        for r in raw:
            v = r.get(col)
            if v and v not in seen:
                seen.add(v)
                out.append(v)
        return sorted(out)
    except Exception as e:
        logger.error("[AGG] Failed to fetch distinct %s: %s", col, e)
        raise


async def _fetch_companies_in_group(group_type: str, group_key: str) -> List[int]:
    """Return list of company_ids belonging to a group."""
    try:
        resp = (
            supabase.table("companies")
            .select("company_id")
            .eq(group_type, group_key)
            .execute()
        )
        return [r["company_id"] for r in (resp.data or [])]
    except Exception as e:
        logger.error("[AGG] Failed to fetch companies for %s=%s: %s", group_type, group_key, e)
        raise


async def _fetch_latest_ratio_values(
    company_ids: List[int],
    column: str,
) -> List[float]:
    """Fetch the latest positive value of a ratio column for given companies."""
    if not company_ids:
        return []
    values: List[float] = []
    try:
        batch_size = 50
        for i in range(0, len(company_ids), batch_size):
            batch = company_ids[i : i + batch_size]
            resp = (
                supabase.table("financial_ratios")
                .select("company_id, fiscal_year, fiscal_quarter, " + column)
                .in_("company_id", batch)
                .gt(column, 0)
                .order("company_id", desc=False)
                .order("fiscal_year", desc=True)
                .order("fiscal_quarter", desc=True)
                .execute()
            )
            rows = resp.data or []
            seen_ids: set = set()
            for r in rows:
                cid = r.get("company_id")
                val = r.get(column)
                if cid is not None and val is not None and cid not in seen_ids:
                    seen_ids.add(cid)
                    values.append(float(val))
        return values
    except Exception as e:
        logger.error("[AGG] Failed to fetch column %s: %s", column, e)
        raise


async def _compute_group_stats(
    group_type: str,
    group_key: str,
    min_sample_size: int,
) -> None:
    """Compute and upsert percentile stats for a single group."""
    company_ids = await _fetch_companies_in_group(group_type, group_key)

    if len(company_ids) < min_sample_size:
        logger.debug(
            "[AGG] Skipping %s=%s: %d companies < min_sample_size=%d",
            group_type, group_key, len(company_ids), min_sample_size,
        )
        return

    now_ts = datetime.now(timezone.utc).isoformat()

    for metric_id in METRIC_IDS:
        column = COLUMN_MAP[metric_id]
        values = await _fetch_latest_ratio_values(company_ids, column)

        if len(values) < min_sample_size:
            logger.debug(
                "[AGG] Skipping %s=%s metric=%s: %d values < min_sample_size=%d",
                group_type, group_key, metric_id, len(values), min_sample_size,
            )
            continue

        sorted_vals = sorted(values)
        n = len(sorted_vals)

        def percentile(p: float) -> Optional[float]:
            if not sorted_vals:
                return None
            idx = p / 100.0 * (n - 1)
            lo = int(idx)
            hi = min(lo + 1, n - 1)
            frac = idx - lo
            return round(sorted_vals[lo] + frac * (sorted_vals[hi] - sorted_vals[lo]), 2)

        p05 = percentile(5)
        p25 = percentile(25)
        p50 = percentile(50)
        p75 = percentile(75)
        p95 = percentile(95)
        mean_val = round(sum(sorted_vals) / n, 2) if n > 0 else None

        # Upsert into group_metric_stats
        payload = {
            "group_type": group_type,
            "group_key": group_key,
            "metric_id": metric_id,
            "p05": p05,
            "p25": p25,
            "p50": p50,
            "p75": p75,
            "p95": p95,
            "mean": mean_val,
            "sample_size": n,
            "computed_at": now_ts,
        }

        try:
            # Delete existing row for this group+metric, then insert fresh
            supabase.table("group_metric_stats") \
                .delete() \
                .eq("group_type", group_type) \
                .eq("group_key", group_key) \
                .eq("metric_id", metric_id) \
                .execute()
            supabase.table("group_metric_stats").insert(payload).execute()
            logger.debug(
                "[AGG] Written %s=%s metric=%s (n=%d, p50=%.1f)",
                group_type, group_key, metric_id, n, p50 if p50 else 0,
            )
        except Exception as e:
            logger.error(
                "[AGG] Failed to write %s=%s metric=%s: %s",
                group_type, group_key, metric_id, e,
            )
            raise

    # Update aggregation state watermark
    try:
        supabase.table("aggregation_state") \
            .update({"last_completed_at": now_ts, "is_running": False}) \
            .eq("aggregation_id", "sector_metric_agg") \
            .execute()
    except Exception as e:
        logger.error("[AGG] Failed to update aggregation state: %s", e)
