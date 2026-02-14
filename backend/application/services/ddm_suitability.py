# application/services/ddm_suitability.py
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from domain.models.valuation_rule1 import DiagnosticFlag

SECTOR_FIN = {"Financial Services", "Banks", "Insurance", "Diversified Financials"}


@dataclass
class MetricResult:
    code: str
    name: str
    status: str  # pass | caution | fail | na
    points: int  # 1 only if pass
    flag: Optional[DiagnosticFlag] = None


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isfinite(f):
            return f
    except Exception:
        return None
    return None


def _mean(vals: List[float]) -> Optional[float]:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _stdev(vals: List[float]) -> Optional[float]:
    if len(vals) < 2:
        return None
    m = _mean(vals)
    if m is None:
        return None
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var)


def _cagr(v0: float, vN: float, years: int) -> Optional[float]:
    if years <= 0 or v0 <= 0 or vN <= 0:
        return None
    try:
        return (vN / v0) ** (1.0 / years) - 1.0
    except Exception:
        return None


def _points_to_score(points: int, total_possible: int) -> int:
    if total_possible <= 0:
        return 0
    return int(round((points / total_possible) * 100))


def _category_from_passes(passes: int) -> str:
    # 6–7 -> Good (use Gordon)
    # 4–5 -> Caution (use Two-Stage)
    # <=3 -> Poor
    if passes >= 6:
        return "Good"
    if passes >= 4:
        return "Caution"
    return "Poor"


def _recommended_model_from_passes(passes: int) -> str:
    if passes >= 6:
        return "gordon"
    if passes >= 4:
        return "two_stage"
    return "none"


