"""
ValuationRepository
-------------------
Supabase-backed repository for valuation inputs, freshness checks, and persistence.

Key responsibilities
* Input resolution for Rule #1 (EPS, growth, industry PE, histories, shares)
* Freshness gate support:
    - get_last_valuation_ts(company_id)
    - get_latest_dependency_ts(company_id)
* Persistence:
    - upsert_intrinsic_value_analysis
    - insert_valuation_run
    - (optional) insert_diagnostics_batch
* Cached read helpers for fast API returns

Improvements in this version
- Robust handling for Supabase DATE/TIMESTAMPTZ fields (strings → date/datetime)
- Fixed get_cached_intrinsic_value() query + stray code
- Safer _as_datetime_from_date() and _normalize_datetime()
"""

from __future__ import annotations

import logging
from datetime import datetime, date, time
from typing import Any, Dict, List, Optional

from database import supabase

logger = logging.getLogger(__name__)

# -------------------------------
# Helpers: parsing and utilities
# -------------------------------

def _first(data: Any) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return None


def _normalize_date(d: Any) -> Optional[date]:
    """
    Normalize Supabase DATE payloads (often ISO strings) into datetime.date.
    Accepts: datetime.date, ISO string (YYYY-MM-DD), or None.
    """
    if d is None:
        return None
    if isinstance(d, date) and not isinstance(d, datetime):
        return d
    if isinstance(d, str):
        try:
            return date.fromisoformat(d)
        except Exception:
            return None
    return None


