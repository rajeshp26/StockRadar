# application/services/owner_earnings_suitability.py
from __future__ import annotations
import math
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from domain.models.valuation_rule1 import DiagnosticFlag


@dataclass
class MetricResult:
    code: str
    name: str
    status: str   # pass | caution | fail | na
    points: int   # 1 only if pass
    flag: Optional[DiagnosticFlag] = None


# ── Helpers (local copies — do NOT import from other services to preserve isolation) ─

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
    return sum(vals) / len(vals) if vals else None


def _stdev(vals: List[float]) -> Optional[float]:
    if len(vals) < 2:
        return None
    m = _mean(vals)
    if m is None:
        return None
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


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
    # Consistent with DCF / DDM scorecards
    if passes >= 6:
        return "Good"
    if passes >= 4:
        return "Caution"
    return "Poor"


# ── Scorecard ─────────────────────────────────────────────────────────────────

async def evaluate_owner_earnings_suitability(
    repo: Any,
    company_id: int,
    sector: Optional[str],
) -> Tuple[int, str, List[DiagnosticFlag], Dict[str, Any]]:
    """
    7-metric Owner Earnings suitability scorecard.

    Returns:
        score_0_100, category ("Good"|"Caution"|"Poor"), flags, evidence

    Data sources (all via repo methods, never direct DB):
    - OE history: repo.get_owner_earnings_history (NI + D&A − |Capex|, per year)
    - Revenue: repo.get_revenue_history (for OE margin metric)
    - Capex + D&A: repo.get_capex_da_history (for capital intensity metric)
    - Balance sheet: repo.get_balance_sheet_latest
    - Income statement: repo.get_income_statement_latest
    - ROIC history: repo.get_roic_history
    """
    results: List[MetricResult] = []
    flags: List[DiagnosticFlag] = []
    evidence: Dict[str, Any] = {}
    coverage: Dict[str, Any] = {}

    def add(m: MetricResult) -> None:
        results.append(m)
        if m.flag is not None:
            flags.append(m.flag)

    # ── Fetch data ────────────────────────────────────────────────────────────

    oe_series: List[Dict[str, Any]] = []
    if hasattr(repo, "get_annual_owner_earnings"):
        try:
            oe_series = await repo.get_annual_owner_earnings(company_id, years=5)
        except Exception:
            oe_series = []

    rev_series: List[Dict[str, Any]] = []
    try:
        rev_series = await repo.get_revenue_history(company_id)
    except Exception:
        rev_series = []

    capex_da_series: List[Dict[str, Any]] = []
    if hasattr(repo, "get_capex_da_history"):
        try:
            capex_da_series = await repo.get_capex_da_history(company_id, years=5)
        except Exception:
            capex_da_series = []

    bs_latest: Optional[Dict[str, Any]] = None
    is_latest: Optional[Dict[str, Any]] = None
    try:
        bs_latest = await repo.get_balance_sheet_latest(company_id)
    except Exception:
        pass
    try:
        is_latest = await repo.get_income_statement_latest(company_id)
    except Exception:
        pass

    roic_rows: List[Dict[str, Any]] = []
    try:
        roic_rows = await repo.get_roic_history(company_id)
    except Exception:
        pass

    # ── Sort and slice OE series (most recent 5 years) ────────────────────────

    oe_rows = sorted(
        [r for r in oe_series if r.get("fiscal_year") is not None],
        key=lambda r: int(r.get("fiscal_year") or 0),
    )[-5:]
    oe_vals = [_safe_float(r.get("oe")) for r in oe_rows]
    oe_years = [r.get("fiscal_year") for r in oe_rows]

    # ── Metric 1: OE Positivity (5y) ─────────────────────────────────────────

    pos_count = sum(1 for v in oe_vals if v is not None and v > 0)
    evidence["m1_oe_positivity"] = {"positiveYears": pos_count, "totalYears": len(oe_rows), "years": oe_years}
    coverage["OE-POS"] = {"requiredYears": 5, "availableYears": len(oe_rows)}

    if len(oe_rows) < 3:
        add(MetricResult(
            code="OE-POS", name="OE Positivity (5y)", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-POS", severity="low",
                message="Insufficient Owner Earnings history for 5-year positivity check.",
                evidence={"availableYears": len(oe_rows)},
            ),
        ))
    else:
        pct = pos_count / max(len(oe_rows), 1)
        if pos_count >= 4:
            add(MetricResult("OE-POS", "OE Positivity (5y)", "pass", 1))
        elif 2 <= pos_count <= 3:
            add(MetricResult(
                code="OE-POS", name="OE Positivity (5y)", status="caution", points=0,
                flag=DiagnosticFlag(
                    code="OE-POS", severity="medium",
                    message=f"Owner Earnings positive in {pos_count}/{len(oe_rows)} years ({pct:.0%}). Use conservative assumptions.",
                    evidence={"positiveYears": pos_count, "totalYears": len(oe_rows)},
                    recommendation="Apply conservative growth; validate normalised earnings power.",
                ),
            ))
        else:
            add(MetricResult(
                code="OE-POS", name="OE Positivity (5y)", status="fail", points=0,
                flag=DiagnosticFlag(
                    code="OE-POS", severity="critical",
                    message=f"Owner Earnings positive in only {pos_count}/{len(oe_rows)} years. OE method not suitable.",
                    evidence={"positiveYears": pos_count, "totalYears": len(oe_rows)},
                    recommendation="Avoid Owner Earnings model; company lacks consistent earnings power.",
                ),
            ))

    # ── Metric 2: OE Volatility (StdDev / |Mean|, 5y) ────────────────────────

    oe_clean = [v for v in oe_vals if v is not None]
    mu_oe = _mean(oe_clean)
    sd_oe = _stdev(oe_clean)
    vol_oe = (sd_oe / abs(mu_oe)) if (mu_oe is not None and sd_oe is not None and mu_oe != 0) else None
    evidence["m2_oe_volatility"] = {"mean": mu_oe, "stdev": sd_oe, "volatility": vol_oe}

    if mu_oe is not None and mu_oe <= 0:
        add(MetricResult(
            code="OE-VOL", name="OE Volatility (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-VOL", severity="critical",
                message="Average Owner Earnings is non-positive; the business does not generate reliable economic profit.",
                evidence={"mean": mu_oe, "stdev": sd_oe},
                recommendation="Avoid OE model; stabilise earnings before applying this method.",
            ),
        ))
    elif vol_oe is None:
        add(MetricResult(
            code="OE-VOL", name="OE Volatility (5y)", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-VOL", severity="low",
                message="Could not compute OE volatility (insufficient or zero-mean series).",
                evidence={"mean": mu_oe, "stdev": sd_oe},
            ),
        ))
    elif vol_oe < 0.40:
        add(MetricResult("OE-VOL", "OE Volatility (5y)", "pass", 1))
    elif vol_oe <= 0.80:
        add(MetricResult(
            code="OE-VOL", name="OE Volatility (5y)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="OE-VOL", severity="medium",
                message=f"OE volatility is {vol_oe:.0%} (moderate). Use conservative growth assumptions.",
                evidence={"volatility": vol_oe},
            ),
        ))
    else:
        add(MetricResult(
            code="OE-VOL", name="OE Volatility (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-VOL", severity="critical",
                message=f"OE volatility is {vol_oe:.0%} (high). Owner Earnings model may be unreliable.",
                evidence={"volatility": vol_oe},
                recommendation="Use DCF with scenario ranges or apply a wide margin of safety.",
            ),
        ))

    # ── Metric 3: OE Margin (OE / Revenue, 5y avg) ───────────────────────────

    rev_by_year: Dict[int, Optional[float]] = {}
    for r in rev_series:
        y = r.get("fiscal_year")
        v = _safe_float(r.get("revenue"))
        if isinstance(y, int):
            rev_by_year[y] = v

    oe_margins: List[float] = []
    for r in oe_rows:
        y = r.get("fiscal_year")
        oe_v = _safe_float(r.get("oe"))
        rev_v = rev_by_year.get(y) if isinstance(y, int) else None
        if oe_v is not None and rev_v is not None and rev_v > 0:
            oe_margins.append(oe_v / rev_v)

    oe_margin_avg = _mean(oe_margins)
    evidence["m3_oe_margin"] = {"margins5y": oe_margins, "avg": oe_margin_avg}

    if oe_margin_avg is None:
        add(MetricResult(
            code="OE-MARGIN", name="OE Margin (5y avg)", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-MARGIN", severity="low",
                message="Could not compute OE margin (missing OE or revenue history).",
                evidence={"availablePoints": len(oe_margins)},
            ),
        ))
    elif oe_margin_avg >= 0.05:
        add(MetricResult("OE-MARGIN", "OE Margin (5y avg)", "pass", 1))
    elif oe_margin_avg >= 0.0:
        add(MetricResult(
            code="OE-MARGIN", name="OE Margin (5y avg)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="OE-MARGIN", severity="medium",
                message=f"OE margin is {oe_margin_avg:.1%} (thin). Business may have limited economic moat.",
                evidence={"oeMarginAvg": oe_margin_avg},
                recommendation="Validate competitive advantage and use conservative terminal assumptions.",
            ),
        ))
    else:
        add(MetricResult(
            code="OE-MARGIN", name="OE Margin (5y avg)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-MARGIN", severity="critical",
                message=f"OE margin is {oe_margin_avg:.1%} (negative). Avoid OE model.",
                evidence={"oeMarginAvg": oe_margin_avg},
            ),
        ))

    # ── Metric 4: OE CAGR (5y) ───────────────────────────────────────────────

    oe_cagr: Optional[float] = None
    years_span_oe: Optional[int] = None
    if len(oe_rows) >= 2:
        v0_oe = _safe_float(oe_rows[0].get("oe"))
        vN_oe = _safe_float(oe_rows[-1].get("oe"))
        try:
            years_span_oe = int(oe_rows[-1]["fiscal_year"]) - int(oe_rows[0]["fiscal_year"])
        except Exception:
            years_span_oe = None
        if v0_oe and vN_oe and years_span_oe and years_span_oe > 0:
            oe_cagr = _cagr(v0_oe, vN_oe, years_span_oe)

    evidence["m4_oe_cagr"] = {"cagr": oe_cagr, "spanYears": years_span_oe}

    if oe_cagr is None:
        add(MetricResult(
            code="OE-CAGR", name="OE CAGR (5y)", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-CAGR", severity="low",
                message="Could not compute OE CAGR (insufficient history or non-positive endpoints).",
                evidence=evidence["m4_oe_cagr"],
            ),
        ))
    elif oe_cagr >= 0.04:
        add(MetricResult("OE-CAGR", "OE CAGR (5y)", "pass", 1))
    elif oe_cagr >= 0.0:
        add(MetricResult(
            code="OE-CAGR", name="OE CAGR (5y)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="OE-CAGR", severity="medium",
                message=f"OE CAGR is {oe_cagr:.1%} (slow). Use conservative growth assumptions.",
                evidence={"oeCagr": oe_cagr},
            ),
        ))
    else:
        add(MetricResult(
            code="OE-CAGR", name="OE CAGR (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-CAGR", severity="critical",
                message=f"OE CAGR is {oe_cagr:.1%} (declining). OE model is not suitable.",
                evidence={"oeCagr": oe_cagr},
                recommendation="Avoid OE model unless turnaround is clearly evidenced.",
            ),
        ))

    # ── Metric 5: Capex / D&A ratio (5y avg) ─────────────────────────────────
    # Measures capital intensity relative to depreciation.
    # High ratio → company needs more capex than it depreciates → high reinvestment burden.
    # Rule-of-thumb: < 1.5× is capital-light (Buffett preferred); > 3× is capital-heavy.

    capex_da_ratios: List[float] = []
    for r in capex_da_series:
        capex_v = _safe_float(r.get("capex"))
        da_v = _safe_float(r.get("da"))
        if capex_v is not None and da_v is not None and da_v > 0:
            capex_da_ratios.append(abs(capex_v) / da_v)

    capex_da_avg = _mean(capex_da_ratios)
    evidence["m5_capex_da_ratio"] = {"ratios": capex_da_ratios, "avg": capex_da_avg}

    if capex_da_avg is None:
        add(MetricResult(
            code="OE-CAPEX-DA", name="Capex / D&A (5y avg)", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-CAPEX-DA", severity="low",
                message="Could not compute Capex/D&A ratio (missing capex or D&A history).",
                evidence={"availablePoints": len(capex_da_ratios)},
            ),
        ))
    elif capex_da_avg < 1.5:
        add(MetricResult("OE-CAPEX-DA", "Capex / D&A (5y avg)", "pass", 1))
    elif capex_da_avg <= 3.0:
        add(MetricResult(
            code="OE-CAPEX-DA", name="Capex / D&A (5y avg)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="OE-CAPEX-DA", severity="medium",
                message=f"Capex/D&A ratio is {capex_da_avg:.1f}× (moderate capital intensity).",
                evidence={"capexDaRatioAvg": capex_da_avg},
                recommendation="Use conservative maintenance capex assumptions; validate moat.",
            ),
        ))
    else:
        add(MetricResult(
            code="OE-CAPEX-DA", name="Capex / D&A (5y avg)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-CAPEX-DA", severity="critical",
                message=f"Capex/D&A ratio is {capex_da_avg:.1f}× (high capital intensity). OE assumptions are sensitive.",
                evidence={"capexDaRatioAvg": capex_da_avg},
                recommendation="Split total capex into maintenance vs. growth before applying OE model.",
            ),
        ))

    # ── Metric 6: Net Debt / EBITDA (balance sheet health) ───────────────────

    total_debt = _safe_float(bs_latest.get("total_debt")) if bs_latest else None
    cash = _safe_float(bs_latest.get("cash_and_cash_equivalents")) if bs_latest else None
    ebitda = _safe_float(is_latest.get("ebitda")) if is_latest else None
    nd_to_ebitda: Optional[float] = None
    if total_debt is not None and cash is not None and ebitda is not None and ebitda > 0:
        nd_to_ebitda = (total_debt - cash) / ebitda

    evidence["m6_net_debt_to_ebitda"] = {
        "totalDebt": total_debt, "cash": cash, "ebitda": ebitda, "ratio": nd_to_ebitda,
    }

    if ebitda is not None and ebitda <= 0:
        add(MetricResult(
            code="OE-LEVERAGE", name="Net Debt / EBITDA", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-LEVERAGE", severity="critical",
                message="EBITDA is non-positive; leverage cannot be assessed and balance-sheet risk is elevated.",
                evidence=evidence["m6_net_debt_to_ebitda"],
            ),
        ))
    elif nd_to_ebitda is None:
        add(MetricResult(
            code="OE-LEVERAGE", name="Net Debt / EBITDA", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-LEVERAGE", severity="low",
                message="Could not compute Net Debt/EBITDA (missing debt, cash, or EBITDA).",
                evidence=evidence["m6_net_debt_to_ebitda"],
            ),
        ))
    elif nd_to_ebitda < 3.0:
        add(MetricResult("OE-LEVERAGE", "Net Debt / EBITDA", "pass", 1))
    elif nd_to_ebitda <= 5.0:
        add(MetricResult(
            code="OE-LEVERAGE", name="Net Debt / EBITDA", status="caution", points=0,
            flag=DiagnosticFlag(
                code="OE-LEVERAGE", severity="medium",
                message=f"Net Debt/EBITDA is {nd_to_ebitda:.1f}× (moderate leverage).",
                evidence={"ratio": nd_to_ebitda},
                recommendation="Use conservative discount rate to price in debt risk.",
            ),
        ))
    else:
        add(MetricResult(
            code="OE-LEVERAGE", name="Net Debt / EBITDA", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-LEVERAGE", severity="critical",
                message=f"Net Debt/EBITDA is {nd_to_ebitda:.1f}× (risky). OE model assumptions are fragile.",
                evidence={"ratio": nd_to_ebitda},
            ),
        ))

    # ── Metric 7: ROIC (5y avg) ───────────────────────────────────────────────

    roic_pairs = sorted(
        [(r.get("fiscal_year"), _safe_float(r.get("roic"))) for r in roic_rows
         if r.get("fiscal_year") is not None and _safe_float(r.get("roic")) is not None],
        key=lambda t: t[0],
    )[-5:]
    roic_vals = [v for _, v in roic_pairs if v is not None]
    # Normalise percent → fraction if needed
    roic_norm = [v / 100.0 if v > 1.0 else v for v in roic_vals]
    roic_avg = _mean(roic_norm) if len(roic_norm) >= 3 else None
    evidence["m7_roic_5y"] = {"roicAvg": roic_avg, "points": len(roic_norm)}

    if roic_avg is None:
        add(MetricResult(
            code="OE-ROIC", name="ROIC (5y avg)", status="na", points=0,
            flag=DiagnosticFlag(
                code="OE-ROIC", severity="low",
                message="Insufficient ROIC history to evaluate capital allocation quality.",
            ),
        ))
    elif roic_avg >= 0.15:
        add(MetricResult("OE-ROIC", "ROIC (5y avg)", "pass", 1))
    elif roic_avg >= 0.10:
        add(MetricResult(
            code="OE-ROIC", name="ROIC (5y avg)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="OE-ROIC", severity="medium",
                message=f"ROIC is {roic_avg:.1%} (adequate). Use conservative terminal growth.",
                evidence={"roicAvg5y": roic_avg},
            ),
        ))
    else:
        add(MetricResult(
            code="OE-ROIC", name="ROIC (5y avg)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="OE-ROIC", severity="critical",
                message=f"ROIC is {roic_avg:.1%} (weak). OE model assumes durable excess returns; these are not present.",
                evidence={"roicAvg5y": roic_avg},
                recommendation="Avoid OE model or use a very low terminal growth rate.",
            ),
        ))

    # ── Final scoring ─────────────────────────────────────────────────────────

    total_possible = 7  # fixed denominator per design decision (consistent with DCF)
    passes = sum(r.points for r in results)
    score_0_100 = _points_to_score(passes, total_possible)
    category = _category_from_passes(passes)

    evidence["data_coverage"] = coverage
    evidence["final_scoring"] = {
        "passes": passes,
        "totalPossible": total_possible,
        "score0to100": score_0_100,
        "category": category,
        "asOf": date.today().isoformat(),
        "sector": sector,
    }

    flags.insert(0, DiagnosticFlag(
        code="OE-DATA-COVERAGE",
        severity="info",
        message="OE suitability data coverage summary.",
        evidence=coverage,
        recommendation="Improve data completeness for higher-confidence suitability metrics.",
    ))
    flags.insert(0, DiagnosticFlag(
        code="OE-SCORECARD",
        severity="info",
        message=f"Owner Earnings suitability: {passes}/{total_possible} passes (mapped to {score_0_100}/100).",
        evidence=evidence["final_scoring"],
        recommendation="Use suitability diagnostics to set appropriate conservatism in OE assumptions.",
    ))

    return score_0_100, category, flags, evidence   