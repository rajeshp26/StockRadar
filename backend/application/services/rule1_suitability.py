from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from domain.models.valuation_rule1 import DiagnosticFlag

SECTOR_FIN = {"Financial Services", "Banks", "Insurance", "Diversified Financials"}

@dataclass
class MetricResult:
    id: str
    name: str
    status: str  # "pass" | "caution" | "fail" | "na"
    points: int  # 1 only if pass
    flag: DiagnosticFlag | None = None


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


def _cagr(v0: float, vN: float, years: int) -> float | None:
    if years <= 0 or v0 <= 0 or vN <= 0:
        return None
    try:
        return (vN / v0) ** (1.0 / years) - 1.0
    except Exception:
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


def _take_last_n_years(rows: list[dict[str, Any]], key: str, n: int) -> list[tuple[int, float]]:
    """
    rows: [{fiscal_year:int, <key>: number}, ...] ascending by fiscal_year
    returns last n usable (year,value) pairs
    """
    out: list[tuple[int, float]] = []
    for r in rows:
        y = r.get("fiscal_year")
        v = _safe_float(r.get(key))
        if isinstance(y, int) and v is not None:
            out.append((y, v))
    # sort once (do not sort inside loop)
    out.sort(key=lambda t: t[0])
    return out[-n:]


def _series_cagr_span(
    rows: list[dict[str, Any]],
    key: str,
    target_years: int,
) -> tuple[float | None, int | None, list[int], list[int]]:
    """
    Option 1: Compute CAGR over the actual span (yN - y0) and report gaps.
    - Return gaps so UI can show "computed over 6y span due to missing fiscal years".
    Returns: (cagr, span_years, years_present, missing_years_between)
    """
    pairs = _take_last_n_years(rows, key=key, n=target_years + 1)
    if len(pairs) < 2:
        return None, None, [], []

    y0, v0 = pairs[0]
    yN, vN = pairs[-1]
    span = yN - y0
    if span <= 0:
        return None, None, [y for y, _ in pairs], []

    years_present = [y for y, _ in pairs]
    present_set = set(years_present)
    missing = [y for y in range(y0 + 1, yN) if y not in present_set]

    cagr = _cagr(v0, vN, span)
    return cagr, span, years_present, missing


def _eps_drawdown(rows: list[dict[str, Any]], key: str, window_years: int = 5) -> float | None:
    pairs = _take_last_n_years(rows, key=key, n=window_years)
    if len(pairs) < 3:
        return None
    vals = [v for _, v in pairs]
    peak = max(vals)
    trough = min(vals)
    if peak <= 0:
        return None
    return (peak - trough) / peak


def _points_to_score(points: int, total_possible: int) -> int:
    if total_possible <= 0:
        return 0
    return int(round((points / total_possible) * 100))


def _category_from_points(points: int, total_possible: int, has_hard_fail: bool) -> str:
    """
    Spreadsheet-friendly mapping:
    - If any hard fail => Poor
    - Else thresholds scaled to total_possible:
        Strong ~ "max-2"  (9-11 when total=11)
        Caution ~ "max-4" (7-8 when total=11)
        Else Poor
    """
    if has_hard_fail:
        return "Poor"

    strong_min = max(0, total_possible - 2)
    caution_min = max(0, total_possible - 4)

    if points >= strong_min:
        return "Good"
    if points >= caution_min:
        return "Caution"
    return "Poor"


