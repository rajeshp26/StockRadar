from __future__ import annotations

import logging
import math
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional

from database import supabase

logger = logging.getLogger(__name__)

# Allowed methods as per your DB check constraint / design intent
ALLOWED_METHODS = {
    "rule1",
    "ddm_gordon",
    "ddm_two_stage",
    "dcf",
    "owner_earnings",
    "relative",
}


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
    Normalize Supabase TIMESTAMPTZ payloads into datetime.
    Accepts Z suffix or offset strings.
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
    base = _normalize_date(d)
    if not base:
        return None
    return datetime.combine(base, time(0, 0, 0))


def _max_dt(*vals: Optional[datetime]) -> Optional[datetime]:
    present = [v for v in vals if v is not None]
    return max(present) if present else None


def _pct_to_frac(x: float) -> float:
    # Convert 12.5 => 0.125, but keep 0.125 unchanged.
    return x / 100.0 if x > 1.0 else x


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
            return _first(resp.data)
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
    # Freshness gate support (method-aware, backward compatible)
    # ---------------------------
    async def get_last_valuation_ts(self, company_id: int, method: str = "rule1") -> Optional[datetime]:
        """
        Rule #1 prefers intrinsic_value_analysis.last_updated.
        All methods fallback to valuation_runs.run_at.
        """
        if method not in ALLOWED_METHODS:
            method = "rule1"

        if method == "rule1":
            try:
                iva = (
                    supabase.table("intrinsic_value_analysis")
                    .select("last_updated")
                    .eq("company_id", company_id)
                    .limit(1)
                    .execute()
                )
                row = _first(iva.data)
                ts = _normalize_datetime(row.get("last_updated")) if row else None
                if ts:
                    return ts
            except Exception:
                pass

        try:
            runs = (
                supabase.table("valuation_runs")
                .select("run_at")
                .eq("company_id", company_id)
                .eq("method", method)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(runs.data)
            return _normalize_datetime(row.get("run_at")) if row else None
        except Exception as e:
            logger.error("get_last_valuation_ts failed (%s): %s", method, e)
            return None

    async def get_latest_dependency_ts(self, company_id: int, method: str = "rule1") -> Optional[datetime]:
        """
        Method-aware dependency timestamps.
        Backward compatible: if method omitted/invalid, defaults to rule1.
        """
        if method not in ALLOWED_METHODS:
            method = "rule1"

        if method == "rule1":
            return await self._latest_dependency_rule1(company_id)
        if method in {"ddm_gordon", "ddm_two_stage"}:
            return await self._latest_dependency_ddm(company_id, method=method)

        return None

    async def _latest_dependency_rule1(self, company_id: int) -> Optional[datetime]:
        """
        Existing Rule #1 dependency set.
        """
        try:
            cm = await self.get_company_meta(company_id)
            sector = cm.get("sector") if cm else None
            industry = cm.get("industry") if cm else None

            cs = (
                supabase.table("company_summary")
                .select("snapshot_date")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_dt = _as_datetime_from_date((_first(cs.data) or {}).get("snapshot_date"))

            ef = (
                supabase.table("earnings_forecast")
                .select("report_date")
                .eq("company_id", company_id)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            ef_dt = _as_datetime_from_date((_first(ef.data) or {}).get("report_date"))

            er = (
                supabase.table("earnings")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            er_dt = _normalize_datetime((_first(er.data) or {}).get("updated_at"))

            is_ = (
                supabase.table("income_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            is_dt = _normalize_datetime((_first(is_.data) or {}).get("updated_at"))

            st = (
                supabase.table("statistics")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            st_dt = _normalize_datetime((_first(st.data) or {}).get("updated_at"))

            sp = (
                supabase.table("splits")
                .select("report_date")
                .eq("company_id", company_id)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            sp_dt = _as_datetime_from_date((_first(sp.data) or {}).get("report_date"))

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
                im_dt = _as_datetime_from_date((_first(im.data) or {}).get("calculation_date"))

            md = (
                supabase.table("valuation_method_defaults")
                .select("updated_at")
                .eq("method", "rule1")
                .limit(1)
                .execute()
            )
            md_dt = _normalize_datetime((_first(md.data) or {}).get("updated_at"))

            co = (
                supabase.table("company_valuation_overrides")
                .select("updated_at")
                .eq("company_id", company_id)
                .eq("method", "rule1")
                .limit(1)
                .execute()
            )
            co_dt = _normalize_datetime((_first(co.data) or {}).get("updated_at"))

            return _max_dt(cs_dt, ef_dt, er_dt, is_dt, st_dt, sp_dt, im_dt, md_dt, co_dt)

        except Exception as e:
            logger.error("get_latest_dependency_ts(rule1) failed company_id=%s: %s", company_id, e)
            return None

    async def _latest_dependency_ddm(self, company_id: int, method: str) -> Optional[datetime]:
        """
        DDM dependencies:
          - company_summary.snapshot_date (beta)
          - dividend_history.updated_at
          - dividend_metrics.created_at (schema has created_at, not updated_at)
          - statistics.updated_at (ROE)
          - method defaults updated_at
          - company overrides updated_at
        Price is intentionally excluded (read-time only).
        """
        try:
            cs = (
                supabase.table("company_summary")
                .select("snapshot_date")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_dt = _as_datetime_from_date((_first(cs.data) or {}).get("snapshot_date"))

            dh = (
                supabase.table("dividend_history")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            dh_dt = _normalize_datetime((_first(dh.data) or {}).get("updated_at"))

            dm = (
                supabase.table("dividend_metrics")
                .select("created_at")
                .eq("company_id", company_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            dm_dt = _normalize_datetime((_first(dm.data) or {}).get("created_at"))

            st = (
                supabase.table("statistics")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            st_dt = _normalize_datetime((_first(st.data) or {}).get("updated_at"))

            md = (
                supabase.table("valuation_method_defaults")
                .select("updated_at")
                .eq("method", method)
                .limit(1)
                .execute()
            )
            md_dt = _normalize_datetime((_first(md.data) or {}).get("updated_at"))

            co = (
                supabase.table("company_valuation_overrides")
                .select("updated_at")
                .eq("company_id", company_id)
                .eq("method", method)
                .limit(1)
                .execute()
            )
            co_dt = _normalize_datetime((_first(co.data) or {}).get("updated_at"))

            return _max_dt(cs_dt, dh_dt, dm_dt, st_dt, md_dt, co_dt)
        except Exception as e:
            logger.error("get_latest_dependency_ts(%s) failed company_id=%s: %s", method, company_id, e)
            return None

    # ---------------------------
    # Parameters (defaults + overrides) METHOD-AWARE + BACKWARD COMPATIBLE
    # ---------------------------
    async def get_method_params(self, company_id: int, method: str = "rule1") -> Dict[str, Any]:
        """
        Merge valuation_method_defaults.params + company_valuation_overrides.params for the given method.
        Backward compatible: default method='rule1' if not provided.
        """
        if method not in ALLOWED_METHODS:
            method = "rule1"

        out: Dict[str, Any] = {}
        try:
            defaults = (
                supabase.table("valuation_method_defaults")
                .select("params, updated_at")
                .eq("method", method)
                .limit(1)
                .execute()
            )
            drow = _first(defaults.data)
            if drow and drow.get("params"):
                out.update(drow["params"])
        except Exception as e:
            logger.error("get_method_params defaults failed (%s): %s", method, e)

        try:
            overrides = (
                supabase.table("company_valuation_overrides")
                .select("params, updated_at")
                .eq("company_id", company_id)
                .eq("method", method)
                .limit(1)
                .execute()
            )
            orow = _first(overrides.data)
            if orow and orow.get("params"):
                out.update(orow["params"])
        except Exception as e:
            logger.error("get_method_params overrides failed (%s): %s", method, e)

        return out

    # Old name used by earlier code (keep compatibility)
    async def get_method_params_rule1(self, company_id: int) -> Dict[str, Any]:
        return await self.get_method_params(company_id, method="rule1")

    # ---------------------------
    # Cached-path hydration (method-aware)
    # ---------------------------
    async def get_last_output_snapshot(self, company_id: int, method: str) -> Optional[Dict[str, Any]]:
        if method not in ALLOWED_METHODS:
            method = "rule1"
        try:
            resp = (
                supabase.table("valuation_runs")
                .select("output_snapshot")
                .eq("company_id", company_id)
                .eq("method", method)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return (row.get("output_snapshot") if row else None) or None
        except Exception:
            return None

    async def get_last_rule1_output_snapshot(self, company_id: int) -> Optional[Dict[str, Any]]:
        return await self.get_last_output_snapshot(company_id, method="rule1")

    async def get_last_rule1_diagnostics(self, company_id: int) -> Dict[str, Any]:
        snap = await self.get_last_rule1_output_snapshot(company_id)
        if not snap:
            return {}

        app = snap.get("applicability") or {}
        dq = snap.get("dataQuality") or {}
        assumptions = (dq.get("inputDecisions") or {}).get("assumptions", {}) if isinstance(dq, dict) else {}

        return {"applicability": app, "dataQuality": dq, "assumptions": assumptions}

    # ✅ NEW: generic method diagnostics for cached path (required by ValuationService)
    async def get_last_method_diagnostics(self, company_id: int, method: str = "rule1") -> Dict[str, Any]:
        snap = await self.get_last_output_snapshot(company_id, method=method)
        if not snap:
            return {}

        app = snap.get("applicability") or {}
        dq = snap.get("dataQuality") or {}
        assumptions = (dq.get("inputDecisions") or {}).get("assumptions", {}) if isinstance(dq, dict) else {}

        return {"applicability": app, "dataQuality": dq, "assumptions": assumptions}

    # ---------------------------
    # Persistence (method-aware)
    # ---------------------------
    async def insert_valuation_run(self, company_id: int, run: Dict[str, Any], method: str = "rule1") -> None:
        """
        Backward compatible:
          - old callers pass (company_id, run)
          - new callers can pass method explicitly
        """
        if method not in ALLOWED_METHODS:
            logger.warning("insert_valuation_run received invalid method=%s; defaulting to rule1", method)
            method = "rule1"
        try:
            rec = {
                "company_id": company_id,
                "method": method,
                "run_by_user_id": run.get("run_by_user_id"),
                "input_snapshot": run["input_snapshot"],
                "assumption_snapshot": run["assumption_snapshot"],
                "output_snapshot": run["output_snapshot"],
                "data_version_tag": run.get("data_version_tag"),
                "notes": run.get("notes"),
            }
            supabase.table("valuation_runs").insert(rec).execute()
        except Exception as e:
            logger.error("insert_valuation_run failed (%s): %s", method, e)
            raise

    async def upsert_intrinsic_value_analysis(self, company_id: int, payload: Dict[str, Any]) -> None:
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

    # ---------------------------
    # Cached value read (Rule #1)
    # ---------------------------
    async def get_cached_intrinsic_value(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("intrinsic_value_analysis")
                .select(
                    "company_id, growth_rate, current_eps, future_pe, "
                    "future_price, sticker_price, mos_price, last_updated"
                )
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_cached_intrinsic_value failed: %s", e)
            return None

    # ---------------------------
    # Inputs: EPS, growth, histories (Rule #1)
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
                .is_("fiscal_quarter", None)
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
                .select("fiscal_year, fiscal_quarter, revenue")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
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
            return _normalize_date(row.get("next_earnings_date")) if row else None
        except Exception as e:
            logger.error("get_next_earnings_date failed: %s", e)
            return None

    # ---------------------------
    # ✅ Methods required by rule1_suitability.py (present + relied upon)
    # ---------------------------
    async def get_net_income_history(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Annual fiscal net income history.
        Used by Rule #1 suitability evaluator.
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
        return await self.get_eps_history(company_id)

    async def get_revenue_yearly_series(self, company_id: int) -> List[Dict[str, Any]]:
        return await self.get_revenue_history(company_id)

    async def get_balance_sheet_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("balance_sheets")
                .select(
                    "fiscal_year, fiscal_quarter, total_debt, shareholders_equity, "
                    "cash_and_cash_equivalents, updated_at, confidence_score"
                )
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
        try:
            resp = (
                supabase.table("income_statements")
                .select(
                    "fiscal_year, fiscal_quarter, ebit, ebitda, interest_expense, "
                    "net_income_to_common, net_income, updated_at, confidence_score"
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
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select(
                    "fiscal_year, fiscal_quarter, cash_from_operating_activities, "
                    "capital_expenditures, updated_at, confidence_score"
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
            return [{"fiscal_year": r["fiscal_year"], "roic": r.get("return_on_invested_capital_pct")} for r in rows]
        except Exception as e:
            logger.error("get_roic_history failed: %s", e)
            return []

    async def get_shares_history(self, company_id: int) -> List[Dict[str, Any]]:
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
            return [{"fiscal_year": r["fiscal_year"], "shares_outstanding_diluted": r.get("shares_outstanding_diluted")} for r in rows]
        except Exception as e:
            logger.error("get_shares_history failed: %s", e)
            return []

    # ---------------------------
    # DDM: price + dividend + beta + growth
    # ---------------------------
    async def get_current_market_price(self, company_id: int) -> Optional[float]:
        try:
            resp = (
                supabase.table("current_market_data")
                .select("current_price")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return float(row["current_price"]) if row and row.get("current_price") is not None else None
        except Exception as e:
            logger.error("get_current_market_price failed: %s", e)
            return None

    async def get_beta_latest(self, company_id: int) -> Optional[float]:
        try:
            resp = (
                supabase.table("company_summary")
                .select("beta, snapshot_date")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return float(row["beta"]) if row and row.get("beta") is not None else None
        except Exception as e:
            logger.error("get_beta_latest failed: %s", e)
            return None

    async def get_dividend_history(self, company_id: int, limit: int = 600) -> List[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("dividend_history")
                .select("ex_dividend_date, dividend_amount, currency, updated_at")
                .eq("company_id", company_id)
                .order("ex_dividend_date", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error("get_dividend_history failed: %s", e)
            return []

    async def get_dividend_ttm_dps(self, company_id: int) -> Optional[float]:
        rows = await self.get_dividend_history(company_id, limit=300)
        if not rows:
            return None
        cutoff = date.today() - timedelta(days=365)
        total = 0.0
        hit = False
        for r in rows:
            exd = _normalize_date(r.get("ex_dividend_date"))
            amt = r.get("dividend_amount")
            if exd is None or amt is None:
                continue
            if exd >= cutoff:
                try:
                    total += float(amt)
                    hit = True
                except Exception:
                    continue
        return float(total) if hit and total > 0 else None

    async def get_dividend_yearly_dps(self, company_id: int, years: int = 10) -> List[Dict[str, Any]]:
        rows = await self.get_dividend_history(company_id, limit=800)
        per_year: Dict[int, float] = {}
        for r in rows:
            exd = _normalize_date(r.get("ex_dividend_date"))
            amt = r.get("dividend_amount")
            if exd is None or amt is None:
                continue
            try:
                per_year[exd.year] = per_year.get(exd.year, 0.0) + float(amt)
            except Exception:
                continue

        if not per_year:
            return []

        ys = sorted(per_year.keys())
        last = ys[-years:]
        return [{"year": y, "dps": per_year.get(y)} for y in last]

    async def get_dividend_metrics_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("dividend_metrics")
                .select(
                    "annual_dps, dividend_payout_ratio, fcf_dividend_payout_ratio, "
                    "dividend_growth_rate_5yr, dividend_growth_rate_10yr, retention_ratio, created_at"
                )
                .eq("company_id", company_id)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_dividend_metrics_latest failed: %s", e)
            return None

    async def get_dividend_cagr(self, company_id: int, years: int = 10) -> Optional[float]:
        series = await self.get_dividend_yearly_dps(company_id, years=years)
        if len(series) < 6:
            return None
        series = sorted(series, key=lambda r: r.get("year", 0))
        y0 = series[0].get("year")
        yN = series[-1].get("year")
        v0 = series[0].get("dps")
        vN = series[-1].get("dps")
        if not isinstance(y0, int) or not isinstance(yN, int) or yN <= y0:
            return None
        try:
            v0f = float(v0)
            vNf = float(vN)
        except Exception:
            return None
        if v0f <= 0 or vNf <= 0:
            return None
        n = yN - y0
        try:
            g = (vNf / v0f) ** (1.0 / n) - 1.0
            return float(g) if math.isfinite(g) else None
        except Exception:
            return None

    async def get_sustainable_dividend_growth(self, company_id: int) -> Optional[float]:
        try:
            st = (
                supabase.table("statistics")
                .select("return_on_equity_pct, updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            st_row = _first(st.data)
            roe = st_row.get("return_on_equity_pct") if st_row else None
            dm = await self.get_dividend_metrics_latest(company_id)
            retention = dm.get("retention_ratio") if dm else None
            if roe is None or retention is None:
                return None
            roe_f = _pct_to_frac(float(roe))
            ret_f = _pct_to_frac(float(retention))
            g = roe_f * ret_f
            return float(g) if math.isfinite(g) else None
        except Exception as e:
            logger.error("get_sustainable_dividend_growth failed: %s", e)
            return None

    async def insert_ddm_valuation(self, payload: Dict[str, Any]) -> None:
        try:
            supabase.table("ddm_valuations").insert(payload).execute()
        except Exception as e:
            logger.error("insert_ddm_valuation failed: %s", e)

    # ---------------------------
    # RULE #1 HISTORY (existing fixed shape)
    # ---------------------------
    async def get_rule1_history(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        try:
            ctx = await self.get_company_context(symbol)
            if not ctx:
                return []

            company_id = ctx["company_id"]

            resp = (
                supabase.table("valuation_runs")
                .select("run_at, output_snapshot")
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

    async def get_ddm_history(self, symbol: str, method: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Returns recent DDM valuation runs (newest first).
        Shape (FE-ready):
        { runAt, method, intrinsicValue, dividendGrowthRate, requiredReturn, score, category }
        """
        try:
            ctx = await self.get_company_context(symbol)
            if not ctx:
                return []
            company_id = ctx["company_id"]

            resp = (
                supabase.table("valuation_runs")
                .select("run_at, output_snapshot")
                .eq("company_id", company_id)
                .eq("method", method)
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
                        "method": valuation.get("method"),
                        "intrinsicValue": valuation.get("intrinsicValue"),
                        "dividendGrowthRate": valuation.get("dividendGrowthRate"),
                        "requiredReturn": valuation.get("requiredReturn"),
                        "score": applicability.get("score"),
                        "category": applicability.get("category"),
                    }
                )
            return items
        except Exception as e:
            logger.error("get_ddm_history failed for %s: %s", symbol, e)
            return []