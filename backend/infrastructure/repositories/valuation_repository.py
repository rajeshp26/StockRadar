# infrastructure/repositories/valuation_repository.py
from __future__ import annotations
import logging
import math
from datetime import datetime, date, time, timedelta
from typing import Any, Dict, List, Optional
from database import supabase

logger = logging.getLogger(__name__)

ALLOWED_METHODS = {
    "rule1",
    "ddm_gordon",
    "ddm_two_stage",
    "dcf",
    "owner_earnings",
    "residual_income", 
    "relative",
}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _first(data: Any) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return None


def _normalize_date(d: Any) -> Optional[date]:
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
    return x / 100.0 if x > 1.0 else x


def _compute_fcf(ocf_f: Optional[float], capex_f: Optional[float]) -> Optional[float]:
    """
    Sign-aware FCF: capex is stored as a NEGATIVE outflow in cash_flow_statements.
    BUG-01 fix applied here too: the previous get_fcf_history() used ocf - capex
    which produced the wrong sign when capex is negative.
    """
    if ocf_f is None or capex_f is None:
        return None
    return (ocf_f + capex_f) if capex_f < 0 else (ocf_f - capex_f)


# ─── Repository ───────────────────────────────────────────────────────────────

class ValuationRepository:
    """Supabase repository used by valuation services/guards."""

    # ── Company context ────────────────────────────────────────────────────────

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

    # ── Freshness gate ─────────────────────────────────────────────────────────

    async def get_last_valuation_ts(self, company_id: int, method: str = "rule1") -> Optional[datetime]:
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
        if method not in ALLOWED_METHODS:
            method = "rule1"
        if method == "rule1":
            return await self._latest_dependency_rule1(company_id)
        if method in {"ddm_gordon", "ddm_two_stage"}:
            return await self._latest_dependency_ddm(company_id, method=method)
        if method == "dcf":
            return await self._latest_dependency_dcf(company_id)
        if method == "owner_earnings":
            return await self._latest_dependency_owner_earnings(company_id)
        if method == "residual_income":
            return await self._latest_dependency_residual_income(company_id)
        return None

    async def _latest_dependency_rule1(self, company_id: int) -> Optional[datetime]:
        """
        Phase 2: statistics table removed (dropped in 002_phase2a).
        Dependency set updated: statistics → financial_ratios (computed_at).
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
            fr = (
                supabase.table("financial_ratios")
                .select("computed_at")
                .eq("company_id", company_id)
                .order("computed_at", desc=True)
                .limit(1)
                .execute()
            )
            fr_dt = _normalize_datetime((_first(fr.data) or {}).get("computed_at"))
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
            return _max_dt(cs_dt, ef_dt, er_dt, is_dt, fr_dt, sp_dt, im_dt, md_dt, co_dt)
        except Exception as e:
            logger.error("get_latest_dependency_ts(rule1) failed company_id=%s: %s", company_id, e)
            return None

    async def _latest_dependency_ddm(self, company_id: int, method: str) -> Optional[datetime]:
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
            # Phase 2: statistics removed — financial_ratios (computed_at) replaces it.
            fr = (
                supabase.table("financial_ratios")
                .select("computed_at")
                .eq("company_id", company_id)
                .order("computed_at", desc=True)
                .limit(1)
                .execute()
            )
            fr_dt = _normalize_datetime((_first(fr.data) or {}).get("computed_at"))
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
            return _max_dt(cs_dt, dh_dt, dm_dt, fr_dt, md_dt, co_dt)
        except Exception as e:
            logger.error("get_latest_dependency_ts(%s) failed company_id=%s: %s", method, company_id, e)
            return None

    async def _latest_dependency_dcf(self, company_id: int) -> Optional[datetime]:
        try:
            cf = (
                supabase.table("cash_flow_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            cf_dt = _normalize_datetime((_first(cf.data) or {}).get("updated_at"))
            is_ = (
                supabase.table("income_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            is_dt = _normalize_datetime((_first(is_.data) or {}).get("updated_at"))
            bs = (
                supabase.table("balance_sheets")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            bs_dt = _normalize_datetime((_first(bs.data) or {}).get("updated_at"))
            # Phase 2: statistics removed — financial_ratios (computed_at) replaces it.
            fr = (
                supabase.table("financial_ratios")
                .select("computed_at")
                .eq("company_id", company_id)
                .order("computed_at", desc=True)
                .limit(1)
                .execute()
            )
            fr_dt = _normalize_datetime((_first(fr.data) or {}).get("computed_at"))
            rf = (
                supabase.table("revenue_forecast")
                .select("report_date")
                .eq("company_id", company_id)
                .order("report_date", desc=True)
                .limit(1)
                .execute()
            )
            rf_dt = _as_datetime_from_date((_first(rf.data) or {}).get("report_date"))
            md = (
                supabase.table("valuation_method_defaults")
                .select("updated_at")
                .eq("method", "dcf")
                .limit(1)
                .execute()
            )
            md_dt = _normalize_datetime((_first(md.data) or {}).get("updated_at"))
            co = (
                supabase.table("company_valuation_overrides")
                .select("updated_at")
                .eq("company_id", company_id)
                .eq("method", "dcf")
                .limit(1)
                .execute()
            )
            co_dt = _normalize_datetime((_first(co.data) or {}).get("updated_at"))
            return _max_dt(cf_dt, is_dt, bs_dt, fr_dt, rf_dt, md_dt, co_dt)
        except Exception as e:
            logger.error("get_latest_dependency_ts(dcf) failed company_id=%s: %s", company_id, e)
            return None

    # ── Owner Earnings dependency timestamp ───────────────────────────────────

    async def _latest_dependency_owner_earnings(self, company_id: int) -> Optional[datetime]:
        """
        Dependency set for Owner Earnings:
        - income_statements  (net_income, shares)
        - cash_flow_statements  (D&A, capex, WC change)
        - balance_sheets  (net debt equity bridge)
        - financial_ratios  (ROIC for suitability)
        - valuation_method_defaults  (method = owner_earnings)
        - company_valuation_overrides  (method = owner_earnings)
        """
        try:
            is_ = (
                supabase.table("income_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            is_dt = _normalize_datetime((_first(is_.data) or {}).get("updated_at"))

            cf = (
                supabase.table("cash_flow_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            cf_dt = _normalize_datetime((_first(cf.data) or {}).get("updated_at"))

            bs = (
                supabase.table("balance_sheets")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            bs_dt = _normalize_datetime((_first(bs.data) or {}).get("updated_at"))

            fr = (
                supabase.table("financial_ratios")
                .select("computed_at")
                .eq("company_id", company_id)
                .order("computed_at", desc=True)
                .limit(1)
                .execute()
            )
            fr_dt = _normalize_datetime((_first(fr.data) or {}).get("computed_at"))

            md = (
                supabase.table("valuation_method_defaults")
                .select("updated_at")
                .eq("method", "owner_earnings")
                .limit(1)
                .execute()
            )
            md_dt = _normalize_datetime((_first(md.data) or {}).get("updated_at"))

            co = (
                supabase.table("company_valuation_overrides")
                .select("updated_at")
                .eq("company_id", company_id)
                .eq("method", "owner_earnings")
                .limit(1)
                .execute()
            )
            co_dt = _normalize_datetime((_first(co.data) or {}).get("updated_at"))

            return _max_dt(is_dt, cf_dt, bs_dt, fr_dt, md_dt, co_dt)
        except Exception as e:
            logger.error("_latest_dependency_owner_earnings failed company_id=%s: %s", company_id, e)
            return None

    # ── Residual Income dependency timestamp ──────────────────────────────────

    async def _latest_dependency_residual_income(self, company_id: int) -> Optional[datetime]:
        """
        Dependency set for Residual Income:
        - income_statements  (EPS, net_income)
        - balance_sheets  (shareholders_equity, total_assets, intangibles)
        - company_summary  (beta)
        - financial_ratios  (ROE for suitability)
        - valuation_method_defaults  (method = residual_income)
        - company_valuation_overrides  (method = residual_income)
        """
        try:
            is_ = (
                supabase.table("income_statements")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            is_dt = _normalize_datetime((_first(is_.data) or {}).get("updated_at"))

            bs = (
                supabase.table("balance_sheets")
                .select("updated_at")
                .eq("company_id", company_id)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
            bs_dt = _normalize_datetime((_first(bs.data) or {}).get("updated_at"))

            cs = (
                supabase.table("company_summary")
                .select("snapshot_date")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_dt = _as_datetime_from_date((_first(cs.data) or {}).get("snapshot_date"))

            fr = (
                supabase.table("financial_ratios")
                .select("computed_at")
                .eq("company_id", company_id)
                .order("computed_at", desc=True)
                .limit(1)
                .execute()
            )
            fr_dt = _normalize_datetime((_first(fr.data) or {}).get("computed_at"))

            md = (
                supabase.table("valuation_method_defaults")
                .select("updated_at")
                .eq("method", "residual_income")
                .limit(1)
                .execute()
            )
            md_dt = _normalize_datetime((_first(md.data) or {}).get("updated_at"))

            co = (
                supabase.table("company_valuation_overrides")
                .select("updated_at")
                .eq("company_id", company_id)
                .eq("method", "residual_income")
                .limit(1)
                .execute()
            )
            co_dt = _normalize_datetime((_first(co.data) or {}).get("updated_at"))

            return _max_dt(is_dt, bs_dt, cs_dt, fr_dt, md_dt, co_dt)
        except Exception as e:
            logger.error("_latest_dependency_residual_income failed company_id=%s: %s", company_id, e)
            return None

    # ── Analytics stream inserts ──────────────────────────────────────────────

    # ── Owner Earnings repo helpers ───────────────────────────────────────────

    async def get_cash_flow_oe_inputs(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Latest annual cash flow row including D&A and WC change — required for OE computation.
        Intentionally a separate method from get_cash_flow_latest to avoid widening
        the existing method's SELECT (no breaking changes to callers).
        """
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select(
                    "fiscal_year, fiscal_quarter, "
                    "cash_from_operating_activities, capital_expenditures, "
                    "depreciation_amortization, change_in_working_capital, "
                    "updated_at"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("cash_from_operating_activities", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_cash_flow_oe_inputs failed: %s", e)
            return None

    async def get_annual_owner_earnings(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Compute annual Owner Earnings history: NI + D&A − |Capex| per year.
        Joins income_statements (net_income) with cash_flow_statements (D&A, capex).
        Used by owner_earnings_suitability for multi-year metrics.

        Note: Uses total capex as maintenance capex proxy (conservative; no ratio applied).
        """
        try:
            cf_resp = (
                supabase.table("cash_flow_statements")
                .select(
                    "fiscal_year, fiscal_quarter, "
                    "capital_expenditures, depreciation_amortization"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            is_resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, net_income, net_income_to_common")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("net_income", "null")
                .order("fiscal_year", desc=False)
                .execute()
            )

            cf_by_year: Dict[int, Dict[str, Any]] = {}
            for r in (cf_resp.data or []):
                y = r.get("fiscal_year")
                if isinstance(y, int):
                    cf_by_year[y] = r

            out: List[Dict[str, Any]] = []
            for r in (is_resp.data or []):
                y = r.get("fiscal_year")
                if not isinstance(y, int):
                    continue
                ni_raw = r.get("net_income_to_common") or r.get("net_income")
                ni = float(ni_raw) if ni_raw is not None else None

                cf = cf_by_year.get(y, {})
                da_raw = cf.get("depreciation_amortization")
                capex_raw = cf.get("capital_expenditures")
                da = float(da_raw) if da_raw is not None else None
                capex = float(capex_raw) if capex_raw is not None else None

                # Sign-aware: same logic as _compute_fcf
                oe: Optional[float] = None
                if ni is not None:
                    da_val = da if da is not None else 0.0
                    capex_adj = 0.0
                    if capex is not None:
                        capex_adj = capex if capex < 0 else -capex
                    oe = ni + da_val + capex_adj

                out.append({
                    "fiscal_year": y,
                    "oe": oe,
                    "net_income": ni,
                    "da": da,
                    "capex": capex,
                })

            out = sorted(out, key=lambda x: x.get("fiscal_year", 0))
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_owner_earnings_history failed: %s", e)
            return []

    async def get_capex_da_history(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Annual Capex + D&A history for OE suitability Capex/D&A ratio metric.
        Returns [{fiscal_year, capex, da}] sorted ascending.
        """
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select(
                    "fiscal_year, fiscal_quarter, "
                    "capital_expenditures, depreciation_amortization"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            out = [
                {
                    "fiscal_year": r["fiscal_year"],
                    "capex": r.get("capital_expenditures"),
                    "da": r.get("depreciation_amortization"),
                }
                for r in rows if r.get("fiscal_year") is not None
            ]
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_capex_da_history failed: %s", e)
            return []

    # ── Residual Income repo helpers ──────────────────────────────────────────

    async def get_balance_sheet_ri_inputs(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Latest annual balance sheet with intangibles and total_assets for RI suitability.
        Separate from get_balance_sheet_latest to avoid widening that method's SELECT.
        """
        try:
            resp = (
                supabase.table("balance_sheets")
                .select(
                    "fiscal_year, total_assets, shareholders_equity, "
                    "intangible_assets, goodwill, "
                    "total_debt, cash_and_cash_equivalents"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("total_assets", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_balance_sheet_ri_inputs failed: %s", e)
            return None

    async def get_book_value_history(
        self, company_id: int, years: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Annual shareholders' equity (book value) history.
        Used by RI suitability for book value CAGR metric.
        Returns [{fiscal_year, book_value}] ascending.
        """
        try:
            resp = (
                supabase.table("balance_sheets")
                .select("fiscal_year, fiscal_quarter, shareholders_equity")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("shareholders_equity", "null")
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            out = [
                {
                    "fiscal_year": r["fiscal_year"],
                    "book_value": r.get("shareholders_equity"),
                }
                for r in rows if r.get("fiscal_year") is not None
            ]
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_book_value_history failed: %s", e)
            return []

    async def get_roe_history(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Annual ROE history from financial_ratios.
        Used by RI suitability.
        Returns [{fiscal_year, roe}] ascending.
        """
        try:
            resp = (
                supabase.table("financial_ratios")
                .select("fiscal_year, roe")
                .eq("company_id", company_id)
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            out = [
                {"fiscal_year": r["fiscal_year"], "roe": r.get("roe")}
                for r in rows if r.get("fiscal_year") is not None
            ]
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_roe_history failed: %s", e)
            return []

    # ── Run history (used by API history endpoints) ───────────────────────────

    async def get_owner_earnings_history(
        self, symbol: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        try:
            ctx = await self.get_company_context(symbol)
            if not ctx:
                return []
            company_id = ctx["company_id"]
            resp = (
                supabase.table("valuation_runs")
                .select("run_at, output_snapshot")
                .eq("company_id", company_id)
                .eq("method", "owner_earnings")
                .order("run_at", desc=True)
                .limit(limit)
                .execute()
            )
            items = []
            for r in (resp.data or []):
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                val = snap.get("valuation") or {}
                app = snap.get("applicability") or {}
                items.append({
                    "runAt": run_at.isoformat() if run_at else None,
                    "intrinsicValuePerShare": val.get("intrinsicValuePerShare"),
                    "baseOe": val.get("baseOe"),
                    "discountRateUsed": val.get("discountRateUsed"),
                    "oeGrowthRateUsed": val.get("oeGrowthRateUsed"),
                    "terminalGrowthRateUsed": val.get("terminalGrowthRateUsed"),
                    "enterpriseValue": val.get("enterpriseValue"),
                    "score": app.get("score"),
                    "category": app.get("category"),
                })
            return items
        except Exception as e:
            logger.error("get_owner_earnings_history failed for %s: %s", symbol, e)
            return []

    async def get_residual_income_history(
        self, symbol: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        try:
            ctx = await self.get_company_context(symbol)
            if not ctx:
                return []
            company_id = ctx["company_id"]
            resp = (
                supabase.table("valuation_runs")
                .select("run_at, output_snapshot")
                .eq("company_id", company_id)
                .eq("method", "residual_income")
                .order("run_at", desc=True)
                .limit(limit)
                .execute()
            )
            items = []
            for r in (resp.data or []):
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                val = snap.get("valuation") or {}
                app = snap.get("applicability") or {}
                items.append({
                    "runAt": run_at.isoformat() if run_at else None,
                    "intrinsicValuePerShare": val.get("intrinsicValuePerShare"),
                    "bvPerShare": val.get("bvPerShare"),
                    "costOfEquityUsed": val.get("costOfEquityUsed"),
                    "ri0PerShare": val.get("ri0PerShare"),
                    "riGrowthRateUsed": val.get("riGrowthRateUsed"),
                    "score": app.get("score"),
                    "category": app.get("category"),
                })
            return items
        except Exception as e:
            logger.error("get_residual_income_history failed for %s: %s", symbol, e)
            return []


    # ── Parameters ─────────────────────────────────────────────────────────────

    async def get_method_params(self, company_id: int, method: str = "rule1") -> Dict[str, Any]:
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

    async def get_method_params_rule1(self, company_id: int) -> Dict[str, Any]:
        return await self.get_method_params(company_id, method="rule1")

    # ── Cached-path hydration ──────────────────────────────────────────────────

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

    async def get_last_method_diagnostics(self, company_id: int, method: str = "rule1") -> Dict[str, Any]:
        snap = await self.get_last_output_snapshot(company_id, method=method)
        if not snap:
            return {}
        app = snap.get("applicability") or {}
        dq = snap.get("dataQuality") or {}
        assumptions = (dq.get("inputDecisions") or {}).get("assumptions", {}) if isinstance(dq, dict) else {}
        return {"applicability": app, "dataQuality": dq, "assumptions": assumptions}

    async def get_company_summary_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Latest company_summary row.
        Used as shares_outstanding fallback in DCF when
        income_statements.shares_outstanding_diluted is not populated.
        """
        try:
            resp = (
                supabase.table("company_summary")
                .select("snapshot_date, shares_outstanding, implied_shares_outstanding, trailing_eps")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_company_summary_latest failed: %s", e)
            return None

    # ── Persistence ────────────────────────────────────────────────────────────

    async def insert_valuation_run(self, company_id: int, run: Dict[str, Any], method: str = "rule1") -> None:
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

    async def insert_dcf_valuation(self, payload: Dict[str, Any]) -> None:
        try:
            supabase.table("dcf_valuations").insert(payload).execute()
        except Exception as e:
            logger.error("insert_dcf_valuation failed: %s", e)

    async def insert_ddm_valuation(self, payload: Dict[str, Any]) -> None:
        try:
            supabase.table("ddm_valuations").insert(payload).execute()
        except Exception as e:
            logger.error("insert_ddm_valuation failed: %s", e)

    # ── Cached value read ──────────────────────────────────────────────────────

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

    # ── EPS, growth, histories (Rule #1) ──────────────────────────────────────

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
            is_ = (
                supabase.table("income_statements")
                .select("eps_diluted, net_income_to_common, shares_outstanding_diluted, fiscal_year, fiscal_quarter")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("net_income_to_common", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(is_.data)
            if not row:
                return None
            eps = row.get("eps_diluted")
            if eps is not None:
                return float(eps)
            ni = row.get("net_income_to_common")
            sh = row.get("shares_outstanding_diluted")
            if ni is not None and sh is not None and float(sh) > 0:
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
        rows = await self._get_eps_components_from_income_statements(company_id)
        eps_rows = []
        for r in rows:
            ni = r.get("net_income")
            shares = r.get("shares_outstanding_diluted")
            if ni is None or shares in (None, 0):
                eps = None
            else:
                try:
                    eps = float(ni) / float(shares)
                except Exception:
                    eps = None
            eps_rows.append({"fiscal_year": r.get("fiscal_year"), "eps": eps})
        return eps_rows

    async def _get_eps_components_from_income_statements(self, company_id: int) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("income_statements")
            .select("fiscal_year, net_income, shares_outstanding_diluted")
            .eq("company_id", company_id)
            .is_("fiscal_quarter", None)
            .not_.is_("net_income", "null")
            .order("fiscal_year", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_revenue_history(self, company_id: int) -> List[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, revenue")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("revenue", "null")
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

    # ── Rule #1 suitability helpers ────────────────────────────────────────────

    async def get_net_income_history(self, company_id: int) -> List[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, net_income")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("net_income", "null")
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

    # ── Statement reads ────────────────────────────────────────────────────────

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
                .not_.is_("total_assets", "null")
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
        Most recent annual income statement row.
        Used by ddm_suitability for raw IS values: ebit, ebitda, interest_expense.
        These are source-of-truth P&L figures — they live only in income_statements
        and are never duplicated into derived_financial_metrics.
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select(
                    "fiscal_year, period_end_date, revenue, gross_profit, "
                    "operating_income, net_income, net_income_to_common, "
                    "ebit, ebitda, interest_expense, pretax_income, tax_expense, "
                    "eps_diluted, shares_outstanding_diluted"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("revenue", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_income_statement_latest failed: %s", e)
            return None

    async def get_income_statements_annual(self, company_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """
        N most recent annual income statement rows (newest first).
        Used for multi-year trend analysis.
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select(
                    "fiscal_year, period_end_date, revenue, ebit, ebitda, "
                    "interest_expense, net_income, net_income_to_common, "
                    "shares_outstanding_diluted"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("revenue", "null")
                .order("fiscal_year", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error("get_income_statements_annual failed: %s", e)
            return []

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
                .not_.is_("cash_from_operating_activities", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_cash_flow_latest failed: %s", e)
            return None

    # ── Derived metrics ────────────────────────────────────────────────────────

    async def get_derived_metrics_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Most recent annual financial ratios row.

        Phase 2: reads from financial_ratios (consolidated table).
        All ratios stored as fractions (0.15 = 15%).

        Used by:
          - ddm_suitability: dividend_payout_ratio, fcf_dividend_payout_ratio
          - dcf_suitability: roic, roe, roa, debt_to_equity, interest_coverage
          - rule1_suitability: roic, roe, debt_to_equity
        """
        try:
            resp = (
                supabase.table("financial_ratios")
                .select(
                    "fiscal_year, "
                    "roic, roe, roa, "
                    "gross_margin, operating_margin, ebitda_margin, net_margin, fcf_margin, "
                    "free_cash_flow, fcf_conversion, "
                    "dividend_payout_ratio, fcf_dividend_payout_ratio, dividend_coverage_fcf, "
                    "debt_to_equity, debt_to_assets, "
                    "long_term_debt_to_equity, long_term_debt_to_assets, "
                    "interest_coverage, "
                    "current_ratio, quick_ratio, "
                    "asset_turnover, inventory_turnover, "
                    "revenue_per_share, ocf_per_share, fcf_per_share, "
                    "ebit_per_share, ebitda_per_share, "
                    "book_value_per_share, tangible_book_value_per_share, "
                    "cash_per_share, total_debt_per_share, "
                    "working_capital_per_share, capex_per_share, "
                    "computed_at"
                )
                .eq("company_id", company_id)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_derived_metrics_latest failed: %s", e)
            return None

    async def get_roic_history(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Annual ROIC history.
        Phase 2: reads from financial_ratios only. statistics table has been dropped.
        """
        try:
            resp = (
                supabase.table("financial_ratios")
                .select("fiscal_year, roic")
                .eq("company_id", company_id)
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            return [{"fiscal_year": r["fiscal_year"], "roic": r.get("roic")} for r in rows]
        except Exception as e:
            logger.error("get_roic_history failed: %s", e)
            return []


    async def get_shares_history(self, company_id: int) -> List[Dict[str, Any]]:
        """
        Diluted shares history from income_statements.

        Phase 2: statistics table dropped. income_statements is now the sole
        canonical source for shares_outstanding_diluted (written by defeat_beta_provider
        via the 'Diluted Average Shares' row alias).
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year, shares_outstanding_diluted, shares_outstanding_basic")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .not_.is_("shares_outstanding_diluted", "null")
                .order("fiscal_year", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error("get_shares_history failed for company_id=%s: %s", company_id, e)
            return []

    # ── DCF suitability helpers ────────────────────────────────────────────────

    async def get_fcf_history(self, company_id: int, years: int = 5) -> List[Dict[str, Any]]:
        """
        Annual FCF history used by DCF suitability.

        FIX (BUG-01 variant): Previous implementation used ocf_f - capex_f
        which produces the wrong sign when capex is stored as a negative outflow
        (e.g. BN 2024: capex = -11,172M → 7,569 - (-11,172) = +18,741M WRONG).
        Now delegates to _compute_fcf() which handles both sign conventions.
        """
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select("fiscal_year, fiscal_quarter, cash_from_operating_activities, capital_expenditures")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            out: List[Dict[str, Any]] = []
            for r in rows:
                y = r.get("fiscal_year")
                if y is None:
                    continue
                ocf_raw = r.get("cash_from_operating_activities")
                capex_raw = r.get("capital_expenditures")
                try:
                    ocf_f = float(ocf_raw) if ocf_raw is not None else None
                except Exception:
                    ocf_f = None
                try:
                    capex_f = float(capex_raw) if capex_raw is not None else None
                except Exception:
                    capex_f = None
                fcf = _compute_fcf(ocf_f, capex_f)
                out.append({"fiscal_year": int(y), "fcf": fcf, "ocf": ocf_f, "capex": capex_f})
            out = sorted(out, key=lambda x: x.get("fiscal_year", 0))
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_fcf_history failed: %s", e)
            return []

    async def get_capex_and_revenue_history(self, company_id: int, years: int = 5) -> List[Dict[str, Any]]:
        try:
            cf = (
                supabase.table("cash_flow_statements")
                .select("fiscal_year, fiscal_quarter, capital_expenditures")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            is_ = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, revenue")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            capex_by_year: Dict[int, Optional[float]] = {}
            for r in (cf.data or []):
                y = r.get("fiscal_year")
                if y is None:
                    continue
                v = r.get("capital_expenditures")
                try:
                    capex_by_year[int(y)] = float(v) if v is not None else None
                except Exception:
                    capex_by_year[int(y)] = None
            rev_by_year: Dict[int, Optional[float]] = {}
            for r in (is_.data or []):
                y = r.get("fiscal_year")
                if y is None:
                    continue
                v = r.get("revenue")
                try:
                    rev_by_year[int(y)] = float(v) if v is not None else None
                except Exception:
                    rev_by_year[int(y)] = None
            years_all = sorted(set(capex_by_year.keys()) | set(rev_by_year.keys()))
            merged = [{"fiscal_year": y, "capex": capex_by_year.get(y), "revenue": rev_by_year.get(y)} for y in years_all]
            return merged[-years:] if years and len(merged) > years else merged
        except Exception as e:
            logger.error("get_capex_and_revenue_history failed: %s", e)
            return []

    # ── DDM: price, dividends, beta, growth ───────────────────────────────────

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
        """
        Dividend-specific metrics: growth rates, years paid, retention ratio, annual DPS.

        Phase 2: dividend_payout_ratio, fcf_dividend_payout_ratio, dividend_coverage_fcf
        removed from SELECT — these columns are dropped from dividend_metrics in Phase 2b
        (003_phase2b_cleanup.sql). They are now the sole responsibility of financial_ratios
        and accessed via get_derived_metrics_latest().
        """
        try:
            resp = (
                supabase.table("dividend_metrics")
                .select(
                    "annual_dps, dividend_yield, "
                    "dividend_growth_rate_3yr, dividend_growth_rate_5yr, dividend_growth_rate_10yr, "
                    "consecutive_years_paid, fcfe_coverage_ratio, "
                    "cash_dividend_payout_ratio, ebitda_dividend_coverage, "
                    "retention_ratio, created_at"
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
        """
        Sustainable growth rate = ROE × retention_ratio.

        Phase 2: ROE read from financial_ratios.roe (stored as fraction, e.g. 0.15).
        statistics table has been dropped.
        retention_ratio still read from dividend_metrics (dividend-specific table).
        """
        try:
            fr = (
                supabase.table("financial_ratios")
                .select("roe, computed_at")
                .eq("company_id", company_id)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            fr_row = _first(fr.data)
            roe = fr_row.get("roe") if fr_row else None
            dm = await self.get_dividend_metrics_latest(company_id)
            retention = dm.get("retention_ratio") if dm else None
            if roe is None or retention is None:
                return None
            # financial_ratios.roe is already a fraction — no _pct_to_frac() needed.
            # retention_ratio from dividend_metrics may be stored as pct — apply conversion.
            roe_f = float(roe)
            ret_f = _pct_to_frac(float(retention))
            g = roe_f * ret_f
            return float(g) if math.isfinite(g) else None
        except Exception as e:
            logger.error("get_sustainable_dividend_growth failed: %s", e)
            return None

    # ── Valuation history ──────────────────────────────────────────────────────

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
            items = []
            for r in rows:
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}
                items.append({
                    "runAt": run_at.isoformat() if run_at else None,
                    "stickerPrice": valuation.get("stickerPrice"),
                    "mosPrice": valuation.get("mosPrice"),
                    "futurePrice": valuation.get("futurePrice"),
                    "growth": valuation.get("growth"),
                    "futurePE": valuation.get("futurePE"),
                    "score": applicability.get("score"),
                    "category": applicability.get("category"),
                })
            return items
        except Exception as e:
            logger.error("get_rule1_history failed for %s: %s", symbol, e)
            return []

    async def get_ddm_history(self, symbol: str, method: str, limit: int = 50) -> List[Dict[str, Any]]:
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
            items = []
            for r in rows:
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}
                items.append({
                    "runAt": run_at.isoformat() if run_at else None,
                    "method": valuation.get("method"),
                    "intrinsicValue": valuation.get("intrinsicValue"),
                    "dividendGrowthRate": valuation.get("dividendGrowthRate"),
                    "requiredReturn": valuation.get("requiredReturn"),
                    "score": applicability.get("score"),
                    "category": applicability.get("category"),
                })
            return items
        except Exception as e:
            logger.error("get_ddm_history failed for %s: %s", symbol, e)
            return []

    async def get_dcf_history(self, symbol: str, method: str = "dcf", limit: int = 50) -> List[Dict[str, Any]]:
        if method not in ALLOWED_METHODS:
            method = "dcf"
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
            items = []
            for r in rows:
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}
                items.append({
                    "runAt": run_at.isoformat() if run_at else None,
                    "terminalMethod": valuation.get("terminalMethod"),
                    "intrinsicValuePerShare": valuation.get("intrinsicValuePerShare"),
                    "waccUsed": valuation.get("waccUsed"),
                    "terminalValue": valuation.get("terminalValue"),
                    "enterpriseValue": valuation.get("enterpriseValue"),
                    "score": applicability.get("score"),
                    "category": applicability.get("category"),
                })
            return items
        except Exception as e:
            logger.error("get_dcf_history failed for %s: %s", symbol, e)
            return []

    # ── Earnings events (event data only, not for fundamentals) ───────────────

    async def get_earnings_events(self, company_id: int) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("earnings")
            .select("*")
            .eq("company_id", company_id)
            .order("report_date", desc=False)
            .execute()
        )
        return resp.data or []