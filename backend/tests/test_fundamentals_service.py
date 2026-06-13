from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from application.services.fundamentals_service import (
    _compute_quality_metrics,
    _compute_growth_metrics,
    _compute_moat_metrics,
    _compute_narrative_metrics,
    _compute_valuation_metrics,
    _compute_section_status,
    _compute_composite,
    _determine_trend,
    _build_quarter_series,
    _quarter_label,
    _f,
    _safe_div,
    _align_ttm_components,
)


def make_qratio(
    fiscal_year: int,
    fiscal_quarter: int,
    roic: Optional[float] = None,
    roe: Optional[float] = None,
    gross_margin: Optional[float] = None,
    operating_margin: Optional[float] = None,
    debt_to_equity: Optional[float] = None,
    piotroski_score: Optional[float] = None,
    altman_z_score: Optional[float] = None,
    interest_coverage: Optional[float] = None,
) -> Dict[str, Any]:
    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "roic": roic,
        "roe": roe,
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "debt_to_equity": debt_to_equity,
        "piotroski_score": piotroski_score,
        "altman_z_score": altman_z_score,
        "interest_coverage": interest_coverage,
    }


def make_qincome(
    fiscal_year: int,
    fiscal_quarter: int,
    revenue: float,
    net_income: float,
    shares: float = 100_000_000,
) -> Dict[str, Any]:
    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "revenue": revenue,
        "net_income": net_income,
        "net_income_to_common": net_income,
        "shares_outstanding_diluted": shares,
    }


def make_qcf(
    fiscal_year: int,
    fiscal_quarter: int,
    cfo: float,
    capex: float,
) -> Dict[str, Any]:
    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "cash_from_operating_activities": cfo,
        "capital_expenditures": capex,
    }


def make_earnings(
    fiscal_year: int,
    fiscal_quarter: int,
    eps_surprise: Optional[float],
    rev_surprise: Optional[float],
) -> Dict[str, Any]:
    return {
        "fiscal_year": fiscal_year,
        "fiscal_quarter": fiscal_quarter,
        "eps_surprise_percent": eps_surprise,
        "revenue_surprise_percent": rev_surprise,
    }


# ─── Test helpers ─────────────────────────────────────────────────────────────

class TestHelpers:
    def test_f_parses_float(self):
        assert _f(42.5) == 42.5
        assert _f("12.3") == 12.3
        assert _f(None) is None
        assert _f("invalid") is None

    def test_safe_div(self):
        assert _safe_div(10, 2) == 5.0
        assert _safe_div(10, 0) is None
        assert _safe_div(None, 2) is None
        assert _safe_div(10, None) is None

    def test_quarter_label(self):
        assert _quarter_label(2025, 2) == "Q2 2025"
        assert _quarter_label(2024, 4) == "Q4 2024"

    def test_determine_trend(self):
        dir_, pct, label = _determine_trend([1.0, 1.5, 2.0], True)
        assert dir_ == "up"
        assert pct is not None
        assert "+" in label

        dir_, pct, label = _determine_trend([2.0, 1.5, 1.0], True)
        assert dir_ == "down"
        assert pct is not None
        assert "-" in label

        dir_, pct, label = _determine_trend([1.0, 1.02, 1.04], True)
        assert dir_ == "stable"

        dir_, pct, label = _determine_trend([1.0], True)
        assert dir_ == "stable"

        dir_, pct, label = _determine_trend([], True)
        assert dir_ == "stable"

    def test_determine_trend_lower_is_better(self):
        dir_, pct, label = _determine_trend([2.0, 1.5, 1.0], False)
        assert dir_ == "up"
        assert pct is not None

        dir_, pct, label = _determine_trend([1.0, 1.5, 2.0], False)
        assert dir_ == "down"

    def test_compute_section_status(self):
        assert _compute_section_status(85).label == "Intact"
        assert _compute_section_status(70).label == "Intact"
        assert _compute_section_status(55).label == "Watch"
        assert _compute_section_status(40).label == "Watch"
        assert _compute_section_status(20).label == "Concern"
        assert _compute_section_status(None).label == "Watch"

    def test_compute_composite(self):
        result = _compute_composite([80, 60, 70, 50, 65])
        assert result is not None
        # 80*0.3 + 60*0.15 + 70*0.25 + 50*0.2 + 65*0.1 = 24+9+17.5+10+6.5 = 67
        assert result == 67

        result = _compute_composite([None, 60, 70, None, 65])
        assert result is not None
        assert result == 66

        result = _compute_composite([None, None, None, None, None])
        assert result is None

    def test_build_quarter_series(self):
        rows = [
            {"fiscal_year": 2023, "fiscal_quarter": 1, "roic": 0.10},
            {"fiscal_year": 2023, "fiscal_quarter": 2, "roic": 0.12},
            {"fiscal_year": 2023, "fiscal_quarter": 3, "roic": 0.14},
        ]
        series = _build_quarter_series("roic", "ROIC", "%", rows, "roic", True, 1)
        assert series.metric_id == "roic"
        assert series.label == "ROIC"
        assert series.unit == "%"
        assert len(series.quarters) == 3
        assert series.quarters[0].label == "Q1 2023"
        assert series.quarters[0].value == 0.10
        assert series.buy_quarter_index == 1
        assert series.trend_direction == "up"


