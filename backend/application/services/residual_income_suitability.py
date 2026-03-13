# application/services/residual_income_suitability.py
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


# ── Helpers ───────────────────────────────────────────────────────────────────

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
    if passes >= 6:
        return "Good"
    if passes >= 4:
        return "Caution"
    return "Poor"


# ── Scorecard ─────────────────────────────────────────────────────────────────

async def evaluate_residual_income_suitability(
    repo: Any,
    company_id: int,
    sector: Optional[str],
    cost_of_equity: Optional[float] = None,
) -> Tuple[int, str, List[DiagnosticFlag], Dict[str, Any]]:
    """
    7-metric Residual Income suitability scorecard.

    Args:
        cost_of_equity: If provided (computed by service), used directly for ROE-excess metric.
                        If None, the metric is marked 'na'.

    Returns:
        score_0_100, category, flags, evidence

    Data sources (via repo only):
    - ROE history:       repo.get_roe_history
    - EPS series:        repo.get_eps_yearly_series
    - Book value history: repo.get_book_value_history
    - Balance sheet:     repo.get_balance_sheet_latest + get_balance_sheet_ri_inputs
    - Income statement:  repo.get_income_statement_latest
    - Cash flow:         repo.get_cash_flow_latest
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

    roe_rows: List[Dict[str, Any]] = []
    if hasattr(repo, "get_roe_history"):
        try:
            roe_rows = await repo.get_roe_history(company_id, years=5)
        except Exception:
            pass

    eps_rows: List[Dict[str, Any]] = []
    try:
        eps_rows = await repo.get_eps_yearly_series(company_id)
    except Exception:
        pass

    bv_rows: List[Dict[str, Any]] = []
    if hasattr(repo, "get_book_value_history"):
        try:
            bv_rows = await repo.get_book_value_history(company_id, years=6)
        except Exception:
            pass

    bs_latest: Optional[Dict[str, Any]] = None
    bs_ri: Optional[Dict[str, Any]] = None
    is_latest: Optional[Dict[str, Any]] = None
    cf_latest: Optional[Dict[str, Any]] = None

    try:
        bs_latest = await repo.get_balance_sheet_latest(company_id)
    except Exception:
        pass
    if hasattr(repo, "get_balance_sheet_ri_inputs"):
        try:
            bs_ri = await repo.get_balance_sheet_ri_inputs(company_id)
        except Exception:
            pass
    try:
        is_latest = await repo.get_income_statement_latest(company_id)
    except Exception:
        pass
    try:
        cf_latest = await repo.get_cash_flow_latest(company_id)
    except Exception:
        pass

    # ── Metric 1: ROE vs Cost of Equity (excess return) ──────────────────────
    # Core RI pre-requisite: RI > 0 requires ROE > k_e.
    # evidence uses the service-provided k_e (most accurate) or None.

    roe_latest: Optional[float] = None
    derived = None
    if hasattr(repo, "get_derived_metrics_latest"):
        try:
            derived = await repo.get_derived_metrics_latest(company_id)
        except Exception:
            pass
    if derived:
        roe_latest = _safe_float(derived.get("roe"))

    # Fallback: compute from IS/BS
    if roe_latest is None and is_latest and bs_latest:
        ni = _safe_float(is_latest.get("net_income"))
        eq = _safe_float(bs_latest.get("shareholders_equity"))
        if ni is not None and eq is not None and eq > 0:
            roe_latest = ni / eq

    excess = None
    if roe_latest is not None and cost_of_equity is not None:
        excess = roe_latest - cost_of_equity

    evidence["m1_roe_excess"] = {"roe": roe_latest, "costOfEquity": cost_of_equity, "excess": excess}
    coverage["RI-ROE-EXCESS"] = {"hasRoe": roe_latest is not None, "hasCostOfEquity": cost_of_equity is not None}

    if excess is None:
        add(MetricResult(
            code="RI-ROE-EXCESS", name="ROE Excess Return (ROE − k_e)", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-ROE-EXCESS", severity="low",
                message="Could not compute ROE excess return (missing ROE or cost of equity).",
                evidence=evidence["m1_roe_excess"],
            ),
        ))
    elif excess > 0.02:
        add(MetricResult("RI-ROE-EXCESS", "ROE Excess Return (ROE − k_e)", "pass", 1))
    elif excess >= -0.02:
        add(MetricResult(
            code="RI-ROE-EXCESS", name="ROE Excess Return (ROE − k_e)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-ROE-EXCESS", severity="medium",
                message=f"ROE barely covers cost of equity (excess = {excess:.1%}). Residual Income is near zero.",
                evidence={"excess": excess, "roe": roe_latest, "ke": cost_of_equity},
                recommendation="Use conservative growth; intrinsic value will closely approximate book value.",
            ),
        ))
    else:
        add(MetricResult(
            code="RI-ROE-EXCESS", name="ROE Excess Return (ROE − k_e)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-ROE-EXCESS", severity="critical",
                message=f"ROE ({roe_latest:.1%}) < cost of equity ({cost_of_equity:.1%}). Company is destroying value. RI is negative.",
                evidence={"excess": excess, "roe": roe_latest, "ke": cost_of_equity},
                recommendation="The RI model will produce an intrinsic value below book value — this is a valid result, not an error. "
                               "Consider whether the business model can improve ROE above k_e.",
            ),
        ))

    # ── Metric 2: ROE Positivity (5y) ────────────────────────────────────────

    roe_sorted = sorted(
        [r for r in roe_rows if r.get("fiscal_year") is not None and _safe_float(r.get("roe")) is not None],
        key=lambda r: int(r.get("fiscal_year") or 0),
    )[-5:]
    roe_vals = [_safe_float(r.get("roe")) for r in roe_sorted]
    roe_pos = sum(1 for v in roe_vals if v is not None and v > 0)
    evidence["m2_roe_consistency"] = {"positiveYears": roe_pos, "totalYears": len(roe_sorted)}
    coverage["RI-ROE-CONS"] = {"availableYears": len(roe_sorted)}

    if len(roe_sorted) < 3:
        add(MetricResult(
            code="RI-ROE-CONS", name="ROE Positivity (5y)", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-ROE-CONS", severity="low",
                message="Insufficient ROE history for 5-year consistency check.",
                evidence={"availableYears": len(roe_sorted)},
            ),
        ))
    elif roe_pos >= 4:
        add(MetricResult("RI-ROE-CONS", "ROE Positivity (5y)", "pass", 1))
    elif roe_pos >= 2:
        add(MetricResult(
            code="RI-ROE-CONS", name="ROE Positivity (5y)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-ROE-CONS", severity="medium",
                message=f"ROE positive in {roe_pos}/{len(roe_sorted)} years. RI stream will be volatile.",
                evidence={"positiveYears": roe_pos, "totalYears": len(roe_sorted)},
            ),
        ))
    else:
        add(MetricResult(
            code="RI-ROE-CONS", name="ROE Positivity (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-ROE-CONS", severity="critical",
                message=f"ROE positive in only {roe_pos}/{len(roe_sorted)} years. Avoid RI model.",
                evidence={"positiveYears": roe_pos, "totalYears": len(roe_sorted)},
            ),
        ))

    # ── Metric 3: Book Value CAGR (5y) ───────────────────────────────────────
    # Positive BV growth validates the clean-surplus assumption (retained earnings build equity).

    bv_sorted = sorted(
        [r for r in bv_rows if r.get("fiscal_year") is not None and _safe_float(r.get("book_value")) is not None],
        key=lambda r: int(r.get("fiscal_year") or 0),
    )[-6:]

    bv_cagr: Optional[float] = None
    bv_span: Optional[int] = None
    if len(bv_sorted) >= 2:
        bv0 = _safe_float(bv_sorted[0].get("book_value"))
        bvN = _safe_float(bv_sorted[-1].get("book_value"))
        try:
            bv_span = int(bv_sorted[-1]["fiscal_year"]) - int(bv_sorted[0]["fiscal_year"])
        except Exception:
            bv_span = None
        if bv0 and bvN and bv_span and bv_span > 0:
            bv_cagr = _cagr(bv0, bvN, bv_span)

    evidence["m3_bv_cagr"] = {"cagr": bv_cagr, "spanYears": bv_span, "points": len(bv_sorted)}
    coverage["RI-BV-GROWTH"] = {"availableYears": len(bv_sorted)}

    if bv_cagr is None:
        add(MetricResult(
            code="RI-BV-GROWTH", name="Book Value CAGR (5y)", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-BV-GROWTH", severity="low",
                message="Could not compute Book Value CAGR (insufficient balance sheet history).",
                evidence=evidence["m3_bv_cagr"],
            ),
        ))
    elif bv_cagr >= 0.03:
        add(MetricResult("RI-BV-GROWTH", "Book Value CAGR (5y)", "pass", 1))
    elif bv_cagr >= 0.0:
        add(MetricResult(
            code="RI-BV-GROWTH", name="Book Value CAGR (5y)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-BV-GROWTH", severity="medium",
                message=f"Book Value CAGR is {bv_cagr:.1%} (stagnant). Equity is not compounding.",
                evidence={"bvCagr": bv_cagr},
                recommendation="Investigate whether dividends, buybacks, or losses are eroding retained equity.",
            ),
        ))
    else:
        add(MetricResult(
            code="RI-BV-GROWTH", name="Book Value CAGR (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-BV-GROWTH", severity="critical",
                message=f"Book Value CAGR is {bv_cagr:.1%} (shrinking). Clean-surplus assumption is violated.",
                evidence={"bvCagr": bv_cagr},
            ),
        ))

    # ── Metric 4: EPS Volatility (5y) ────────────────────────────────────────

    eps_sorted = sorted(
        [r for r in eps_rows if r.get("fiscal_year") is not None and _safe_float(r.get("eps")) is not None],
        key=lambda r: int(r.get("fiscal_year") or 0),
    )[-5:]
    eps_vals_clean = [_safe_float(r.get("eps")) for r in eps_sorted if _safe_float(r.get("eps")) is not None]
    mu_eps = _mean(eps_vals_clean)
    sd_eps = _stdev(eps_vals_clean)
    vol_eps = (sd_eps / abs(mu_eps)) if (mu_eps is not None and sd_eps is not None and mu_eps != 0) else None
    evidence["m4_eps_volatility"] = {"mean": mu_eps, "stdev": sd_eps, "volatility": vol_eps}

    if mu_eps is not None and mu_eps <= 0:
        add(MetricResult(
            code="RI-EPS-VOL", name="EPS Volatility (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-EPS-VOL", severity="critical",
                message="Average EPS is non-positive. RI model requires sustained profitability.",
                evidence={"mean": mu_eps},
            ),
        ))
    elif vol_eps is None:
        add(MetricResult(
            code="RI-EPS-VOL", name="EPS Volatility (5y)", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-EPS-VOL", severity="low",
                message="Could not compute EPS volatility (insufficient history).",
            ),
        ))
    elif vol_eps < 0.30:
        add(MetricResult("RI-EPS-VOL", "EPS Volatility (5y)", "pass", 1))
    elif vol_eps <= 0.60:
        add(MetricResult(
            code="RI-EPS-VOL", name="EPS Volatility (5y)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-EPS-VOL", severity="medium",
                message=f"EPS volatility is {vol_eps:.0%} (moderate). RI growth assumption is uncertain.",
                evidence={"epsVolatility": vol_eps},
            ),
        ))
    else:
        add(MetricResult(
            code="RI-EPS-VOL", name="EPS Volatility (5y)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-EPS-VOL", severity="critical",
                message=f"EPS volatility is {vol_eps:.0%} (high). RI forecasts will be unreliable.",
                evidence={"epsVolatility": vol_eps},
                recommendation="Avoid RI model for highly cyclical businesses.",
            ),
        ))

    # ── Metric 5: Intangibles / Total Assets ─────────────────────────────────
    # High intangibles distort book value → RI anchor (BV/share) is less reliable.

    intangibles = None
    goodwill = None
    total_assets = None
    if bs_ri:
        intangibles = _safe_float(bs_ri.get("intangible_assets"))
        goodwill = _safe_float(bs_ri.get("goodwill"))
        total_assets = _safe_float(bs_ri.get("total_assets"))

    intangible_ratio: Optional[float] = None
    if total_assets is not None and total_assets > 0:
        ia = (intangibles or 0.0) + (goodwill or 0.0)
        intangible_ratio = ia / total_assets

    evidence["m5_intangibles_ratio"] = {
        "intangibleAssets": intangibles, "goodwill": goodwill,
        "totalAssets": total_assets, "ratio": intangible_ratio,
    }

    if intangible_ratio is None:
        add(MetricResult(
            code="RI-INTANGIBLES", name="Intangibles / Total Assets", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-INTANGIBLES", severity="low",
                message="Could not compute intangibles ratio (missing intangibles or total assets).",
                evidence=evidence["m5_intangibles_ratio"],
            ),
        ))
    elif intangible_ratio < 0.40:
        add(MetricResult("RI-INTANGIBLES", "Intangibles / Total Assets", "pass", 1))
    elif intangible_ratio <= 0.65:
        add(MetricResult(
            code="RI-INTANGIBLES", name="Intangibles / Total Assets", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-INTANGIBLES", severity="medium",
                message=f"Intangibles/Total Assets is {intangible_ratio:.0%}. Book value anchor may be inflated.",
                evidence={"ratio": intangible_ratio},
                recommendation="Consider tangible book value as an alternative floor.",
            ),
        ))
    else:
        add(MetricResult(
            code="RI-INTANGIBLES", name="Intangibles / Total Assets", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-INTANGIBLES", severity="critical",
                message=f"Intangibles/Total Assets is {intangible_ratio:.0%} (very high). Book value is largely intangible. RI anchor is unreliable.",
                evidence={"ratio": intangible_ratio},
                recommendation="Prefer DCF or Owner Earnings for intangibles-heavy companies.",
            ),
        ))

    # ── Metric 6: Net Debt / Equity ───────────────────────────────────────────

    total_debt = _safe_float(bs_latest.get("total_debt")) if bs_latest else None
    cash = _safe_float(bs_latest.get("cash_and_cash_equivalents")) if bs_latest else None
    equity = _safe_float(bs_latest.get("shareholders_equity")) if bs_latest else None
    nd_to_equity: Optional[float] = None
    if total_debt is not None and cash is not None and equity is not None and equity > 0:
        nd_to_equity = (total_debt - cash) / equity

    evidence["m6_leverage"] = {"totalDebt": total_debt, "cash": cash, "equity": equity, "ratio": nd_to_equity}

    if equity is not None and equity <= 0:
        add(MetricResult(
            code="RI-LEVERAGE", name="Net Debt / Equity", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-LEVERAGE", severity="critical",
                message="Shareholders' equity is negative; RI model is not applicable (book value anchor breaks down).",
                evidence={"equity": equity},
                recommendation="RI model requires positive book equity as anchor. Avoid until equity is restored.",
            ),
        ))
    elif nd_to_equity is None:
        add(MetricResult(
            code="RI-LEVERAGE", name="Net Debt / Equity", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-LEVERAGE", severity="low",
                message="Could not compute Net Debt/Equity (missing debt, cash, or equity).",
                evidence=evidence["m6_leverage"],
            ),
        ))
    elif nd_to_equity < 1.0:
        add(MetricResult("RI-LEVERAGE", "Net Debt / Equity", "pass", 1))
    elif nd_to_equity <= 2.0:
        add(MetricResult(
            code="RI-LEVERAGE", name="Net Debt / Equity", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-LEVERAGE", severity="medium",
                message=f"Net Debt/Equity is {nd_to_equity:.1f}× (moderate). Financial distress risk is elevated.",
                evidence={"ratio": nd_to_equity},
            ),
        ))
    else:
        add(MetricResult(
            code="RI-LEVERAGE", name="Net Debt / Equity", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-LEVERAGE", severity="critical",
                message=f"Net Debt/Equity is {nd_to_equity:.1f}× (high). Equity base is fragile; RI anchor is at risk.",
                evidence={"ratio": nd_to_equity},
            ),
        ))

    # ── Metric 7: Accruals Quality (|NI − CFO| / Total Assets) ───────────────
    # High accruals indicate earnings less cash-backed → RI growth projections less reliable.

    ni_latest = _safe_float(is_latest.get("net_income")) if is_latest else None
    cfo_latest = _safe_float(cf_latest.get("cash_from_operating_activities")) if cf_latest else None
    ta_latest = total_assets  # reuse from metric 5 if available
    if ta_latest is None and bs_ri:
        ta_latest = _safe_float(bs_ri.get("total_assets"))

    accruals_ratio: Optional[float] = None
    if ni_latest is not None and cfo_latest is not None and ta_latest is not None and ta_latest > 0:
        accruals_ratio = abs(ni_latest - cfo_latest) / ta_latest

    evidence["m7_accruals"] = {
        "netIncome": ni_latest, "cfo": cfo_latest,
        "totalAssets": ta_latest, "accrualRatio": accruals_ratio,
    }

    if accruals_ratio is None:
        add(MetricResult(
            code="RI-ACCRUALS", name="Accruals Quality (|NI − CFO| / Assets)", status="na", points=0,
            flag=DiagnosticFlag(
                code="RI-ACCRUALS", severity="low",
                message="Could not compute accruals quality (missing NI, CFO, or total assets).",
                evidence=evidence["m7_accruals"],
            ),
        ))
    elif accruals_ratio < 0.05:
        add(MetricResult("RI-ACCRUALS", "Accruals Quality (|NI − CFO| / Assets)", "pass", 1))
    elif accruals_ratio <= 0.10:
        add(MetricResult(
            code="RI-ACCRUALS", name="Accruals Quality (|NI − CFO| / Assets)", status="caution", points=0,
            flag=DiagnosticFlag(
                code="RI-ACCRUALS", severity="medium",
                message=f"Accruals ratio is {accruals_ratio:.1%} (moderate). Earnings quality may be lower.",
                evidence={"accrualRatio": accruals_ratio},
                recommendation="Validate earnings quality; consider conservative RI growth assumptions.",
            ),
        ))
    else:
        add(MetricResult(
            code="RI-ACCRUALS", name="Accruals Quality (|NI − CFO| / Assets)", status="fail", points=0,
            flag=DiagnosticFlag(
                code="RI-ACCRUALS", severity="critical",
                message=f"Accruals ratio is {accruals_ratio:.1%} (high). Earnings are not well-supported by cash flow. RI projections are unreliable.",
                evidence={"accrualRatio": accruals_ratio},
                recommendation="Use cash-based methods (DCF / Owner Earnings) instead.",
            ),
        ))

    # ── Final scoring ─────────────────────────────────────────────────────────

    total_possible = 7  # fixed denominator, consistent with other scorecards
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
        code="RI-DATA-COVERAGE",
        severity="info",
        message="RI suitability data coverage summary.",
        evidence=coverage,
        recommendation="Improve data completeness for higher-confidence suitability metrics.",
    ))
    flags.insert(0, DiagnosticFlag(
        code="RI-SCORECARD",
        severity="info",
        message=f"Residual Income suitability: {passes}/{total_possible} passes (mapped to {score_0_100}/100).",
        evidence=evidence["final_scoring"],
        recommendation="Use suitability diagnostics to assess reliability of book value anchor and RI projections.",
    ))

    return score_0_100, category, flags, evidence