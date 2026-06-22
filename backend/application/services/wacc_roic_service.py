# application/services/wacc_roic_service.py
"""
WACC / ROIC Analysis Service.

Computes Weighted Average Cost of Capital (WACC) using CAPM for cost of equity,
and Return on Invested Capital (ROIC) from financial ratios history.

Follows existing conventions:
  - All DB access via ValuationRepository (no raw queries)
  - Communicates with AI provider for narrative generation
  - Returns typed Pydantic models (or plain dicts for API serialization)
"""
from __future__ import annotations

import logging
from shared.time_utils import now_utc, now_iso, parse_db_timestamp
from typing import Any, Dict, List, Optional, Tuple

from application.services.ai_service import generate_wacc_roic_narrative
from domain.models.exceptions import WaccRoicError
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.finance_math import (
    clamp,
    compute_cost_of_equity,
    compute_nopat,
    compute_roic,
    compute_wacc,
    pct_or_frac_to_frac,
    safe_div,
    safe_float,
)

logger = logging.getLogger(__name__)

# -- Defaults ----------------------------------------------------------------

_DEFAULT_RISK_FREE_RATE  = 0.045   # 10yr Treasury (fraction)
_DEFAULT_EQUITY_PREMIUM  = 0.055   # Historical ERP (fraction)
_DEFAULT_BETA            = 1.0
_DEFAULT_COST_OF_DEBT    = 0.05    # Pre-tax cost of debt (fraction)
_DEFAULT_TAX_RATE        = 0.21    # Effective tax rate (fraction)
_DEFAULT_MARKET_CAP      = 0.0

# -- Service -----------------------------------------------------------------