# ─── Test _compute_quality_metrics ───────────────────────────────────────────

class TestQualityMetrics:
    def test_high_quality(self):
        ratios = [
            make_qratio(2023, 1, roic=0.18, roe=0.25, gross_margin=0.60, operating_margin=0.25, debt_to_equity=0.3),
            make_qratio(2023, 2, roic=0.20, roe=0.28, gross_margin=0.62, operating_margin=0.27, debt_to_equity=0.25),
            make_qratio(2023, 3, roic=0.22, roe=0.30, gross_margin=0.65, operating_margin=0.28, debt_to_equity=0.20),
        ]
        section = _compute_quality_metrics(ratios, buy_idx=1)
        assert section.section_id == "quality"
        assert len(section.metrics) == 5
        assert section.score is not None and section.score >= 70
        assert section.status.label == "Intact"
        assert section.metrics[0].metric_id == "roic"
        assert section.metrics[4].metric_id == "debt_to_equity"

    def test_low_quality(self):
        ratios = [
            make_qratio(2023, 1, roic=0.02, roe=0.03, gross_margin=0.10, operating_margin=0.01, debt_to_equity=2.0),
        ]
        section = _compute_quality_metrics(ratios, buy_idx=0)
        assert section.score is not None and section.score < 40
        assert section.status.label == "Concern"

    def test_empty_ratios(self):
        section = _compute_quality_metrics([])
        assert len(section.metrics) == 0
        assert section.score is None

    def test_partial_data(self):
        ratios = [
            make_qratio(2023, 1, roic=0.10, roe=0.15),
            make_qratio(2023, 2, roic=0.12, roe=0.17),
        ]
        section = _compute_quality_metrics(ratios)
        assert len(section.metrics) == 5
        assert section.score is not None


# ─── Test _compute_growth_metrics ────────────────────────────────────────────

