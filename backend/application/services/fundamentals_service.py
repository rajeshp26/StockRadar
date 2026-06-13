from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from schemas_fundamentals import (
    DataQuality,
    FundamentalsResponse,
    GaugeConfig,
    IntrinsicValuation,
    MetricComponent,
    MetricQuarterSeries,
    MetricSection,
    QuarterDataPoint,
    SectionStatus,
)
from infrastructure.repositories.fundamentals_repository import FundamentalsRepository

logger = logging.getLogger(__name__)


def _f(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (ValueError, TypeError):
        return None


def _safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _quarter_label(fy: int, fq: Optional[int]) -> str:
    if fq is None:
        return str(fy)
    return f"Q{fq} {fy}"


def _align_ttm_components(
    fiscal_year: int,
    fiscal_quarter: int,
    eps_lookup: Dict[Tuple[int, int], float],
) -> Tuple[Optional[float], List[MetricComponent]]:
    components: List[MetricComponent] = []
    ttm_sum = 0.0
    has_any = False
    found_all = True
    for offset in range(4):
        y, q = fiscal_year, fiscal_quarter - offset
        while q < 1:
            y -= 1
            q += 4
        eps = eps_lookup.get((y, q))
        if eps is not None:
            components.append(MetricComponent(
                label=_quarter_label(y, q), value=eps,
                highlight="driver" if offset == 0 and eps < 0 else None,
            ))
            ttm_sum += eps
            has_any = True
        else:
            components.append(MetricComponent(label=_quarter_label(y, q), value=None))
            found_all = False
    if not has_any:
        return None, []
    return ttm_sum, components


def _quarters_chronological(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        rows,
        key=lambda x: (
            x.get("fiscal_year") if isinstance(x.get("fiscal_year"), (int, float)) else 0,
            x.get("fiscal_quarter") if isinstance(x.get("fiscal_quarter"), (int, float)) else -1,
        ),
    )


# ── Trend direction helpers ──────────────────────────────────────────────

def _determine_trend(
    values: List[Optional[float]], higher_is_better: bool
) -> Tuple[str, Optional[float], str]:
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return ("stable", None, "stable")
    first, last = clean[0], clean[-1]
    if first == 0:
        return ("stable", None, "stable")
    pct_change = (last - first) / abs(first)
    if abs(pct_change) < 0.05:
        return ("stable", pct_change, "stable")
    improving = (last > first and higher_is_better) or (last < first and not higher_is_better)
    direction = "up" if improving else "down"
    label = f"{pct_change:+.1%}"
    return (direction, pct_change, label)


def _build_quarter_series(
    metric_id: str,
    label: str,
    unit: str,
    rows: List[Dict[str, Any]],
    value_key: str,
    higher_is_better: bool,
    buy_idx: Optional[int] = None,
    narrative_key: Optional[str] = None,
    is_annual: bool = False,
) -> MetricQuarterSeries:
    sorted_rows = _quarters_chronological(rows)
    quarters: List[QuarterDataPoint] = []
    vals: List[Optional[float]] = []
    for r in sorted_rows:
        fy = r.get("fiscal_year")
        fq = r.get("fiscal_quarter")
        v = _f(r.get(value_key))
        vals.append(v)
        fq_val: Optional[int] = int(fq) if fq is not None else None
        qp = QuarterDataPoint(
            fiscal_year=int(fy) if fy else 0,
            fiscal_quarter=fq_val if fq_val is not None else 0,
            label=_quarter_label(int(fy), fq_val) if fy else "",
            value=v,
            narrative_label=str(r.get(narrative_key)) if narrative_key and r.get(narrative_key) else None,
        )
        quarters.append(qp)
    direction, change_pct, change_label = _determine_trend(vals, higher_is_better)
    return MetricQuarterSeries(
        metric_id=metric_id,
        label=label,
        unit=unit,
        quarters=quarters,
        buy_quarter_index=buy_idx,
        trend_direction=direction,
        change_pct=change_pct,
        change_label=change_label,
    )


def _compute_section_status(score: Optional[float]) -> SectionStatus:
    if score is None:
        return SectionStatus(label="Watch")
    if score >= 70:
        return SectionStatus(label="Intact")
    if score >= 40:
        return SectionStatus(label="Watch")
    return SectionStatus(label="Concern")


# ── Quality Section ──────────────────────────────────────────────────────

def _compute_quality_metrics(
    ratios: List[Dict[str, Any]], buy_idx: Optional[int] = None,
    is_annual: bool = False,
) -> MetricSection:
    if not ratios:
        return MetricSection(
            section_id="quality",
            title="Quality metrics",
            metrics=[],
            status=_compute_section_status(None),
            score=None,
        )

    metrics = [
        _build_quarter_series("roic", "ROIC", "%", ratios, "roic", True, buy_idx, is_annual=is_annual),
        _build_quarter_series("roe", "ROE", "%", ratios, "roe", True, buy_idx, is_annual=is_annual),
        _build_quarter_series("gross_margin", "Gross margin", "%", ratios, "gross_margin", True, buy_idx, is_annual=is_annual),
        _build_quarter_series("operating_margin", "Op. margin", "%", ratios, "operating_margin", True, buy_idx, is_annual=is_annual),
        _build_quarter_series("debt_to_equity", "D/E", "x", ratios, "debt_to_equity", False, buy_idx, is_annual=is_annual),
    ]

    # Score: ROIC 40, ROE 30, margins 20, D/E 10
    roic_vals = [_f(r.get("roic")) for r in ratios]
    roe_vals = [_f(r.get("roe")) for r in ratios]
    gm_vals = [_f(r.get("gross_margin")) for r in ratios]
    om_vals = [_f(r.get("operating_margin")) for r in ratios]
    de_vals = [_f(r.get("debt_to_equity")) for r in ratios]

    avg_roic = sum(v for v in roic_vals if v is not None) / len([v for v in roic_vals if v is not None]) if any(v is not None for v in roic_vals) else None
    avg_roe = sum(v for v in roe_vals if v is not None) / len([v for v in roe_vals if v is not None]) if any(v is not None for v in roe_vals) else None
    avg_gm = sum(v for v in gm_vals if v is not None) / len([v for v in gm_vals if v is not None]) if any(v is not None for v in gm_vals) else None
    avg_om = sum(v for v in om_vals if v is not None) / len([v for v in om_vals if v is not None]) if any(v is not None for v in om_vals) else None
    avg_de = sum(v for v in de_vals if v is not None) / len([v for v in de_vals if v is not None]) if any(v is not None for v in de_vals) else None

    score = 0
    if avg_roic is not None:
        if avg_roic >= 0.15: score += 40
        elif avg_roic >= 0.10: score += 25
        elif avg_roic >= 0.05: score += 15
        else: score += 5
    if avg_roe is not None:
        if avg_roe >= 0.20: score += 30
        elif avg_roe >= 0.15: score += 20
        elif avg_roe >= 0.10: score += 10
        else: score += 5
    if avg_gm is not None and avg_gm >= 0.40: score += 10
    elif avg_gm is not None and avg_gm >= 0.20: score += 5
    if avg_om is not None and avg_om >= 0.15: score += 10
    elif avg_om is not None and avg_om >= 0.05: score += 5
    if avg_de is not None and avg_de <= 0.5: score += 10
    elif avg_de is not None and avg_de <= 1.0: score += 5

    return MetricSection(
        section_id="quality",
        title="Quality metrics",
        metrics=metrics,
        status=_compute_section_status(float(score)),
        score=float(score),
    )


# ── Growth Section — YoY% computed on-the-fly ────────────────────────────

def _compute_growth_metrics(
    income_stmts: List[Dict[str, Any]],
    cash_flows: List[Dict[str, Any]],
    buy_idx: Optional[int] = None,
    is_annual: bool = False,
) -> MetricSection:
    def yoy_series(
        metric_id: str, label: str, rows: List[Dict[str, Any]],
        compute_val: callable, buy_idx: Optional[int] = None,
        is_annual: bool = False,
    ) -> MetricQuarterSeries:
        sorted_rows = _quarters_chronological(rows)
        yoy_map: Dict[Tuple[int, int], Tuple[int, int, float]] = {}
        for r in sorted_rows:
            fy = r.get("fiscal_year")
            fq = r.get("fiscal_quarter")
            v = compute_val(r)
            key_fq = 0 if is_annual else (int(fq) if fq is not None else 0)
            if fy is not None and v is not None:
                yoy_map[(int(fy), key_fq)] = (int(fy), key_fq, v)

        quarters: List[QuarterDataPoint] = []
        ordered = sorted(yoy_map.keys())
        for fy, fq_key in ordered:
            _, _, val = yoy_map[(fy, fq_key)]
            prior = yoy_map.get((fy - 1, fq_key))
            if prior is not None:
                _, _, prior_val = prior
                yoy = _safe_div(val - prior_val, abs(prior_val))
                if yoy is not None:
                    yoy_pct = round(yoy * 100, 2)
                else:
                    yoy_pct = None
            else:
                yoy_pct = None
            fq_label: Optional[int] = None if is_annual else fq_key
            quarters.append(QuarterDataPoint(
                fiscal_year=fy,
                fiscal_quarter=fq_key,
                label=_quarter_label(fy, fq_label),
                value=yoy_pct,
            ))

        vals = [q.value for q in quarters]
        direction, change_pct, change_label = _determine_trend(vals, True)
        return MetricQuarterSeries(
            metric_id=metric_id, label=label, unit="%",
            quarters=quarters, buy_quarter_index=buy_idx,
            trend_direction=direction, change_pct=change_pct,
            change_label=change_label,
        )

    inc_sorted = _quarters_chronological(income_stmts)
    cf_sorted = _quarters_chronological(cash_flows)

    revenue_series = yoy_series(
        "revenue_yoy", "Revenue YoY", inc_sorted,
        lambda r: _f(r.get("revenue")), buy_idx, is_annual=is_annual,
    )
    eps_series = yoy_series(
        "eps_yoy", "EPS YoY", inc_sorted,
        lambda r: _safe_div(
            _f(r.get("net_income_to_common")) or _f(r.get("net_income")),
            _f(r.get("shares_outstanding_diluted")) or _f(r.get("shares_outstanding")),
        ), buy_idx, is_annual=is_annual,
    )
    fcf_series = yoy_series(
        "fcf_yoy", "FCF YoY", cf_sorted,
        lambda r: (
            (_f(r.get("cash_from_operating_activities")) or 0)
            + (_f(r.get("capital_expenditures")) or 0)
        ) if (
            _f(r.get("cash_from_operating_activities")) is not None
            and _f(r.get("capital_expenditures")) is not None
        ) else None,
        buy_idx, is_annual=is_annual,
    )

    avg_yoy = []
    for s in [revenue_series, eps_series, fcf_series]:
        vals = [q.value for q in s.quarters if q.value is not None]
        if vals:
            avg_yoy.append(sum(vals) / len(vals))

    score = 0
    if avg_yoy:
        mean = sum(avg_yoy) / len(avg_yoy)
        if mean >= 20: score = 80
        elif mean >= 10: score = 60
        elif mean >= 5: score = 40
        elif mean > 0: score = 20
        else: score = 0

    return MetricSection(
        section_id="growth",
        title="Growth metrics",
        metrics=[revenue_series, eps_series, fcf_series],
        status=_compute_section_status(float(score) if avg_yoy else None),
        score=float(score) if avg_yoy else None,
    )


# ── Moat Signals Section ─────────────────────────────────────────────────

def _compute_moat_metrics(
    ratios: List[Dict[str, Any]], buy_idx: Optional[int] = None,
    is_annual: bool = False,
) -> MetricSection:
    if not ratios:
        return MetricSection(
            section_id="moat",
            title="Moat signals",
            metrics=[],
            status=_compute_section_status(None),
            score=None,
        )

    metrics = [
        _build_quarter_series("piotroski_f", "Piotroski F", "score", ratios, "piotroski_score", True, buy_idx, is_annual=is_annual),
        _build_quarter_series("altman_z", "Altman Z", "score", ratios, "altman_z_score", True, buy_idx, is_annual=is_annual),
        _build_quarter_series("interest_coverage", "Int. coverage", "x", ratios, "interest_coverage", True, buy_idx, is_annual=is_annual),
    ]

    piotroski_vals = [_f(r.get("piotroski_score")) for r in ratios]
    altman_vals = [_f(r.get("altman_z_score")) for r in ratios]
    ic_vals = [_f(r.get("interest_coverage")) for r in ratios]

    latest_piotroski = next((v for v in reversed(piotroski_vals) if v is not None), None)
    latest_altman = next((v for v in reversed(altman_vals) if v is not None), None)
    latest_ic = next((v for v in reversed(ic_vals) if v is not None), None)

    pts = 0
    if latest_piotroski is not None:
        pts += min(45, int(latest_piotroski) * 5)
    if latest_altman is not None:
        if latest_altman >= 3.0: pts += 35
        elif latest_altman >= 2.7: pts += 25
        elif latest_altman >= 1.8: pts += 15
        else: pts += 5
    if latest_ic is not None:
        if latest_ic >= 5: pts += 20
        elif latest_ic >= 2: pts += 10
        elif latest_ic >= 1: pts += 5

    return MetricSection(
        section_id="moat",
        title="Moat signals",
        metrics=metrics,
        status=_compute_section_status(float(pts)),
        score=float(pts),
    )


# ── Sector-aware valuation thresholds ──────────────────────────────────

SECTOR_THRESHOLDS: Dict[str, Dict[str, Optional[float]]] = {
    "Technology":                     {"pe": 28, "ev_ebitda": 20, "pfcf": 28},
    "Communication Services":        {"pe": 22, "ev_ebitda": 15, "pfcf": 22},
    "Consumer Cyclical":             {"pe": 18, "ev_ebitda": 12, "pfcf": 18},
    "Consumer Defensive":            {"pe": 22, "ev_ebitda": 14, "pfcf": 20},
    "Energy":                        {"pe": 11, "ev_ebitda": 5,  "pfcf": 12},
    "Basic Materials":               {"pe": 16, "ev_ebitda": 9,  "pfcf": 16},
    "Industrials":                   {"pe": 20, "ev_ebitda": 13, "pfcf": 20},
    "Financial Services":            {"pe": 13, "ev_ebitda": None, "pfcf": 14},
    "Healthcare":                    {"pe": 22, "ev_ebitda": 15, "pfcf": 22},
    "Real Estate":                   {"pe": 18, "ev_ebitda": 17, "pfcf": 18},
    "Utilities":                     {"pe": 19, "ev_ebitda": 12, "pfcf": 19},
}
DEFAULT_THRESHOLDS: Dict[str, Optional[float]] = {"pe": 15, "ev_ebitda": 10, "pfcf": 15}


def _median_of_recent(values: List[Optional[float]], n: int = 4) -> Optional[float]:
    clean = [v for v in values[-n:] if v is not None and v > 0]
    if not clean:
        return None
    if len(clean) >= 3:
        return sorted(clean)[len(clean) // 2]
    return clean[-1]


# ── Gauge Config Decision Tree ───────────────────────────────────────────

def _coeff_of_variation(values: List[Optional[float]]) -> Optional[float]:
    clean = [v for v in values if v is not None and v > 0]
    if len(clean) < 3:
        return None
    mean = sum(clean) / len(clean)
    if mean == 0:
        return None
    variance = sum((v - mean) ** 2 for v in clean) / len(clean)
    return (variance ** 0.5) / abs(mean)


def _most_recent_positive(quarters: List[QuarterDataPoint]) -> Optional[float]:
    for q in reversed(quarters):
        if q.value is not None and q.value > 0:
            return q.value
    return None


def _positive_values(quarters: List[QuarterDataPoint]) -> List[float]:
    return [q.value for q in quarters if q.status == "normal" and q.value is not None and q.value > 0]


def _na_count(quarters: List[QuarterDataPoint]) -> int:
    return sum(1 for q in quarters if q.status == "not_applicable")


def _compute_metric_gauge_config(
    metric_id: str,
    quarters: List[QuarterDataPoint],
    sector: Optional[str] = None,
    security_type: str = "stock",
) -> GaugeConfig:
    positive = _positive_values(quarters)
    pos_count = len(positive)
    total = len(quarters)
    na = _na_count(quarters)
    raw_current = quarters[-1].value if quarters else None
    current = _most_recent_positive(quarters)
    cov = _coeff_of_variation([q.value for q in quarters])
    min_v = min(positive) if positive else None
    max_v = max(positive) if positive else None
    avg_v = sum(positive) / pos_count if pos_count > 0 else None
    warnings: List[str] = []

    if raw_current is not None and raw_current <= 0 and current is not None:
        for q in reversed(quarters):
            if q.value is not None and q.value > 0:
                warnings.append(f"Recent losses — {metric_id.upper()} based on {q.label}")
                break

    sector_threshold = DEFAULT_THRESHOLDS.get(metric_id, None)
    if sector and sector in SECTOR_THRESHOLDS and metric_id in SECTOR_THRESHOLDS[sector]:
        sector_threshold = SECTOR_THRESHOLDS[sector][metric_id]

    if cov is not None and cov > 1.5:
        return GaugeConfig(
            display_mode="slider", benchmark="none",
            current_value=current, current_quarter_raw=raw_current,
            min_value=min_v, max_value=max_v, avg_value=avg_v,
            positive_count=pos_count, total_quarters=total,
            na_count=na, warnings=["Extreme variance — may be unreliable"],
        )

    if metric_id == "pe":
        if pos_count >= 16 and cov is not None and cov < 0.5:
            return GaugeConfig(
                display_mode="gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.85 if avg_v else None,
                band_high=avg_v * 1.25 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
            )
        if pos_count >= 12 and cov is not None and cov < 0.5:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.85 if avg_v else None,
                band_high=avg_v * 1.25 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Limited history — bands based on 3 years"],
            )
        if pos_count >= 12 and cov is not None and cov < 0.75:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.85 if avg_v else None,
                band_high=avg_v * 1.25 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Moderate variance — bands are wider"],
            )
        if current is not None and sector_threshold is not None:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="sector",
                benchmark_value=sector_threshold,
                band_low=sector_threshold * 0.85,
                band_high=sector_threshold * 1.25,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Limited history or high variance — showing sector benchmark"],
            )
        return GaugeConfig(
            display_mode="slider", benchmark="none",
            current_value=current, current_quarter_raw=raw_current,
            min_value=min_v, max_value=max_v, avg_value=avg_v,
            positive_count=pos_count, total_quarters=total,
            na_count=na,
        )

    if metric_id == "ev_ebitda":
        if sector == "Financial Services":
            return GaugeConfig(
                display_mode="disabled", benchmark="none",
                current_value=current, current_quarter_raw=raw_current,
                positive_count=pos_count, total_quarters=total, na_count=na,
                warnings=["EV/EBITDA not meaningful for financials — use P/E or P/B"],
            )
        if pos_count >= 16 and cov is not None and cov < 0.5:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.80 if avg_v else None,
                band_high=avg_v * 1.30 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
            )
        if pos_count >= 12 and cov is not None and cov < 0.75:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.80 if avg_v else None,
                band_high=avg_v * 1.30 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Moderate variance — bands are wider"],
            )
        if pos_count >= 12 and cov is not None and cov >= 0.75:
            if sector_threshold is not None:
                return GaugeConfig(
                    display_mode="compact_gauge", benchmark="sector",
                    benchmark_value=sector_threshold,
                    band_low=sector_threshold * 0.80,
                    band_high=sector_threshold * 1.30,
                    current_value=current, current_quarter_raw=raw_current,
                    min_value=min_v, max_value=max_v, avg_value=avg_v,
                    positive_count=pos_count, total_quarters=total,
                    na_count=na,
                    warnings=["High own-stock variance — showing sector benchmark"],
                )
            return GaugeConfig(
                display_mode="slider", benchmark="none",
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
            )
        if pos_count < 12 and sector_threshold is not None:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="sector",
                benchmark_value=sector_threshold,
                band_low=sector_threshold * 0.80,
                band_high=sector_threshold * 1.30,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Limited history — showing sector benchmark"],
            )
        return GaugeConfig(
            display_mode="slider", benchmark="none",
            current_value=current, current_quarter_raw=raw_current,
            min_value=min_v, max_value=max_v, avg_value=avg_v,
            positive_count=pos_count, total_quarters=total,
            na_count=na,
        )

    if metric_id == "pfcf":
        if pos_count >= 16 and cov is not None and cov < 0.5:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.75 if avg_v else None,
                band_high=avg_v * 1.35 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
            )
        if pos_count >= 16 and cov is not None and cov < 0.75:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="historical",
                benchmark_value=avg_v,
                band_low=avg_v * 0.75 if avg_v else None,
                band_high=avg_v * 1.35 if avg_v else None,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Higher variance — bands wider than P/E"],
            )
        if current is not None and sector_threshold is not None and pos_count >= 12:
            return GaugeConfig(
                display_mode="compact_gauge", benchmark="sector",
                benchmark_value=sector_threshold,
                band_low=sector_threshold * 0.75,
                band_high=sector_threshold * 1.35,
                current_value=current, current_quarter_raw=raw_current,
                min_value=min_v, max_value=max_v, avg_value=avg_v,
                positive_count=pos_count, total_quarters=total,
                na_count=na,
                warnings=["Limited history — showing sector benchmark"],
            )
        return GaugeConfig(
            display_mode="slider", benchmark="none",
            current_value=current, current_quarter_raw=raw_current,
            min_value=min_v, max_value=max_v, avg_value=avg_v,
            positive_count=pos_count, total_quarters=total,
            na_count=na,
            warnings=["Insufficient data or high variance for banded display"] if pos_count < 16 else [],
        )

    return GaugeConfig(
        display_mode="slider", benchmark="none",
        current_value=current, current_quarter_raw=raw_current,
        positive_count=pos_count, total_quarters=total,
        na_count=na,
    )