def _normalize_datetime(ts: Any) -> Optional[datetime]:
    """
    Normalize Supabase TIMESTAMPTZ payloads (strings with 'Z' or offset) into datetime.
    Accepts: datetime, ISO string, or None.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        return ts
    if isinstance(ts, str):
        try:
            s = ts.replace("Z", "+00:00")
            return datetime.fromisoformat(s)
        except Exception:
            return None
    return None


def _as_datetime_from_date(d: Any) -> Optional[datetime]:
    """
    Convert a DATE (date or ISO string) into a datetime at 00:00 for comparisons.
    """
    base = _normalize_date(d)
    if not base:
        return None
    return datetime.combine(base, time(0, 0, 0))


def _max_dt(*vals: Optional[datetime]) -> Optional[datetime]:
    present = [v for v in vals if v is not None]
    return max(present) if present else None


# -------------------------------
# Repository
# -------------------------------

class ValuationRepository:
    """Supabase repository used by valuation services/guards."""

    # ---------------------------
    # Company context
    # ---------------------------
    async def get_company_context(self, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("companies")
                .select("company_id, currency, sector, industry, ticker_symbol")
                .eq("ticker_symbol", symbol.upper())
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return row if row else None
        except Exception as e:
            logger.error("get_company_context failed for %s: %s", symbol, e)
            return None

    async def get_company_meta(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("companies")
                .select("company_id, currency, sector, industry, ticker_symbol, next_earnings_date")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_company_meta failed: %s", e)
            return None

    # ---------------------------
    # Freshness gate (for RecomputeGuard)
    # ---------------------------
    async def get_last_valuation_ts(self, company_id: int) -> Optional[datetime]:
        """
        Prefer intrinsic_value_analysis.last_updated.
        Fallback to latest valuation_runs.run_at for method='rule1'.
        """
        try:
            iva = (
                supabase.table("intrinsic_value_analysis")
                .select("last_updated")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            row = _first(iva.data)
            ts = _normalize_datetime(row["last_updated"]) if row and row.get("last_updated") else None
            if ts:
                return ts
        except Exception:
            # soft fail to fallback
            pass

        try:
            runs = (
                supabase.table("valuation_runs")
                .select("run_at")
                .eq("company_id", company_id)
                .eq("method", "rule1")
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(runs.data)
            return _normalize_datetime(row["run_at"]) if row and row.get("run_at") else None
        except Exception as e:
            logger.error("get_last_valuation_ts fallback failed: %s", e)
            return None

    async def get_latest_dependency_ts(self, company_id: int) -> Optional[datetime]:
        """
        Compute the latest timestamp across all dependency signals that
        can affect Rule #1 valuation.
        """
        try:
            # Pre-fetch sector/industry for industry_multiples lookup
            cm = await self.get_company_meta(company_id)
            sector = cm.get("sector") if cm else None
            industry = cm.get("industry") if cm else None

            # company_summary.snapshot_date (DATE)
            cs = (
                supabase.table("company_summary")
                .select("snapshot_date")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_row = _first(cs.data)
            cs_dt = _as_datetime_from_date(cs_row.get("snapshot_date")) if cs_row else None

            # earnings_forecast.report_date (DATE)
            ef = (
                supabase.table("earnings_forecast")
                .select("report_date")
                .eq("company_id", company_id)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            ef_row = _first(ef.data)
            ef_dt = _as_datetime_from_date(ef_row.get("report_date")) if ef_row else None

            # earnings.updated_at (TIMESTAMPTZ)
            er = (
                supabase.table("earnings")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            er_row = _first(er.data)
            er_dt = _normalize_datetime(er_row.get("updated_at")) if er_row else None

            # income_statements.updated_at (TIMESTAMPTZ)
            is_ = (
                supabase.table("income_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            is_row = _first(is_.data)
            is_dt = _normalize_datetime(is_row.get("updated_at")) if is_row else None

            # statistics.updated_at (TIMESTAMPTZ)
            st = (
                supabase.table("statistics")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            st_row = _first(st.data)
            st_dt = _normalize_datetime(st_row.get("updated_at")) if st_row else None

            # splits.report_date (DATE)
            sp = (
                supabase.table("splits")
                .select("report_date")
                .eq("company_id", company_id)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            sp_row = _first(sp.data)
            sp_dt = _as_datetime_from_date(sp_row.get("report_date")) if sp_row else None

            # industry_multiples.calculation_date (DATE) for this sector+industry
            im_dt: Optional[datetime] = None
            if sector and industry:
                im = (
                    supabase.table("industry_multiples")
                    .select("calculation_date")
                    .eq("sector", sector)
                    .eq("industry", industry)
                    .order("calculation_date", desc=True)
                    .limit(1)
                    .execute()
                )
                im_row = _first(im.data)
                im_dt = _as_datetime_from_date(im_row.get("calculation_date")) if im_row else None

            latest = _max_dt(cs_dt, ef_dt, er_dt, is_dt, st_dt, sp_dt, im_dt)
            return latest

        except Exception as e:
            logger.error("get_latest_dependency_ts failed for company_id=%s: %s", company_id, e)
            return None

    # ---------------------------
    # Inputs: EPS, growth, industry PE, histories
    # ---------------------------
    async def get_trailing_eps(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("company_summary")
                .select("trailing_eps, snapshot_date")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_trailing_eps failed: %s", e)
            return None

    async def compute_ttm_eps_fallback(self, company_id: int) -> Optional[float]:
        """
        Approximation:
        - latest annual income statement: net_income_to_common
        - latest annual statistics: shares_outstanding_diluted
        - EPS ≈ net_income_to_common / diluted_shares
        """
        try:
            inc = (
                supabase.table("income_statements")
                .select("net_income_to_common, fiscal_year, fiscal_quarter")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            st = (
                supabase.table("statistics")
                .select("shares_outstanding_diluted, fiscal_year, fiscal_quarter, period_type")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .eq("period_type", "fiscal")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            inc_row = _first(inc.data)
            st_row = _first(st.data)
            if inc_row and st_row:
                ni = inc_row.get("net_income_to_common")
                sh = st_row.get("shares_outstanding_diluted")
                if ni is not None and sh and float(sh) > 0:
                    return float(ni) / float(sh)
            return None
        except Exception as e:
            logger.error("compute_ttm_eps_fallback failed: %s", e)
            return None

    async def get_eps_forecast_growth(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("earnings_forecast")
                .select("estimate_eps_growth, report_date, period_type")
                .eq("company_id", company_id)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_eps_forecast_growth failed: %s", e)
            return None

    async def get_eps_history(self, company_id: int) -> List[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("earnings")
                .select("fiscal_year, fiscal_quarter, eps_reported_diluted")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)  # annual fiscal rows only
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            return [{"fiscal_year": r["fiscal_year"], "eps": r.get("eps_reported_diluted")} for r in rows]
        except Exception as e:
            logger.error("get_eps_history failed: %s", e)
            return []

    async def get_revenue_history(self, company_id: int) -> List[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year,  fiscal_quarter, revenue")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)  # annual fiscal rows only
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            return [{"fiscal_year": r["fiscal_year"], "revenue": r.get("revenue")} for r in rows]
        except Exception as e:
            logger.error("get_revenue_history failed: %s", e)
            return []

    async def get_industry_multiples(self, sector: Optional[str], industry: Optional[str]) -> Optional[Dict[str, Any]]:
        if not sector or not industry:
            return None
        try:
            resp = (
                supabase.table("industry_multiples")
                .select("median_pe, median_eps_growth, calculation_date")
                .eq("sector", sector)
                .eq("industry", industry)
                .order("calculation_date", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_industry_multiples failed: %s", e)
            return None

    async def get_shares_history(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Annual fiscal shares only (avoid TTM contamination).
        Source: statistics.shares_outstanding_diluted
        """
        try:
            resp = (
                supabase.table("statistics")
                .select("fiscal_year, fiscal_quarter, period_type, shares_outstanding_diluted")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .eq("period_type", "fiscal")
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            return [
                {"fiscal_year": r["fiscal_year"], "shares_outstanding_diluted": r.get("shares_outstanding_diluted")}
                for r in rows
            ]
        except Exception as e:
            logger.error("get_shares_history failed: %s", e)
            return []

    async def get_recent_split_count_after(self, company_id: int, ref_date: date) -> int:
        try:
            resp = (
                supabase.table("splits")
                .select("report_date")
                .eq("company_id", company_id)
                .gt("report_date", ref_date.isoformat())
                .execute()
            )
            return len(resp.data or [])
        except Exception as e:
            logger.error("get_recent_split_count_after failed: %s", e)
            return 0

    async def get_next_earnings_date(self, company_id: int) -> Optional[date]:
        try:
            resp = (
                supabase.table("companies")
                .select("next_earnings_date")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            if not row:
                return None
            # Normalize to date
            return _normalize_date(row.get("next_earnings_date"))
        except Exception as e:
            logger.error("get_next_earnings_date failed: %s", e)
            return None

    # ---------------------------
    # NEW: Methods required by rule1_suitability.py
    # ---------------------------

    async def get_net_income_history(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Annual fiscal net income history.
        Source: income_statements.net_income
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, net_income")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            return [{"fiscal_year": r["fiscal_year"], "net_income": r.get("net_income")} for r in rows]
        except Exception as e:
            logger.error("get_net_income_history failed: %s", e)
            return []

    async def get_eps_yearly_series(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Wrapper for annual EPS series.
        Source: earnings.eps_reported_diluted (annual fiscal rows)
        """
        return await self.get_eps_history(company_id)

    async def get_revenue_yearly_series(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Wrapper for annual revenue series.
        Source: income_statements.revenue (annual fiscal rows)
        """
        return await self.get_revenue_history(company_id)

    async def get_balance_sheet_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Latest annual fiscal balance sheet.
        Source: balance_sheets (fiscal_quarter IS NULL)
        """
        try:
            resp = (
                supabase.table("balance_sheets")
                .select("fiscal_year, fiscal_quarter, total_debt, shareholders_equity, updated_at, confidence_score")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_balance_sheet_latest failed: %s", e)
            return None

    async def get_income_statement_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Latest annual fiscal income statement.
        Source: income_statements (fiscal_quarter IS NULL)
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select(
                    "fiscal_year, fiscal_quarter, ebit, interest_expense, net_income_to_common, net_income, updated_at, confidence_score"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_income_statement_latest failed: %s", e)
            return None

    async def get_cash_flow_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Latest annual fiscal cash flow statement.
        Source: cash_flow_statements (fiscal_quarter IS NULL)
        """
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select(
                    "fiscal_year, fiscal_quarter, cash_from_operating_activities, capital_expenditures, updated_at, confidence_score"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_cash_flow_latest failed: %s", e)
            return None

    async def get_roic_history(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Annual fiscal ROIC history.
        Source: statistics.return_on_invested_capital_pct (annual fiscal rows)
        """
        try:
            resp = (
                supabase.table("statistics")
                .select("fiscal_year, fiscal_quarter, period_type, return_on_invested_capital_pct")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .eq("period_type", "fiscal")
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            # evaluator expects key 'roic'
            return [{"fiscal_year": r["fiscal_year"], "roic": r.get("return_on_invested_capital_pct")} for r in rows]
        except Exception as e:
            logger.error("get_roic_history failed: %s", e)
            return []

    # ---------------------------
    # NEW: Cached-path hydration (moved from service)
    # ---------------------------
    async def get_last_rule1_output_snapshot(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("valuation_runs")
                .select("output_snapshot")
                .eq("company_id", company_id)
                .eq("method", "rule1")
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return (row.get("output_snapshot") if row else None) or None
        except Exception:
            return None

    async def get_last_rule1_diagnostics(self, company_id: int) -> Dict[str, Any]:
        """
        Returns a minimal dict used by cached path:
          { applicability, dataQuality, assumptions }
        Returns {} if missing.
        """
        snap = await self.get_last_rule1_output_snapshot(company_id)
        if not snap:
            return {}

        app = snap.get("applicability") or {}
        dq = snap.get("dataQuality") or {}
        assumptions = (dq.get("inputDecisions") or {}).get("assumptions", {}) if isinstance(dq, dict) else {}

        return {
            "applicability": app,
            "dataQuality": dq,
            "assumptions": assumptions,
        }


    # ---------------------------
    # Parameters (defaults + overrides)
    # ---------------------------
    async def get_method_params(self, company_id: int) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        try:
            defaults = (
                supabase.table("valuation_method_defaults")
                .select("params, updated_at")
                .eq("method", "rule1")
                .limit(1)
                .execute()
            )
            drow = _first(defaults.data)
            if drow and drow.get("params"):
                out.update(drow["params"])
        except Exception as e:
            logger.error("get_method_params defaults failed: %s", e)

        try:
            overrides = (
                supabase.table("company_valuation_overrides")
                .select("params, updated_at")
                .eq("company_id", company_id)
                .eq("method", "rule1")
                .limit(1)
                .execute()
            )
            orow = _first(overrides.data)
            if orow and orow.get("params"):
                out.update(orow["params"])
        except Exception as e:
            logger.error("get_method_params overrides failed: %s", e)

        return out

    # ---------------------------
    # Persistence
    # ---------------------------
    async def upsert_intrinsic_value_analysis(self, company_id: int, payload: Dict[str, Any]) -> None:
        """
        payload requires:
          - growth_rate
          - current_eps
          - future_pe
          - future_price
          - sticker_price
          - mos_price
        """
        try:
            data = {
                "company_id": company_id,
                "growth_rate": payload["growth_rate"],
                "current_eps": payload["current_eps"],
                "future_pe": payload["future_pe"],
                "future_price": payload["future_price"],
                "sticker_price": payload["sticker_price"],
                "mos_price": payload["mos_price"],
            }
            supabase.table("intrinsic_value_analysis").upsert(data, on_conflict="company_id").execute()
        except Exception as e:
            logger.error("upsert_intrinsic_value_analysis failed: %s", e)
            raise

    async def insert_valuation_run(self, company_id: int, run: Dict[str, Any]) -> None:
        """
        run must contain:
          - run_by_user_id (nullable)
          - input_snapshot (json)
          - assumption_snapshot (json)
          - output_snapshot (json)
          - data_version_tag (nullable)
          - notes (nullable)
        """
        try:
            rec = {
                "company_id": company_id,
                "method": "rule1",
                "run_by_user_id": run.get("run_by_user_id"),
                "input_snapshot": run["input_snapshot"],
                "assumption_snapshot": run["assumption_snapshot"],
                "output_snapshot": run["output_snapshot"],
                "data_version_tag": run.get("data_version_tag"),
                "notes": run.get("notes"),
            }
            supabase.table("valuation_runs").insert(rec).execute()
        except Exception as e:
            logger.error("insert_valuation_run failed: %s", e)
            raise

    async def insert_diagnostics_batch(self, company_id: int, flags: List[Dict[str, Any]]) -> None:
        if not flags:
            return
        try:
            rows = [
                {
                    "company_id": company_id,
                    "method": "rule1",
                    "code": f.get("code"),
                    "severity": f.get("severity"),
                    "message": f.get("message"),
                    "context": f.get("evidence") or f.get("context") or {},
                }
                for f in flags
            ]
            supabase.table("valuation_diagnostics").insert(rows).execute()
        except Exception as e:
            logger.error("insert_diagnostics_batch failed: %s", e)

    # ---------------------------
    # Cached value read (for API)
    # ---------------------------
    async def get_cached_intrinsic_value(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Returns latest IVA snapshot for fast API cached return.
        """
        try:
            resp = (
                supabase.table("intrinsic_value_analysis")
                .select(
                    "company_id, growth_rate, current_eps, future_pe, future_price, "
                    "sticker_price, mos_price, last_updated"
                )
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return row if row else None
        except Exception as e:
            logger.error("get_cached_intrinsic_value failed: %s", e)
            return None

    # =====================================================================
    # ✅ RULE #1 HISTORY (FIXED)
    # =====================================================================

    async def get_rule1_history(
        self, symbol: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Returns recent Rule #1 valuation runs (newest first).

        Shape (FE-ready):
        {
          runAt,
          stickerPrice,
          mosPrice,
          futurePrice,
          growth,
          futurePE,
          score,
          category
        }
        """
        try:
            ctx = await self.get_company_context(symbol)
            if not ctx:
                return []

            company_id = ctx["company_id"]

            resp = (
                supabase.table("valuation_runs")
                .select(
                    "run_at, run_by_user_id, data_version_tag, notes, output_snapshot"
                )
                .eq("company_id", company_id)
                .eq("method", "rule1")
                .order("run_at", desc=True)
                .limit(limit)
                .execute()
            )

            rows = resp.data or []
            items: List[Dict[str, Any]] = []

            for r in rows:
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}

                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}

                items.append(
                    {
                        "runAt": run_at.isoformat() if run_at else None,
                        "stickerPrice": valuation.get("stickerPrice"),
                        "mosPrice": valuation.get("mosPrice"),
                        "futurePrice": valuation.get("futurePrice"),
                        "growth": valuation.get("growth"),
                        "futurePE": valuation.get("futurePE"),
                        "score": applicability.get("score"),
                        "category": applicability.get("category"),
                    }
                )

            return items

        except Exception as e:
            logger.error("get_rule1_history failed for %s: %s", symbol, e)
            return []