class TestGrowthMetrics:
    def test_strong_growth(self):
        income = [
            make_qincome(2022, 1, 100, 10),
            make_qincome(2022, 2, 110, 11),
            make_qincome(2022, 3, 120, 12),
            make_qincome(2022, 4, 130, 13),
            make_qincome(2023, 1, 150, 15),
            make_qincome(2023, 2, 165, 17),
            make_qincome(2023, 3, 180, 19),
            make_qincome(2023, 4, 200, 21),
        ]
        cf = [
            make_qcf(2022, 1, 15, -3),
            make_qcf(2022, 2, 16, -3),
            make_qcf(2022, 3, 18, -4),
            make_qcf(2022, 4, 20, -4),
            make_qcf(2023, 1, 25, -5),
            make_qcf(2023, 2, 28, -5),
            make_qcf(2023, 3, 30, -6),
            make_qcf(2023, 4, 35, -7),
        ]
        section = _compute_growth_metrics(income, cf, buy_idx=2)
        assert section.section_id == "growth"
        assert len(section.metrics) == 3
        assert section.metrics[0].metric_id == "revenue_yoy"
        # First quarter (2022 Q1) has no prior year → None
        assert section.metrics[0].quarters[0].value is None
        # 2023 Q1 = 150 vs 2022 Q1 = 100 → 50% YoY
        assert section.metrics[0].quarters[4].value is not None
        assert section.metrics[0].quarters[4].value == pytest.approx(50.0, rel=0.1)
        assert section.score is not None and section.score >= 40

    def test_declining_growth(self):
        income = [
            make_qincome(2022, 1, 200, 20),
            make_qincome(2023, 1, 150, 10),
        ]
        cf = [
            make_qcf(2022, 1, 30, -5),
            make_qcf(2023, 1, 20, -4),
        ]
        section = _compute_growth_metrics(income, cf)
        assert section.score is not None
        # Revenue: 150/200 → -25%; should be < 40
        assert section.score < 40

    def test_insufficient_data(self):
        section = _compute_growth_metrics([], [])
        assert section.score is None
        assert section.status.label == "Watch"


# ─── Test _compute_moat_metrics ──────────────────────────────────────────────

class TestMoatMetrics:
    def test_strong_moat(self):
        ratios = [
            make_qratio(2023, 1, piotroski_score=8, altman_z_score=3.5, interest_coverage=8.0),
            make_qratio(2023, 2, piotroski_score=9, altman_z_score=4.0, interest_coverage=10.0),
        ]
        section = _compute_moat_metrics(ratios)
        assert section.section_id == "moat"
        assert len(section.metrics) == 3
        assert section.score is not None and section.score >= 70
        assert section.status.label == "Intact"

    def test_weak_moat(self):
        ratios = [
            make_qratio(2023, 1, piotroski_score=2, altman_z_score=1.2, interest_coverage=0.5),
        ]
        section = _compute_moat_metrics(ratios)
        assert section.score is not None and section.score < 40
        assert section.status.label == "Concern"

    def test_empty(self):
        section = _compute_moat_metrics([])
        assert len(section.metrics) == 0
        assert section.score is None

    def test_none_columns(self):
        ratios = [
            make_qratio(2023, 1, roic=0.10),
            make_qratio(2023, 2, roic=0.12),
        ]
        section = _compute_moat_metrics(ratios)
        assert len(section.metrics) == 3
        assert section.score is not None and section.score < 10


# ─── Test _align_ttm_components ──────────────────────────────────────────────────