# ── Valuation Section ────────────────────────────────────────────────────

def _compute_valuation_metrics(
    company_summary: Optional[Dict[str, Any]],
    valuation_snapshots: Optional[Dict[str, Any]],
    current_price: Optional[float],
    fcf_data: List[Dict[str, Any]],
    qratios: Optional[List[Dict[str, Any]]] = None,
    income_data: Optional[List[Dict[str, Any]]] = None,
    buy_idx: Optional[int] = None,
    security_type: str = "stock",
    sector: Optional[str] = None,
) -> MetricSection:
    if security_type != "stock":
        return MetricSection(
            section_id="valuation",
            title="Valuation",
            metrics=[],
            status=_compute_section_status(None),
            score=None,
        )

    ev_ebitda_current = _f(company_summary.get("enterprise_to_ebitda")) if company_summary else None

    eps_lookup: Dict[Tuple[int, int], float] = {}
    if income_data:
        for row in income_data:
            fy = row.get("fiscal_year")
            fq = row.get("fiscal_quarter")
            eps = _safe_div(_f(row.get("net_income_to_common")),
                             _f(row.get("shares_outstanding_diluted")))
            if fy is not None and fq is not None and eps is not None:
                eps_lookup[(int(fy), int(fq))] = eps

    pe_quarters: List[QuarterDataPoint] = []
    ev_quarters: List[QuarterDataPoint] = []
    pfcf_quarters: List[QuarterDataPoint] = []

    if qratios:
        for r in qratios:
            fq = r.get("fiscal_quarter")
            if fq is None:
                continue
            fy = r.get("fiscal_year")
            if fy is None or fq is None:
                continue
            fy_i, fq_i = int(fy), int(fq)

            pe_val = _f(r.get("trailing_pe"))
            price = _f(r.get("quarter_end_price"))
            ttm, components = _align_ttm_components(fy_i, fq_i, eps_lookup)
            if ttm is not None and ttm > 0:
                pe_status = "normal"
            elif ttm is not None and ttm <= 0:
                pe_status = "not_applicable"
            else:
                pe_status = "insufficient_data"
            pe_quarters.append(QuarterDataPoint(
                fiscal_year=fy_i, fiscal_quarter=fq_i,
                label=_quarter_label(fy_i, fq_i),
                value=pe_val, status=pe_status,
                ttm_eps=ttm, components=components or None,
                quarter_end_price=price,
            ))

            ev_val = _f(r.get("ev_ebitda"))
            ev_ebitda = _f(r.get("ebitda"))
            ev = _f(r.get("enterprise_value"))
            ev_components = []
            if ev is not None:
                ev_components.append(MetricComponent(label="Enterprise Value", value=ev))
            if ev_ebitda is not None:
                ev_components.append(MetricComponent(
                    label="EBITDA", value=ev_ebitda,
                    highlight="negative" if ev_ebitda <= 0 else None,
                ))
            ev_status: str = "normal" if ev_val is not None else (
                "not_applicable" if ev_ebitda is not None and ev_ebitda <= 0
                else "insufficient_data"
            )
            ev_quarters.append(QuarterDataPoint(
                fiscal_year=fy_i, fiscal_quarter=fq_i,
                label=_quarter_label(fy_i, fq_i),
                value=ev_val, status=ev_status,
                components=ev_components or None,
            ))

            pfcf_val = _f(r.get("price_to_fcf"))
            fcf = _f(r.get("free_cash_flow"))
            pfcf_components = []
            if ev is not None:
                pfcf_components.append(MetricComponent(label="Enterprise Value", value=ev))
            if fcf is not None:
                pfcf_components.append(MetricComponent(
                    label="Free Cash Flow", value=fcf,
                    highlight="negative" if fcf <= 0 else None,
                ))
            pfcf_status: str = "normal" if pfcf_val is not None else (
                "not_applicable" if fcf is not None and fcf <= 0
                else "insufficient_data"
            )
            pfcf_quarters.append(QuarterDataPoint(
                fiscal_year=fy_i, fiscal_quarter=fq_i,
                label=_quarter_label(fy_i, fq_i),
                value=pfcf_val, status=pfcf_status,
                components=pfcf_components or None,
            ))

    pe_values = [q.value for q in pe_quarters]
    pe_dir, pe_pct, pe_label = _determine_trend(pe_values, False)
    pe_series = MetricQuarterSeries(
        metric_id="pe_ratio", label="P/E", unit="x",
        quarters=pe_quarters, buy_quarter_index=buy_idx,
        trend_direction=pe_dir, change_pct=pe_pct,
        change_label=pe_label if pe_quarters else "current snapshot",
        gauge_config=_compute_metric_gauge_config("pe", pe_quarters, sector, security_type),
    )
    ev_values = [q.value for q in ev_quarters]
    ev_dir, ev_pct, ev_label = _determine_trend(ev_values, False)
    ev_series = MetricQuarterSeries(
        metric_id="ev_ebitda", label="EV/EBITDA", unit="x",
        quarters=ev_quarters, buy_quarter_index=buy_idx,
        trend_direction=ev_dir, change_pct=ev_pct,
        change_label=ev_label if ev_quarters else "current snapshot",
        gauge_config=_compute_metric_gauge_config("ev_ebitda", ev_quarters, sector, security_type),
    )
    pfcf_values = [q.value for q in pfcf_quarters]
    pfcf_dir, pfcf_pct, pfcf_label = _determine_trend(pfcf_values, False)
    pfcf_series = MetricQuarterSeries(
        metric_id="price_to_fcf", label="P/FCF", unit="x",
        quarters=pfcf_quarters, buy_quarter_index=buy_idx,
        trend_direction=pfcf_dir, change_pct=pfcf_pct,
        change_label=pfcf_label if pfcf_quarters else "current snapshot",
        gauge_config=_compute_metric_gauge_config("pfcf", pfcf_quarters, sector, security_type),
    )

    intrinsic_valuations: List[Dict[str, Any]] = []
    if valuation_snapshots:
        METHOD_KEYS = {
            "dcf":              ["valuation", "intrinsicValuePerShare"],
            "owner_earnings":   ["valuation", "intrinsicValuePerShare"],
            "residual_income":  ["valuation", "intrinsicValuePerShare"],
            "ddm_gordon":       ["valuation", "intrinsicValue"],
            "ddm_two_stage":    ["valuation", "intrinsicValue"],
            "rule1":            ["valuation", "stickerPrice"],
        }
        METHOD_LABELS = {
            "dcf": "DCF", "owner_earnings": "Owner Earnings",
            "residual_income": "Residual Income", "ddm_gordon": "DDM (Gordon)",
            "ddm_two_stage": "DDM (Two-Stage)", "rule1": "Rule #1",
        }
        for method, keys in METHOD_KEYS.items():
            snap = valuation_snapshots.get(method)
            if not snap:
                continue
            if isinstance(snap, str):
                import json
                try:
                    snap = json.loads(snap)
                except (json.JSONDecodeError, TypeError):
                    continue
            val = _f(snap.get(keys[0], {}).get(keys[1])) if len(keys) == 2 else _f(snap.get(keys[0]))
            if val is not None and val > 0:
                intrinsic_valuations.append({
                    "method": METHOD_LABELS.get(method, method),
                    "intrinsic_value": val,
                })

    price_vs_intrinsic = None
    if intrinsic_valuations and current_price is not None:
        avg_iv = sum(v["intrinsic_value"] for v in intrinsic_valuations) / len(intrinsic_valuations)
        price_vs_intrinsic = round(((current_price - avg_iv) / avg_iv) * 100, 2)

    def _flat_series(mid: str, label: str, unit: str, val: Optional[float], higher_is_better: bool) -> MetricQuarterSeries:
        q = QuarterDataPoint(fiscal_year=0, fiscal_quarter=0, label="Current", value=val)
        return MetricQuarterSeries(
            metric_id=mid, label=label, unit=unit,
            quarters=[q], buy_quarter_index=0,
            trend_direction="stable", change_pct=None, change_label="current snapshot",
        )

    metrics = [
        pe_series,
        ev_series,
        pfcf_series,
        _flat_series("price_vs_intrinsic", "Price vs intrinsic", "%", price_vs_intrinsic, False),
    ]

    pe_values = [q.value for q in pe_quarters]
    ev_values = [q.value for q in ev_quarters]
    pfcf_values = [q.value for q in pfcf_quarters]
    med_pe = _median_of_recent(pe_values) if pe_quarters else None
    med_ev = _median_of_recent(ev_values) if ev_quarters else None
    med_pfcf = _median_of_recent(pfcf_values) if pfcf_quarters else None

    if not qratios and company_summary:
        ev_ebitda_current = _f(company_summary.get("enterprise_to_ebitda"))
        ev_current = _f(company_summary.get("enterprise_value"))
        latest_fcf = None
        for r in reversed(fcf_data):
            cfo = _f(r.get("cash_from_operating_activities"))
            capex = _f(r.get("capital_expenditures"))
            if cfo is not None and capex is not None:
                latest_fcf = cfo + capex if capex < 0 else cfo - capex
                break
        pfcf_current = _safe_div(ev_current, latest_fcf) if latest_fcf is not None else None
        metrics = [
            pe_series if pe_quarters else _flat_series("pe_ratio", "P/E", "x", None, False),
            _flat_series("ev_ebitda", "EV/EBITDA", "x", ev_ebitda_current, False),
            _flat_series("price_to_fcf", "P/FCF", "x", pfcf_current, False),
            _flat_series("price_vs_intrinsic", "Price vs intrinsic", "%", price_vs_intrinsic, False),
        ]
        if med_pe is None:
            med_pe = _f(company_summary.get("trailing_pe"))
        if med_ev is None:
            med_ev = ev_ebitda_current
        if med_pfcf is None:
            med_pfcf = pfcf_current

    thresh = DEFAULT_THRESHOLDS.copy()
    if sector and sector in SECTOR_THRESHOLDS:
        thresh = SECTOR_THRESHOLDS[sector]

    score_parts = 0
    score_total = 0
    for metric_val, key in [(med_pe, "pe"), (med_ev, "ev_ebitda"), (med_pfcf, "pfcf")]:
        threshold = thresh.get(key)
        if threshold is None or metric_val is None or metric_val <= 0:
            continue
        score_total += 25
        if metric_val <= threshold:
            score_parts += 25
        elif metric_val <= threshold * 1.67:
            score_parts += 12
    if price_vs_intrinsic is not None:
        score_total += 25
        if price_vs_intrinsic <= 0:
            score_parts += 25
        elif price_vs_intrinsic <= 20:
            score_parts += 12

    score = round((score_parts / score_total) * 100) if score_total > 0 else None

    return MetricSection(
        section_id="valuation",
        title="Valuation",
        metrics=metrics,
        status=_compute_section_status(score),
        score=score,
        intrinsic_valuations=[IntrinsicValuation(**v) for v in intrinsic_valuations] if intrinsic_valuations else None,
        current_price=current_price,
    )