async def evaluate_rule1_suitability(
    repo: Any,
    company_id: int,
    sector: str | None,
) -> tuple[int, str, list[DiagnosticFlag], dict[str, Any]]:
    """
    Returns:
      score_0_100,
      category ("Good"|"Caution"|"Poor"),
      flags (diagnostics),
      evidence (metric values + totals)
    IMPORTANT:
    - This function is the ONLY authority for Applicability.score/category.
    - Other diagnostics (staleness, splits, sector notes) may be appended as flags,
      but must NOT change score/category to avoid conflicting truth sources.
    """

    # Pull time-series + snapshots needed for metrics
    net_income_rows = await repo.get_net_income_history(company_id)      # [{fiscal_year, net_income}]
    eps_rows = await repo.get_eps_yearly_series(company_id)              # [{fiscal_year, eps}]
    revenue_rows = await repo.get_revenue_yearly_series(company_id)      # [{fiscal_year, revenue}]
    shares_rows = await repo.get_shares_history(company_id)              # [{fiscal_year, shares_outstanding_diluted}]
    roic_rows = await repo.get_roic_history(company_id)                  # [{fiscal_year, roic}]
    bs_latest = await repo.get_balance_sheet_latest(company_id)          # {total_debt, shareholders_equity, ...}
    is_latest = await repo.get_income_statement_latest(company_id)       # {ebit, interest_expense, ...}
    cf_latest = await repo.get_cash_flow_latest(company_id)              # {cfo, capex, ...}
    derived_latest = None
    if hasattr(repo, "get_derived_metrics_latest"):
        derived_latest = await repo.get_derived_metrics_latest(company_id)

    results: list[MetricResult] = []
    flags: list[DiagnosticFlag] = []
    evidence: dict[str, Any] = {}

    # ---------------------------------------------------------------------
    # Debug / Transparency: Capture actual keys returned by repo snapshots.
    # This avoids guessing field names and makes "missing data" diagnosable.
    # ---------------------------------------------------------------------
    evidence["repo_payload_keys"] = {
        "balance_sheet_latest": sorted(list(bs_latest.keys())) if isinstance(bs_latest, dict) else None,
        "income_statement_latest": sorted(list(is_latest.keys())) if isinstance(is_latest, dict) else None,
        "cash_flow_latest": sorted(list(cf_latest.keys())) if isinstance(cf_latest, dict) else None,
        "derived_metrics_latest": sorted(list(derived_latest.keys())) if isinstance(derived_latest, dict) else None,
    }
    flags.append(DiagnosticFlag(
        code="R1-REPO-KEYS",
        severity="info",
        message="Repo payload keys captured for suitability debugging.",
        evidence=evidence["repo_payload_keys"],
    ))

    # Helper to append
    def add(m: MetricResult):
        results.append(m)
        if m.flag is not None:
            flags.append(m.flag)

    hard_fail = False

    # Collect per-metric coverage so UI can show "missing data" clearly.
    # Filled progressively as metrics compute their input availability.
    coverage: dict[str, Any] = {}
    # ---------------------------------------------------------
    # Metric 1: Positive Earnings Consistency (last 5 years)
    # % of last 5 years with positive net income
    # ---------------------------------------------------------
    ni_pairs = _take_last_n_years(net_income_rows, "net_income", 5)
    coverage["M1"] = {"requiredYears": 5, "availableYears": len(ni_pairs)}
    if len(ni_pairs) >= 3:
        pos = sum(1 for _, v in ni_pairs if v > 0)
        total = len(ni_pairs)
        pct = pos / total
        evidence["eps_quality_positive_net_income_years"] = {"positive": pos, "total": total, "pct": pct}

        if pct >= 0.80:
            add(MetricResult("M1", "Positive Earnings Consistency", "pass", 1))
        elif pct >= 0.60:
            add(MetricResult(
                "M1", "Positive Earnings Consistency", "caution", 0,
                DiagnosticFlag(
                    code="R1-EPS-CONSISTENCY",
                    severity="medium",
                    message=f"{pos} of last {total} years had positive net income (={pct:.0%}). Investigate volatility.",
                    evidence={"positiveYears": pos, "totalYears": total, "pct": pct},
                    recommendation="Inspect cyclicality and normalize earnings where needed."
                )
            ))
        else:
            hard_fail = True
            add(MetricResult(
                "M1", "Positive Earnings Consistency", "fail", 0,
                DiagnosticFlag(
                    code="R1-EPS-CONSISTENCY",
                    severity="critical",
                    message=f"Only {pos} of last {total} years had positive net income (={pct:.0%}). Rule #1 not suitable.",
                    evidence={"positiveYears": pos, "totalYears": total, "pct": pct},
                    recommendation="Avoid Rule #1; consider DCF/Owner Earnings with conservative assumptions."
                )
            ))
    else:
        add(MetricResult(
            "M1", "Positive Earnings Consistency", "caution", 0,
            DiagnosticFlag(
                code="R1-EPS-CONSISTENCY",
                severity="low",
                message="Insufficient net income history to evaluate earnings consistency.",
                evidence={"availableYears": len(ni_pairs)},
            )
        ))

    # ---------------------------------------------------------
    # Metric 2: EPS Volatility (Std Dev / Avg EPS over 5 years)
    # ---------------------------------------------------------
    eps_pairs = _take_last_n_years(eps_rows, "eps", 5)
    coverage["M2"] = {"requiredYears": 5, "availableYears": len(eps_pairs)}
    if len(eps_pairs) >= 3:
        eps_vals = [v for _, v in eps_pairs if v is not None]
        avg = _mean(eps_vals)
        sd = _stdev(eps_vals)
        vol = None
        if avg is not None and sd is not None and avg != 0:
            vol = abs(sd / avg)
        evidence["eps_quality_volatility"] = {"avg": avg, "stdev": sd, "volatility": vol}

        if vol is None:
            add(MetricResult(
                "M2", "Earnings Volatility (EPS)", "caution", 0,
                DiagnosticFlag(
                    code="R1-EPS-VOL",
                    severity="low",
                    message="Could not compute EPS volatility (insufficient stable EPS values).",
                    evidence={"avg": avg, "stdev": sd},
                )
            ))
        elif vol < 0.30:
            add(MetricResult("M2", "Earnings Volatility (EPS)", "pass", 1))
        elif vol <= 0.60:
            add(MetricResult(
                "M2", "Earnings Volatility (EPS)", "caution", 0,
                DiagnosticFlag(
                    code="R1-EPS-VOL",
                    severity="medium",
                    message=f"EPS volatility is {vol:.0%} (moderate). Consider normalization.",
                    evidence={"volatility": vol, "avg": avg, "stdev": sd},
                    recommendation="Use conservative growth and MOS; sanity-check trough years."
                )
            ))
        else:
            hard_fail = True
            add(MetricResult(
                "M2", "Earnings Volatility (EPS)", "fail", 0,
                DiagnosticFlag(
                    code="R1-EPS-VOL",
                    severity="critical",
                    message=f"EPS volatility is {vol:.0%} (high). Rule #1 not suitable.",
                    evidence={"volatility": vol, "avg": avg, "stdev": sd},
                    recommendation="Avoid Rule #1; use DCF with scenario ranges."
                )
            ))
    else:
        add(MetricResult(
            "M2", "Earnings Volatility (EPS)", "caution", 0,
            DiagnosticFlag(
                code="R1-EPS-VOL",
                severity="low",
                message="Insufficient EPS history to evaluate volatility.",
                evidence={"availableYears": len(eps_pairs)},
            )
        ))

    # ---------------------------------------------------------
    # Metric 3: Revenue CAGR (5y)
    # ---------------------------------------------------------
    rev_cagr, rev_span, rev_years_present, rev_missing = _series_cagr_span(revenue_rows, "revenue", 5)
    evidence["growth_revenue_cagr"] = {
        "targetYears": 5,
        "spanYears": rev_span,
        "yearsPresent": rev_years_present,
        "missingYears": rev_missing,
        "cagr": rev_cagr,
    }
    coverage["M3"] = {
        "requiredYears": 6,  # points needed for true 5y comparison
        "availableYears": len(rev_years_present),
        "spanYears": rev_span,
        "missingYears": rev_missing,
    }

    span_flag_m3: DiagnosticFlag | None = None
    if rev_cagr is not None and rev_span is not None and rev_span != 5:
        span_flag_m3 = DiagnosticFlag(
            code="R1-REV-CAGR-SPAN",
            severity="info",
            message=f"Revenue CAGR computed over {rev_span}y span (target 5y) due to missing fiscal years.",
            evidence=evidence["growth_revenue_cagr"],
            recommendation="Backfill missing fiscal years for a true 5-year CAGR."
        )
    if rev_cagr is None:
        add(MetricResult(
            "M3", "Revenue CAGR (5y)", "caution", 0,
            DiagnosticFlag(
                code="R1-REV-CAGR",
                severity="low",
                message="Insufficient revenue history to compute CAGR.",
                evidence=evidence["growth_revenue_cagr"],
            )
        ))
    elif rev_cagr >= 0.05:
        add(MetricResult("M3", "Revenue CAGR (5y)", "pass", 1, span_flag_m3))
    elif rev_cagr >= 0.0:
        add(MetricResult(
            "M3", "Revenue CAGR (5y)", "caution", 0,
            span_flag_m3 or DiagnosticFlag(
                code="R1-REV-CAGR",
                severity="medium",
                message=f"Revenue CAGR is {rev_cagr:.1%} (low growth).",
                evidence={"revenueCagr": rev_cagr, **evidence["growth_revenue_cagr"]},
                recommendation="Use conservative growth; validate business durability."
            )
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "M3", "Revenue CAGR (5y)", "fail", 0,
            DiagnosticFlag(
                code="R1-REV-CAGR",
                severity="critical",
                message=f"Revenue CAGR is {rev_cagr:.1%} (declining). Rule #1 not suitable.",
                evidence={"revenueCagr": rev_cagr, **evidence["growth_revenue_cagr"]},
                recommendation="Avoid Rule #1; consider turnaround-specific methods."
            )
        ))

    # ---------------------------------------------------------
    # Metric 4: EPS CAGR (5y)
    # ---------------------------------------------------------

    eps_cagr, eps_span, eps_years_present, eps_missing = _series_cagr_span(eps_rows, "eps", 5)
    evidence["growth_eps_cagr"] = {
        "targetYears": 5,
        "spanYears": eps_span,
        "yearsPresent": eps_years_present,
        "missingYears": eps_missing,
        "cagr": eps_cagr,
    }
    coverage["M4"] = {
        "requiredYears": 6,
        "availableYears": len(eps_years_present),
        "spanYears": eps_span,
        "missingYears": eps_missing,
    }

    span_flag_m4: DiagnosticFlag | None = None
    if eps_cagr is not None and eps_span is not None and eps_span != 5:
        span_flag_m4 = DiagnosticFlag(
            code="R1-EPS-CAGR-SPAN",
            severity="info",
            message=f"EPS CAGR computed over {eps_span}y span (target 5y) due to missing fiscal years.",
            evidence=evidence["growth_eps_cagr"],
            recommendation="Backfill missing fiscal years for a true 5-year CAGR."
        )
    if eps_cagr is None:
        add(MetricResult(
            "M4", "EPS CAGR (5y)", "caution", 0,
            DiagnosticFlag(
                code="R1-EPS-CAGR",
                severity="low",
                message="Insufficient EPS history to compute CAGR.",
                evidence=evidence["growth_eps_cagr"],
            )
        ))
    elif eps_cagr >= 0.08:
        add(MetricResult("M4", "EPS CAGR (5y)", "pass", 1))
    elif eps_cagr >= 0.03:
        add(MetricResult(
            "M4", "EPS CAGR (5y)", "caution", 0,
            span_flag_m4 or DiagnosticFlag(
                code="R1-EPS-CAGR",
                severity="medium",
                message=f"EPS CAGR is {eps_cagr:.1%} (slow compounding).",
                evidence={"epsCagr": eps_cagr, **evidence["growth_eps_cagr"]},
                recommendation="Use conservative growth assumptions; validate drivers."
            )
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "M4", "EPS CAGR (5y)", "fail", 0,
            DiagnosticFlag(
                code="R1-EPS-CAGR",
                severity="critical",
                message=f"EPS CAGR is {eps_cagr:.1%} (weak). Rule #1 not suitable.",
                evidence={"epsCagr": eps_cagr, **evidence["growth_eps_cagr"]},
                recommendation="Avoid Rule #1; use scenario-based cash flow approaches."
            )
        ))

    # ---------------------------------------------------------
    # Metric 5: Revenue vs EPS Alignment
    # ---------------------------------------------------------
    if rev_cagr is not None and eps_cagr is not None:
        gap = eps_cagr - rev_cagr
        evidence["growth_rev_eps_alignment"] = {"revCagr5y": rev_cagr, "epsCagr5y": eps_cagr, "gap": gap}

        if abs(gap) <= 0.05:
            add(MetricResult("M5", "Revenue vs EPS Alignment", "pass", 1))
        elif gap >= 0.10:
            add(MetricResult(
                "M5", "Revenue vs EPS Alignment", "caution", 0,
                DiagnosticFlag(
                    code="R1-ALIGNMENT",
                    severity="medium",
                    message=f"EPS CAGR exceeds revenue CAGR by {gap:.1%}. Possible buybacks/cost cutting.",
                    evidence={"gap": gap, "revCagr5y": rev_cagr, "epsCagr5y": eps_cagr},
                    recommendation="Investigate margins, buybacks, and share count trends."
                )
            ))
        elif abs(rev_cagr) <= 0.01 and eps_cagr >= 0.05:
            add(MetricResult(
                "M5", "Revenue vs EPS Alignment", "caution", 0,
                DiagnosticFlag(
                    code="R1-ALIGNMENT",
                    severity="medium",
                    message="Revenue flat but EPS growing. Potential financial engineering risk.",
                    evidence={"revCagr5y": rev_cagr, "epsCagr5y": eps_cagr},
                    recommendation="Deep dive into share count, margin expansion, and one-time items."
                )
            ))
        else:
            add(MetricResult(
                "M5", "Revenue vs EPS Alignment", "caution", 0,
                DiagnosticFlag(
                    code="R1-ALIGNMENT",
                    severity="low",
                    message="Revenue and EPS growth are not well aligned. Investigate drivers.",
                    evidence={"revCagr5y": rev_cagr, "epsCagr5y": eps_cagr, "gap": gap},
                )
            ))
    else:
        add(MetricResult(
            "M5", "Revenue vs EPS Alignment", "caution", 0,
            DiagnosticFlag(
                code="R1-ALIGNMENT",
                severity="low",
                message="Insufficient data to compare revenue vs EPS alignment.",
            )
        ))

    # ---------------------------------------------------------
    # Metric 6: EPS Drawdown (cyclicality)
    # ---------------------------------------------------------
    dd = _eps_drawdown(eps_rows, "eps", window_years=5)
    evidence["cyclicality_eps_drawdown_5y"] = dd
    if dd is None:
        add(MetricResult(
            "M6", "EPS Drawdown (5y)", "caution", 0,
            DiagnosticFlag(
                code="R1-DRAWDOWN",
                severity="low",
                message="Insufficient EPS series to compute drawdown.",
            )
        ))
    elif dd < 0.30:
        add(MetricResult("M6", "EPS Drawdown (5y)", "pass", 1))
    elif dd <= 0.60:
        add(MetricResult(
            "M6", "EPS Drawdown (5y)", "caution", 0,
            DiagnosticFlag(
                code="R1-DRAWDOWN",
                severity="medium",
                message=f"EPS drawdown is {dd:.0%} (moderate cyclicality).",
                evidence={"drawdown": dd},
                recommendation="Normalize EPS and use conservative growth."
            )
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "M6", "EPS Drawdown (5y)", "fail", 0,
            DiagnosticFlag(
                code="R1-DRAWDOWN",
                severity="critical",
                message=f"EPS drawdown is {dd:.0%} (deep cycle). Avoid Rule #1.",
                evidence={"drawdown": dd},
                recommendation="Avoid Rule #1; consider cycle-adjusted models or DCF with scenarios."
            )
        ))

    # ---------------------------------------------------------
    # Metric 7: Debt to Equity (exclude financials)
    # ---------------------------------------------------------
    exclude_bs_metrics = sector in SECTOR_FIN
    if exclude_bs_metrics:
        add(MetricResult(
            "M7", "Debt to Equity", "na", 0,
            DiagnosticFlag(
                code="R1-DEBT-EQUITY",
                severity="info",
                message="Debt/Equity test excluded for financials/banks.",
                evidence={"sector": sector},
            )
        ))
    else:
        dte = _safe_float((derived_latest or {}).get("debt_to_equity"))
        if dte is None:
            total_debt = _safe_float(bs_latest.get("total_debt")) if bs_latest else None
            equity = _safe_float(bs_latest.get("shareholders_equity")) if bs_latest else None
            if total_debt is not None and equity is not None:
                if equity <= 0:
                    dte = None
                    hard_fail = True
                    add(MetricResult(
                        "M7", "Debt to Equity", "fail", 0,
                        DiagnosticFlag(
                            code="R1-DEBT-EQUITY",
                            severity="critical",
                            message="Shareholders' equity is <= 0; leverage risk is high / ratio not meaningful. Avoid Rule #1.",
                            evidence={"equity": equity, "totalDebt": total_debt},
                        )
                    ))
                else:
                    dte = total_debt / equity
            evidence["balance_debt_to_equity"] = dte
        # if we already emitted the negative equity fail above, skip normal evaluation
        if hard_fail and any(r.id == "M7" and r.status == "fail" for r in results):
            pass
        elif dte is None:
            add(MetricResult(
                "M7", "Debt to Equity", "caution", 0,
                DiagnosticFlag(
                    code="R1-DEBT-EQUITY",
                    severity="low",
                    message="Could not compute Debt/Equity (missing debt or equity).",
                )
            ))
        elif dte < 0.8:
            add(MetricResult("M7", "Debt to Equity", "pass", 1))
        elif dte <= 1.5:
            add(MetricResult(
                "M7", "Debt to Equity", "caution", 0,
                DiagnosticFlag(
                    code="R1-DEBT-EQUITY",
                    severity="medium",
                    message=f"Debt/Equity is {dte:.2f} (moderate). Use conservative assumptions.",
                    evidence={"debtToEquity": dte},
                )
            ))
        else:
            hard_fail = True
            add(MetricResult(
                "M7", "Debt to Equity", "fail", 0,
                DiagnosticFlag(
                    code="R1-DEBT-EQUITY",
                    severity="critical",
                    message=f"Debt/Equity is {dte:.2f} (risky). Avoid Rule #1.",
                    evidence={"debtToEquity": dte},
                    recommendation="Avoid Rule #1; require stronger balance sheet or use stress-tested DCF."
                )
            ))

    # ---------------------------------------------------------
    # Metric 8: Interest Coverage (EBIT / Interest Expense) exclude financials
    # ---------------------------------------------------------
    if exclude_bs_metrics:
        add(MetricResult(
            "M8", "Interest Coverage", "na", 0,
            DiagnosticFlag(
                code="R1-INT-COV",
                severity="info",
                message="Interest coverage test excluded for financials/banks.",
                evidence={"sector": sector},
            )
        ))
    else:
        ic = _safe_float((derived_latest or {}).get("interest_coverage"))
        if ic is None:
            ebit = _safe_float(is_latest.get("ebit")) if is_latest else None
            interest = _safe_float(is_latest.get("interest_expense")) if is_latest else None
            if ebit is not None and interest is not None:
                if interest == 0 and ebit > 0:
                    ic = math.inf
                elif interest != 0:
                    ic = ebit / abs(interest)
            evidence["balance_interest_coverage"] = ic

        if ic is None:
            add(MetricResult(
                "M8", "Interest Coverage", "caution", 0,
                DiagnosticFlag(
                    code="R1-INT-COV",
                    severity="low",
                    message="Could not compute interest coverage (missing EBIT or interest expense).",
                )
            ))
        elif ic > 5.0:
            add(MetricResult("M8", "Interest Coverage", "pass", 1))
        elif ic >= 3.0:
            add(MetricResult(
                "M8", "Interest Coverage", "caution", 0,
                DiagnosticFlag(
                    code="R1-INT-COV",
                    severity="medium",
                    message=f"Interest coverage is {ic:.1f}x (caution).",
                    evidence={"interestCoverage": ic},
                )
            ))
        else:
            hard_fail = True
            add(MetricResult(
                "M8", "Interest Coverage", "fail", 0,
                DiagnosticFlag(
                    code="R1-INT-COV",
                    severity="critical",
                    message=f"Interest coverage is {ic:.1f}x (dangerous). Avoid Rule #1.",
                    evidence={"interestCoverage": ic},
                )
            ))

    # ---------------------------------------------------------
    # Metric 9: FCF Conversion (FCF / Net Income)
    # FCF = CFO +/- CapEx (sign-normalized; do NOT assume sign convention)
    # ---------------------------------------------------------
    conv: float | None = None
    fcf: float | None = None
    capex_rule: str = "n/a"

    # Prefer derived metrics if present (safe: does not assume keys exist)
    if derived_latest:
        conv = _safe_float(derived_latest.get("fcf_conversion"))
        fcf = _safe_float(derived_latest.get("free_cash_flow"))
        if conv is not None:
            capex_rule = "derived"

    # Fallback only if derived is missing or unusable (keys may differ; debug keys are emitted above)
    if conv is None:
        cfo = _safe_float(cf_latest.get("cash_from_operating_activities")) if cf_latest else None
        capex = _safe_float(cf_latest.get("capital_expenditures")) if cf_latest else None
        ni_latest = _safe_float(is_latest.get("net_income_to_common")) if is_latest else None

        if cfo is not None and capex is not None:
            if capex < 0:
                fcf = cfo + capex
                capex_rule = "fallback: fcf=cfo+capex (capex negative)"
            else:
                fcf = cfo - capex
                capex_rule = "fallback: fcf=cfo-capex (capex positive)"

        if fcf is not None and ni_latest is not None and ni_latest != 0:
            conv = fcf / ni_latest

    evidence["cashflow_fcf_conversion"] = {
        "fcf": fcf,
        "capexRule": capex_rule,
        "fcfConversion": conv
        }

    if conv is None:
        add(MetricResult(
            "M9", "FCF Conversion", "caution", 0,
            DiagnosticFlag(
                code="R1-FCF-CONV",
                severity="low",
                message="Could not compute FCF conversion (missing CFO/CapEx/Net Income).",
            )
        ))
    elif conv >= 0.70:
        add(MetricResult("M9", "FCF Conversion", "pass", 1))
    elif conv >= 0.50:
        add(MetricResult(
            "M9", "FCF Conversion", "caution", 0,
            DiagnosticFlag(
                code="R1-FCF-CONV",
                severity="medium",
                message=f"FCF conversion is {conv:.0%} (acceptable).",
                evidence={"fcfConversion": conv},
            )
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "M9", "FCF Conversion", "fail", 0,
            DiagnosticFlag(
                code="R1-FCF-CONV",
                severity="critical",
                message=f"FCF conversion is {conv:.0%} (low quality earnings). Avoid Rule #1.",
                evidence={"fcfConversion": conv},
            )
        ))

    # ---------------------------------------------------------
    # Metric 10: Share Dilution (5y annualized change)
    # Pass: <= 0%
    # Caution: 1–5% annual
    # Fail: > 5% annual
    # ---------------------------------------------------------
    share_pairs = _take_last_n_years(shares_rows, "shares_outstanding_diluted", 6)  # 5y span needs 6 points
    dilution_rate = None
    if len(share_pairs) >= 2:
        y0, s0 = share_pairs[0]
        yN, sN = share_pairs[-1]
        years = yN - y0
        if years <= 0:
            years = 5
        dilution_rate = _cagr(s0, sN, years)
    evidence["cashflow_share_dilution_cagr"] = dilution_rate

    if dilution_rate is None:
        add(MetricResult(
            "M10", "Share Dilution (5y)", "caution", 0,
            DiagnosticFlag(
                code="R1-DILUTION",
                severity="low",
                message="Insufficient share count history to evaluate dilution.",
            )
        ))
    elif dilution_rate <= 0.0:
        add(MetricResult("M10", "Share Dilution (5y)", "pass", 1))
    elif dilution_rate <= 0.05:
        add(MetricResult(
            "M10", "Share Dilution (5y)", "caution", 0,
            DiagnosticFlag(
                code="R1-DILUTION",
                severity="medium",
                message=f"Shares growing at {dilution_rate:.1%}/yr (mild dilution).",
                evidence={"shareCagr": dilution_rate},
            )
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "M10", "Share Dilution (5y)", "fail", 0,
            DiagnosticFlag(
                code="R1-DILUTION",
                severity="critical",
                message=f"Shares growing at {dilution_rate:.1%}/yr (heavy dilution). Avoid Rule #1.",
                evidence={"shareCagr": dilution_rate},
            )
        ))

    # ---------------------------------------------------------
    # Metric 11: ROIC (5y avg)
    # thresholds: >=15% pass, 10–15 caution, <10 fail
    # ---------------------------------------------------------
    roic_pairs = _take_last_n_years(roic_rows, "roic", 5)
    roic_avg = None
    if len(roic_pairs) >= 3:
        vals = [v for _, v in roic_pairs]
        # normalize if stored as percent (>1.0 likely means percent units)
        norm = []
        for v in vals:
            norm.append(v / 100.0 if v > 1.0 else v)
        roic_avg = _mean(norm)
    evidence["compounding_roic_avg_5y"] = roic_avg

    if roic_avg is None:
        add(MetricResult(
            "M11", "ROIC (5y avg)", "caution", 0,
            DiagnosticFlag(
                code="R1-ROIC",
                severity="low",
                message="Insufficient ROIC history to evaluate compounding engine.",
            )
        ))
    elif roic_avg >= 0.15:
        add(MetricResult("M11", "ROIC (5y avg)", "pass", 1))
    elif roic_avg >= 0.10:
        add(MetricResult(
            "M11", "ROIC (5y avg)", "caution", 0,
            DiagnosticFlag(
                code="R1-ROIC",
                severity="medium",
                message=f"ROIC is {roic_avg:.1%} (good). Use conservative inputs.",
                evidence={"roicAvg5y": roic_avg},
            )
        ))
    else:
        hard_fail = True
        add(MetricResult(
            "M11", "ROIC (5y avg)", "fail", 0,
            DiagnosticFlag(
                code="R1-ROIC",
                severity="critical",
                message=f"ROIC is {roic_avg:.1%} (weak). Avoid Rule #1.",
                evidence={"roicAvg5y": roic_avg},
            )
        ))

    # ---------------------------------------------------------
    # Final score aggregation (points for passes only)
    # ---------------------------------------------------------
    total_possible = sum(1 for r in results if r.status != "na")
    points = sum(r.points for r in results)
    score_0_100 = _points_to_score(points, total_possible)
    category = _category_from_points(points, total_possible, hard_fail)

    evidence["final_scoring"] = {
        "points": points,
        "totalPossible": total_possible,
        "score0to100": score_0_100,
        "category": category,
        "hardFail": hard_fail,
    }

    # Expose missing/coverage explicitly for UI
    evidence["data_coverage"] = coverage
    flags.insert(0, DiagnosticFlag(
        code="R1-DATA-COVERAGE",
        severity="info",
        message="Suitability data coverage summary (missing inputs may reduce confidence).",
        evidence=coverage,
        recommendation="Backfill missing fiscal years / statements to reduce 'unknowns' in suitability."
    ))

    # Add a summary diagnostic (info) so it’s transparent & spreadsheet-friendly
    flags.insert(0, DiagnosticFlag(
        code="R1-SCORECARD",
        severity="info",
        message=f"Rule #1 suitability score: {points}/{total_possible} passes (mapped to {score_0_100}/100).",
        evidence=evidence["final_scoring"],
        recommendation="Use deep-dive diagnostics to understand which tests failed or need investigation."
    ))

    return score_0_100, category, flags, evidence