class WaccRoicService:
    """WACC and ROIC computation with AI narrative generation."""

    def __init__(self, repo: ValuationRepository):
        self.repo = repo

    # -- Public entry points -------------------------------------------------

    async def compute_wacc_analysis(
        self,
        symbol: str,
        risk_free_rate: Optional[float] = None,
        equity_risk_premium: Optional[float] = None,
        beta: Optional[float] = None,
        cost_of_debt: Optional[float] = None,
        tax_rate: Optional[float] = None,
        market_cap: Optional[float] = None,
        total_debt: Optional[float] = None,
        generate_narrative: bool = True,
    ) -> Dict[str, Any]:
        """
        Compute WACC for a company using CAPM + debt weighting.

        Returns a dict ready for JSON serialization with:
          - wacc:                    final WACC (fraction)
          - costOfEquity:            ke (fraction)
          - costOfDebtAfterTax:      kd*(1-t) (fraction)
          - equityWeight:            E/V
          - debtWeight:              D/V
          - betaUsed:                beta value used
          - riskFreeRateUsed:        rf value used
          - equityRiskPremiumUsed:   ERP value used
          - narrative:               AI-generated explanation (optional)
          - dataQuality:             metadata about input sources
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise WaccRoicError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"

        # -- Resolve CAPM inputs --------------------------------------------
        rf  = pct_or_frac_to_frac(float(risk_free_rate))  if risk_free_rate  is not None else _DEFAULT_RISK_FREE_RATE
        erp = pct_or_frac_to_frac(float(equity_risk_premium)) if equity_risk_premium is not None else _DEFAULT_EQUITY_PREMIUM

        b = beta
        beta_source = "default"
        if b is not None:
            b = float(b)
            beta_source = "override"
        else:
            beta_row = await self.repo.get_beta_latest(company_id)
            if beta_row is not None:
                b = safe_float(beta_row)
                beta_source = "defeatbeta"
            else:
                b = _DEFAULT_BETA
                beta_source = "default"

        ke = compute_cost_of_equity(rf, b, erp)

        # -- Resolve market cap & debt --------------------------------------
        mc = market_cap
        mc_source = "override"
        if mc is None:
            summary = await self.repo.get_company_summary_latest(company_id)
            if summary and summary.get("market_cap"):
                mc = safe_float(summary.get("market_cap"))
                mc_source = "company_summary.market_cap"
            else:
                mc = _DEFAULT_MARKET_CAP
                mc_source = "default"

        td = total_debt
        td_source = "override"
        if td is None:
            bs = await self.repo.get_balance_sheet_latest(company_id)
            if bs and bs.get("total_debt"):
                td = safe_float(bs.get("total_debt"))
                td_source = "balance_sheets.total_debt"
            else:
                td = None
                td_source = "none"

        # -- Resolve cost of debt & tax rate --------------------------------
        kd = cost_of_debt
        kd_source = "override"
        if kd is None:
            kd = _DEFAULT_COST_OF_DEBT
            kd_source = "default"

        t = tax_rate
        t_source = "override"
        if t is None:
            # Derive from most recent income statement
            is_latest = await self.repo.get_income_statement_latest(company_id)
            if is_latest:
                pretax = safe_float(is_latest.get("pretax_income"))
                tax    = safe_float(is_latest.get("tax_expense"))
                if pretax is not None and pretax != 0 and tax is not None:
                    t = clamp(float(tax) / float(pretax), 0.0, 1.0)
                    t_source = "income_statements (derived)"
                else:
                    t = _DEFAULT_TAX_RATE
                    t_source = "default"
            else:
                t = _DEFAULT_TAX_RATE
                t_source = "default"

        # -- Compute WACC ---------------------------------------------------
        wacc = compute_wacc(mc, td, ke, kd, t)

        eq_weight = None
        db_weight = None
        kd_after   = None
        if mc is not None and (mc > 0 or (td is not None and td > 0)):
            ev = float(mc) if mc is not None and mc > 0 else 0.0
            dv = float(td) if td is not None and td > 0 else 0.0
            total = ev + dv
            if total > 0:
                eq_weight = ev / total
                db_weight = dv / total
                if kd is not None and dv > 0:
                    kd_after = float(kd) * (1.0 - float(t))

        # -- Build result ---------------------------------------------------
        data_quality = {
            "betaSource":    beta_source,
            "marketCapSource": mc_source,
            "debtSource":    td_source,
            "costOfDebtSource": kd_source,
            "taxRateSource": t_source,
        }

        result: Dict[str, Any] = {
            "symbol":       symbol.upper(),
            "companyId":    company_id,
            "currency":     currency,
            "wacc":         round(float(wacc), 4)  if wacc  is not None else None,
            "costOfEquity": round(float(ke), 4)    if ke    is not None else None,
            "costOfDebtAfterTax": round(float(kd_after), 4) if kd_after is not None else None,
            "equityWeight": round(float(eq_weight), 4) if eq_weight is not None else None,
            "debtWeight":   round(float(db_weight), 4) if db_weight is not None else None,
            "betaUsed":     round(float(b), 4)     if b     is not None else None,
            "riskFreeRateUsed": round(float(rf), 4),
            "equityRiskPremiumUsed": round(float(erp), 4),
            "costOfDebtPreTax": round(float(kd), 4) if kd is not None else None,
            "taxRateUsed":  round(float(t), 4)      if t     is not None else None,
            "marketCapUsed": round(float(mc), 2)    if mc    is not None else None,
            "totalDebtUsed": round(float(td), 2)    if td    is not None else None,
            "dataQuality":  data_quality,
            "computedAt":   now_iso(),
        }

        # -- AI narrative ---------------------------------------------------
        if generate_narrative and wacc is not None:
            try:
                narrative = await generate_wacc_roic_narrative(
                    symbol=symbol.upper(),
                    wacc=float(wacc),
                    cost_of_equity=ke,
                    beta=float(b),
                    risk_free_rate=rf,
                    equity_risk_premium=erp,
                    equity_weight=eq_weight,
                    debt_weight=db_weight,
                    cost_of_debt=kd,
                    tax_rate=t,
                )
                result["narrative"] = narrative
            except Exception as exc:
                logger.warning("[WACC] AI narrative generation failed for %s: %s", symbol, exc)
                result["narrative"] = None

        return result

    async def compute_roic_analysis(
        self,
        symbol: str,
        years: int = 5,
        generate_narrative: bool = True,
    ) -> Dict[str, Any]:
        """
        Compute ROIC history and current ROIC for a company.

        Returns a dict with:
          - roicHistory:     list of {fiscalYear, roic}
          - currentRoic:     most recent ROIC (fraction)
          - roicAverage5y:   5-year average ROIC (fraction)
          - roicTrend:       'improving' | 'declining' | 'stable' | 'insufficient_data'
          - narrative:       AI-generated explanation (optional)
          - dataQuality:     metadata
        """
        ctx = await self.repo.get_company_context(symbol)
        if not ctx:
            raise WaccRoicError(f"Symbol '{symbol}' not found in companies.")
        company_id = int(ctx["company_id"])
        currency   = ctx.get("currency") or "USD"

        # -- Fetch ROIC history ---------------------------------------------
        rows = await self.repo.get_roic_history(company_id)

        # Filter to only rows with valid ROIC, sorted by fiscal_year
        valid: List[Dict[str, Any]] = []
        for r in rows:
            fy = r.get("fiscal_year")
            roic_val = safe_float(r.get("roic"))
            if fy is not None and roic_val is not None:
                valid.append({"fiscalYear": int(fy), "roic": float(roic_val)})

        valid.sort(key=lambda x: x["fiscalYear"])

        # Slice to last years entries
        recent = valid[-years:] if len(valid) >= years else valid

        # -- Compute summary ------------------------------------------------
        current_roic = recent[-1]["roic"] if recent else None

        avg_5y = None
        if len(recent) >= 2:
            vals = [r["roic"] for r in recent]
            avg_5y = sum(vals) / len(vals)

        # Trend detection: compare first half vs second half average
        trend = "insufficient_data"
        if len(recent) >= 4:
            mid = len(recent) // 2
            first_half  = [r["roic"] for r in recent[:mid]]
            second_half = [r["roic"] for r in recent[mid:]]
            if first_half and second_half:
                f_avg = sum(first_half) / len(first_half)
                s_avg = sum(second_half) / len(second_half)
                diff  = s_avg - f_avg
                threshold = 0.01  # 1 percentage point
                if diff > threshold:
                    trend = "improving"
                elif diff < -threshold:
                    trend = "declining"
                else:
                    trend = "stable"

        result: Dict[str, Any] = {
            "symbol":         symbol.upper(),
            "companyId":      company_id,
            "currency":       currency,
            "currentRoic":    round(float(current_roic), 4)  if current_roic is not None else None,
            "roicAverage5y":  round(float(avg_5y), 4)        if avg_5y       is not None else None,
            "roicTrend":      trend,
            "roicHistory":    recent,
            "yearsEvaluated": len(recent),
            "dataQuality": {
                "roicSource": "financial_ratios.roic",
                "yearsRequested": years,
                "yearsAvailable": len(valid),
            },
            "computedAt":     now_iso(),
        }

        # -- AI narrative ---------------------------------------------------
        if generate_narrative and current_roic is not None:
            try:
                narrative = await generate_wacc_roic_narrative(
                    symbol=symbol.upper(),
                    roic_current=current_roic,
                    roic_average_5y=avg_5y,
                    roic_trend=trend,
                )
                result["narrative"] = narrative
            except Exception as exc:
                logger.warning("[ROIC] AI narrative generation failed for %s: %s", symbol, exc)
                result["narrative"] = None

        return result

    async def compute_combined_analysis(
        self,
        symbol: str,
        generate_narrative: bool = True,
        **wacc_overrides,
    ) -> Dict[str, Any]:
        """
        Combined WACC + ROIC analysis.
        Returns both results plus a consolidated AI narrative.
        """
        wacc_result = await self.compute_wacc_analysis(
            symbol=symbol,
            generate_narrative=False,  # We'll generate a combined one
            **wacc_overrides,
        )
        roic_result = await self.compute_roic_analysis(
            symbol=symbol,
            generate_narrative=False,
        )

        combined = {
            "symbol":    symbol.upper(),
            "currency":  wacc_result.get("currency"),
            "companyId": wacc_result.get("companyId"),
            "wacc":      wacc_result,
            "roic":      roic_result,
            "spread":    None,
        }

        # Compute spread (ROIC - WACC)
        w = combined["wacc"].get("wacc")
        r = combined["roic"].get("currentRoic")
        if w is not None and r is not None:
            combined["spread"] = round(float(r) - float(w), 4)

        # Generate combined narrative
        if generate_narrative:
            try:
                narrative = await generate_wacc_roic_narrative(
                    symbol=symbol.upper(),
                    wacc=combined["wacc"].get("wacc"),
                    cost_of_equity=combined["wacc"].get("costOfEquity"),
                    beta=combined["wacc"].get("betaUsed"),
                    risk_free_rate=combined["wacc"].get("riskFreeRateUsed"),
                    equity_risk_premium=combined["wacc"].get("equityRiskPremiumUsed"),
                    equity_weight=combined["wacc"].get("equityWeight"),
                    debt_weight=combined["wacc"].get("debtWeight"),
                    cost_of_debt=combined["wacc"].get("costOfDebtPreTax"),
                    tax_rate=combined["wacc"].get("taxRateUsed"),
                    roic_current=combined["roic"].get("currentRoic"),
                    roic_average_5y=combined["roic"].get("roicAverage5y"),
                    roic_trend=combined["roic"].get("roicTrend"),
                    spread=combined.get("spread"),
                )
                combined["narrative"] = narrative
            except Exception as exc:
                logger.warning("[WACC/ROIC] Combined AI narrative failed for %s: %s", symbol, exc)
                combined["narrative"] = None

        return combined