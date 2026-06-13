# -*- coding: utf-8 -*-
# application/jobs/derived_financial_metrics_job.py
#
# CHANGES vs previous version
# ─────────────────────────────────────────────────
# Phase 1 — Version-gate upsert:
#   Before writing to financial_ratios, batch-fetch the stored source_version_tag
#   for every (company_id, fiscal_year) we computed. Only upsert rows whose tag
#   differs from what is already stored.
#
#   Effect: computed_at no longer advances when IS/BS/CF source data is unchanged.
#   This eliminates the primary driver of spurious DDM/Rule1/DCF recomputes.
#
#   Return shape extended: {"count", "rows_changed", "upserted"}
#   - rows_changed: number of rows actually written (0 = no-op cycle)
#   - upserted:     False when all rows were identical (tag match)
#   The market_data_scheduler reads rows_changed to gate Rule #1 evaluation.
# ─────────────────────────────────────────────────

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from database import supabase
from config import settings

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _f(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    try:
        return a / b
    except Exception:
        return None


def _fcf(cfo: Optional[float], capex: Optional[float]) -> Optional[float]:
    """Sign-aware FCF. capex stored as negative outflow → add; positive → subtract."""
    if cfo is None or capex is None:
        return None
    return (cfo + capex) if capex < 0 else (cfo - capex)


def _version_tag(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


# ─── Job ──────────────────────────────────────────────────────────────────────

async def compute_and_upsert_derived_financial_metrics(company_id: int) -> Dict[str, Any]:
    """
    Computes annual financial ratios from canonical statement tables and writes
    to financial_ratios (Phase 2 consolidated table).

    Sources (read-only):
      income_statements    — P&L items, EBITDA, EBIT, shares
      balance_sheets       — assets, liabilities, equity, debt
      cash_flow_statements — OCF, capex, dividends paid

    Writes to: financial_ratios (on_conflict: company_id, fiscal_year)
    Does NOT write to: derived_financial_metrics (deprecated), statistics, dividend_metrics

    Phase 1 change: version-gated upsert.
    Rows whose source_version_tag matches the stored tag are skipped entirely,
    so computed_at does NOT advance when underlying data is unchanged.

    Returns:
      {
        "count":        int,   # total fiscal years evaluated
        "rows_changed": int,   # rows actually written to DB (0 = no-op)
        "upserted":     bool,  # True only when at least one row was written
      }
    """

    # ── Fetch annual statement series ──────────────────────────────────────────

    is_resp = (
        supabase.table("income_statements")
        .select(
           "is_id, fiscal_year, period_end_date, revenue, cost_of_goods_sold, gross_profit, "
           "operating_income, net_income, ebit, ebitda, pretax_income, tax_expense, "
           "net_income_to_common, interest_expense, shares_outstanding_diluted"
        )
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    bs_resp = (
        supabase.table("balance_sheets")
        .select(
            "bs_id, fiscal_year, period_end_date, total_assets, current_assets, current_liabilities, "
            "total_debt, long_term_debt, shareholders_equity, cash_and_cash_equivalents, "
            "intangible_assets, goodwill, inventory, "
            "shares_outstanding, invested_capital"
        )
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    cf_resp = (
        supabase.table("cash_flow_statements")
        .select(
            "cf_id, fiscal_year, period_end_date, cash_from_operating_activities, "
            "capital_expenditures, dividends_paid"
        )
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )

    is_rows = is_resp.data or []
    bs_rows = bs_resp.data or []
    cf_rows = cf_resp.data or []

    def _best_row(rows: List[Dict], score_fields: List[str], pk_field: str) -> Dict[int, Dict]:
       """
       Build a fiscal_year -> row dict by picking the most complete row per year.
       'Most complete' = most non-null values in score_fields.
       Tiebreaker: largest pk_field value (most recently written = likely defeatbeta path).
       """
       by_year: Dict[int, Dict] = {}
       for r in rows:
           fy = r.get("fiscal_year")
           if fy is None:
               continue
           if fy not in by_year:
               by_year[fy] = r
               continue
           existing_score = sum(1 for f in score_fields if by_year[fy].get(f) is not None)
           candidate_score = sum(1 for f in score_fields if r.get(f) is not None)
           if candidate_score > existing_score:
               by_year[fy] = r
           elif candidate_score == existing_score:
               if (r.get(pk_field) or 0) > (by_year[fy].get(pk_field) or 0):
                   by_year[fy] = r
       return by_year

    is_by_year = _best_row(is_rows, [
       "net_income_to_common", "shares_outstanding_diluted",
       "net_income", "ebit", "ebitda", "revenue", "gross_profit",
    ], pk_field="is_id")

    bs_by_year = _best_row(bs_rows, [
       "total_assets", "shareholders_equity", "total_debt",
       "intangible_assets", "goodwill",
       "shares_outstanding", "invested_capital",
    ], pk_field="bs_id")

    cf_by_year = _best_row(cf_rows, [
       "cash_from_operating_activities", "capital_expenditures",
       "dividends_paid",
    ], pk_field="cf_id")

    years = sorted(set(is_by_year) | set(bs_by_year) | set(cf_by_year))
    out: List[Dict[str, Any]] = []

    for y in years:
        isr = is_by_year.get(y) or {}
        bsr = bs_by_year.get(y) or {}
        cfr = cf_by_year.get(y) or {}

        revenue      = _f(isr.get("revenue"))
        cogs         = _f(isr.get("cost_of_goods_sold"))
        gross_profit = _f(isr.get("gross_profit"))
        op_inc       = _f(isr.get("operating_income"))
        net_inc      = _f(isr.get("net_income"))
        net_inc_common = _f(isr.get("net_income_to_common")) or net_inc
        ebit         = _f(isr.get("ebit"))
        ebitda       = _f(isr.get("ebitda"))
        pretax       = _f(isr.get("pretax_income"))
        tax          = _f(isr.get("tax_expense"))
        interest_exp = _f(isr.get("interest_expense"))
        # Phase 6: prefer period-end shares from balance_sheets (correct BV/share denominator).
        # Fall back to weighted-average diluted shares from income_statements if not yet populated.
        shares = (
            _f(bsr.get("shares_outstanding"))
            or _f(isr.get("shares_outstanding_diluted"))
        )
        if shares is not None:
            _shares_source = "balance_sheets" if _f(bsr.get("shares_outstanding")) else "income_statements"
        else:
            _shares_source = "none"

        total_assets      = _f(bsr.get("total_assets"))
        current_assets    = _f(bsr.get("current_assets"))
        current_liab      = _f(bsr.get("current_liabilities"))
        total_debt        = _f(bsr.get("total_debt"))
        lt_debt           = _f(bsr.get("long_term_debt"))
        equity            = _f(bsr.get("shareholders_equity"))
        cash              = _f(bsr.get("cash_and_cash_equivalents"))
        intangibles       = _f(bsr.get("intangible_assets"))
        goodwill          = _f(bsr.get("goodwill"))
        inventory         = _f(bsr.get("inventory"))

        cfo          = _f(cfr.get("cash_from_operating_activities"))
        capex        = _f(cfr.get("capital_expenditures"))
        div_paid     = _f(cfr.get("dividends_paid"))
        div_paid_abs = abs(div_paid) if div_paid is not None else None

        fcf = _fcf(cfo, capex)

        # Phase 6: prefer defeatbeta pre-computed value; fall back to manual formula.
        invested_capital = _f(bsr.get("invested_capital"))
        if invested_capital is None and total_debt is not None and equity is not None:
            invested_capital = total_debt + equity - (cash or 0.0)

        tax_rate = None
        if pretax is not None and pretax != 0 and tax is not None:
            tax_rate = max(0.0, min(1.0, tax / pretax))

        nopat = None
        if ebit is not None:
            nopat = ebit * (1.0 - (tax_rate if tax_rate is not None else 0.21))

        roic = (
            _safe_div(nopat, invested_capital)
            if nopat is not None and invested_capital not in (None, 0.0)
            else None
        )
        roe = (
            _safe_div(net_inc_common, equity)
            if net_inc_common is not None and equity not in (None, 0.0)
            else None
        )
        roa = (
            _safe_div(net_inc, total_assets)
            if net_inc is not None and total_assets not in (None, 0.0)
            else None
        )

        gross_margin     = _safe_div(gross_profit, revenue)
        operating_margin = _safe_div(op_inc, revenue)
        ebitda_margin    = _safe_div(ebitda, revenue)
        net_margin       = _safe_div(net_inc, revenue)
        fcf_margin       = _safe_div(fcf, revenue)

        fcf_conversion = (
            _safe_div(fcf, net_inc_common)
            if fcf is not None and net_inc_common not in (None, 0.0)
            else None
        )

        payout = (
            _safe_div(div_paid_abs, net_inc_common)
            if div_paid_abs is not None and net_inc_common not in (None, 0.0)
            else None
        )
        fcf_payout = (
            _safe_div(div_paid_abs, fcf)
            if div_paid_abs is not None and fcf not in (None, 0.0)
            else None
        )
        coverage = (
            _safe_div(fcf, div_paid_abs)
            if fcf is not None and div_paid_abs not in (None, 0.0)
            else None
        )

        debt_to_equity = (
            _safe_div(total_debt, equity)
            if total_debt is not None and equity not in (None, 0.0)
            else None
        )
        debt_to_assets = (
            _safe_div(total_debt, total_assets)
            if total_debt is not None and total_assets not in (None, 0.0)
            else None
        )
        lt_debt_to_equity = (
            _safe_div(lt_debt, equity)
            if lt_debt is not None and equity not in (None, 0.0)
            else None
        )
        lt_debt_to_assets = (
            _safe_div(lt_debt, total_assets)
            if lt_debt is not None and total_assets not in (None, 0.0)
            else None
        )
        interest_coverage = None
        if ebit is not None and interest_exp is not None and interest_exp != 0:
            interest_coverage = ebit / abs(interest_exp)

        current_ratio = (
            _safe_div(current_assets, current_liab)
            if current_assets is not None and current_liab not in (None, 0.0)
            else None
        )
        quick_ratio = None
        if current_assets is not None and current_liab not in (None, 0.0):
            liquid = current_assets - (inventory or 0.0)
            quick_ratio = _safe_div(liquid, current_liab)

        asset_turnover = (
            _safe_div(revenue, total_assets)
            if revenue is not None and total_assets not in (None, 0.0)
            else None
        )
        inventory_turnover = (
            _safe_div(cogs, inventory)
            if cogs is not None and inventory not in (None, 0.0)
            else None
        )

        capex_abs = abs(capex) if capex is not None else None
        working_capital = (
            (current_assets - current_liab)
            if current_assets is not None and current_liab is not None
            else None
        )
        tangible_equity = None
        if equity is not None:
            tangible_equity = equity - (intangibles or 0.0) - (goodwill or 0.0)

        def _per_share(val: Optional[float]) -> Optional[float]:
            return _safe_div(val, shares) if shares is not None and shares > 0 else None

        revenue_ps    = _per_share(revenue)
        ocf_ps        = _per_share(cfo)
        fcf_ps        = _per_share(fcf)
        ebit_ps       = _per_share(ebit)
        ebitda_ps     = _per_share(ebitda)
        bvps          = _per_share(equity)
        tangible_bvps = _per_share(tangible_equity)
        cash_ps       = _per_share(cash)
        debt_ps       = _per_share(total_debt)
        wc_ps         = _per_share(working_capital)
        capex_ps      = _per_share(capex_abs)

        source_payload = {
            "is": {k: isr.get(k) for k in [
                "revenue", "gross_profit", "operating_income", "net_income",
                "ebit", "ebitda", "pretax_income", "tax_expense",
                "net_income_to_common", "interest_expense", "shares_outstanding_diluted",
            ]},
            "bs": {k: bsr.get(k) for k in [
                "total_assets", "current_assets", "current_liabilities",
                "total_debt", "long_term_debt", "shareholders_equity",
                "cash_and_cash_equivalents", "intangible_assets", "goodwill", "inventory",
                "shares_outstanding", "invested_capital",
            ]},
            "cf": {k: cfr.get(k) for k in [
                "cash_from_operating_activities", "capital_expenditures", "dividends_paid",
            ]},
        }
        period_end = (
            isr.get("period_end_date")
            or bsr.get("period_end_date")
            or cfr.get("period_end_date")
        )

        out.append({
            "company_id":   company_id,
            "fiscal_year":  int(y),
            "fiscal_quarter": None,
            "period_end_date": period_end,

            "roic":  roic,
            "roe":   roe,
            "roa":   roa,

            "gross_margin":     gross_margin,
            "operating_margin": operating_margin,
            "ebitda_margin":    ebitda_margin,
            "net_margin":       net_margin,
            "fcf_margin":       fcf_margin,

            "free_cash_flow":  fcf,
            "fcf_conversion":  fcf_conversion,

            "dividend_payout_ratio":     payout,
            "fcf_dividend_payout_ratio": fcf_payout,
            "dividend_coverage_fcf":     coverage,

            "debt_to_equity":           debt_to_equity,
            "debt_to_assets":           debt_to_assets,
            "long_term_debt_to_equity": lt_debt_to_equity,
            "long_term_debt_to_assets": lt_debt_to_assets,
            "interest_coverage":        interest_coverage,

            "current_ratio": current_ratio,
            "quick_ratio":   quick_ratio,

            "asset_turnover":    asset_turnover,
            "inventory_turnover": inventory_turnover,

            "revenue_per_share":             revenue_ps,
            "ocf_per_share":                 ocf_ps,
            "fcf_per_share":                 fcf_ps,
            "ebit_per_share":                ebit_ps,
            "ebitda_per_share":              ebitda_ps,
            "book_value_per_share":          bvps,
            "tangible_book_value_per_share": tangible_bvps,
            "cash_per_share":                cash_ps,
            "total_debt_per_share":          debt_ps,
            "working_capital_per_share":     wc_ps,
            "capex_per_share":               capex_ps,

            "computed_at":        datetime.utcnow().isoformat(),
            "source_version_tag": _version_tag(source_payload),
            "data_source":        "derived",
            "confidence_score":   float(
                getattr(settings, "DERIVED_METRICS_CONFIDENCE_SCORE", 1.0)
            ),
        })

    if not out:
        logger.info("[RATIOS] No statement rows found for company_id=%s", company_id)
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # ── Phase 1: Version-gate — only upsert rows whose source data changed ─────
    #
    # Batch-fetch the stored source_version_tag for every fiscal year we computed.
    # Filter out rows where the tag matches what is already in financial_ratios.
    #
    # This prevents computed_at from advancing when IS/BS/CF values are identical,
    # which was the primary cause of spurious downstream recomputes for all
    # valuation methods (DDM, Rule1, DCF, Owner Earnings, Residual Income).
    #
    # If the pre-fetch itself fails (network/permission error), we fall back to
    # the full upsert so the job never silently drops an update.

    existing_tags: Dict[int, str] = {}
    try:
        fiscal_years = [row["fiscal_year"] for row in out]
        tags_resp = (
            supabase.table("financial_ratios")
            .select("fiscal_year, source_version_tag")
            .eq("company_id", company_id)
            .in_("fiscal_year", fiscal_years)
            .is_("fiscal_quarter", None)
            .execute()
        )
        for r in (tags_resp.data or []):
            fy  = r.get("fiscal_year")
            tag = r.get("source_version_tag")
            if fy is not None and tag:
                existing_tags[int(fy)] = tag
    except Exception as e:
        logger.warning(
            "[RATIOS] Tag pre-fetch failed for company_id=%s; "
            "falling back to full upsert: %s",
            company_id, e,
        )
        # existing_tags remains empty → all rows treated as changed → full upsert

    changed_rows = [
        row for row in out
        if existing_tags.get(row["fiscal_year"]) != row["source_version_tag"]
    ]

    if not changed_rows:
        logger.debug(
            "[RATIOS] All %d rows unchanged for company_id=%s "
            "(source_version_tag match — skipping upsert)",
            len(out), company_id,
        )
        return {"count": len(out), "rows_changed": 0, "upserted": False}

    supabase.table("financial_ratios").upsert(
        changed_rows, on_conflict="company_id,fiscal_year,fiscal_quarter"
    ).execute()

    logger.info(
        "[RATIOS] Upserted %d/%d changed rows into financial_ratios for company_id=%s",
        len(changed_rows), len(out), company_id,
    )
    
    return {"count": len(out), "rows_changed": len(changed_rows), "upserted": True}


# ─── Health Score Helpers ──────────────────────────────────────────────────────
# These are used by compute_and_upsert_quarterly_health_scores below.


def _compute_piotroski_score(q: Dict[str, Any], prev_q: Dict[str, Any]) -> int:
    """Compute Piotroski F-Score (0–9) for a quarterly period.

    Nine binary criteria across three categories:
      Profitability (4 pts):  ROA > 0, CFO > 0, change in ROA > 0, accrual ratio < 0
      Leverage/Liquidity (3 pts): Δ leverage < 0, Δ current_ratio > 0, no new shares
      Efficiency (2 pts):  Δ gross_margin > 0, Δ asset_turnover > 0
    """
    score = 0

    # ── Profitability (4 pts) ─────────────────────────────────────────────
    # 1. Positive ROA
    roa = _f(q.get("roa"))
    if roa is not None and roa > 0:
        score += 1

    # 2. Positive CFO (cash_from_operating_activities > 0)
    cfo = _f(q.get("cash_from_operating_activities"))
    if cfo is not None and cfo > 0:
        score += 1

    # 3. Change in ROA (current > prior)
    prev_roa = _f(prev_q.get("roa"))
    if roa is not None and prev_roa is not None and roa > prev_roa:
        score += 1

    # 4. Accrual (CFO / Total Assets) > ROA → negative accrual → good
    ta = _f(q.get("total_assets"))
    if cfo is not None and ta not in (None, 0) and roa is not None:
        if (cfo / ta) > roa:
            score += 1

    # ── Leverage / Liquidity (3 pts) ──────────────────────────────────────
    # 5. Δ long-term-debt-to-assets < 0 (less leverage)
    prev_lt_debt_assets = _f(prev_q.get("long_term_debt_to_assets"))
    lt_debt_assets = _f(q.get("long_term_debt_to_assets"))
    if lt_debt_assets is not None and prev_lt_debt_assets is not None:
        if lt_debt_assets < prev_lt_debt_assets:
            score += 1

    # 6. Δ current_ratio > 0
    prev_cr = _f(prev_q.get("current_ratio"))
    cr = _f(q.get("current_ratio"))
    if cr is not None and prev_cr is not None and cr > prev_cr:
        score += 1

    # 7. No new shares (shares_outstanding ≤ previous)
    prev_shares = _f(prev_q.get("shares_outstanding"))
    shares = _f(q.get("shares_outstanding"))
    if shares is not None and prev_shares is not None and shares <= prev_shares:
        score += 1

    # ── Efficiency (2 pts) ────────────────────────────────────────────────
    # 8. Δ gross_margin > 0
    prev_gm = _f(prev_q.get("gross_margin"))
    gm = _f(q.get("gross_margin"))
    if gm is not None and prev_gm is not None and gm > prev_gm:
        score += 1

    # 9. Δ asset_turnover > 0
    prev_at = _f(prev_q.get("asset_turnover"))
    at = _f(q.get("asset_turnover"))
    if at is not None and prev_at is not None and at > prev_at:
        score += 1

    return score


def _compute_altman_z_score(q: Dict[str, Any]) -> Optional[float]:
    """Compute Altman Z-Score for a quarterly period.

    Z = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E

    A = working_capital / total_assets
    B = retained_earnings / total_assets
    C = EBIT / total_assets
    D = market_value_of_equity / total_liabilities
    E = revenue / total_assets

    Z ≥ 3.0   → Safe zone
    2.7–2.99  → Grey zone (caution)
    1.8–2.69  → Grey zone (distress)
    < 1.8     → Distress zone
    """
    ta = _f(q.get("total_assets"))
    if ta is None or ta == 0:
        return None

    wc = _f(q.get("working_capital"))
    re = _f(q.get("retained_earnings"))
    ebit = _f(q.get("ebit"))
    mkt_equity = _f(q.get("market_cap"))
    total_liab = _f(q.get("total_liabilities"))
    rev = _f(q.get("revenue"))

    A = _safe_div(wc, ta) or 0.0
    B = _safe_div(re, ta) or 0.0
    C = _safe_div(ebit, ta) or 0.0
    D = (
        _safe_div(mkt_equity, total_liab)
        if mkt_equity is not None and total_liab not in (None, 0.0)
        else 0.0
    )
    E = _safe_div(rev, ta) or 0.0

    return 1.2 * A + 1.4 * B + 3.3 * C + 0.6 * D + 1.0 * E


# ─── Quarterly Health Scores ────────────────────────────────────────────────────


def _fetch_quarterly_statements(
    company_id: int, fiscal_year: int
) -> Dict[str, List[Dict]]:
    """Fetch income_statement, balance_sheet, cash_flow rows for a given fiscal year, quarterly.

    Returns a dict with keys: is_rows, bs_rows, cf_rows.
    Each value is a list of rows, sorted by fiscal_quarter ascending.
    """
    out: Dict[str, List[Dict]] = {"is_rows": [], "bs_rows": [], "cf_rows": []}

    for table, key in [
        ("income_statements", "is_rows"),
        ("balance_sheets", "bs_rows"),
        ("cash_flow_statements", "cf_rows"),
    ]:
        resp = (
            supabase.table(table)
            .select("*")
            .eq("company_id", company_id)
            .eq("fiscal_year", fiscal_year)
            .neq("fiscal_quarter", None)
            .order("fiscal_quarter", desc=False)
            .execute()
        )
        out[key] = resp.data or []
    return out


def _find_prior_year_row(lookup_rows: List[Dict], fy: int, q: int) -> Optional[Dict]:
    """Find the same-quarter row from the previous fiscal year.

    Used to provide prior-period values for the 9 Piotroski criteria that
    require year-over-year comparison (e.g. Δ ROA, Δ gross_margin).
    """
    for r in lookup_rows:
        if r.get("fiscal_year") == fy - 1 and r.get("fiscal_quarter") == q:
            return r
    return None


async def compute_and_upsert_quarterly_health_scores(company_id: int) -> Dict[str, Any]:
    """Compute and upsert quarterly Piotroski F-Score + Altman Z-Score for a company.

    Orchestration:
      1. Determine which fiscal years have quarterly IS/BS/CF data.
      2. For each (year, quarter), compute the standard ratio set (reuses same
         formulas as compute_and_upsert_derived_financial_metrics).
      3. Compute health scores — Piotroski F (needs prior-year same-quarter for
         YoY deltas) and Altman Z (cross-sectional, no prior needed).
      4. Include computed_at field so freshness is tracked per-quarter.
      5. Upsert on (company_id, fiscal_year, fiscal_quarter).

    Returns same shape as compute_and_upsert_derived_financial_metrics:
      {"count": int, "rows_changed": int, "upserted": bool}
    """
    # ── Step 1: find all fiscal years that have quarterly data ──────────
    qis_resp = (
        supabase.table("income_statements")
        .select("fiscal_year")
        .eq("company_id", company_id)
        .neq("fiscal_quarter", None)
        .execute()
    )
    quarters = qis_resp.data or []
    fiscal_years = sorted(set(r["fiscal_year"] for r in quarters if r.get("fiscal_year")))

    if not fiscal_years:
        logger.info(
            "[HLTH] No quarterly data found for company_id=%s", company_id
        )
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # Pre-fetch the *previous* year's annual ratios for prior-period lookups.
    # This avoids hitting the DB per-row in the innermost loop.
    min_year = min(fiscal_years)
    prior_annual: List[Dict] = []
    if min_year > 2010:
        try:
            resp = (
                supabase.table("financial_ratios")
                .select("*")
                .eq("company_id", company_id)
                .eq("fiscal_year", min_year - 1)
                .is_("fiscal_quarter", None)
                .execute()
            )
            prior_annual = resp.data or []
        except Exception:
            prior_annual = []

    all_quarterly_ratios: List[Dict] = []

    for fy in fiscal_years:
        stmts = _fetch_quarterly_statements(company_id, fy)
        is_rows: List[Dict] = stmts["is_rows"]
        bs_rows: List[Dict] = stmts["bs_rows"]
        cf_rows: List[Dict] = stmts["cf_rows"]

        if not is_rows and not bs_rows and not cf_rows:
            continue

        quarters_set = sorted(set(
            r.get("fiscal_quarter")
            for lst in (is_rows, bs_rows, cf_rows)
            for r in lst
            if r.get("fiscal_quarter") is not None
        ))

        # Fetch the same-quarter prior-year data for Piotroski YoY deltas.
        prior_ratios: List[Dict] = []
        if fy > min_year or True:
            try:
                prior_resp = (
                    supabase.table("financial_ratios")
                    .select("*")
                    .eq("company_id", company_id)
                    .eq("fiscal_year", fy - 1)
                    .neq("fiscal_quarter", None)
                    .execute()
                )
                prior_ratios = prior_resp.data or []
            except Exception:
                prior_ratios = prior_annual

        # Build lookup maps for fast access
        is_by_q: Dict[int, Dict] = {r.get("fiscal_quarter"): r for r in is_rows if r.get("fiscal_quarter")}
        bs_by_q: Dict[int, Dict] = {r.get("fiscal_quarter"): r for r in bs_rows if r.get("fiscal_quarter")}
        cf_by_q: Dict[int, Dict] = {r.get("fiscal_quarter"): r for r in cf_rows if r.get("fiscal_quarter")}
        prior_by_q: Dict[int, Dict] = {r.get("fiscal_quarter"): r for r in prior_ratios if r.get("fiscal_quarter")}

        for q in quarters_set:
            isr = is_by_q.get(q) or {}
            bsr = bs_by_q.get(q) or {}
            cfr = cf_by_q.get(q) or {}

            # ── Extract raw values ─────────────────────────────────────
            revenue        = _f(isr.get("revenue"))
            cogs           = _f(isr.get("cost_of_goods_sold"))
            gross_profit   = _f(isr.get("gross_profit"))
            op_inc         = _f(isr.get("operating_income"))
            net_inc        = _f(isr.get("net_income"))
            net_inc_common = _f(isr.get("net_income_to_common")) or net_inc
            ebit           = _f(isr.get("ebit"))
            interest_exp   = _f(isr.get("interest_expense"))
            pretax         = _f(isr.get("pretax_income"))
            tax            = _f(isr.get("tax_expense"))

            total_assets   = _f(bsr.get("total_assets"))
            current_assets = _f(bsr.get("current_assets"))
            current_liab   = _f(bsr.get("current_liabilities"))
            total_debt     = _f(bsr.get("total_debt"))
            lt_debt        = _f(bsr.get("long_term_debt"))
            equity         = _f(bsr.get("shareholders_equity"))
            cash           = _f(bsr.get("cash_and_cash_equivalents"))
            inventory      = _f(bsr.get("inventory"))
            intangibles    = _f(bsr.get("intangible_assets"))
            goodwill       = _f(bsr.get("goodwill"))
            shares         = _f(bsr.get("shares_outstanding"))

            cfo            = _f(cfr.get("cash_from_operating_activities"))
            capex          = _f(cfr.get("capital_expenditures"))
            div_paid       = _f(cfr.get("dividends_paid"))
            div_paid_abs   = abs(div_paid) if div_paid is not None else None

            fcf = _fcf(cfo, capex)

            # ── Computed ratios ────────────────────────────────────────
            tax_rate = None
            if pretax is not None and pretax != 0 and tax is not None:
                tax_rate = max(0.0, min(1.0, tax / pretax))

            nopat = None
            if ebit is not None:
                nopat = ebit * (1.0 - (tax_rate if tax_rate is not None else 0.21))

            invested_capital = None
            if total_debt is not None and equity is not None:
                invested_capital = total_debt + equity - (cash or 0.0)

            roic = _safe_div(nopat, invested_capital) if nopat is not None and invested_capital not in (None, 0.0) else None
            roe  = _safe_div(net_inc_common, equity) if net_inc_common is not None and equity not in (None, 0.0) else None
            roa  = _safe_div(net_inc, total_assets) if net_inc is not None and total_assets not in (None, 0.0) else None

            gross_margin     = _safe_div(gross_profit, revenue)
            operating_margin = _safe_div(op_inc, revenue)
            net_margin       = _safe_div(net_inc, revenue)
            fcf_margin       = _safe_div(fcf, revenue)

            debt_to_equity = _safe_div(total_debt, equity) if total_debt is not None and equity not in (None, 0.0) else None
            lt_debt_assets = _safe_div(lt_debt, total_assets) if lt_debt is not None and total_assets not in (None, 0.0) else None

            current_ratio = _safe_div(current_assets, current_liab) if current_assets is not None and current_liab not in (None, 0.0) else None
            asset_turnover = _safe_div(revenue, total_assets) if revenue is not None and total_assets not in (None, 0.0) else None

            working_capital = (current_assets - current_liab) if current_assets is not None and current_liab is not None else None

            # ── Health scores ──────────────────────────────────────────
            # Build a flat dict for the _compute helpers to consume.
            period_dict: Dict[str, Any] = {
                "roa": roa,
                "cash_from_operating_activities": cfo,
                "total_assets": total_assets,
                "long_term_debt_to_assets": lt_debt_assets,
                "current_ratio": current_ratio,
                "shares_outstanding": shares,
                "gross_margin": gross_margin,
                "asset_turnover": asset_turnover,
                "working_capital": working_capital,
                "retained_earnings": _f(bsr.get("retained_earnings")),
                "ebit": ebit,
                "market_cap": _f(bsr.get("market_cap")),
                "total_liabilities": _f(bsr.get("total_liabilities")),
                "revenue": revenue,
            }

            # Prior-period ratios for YoY Piotroski deltas.
            prior_q = prior_by_q.get(q) or {}
            piotroski = _compute_piotroski_score(period_dict, prior_q)

            altman_z = _compute_altman_z_score(period_dict)

            # ── Assemble output row ────────────────────────────────────
            period_end = (
                isr.get("period_end_date")
                or bsr.get("period_end_date")
                or cfr.get("period_end_date")
            )

            source_payload = {
                "is": {k: isr.get(k) for k in [
                    "revenue", "gross_profit", "operating_income", "net_income",
                    "ebit", "pretax_income", "tax_expense", "interest_expense",
                    "net_income_to_common",
                ]},
                "bs": {k: bsr.get(k) for k in [
                    "total_assets", "current_assets", "current_liabilities",
                    "total_debt", "long_term_debt", "shareholders_equity",
                    "cash_and_cash_equivalents", "inventory", "intangible_assets",
                    "goodwill", "shares_outstanding", "retained_earnings",
                    "market_cap", "total_liabilities",
                ]},
                "cf": {k: cfr.get(k) for k in [
                    "cash_from_operating_activities", "capital_expenditures",
                    "dividends_paid",
                ]},
            }

            all_quarterly_ratios.append({
                "company_id":       company_id,
                "fiscal_year":      fy,
                "fiscal_quarter":   q,
                "period_end_date":  period_end,
                "roic": roic,
                "roe":  roe,
                "roa":  roa,
                "gross_margin":     gross_margin,
                "operating_margin": operating_margin,
                "net_margin":       net_margin,
                "fcf_margin":       fcf_margin,
                "free_cash_flow":   fcf,
                "debt_to_equity":           debt_to_equity,
                "long_term_debt_to_assets": lt_debt_assets,
                "current_ratio":    current_ratio,
                "asset_turnover":   asset_turnover,
                "working_capital":  working_capital,
                "piotroski_score":  piotroski,
                "altman_z_score":   altman_z,
                "computed_at":      datetime.utcnow().isoformat(),
                "source_version_tag": _version_tag(source_payload),
                "data_source":      "derived",
                "confidence_score": float(
                    getattr(settings, "DERIVED_METRICS_CONFIDENCE_SCORE", 1.0)
                ),
            })

    if not all_quarterly_ratios:
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # ── Step 4: version-gated upsert ────────────────────────────────────
    existing_tags: Dict[tuple, str] = {}
    try:
        fiscal_quarters_paris = [
            (row["fiscal_year"], row["fiscal_quarter"])
            for row in all_quarterly_ratios
        ]
        # Batch fetch existing tags
        tags_resp = (
            supabase.table("financial_ratios")
            .select("fiscal_year, fiscal_quarter, source_version_tag")
            .eq("company_id", company_id)
            .neq("fiscal_quarter", None)
            .execute()
        )
        for r in tags_resp.data or []:
            fy = r.get("fiscal_year")
            fq = r.get("fiscal_quarter")
            tag = r.get("source_version_tag")
            if fy is not None and fq is not None and tag:
                existing_tags[(int(fy), int(fq))] = tag
    except Exception as e:
        logger.warning(
            "[HLTH] Tag pre-fetch failed for company_id=%s; "
            "falling back to full upsert: %s",
            company_id, e,
        )

    changed_rows = [
        row for row in all_quarterly_ratios
        if existing_tags.get((row["fiscal_year"], row["fiscal_quarter"]))
           != row["source_version_tag"]
    ]

    if not changed_rows:
        logger.debug(
            "[HLTH] All %d quarterly rows unchanged for company_id=%s",
            len(all_quarterly_ratios), company_id,
        )
        return {"count": len(all_quarterly_ratios), "rows_changed": 0, "upserted": False}

    supabase.table("financial_ratios").upsert(
        changed_rows, on_conflict="company_id,fiscal_year,fiscal_quarter"
    ).execute()

    logger.info(
        "[HLTH] Upserted %d/%d health-score rows for company_id=%s",
        len(changed_rows), len(all_quarterly_ratios), company_id,
    )
    return {"count": len(all_quarterly_ratios), "rows_changed": len(changed_rows), "upserted": True}


# ─── Quarterly Valuation Metrics ────────────────────────────────────────────────────


async def compute_and_upsert_quarterly_valuation_metrics(company_id: int) -> Dict[str, Any]:
    """
    Computes quarterly valuation metrics from income_statements + balance_sheets +
    cash_flow_statements + price_history and writes to financial_ratios.

    Metrics per quarter:
      1. trailing_pe     = quarter_end_price / TTM_EPS   (NULL if TTM_EPS ≤ 0)
      2. market_cap      = shares_outstanding_diluted × quarter_end_price
      3. enterprise_value = market_cap + total_debt - cash_and_cash_equivalents
      4. ev_ebitda        = enterprise_value / ebitda     (NULL if ebitda ≤ 0)
      5. price_to_fcf     = enterprise_value / FCF        (NULL if FCF ≤ 0)
         where FCF = cash_from_operating_activities + capital_expenditures

    Version-gated: only upserts when source data changed.
    On-conflict key: (company_id, fiscal_year, fiscal_quarter).

    Returns: {"count": int, "rows_changed": int, "upserted": bool}
    """
    # ── 1. Fetch quarterly income statements (now includes ebitda) ────────
    is_resp = (
        supabase.table("income_statements")
        .select("fiscal_year, fiscal_quarter, period_end_date, net_income_to_common, shares_outstanding_diluted, ebitda")
        .eq("company_id", company_id)
        .not_.is_("fiscal_quarter", "null")
        .order("fiscal_year", desc=False)
        .order("fiscal_quarter", desc=False)
        .execute()
    )
    is_rows = is_resp.data or []
    if not is_rows:
        logger.info("[VPE] No quarterly income data for company_id=%s", company_id)
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # Build a chronologically ordered list of (fy, fq, eps, ebitda, period_end)
    quarters: List[Dict] = []
    for r in is_rows:
        fy = r.get("fiscal_year")
        fq = r.get("fiscal_quarter")
        net_inc = _f(r.get("net_income_to_common"))
        shares = _f(r.get("shares_outstanding_diluted"))
        ebitda = _f(r.get("ebitda"))
        end_date = r.get("period_end_date")
        if fy is None or fq is None or end_date is None:
            continue
        eps = _safe_div(net_inc, shares)
        quarters.append({
            "fiscal_year": int(fy),
            "fiscal_quarter": int(fq),
            "eps": eps,
            "ebitda": ebitda,
            "shares": shares,
            "period_end_date": str(end_date)[:10],
        })
    quarters.sort(key=lambda x: (x["fiscal_year"], x["fiscal_quarter"]))

    if len(quarters) < 4:
        logger.info("[VPE] Need at least 4 quarters of data for TTM EPS (got %d)", len(quarters))
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # ── 2. Compute TTM EPS per quarter ────────────────────────────────────
    for i, q in enumerate(quarters):
        if i >= 3:
            ttm = sum(
                quarters[j]["eps"] or 0 for j in range(i - 3, i + 1)
                if quarters[j]["eps"] is not None
            )
            q["ttm_eps"] = ttm
        else:
            q["ttm_eps"] = None
        q["trailing_pe"] = None
        q["quarter_end_price"] = None
        q["market_cap"] = None
        q["enterprise_value"] = None
        q["ev_ebitda"] = None
        q["free_cash_flow"] = None
        q["price_to_fcf"] = None

    # ── 3. Fetch balance_sheets → lookup by (fy, fq) ──────────────────────
    bs_resp = (
        supabase.table("balance_sheets")
        .select("fiscal_year, fiscal_quarter, total_debt, cash_and_cash_equivalents")
        .eq("company_id", company_id)
        .not_.is_("fiscal_quarter", "null")
        .execute()
    )
    bs_by_key: Dict[tuple, Dict] = {}
    for r in bs_resp.data or []:
        fy = r.get("fiscal_year")
        fq = r.get("fiscal_quarter")
        if fy is not None and fq is not None:
            bs_by_key[(int(fy), int(fq))] = r

    # ── 4. Fetch cash_flow_statements → lookup by (fy, fq) ────────────────
    cf_resp = (
        supabase.table("cash_flow_statements")
        .select("fiscal_year, fiscal_quarter, cash_from_operating_activities, capital_expenditures")
        .eq("company_id", company_id)
        .not_.is_("fiscal_quarter", "null")
        .execute()
    )
    cf_by_key: Dict[tuple, Dict] = {}
    for r in cf_resp.data or []:
        fy = r.get("fiscal_year")
        fq = r.get("fiscal_quarter")
        if fy is not None and fq is not None:
            cf_by_key[(int(fy), int(fq))] = r

    # ── 5. Fetch price_history for quarter-end close prices ───────────────
    ph_resp = (
        supabase.table("price_history")
        .select("price_date, close_price")
        .eq("company_id", company_id)
        .order("price_date", desc=False)
        .execute()
    )
    ph_rows = ph_resp.data or []

    price_by_date: Dict[str, float] = {}
    for r in ph_rows:
        d = r.get("price_date")
        cp = _f(r.get("close_price"))
        if d and cp is not None:
            price_by_date[str(d)[:10]] = cp

    if price_by_date:
        price_dates_sorted = sorted(price_by_date.keys())

        for q in quarters:
            end = q["period_end_date"]
            if not end or q["ttm_eps"] is None:
                continue
            try:
                end_dt = datetime.strptime(end, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            best_price = None
            best_diff = timedelta(days=46)
            for pd in price_dates_sorted:
                try:
                    pd_dt = datetime.strptime(pd, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                diff = abs((pd_dt - end_dt).days)
                if diff < best_diff.days:
                    best_diff = timedelta(days=diff)
                    best_price = price_by_date[pd]
            if best_price is not None and best_diff.days <= 45:
                q["quarter_end_price"] = best_price
                pe = _safe_div(best_price, q["ttm_eps"])
                q["trailing_pe"] = round(pe, 2) if pe is not None else None

                # ── Compute valuation multiples ──────────────────────────
                key = (q["fiscal_year"], q["fiscal_quarter"])
                shares = q.get("shares")
                ebitda = q.get("ebitda")

                # market_cap
                if shares is not None:
                    q["market_cap"] = round(shares * best_price, 2)

                # enterprise_value = market_cap + total_debt - cash
                bs_row = bs_by_key.get(key)
                if bs_row is not None:
                    total_debt = _f(bs_row.get("total_debt"))
                    cash = _f(bs_row.get("cash_and_cash_equivalents"))
                    mcap = q["market_cap"]
                    if mcap is not None and total_debt is not None and cash is not None:
                        q["enterprise_value"] = round(mcap + total_debt - cash, 2)

                # ev_ebitda
                ev = q["enterprise_value"]
                if ev is not None and ebitda is not None and ebitda > 0:
                    q["ev_ebitda"] = round(ev / ebitda, 4)

                # free_cash_flow and price_to_fcf
                cf_row = cf_by_key.get(key)
                if cf_row is not None:
                    cfo = _f(cf_row.get("cash_from_operating_activities"))
                    capex = _f(cf_row.get("capital_expenditures"))
                    if cfo is not None and capex is not None:
                        fcf = cfo + capex  # capex is negative
                        q["free_cash_flow"] = fcf
                        if ev is not None and fcf > 0:
                            q["price_to_fcf"] = round(ev / fcf, 4)

    # ── 6. Assemble rows for upsert ───────────────────────────────────────
    out: List[Dict[str, Any]] = []
    for q in quarters:
        key = (q["fiscal_year"], q["fiscal_quarter"])
        bs_row = bs_by_key.get(key)
        cf_row = cf_by_key.get(key)

        source_payload = {
            "is": {"net_income_to_common": None, "shares_outstanding_diluted": None, "ebitda": None},
            "bs": {"total_debt": None, "cash_and_cash_equivalents": None},
            "cf": {"cash_from_operating_activities": None, "capital_expenditures": None},
            "price": {"close_price": q.get("quarter_end_price")},
        }
        for r in is_rows:
            if r.get("fiscal_year") == q["fiscal_year"] and r.get("fiscal_quarter") == q["fiscal_quarter"]:
                source_payload["is"] = {
                    "net_income_to_common": r.get("net_income_to_common"),
                    "shares_outstanding_diluted": r.get("shares_outstanding_diluted"),
                    "ebitda": r.get("ebitda"),
                }
                break
        if bs_row:
            source_payload["bs"] = {
                "total_debt": bs_row.get("total_debt"),
                "cash_and_cash_equivalents": bs_row.get("cash_and_cash_equivalents"),
            }
        if cf_row:
            source_payload["cf"] = {
                "cash_from_operating_activities": cf_row.get("cash_from_operating_activities"),
                "capital_expenditures": cf_row.get("capital_expenditures"),
            }

        out.append({
            "company_id":          company_id,
            "fiscal_year":         q["fiscal_year"],
            "fiscal_quarter":      q["fiscal_quarter"],
            "period_end_date":     q["period_end_date"],
            "trailing_pe":         q["trailing_pe"],
            "quarter_end_price":   q.get("quarter_end_price"),
            "market_cap":          q.get("market_cap"),
            "enterprise_value":    q.get("enterprise_value"),
            "ev_ebitda":           q.get("ev_ebitda"),
            "price_to_fcf":        q.get("price_to_fcf"),
            "computed_at":         datetime.utcnow().isoformat(),
            "source_version_tag":  _version_tag(source_payload),
            "data_source":         "derived",
            "confidence_score":    float(
                getattr(settings, "DERIVED_METRICS_CONFIDENCE_SCORE", 1.0)
            ),
        })

    if not out:
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # ── 7. Version-gated upsert ───────────────────────────────────────────
    existing_tags: Dict[tuple, str] = {}
    try:
        tags_resp = (
            supabase.table("financial_ratios")
            .select("fiscal_year, fiscal_quarter, source_version_tag")
            .eq("company_id", company_id)
            .not_.is_("fiscal_quarter", "null")
            .execute()
        )
        for r in tags_resp.data or []:
            fy = r.get("fiscal_year")
            fq = r.get("fiscal_quarter")
            tag = r.get("source_version_tag")
            if fy is not None and fq is not None and tag:
                existing_tags[(int(fy), int(fq))] = tag
    except Exception as e:
        logger.warning(
            "[VPE] Tag pre-fetch failed for company_id=%s; "
            "falling back to full upsert: %s",
            company_id, e,
        )

    changed_rows = [
        row for row in out
        if existing_tags.get((row["fiscal_year"], row["fiscal_quarter"]))
           != row["source_version_tag"]
    ]

    if not changed_rows:
        logger.debug(
            "[VPE] All %d rows unchanged for company_id=%s",
            len(out), company_id,
        )
        return {"count": len(out), "rows_changed": 0, "upserted": False}

    supabase.table("financial_ratios").upsert(
        changed_rows, on_conflict="company_id,fiscal_year,fiscal_quarter"
    ).execute()

    logger.info(
        "[VPE] Upserted %d/%d valuation-ratio rows for company_id=%s",
        len(changed_rows), len(out), company_id,
    )
    return {"count": len(out), "rows_changed": len(changed_rows), "upserted": True}


async def compute_and_upsert_dividend_metrics(company_id: int) -> Dict[str, Any]:
    """
    Computes dividend-specific metrics from raw statement tables and writes to
    dividend_metrics (on_conflict: company_id, fiscal_year).

    Sources (read-only):
      dividend_history       — ex_dividend_date, dividend_amount (per-share amounts)
      income_statements      — net_income, net_income_to_common (annual, no quarter)
      cash_flow_statements   — dividends_paid, cash_from_operating_activities,
                               capital_expenditures (annual, no quarter)

    Writes to: dividend_metrics

    Computed metrics per fiscal year:
      annual_dps                — sum of per-share dividend payments in that calendar year
      dividend_growth_rate_3yr  — CAGR of annual_dps over 3 years ending this year
      dividend_growth_rate_5yr  — CAGR of annual_dps over 5 years ending this year
      dividend_growth_rate_10yr — CAGR of annual_dps over 10 years ending this year
      consecutive_years_paid    — streak of years with YoY increase in annual_dps
      cash_dividend_payout_ratio — abs(dividends_paid) / net_income (GAAP basis)
      retention_ratio            — 1 − cash_dividend_payout_ratio
      fcfe_coverage_ratio        — fcf / abs(dividends_paid)

    Caller: call this after compute_and_upsert_derived_financial_metrics() in the
    market_data_scheduler refresh cycle for dividend-paying companies.
    """
    # ── 1. Fetch dividend history ──────────────────────────────────────────────
    dh_resp = (
        supabase.table("dividend_history")
        .select("ex_dividend_date, dividend_amount")
        .eq("company_id", company_id)
        .not_.is_("ex_dividend_date", None)
        .not_.is_("dividend_amount", None)
        .order("ex_dividend_date", desc=False)
        .execute()
    )
    dh_rows = dh_resp.data or []

    if not dh_rows:
        logger.info("[DIV_METRICS] No dividend history for company_id=%s — skipping", company_id)
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # ── 2. Aggregate per-share DPS totals by calendar year ────────────────────
    # dividend_history.dividend_amount is already a per-share amount per payment.
    # Summing within a year gives annual DPS (per share) — no shares division needed.
    annual_dps: Dict[int, float] = {}
    for row in dh_rows:
        raw_date = row.get("ex_dividend_date", "")
        amt = _f(row.get("dividend_amount"))
        if not raw_date or amt is None:
            continue
        try:
            year = int(str(raw_date)[:4])
        except (ValueError, TypeError):
            continue
        annual_dps[year] = annual_dps.get(year, 0.0) + amt

    if not annual_dps:
        return {"count": 0, "rows_changed": 0, "upserted": False}

    years_sorted = sorted(annual_dps.keys())

    # ── 3. Fetch income statements (annual) ───────────────────────────────────
    is_resp = (
        supabase.table("income_statements")
        .select("fiscal_year, net_income, net_income_to_common")
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    is_by_year: Dict[int, Dict] = {}
    for r in (is_resp.data or []):
        fy = r.get("fiscal_year")
        if fy is not None:
            is_by_year[int(fy)] = r

    # ── 4. Fetch cash flow statements (annual) ────────────────────────────────
    cf_resp = (
        supabase.table("cash_flow_statements")
        .select("fiscal_year, dividends_paid, cash_from_operating_activities, capital_expenditures")
        .eq("company_id", company_id)
        .is_("fiscal_quarter", None)
        .order("fiscal_year", desc=False)
        .execute()
    )
    cf_by_year: Dict[int, Dict] = {}
    for r in (cf_resp.data or []):
        fy = r.get("fiscal_year")
        if fy is not None:
            cf_by_year[int(fy)] = r

    # ── 5. Helpers ────────────────────────────────────────────────────────────
    def _cagr_between(start_year: int, end_year: int) -> Optional[float]:
        """CAGR of annual_dps from start_year to end_year."""
        v0 = annual_dps.get(start_year)
        vn = annual_dps.get(end_year)
        n  = end_year - start_year
        if v0 is None or vn is None or v0 <= 0 or vn <= 0 or n <= 0:
            return None
        try:
            return (vn / v0) ** (1.0 / n) - 1.0
        except Exception:
            return None

    def _consecutive_increases() -> int:
        """Count of trailing years where annual_dps increased YoY (>0.1% threshold)."""
        if len(years_sorted) < 2:
            return 0
        count = 0
        for i in range(len(years_sorted) - 1, 0, -1):
            curr = annual_dps.get(years_sorted[i], 0.0)
            prev = annual_dps.get(years_sorted[i - 1], 0.0)
            if prev > 0 and curr > prev * 1.001:
                count += 1
            else:
                break
        return count

    consec = _consecutive_increases()

    # ── 6. Compute one row per fiscal year ────────────────────────────────────
    out: List[Dict[str, Any]] = []

    for fiscal_year in years_sorted:
        dps = annual_dps[fiscal_year]
        isr = is_by_year.get(fiscal_year) or {}
        cfr = cf_by_year.get(fiscal_year) or {}

        # CAGRs relative to this year
        cagr_3y  = _cagr_between(fiscal_year - 3,  fiscal_year)
        cagr_5y  = _cagr_between(fiscal_year - 5,  fiscal_year)
        cagr_10y = _cagr_between(fiscal_year - 10, fiscal_year)

        # Payout and coverage from cash flow
        divs_paid_raw = _f(cfr.get("dividends_paid"))
        divs_paid_abs = abs(divs_paid_raw) if divs_paid_raw is not None else None

        net_income = _f(isr.get("net_income_to_common")) or _f(isr.get("net_income"))
        cash_payout = _safe_div(divs_paid_abs, net_income) if (
            divs_paid_abs is not None and net_income and net_income > 0
        ) else None
        retention = (1.0 - cash_payout) if cash_payout is not None else None

        ocf   = _f(cfr.get("cash_from_operating_activities"))
        capex = _f(cfr.get("capital_expenditures"))
        fcf   = _fcf(ocf, capex) if (ocf is not None and capex is not None) else None
        fcf_cov = _safe_div(fcf, divs_paid_abs) if (
            fcf is not None and divs_paid_abs and divs_paid_abs > 0
        ) else None

        out.append({
            "company_id":                 company_id,
            "fiscal_year":                int(fiscal_year),
            "annual_dps":                 round(dps, 4),
            "dividend_growth_rate_3yr":   round(cagr_3y,  4) if cagr_3y  is not None else None,
            "dividend_growth_rate_5yr":   round(cagr_5y,  4) if cagr_5y  is not None else None,
            "dividend_growth_rate_10yr":  round(cagr_10y, 4) if cagr_10y is not None else None,
            "consecutive_years_paid":     consec,
            "cash_dividend_payout_ratio": round(cash_payout, 4) if cash_payout is not None else None,
            "retention_ratio":            round(retention,   4) if retention   is not None else None,
            "fcfe_coverage_ratio":        round(fcf_cov,     2) if fcf_cov     is not None else None,
        })

    if not out:
        return {"count": 0, "rows_changed": 0, "upserted": False}

    # ── 7. Upsert — unique on (company_id, fiscal_year) ───────────────────────
    # created_at is intentionally omitted: DB DEFAULT handles insert,
    # and we do not want to overwrite it on conflict updates.
    try:
        supabase.table("dividend_metrics").upsert(
            out, on_conflict="company_id,fiscal_year"
        ).execute()
        logger.info(
            "[DIV_METRICS] Upserted %d rows into dividend_metrics for company_id=%s",
            len(out), company_id,
        )
        return {"count": len(out), "rows_changed": len(out), "upserted": True}
    except Exception as exc:
        logger.error(
            "[DIV_METRICS] Upsert failed for company_id=%s: %s", company_id, exc
        )
        return {"count": len(out), "rows_changed": 0, "upserted": False}