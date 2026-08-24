# application/jobs/data_quality_audit_job.py
#
# CHANGES IN THIS VERSION
# ─────────────────────────────────────────────────────────────────────────────
# Bug 3 fix: the file previously defined audit_company_data_quality twice.
#   Python silently discards the first definition and uses the second. The
#   second definition referenced DataQualityAuditJob — a class that does not
#   exist anywhere in the codebase — causing every call to this function to
#   raise a NameError, breaking the post-sync audit pipeline for all companies.
#
#   Fix: the working first implementation (procedural, correct) is kept
#   exactly as written. The broken second definition is removed entirely.
#   No logic changes to the working code.
#
# Phase 6 additions:
#   1. CF reconciliation check — verifies OCF + ICF + financing_cf + fx_effect
#      equals net_change_in_cash within a tolerance threshold. Flags multinationals
#      where FX distorts the cash bridge.
#   2. Deprecated table reference fixed: derived_financial_metrics → financial_ratios.
#   3. balance_sheets.shares_outstanding population check added.
# ─────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

import logging
from typing import Any

from database import supabase

logger = logging.getLogger(__name__)


def _as_int(x: Any) -> int | None:
    try:
        return int(x) if x is not None else None
    except Exception:
        return None


def _log_event(
    company_id: int,
    scope: str,
    metric: str,
    severity: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    payload = {
        "company_id": company_id,
        "scope":      scope,
        "metric":     metric,
        "severity":   severity,
        "message":    message,
        "details":    details or None,
    }
    supabase.table("data_quality_events").insert(payload).execute()


def _detect_year_gaps(years: list[int]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    ys = sorted(set([y for y in years if isinstance(y, int)]))
    for i in range(1, len(ys)):
        prev_y = ys[i - 1]
        cur_y  = ys[i]
        if cur_y - prev_y > 1:
            gaps.append({"prev_year": prev_y, "year": cur_y, "gap": cur_y - prev_y})
    return gaps


async def audit_company_data_quality(company_id: int) -> dict[str, Any]:
    """
    PHASE 8 audit:
      - missing years / insufficient depth for annual EPS / shares / revenue
      - year gaps in annual fiscal series
      - fallback usage detection (presence of yfinance rows)
      - derived metrics presence
      - CF statement reconciliation (Phase 6)
      - balance_sheets.shares_outstanding population (Phase 6)
    Writes data_quality_events rows; returns summary counts.
    Called by the earnings scheduler after each company financial refresh.
    """

    summary = {"events_written": 0}

    # ── Income statements: annual EPS inputs ──────────────────────────────────
    is_resp = (
        supabase.table("income_statements")
        .select(
            "fiscal_year, fiscal_quarter, revenue, net_income, "
            "net_income_to_common, shares_outstanding_diluted, data_source"
        )
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    is_rows = is_resp.data or []
    years   = [_as_int(r.get("fiscal_year")) for r in is_rows if r.get("fiscal_year") is not None]
    gaps    = _detect_year_gaps([y for y in years if y is not None])

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

    missing_rev = sum(1 for r in is_rows if r.get("revenue") is None)
    missing_sh  = sum(1 for r in is_rows if r.get("shares_outstanding_diluted") is None)

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

    # ── Cash flow statements: annual CFO/CapEx presence ───────────────────────
    cf_resp = (
        supabase.table("cash_flow_statements")
        .select(
            "fiscal_year, fiscal_quarter, "
            "cash_from_operating_activities, capital_expenditures, data_source"
        )
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    cf_rows  = cf_resp.data or []
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

    missing_cfo   = sum(1 for r in cf_rows if r.get("cash_from_operating_activities") is None)
    missing_capex = sum(1 for r in cf_rows if r.get("capital_expenditures") is None)

    if missing_cfo > 0 or missing_capex > 0:
        _log_event(
            company_id,
            scope="cash_flow_statements",
            metric="fcf_inputs",
            severity="low",
            message="Missing CFO and/or CapEx in one or more annual cash_flow_statements rows.",
            details={
                "missing_cfo_rows":   missing_cfo,
                "missing_capex_rows": missing_capex,
                "annual_years":       cf_annual,
            },
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

    # ── Phase 6: CF reconciliation check ─────────────────────────────────────
    # Verify: OCF + ICF + financing_cf + fx_effect ≈ net_change_in_cash
    # Only check rows where all four inputs are populated.
    # Threshold: 1% of max(|OCF|, |net_change|) — tight enough to catch data
    # errors, loose enough not to flag rounding differences.
    cf_recon_resp = (
        supabase.table("cash_flow_statements")
        .select(
            "fiscal_year, cash_from_operating_activities, cash_from_investing_activities, "
            "cash_from_financing_activities, effect_of_fx_on_cash, net_change_in_cash"
        )
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .not_.is_("net_change_in_cash", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    recon_failures: list[dict[str, Any]] = []
    for row in (cf_recon_resp.data or []):
        ocf      = row.get("cash_from_operating_activities")
        icf      = row.get("cash_from_investing_activities")
        fcf_flow = row.get("cash_from_financing_activities")
        fx       = row.get("effect_of_fx_on_cash") or 0.0
        net      = row.get("net_change_in_cash")
        if any(v is None for v in (ocf, icf, fcf_flow, net)):
            continue
        computed = float(ocf) + float(icf) + float(fcf_flow) + float(fx)
        actual   = float(net)
        denom    = max(abs(computed), abs(actual), 1.0)
        pct_err  = abs(computed - actual) / denom
        if pct_err > 0.01:
            recon_failures.append({
                "fiscal_year":  row.get("fiscal_year"),
                "computed_sum": round(computed, 2),
                "reported_net": round(actual, 2),
                "pct_error":    round(pct_err * 100, 2),
            })
    if recon_failures:
        _log_event(
            company_id,
            scope="cash_flow_statements",
            metric="reconciliation_failure",
            severity="high",
            message=(
                f"CF statement does not reconcile in {len(recon_failures)} annual row(s): "
                "OCF + ICF + financing_cf + fx_effect ≠ net_change_in_cash (>1% deviation)."
            ),
            details={"failures": recon_failures},
        )
        summary["events_written"] += 1

    # ── Phase 6: balance_sheets.shares_outstanding population check ───────────
    bs_shares_resp = (
        supabase.table("balance_sheets")
        .select("fiscal_year, shares_outstanding")
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    bs_share_rows = bs_shares_resp.data or []
    missing_bs_shares = sum(1 for r in bs_share_rows if r.get("shares_outstanding") is None)
    if missing_bs_shares > 0 and bs_share_rows:
        _log_event(
            company_id,
            scope="balance_sheets",
            metric="shares_outstanding_missing",
            severity="medium",
            message=(
                f"balance_sheets.shares_outstanding is NULL in {missing_bs_shares}/"
                f"{len(bs_share_rows)} annual rows. "
                "BV/share calculations will fall back to IS weighted-average shares."
            ),
            details={
                "missing_rows": missing_bs_shares,
                "total_rows": len(bs_share_rows),
            },
        )
        summary["events_written"] += 1

    # ── Derived metrics presence ───────────────────────────────────────────────
    dfm = (
        supabase.table("financial_ratios")
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
            scope="financial_ratios",
            metric="missing",
            severity="low",
            message="No financial_ratios rows found; derived metrics not computed yet.",
            details=None,
        )
        summary["events_written"] += 1

    return summary
