# backend/application/services/dividend_analysis_service.py
"""
Dividend Analysis Service — Overview, Safety, Growth, Yield

Data sources — all verified against valuation_repository.py:
  dividend_history     → repo.get_dividend_history()
                         columns: ex_dividend_date, dividend_amount, currency, updated_at
                         NOTE: NO frequency / payment_date / record_date columns
  dividend_metrics     → repo.get_dividend_metrics_latest()
                         columns: annual_dps, dividend_yield,
                                  dividend_growth_rate_3yr/5yr/10yr,
                                  consecutive_years_paid, fcfe_coverage_ratio,
                                  cash_dividend_payout_ratio, ebitda_dividend_coverage,
                                  retention_ratio
  income_statements    → repo.get_income_statement_latest() / get_income_statements_annual()
  cash_flow_statements → repo.get_cash_flow_latest() for OCF+capex
                         + direct supabase query for dividends_paid (not in repo SELECT)
  balance_sheets       → repo.get_balance_sheet_latest()
  price_history        → direct supabase query (no repo method exists)
  current_market_data  → repo.get_current_market_price()
  FCF                  → repo.get_fcf_history() — already computes OCF+capex

No new DB writes. GET-only. React Query caches 5 minutes client-side.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from datetime import date, timedelta
from shared.time_utils import now_utc, now_iso, parse_db_timestamp
from typing import Any, Dict, List, Optional, Tuple

from database import supabase
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import safe_float

logger = logging.getLogger(__name__)


# ── Pure helpers ──────────────────────────────────────────────────────────────

def _infer_frequency(sorted_desc: List[Dict]) -> Tuple[str, int]:
    """
    Infer payment frequency from average gap between dividend_history rows.
    Returns (label, payments_per_year).
    """
    dates = []
    for d in sorted_desc[:8]:
        raw = d.get("ex_dividend_date")
        if raw:
            try:
                dates.append(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                pass
    if len(dates) < 3:
        return "quarterly", 4
    dates_sorted = sorted(dates)
    gaps = [(dates_sorted[i + 1] - dates_sorted[i]).days for i in range(len(dates_sorted) - 1)]
    avg  = sum(gaps) / len(gaps)
    if avg <= 35:   return "monthly",     12
    if avg <= 100:  return "quarterly",   4
    if avg <= 200:  return "semi-annual", 2
    return "annual", 1


# ── Service ───────────────────────────────────────────────────────────────────

class DividendAnalysisService:
    def __init__(self, repo: ValuationRepository):
        self.repo = repo

    async def get_dividend_analysis(self, symbol: str) -> Dict[str, Any]:
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise ValueError(f"Symbol '{symbol}' not found.")
        company_id = int(ctx["company_id"])

        (
            div_history,
            div_metrics,
            income_latest,
            income_annual,
            cf_latest,
            dividends_paid_row,
            bs_latest,
            current_price,
            fcf_history,
            price_history,
        ) = await asyncio.gather(
            self._fetch_dividend_history(company_id),
            self.repo.get_dividend_metrics_latest(company_id),
            self.repo.get_income_statement_latest(company_id),
            self.repo.get_income_statements_annual(company_id, limit=6),
            self.repo.get_cash_flow_latest(company_id),
            self._fetch_dividends_paid(company_id),
            self.repo.get_balance_sheet_latest(company_id),
            self.repo.get_current_market_price(company_id),
            self.repo.get_fcf_history(company_id, years=5),
            self._fetch_price_history(company_id),
        )

        if not div_history:
            return {
                "symbol": symbol.upper(), "pays_dividend": False,
                "overview": None, "safety": None,
                "growth": None, "yield_analysis": None,
            }

        sorted_desc = sorted(
            div_history,
            key=lambda d: d.get("ex_dividend_date") or "",
            reverse=True,
        )
        freq_label, freq_mult = _infer_frequency(sorted_desc)

        return {
            "symbol":         symbol.upper(),
            "pays_dividend":  True,
            "overview":       self._compute_overview(sorted_desc, freq_label, freq_mult,
                                                      income_latest or {}, div_metrics,
                                                      dividends_paid_row, current_price),
            "safety":         self._compute_safety(sorted_desc, income_annual, income_latest or {},
                                                    cf_latest, dividends_paid_row, bs_latest,
                                                    fcf_history, div_metrics),
            "growth":         self._compute_growth(sorted_desc, div_metrics),
            "yield_analysis": self._compute_yield(sorted_desc, freq_mult, price_history,
                                                   current_price, div_metrics),
        }

    # ── Data fetchers ─────────────────────────────────────────────────────────

    async def _fetch_dividend_history(self, company_id: int) -> List[Dict]:
        """Uses repo.get_dividend_history — reads dividend_history table."""
        return await self.repo.get_dividend_history(company_id, limit=120)

    async def _fetch_dividends_paid(self, company_id: int) -> Optional[Dict]:
        """
        Direct query: dividends_paid is NOT in repo.get_cash_flow_latest's SELECT list.
        Also fetches free_cash_flow for fallback FCF payout computation.
        """
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select("fiscal_year, dividends_paid, free_cash_flow")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", None)
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as exc:
            logger.warning("_fetch_dividends_paid failed company_id=%s: %s", company_id, exc)
            return None

    async def _fetch_price_history(self, company_id: int) -> List[Dict]:
        """Direct query — price_history has no method in ValuationRepository."""
        try:
            cutoff = (now_utc().date() - timedelta(days=6 * 365)).isoformat()
            resp = (
                supabase.table("price_history")
                .select("price_date, close_price")
                .eq("company_id", company_id)
                .gte("price_date", cutoff)
                .order("price_date", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception as exc:
            logger.warning("_fetch_price_history failed company_id=%s: %s", company_id, exc)
            return []

    # ── Overview ──────────────────────────────────────────────────────────────

    def _compute_overview(
        self,
        sorted_desc:        List[Dict],
        freq_label:         str,
        freq_mult:          int,
        income_latest:      Dict,
        div_metrics:        Optional[Dict],
        dividends_paid_row: Optional[Dict],
        current_price:      Optional[float],
    ) -> Dict[str, Any]:
        dm         = div_metrics or {}
        latest     = sorted_desc[0]
        per_period = safe_float(latest.get("dividend_amount"))

        # Prefer pre-computed annual_dps from dividend_metrics
        annual_div = safe_float(dm.get("annual_dps"))
        if annual_div is None and per_period:
            annual_div = per_period * freq_mult

        # Prefer pre-computed yield from dividend_metrics
        cp             = safe_float(current_price)
        dividend_yield = safe_float(dm.get("dividend_yield"))
        if dividend_yield is None and annual_div and cp and cp > 0:
            dividend_yield = annual_div / cp

        # Payout — adj EPS basis
        eps = safe_float(income_latest.get("eps_diluted"))
        payout_adj_eps = None
        if annual_div and eps and eps > 0:
            payout_adj_eps = annual_div / eps

        # Payout — GAAP (net income)
        divs_paid_raw = safe_float((dividends_paid_row or {}).get("dividends_paid"))
        divs_paid     = abs(divs_paid_raw) if divs_paid_raw is not None else None
        net_income    = safe_float(income_latest.get("net_income") or income_latest.get("net_income_to_common"))
        payout_gaap   = None
        if divs_paid and net_income and net_income > 0:
            payout_gaap = divs_paid / net_income

        # FCF payout — prefer pre-computed cash_dividend_payout_ratio
        payout_fcf = safe_float(dm.get("cash_dividend_payout_ratio"))
        if payout_fcf is None:
            fcf = safe_float((dividends_paid_row or {}).get("free_cash_flow"))
            if divs_paid and fcf and fcf > 0:
                payout_fcf = divs_paid / fcf

        gaap_negative_eps  = (net_income is not None and net_income <= 0)
        last_increase_date = self._last_increase_date(sorted_desc)
        status             = self._determine_status(sorted_desc)

        sparkline = [
            {"date": d.get("ex_dividend_date"), "amount": safe_float(d.get("dividend_amount"))}
            for d in sorted(sorted_desc[:24], key=lambda x: x.get("ex_dividend_date") or "")
            if d.get("ex_dividend_date") and d.get("dividend_amount") is not None
        ]

        return {
            "annual_dividend":      round(annual_div, 4)      if annual_div      is not None else None,
            "per_period_amount":    round(per_period, 4)       if per_period      is not None else None,
            "dividend_yield":       round(dividend_yield, 4)   if dividend_yield  is not None else None,
            "payout_ratio_adj_eps": round(payout_adj_eps, 4)  if payout_adj_eps  is not None else None,
            "payout_ratio_gaap":    round(payout_gaap, 4)     if payout_gaap     is not None else None,
            "payout_ratio_fcf":     round(payout_fcf, 4)      if payout_fcf      is not None else None,
            "gaap_negative_eps":    gaap_negative_eps,
            "frequency":            freq_label,
            "frequency_multiplier": freq_mult,
            # dividend_history has no payment_date column — omit
            "ex_dividend_date":     latest.get("ex_dividend_date"),
            "payment_date":         None,
            "last_increase_date":   last_increase_date,
            "status":               status,
            "sparkline":            sparkline,
            "current_price":        round(float(cp), 2) if cp else None,
        }

    def _last_increase_date(self, sorted_desc: List[Dict]) -> Optional[str]:
        for i in range(len(sorted_desc) - 1):
            curr = safe_float(sorted_desc[i].get("dividend_amount"))
            prev = safe_float(sorted_desc[i + 1].get("dividend_amount"))
            if curr and prev and curr > prev * 1.001:
                return sorted_desc[i].get("ex_dividend_date")
        return None

    def _determine_status(self, sorted_desc: List[Dict]) -> str:
        if not sorted_desc:
            return "no_dividend"
        amounts = [safe_float(d.get("dividend_amount")) for d in sorted_desc[:8] if d.get("dividend_amount")]
        if not amounts or len(amounts) < 2:
            return "stable"
        if any(amounts[i] < amounts[i + 1] * 0.90 for i in range(len(amounts) - 1)):
            return "declining"
        if amounts[0] > amounts[-1] * 1.05:
            return "growing"
        return "stable"

    # ── Safety ────────────────────────────────────────────────────────────────

    def _compute_safety(
        self,
        sorted_desc:        List[Dict],
        income_annual:      List[Dict],
        income_latest:      Dict,
        cf_latest:          Optional[Dict],
        dividends_paid_row: Optional[Dict],
        bs_latest:          Optional[Dict],
        fcf_history:        List[Dict],
        div_metrics:        Optional[Dict],
    ) -> Dict[str, Any]:
        dm = div_metrics or {}

        # Income
        ebit         = safe_float(income_latest.get("ebit"))
        interest_exp = safe_float(income_latest.get("interest_expense"))
        ebitda       = safe_float(income_latest.get("ebitda"))
        net_income   = safe_float(income_latest.get("net_income") or income_latest.get("net_income_to_common"))

        # Cash flow — OCF from repo, dividends_paid from direct query
        ocf           = safe_float((cf_latest or {}).get("cash_from_operating_activities"))
        divs_paid_raw = safe_float((dividends_paid_row or {}).get("dividends_paid"))
        divs_paid     = abs(divs_paid_raw) if divs_paid_raw is not None else None

        # FCF from repo.get_fcf_history (latest year)
        fcf = None
        if fcf_history:
            latest_fcf = sorted(fcf_history, key=lambda r: r.get("fiscal_year") or 0)[-1]
            fcf = safe_float(latest_fcf.get("fcf"))

        # Balance sheet
        total_debt = safe_float((bs_latest or {}).get("total_debt"))
        cash       = safe_float((bs_latest or {}).get("cash_and_cash_equivalents"))
        net_debt   = (total_debt - cash) if (total_debt is not None and cash is not None) else None

        # ── Payout ratios ──────────────────────────────────────────────────────
        # EPS-based payout — annual_dps (per share) / eps_diluted (per share).
        # Prefer pre-computed annual_dps from dividend_metrics; fall back to
        # latest dividend × inferred frequency when the table is not yet populated.
        annual_dps = safe_float(dm.get("annual_dps"))
        if annual_dps is None:
            _freq_label, _freq_mult = _infer_frequency(sorted_desc)
            _latest_amt = safe_float(
                (sorted_desc[0] if sorted_desc else {}).get("dividend_amount")
            )
            if _latest_amt and _freq_mult:
                annual_dps = _latest_amt * _freq_mult
        eps = safe_float(income_latest.get("eps_diluted"))
        payout_eps = (annual_dps / eps) if (annual_dps and eps and eps > 0) else None

        # GAAP payout — total cash dividends paid / net income
        payout_gaap = (divs_paid / net_income) if (divs_paid and net_income and net_income > 0) else None

        # FCF coverage — prefer pre-computed, fall back to fcf / divs_paid
        fcf_cov = safe_float(dm.get("fcfe_coverage_ratio"))
        if fcf_cov is None and fcf and divs_paid and divs_paid > 0:
            fcf_cov = fcf / divs_paid

        # OCF payout, FCF payout, leverage, interest coverage
        cash_payout = (divs_paid / ocf)           if (divs_paid and ocf and ocf > 0)                      else None
        fcf_payout  = (divs_paid / fcf)           if (divs_paid and fcf and fcf > 0)                      else None
        nd_ebitda   = (net_debt / ebitda)         if (net_debt is not None and ebitda and ebitda > 0)      else None
        int_cov     = (ebit / abs(interest_exp))  if (ebit and interest_exp and interest_exp != 0)         else None

        has_cut, cut_year = self._check_cut_history(sorted_desc)
        score    = self._score_safety(payout_eps, fcf_cov, cash_payout, nd_ebitda, int_cov, has_cut, cut_year)
        category = "Good" if score >= 70 else "Caution" if score >= 45 else "Poor"

        metrics = self._build_safety_metrics(
            payout_eps, payout_gaap, cash_payout, fcf_payout,
            fcf_cov, nd_ebitda, int_cov, net_income,
        )

        incomes = [
            safe_float(r.get("net_income") or r.get("net_income_to_common"))
            for r in income_annual[:5] if r
        ]
        incomes = [x for x in incomes if x is not None]
        earnings_stability = self._classify_earnings_stability(incomes)

        retention_rate  = safe_float(dm.get("retention_ratio"))
        growth_trend    = self._growth_trend(sorted_desc)
        dividend_policy = {
            "growth_trend":   growth_trend,
            "cut_history":    f"Major cut ({cut_year})" if (has_cut and cut_year) else "No cuts on record",
            "has_cut":        has_cut,
            "cut_year":       cut_year,
            "retention_rate": round(retention_rate, 3) if retention_rate is not None else None,
        }

        strengths, key_risks = self._strengths_risks(
            payout_eps, fcf_cov, nd_ebitda, int_cov, has_cut, category
        )

        return {
            "composite_score":    score,
            "composite_category": category,
            "metrics":            metrics,
            "earnings_stability": earnings_stability,
            "dividend_policy":    dividend_policy,
            "strengths":          strengths,
            "key_risks":          key_risks,
        }

    def _score_safety(self, payout_adj, fcf_cov, cash_payout, nd_ebitda, int_cov, has_cut, cut_year) -> int:
        s = 0
        if payout_adj is not None:
            s += 20 if payout_adj < 0.40 else 17 if payout_adj < 0.55 else 12 if payout_adj < 0.70 else 6 if payout_adj < 0.85 else 0
        if fcf_cov is not None:
            s += 25 if fcf_cov > 3.0 else 20 if fcf_cov > 2.0 else 12 if fcf_cov > 1.5 else 6 if fcf_cov > 1.0 else 0
        if cash_payout is not None:
            s += 15 if cash_payout < 0.50 else 12 if cash_payout < 0.65 else 8 if cash_payout < 0.80 else 3 if cash_payout < 1.00 else 0
        if nd_ebitda is not None:
            s += 20 if nd_ebitda < 1.0 else 16 if nd_ebitda < 2.0 else 10 if nd_ebitda < 3.0 else 4 if nd_ebitda < 4.0 else 0
        if int_cov is not None:
            s += 10 if int_cov > 5.0 else 8 if int_cov > 3.0 else 5 if int_cov > 2.0 else 2 if int_cov > 1.0 else 0
        s += 10 if not has_cut else (4 if cut_year and (now_utc().year - cut_year) > 5 else 0)
        return min(100, s)

    def _build_safety_metrics(self, payout_adj, payout_gaap, cash_payout, fcf_payout,
                               fcf_cov, nd_ebitda, int_cov, net_income) -> List[Dict]:
        def _rate(v, tiers):
            if v is None: return "info"
            for t, r in tiers:
                if v < t: return r
            return tiers[-1][1]
        gaap_neg = (net_income is not None and net_income <= 0)
        return [
            {"name": "Div Payout (Adj EPS)", "benchmark": "<60%",
             "value": round(payout_adj, 4) if payout_adj is not None else None,
             "formatted": f"{payout_adj*100:.0f}%" if payout_adj is not None else "N/A",
             "rating": _rate(payout_adj, [(0.60,"safe"),(0.80,"moderate"),(999,"risk")])},
            {"name": "Div Payout (GAAP)", "benchmark": "—",
             "value": round(payout_gaap, 4) if payout_gaap is not None else None,
             "formatted": (f"{payout_gaap*100:.0f}%" if payout_gaap is not None
                           else "Not meaningful (neg EPS)" if gaap_neg else "N/A"),
             "rating": "info", "info_note": "Neg EPS" if gaap_neg else None},
            {"name": "Cash Div Payout", "benchmark": "<80%",
             "value": round(cash_payout, 4) if cash_payout is not None else None,
             "formatted": f"{cash_payout*100:.0f}%" if cash_payout is not None else "N/A",
             "rating": _rate(cash_payout, [(0.80,"safe"),(1.00,"moderate"),(999,"risk")])},
            {"name": "FCF Payout Ratio", "benchmark": "<80%",
             "value": round(fcf_payout, 4) if fcf_payout is not None else None,
             "formatted": f"{fcf_payout*100:.0f}%" if fcf_payout is not None else "N/A",
             "rating": _rate(fcf_payout, [(0.80,"safe"),(1.00,"moderate"),(999,"risk")])},
            {"name": "Div Coverage (FCF)", "benchmark": "≥2×",
             "value": round(fcf_cov, 2) if fcf_cov is not None else None,
             "formatted": f"{fcf_cov:.1f}×" if fcf_cov is not None else "N/A",
             "rating": ("safe" if fcf_cov and fcf_cov >= 2.0 else
                        "moderate" if fcf_cov and fcf_cov >= 1.0 else "risk") if fcf_cov is not None else "info"},
            {"name": "Net Debt / EBITDA", "benchmark": "<3×",
             "value": round(nd_ebitda, 2) if nd_ebitda is not None else None,
             "formatted": f"{nd_ebitda:.1f}×" if nd_ebitda is not None else "N/A",
             "rating": ("safe" if nd_ebitda is not None and nd_ebitda < 2.0 else
                        "moderate" if nd_ebitda is not None and nd_ebitda < 3.0 else
                        "borderline" if nd_ebitda is not None and nd_ebitda < 4.0 else "risk")
                       if nd_ebitda is not None else "info"},
            {"name": "Interest Coverage", "benchmark": "≥3×",
             "value": round(int_cov, 2) if int_cov is not None else None,
             "formatted": f"{int_cov:.1f}×" if int_cov is not None else "N/A",
             "rating": ("safe" if int_cov and int_cov >= 3.0 else
                        "moderate" if int_cov and int_cov >= 2.0 else "risk") if int_cov is not None else "info"},
        ]

    def _check_cut_history(self, sorted_desc: List[Dict]) -> Tuple[bool, Optional[int]]:
        for i in range(len(sorted_desc) - 1):
            curr = safe_float(sorted_desc[i].get("dividend_amount"))
            prev = safe_float(sorted_desc[i + 1].get("dividend_amount"))
            if curr and prev and curr < prev * 0.90:
                dt = sorted_desc[i].get("ex_dividend_date", "")
                try:    return True, int(str(dt)[:4])
                except: return True, None
        return False, None

    def _classify_earnings_stability(self, incomes: List[float]) -> str:
        if len(incomes) < 3:
            return "insufficient_data"
        try:
            mean = statistics.mean(incomes)
            if mean == 0: return "volatile"
            cv = statistics.stdev(incomes) / abs(mean)
            return "high" if cv < 0.10 else "moderate" if cv < 0.30 else "volatile"
        except statistics.StatisticsError:
            return "insufficient_data"

    def _growth_trend(self, sorted_desc: List[Dict]) -> str:
        amounts = [safe_float(d.get("dividend_amount")) for d in sorted_desc[:8] if d.get("dividend_amount")]
        if not amounts or len(amounts) < 2: return "insufficient_data"
        if amounts[0] > amounts[-1] * 1.02: return "growing"
        if amounts[0] < amounts[-1] * 0.98: return "declining"
        return "flat"

    def _strengths_risks(self, payout_adj, fcf_cov, nd_ebitda, int_cov, has_cut, category):
        strengths, risks = [], []
        if payout_adj and payout_adj < 0.60:
            strengths.append("Dividend well-covered by adjusted earnings")
        if fcf_cov and fcf_cov >= 1.5:
            strengths.append("Free cash flow generation supports the distribution")
        if int_cov and int_cov >= 3.0:
            strengths.append("Strong interest coverage provides debt service buffer")
        if nd_ebitda is not None and nd_ebitda < 2.0:
            strengths.append("Conservative leverage preserves dividend flexibility")
        if not has_cut:
            strengths.append("No dividend reductions in recent payment history")
        if has_cut:
            risks.append("Prior dividend cut impairs reliability track record")
        if nd_ebitda is not None and nd_ebitda >= 3.0:
            risks.append(f"Leverage at {nd_ebitda:.1f}× Net Debt/EBITDA constrains growth")
        if fcf_cov and fcf_cov < 1.5:
            risks.append(f"FCF coverage of {fcf_cov:.1f}× is below the ≥2× safe threshold")
        if payout_adj and payout_adj >= 0.70:
            risks.append(f"Payout ratio of {payout_adj*100:.0f}% limits reinvestment capacity")
        if int_cov and int_cov < 2.0:
            risks.append("Low interest coverage increases financial vulnerability")
        if not strengths: strengths.append("Dividend payments maintained through challenging periods")
        if not risks:     risks.append("Monitor coverage ratios if earnings deteriorate")
        return strengths[:5], risks[:5]

    # ── Growth ────────────────────────────────────────────────────────────────

    def _compute_growth(self, sorted_desc: List[Dict], div_metrics: Optional[Dict]) -> Dict[str, Any]:
        dm = div_metrics or {}

        # Prefer pre-computed CAGRs from dividend_metrics
        cagr_3y  = safe_float(dm.get("dividend_growth_rate_3yr"))
        cagr_5y  = safe_float(dm.get("dividend_growth_rate_5yr"))
        cagr_10y = safe_float(dm.get("dividend_growth_rate_10yr"))
        cagr_1y  = self._compute_1y_cagr(sorted_desc)
        if cagr_3y is None:
            cagr_3y = self._compute_cagr_from_history(sorted_desc, 3)
        if cagr_5y is None:
            cagr_5y = self._compute_cagr_from_history(sorted_desc, 5)
        # cagr_10y: no computed fallback — history is capped at 5 years

        consecutive_increases = self._count_consecutive_increases(sorted_desc)

        score = 0
        def _pts(c, m):
            if c is None: return 0
            for t, p in sorted(m.items(), reverse=True):
                if c >= t: return p
            return 0
        score += _pts(cagr_1y,  {0.08:15, 0.05:12, 0.02:8, 0.00:4})
        score += _pts(cagr_5y,  {0.08:25, 0.05:20, 0.02:12, 0.00:5})
        score += _pts(cagr_10y, {0.08:20, 0.05:15, 0.02:8, 0.00:4})
        if consecutive_increases >= 10:   score += 40
        elif consecutive_increases >= 5:  score += 28
        elif consecutive_increases >= 3:  score += 16
        elif consecutive_increases >= 1:  score += 8
        # Aggregate annual totals from dividend history
        annual_totals: Dict[str, float] = {}
        for d in sorted_desc:
            raw = d.get("ex_dividend_date", "")
            try:
                year = str(raw)[:4]
            except:
                continue
            amt = safe_float(d.get("dividend_amount"))
            if amt:
                annual_totals[year] = annual_totals.get(year, 0.0) + amt
        # Sort by year ascending
        annual_totals = dict(sorted(annual_totals.items()))

        score = min(100, score)

        growth_category = "Good" if score >= 65 else "Caution" if score >= 35 else "Poor"

        recent_changes = []
        for i in range(min(8, len(sorted_desc) - 1)):
            curr_amt = safe_float(sorted_desc[i].get("dividend_amount"))
            prev_amt = safe_float(sorted_desc[i + 1].get("dividend_amount"))
            if curr_amt is None or prev_amt is None: continue
            chg       = (curr_amt - prev_amt) / prev_amt if prev_amt > 0 else 0.0
            direction = "increase" if chg > 0.001 else "decrease" if chg < -0.001 else "flat"
            recent_changes.append({
                "date":       sorted_desc[i].get("ex_dividend_date"),
                "amount":     round(curr_amt, 4),
                "change_pct": round(chg, 4),
                "label":      "Flat" if direction == "flat" else f"+{chg*100:.1f}%" if direction == "increase" else f"{chg*100:.1f}%",
                "direction":  direction,
            })

        return {
            "growth_score":          score,
            "growth_category":       growth_category,
            "cagr_1y":               round(cagr_1y, 4)  if cagr_1y  is not None else None,
            "cagr_3y":               round(cagr_3y, 4)  if cagr_3y  is not None else None,
            "cagr_5y":               round(cagr_5y, 4)  if cagr_5y  is not None else None,
            "cagr_10y":              round(cagr_10y, 4) if cagr_10y is not None else None,
            "consecutive_increases": consecutive_increases,
            "annual_totals":         annual_totals,
            "recent_changes":        recent_changes[:6],
        }

    def _compute_1y_cagr(self, sorted_desc: List[Dict]) -> Optional[float]:
        if len(sorted_desc) < 5: return None
        curr = safe_float(sorted_desc[0].get("dividend_amount"))
        prev = safe_float(sorted_desc[4].get("dividend_amount"))
        if curr and prev and prev > 0:
            return (curr - prev) / prev
        return None
    
    def _compute_cagr_from_history(self, sorted_desc: List[Dict], years: int) -> Optional[float]:
        """
        Computes CAGR by aggregating dividend payments into annual totals per
        calendar year, then comparing the most recent full year against `years`
        years prior.  Used as a fallback when dividend_metrics is not yet
        populated by the ingestion job.
        """
        annual: Dict[int, float] = {}
        for d in sorted_desc:
            raw = d.get("ex_dividend_date", "")
            try:
                year = int(str(raw)[:4])
            except (ValueError, TypeError):
                continue
            amt = safe_float(d.get("dividend_amount"))
            if amt:
                annual[year] = annual.get(year, 0.0) + amt
        if len(annual) < 2:
            return None
        years_list   = sorted(annual.keys(), reverse=True)
        recent_year  = years_list[0]
        target_year  = recent_year - years
        if target_year not in annual:
            return None
        v0 = annual[target_year]
        vn = annual[recent_year]
        if v0 <= 0 or vn <= 0:
            return None
        try:
            return (vn / v0) ** (1.0 / years) - 1.0
        except Exception:
            return None

    def _count_consecutive_increases(self, sorted_desc: List[Dict]) -> int:
        annual: Dict[int, float] = {}
        for d in sorted_desc:
            dt = d.get("ex_dividend_date", "")
            try:   year = int(str(dt)[:4])
            except: continue
            amt = safe_float(d.get("dividend_amount"))
            if amt: annual[year] = annual.get(year, 0.0) + amt
        if len(annual) < 2: return 0
        years = sorted(annual.keys(), reverse=True)
        consecutive = 0
        for i in range(len(years) - 1):
            if annual[years[i]] > annual[years[i + 1]] * 1.001:
                consecutive += 1
            else:
                break
        return consecutive

    # ── Yield ─────────────────────────────────────────────────────────────────

    def _compute_yield(
        self,
        sorted_desc:   List[Dict],
        freq_mult:     int,
        price_history: List[Dict],
        current_price: Optional[float],
        div_metrics:   Optional[Dict],
    ) -> Dict[str, Any]:
        dm = div_metrics or {}

        curr_yield = safe_float(dm.get("dividend_yield"))
        if curr_yield is None:
            annual_div = safe_float(dm.get("annual_dps"))
            per_period = safe_float((sorted_desc[0] if sorted_desc else {}).get("dividend_amount"))
            if not annual_div and per_period:
                annual_div = per_period * freq_mult
            cp = safe_float(current_price)
            if annual_div and cp and cp > 0:
                curr_yield = annual_div / cp

        yield_history = self._build_yield_history(sorted_desc, price_history)
        yield_vals    = [p["yield"] for p in yield_history if p.get("yield") is not None]

        avg_5y     = statistics.mean(yield_vals) if yield_vals else None
        min_5y     = min(yield_vals)             if yield_vals else None
        max_5y     = max(yield_vals)             if yield_vals else None
        percentile = None
        if curr_yield and yield_vals:
            below      = sum(1 for y in yield_vals if y <= curr_yield)
            percentile = round((below / len(yield_vals)) * 100)

        theory = None
        if curr_yield and avg_5y:
            if curr_yield > avg_5y * 1.05:
                theory = ("Yield is currently above its 5-year average, suggesting "
                          "potential undervaluation relative to historical norms.")
            elif curr_yield < avg_5y * 0.95:
                theory = ("Yield is below its 5-year average, suggesting the stock "
                          "may be trading at a premium to historical valuation levels.")
            else:
                theory = ("Yield is near its 5-year average, consistent with "
                          "fair valuation relative to historical norms.")

        return {
            "current_yield":       round(curr_yield, 4) if curr_yield else None,
            "avg_yield_5y":        round(avg_5y, 4)     if avg_5y    else None,
            "yield_min_5y":        round(min_5y, 4)     if min_5y    else None,
            "yield_max_5y":        round(max_5y, 4)     if max_5y    else None,
            "yield_percentile_5y": percentile,
            "yield_vs_sector":     None,
            "yield_vs_market":     None,
            "theory_signal":       theory,
            "yield_history":       yield_history[-60:],
        }

    def _build_yield_history(self, sorted_desc: List[Dict], price_history: List[Dict]) -> List[Dict]:
        if not price_history or not sorted_desc:
            return []
        div_timeline = sorted(
            [(str(d.get("ex_dividend_date") or ""), safe_float(d.get("dividend_amount")) or 0.0)
             for d in sorted_desc if d.get("ex_dividend_date")],
            key=lambda x: x[0],
        )
        results = []
        for row in price_history:
            price_date = str(row.get("price_date") or "")
            close      = safe_float(row.get("close_price"))
            if not close or close <= 0 or not price_date: continue
            try:    year_ago = f"{int(price_date[:4]) - 1}{price_date[4:]}"
            except: continue
            ttm = sum(amt for dt, amt in div_timeline if year_ago <= dt <= price_date)
            if ttm > 0:
                results.append({
                    "date":         price_date,
                    "yield":        round(ttm / close, 4),
                    "price":        round(close, 2),
                    "ttm_dividend": round(ttm, 4),
                })
        return results