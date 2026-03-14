# infrastructure/repositories/valuation_repository.py
from __future__ import annotations
import hashlib
import json
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
        # Strip tzinfo so all timestamps are naive UTC.
        # Supabase stores everything in UTC; discarding the timezone label
        # makes offset-aware and offset-naive values comparable in _max_dt().
        return ts.replace(tzinfo=None)
    if isinstance(ts, str):
        try:
            s = ts.replace("Z", "+00:00")
            return datetime.fromisoformat(s).replace(tzinfo=None)
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
    BUG-01 fix: previous get_fcf_history() used ocf - capex which produced the
    wrong sign when capex is negative.
    """
    if ocf_f is None or capex_f is None:
        return None
    return (ocf_f + capex_f) if capex_f < 0 else (ocf_f - capex_f)


def _hash_params(params_rows: list) -> str:
    """
    Stable content-hash of valuation_method_defaults params values.
    Hashes the actual JSONB params content, not updated_at, so that an
    administrative timestamp touch without a value change does not alter
    the fingerprint and does not trigger downstream recomputes.
    """
    normalized = sorted(
        [
            {"method": r.get("method"), "params": r.get("params")}
            for r in params_rows
        ],
        key=lambda x: x.get("method") or "",
    )
    raw = json.dumps(normalized, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _safe_float_repo(x: Any) -> Optional[float]:
    """Local safe float for repo helpers — avoids importing from service layer."""
    try:
        if x is None:
            return None
        f = float(x)
        return f if f == f else None
    except Exception:
        return None


def _round2(x: Any) -> Optional[float]:
    v = _safe_float_repo(x)
    return round(v, 2) if v is not None else None


def _round6(x: Any) -> Optional[float]:
    v = _safe_float_repo(x)
    return round(v, 6) if v is not None else None


def _round8(x: Any) -> Optional[float]:
    v = _safe_float_repo(x)
    return round(v, 8) if v is not None else None


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

    async def _latest_dependency_owner_earnings(self, company_id: int) -> Optional[datetime]:
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

    async def _latest_dependency_residual_income(self, company_id: int) -> Optional[datetime]:
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

    # ── Owner Earnings repo helpers ───────────────────────────────────────────

    async def get_cash_flow_oe_inputs(self, company_id: int) -> Optional[Dict[str, Any]]:
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

    async def get_annual_owner_earnings(self, company_id: int, years: int = 5) -> List[Dict[str, Any]]:
        try:
            cf_resp = (
                supabase.table("cash_flow_statements")
                .select("fiscal_year, fiscal_quarter, capital_expenditures, depreciation_amortization")
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
                oe: Optional[float] = None
                if ni is not None:
                    da_val = da if da is not None else 0.0
                    capex_adj = 0.0
                    if capex is not None:
                        capex_adj = capex if capex < 0 else -capex
                    oe = ni + da_val + capex_adj
                out.append({"fiscal_year": y, "oe": oe, "net_income": ni, "da": da, "capex": capex})
            out = sorted(out, key=lambda x: x.get("fiscal_year", 0))
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_owner_earnings_history failed: %s", e)
            return []

    async def get_capex_da_history(self, company_id: int, years: int = 5) -> List[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select("fiscal_year, fiscal_quarter, capital_expenditures, depreciation_amortization")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=False)
                .execute()
            )
            rows = resp.data or []
            out = [
                {"fiscal_year": r["fiscal_year"], "capex": r.get("capital_expenditures"), "da": r.get("depreciation_amortization")}
                for r in rows if r.get("fiscal_year") is not None
            ]
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_capex_da_history failed: %s", e)
            return []

    # ── Residual Income repo helpers ──────────────────────────────────────────

    async def get_balance_sheet_ri_inputs(self, company_id: int) -> Optional[Dict[str, Any]]:
        try:
            resp = (
                supabase.table("balance_sheets")
                .select(
                    "fiscal_year, total_assets, shareholders_equity, "
                    "intangible_assets, goodwill, total_debt, cash_and_cash_equivalents"
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

    async def get_book_value_history(self, company_id: int, years: int = 6) -> List[Dict[str, Any]]:
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
                {"fiscal_year": r["fiscal_year"], "book_value": r.get("shareholders_equity")}
                for r in rows if r.get("fiscal_year") is not None
            ]
            return out[-years:] if years and len(out) > years else out
        except Exception as e:
            logger.error("get_book_value_history failed: %s", e)
            return []

    async def get_roe_history(self, company_id: int, years: int = 5) -> List[Dict[str, Any]]:
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

    async def get_owner_earnings_history(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
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

    async def get_residual_income_history(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
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

    async def get_last_input_snapshot(self, company_id: int, method: str) -> Optional[Dict[str, Any]]:
        """
        Returns the input_snapshot from the most recent valuation run.
        Contains: dependency_fingerprint, resolved inputs, overrides.
        Used by Gate 2 (fingerprint comparison) and Gate 3 (resolved comparison).
        """
        if method not in ALLOWED_METHODS:
            method = "rule1"
        try:
            resp = (
                supabase.table("valuation_runs")
                .select("input_snapshot")
                .eq("company_id", company_id)
                .eq("method", method)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            return (row.get("input_snapshot") if row else None) or None
        except Exception as exc:
            logger.error("get_last_input_snapshot failed (%s): %s", method, exc)
            return None

    async def update_valuation_fingerprint(self, company_id: int, method: str, new_fingerprint: str) -> None:
        """
        Gate 3 skip action: advance the stored dependency_fingerprint in the most
        recent valuation run's input_snapshot without writing a new run record.
        """
        if method not in ALLOWED_METHODS:
            return
        try:
            resp = (
                supabase.table("valuation_runs")
                .select("run_at, input_snapshot")
                .eq("company_id", company_id)
                .eq("method", method)
                .order("run_at", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            if not row:
                return
            run_at = row.get("run_at")
            if not run_at:
                return
            existing_snap = row.get("input_snapshot") or {}
            existing_snap["dependency_fingerprint"] = new_fingerprint
            supabase.table("valuation_runs").update(
                {"input_snapshot": existing_snap}
            ).eq("company_id", company_id).eq("method", method).eq("run_at", run_at).execute()
        except Exception as exc:
            logger.error("update_valuation_fingerprint failed (%s, %s): %s", company_id, method, exc)

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

    # ── Fingerprint dependency values ─────────────────────────────────────────

    async def get_ddm_dependency_values(self, company_id: int) -> Dict[str, Any]:
        ttm_rows = await self.get_dividend_history(company_id, limit=300)
        cutoff   = date.today() - timedelta(days=365)
        ttm_dividends = sorted(
            [
                {"date": str(r["ex_dividend_date"]), "amount": round(float(r["dividend_amount"]), 6)}
                for r in ttm_rows
                if (
                    _normalize_date(r.get("ex_dividend_date")) is not None
                    and _normalize_date(r["ex_dividend_date"]) >= cutoff
                    and r.get("dividend_amount") is not None
                )
            ],
            key=lambda x: x["date"],
        )
        yearly_dps = await self.get_dividend_yearly_dps(company_id, years=10)
        yearly_dps_rounded = [
            {"year": r["year"], "dps": round(float(r["dps"]), 6)}
            for r in yearly_dps if r.get("dps") is not None
        ]
        roe: Optional[float] = None
        try:
            fr_resp = (
                supabase.table("financial_ratios")
                .select("roe")
                .eq("company_id", company_id)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            fr_row = _first(fr_resp.data)
            if fr_row and fr_row.get("roe") is not None:
                roe = round(float(fr_row["roe"]), 8)
        except Exception as exc:
            logger.warning("get_ddm_dependency_values: ROE fetch failed: %s", exc)
        retention: Optional[float] = None
        dm = await self.get_dividend_metrics_latest(company_id)
        if dm and dm.get("retention_ratio") is not None:
            retention = round(float(dm["retention_ratio"]), 8)
        beta: Optional[float] = None
        try:
            cs_resp = (
                supabase.table("company_summary")
                .select("beta")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_row = _first(cs_resp.data)
            if cs_row and cs_row.get("beta") is not None:
                beta = round(float(cs_row["beta"]), 6)
        except Exception as exc:
            logger.warning("get_ddm_dependency_values: beta fetch failed: %s", exc)
        params_hash: Optional[str] = None
        try:
            md_resp = (
                supabase.table("valuation_method_defaults")
                .select("method, params")
                .in_("method", ["ddm_gordon", "ddm_two_stage"])
                .execute()
            )
            params_hash = _hash_params(md_resp.data or [])
        except Exception as exc:
            logger.warning("get_ddm_dependency_values: params fetch failed: %s", exc)
        return {
            "ttm_dividends":   ttm_dividends,
            "yearly_dps_10yr": yearly_dps_rounded,
            "roe_latest":      roe,
            "retention_ratio": retention,
            "beta_latest":     beta,
            "params_version":  params_hash,
        }

    async def get_rule1_dependency_values(self, company_id: int) -> Dict[str, Any]:
        ratios_series: list = []
        try:
            r = (
                supabase.table("financial_ratios")
                .select("fiscal_year, roic, roe, debt_to_equity, interest_coverage, fcf_conversion, free_cash_flow")
                .eq("company_id", company_id)
                .order("fiscal_year", desc=True)
                .limit(6)
                .execute()
            )
            for row in sorted(r.data or [], key=lambda x: x.get("fiscal_year") or 0):
                ratios_series.append({
                    "fiscal_year":       row.get("fiscal_year"),
                    "roic":              _round8(row.get("roic")),
                    "roe":               _round8(row.get("roe")),
                    "debt_to_equity":    _round6(row.get("debt_to_equity")),
                    "interest_coverage": _round6(row.get("interest_coverage")),
                    "fcf_conversion":    _round6(row.get("fcf_conversion")),
                    "free_cash_flow":    _round2(row.get("free_cash_flow")),
                })
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: ratios series failed: %s", exc)
        is_series: list = []
        try:
            r = (
                supabase.table("income_statements")
                .select("fiscal_year, revenue, net_income, net_income_to_common, shares_outstanding_diluted")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=True)
                .limit(7)
                .execute()
            )
            for row in sorted(r.data or [], key=lambda x: x.get("fiscal_year") or 0):
                is_series.append({
                    "fiscal_year":                row.get("fiscal_year"),
                    "revenue":                    _round2(row.get("revenue")),
                    "net_income":                 _round2(row.get("net_income")),
                    "net_income_to_common":       _round2(row.get("net_income_to_common")),
                    "shares_outstanding_diluted": _round2(row.get("shares_outstanding_diluted")),
                })
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: IS series failed: %s", exc)
        bs_snap: dict = {}
        try:
            bs = await self.get_balance_sheet_latest(company_id)
            if bs:
                bs_snap = {
                    "total_debt":                _round2(bs.get("total_debt")),
                    "shareholders_equity":       _round2(bs.get("shareholders_equity")),
                    "cash_and_cash_equivalents": _round2(bs.get("cash_and_cash_equivalents")),
                }
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: BS latest failed: %s", exc)
        is_snap: dict = {}
        try:
            is_row = await self.get_income_statement_latest(company_id)
            if is_row:
                is_snap = {
                    "ebit":             _round2(is_row.get("ebit")),
                    "interest_expense": _round2(is_row.get("interest_expense")),
                }
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: IS latest failed: %s", exc)
        cf_snap: dict = {}
        try:
            cf = await self.get_cash_flow_latest(company_id)
            if cf:
                cf_snap = {
                    "cash_from_operating_activities": _round2(cf.get("cash_from_operating_activities")),
                    "capital_expenditures":           _round2(cf.get("capital_expenditures")),
                }
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: CF latest failed: %s", exc)
        beta: Optional[float] = None
        try:
            cs = (
                supabase.table("company_summary")
                .select("beta")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_row = _first(cs.data)
            if cs_row and cs_row.get("beta") is not None:
                beta = _round6(cs_row["beta"])
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: beta failed: %s", exc)
        params_hash: Optional[str] = None
        try:
            md = (
                supabase.table("valuation_method_defaults")
                .select("method, params")
                .in_("method", ["rule1"])
                .execute()
            )
            params_hash = _hash_params(md.data or [])
        except Exception as exc:
            logger.warning("get_rule1_dependency_values: params failed: %s", exc)
        return {
            "ratios_series":      ratios_series,
            "is_series":          is_series,
            "balance_sheet":      bs_snap,
            "income_stmt_latest": is_snap,
            "cash_flow_latest":   cf_snap,
            "beta_latest":        beta,
            "params_version":     params_hash,
        }

    async def get_dcf_dependency_values(self, company_id: int) -> Dict[str, Any]:
        cf_snap: dict = {}
        try:
            cf = await self.get_cash_flow_latest(company_id)
            if cf:
                cf_snap = {
                    "fiscal_year":                    cf.get("fiscal_year"),
                    "cash_from_operating_activities": _round2(cf.get("cash_from_operating_activities")),
                    "capital_expenditures":           _round2(cf.get("capital_expenditures")),
                }
        except Exception as exc:
            logger.warning("get_dcf_dependency_values: CF latest failed: %s", exc)
        bs_snap: dict = {}
        try:
            bs = await self.get_balance_sheet_latest(company_id)
            if bs:
                bs_snap = {
                    "fiscal_year":               bs.get("fiscal_year"),
                    "total_debt":                _round2(bs.get("total_debt")),
                    "cash_and_cash_equivalents": _round2(bs.get("cash_and_cash_equivalents")),
                }
        except Exception as exc:
            logger.warning("get_dcf_dependency_values: BS latest failed: %s", exc)
        shares: Optional[float] = None
        shares_source: Optional[str] = None
        try:
            rows = await self.get_shares_history(company_id)
            if rows:
                sh = _safe_float_repo(rows[-1].get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares        = _round2(sh)
                    shares_source = "income_statements"
        except Exception as exc:
            logger.warning("get_dcf_dependency_values: shares history failed: %s", exc)
        if shares is None:
            try:
                summary = await self.get_company_summary_latest(company_id)
                if summary:
                    sh = _safe_float_repo(summary.get("shares_outstanding"))
                    if sh and sh > 0:
                        shares        = _round2(sh)
                        shares_source = "company_summary"
            except Exception as exc:
                logger.warning("get_dcf_dependency_values: shares summary failed: %s", exc)
        params_hash: Optional[str] = None
        try:
            md = (
                supabase.table("valuation_method_defaults")
                .select("method, params")
                .in_("method", ["dcf"])
                .execute()
            )
            params_hash = _hash_params(md.data or [])
        except Exception as exc:
            logger.warning("get_dcf_dependency_values: params failed: %s", exc)
        return {
            "cash_flow_latest": cf_snap,
            "balance_sheet":    bs_snap,
            "shares":           shares,
            "shares_source":    shares_source,
            "params_version":   params_hash,
        }

    async def get_oe_dependency_values(self, company_id: int) -> Dict[str, Any]:
        cf_snap: dict = {}
        try:
            cf = await self.get_cash_flow_oe_inputs(company_id)
            if cf:
                cf_snap = {
                    "fiscal_year":                    cf.get("fiscal_year"),
                    "cash_from_operating_activities": _round2(cf.get("cash_from_operating_activities")),
                    "capital_expenditures":           _round2(cf.get("capital_expenditures")),
                    "depreciation_amortization":      _round2(cf.get("depreciation_amortization")),
                    "change_in_working_capital":      _round2(cf.get("change_in_working_capital")),
                }
        except Exception as exc:
            logger.warning("get_oe_dependency_values: CF failed: %s", exc)
        is_snap: dict = {}
        try:
            is_row = await self.get_income_statement_latest(company_id)
            if is_row:
                is_snap = {
                    "fiscal_year":          is_row.get("fiscal_year"),
                    "net_income":           _round2(is_row.get("net_income")),
                    "net_income_to_common": _round2(is_row.get("net_income_to_common")),
                }
        except Exception as exc:
            logger.warning("get_oe_dependency_values: IS latest failed: %s", exc)
        bs_snap: dict = {}
        try:
            bs = await self.get_balance_sheet_latest(company_id)
            if bs:
                bs_snap = {
                    "fiscal_year":               bs.get("fiscal_year"),
                    "total_debt":                _round2(bs.get("total_debt")),
                    "cash_and_cash_equivalents": _round2(bs.get("cash_and_cash_equivalents")),
                    "shareholders_equity":       _round2(bs.get("shareholders_equity")),
                }
        except Exception as exc:
            logger.warning("get_oe_dependency_values: BS latest failed: %s", exc)
        shares: Optional[float] = None
        shares_source: Optional[str] = None
        try:
            rows = await self.get_shares_history(company_id)
            if rows:
                sh = _safe_float_repo(rows[-1].get("shares_outstanding_diluted"))
                if sh and sh > 0:
                    shares        = _round2(sh)
                    shares_source = "income_statements"
        except Exception as exc:
            logger.warning("get_oe_dependency_values: shares history failed: %s", exc)
        if shares is None:
            try:
                summary = await self.get_company_summary_latest(company_id)
                if summary:
                    sh = _safe_float_repo(summary.get("shares_outstanding"))
                    if sh and sh > 0:
                        shares        = _round2(sh)
                        shares_source = "company_summary"
            except Exception as exc:
                logger.warning("get_oe_dependency_values: shares summary failed: %s", exc)
        params_hash: Optional[str] = None
        try:
            md = (
                supabase.table("valuation_method_defaults")
                .select("method, params")
                .in_("method", ["owner_earnings"])
                .execute()
            )
            params_hash = _hash_params(md.data or [])
        except Exception as exc:
            logger.warning("get_oe_dependency_values: params failed: %s", exc)
        return {
            "cash_flow_latest":   cf_snap,
            "income_stmt_latest": is_snap,
            "balance_sheet":      bs_snap,
            "shares":             shares,
            "shares_source":      shares_source,
            "params_version":     params_hash,
        }

    async def get_ri_dependency_values(self, company_id: int) -> Dict[str, Any]:
        bs_snap: dict = {}
        try:
            bs = await self.get_balance_sheet_latest(company_id)
            if bs:
                bs_snap = {
                    "fiscal_year":         bs.get("fiscal_year"),
                    "shareholders_equity": _round2(bs.get("shareholders_equity")),
                }
        except Exception as exc:
            logger.warning("get_ri_dependency_values: BS latest failed: %s", exc)
        is_snap: dict = {}
        try:
            is_row = await self.get_income_statement_latest(company_id)
            if is_row:
                is_snap = {
                    "fiscal_year":                is_row.get("fiscal_year"),
                    "net_income":                 _round2(is_row.get("net_income")),
                    "net_income_to_common":       _round2(is_row.get("net_income_to_common")),
                    "shares_outstanding_diluted": _round2(is_row.get("shares_outstanding_diluted")),
                }
        except Exception as exc:
            logger.warning("get_ri_dependency_values: IS latest failed: %s", exc)
        cs_snap: dict = {}
        try:
            cs = (
                supabase.table("company_summary")
                .select("shares_outstanding, beta")
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            cs_row = _first(cs.data)
            if cs_row:
                cs_snap = {
                    "shares_outstanding": _round2(cs_row.get("shares_outstanding")),
                    "beta":               _round6(cs_row.get("beta")),
                }
        except Exception as exc:
            logger.warning("get_ri_dependency_values: company_summary failed: %s", exc)
        eps_series: list = []
        try:
            eps_rows = await self.get_eps_yearly_series(company_id)
            pairs = sorted(
                [(r["fiscal_year"], r["eps"]) for r in eps_rows
                 if r.get("fiscal_year") and r.get("eps") is not None],
                key=lambda t: t[0],
            )[-7:]
            eps_series = [
                {"year": y, "eps": _round6(float(v))}
                for y, v in pairs if v is not None
            ]
        except Exception as exc:
            logger.warning("get_ri_dependency_values: EPS series failed: %s", exc)
        params_hash: Optional[str] = None
        try:
            md = (
                supabase.table("valuation_method_defaults")
                .select("method, params")
                .in_("method", ["residual_income"])
                .execute()
            )
            params_hash = _hash_params(md.data or [])
        except Exception as exc:
            logger.warning("get_ri_dependency_values: params failed: %s", exc)
        return {
            "balance_sheet":      bs_snap,
            "income_stmt_latest": is_snap,
            "company_summary":    cs_snap,
            "eps_series":         eps_series,
            "params_version":     params_hash,
        }

    # ── Company summary ────────────────────────────────────────────────────────

    async def get_company_summary_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
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
                "company_id":         company_id,
                "method":             method,
                "run_by_user_id":     run.get("run_by_user_id"),
                "input_snapshot":     run["input_snapshot"],
                "assumption_snapshot": run["assumption_snapshot"],
                "output_snapshot":    run["output_snapshot"],
                "data_version_tag":   run.get("data_version_tag"),
                "notes":              run.get("notes"),
            }
            supabase.table("valuation_runs").insert(rec).execute()
        except Exception as e:
            logger.error("insert_valuation_run failed (%s): %s", method, e)
            raise

    async def upsert_intrinsic_value_analysis(self, company_id: int, payload: Dict[str, Any]) -> None:
        try:
            data = {
                "company_id":   company_id,
                "growth_rate":  payload["growth_rate"],
                "current_eps":  payload["current_eps"],
                "future_pe":    payload["future_pe"],
                "future_price": payload["future_price"],
                "sticker_price": payload["sticker_price"],
                "mos_price":    payload["mos_price"],
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
                ocf_f   = _safe_float_repo(r.get("cash_from_operating_activities"))
                capex_f = _safe_float_repo(r.get("capital_expenditures"))
                fcf     = _compute_fcf(ocf_f, capex_f)
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
                if y is not None:
                    capex_by_year[int(y)] = _safe_float_repo(r.get("capital_expenditures"))
            rev_by_year: Dict[int, Optional[float]] = {}
            for r in (is_.data or []):
                y = r.get("fiscal_year")
                if y is not None:
                    rev_by_year[int(y)] = _safe_float_repo(r.get("revenue"))
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
            items = []
            for r in (resp.data or []):
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}
                items.append({
                    "runAt":        run_at.isoformat() if run_at else None,
                    "stickerPrice": valuation.get("stickerPrice"),
                    "mosPrice":     valuation.get("mosPrice"),
                    "futurePrice":  valuation.get("futurePrice"),
                    "growth":       valuation.get("growth"),
                    "futurePE":     valuation.get("futurePE"),
                    "score":        applicability.get("score"),
                    "category":     applicability.get("category"),
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
            items = []
            for r in (resp.data or []):
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}
                items.append({
                    "runAt":              run_at.isoformat() if run_at else None,
                    "method":             valuation.get("method"),
                    "intrinsicValue":     valuation.get("intrinsicValue"),
                    "dividendGrowthRate": valuation.get("dividendGrowthRate"),
                    "requiredReturn":     valuation.get("requiredReturn"),
                    "score":              applicability.get("score"),
                    "category":           applicability.get("category"),
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
            items = []
            for r in (resp.data or []):
                run_at = _normalize_datetime(r.get("run_at"))
                snap = r.get("output_snapshot") or {}
                valuation = snap.get("valuation") or {}
                applicability = snap.get("applicability") or {}
                items.append({
                    "runAt":                  run_at.isoformat() if run_at else None,
                    "terminalMethod":         valuation.get("terminalMethod"),
                    "intrinsicValuePerShare": valuation.get("intrinsicValuePerShare"),
                    "waccUsed":               valuation.get("waccUsed"),
                    "terminalValue":          valuation.get("terminalValue"),
                    "enterpriseValue":        valuation.get("enterpriseValue"),
                    "score":                  applicability.get("score"),
                    "category":               applicability.get("category"),
                })
            return items
        except Exception as e:
            logger.error("get_dcf_history failed for %s: %s", symbol, e)
            return []

    # ── Earnings events ────────────────────────────────────────────────────────

    async def get_earnings_events(self, company_id: int) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("earnings")
            .select("*")
            .eq("company_id", company_id)
            .order("report_date", desc=False)
            .execute()
        )
        return resp.data or []