class TestAlignTtmComponents:
    def test_four_quarters_positive_ttm(self):
        eps = {(2024, 4): 0.45, (2025, 1): 0.12, (2025, 2): -0.01, (2025, 3): 0.60}
        ttm, comps = _align_ttm_components(2025, 3, eps)
        assert ttm == 1.16
        assert len(comps) == 4
        assert comps[0].label == "Q3 2025" and comps[0].value == 0.60
        assert comps[1].label == "Q2 2025" and comps[1].value == -0.01
        assert comps[2].label == "Q1 2025" and comps[2].value == 0.12
        assert comps[3].label == "Q4 2024" and comps[3].value == 0.45
        assert all(c.highlight is None for c in comps)

    def test_four_quarters_negative_ttm_driver_flag(self):
        eps = {(2025, 1): 0.12, (2025, 2): -0.01, (2025, 3): 0.60, (2025, 4): -2.78}
        ttm, comps = _align_ttm_components(2025, 4, eps)
        assert ttm is not None and ttm < 0
        assert len(comps) == 4
        assert comps[0].value == -2.78 and comps[0].highlight == "driver"
        assert all(c.highlight is None for c in comps[1:])

    def test_partial_data_one_quarter(self):
        eps = {(2022, 2): 0.16}
        ttm, comps = _align_ttm_components(2022, 2, eps)
        assert ttm == 0.16
        assert len(comps) == 4
        assert comps[0].value == 0.16
        assert comps[1].value is None
        assert comps[2].value is None
        assert comps[3].value is None

    def test_no_data(self):
        ttm, comps = _align_ttm_components(2022, 2, {})
        assert ttm is None
        assert comps == []

    def test_cross_year_boundary(self):
        eps = {(2024, 1): 0.10, (2023, 4): 0.20, (2023, 3): 0.30, (2023, 2): 0.40}
        ttm, comps = _align_ttm_components(2024, 1, eps)
        assert ttm == 1.0  # 0.10 + 0.20 + 0.30 + 0.40
        assert len(comps) == 4
        assert comps[0].label == "Q1 2024"
        assert comps[1].label == "Q4 2023"
        assert comps[2].label == "Q3 2023"
        assert comps[3].label == "Q2 2023"


# ─── Test _compute_valuation_metrics ─────────────────────────────────────────