async def evaluate_ddm_suitability(
    repo: Any,
    company_id: int,
    sector: Optional[str],
) -> Tuple[int, str, List[DiagnosticFlag], Dict[str, Any]]:
    """
    Quantitative DDM suitability scorecard (7 metrics).

    Returns:
      score_0_100,
      category ("Good"|"Caution"|"Poor"),
      flags,
      evidence
    """
    dividend_yearly = await repo.get_dividend_yearly_dps(company_id, years=10)  # [{year, dps}]
    div_metrics = await repo.get_dividend_metrics_latest(company_id)
    is_latest = await repo.get_income_statement_latest(company_id)
    bs_latest = await repo.get_balance_sheet_latest(company_id)
    cf_latest = await repo.get_cash_flow_latest(company_id)

    results: List[MetricResult] = []
    flags: List[DiagnosticFlag] = []
    evidence: Dict[str, Any] = {}

    hard_fail = False

    def add(m: MetricResult) -> None:
        results.append(m)
        if m.flag is not None:
            flags.append(m.flag)

    series = sorted(dividend_yearly, key=lambda r: r.get("year", 0))
    last10 = [r for r in series if isinstance(r.get("year"), int)][-10:]
    dps_vals = [_safe_float(r.get("dps")) for r in last10]
    years_vals = [r.get("year") for r in last10]

    # Metric 1: Dividend Payment History (10y)
    paid_years = sum(1 for v in dps_vals if v is not None and v > 0)
    evidence["m1_dividend_paid_years_10y"] = {"paidYears": paid_years, "totalYears": len(last10), "years": years_vals}

    if len(last10) < 5:
        add(MetricResult(
            code="DDM-DIV-HISTORY",
            name="Dividend Payment History (10y)",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-DIV-HISTORY",
                severity="low",
                message="Insufficient dividend history to evaluate 10-year payment consistency.",
                evidence={"availableYears": len(last10)},
            ),
        ))
    else:
        pct = paid_years / max(len(last10), 1)
        if paid_years >= 8:
            add(MetricResult("DDM-DIV-HISTORY", "Dividend Payment History (10y)", "pass", 1))
        elif 5 <= paid_years <= 7:
            add(MetricResult(
                code="DDM-DIV-HISTORY",
                name="Dividend Payment History (10y)",
                status="caution",
                points=0,
                flag=DiagnosticFlag(
                    code="DDM-DIV-HISTORY",
                    severity="medium",
                    message=f"Dividends paid in {paid_years}/{len(last10)} years (={pct:.0%}). Two-stage may be safer.",
                    evidence={"paidYears": paid_years, "totalYears": len(last10), "pct": pct},
                    recommendation="Prefer Two-Stage DDM and validate stability.",
                ),
            ))
        else:
            hard_fail = True
            add(MetricResult(
                code="DDM-DIV-HISTORY",
                name="Dividend Payment History (10y)",
                status="fail",
                points=0,
                flag=DiagnosticFlag(
                    code="DDM-DIV-HISTORY",
                    severity="critical",
                    message=f"Dividends paid in only {paid_years}/{len(last10)} years. DDM not suitable.",
                    evidence={"paidYears": paid_years, "totalYears": len(last10), "pct": pct},
                    recommendation="Avoid DDM; use valuation methods not dependent on dividends.",
                ),
            ))

    # Metric 2: Dividend Stability (volatility)
    vals_clean = [v for v in dps_vals if v is not None and v > 0]
    mu = _mean(vals_clean) if vals_clean else None
    sd = _stdev(vals_clean) if vals_clean else None
    vol = (sd / mu) if (mu and sd is not None and mu != 0) else None
    evidence["m2_dividend_volatility_10y"] = {"mean": mu, "stdev": sd, "volatility": vol}

    if vol is None:
        add(MetricResult(
            code="DDM-DIV-VOL",
            name="Dividend Stability (10y volatility)",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-DIV-VOL",
                severity="low",
                message="Could not compute dividend volatility (insufficient stable dividend series).",
                evidence={"mean": mu, "stdev": sd},
            ),
        ))
    elif vol < 0.25:
        add(MetricResult("DDM-DIV-VOL", "Dividend Stability (10y volatility)", "pass", 1))
    elif vol <= 0.50:
        add(MetricResult(
            code="DDM-DIV-VOL",
            name="Dividend Stability (10y volatility)",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-DIV-VOL",
                severity="medium",
                message=f"Dividend volatility is {vol:.0%} (moderate). Two-stage may be safer.",
                evidence={"volatility": vol},
                recommendation="Prefer Two-Stage DDM and use conservative growth assumptions.",
            ),
        ))
    else:
        hard_fail = True
        add(MetricResult(
            code="DDM-DIV-VOL",
            name="Dividend Stability (10y volatility)",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-DIV-VOL",
                severity="critical",
                message=f"Dividend volatility is {vol:.0%} (unstable). Avoid DDM.",
                evidence={"volatility": vol},
                recommendation="Avoid DDM; dividends are not stable enough for reliable valuation.",
            ),
        ))

    # Metric 3: Earnings payout ratio
    payout_eps = _safe_float(div_metrics.get("dividend_payout_ratio")) if div_metrics else None
    evidence["m3_earnings_payout_ratio"] = payout_eps

    if payout_eps is None:
        add(MetricResult(
            code="DDM-PAYOUT-EPS",
            name="Earnings Payout Ratio",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-PAYOUT-EPS",
                severity="low",
                message="Earnings payout ratio not available (dividend_metrics.dividend_payout_ratio missing).",
            ),
        ))
    else:
        payout = payout_eps / 100.0 if payout_eps > 1.0 else payout_eps
        if payout < 0:
            hard_fail = True
            add(MetricResult(
                "DDM-PAYOUT-EPS",
                "Earnings Payout Ratio",
                "fail",
                0,
                DiagnosticFlag(
                    code="DDM-PAYOUT-EPS",
                    severity="critical",
                    message="Negative payout ratio detected; DDM not suitable.",
                    evidence={"payout": payout},
                ),
            ))
        elif 0.25 <= payout <= 0.70:
            add(MetricResult("DDM-PAYOUT-EPS", "Earnings Payout Ratio", "pass", 1))
        elif 0.70 < payout <= 0.90:
            add(MetricResult(
                "DDM-PAYOUT-EPS",
                "Earnings Payout Ratio",
                "caution",
                0,
                DiagnosticFlag(
                    code="DDM-PAYOUT-EPS",
                    severity="medium",
                    message=f"Earnings payout ratio is {payout:.0%} (high). Use conservative growth.",
                    evidence={"payout": payout},
                    recommendation="Prefer conservative g and/or Two-Stage DDM.",
                ),
            ))
        else:
            hard_fail = True
            add(MetricResult(
                "DDM-PAYOUT-EPS",
                "Earnings Payout Ratio",
                "fail",
                0,
                DiagnosticFlag(
                    code="DDM-PAYOUT-EPS",
                    severity="critical",
                    message=f"Earnings payout ratio is {payout:.0%} (unsustainable). Avoid DDM.",
                    evidence={"payout": payout},
                ),
            ))

    # Metric 4: FCF payout ratio
    fcf_payout = _safe_float(div_metrics.get("fcf_dividend_payout_ratio")) if div_metrics else None
    evidence["m4_fcf_payout_ratio"] = fcf_payout

    if fcf_payout is None:
        add(MetricResult(
            code="DDM-PAYOUT-FCF",
            name="FCF Payout Ratio",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-PAYOUT-FCF",
                severity="low",
                message="FCF payout ratio not available (dividend_metrics.fcf_dividend_payout_ratio missing).",
            ),
        ))
    else:
        payout = fcf_payout / 100.0 if fcf_payout > 1.0 else fcf_payout
        if payout < 0:
            hard_fail = True
            add(MetricResult(
                "DDM-PAYOUT-FCF",
                "FCF Payout Ratio",
                "fail",
                0,
                DiagnosticFlag(
                    code="DDM-PAYOUT-FCF",
                    severity="critical",
                    message="Negative FCF payout ratio detected; avoid DDM.",
                    evidence={"payout": payout},
                ),
            ))
        elif payout < 0.70:
            add(MetricResult("DDM-PAYOUT-FCF", "FCF Payout Ratio", "pass", 1))
        elif payout <= 0.90:
            add(MetricResult(
                "DDM-PAYOUT-FCF",
                "FCF Payout Ratio",
                "caution",
                0,
                DiagnosticFlag(
                    code="DDM-PAYOUT-FCF",
                    severity="medium",
                    message=f"FCF payout ratio is {payout:.0%} (watch).",
                    evidence={"payout": payout},
                    recommendation="Prefer Two-Stage DDM and conservative growth.",
                ),
            ))
        else:
            hard_fail = True
            add(MetricResult(
                "DDM-PAYOUT-FCF",
                "FCF Payout Ratio",
                "fail",
                0,
                DiagnosticFlag(
                    code="DDM-PAYOUT-FCF",
                    severity="critical",
                    message=f"FCF payout ratio is {payout:.0%} (dangerous). Avoid DDM.",
                    evidence={"payout": payout},
                ),
            ))

    # Metric 5: Net Debt to EBITDA
    total_debt = _safe_float(bs_latest.get("total_debt")) if bs_latest else None
    cash = _safe_float(bs_latest.get("cash_and_cash_equivalents")) if bs_latest else None
    ebitda = _safe_float(is_latest.get("ebitda")) if is_latest else None

    net_debt_to_ebitda = None
    if total_debt is not None and cash is not None and ebitda is not None and ebitda != 0:
        net_debt = total_debt - cash
        net_debt_to_ebitda = net_debt / ebitda

    evidence["m5_net_debt_to_ebitda"] = net_debt_to_ebitda

    if net_debt_to_ebitda is None:
        add(MetricResult(
            code="DDM-LEVERAGE",
            name="Net Debt to EBITDA",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-LEVERAGE",
                severity="low",
                message="Could not compute Net Debt / EBITDA (missing debt, cash, or EBITDA).",
                evidence={"totalDebt": total_debt, "cash": cash, "ebitda": ebitda},
            ),
        ))
    elif net_debt_to_ebitda < 3.0:
        add(MetricResult("DDM-LEVERAGE", "Net Debt to EBITDA", "pass", 1))
    elif net_debt_to_ebitda <= 5.0:
        add(MetricResult(
            "DDM-LEVERAGE",
            "Net Debt to EBITDA",
            "caution",
            0,
            DiagnosticFlag(
                code="DDM-LEVERAGE",
                severity="medium",
                message=f"Net Debt / EBITDA is {net_debt_to_ebitda:.1f}x (moderate).",
                evidence={"netDebtToEbitda": net_debt_to_ebitda},
                recommendation="Prefer Two-Stage DDM and conservative growth assumptions.",
            ),
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "DDM-LEVERAGE",
            "Net Debt to EBITDA",
            "fail",
            0,
            DiagnosticFlag(
                code="DDM-LEVERAGE",
                severity="critical",
                message=f"Net Debt / EBITDA is {net_debt_to_ebitda:.1f}x (risky). Avoid DDM.",
                evidence={"netDebtToEbitda": net_debt_to_ebitda},
            ),
        ))

    # Metric 6: Interest coverage
    ebit = _safe_float(is_latest.get("ebit")) if is_latest else None
    interest = _safe_float(is_latest.get("interest_expense")) if is_latest else None
    ic = None
    if ebit is not None and interest is not None and interest != 0:
        ic = ebit / abs(interest)

    evidence["m6_interest_coverage"] = ic

    if ic is None:
        add(MetricResult(
            code="DDM-INT-COV",
            name="Interest Coverage",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-INT-COV",
                severity="low",
                message="Could not compute interest coverage (missing EBIT or interest expense).",
                evidence={"ebit": ebit, "interestExpense": interest},
            ),
        ))
    elif ic > 4.0:
        add(MetricResult("DDM-INT-COV", "Interest Coverage", "pass", 1))
    elif ic >= 2.0:
        add(MetricResult(
            "DDM-INT-COV",
            "Interest Coverage",
            "caution",
            0,
            DiagnosticFlag(
                code="DDM-INT-COV",
                severity="medium",
                message=f"Interest coverage is {ic:.1f}x (caution).",
                evidence={"interestCoverage": ic},
            ),
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "DDM-INT-COV",
            "Interest Coverage",
            "fail",
            0,
            DiagnosticFlag(
                code="DDM-INT-COV",
                severity="critical",
                message=f"Interest coverage is {ic:.1f}x (dangerous). Avoid DDM.",
                evidence={"interestCoverage": ic},
            ),
        ))

    # Metric 7: Dividend CAGR
    g = None
    if len(last10) >= 6:
        v0 = _safe_float(last10[0].get("dps")) or 0.0
        vN = _safe_float(last10[-1].get("dps")) or 0.0
        years_span = (last10[-1]["year"] - last10[0]["year"]) if last10[-1].get("year") and last10[0].get("year") else 0
        if years_span <= 0:
            years_span = len(last10) - 1
        g = _cagr(v0, vN, years_span) if v0 > 0 and vN > 0 else None

    evidence["m7_dividend_cagr"] = g

    if g is None:
        add(MetricResult(
            code="DDM-DIV-CAGR",
            name="Dividend CAGR",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DDM-DIV-CAGR",
                severity="low",
                message="Could not compute dividend CAGR (insufficient annual dividend series).",
            ),
        ))
    elif 0.03 <= g <= 0.10:
        add(MetricResult("DDM-DIV-CAGR", "Dividend CAGR", "pass", 1))
    elif 0.0 <= g < 0.03:
        add(MetricResult(
            "DDM-DIV-CAGR",
            "Dividend CAGR",
            "caution",
            0,
            DiagnosticFlag(
                code="DDM-DIV-CAGR",
                severity="medium",
                message=f"Dividend CAGR is {g:.1%} (low growth).",
                evidence={"dividendCagr": g},
                recommendation="Prefer conservative growth; Two-Stage may be safer.",
            ),
        ))
    elif g < 0.0:
        hard_fail = True
        add(MetricResult(
            "DDM-DIV-CAGR",
            "Dividend CAGR",
            "fail",
            0,
            DiagnosticFlag(
                code="DDM-DIV-CAGR",
                severity="critical",
                message=f"Dividend CAGR is {g:.1%} (shrinking). Avoid DDM.",
                evidence={"dividendCagr": g},
            ),
        ))
    else:
        add(MetricResult(
            "DDM-DIV-CAGR",
            "Dividend CAGR",
            "caution",
            0,
            DiagnosticFlag(
                code="DDM-DIV-CAGR",
                severity="medium",
                message=f"Dividend CAGR is {g:.1%} (high). Prefer Two-Stage DDM.",
                evidence={"dividendCagr": g},
                recommendation="Use Two-Stage with lower stable growth rate.",
            ),
        ))

    total_possible = sum(1 for r in results if r.status != "na")
    passes = sum(r.points for r in results)
    score_0_100 = _points_to_score(passes, total_possible)
    category = _category_from_passes(passes)
    recommended_model = _recommended_model_from_passes(passes)

    evidence["final_scoring"] = {
        "passes": passes,
        "totalPossible": total_possible,
        "score0to100": score_0_100,
        "category": category,
        "recommendedModel": recommended_model,
        "hardFail": hard_fail,
        "asOf": date.today().isoformat(),
    }

    flags.insert(0, DiagnosticFlag(
        code="DDM-SCORECARD",
        severity="info",
        message=f"DDM suitability: {passes}/{total_possible} passes (mapped to {score_0_100}/100). Recommended: {recommended_model}.",
        evidence=evidence["final_scoring"],
        recommendation="Use suitability diagnostics to decide whether Gordon or Two-Stage is appropriate.",
    ))

    return score_0_100, category, flags, evidence