# ── Narrative Section ────────────────────────────────────────────────────

def _compute_narrative_metrics(
    earnings: List[Dict[str, Any]], buy_idx: Optional[int] = None
) -> MetricSection:
    if not earnings:
        return MetricSection(
            section_id="narrative",
            title="Narrative",
            metrics=[],
            status=_compute_section_status(None),
            score=None,
        )

    def _surprise_label(v: Optional[float]) -> Optional[str]:
        if v is None:
            return None
        if v > 0.1:
            return "beat"
        if v < -0.1:
            return "miss"
        return "inline"

    sorted_earnings = _quarters_chronological(earnings)

    eps_quarters: List[QuarterDataPoint] = []
    rev_quarters: List[QuarterDataPoint] = []
    for r in sorted_earnings:
        fy, fq = r.get("fiscal_year"), r.get("fiscal_quarter")
        if not fy or fq is None or fq == 0:
            continue
        eps_v = _f(r.get("eps_surprise_percent"))
        rev_v = _f(r.get("revenue_surprise_percent"))
        eps_quarters.append(QuarterDataPoint(
            fiscal_year=int(fy), fiscal_quarter=int(fq),
            label=_quarter_label(int(fy), int(fq)),
            value=eps_v,
            narrative_label=_surprise_label(eps_v),
        ))
        rev_quarters.append(QuarterDataPoint(
            fiscal_year=int(fy), fiscal_quarter=int(fq),
            label=_quarter_label(int(fy), int(fq)),
            value=rev_v,
            narrative_label=_surprise_label(rev_v),
        ))

    eps_vals = [q.value for q in eps_quarters if q.value is not None]
    beat_count = sum(1 for v in eps_vals if v > 0)
    beat_rate = round((beat_count / len(eps_vals)) * 100, 1) if eps_vals else None

    beat_quarters: List[QuarterDataPoint] = []
    for r in sorted_earnings:
        fy, fq = r.get("fiscal_year"), r.get("fiscal_quarter")
        if not fy or fq is None or fq == 0:
            continue
        beat_quarters.append(QuarterDataPoint(
            fiscal_year=int(fy), fiscal_quarter=int(fq),
            label=_quarter_label(int(fy), int(fq)),
            value=beat_rate,
        ))

    eps_series = MetricQuarterSeries(
        metric_id="eps_surprise", label="EPS surprise", unit="%",
        quarters=eps_quarters, buy_quarter_index=buy_idx,
        trend_direction="stable", change_pct=None, change_label="beat/miss",
    )
    rev_series = MetricQuarterSeries(
        metric_id="revenue_surprise", label="Rev. surprise", unit="%",
        quarters=rev_quarters, buy_quarter_index=buy_idx,
        trend_direction="stable", change_pct=None, change_label="beat/miss",
    )
    br_series = MetricQuarterSeries(
        metric_id="beat_rate", label="Beat rate", unit="%",
        quarters=beat_quarters, buy_quarter_index=buy_idx,
        trend_direction="stable", change_pct=None, change_label="rolling",
    )

    score = 0
    if beat_rate is not None:
        score += min(50, int(beat_rate * 0.5))
    if eps_vals:
        avg_abs = sum(abs(v) for v in eps_vals) / len(eps_vals)
        score += min(50, int(avg_abs * 1.5))
    else:
        score = 0

    return MetricSection(
        section_id="narrative",
        title="Narrative",
        metrics=[eps_series, rev_series, br_series],
        status=_compute_section_status(float(score)),
        score=float(score),
    )


