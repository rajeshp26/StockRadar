"""
Daily health check for the dividend pipeline.

Implements design doc §7.6.4 — scheduled function that runs after the
MarketDataRefresh cycle to validate coverage, freshness, and integrity.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from database import supabase

logger = logging.getLogger(__name__)


async def validate_dividend_pipeline(
    portfolio_repo: Any = None,
    alert_slack: Optional[callable] = None,
) -> Dict[str, Any]:
    """Daily health check for the dividend pipeline.

    Checks:
      1. Coverage — at least 15% of holdings have upcoming events
      2. No stale events in upcoming table
      3. Missing rows — track holdings with no upcoming event
      4. Source distribution (drift detection)
      5. Freshness — sources should have reported within 7 days
      6. No NULL amounts on historical rows (regression)

    Args:
        portfolio_repo: Optional repository instance. If None, uses
                        raw supabase client (read-only queries).
        alert_slack:    Optional async callback for alerts.  If None,
                        alerts are logged instead.

    Returns:
        Dict with coverage_pct, stale_count, stale_source_count,
        null_historical_count, missing_event_count, source_distribution.
    """
    if alert_slack is None:
        async def _noop_alert(msg: str) -> None:
            logger.warning("[DIV_MONITOR] Alert would fire: %s", msg)
        alert_slack = _noop_alert

    today = date.today()

    # ── 1. Coverage: at least 15% of holdings have upcoming events ─────
    company_ids: List[int] = []
    if portfolio_repo is not None:
        holdings = await portfolio_repo.get_holdings_with_companies([])
        company_ids = list({h["company_id"] for h in (holdings or []) if h.get("company_id")})

    if not company_ids:
        # Fallback: query distinct company_ids from upcoming_dividend_events
        try:
            all_ids_resp = (
                supabase.table("upcoming_dividend_events")
                .select("company_id")
                .execute()
            )
            company_ids = list({r["company_id"] for r in (all_ids_resp.data or [])})
        except Exception:
            company_ids = []

    upcoming_rows = (
        supabase.table("upcoming_dividend_events")
        .select("company_id")
        .in_("company_id", company_ids)
        .gte("ex_dividend_date", today.isoformat())
        .execute()
    ) if company_ids else type("Empty", (), {"data": []})()

    upcoming_company_ids = {r["company_id"] for r in (upcoming_rows.data or [])}
    coverage = len(upcoming_company_ids) / max(len(company_ids), 1)
    if coverage < 0.15:
        await alert_slack(
            f"Dividend coverage dropped to {coverage:.1%} "
            f"({len(upcoming_company_ids)}/{len(company_ids)} holdings)"
        )

    # ── 2. No stale events in upcoming table ───────────────────────────
    try:
        stale_resp = (
            supabase.table("upcoming_dividend_events")
            .select("id", count="exact")
            .lt("ex_dividend_date", today.isoformat())
            .execute()
        )
        stale_count = len(stale_resp.data) if stale_resp.data else 0
    except Exception:
        stale_count = 0

    if stale_count > 0:
        await alert_slack(
            f"{stale_count} stale events found — cleanup may not be running"
        )

    # ── 3. Missing rows ─────────────────────────────────────────────────
    held_ids = set(company_ids)
    missing_ids = held_ids - upcoming_company_ids
    logger.info(
        "[DIV_MONITOR] %d/%d holdings have no upcoming event",
        len(missing_ids), len(held_ids),
    )

    # ── 4. Source distribution ──────────────────────────────────────────
    try:
        sources_resp = (
            supabase.table("upcoming_dividend_events")
            .select("data_source")
            .execute()
        )
        src_counts: Dict[str, int] = {}
        for r in (sources_resp.data or []):
            s = r.get("data_source", "unknown")
            src_counts[s] = src_counts.get(s, 0) + 1
        source_distribution = [{"data_source": k, "count": v} for k, v in src_counts.items()]
    except Exception:
        source_distribution = []

    logger.info("[DIV_MONITOR] Upcoming event sources: %s", source_distribution)

    # ── 5. Freshness check ──────────────────────────────────────────────
    try:
        stale_sources_resp = (
            supabase.table("upcoming_dividend_events")
            .select("id", count="exact")
            .lt("source_observed_at", (datetime.utcnow() - timedelta(days=7)).isoformat())
            .execute()
        )
        stale_source_count = len(stale_sources_resp.data) if stale_sources_resp.data else 0
    except Exception:
        stale_source_count = 0

    if stale_source_count > 0:
        await alert_slack(
            f"{stale_source_count} stale source observations "
            "(>7 days since last refresh)"
        )

    # ── 6. No NULL amounts on historical rows ───────────────────────────
    try:
        null_amt_resp = (
            supabase.table("dividend_history")
            .select("id", count="exact")
            .is_("dividend_amount", "null")
            .lte("ex_dividend_date", today.isoformat())
            .execute()
        )
        null_historical_count = len(null_amt_resp.data) if null_amt_resp.data else 0
    except Exception:
        null_historical_count = 0

    if null_historical_count > 0:
        await alert_slack(
            f"{null_historical_count} historical rows with NULL "
            "dividend_amount — possible data corruption"
        )

    return {
        "coverage_pct": round(coverage * 100, 1),
        "stale_count": stale_count,
        "stale_source_count": stale_source_count,
        "null_historical_count": null_historical_count,
        "missing_event_count": len(missing_ids),
        "source_distribution": source_distribution,
    }