class TestValuationMetrics:
    def test_all_metrics(self):
        summary = {
            "trailing_pe": 12.5,
            "enterprise_to_ebitda": 8.0,
            "enterprise_value": 200_000_000_000,
        }
        valuation = {"output_snapshot": {"intrinsic_value": 220_000_000_000}}
        fcf = [make_qcf(2023, 1, 20_000_000_000, -3_000_000_000)]
        section = _compute_valuation_metrics(summary, valuation, 210.0, fcf)
        assert section.section_id == "valuation"
        assert len(section.metrics) == 4
        assert section.score is not None and section.score >= 50

    def test_no_data(self):
        section = _compute_valuation_metrics(None, None, None, [])
        assert section.score is None

    def test_expensive(self):
        summary = {
            "trailing_pe": 45.0,
            "enterprise_to_ebitda": 28.0,
            "enterprise_value": 500_000_000_000,
        }
        valuation = {"output_snapshot": {"intrinsic_value": 150.0}}
        fcf = [make_qcf(2023, 1, 5_000_000_000, -1_000_000_000)]
        section = _compute_valuation_metrics(summary, valuation, 300.0, fcf)
        assert section.score is not None and section.score < 40

    def test_jsonb_string_snapshot(self):
        summary = {
            "trailing_pe": 15.0,
            "enterprise_value": 100_000_000_000,
            "enterprise_to_ebitda": 10.0,
        }
        valuation = {"output_snapshot": '{"intrinsic_value": 110_000_000_000}'}
        fcf = [make_qcf(2023, 1, 10_000_000_000, -2_000_000_000)]
        section = _compute_valuation_metrics(summary, valuation, 100.0, fcf)
        assert section.score is not None

    def test_pe_with_normal_status(self):
        """Positive TTM EPS → status='normal', value shown."""
        income = [
            make_qincome(2024, 4, 50e9, 1.824e9, 4.021e9),
            make_qincome(2025, 1, 52e9, 0.471e9, 4.011e9),
            make_qincome(2025, 2, 48e9, -0.036e9, 3.98e9),
            make_qincome(2025, 3, 55e9, 2.447e9, 4.048e9),
        ]
        qratios = [
            {"fiscal_year": 2025, "fiscal_quarter": 3, "trailing_pe": 10.25, "quarter_end_price": 11.96},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 25.0, "enterprise_value": 200e9},
            None, 11.54, [], qratios, income,
        )
        pe = section.metrics[0]
        assert len(pe.quarters) == 1
        q = pe.quarters[0]
        assert q.status == "normal"
        assert q.value == 10.25
        assert q.ttm_eps is not None and q.ttm_eps > 0
        assert len(q.components) == 4
        assert q.quarter_end_price == 11.96

    def test_pe_with_not_applicable_status(self):
        """Negative TTM EPS → status='not_applicable', value suppressed, driver flagged."""
        income = [
            make_qincome(2025, 1, 52e9, 0.471e9, 4.011e9),
            make_qincome(2025, 2, 48e9, -0.036e9, 3.98e9),
            make_qincome(2025, 3, 55e9, 2.447e9, 4.048e9),
            make_qincome(2025, 4, 40e9, -11.064e9, 3.979e9),
        ]
        qratios = [
            {"fiscal_year": 2025, "fiscal_quarter": 4, "trailing_pe": -6.35, "quarter_end_price": 13.12},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 25.0, "enterprise_value": 200e9},
            None, 11.54, [], qratios, income,
        )
        pe = section.metrics[0]
        q = pe.quarters[0]
        assert q.status == "not_applicable"
        assert q.value == -6.35
        assert q.ttm_eps is not None and q.ttm_eps < 0
        assert len(q.components) == 4
        assert q.components[0].highlight == "driver"
        assert q.quarter_end_price == 13.12

    def test_pe_with_insufficient_data_status(self):
        """No matching income data at all → status='insufficient_data'."""
        income: list = []  # no income data
        qratios = [
            {"fiscal_year": 2022, "fiscal_quarter": 2, "trailing_pe": None, "quarter_end_price": 11.13},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 25.0, "enterprise_value": 200e9},
            None, 11.54, [], qratios, income,
        )
        pe = section.metrics[0]
        q = pe.quarters[0]
        assert q.status == "insufficient_data"
        assert q.value is None
        assert q.ttm_eps is None
        assert q.components is None or q.components == []


    def test_ev_ebitda_historical(self):
        """EV/EBITDA builds multi-quarter series from qratios.ev_ebitda."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 15.0, "quarter_end_price": 100.0,
             "ev_ebitda": 8.0, "price_to_fcf": 12.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 16.0, "quarter_end_price": 105.0,
             "ev_ebitda": 8.5, "price_to_fcf": 13.0, "ebitda": 11e9, "free_cash_flow": 6e9},
            {"fiscal_year": 2024, "fiscal_quarter": 3, "trailing_pe": 14.0, "quarter_end_price": 98.0,
             "ev_ebitda": 7.5, "price_to_fcf": 11.0, "ebitda": 9e9, "free_cash_flow": 4e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        ev = section.metrics[1]
        assert ev.metric_id == "ev_ebitda"
        assert len(ev.quarters) == 3
        assert ev.quarters[0].value == 8.0
        assert ev.quarters[1].value == 8.5
        assert ev.quarters[2].value == 7.5
        assert all(q.status == "normal" for q in ev.quarters)

    def test_pfcf_historical(self):
        """P/FCF builds multi-quarter series from qratios.price_to_fcf."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 15.0, "quarter_end_price": 100.0,
             "ev_ebitda": 8.0, "price_to_fcf": 12.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 16.0, "quarter_end_price": 105.0,
             "ev_ebitda": 8.5, "price_to_fcf": 14.0, "ebitda": 11e9, "free_cash_flow": 6e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        pfcf = section.metrics[2]
        assert pfcf.metric_id == "price_to_fcf"
        assert len(pfcf.quarters) == 2
        assert pfcf.quarters[0].value == 12.0
        assert pfcf.quarters[1].value == 14.0

    def test_ev_ebitda_insufficient_data(self):
        """All ev_ebitda = None → status = insufficient_data."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 15.0, "quarter_end_price": 100.0,
             "ev_ebitda": None, "price_to_fcf": None, "ebitda": None, "free_cash_flow": None},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 16.0, "quarter_end_price": 105.0,
             "ev_ebitda": None, "price_to_fcf": None, "ebitda": None, "free_cash_flow": None},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        ev = section.metrics[1]
        pfcf = section.metrics[2]
        assert all(q.status == "insufficient_data" for q in ev.quarters)
        assert all(q.value is None for q in ev.quarters)
        assert all(q.status == "insufficient_data" for q in pfcf.quarters)

    def test_ev_ebitda_not_applicable(self):
        """ebitda ≤ 0 → status = not_applicable."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 15.0, "quarter_end_price": 100.0,
             "ev_ebitda": None, "price_to_fcf": 12.0, "ebitda": 0.0, "free_cash_flow": 5e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        ev = section.metrics[1]
        assert ev.quarters[0].status == "not_applicable"
        assert ev.quarters[0].value is None

    def test_price_vs_intrinsic_stays_flat(self):
        """price_vs_intrinsic remains a single Current bar (DCF comparison)."""
        valuation = {"output_snapshot": {"intrinsic_value": 200_000_000_000}}
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            valuation, 210.0, [],
        )
        pvi = section.metrics[3]
        assert pvi.metric_id == "price_vs_intrinsic"
        assert len(pvi.quarters) == 1
        assert pvi.quarters[0].label == "Current"

    def test_score_uses_latest_quarter(self):
        """Score computed from latest quarter's trailing_pe, ev_ebitda, pfcf."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 25.0, "quarter_end_price": 100.0,
             "ev_ebitda": 20.0, "price_to_fcf": 25.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 12.0, "quarter_end_price": 105.0,
             "ev_ebitda": 8.0, "price_to_fcf": 13.0, "ebitda": 11e9, "free_cash_flow": 6e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        # Latest quarter has pe=12 (≤15) ✓, ev_ebitda=8 (≤10) ✓, pfcf=13 (≤15) ✓
        assert section.score is not None and section.score >= 75

    def test_score_with_none_metrics(self):
        """Score handles None metrics gracefully — no crash."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 12.0, "quarter_end_price": 100.0,
             "ev_ebitda": None, "price_to_fcf": None, "ebitda": None, "free_cash_flow": None},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        assert section.score is not None  # P/E contributes 25, EV/EBITDA and P/FCF skipped

    def test_fallback_no_qratios(self):
        """No qratios → falls back to _flat_series from company_summary."""
        summary = {
            "trailing_pe": 12.5,
            "enterprise_to_ebitda": 8.0,
            "enterprise_value": 200_000_000_000,
        }
        fcf = [make_qcf(2023, 1, 20_000_000_000, -3_000_000_000)]
        section = _compute_valuation_metrics(summary, None, 210.0, fcf, None, None)
        assert len(section.metrics) == 4
        ev = section.metrics[1]
        assert ev.metric_id == "ev_ebitda"
        assert len(ev.quarters) == 1
        assert ev.quarters[0].label == "Current"
        assert ev.quarters[0].value == 8.0
        assert section.score is not None and section.score >= 50

    def test_fallback_with_empty_qratios(self):
        """Empty qratios list → falls back to company_summary snapshots."""
        summary = {
            "trailing_pe": 40.0,
            "enterprise_to_ebitda": 25.0,
            "enterprise_value": 500_000_000_000,
        }
        fcf = [make_qcf(2023, 1, 5_000_000_000, -1_000_000_000)]
        section = _compute_valuation_metrics(summary, None, 300.0, fcf, [], None)
        assert len(section.metrics) == 4
        ev = section.metrics[1]
        assert len(ev.quarters) == 1
        assert ev.quarters[0].value == 25.0

    def test_pe_trend_down_improving(self):
        """P/E values decreasing over time → trend direction = 'down' (improving, lower is better)."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 20.0, "quarter_end_price": 100.0,
             "ev_ebitda": 8.0, "price_to_fcf": 12.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 18.0, "quarter_end_price": 105.0,
             "ev_ebitda": 8.5, "price_to_fcf": 13.0, "ebitda": 11e9, "free_cash_flow": 6e9},
            {"fiscal_year": 2024, "fiscal_quarter": 3, "trailing_pe": 15.0, "quarter_end_price": 98.0,
             "ev_ebitda": 7.5, "price_to_fcf": 11.0, "ebitda": 9e9, "free_cash_flow": 4e9},
            {"fiscal_year": 2024, "fiscal_quarter": 4, "trailing_pe": 12.0, "quarter_end_price": 102.0,
             "ev_ebitda": 7.0, "price_to_fcf": 10.0, "ebitda": 8e9, "free_cash_flow": 3e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 7.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        pe = section.metrics[0]
        # Lower PE is better, so decreasing values = "up" (improving)
        assert pe.trend_direction == "up"
        assert pe.change_label != "per quarter"

    def test_pe_trend_up_worsening(self):
        """P/E values increasing over time → trend direction = 'up' (worsening, higher is worse)."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 10.0, "quarter_end_price": 100.0,
             "ev_ebitda": 8.0, "price_to_fcf": 12.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 15.0, "quarter_end_price": 105.0,
             "ev_ebitda": 8.5, "price_to_fcf": 13.0, "ebitda": 11e9, "free_cash_flow": 6e9},
            {"fiscal_year": 2024, "fiscal_quarter": 3, "trailing_pe": 18.0, "quarter_end_price": 98.0,
             "ev_ebitda": 7.5, "price_to_fcf": 11.0, "ebitda": 9e9, "free_cash_flow": 4e9},
            {"fiscal_year": 2024, "fiscal_quarter": 4, "trailing_pe": 22.0, "quarter_end_price": 102.0,
             "ev_ebitda": 7.0, "price_to_fcf": 10.0, "ebitda": 8e9, "free_cash_flow": 3e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 7.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        pe = section.metrics[0]
        # Since higher_is_better=False, increasing values = 'down' (worsening)
        assert pe.trend_direction == "down"

    def test_ev_trend_improving(self):
        """EV/EBITDA decreasing → trend = 'down' (improving, lower is better)."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 15.0, "quarter_end_price": 100.0,
             "ev_ebitda": 12.0, "price_to_fcf": 18.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 15.0, "quarter_end_price": 105.0,
             "ev_ebitda": 10.0, "price_to_fcf": 16.0, "ebitda": 11e9, "free_cash_flow": 6e9},
            {"fiscal_year": 2024, "fiscal_quarter": 3, "trailing_pe": 15.0, "quarter_end_price": 98.0,
             "ev_ebitda": 8.0, "price_to_fcf": 14.0, "ebitda": 9e9, "free_cash_flow": 4e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        ev = section.metrics[1]
        # Lower EV/EBITDA is better, so decreasing values = "up" (improving)
        assert ev.trend_direction == "up"

    def test_pfcf_trend_stable(self):
        """P/FCF values nearly flat → trend = 'stable'."""
        qratios = [
            {"fiscal_year": 2024, "fiscal_quarter": 1, "trailing_pe": 15.0, "quarter_end_price": 100.0,
             "ev_ebitda": 8.0, "price_to_fcf": 12.0, "ebitda": 10e9, "free_cash_flow": 5e9},
            {"fiscal_year": 2024, "fiscal_quarter": 2, "trailing_pe": 16.0, "quarter_end_price": 105.0,
             "ev_ebitda": 8.5, "price_to_fcf": 12.1, "ebitda": 11e9, "free_cash_flow": 6e9},
            {"fiscal_year": 2024, "fiscal_quarter": 3, "trailing_pe": 14.0, "quarter_end_price": 98.0,
             "ev_ebitda": 7.5, "price_to_fcf": 11.9, "ebitda": 9e9, "free_cash_flow": 4e9},
        ]
        section = _compute_valuation_metrics(
            {"enterprise_to_ebitda": 8.0, "enterprise_value": 200e9},
            None, 100.0, [], qratios, [],
        )
        pfcf = section.metrics[2]
        assert pfcf.trend_direction == "stable"


# ─── Test _compute_narrative_metrics ─────────────────────────────────────────

class TestNarrativeMetrics:
    def test_with_earnings(self):
        earnings = [
            make_earnings(2024, 1, 5.0, 2.0),
            make_earnings(2024, 2, -1.0, 1.0),
            make_earnings(2024, 3, 3.0, 1.5),
            make_earnings(2024, 4, 2.0, 0.5),
        ]
        section = _compute_narrative_metrics(earnings, buy_idx=1)
        assert section.section_id == "narrative"
        assert len(section.metrics) == 3
        assert section.score is not None
        # 3 beats out of 4 = 75%
        eps_series = section.metrics[0]
        assert eps_series.metric_id == "eps_surprise"
        assert len(eps_series.quarters) == 4
        assert eps_series.quarters[0].narrative_label == "beat"
        assert eps_series.quarters[1].narrative_label == "miss"

    def test_all_beats(self):
        earnings = [
            make_earnings(2024, 1, 3.0, 2.0),
            make_earnings(2024, 2, 2.0, 1.0),
        ]
        section = _compute_narrative_metrics(earnings)
        assert section.score is not None and section.score >= 50

    def test_no_earnings(self):
        section = _compute_narrative_metrics([])
        assert len(section.metrics) == 0
        assert section.score is None

    def test_some_null_surprises(self):
        earnings = [
            make_earnings(2024, 1, 3.0, 2.0),
            make_earnings(2024, 2, None, None),
        ]
        section = _compute_narrative_metrics(earnings)
        assert section.score is not None
        assert section.metrics[0].quarters[1].value is None


# ─── Integration: _build_quarter_series with all trends ─────────────────────

class TestBuildQuarterSeries:
    def test_roic_up(self):
        rows = [
            {"fiscal_year": 2023, "fiscal_quarter": 1, "roic": 0.10},
            {"fiscal_year": 2023, "fiscal_quarter": 2, "roic": 0.12},
            {"fiscal_year": 2023, "fiscal_quarter": 3, "roic": 0.15},
        ]
        series = _build_quarter_series("roic", "ROIC", "%", rows, "roic", True)
        assert series.trend_direction == "up"
        assert series.change_label != "stable"

    def test_roe_stable(self):
        rows = [
            {"fiscal_year": 2023, "fiscal_quarter": 1, "roe": 0.20},
            {"fiscal_year": 2023, "fiscal_quarter": 2, "roe": 0.20},
            {"fiscal_year": 2023, "fiscal_quarter": 3, "roe": 0.21},
        ]
        series = _build_quarter_series("roe", "ROE", "%", rows, "roe", True)
        assert series.trend_direction == "stable"

    def test_debt_to_equity_down_is_good(self):
        rows = [
            {"fiscal_year": 2023, "fiscal_quarter": 1, "debt_to_equity": 1.0},
            {"fiscal_year": 2023, "fiscal_quarter": 2, "debt_to_equity": 0.8},
            {"fiscal_year": 2023, "fiscal_quarter": 3, "debt_to_equity": 0.6},
        ]
        series = _build_quarter_series("debt_to_equity", "D/E", "x", rows, "debt_to_equity", False)
        # Lower is better, so decreasing D/E = "up"
        assert series.trend_direction == "up"

    def test_quarter_sorting(self):
        rows = [
            {"fiscal_year": 2023, "fiscal_quarter": 3, "roic": 0.15},
            {"fiscal_year": 2023, "fiscal_quarter": 1, "roic": 0.10},
            {"fiscal_year": 2023, "fiscal_quarter": 2, "roic": 0.12},
        ]
        series = _build_quarter_series("roic", "ROIC", "%", rows, "roic", True)
        assert [q.value for q in series.quarters] == [0.10, 0.12, 0.15]
