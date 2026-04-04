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
from datetime import datetime
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