from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from domain.models.valuation_rule1 import DiagnosticFlag
from shared.time_utils import now_iso


@dataclass
class MetricResult:
    code: str
    name: str
    status: str  # pass | caution | fail | na
    points: int  # 1 only if pass
    flag: DiagnosticFlag | None = None


# -------------------------------
# Helpers (safe math, no assumptions)
# -------------------------------

def _safe_float(x: Any) -> float | None:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isfinite(f):
            return f
    except Exception:
        return None
    return None


def _mean(vals: list[float]) -> float | None:
    if not vals:
        return None
    return sum(vals) / len(vals)


def _stdev(vals: list[float]) -> float | None:
    if len(vals) < 2:
        return None
    m = _mean(vals)
    if m is None:
        return None
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return math.sqrt(var)


def _cagr(v0: float, vN: float, years: int) -> float | None:
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
    # As per your decision tree:
    # 6–7 => Strong
    # 4–5 => Caution
    # <=3 => Avoid
    if passes >= 6:
        return "Good"
    if passes >= 4:
        return "Caution"
    return "Poor"


async def evaluate_dcf_suitability(
    repo: Any,
    company_id: int,
    sector: str | None,
) -> tuple[int, str, list[DiagnosticFlag], dict[str, Any]]:
    """
    Quantitative DCF suitability scorecard (7 metrics), per provided decision tree.

    Returns:
      score_0_100,
      category ("Good"|"Caution"|"Poor"),
      flags,
      evidence

    IMPORTANT:
    - No direct DB access here; repository provides inputs.
    - If required history is not available, metric becomes caution/na with explicit flag.
    """

    results: list[MetricResult] = []
    flags: list[DiagnosticFlag] = []
    evidence: dict[str, Any] = {}
    coverage: dict[str, Any] = {}

    def add(m: MetricResult) -> None:
        results.append(m)
        if m.flag is not None:
            flags.append(m.flag)

    # -------------------------------
    # Pull data (repository only)
    # -------------------------------
    # 5y series are required for multiple metrics. Repository may or may not expose these helpers yet.
    # We guard with hasattr to avoid runtime failures and mark metrics as "na" when missing.
    fcf_series: list[dict[str, Any]] = []
    if hasattr(repo, "get_fcf_history"):
        try:
            # expected: [{fiscal_year, fcf}]
            fcf_series = await repo.get_fcf_history(company_id, years=5)
        except Exception:
            fcf_series = []
    else:
        fcf_series = []

    rev_series = []
    try:
        # existing repo method returns annual series; we slice last 5
        rev_series = await repo.get_revenue_history(company_id)
    except Exception:
        rev_series = []

    is_latest = None
    bs_latest = None
    cf_latest = None
    try:
        is_latest = await repo.get_income_statement_latest(company_id)
    except Exception:
        is_latest = None
    try:
        bs_latest = await repo.get_balance_sheet_latest(company_id)
    except Exception:
        bs_latest = None
    try:
        cf_latest = await repo.get_cash_flow_latest(company_id)
    except Exception:
        cf_latest = None

    # -------------------------------
    # Metric 1: FCF positivity (5y)
    # -------------------------------
    # FCF = OCF - Capex (already computed in fcf_series if available)
    fcf_rows_all = sorted(
        [r for r in (fcf_series or []) if r.get("fiscal_year") is not None],
        key=lambda r: int(r.get("fiscal_year") or 0),
    )
    # Use up-to-5 most recent years (do not under-sample if more data exists)
    fcf_rows = fcf_rows_all[-5:]

    fcf_vals = [_safe_float(r.get("fcf")) for r in fcf_rows]
    years_vals = [r.get("fiscal_year") for r in fcf_rows]

    pos_count = sum(1 for v in fcf_vals if v is not None and v > 0)
    evidence["m1_fcf_positivity_5y"] = {"positiveYears": pos_count, "yearsEvaluated": len(fcf_rows),
        "years": years_vals}
    coverage["DCF-FCF-POS"] = {"requiredYears": 5, "availableYears": len(fcf_rows), "positiveYears": pos_count}

    if len(fcf_rows) < 3:
        add(MetricResult(
            code="DCF-FCF-POS",
            name="FCF Positivity (5y)",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-FCF-POS",
                severity="low",
                message="Insufficient FCF history to evaluate 5-year positivity.",
                evidence={"availableYears": len(fcf_rows)},
            ),
        ))
    else:
        pct = pos_count / max(len(fcf_rows), 1)
        if pos_count >= 4:
            add(MetricResult("DCF-FCF-POS", "FCF Positivity (5y)", "pass", 1))
        elif 2 <= pos_count <= 3:
            add(MetricResult(
                code="DCF-FCF-POS",
                name="FCF Positivity (5y)",
                status="caution",
                points=0,
                flag=DiagnosticFlag(
                    code="DCF-FCF-POS",
                    severity="medium",
                    message=f"FCF is positive in {pos_count}/{len(fcf_rows)} years (={pct:.0%}). Consider normalization / conservatism.",
                    evidence={"positiveYears": pos_count, "totalYears": len(fcf_rows), "pct": pct},
                    recommendation="Use conservative forecast assumptions; validate underlying cash flow drivers.",
                ),
            ))
        else:
            add(MetricResult(
                code="DCF-FCF-POS",
                name="FCF Positivity (5y)",
                status="fail",
                points=0,
                flag=DiagnosticFlag(
                    code="DCF-FCF-POS",
                    severity="critical",
                    message=f"FCF is positive in only {pos_count}/{len(fcf_rows)} years. DCF may not be suitable.",
                    evidence={"positiveYears": pos_count, "totalYears": len(fcf_rows), "pct": pct},
                    recommendation="Avoid DCF unless you can justify stable forward cash flows; consider other methods.",
                ),
            ))

    # -------------------------------
    # Metric 2: FCF volatility = stdev / mean
    # -------------------------------
    fcf_clean = [v for v in fcf_vals if v is not None]
    mu = _mean(fcf_clean)
    sd = _stdev(fcf_clean)
    # IMPORTANT:
    # - Volatility should never "pass" due to negative mean.
    # - Use abs(mean) in denominator; treat non-positive mean as a suitability failure.
    vol = (sd / abs(mu)) if (mu is not None and sd is not None and mu != 0) else None
    evidence["m2_fcf_volatility"] = {"mean": mu, "stdev": sd, "volatility": vol}
    coverage["DCF-FCF-VOL"] = {"requiredYears": 5, "availablePoints": len(fcf_clean)}

    if mu is not None and mu <= 0:
        add(MetricResult(
            code="DCF-FCF-VOL",
            name="FCF Volatility (5y)",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-FCF-VOL",
                severity="critical",
                message="Average FCF is non-positive over the available period; volatility test is not reliable and DCF may be unsuitable.",
                evidence={"mean": mu, "stdev": sd, "volatility": vol},
                recommendation="Avoid DCF unless forward cash flows are clearly expected to become stable and positive.",
            ),
        ))
    elif vol is None:
        add(MetricResult(
            code="DCF-FCF-VOL",
            name="FCF Volatility (5y)",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-FCF-VOL",
                severity="low",
                message="Could not compute FCF volatility (insufficient or zero-mean series).",
                evidence={"mean": mu, "stdev": sd},
            ),
        ))
    elif vol < 0.40:
        add(MetricResult("DCF-FCF-VOL", "FCF Volatility (5y)", "pass", 1))
    elif vol <= 0.80:
        add(MetricResult(
            code="DCF-FCF-VOL",
            name="FCF Volatility (5y)",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-FCF-VOL",
                severity="medium",
                message=f"FCF volatility is {vol:.0%} (moderate). Use conservative assumptions.",
                evidence={"volatility": vol},
            ),
        ))
    else:
        add(MetricResult(
            code="DCF-FCF-VOL",
            name="FCF Volatility (5y)",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-FCF-VOL",
                severity="critical",
                message=f"FCF volatility is {vol:.0%} (high). DCF may be unreliable.",
                evidence={"volatility": vol},
                recommendation="Avoid DCF or use a wide sensitivity range and conservative terminal assumptions.",
            ),
        ))

    # -------------------------------
    # Metric 3: Revenue CAGR (5y)
    # -------------------------------
    # 5-year CAGR requires 6 points (years+1). Use last 6 annual rows.
    # Option: compute over actual span when >=2 points exist and
    # emit an info diagnostic when span != 5y so UI can explain gaps.
    rev_rows_all = sorted(
        [r for r in (rev_series or []) if r.get("fiscal_year") is not None],
        key=lambda r: int(r.get("fiscal_year") or 0),
    )
    rev_rows = rev_rows_all[-6:] if len(rev_rows_all) >= 6 else rev_rows_all[-len(rev_rows_all):]
    rev_vals = [_safe_float(r.get("revenue")) for r in rev_rows]
    rev_years = [r.get("fiscal_year") for r in rev_rows]
    evidence["m3_revenue_cagr_5y"] = {"years": rev_years, "values": rev_vals}

    rev_cagr = None
    years_span: int | None = None
    if len(rev_rows) >= 2:
        v0 = _safe_float(rev_rows[0].get("revenue"))
        vN = _safe_float(rev_rows[-1].get("revenue"))
        try:
            years_span = int(rev_rows[-1]["fiscal_year"]) - int(rev_rows[0]["fiscal_year"])
        except Exception:
            years_span = None
        if v0 is not None and vN is not None and years_span is not None and years_span > 0:
            rev_cagr = _cagr(v0, vN, years_span)

    evidence["m3_revenue_cagr_5y"]["cagr"] = rev_cagr
    evidence["m3_revenue_cagr_5y"]["spanYears"] = years_span
    coverage["DCF-REV-CAGR"] = {"targetYears": 5, "availableYears": len(rev_rows), "spanYears": years_span}

    span_flag_m3: DiagnosticFlag | None = None
    if rev_cagr is not None and years_span is not None and years_span != 5:
        span_flag_m3 = DiagnosticFlag(
            code="DCF-REV-CAGR-SPAN",
            severity="info",
            message=f"Revenue CAGR computed over {years_span}y span (target 5y) due to missing fiscal years.",
            evidence=evidence["m3_revenue_cagr_5y"],
            recommendation="Backfill missing fiscal years for a true 5-year CAGR.",
        )

    if rev_cagr is None:
        add(MetricResult(
            code="DCF-REV-CAGR",
            name="Revenue CAGR (5y)",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-REV-CAGR",
                severity="low",
                message="Could not compute revenue CAGR (insufficient revenue history).",
                evidence={"availableYears": len(rev_rows), "spanYears": years_span, "years": rev_years},
            ),
        ))
    elif rev_cagr >= 0.04:
        add(MetricResult("DCF-REV-CAGR", "Revenue CAGR (5y)", "pass", 1, span_flag_m3))
    elif 0.0 <= rev_cagr < 0.04:
        add(MetricResult(
            code="DCF-REV-CAGR",
            name="Revenue CAGR (5y)",
            status="caution",
            points=0,
            flag=span_flag_m3 or DiagnosticFlag(
                code="DCF-REV-CAGR",
                severity="medium",
                message=f"Revenue CAGR is {rev_cagr:.1%} (slow growth).",
                evidence={"revenueCagr": rev_cagr},
                recommendation="Use conservative growth and terminal assumptions.",
            ),
        ))
    else:
        add(MetricResult(
            code="DCF-REV-CAGR",
            name="Revenue CAGR (5y)",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-REV-CAGR",
                severity="critical",
                message=f"Revenue CAGR is {rev_cagr:.1%} (declining). Avoid DCF unless turnaround is well-supported.",
                evidence={"revenueCagr": rev_cagr},
            ),
        ))

    # -------------------------------
    # Metric 4: Revenue volatility (StdDev of YoY growth)
    # -------------------------------
    yoy: list[float] = []
    for i in range(1, len(rev_rows)):
        prev = _safe_float(rev_rows[i - 1].get("revenue"))
        cur = _safe_float(rev_rows[i].get("revenue"))
        if prev is None or cur is None or prev == 0:
            continue
        yoy.append((cur - prev) / prev)

    rv_sd = _stdev(yoy)
    evidence["m4_revenue_volatility"] = {"yoyGrowth": yoy, "stdev": rv_sd}

    if rv_sd is None:
        add(MetricResult(
            code="DCF-REV-VOL",
            name="Revenue Volatility (StdDev YoY)",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-REV-VOL",
                severity="low",
                message="Could not compute revenue volatility (insufficient YoY growth series).",
                evidence={"yoyPoints": len(yoy)},
            ),
        ))
    elif rv_sd < 0.10:
        add(MetricResult("DCF-REV-VOL", "Revenue Volatility (StdDev YoY)", "pass", 1))
    elif rv_sd <= 0.20:
        add(MetricResult(
            code="DCF-REV-VOL",
            name="Revenue Volatility (StdDev YoY)",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-REV-VOL",
                severity="medium",
                message=f"Revenue growth volatility is {rv_sd:.0%} (moderate).",
                evidence={"revenueVolatility": rv_sd},
                recommendation="Use conservative forecasts and consider wider sensitivity bands.",
            ),
        ))
    else:
        add(MetricResult(
            code="DCF-REV-VOL",
            name="Revenue Volatility (StdDev YoY)",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-REV-VOL",
                severity="critical",
                message=f"Revenue growth volatility is {rv_sd:.0%} (unstable). DCF may be unreliable.",
                evidence={"revenueVolatility": rv_sd},
            ),
        ))

    # -------------------------------
    # Metric 5: Net Debt / EBITDA
    # -------------------------------
    total_debt = _safe_float(bs_latest.get("total_debt")) if bs_latest else None
    cash = _safe_float(bs_latest.get("cash_and_cash_equivalents")) if bs_latest else None
    ebitda = _safe_float(is_latest.get("ebitda")) if is_latest else None

    nd_to_ebitda = None
    # IMPORTANT:
    # - ND/EBITDA is only meaningful when EBITDA > 0.
    # - Negative or zero EBITDA should not "pass" by producing a negative ratio.
    if total_debt is not None and cash is not None and ebitda is not None and ebitda > 0:
        nd = total_debt - cash
        nd_to_ebitda = nd / ebitda

    evidence["m5_net_debt_to_ebitda"] = {
        "totalDebt": total_debt,
        "cash": cash,
        "ebitda": ebitda,
        "netDebtToEbitda": nd_to_ebitda,
    }

    if ebitda is not None and ebitda <= 0:
        add(MetricResult(
            code="DCF-LEVERAGE",
            name="Net Debt / EBITDA",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-LEVERAGE",
                severity="critical",
                message="EBITDA is non-positive; leverage ratio is not meaningful and balance-sheet risk is elevated for DCF.",
                evidence=evidence["m5_net_debt_to_ebitda"],
                recommendation="Avoid DCF unless profitability and cash generation normalize; consider alternative valuation methods.",
            ),
        ))
    elif nd_to_ebitda is None:

        add(MetricResult(
            code="DCF-LEVERAGE",
            name="Net Debt / EBITDA",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-LEVERAGE",
                severity="low",
                message="Could not compute Net Debt / EBITDA (missing debt, cash, or EBITDA).",
                evidence=evidence["m5_net_debt_to_ebitda"],
            ),
        ))
    elif nd_to_ebitda < 3.0:
        add(MetricResult("DCF-LEVERAGE", "Net Debt / EBITDA", "pass", 1))
    elif nd_to_ebitda <= 5.0:
        add(MetricResult(
            code="DCF-LEVERAGE",
            name="Net Debt / EBITDA",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-LEVERAGE",
                severity="medium",
                message=f"Net Debt / EBITDA is {nd_to_ebitda:.1f}x (moderate).",
                evidence={"netDebtToEbitda": nd_to_ebitda},
                recommendation="Use conservative assumptions; validate debt serviceability.",
            ),
        ))
    else:
        add(MetricResult(
            code="DCF-LEVERAGE",
            name="Net Debt / EBITDA",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-LEVERAGE",
                severity="critical",
                message=f"Net Debt / EBITDA is {nd_to_ebitda:.1f}x (risky). Avoid DCF unless leverage normalizes.",
                evidence={"netDebtToEbitda": nd_to_ebitda},
            ),
        ))

    # -------------------------------
    # Metric 6: Interest Coverage (EBIT / Interest)
    # -------------------------------
    ebit = _safe_float(is_latest.get("ebit")) if is_latest else None
    interest = _safe_float(is_latest.get("interest_expense")) if is_latest else None
    ic = None
    if ebit is not None and interest is not None:
        if interest == 0:
            ic = math.inf if ebit > 0 else None
        else:
            ic = ebit / abs(interest)

    evidence["m6_interest_coverage"] = {"ebit": ebit, "interestExpense": interest, "interestCoverage": ic}
    coverage["DCF-INT-COV"] = {"ebit": ebit, "interestExpense": interest}

    if interest == 0 and ebit is not None and ebit > 0:
        add(MetricResult("DCF-INT-COV", "Interest Coverage", "pass", 1))
    elif ic is None:
        add(MetricResult(
            code="DCF-INT-COV",
            name="Interest Coverage",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-INT-COV",
                severity="low",
                message="Could not compute interest coverage (missing EBIT or interest expense).",
                evidence=evidence["m6_interest_coverage"],
            ),
        ))
    elif ic > 4.0:
        add(MetricResult("DCF-INT-COV", "Interest Coverage", "pass", 1))
    elif ic >= 2.0:
        add(MetricResult(
            code="DCF-INT-COV",
            name="Interest Coverage",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-INT-COV",
                severity="medium",
                message=f"Interest coverage is {ic:.1f}x (watch).",
                evidence={"interestCoverage": ic},
                recommendation="Use conservative assumptions; verify cash flow resilience.",
            ),
        ))
    else:
        add(MetricResult(
            code="DCF-INT-COV",
            name="Interest Coverage",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-INT-COV",
                severity="critical",
                message=f"Interest coverage is {ic:.1f}x (dangerous). Avoid DCF unless financing risk is addressed.",
                evidence={"interestCoverage": ic},
            ),
        ))

    # -------------------------------
    # Metric 7: Capex / Revenue (5y avg)
    # -------------------------------
    # This requires capex history. If repo does not expose it yet, fall back to "na".
    capex_ratio = None
    if hasattr(repo, "get_capex_and_revenue_history"):
        try:
            # expected: [{fiscal_year, capex, revenue}]
            cr = await repo.get_capex_and_revenue_history(company_id, years=5)
            ratios: list[float] = []
            for r in (cr or []):
                cap = _safe_float(r.get("capex"))
                rev = _safe_float(r.get("revenue"))
                if cap is None or rev is None or rev == 0:
                    continue
                ratios.append(abs(cap) / rev)
            capex_ratio = _mean(ratios) if ratios else None
            evidence["m7_capex_to_revenue"] = {"ratios": ratios, "avg": capex_ratio}
        except Exception:
            capex_ratio = None
    else:
        evidence["m7_capex_to_revenue"] = {"note": "repo helper missing (get_capex_and_revenue_history)"}

    if capex_ratio is None:
        add(MetricResult(
            code="DCF-CAPINT",
            name="Capex / Revenue (5y avg)",
            status="na",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-CAPINT",
                severity="low",
                message="Could not compute Capex / Revenue (missing capex/revenue history helper).",
                evidence=evidence.get("m7_capex_to_revenue"),
            ),
        ))
    elif capex_ratio < 0.08:
        add(MetricResult("DCF-CAPINT", "Capex / Revenue (5y avg)", "pass", 1))
    elif capex_ratio <= 0.15:
        add(MetricResult(
            code="DCF-CAPINT",
            name="Capex / Revenue (5y avg)",
            status="caution",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-CAPINT",
                severity="medium",
                message=f"Capex / Revenue is {capex_ratio:.0%} (moderate).",
                evidence={"capexToRevenue": capex_ratio},
                recommendation="Use conservative reinvestment assumptions and terminal growth.",
            ),
        ))
    else:
        add(MetricResult(
            code="DCF-CAPINT",
            name="Capex / Revenue (5y avg)",
            status="fail",
            points=0,
            flag=DiagnosticFlag(
                code="DCF-CAPINT",
                severity="critical",
                message=f"Capex / Revenue is {capex_ratio:.0%} (high). DCF requires caution.",
                evidence={"capexToRevenue": capex_ratio},
                recommendation="Use conservative assumptions; validate reinvestment needs explicitly.",
            ),
        ))

    # -------------------------------
    # Final scoring
    # -------------------------------
    # IMPORTANT:
    # Do not inflate the score when metrics are NA.
    # Use fixed denominator = 7 metrics (per decision tree).
    total_possible = 7
    passes = sum(r.points for r in results)
    score_0_100 = _points_to_score(passes, total_possible)
    category = _category_from_passes(passes)

    evidence["final_scoring"] = {
        "passes": passes,
        "totalPossible": total_possible,
        "score0to100": score_0_100,
        "category": category,
        "asOf": now_iso(),
        "sector": sector,
    }

    # UI-friendly missing-data summary (does not affect score/category)
    evidence["data_coverage"] = coverage
    flags.insert(0, DiagnosticFlag(
        code="DCF-DATA-COVERAGE",
        severity="info",
        message="DCF suitability data coverage summary (missing inputs may reduce confidence).",
        evidence=coverage,
        recommendation="Improve data completeness for higher-confidence suitability metrics.",
    ))

    flags.insert(0, DiagnosticFlag(
        code="DCF-SCORECARD",
        severity="info",
        message=f"DCF suitability: {passes}/{total_possible} passes (mapped to {score_0_100}/100).",
        evidence=evidence["final_scoring"],
        recommendation="Use suitability diagnostics to decide whether DCF is appropriate and how conservative assumptions should be.",
    ))

    return score_0_100, category, flags, evidence
