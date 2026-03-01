# backend/application/jobs/data_quality_audit_job.py
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from database import supabase

logger = logging.getLogger(__name__)


def _as_int(x: Any) -> Optional[int]:
    try:
        return int(x) if x is not None else None
    except Exception:
        return None


def _log_event(company_id: int, scope: str, metric: str, severity: str, message: str, details: Optional[Dict[str, Any]] = None) -> None:
    payload = {
        "company_id": company_id,
        "scope": scope,
        "metric": metric,
        "severity": severity,
        "message": message,
        "details": details or None,
    }
    supabase.table("data_quality_events").insert(payload).execute()


def _detect_year_gaps(years: List[int]) -> List[Dict[str, Any]]:
    gaps: List[Dict[str, Any]] = []
    ys = sorted(set([y for y in years if isinstance(y, int)]))
    for i in range(1, len(ys)):
        prev_y = ys[i - 1]
        cur_y = ys[i]
        if cur_y - prev_y > 1:
            gaps.append({"prev_year": prev_y, "year": cur_y, "gap": cur_y - prev_y})
    return gaps


async def audit_company_data_quality(company_id: int) -> Dict[str, Any]:
    """
    PHASE 8 audit:
      - missing years / insufficient depth for annual EPS / shares / revenue
      - year gaps in annual fiscal series
      - fallback usage detection (presence of yfinance rows)
      - derived metrics presence
    Writes data_quality_events rows; returns summary counts.
    """

    summary = {"events_written": 0}

    # -------------------------
    # Income statements: annual EPS inputs
    # -------------------------
    is_resp = (
        supabase.table("income_statements")
        .select("fiscal_year, fiscal_quarter, revenue, net_income, net_income_to_common, shares_outstanding_diluted, data_source")
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    is_rows = is_resp.data or []
    years = [_as_int(r.get("fiscal_year")) for r in is_rows if r.get("fiscal_year") is not None]
    gaps = _detect_year_gaps([y for y in years if y is not None])

    if gaps:
        _log_event(
            company_id,
            scope="income_statements",
            metric="year_gaps",
            severity="medium",
            message="Gaps detected in annual fiscal_year sequence for income_statements.",
            details={"gaps": gaps},
        )
        summary["events_written"] += 1

    # Depth checks (min years for stable suitability)
    annual_count = len(is_rows)
    if annual_count < 5:
        _log_event(
            company_id,
            scope="income_statements",
            metric="insufficient_depth",
            severity="low",
            message="Insufficient annual income_statements depth (<5 years).",
            details={"annual_years": annual_count},
        )
        summary["events_written"] += 1

    # Missing shares/revenue checks
    missing_rev = sum(1 for r in is_rows if r.get("revenue") is None)
    missing_sh = sum(1 for r in is_rows if r.get("shares_outstanding_diluted") is None)

    if missing_rev > 0:
        _log_event(
            company_id,
            scope="income_statements",
            metric="revenue_history",
            severity="low",
            message="Missing revenue in one or more annual income_statements rows.",
            details={"missing_rows": missing_rev, "annual_years": annual_count},
        )
        summary["events_written"] += 1

    if missing_sh > 0:
        _log_event(
            company_id,
            scope="income_statements",
            metric="shares_history",
            severity="low",
            message="Missing diluted shares in one or more annual income_statements rows.",
            details={"missing_rows": missing_sh, "annual_years": annual_count},
        )
        summary["events_written"] += 1

    # Fallback usage (statement-level)
    yf_rows = sum(1 for r in is_rows if (r.get("data_source") or "").lower() == "yfinance")
    if yf_rows > 0:
        _log_event(
            company_id,
            scope="income_statements",
            metric="fallback_usage",
            severity="info",
            message="YFinance fallback rows present in income_statements annual series.",
            details={"yfinance_rows": yf_rows, "annual_years": annual_count},
        )
        summary["events_written"] += 1

    # -------------------------
    # Cash flow statements: annual CFO/CapEx presence (DCF suitability)
    # -------------------------
    cf_resp = (
        supabase.table("cash_flow_statements")
        .select("fiscal_year, fiscal_quarter, cash_from_operating_activities, capital_expenditures, data_source")
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    cf_rows = cf_resp.data or []
    cf_annual = len(cf_rows)

    if cf_annual < 5:
        _log_event(
            company_id,
            scope="cash_flow_statements",
            metric="insufficient_depth",
            severity="low",
            message="Insufficient annual cash_flow_statements depth (<5 years).",
            details={"annual_years": cf_annual},
        )
        summary["events_written"] += 1

    missing_cfo = sum(1 for r in cf_rows if r.get("cash_from_operating_activities") is None)
    missing_capex = sum(1 for r in cf_rows if r.get("capital_expenditures") is None)

    if missing_cfo > 0 or missing_capex > 0:
        _log_event(
            company_id,
            scope="cash_flow_statements",
            metric="fcf_inputs",
            severity="low",
            message="Missing CFO and/or CapEx in one or more annual cash_flow_statements rows.",
            details={"missing_cfo_rows": missing_cfo, "missing_capex_rows": missing_capex, "annual_years": cf_annual},
        )
        summary["events_written"] += 1

    yf_cf = sum(1 for r in cf_rows if (r.get("data_source") or "").lower() == "yfinance")
    if yf_cf > 0:
        _log_event(
            company_id,
            scope="cash_flow_statements",
            metric="fallback_usage",
            severity="info",
            message="YFinance fallback rows present in cash_flow_statements annual series.",
            details={"yfinance_rows": yf_cf, "annual_years": cf_annual},
        )
        summary["events_written"] += 1

    # -------------------------
    # Derived metrics presence
    # -------------------------
    dfm = (
        supabase.table("derived_financial_metrics")
        .select("fiscal_year, computed_at")
        .eq("company_id", company_id)
        .order("fiscal_year", desc=True)
        .limit(1)
        .execute()
    )
    dfm_row = (dfm.data or [None])[0] if dfm.data else None
    if not dfm_row:
        _log_event(
            company_id,
            scope="derived_financial_metrics",
            metric="missing",
            severity="low",
            message="No derived_financial_metrics rows found; derived metrics not computed yet.",
            details=None,
        )
        summary["events_written"] += 1

    return summary