# ── Composite score ──────────────────────────────────────────────────────

def _compute_composite(scores: List[Optional[float]]) -> Optional[float]:
    weights = [0.30, 0.15, 0.25, 0.20, 0.10]
    total_w = 0.0
    weighted_sum = 0.0
    for s, w in zip(scores, weights):
        if s is not None:
            weighted_sum += s * w
            total_w += w
    if total_w == 0:
        return None
    return round(weighted_sum / total_w)


# ── Main service ─────────────────────────────────────────────────────────

class FundamentalsService:
    def __init__(self, repo: FundamentalsRepository):
        self.repo = repo

    async def get_fundamentals(
        self, symbol: str, user_id: Optional[str] = None,
        frequency: str = "quarterly",
    ) -> FundamentalsResponse:
        company = await self.repo.get_company_by_symbol(symbol)
        if not company:
            return FundamentalsResponse(
                success=False, symbol=symbol,
                error=f"Company not found for symbol: {symbol}",
            )

        company_id = company["company_id"]
        company_name = company.get("company_name")
        security_type = company.get("security_type", "stock")
        sector = company.get("sector")

        is_annual = frequency == "annual"
        if is_annual:
            qratios = await self.repo.get_annual_financial_ratios(company_id)
            income_q = await self.repo.get_annual_income_statements(company_id)
            cash_q = await self.repo.get_annual_cash_flows(company_id)
        else:
            qratios = await self.repo.get_quarterly_financial_ratios(company_id)
            income_q = await self.repo.get_quarterly_income_statements(company_id)
            cash_q = await self.repo.get_quarterly_cash_flows(company_id)
        company_summary = await self.repo.get_company_summary_history(company_id)
        valuation_snapshots = await self.repo.get_valuation_snapshots(company_id)
        earnings = await self.repo.get_earnings_history(company_id)
        current_price = await self.repo.get_current_market_price(company_id)

        has_portfolio_position = False
        purchase_date = None
        purchase_period = None
        if user_id:
            anchor = await self.repo.get_buy_anchor(company_id, user_id)
            if anchor:
                has_portfolio_position = True
                pd = anchor.get("transaction_date")
                if pd:
                    purchase_date = str(pd)
                    try:
                        purchase_period = str(pd)[:7]
                    except (IndexError, TypeError):
                        pass

        # Build quarter columns from all available data sources
        all_quarters: set = set()
        for r in qratios:
            fy, fq = r.get("fiscal_year"), r.get("fiscal_quarter")
            if fy:
                key_fq = 0 if is_annual else (int(fq) if fq is not None else 0)
                all_quarters.add((int(fy), key_fq))
        for r in income_q:
            fy, fq = r.get("fiscal_year"), r.get("fiscal_quarter")
            if fy:
                key_fq = 0 if is_annual else (int(fq) if fq is not None else 0)
                all_quarters.add((int(fy), key_fq))
        sorted_q = sorted(all_quarters)
        quarter_labels = [_quarter_label(fy, fq if not is_annual else None) for fy, fq in sorted_q]

        # Compute buy quarter index
        first_quarter = sorted_q[0] if sorted_q else None
        buy_quarter_index = None
        if has_portfolio_position and purchase_date and first_quarter:
            try:
                pd = datetime.strptime(str(purchase_date)[:10], "%Y-%m-%d").date()
                pd_year, pd_month = pd.year, pd.month
                pd_quarter = (pd_month - 1) // 3 + 1
                for i, (fy, fq) in enumerate(sorted_q):
                    if (fy > pd_year) or (not is_annual and fy == pd_year and fq >= pd_quarter):
                        buy_quarter_index = i
                        break
            except (ValueError, TypeError):
                pass

        # Earliest data year across all sources
        earliest_year = None
        all_fys = set()
        for src in (qratios, income_q, cash_q):
            for r in src:
                fy = r.get("fiscal_year")
                if fy:
                    all_fys.add(int(fy))
        for r in earnings:
            fy = r.get("fiscal_year")
            if fy:
                all_fys.add(int(fy))
        if all_fys:
            earliest_year = min(all_fys)

        data_quality = DataQuality(earliest_data_year=earliest_year, quarterly_data_count=len(sorted_q))

        # Compute 5 sections
        summary_row = company_summary[0] if company_summary else {}
        quality = _compute_quality_metrics(qratios, buy_quarter_index, is_annual=is_annual)
        growth = _compute_growth_metrics(income_q, cash_q, buy_quarter_index, is_annual=is_annual)
        moat = _compute_moat_metrics(qratios, buy_quarter_index, is_annual=is_annual)
        valuation = _compute_valuation_metrics(summary_row, valuation_snapshots, current_price, cash_q, qratios, income_q, buy_quarter_index, security_type=security_type, sector=sector)
        narrative = _compute_narrative_metrics(earnings, buy_quarter_index)

        sections = [quality, growth, moat, valuation, narrative]

        composite = _compute_composite([s.score for s in sections])

        return FundamentalsResponse(
            success=True, symbol=symbol, company_name=company_name,
            has_portfolio_position=has_portfolio_position,
            purchase_date=datetime.strptime(str(purchase_date)[:10], "%Y-%m-%d").date() if purchase_date else None,
            purchase_period=purchase_period,
            quarters=quarter_labels,
            buy_quarter_index=buy_quarter_index,
            composite_score=composite,
            sections=sections,
            data_quality=data_quality,
        )
