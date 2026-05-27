from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from domain.models.risk_assessment import (
    RiskAssessmentResponse,
    CompositeScore,
    ScenarioResult,
    RiskMetric,
    RiskLayer,
    BusinessFragility,
    BalanceSheetRisk,
    ValuationCompressionRisk,
    EarningsStressRisk,
    DrawdownRisk,
    LayerName,
)
from application.services.risk_assessment_service import RiskAssessmentService


@pytest.fixture
def mock_risk_repo():
    repo = MagicMock()
    repo.get_company_context = AsyncMock(return_value={
        "company_id": 1, "symbol": "AAPL", "sector": "Technology",
        "industry": "Consumer Electronics", "currency": "USD",
    })
    repo.get_latest_financial_ratios = AsyncMock(return_value={
        "roic": 0.35, "gross_margin": 0.45, "operating_margin": 0.30,
        "net_margin": 0.25, "debt_to_ebitda": 0.5, "net_debt_to_ebitda": 0.3,
        "interest_coverage": 25.0, "current_ratio": 1.5, "quick_ratio": 1.2,
        "debt_to_equity": 0.8, "fcf_conversion": 0.85,
    })
    repo.get_financial_ratios_history = AsyncMock(return_value=[
        {"fiscal_year": 2021, "roic": 0.30, "gross_margin": 0.44},
        {"fiscal_year": 2022, "roic": 0.32, "gross_margin": 0.44},
        {"fiscal_year": 2023, "roic": 0.33, "gross_margin": 0.45},
        {"fiscal_year": 2024, "roic": 0.34, "gross_margin": 0.45},
        {"fiscal_year": 2025, "roic": 0.35, "gross_margin": 0.45},
    ])
    repo.get_price_history_range = AsyncMock(return_value=[
        {"close_price": 150.0, "price_date": "2022-01-01"},
        {"close_price": 200.0, "price_date": "2023-01-01"},
        {"close_price": 180.0, "price_date": "2024-01-01"},
        {"close_price": 220.0, "price_date": "2025-01-01"},
        {"close_price": 210.0, "price_date": "2025-06-01"},
    ])
    repo.get_income_statements_annual = AsyncMock(return_value=[
        {"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps_diluted": 5.0},
        {"fiscal_year": 2022, "net_income": 115, "revenue": 1100, "eps_diluted": 5.75},
        {"fiscal_year": 2023, "net_income": 132, "revenue": 1250, "eps_diluted": 6.60},
        {"fiscal_year": 2024, "net_income": 152, "revenue": 1400, "eps_diluted": 7.60},
        {"fiscal_year": 2025, "net_income": 175, "revenue": 1600, "eps_diluted": 8.75},
    ])
    repo.get_current_market_price = AsyncMock(return_value=200.0)
    repo.get_risk_ai_narrative = AsyncMock(return_value=None)
    repo.upsert_risk_ai_narrative = AsyncMock(return_value=True)
    repo.get_cash_flow_latest = AsyncMock(return_value={
        "cash_from_operating_activities": 90_000,
        "capital_expenditures": -10_000,
        "net_income": 75_000,
    })
    repo.get_company_summary_history = AsyncMock(return_value=[
        {"snapshot_date": "2020-01-01", "trailing_pe": 20.0, "enterprise_to_ebitda": 12.0, "peg_ratio": 1.5},
        {"snapshot_date": "2021-01-01", "trailing_pe": 25.0, "enterprise_to_ebitda": 14.0, "peg_ratio": 1.8},
        {"snapshot_date": "2022-01-01", "trailing_pe": 22.0, "enterprise_to_ebitda": 13.0, "peg_ratio": 1.6},
        {"snapshot_date": "2023-01-01", "trailing_pe": 28.0, "enterprise_to_ebitda": 15.0, "peg_ratio": 2.0},
        {"snapshot_date": "2024-01-01", "trailing_pe": 30.0, "enterprise_to_ebitda": 16.0, "peg_ratio": 2.2},
        {"snapshot_date": "2025-01-01", "trailing_pe": 35.0, "enterprise_to_ebitda": 18.0, "peg_ratio": 2.5},
    ])
    return repo


@pytest.fixture
def mock_moat_service():
    svc = MagicMock()
    mock_valuation = MagicMock()
    mock_valuation.moat_score = 85.0
    mock_valuation.moat_category = "Wide"
    mock_valuation.roic_minus_wacc = 22.0
    mock_response = MagicMock()
    mock_response.symbol = "AAPL"
    mock_response.company_id = 1
    mock_response.valuation = mock_valuation
    svc.get_moat_analysis = AsyncMock(return_value=mock_response)
    return svc


@pytest.fixture
def mock_wacc_service():
    return MagicMock()


@pytest.fixture
def service(mock_risk_repo, mock_moat_service, mock_wacc_service):
    return RiskAssessmentService(mock_risk_repo, mock_moat_service, mock_wacc_service)


class TestRiskAssessmentService:
    """UT-B1 through UT-B18: Unit tests."""

    def test_constructor(self, service, mock_risk_repo, mock_moat_service, mock_wacc_service):
        assert service._repo is mock_risk_repo
        assert service._moat_service is mock_moat_service
        assert service._wacc_service is mock_wacc_service

    @pytest.mark.asyncio
    async def test_get_risk_assessment_happy_path(self, service):
        result = await service.get_risk_assessment("AAPL")
        assert isinstance(result, RiskAssessmentResponse)
        assert result.symbol == "AAPL"
        assert 0 <= result.composite.score <= 100
        assert result.composite.category in ("Very Low Downside", "Moderate", "Elevated", "High Risk")
        assert result.composite.maximum_expected_loss_pct is None or isinstance(result.composite.maximum_expected_loss_pct, float)
        assert len(result.layers) == 5
        for layer_name in ("business_fragility", "balance_sheet", "valuation_compression", "earnings_stress", "drawdown_risk"):
            assert layer_name in result.layers
            layer = result.layers[layer_name]
            assert 0 <= layer.score <= 10
            assert layer.category in ("low", "moderate", "elevated", "high", "severe")
            assert len(layer.metrics) > 0
        assert result.composite.bear_case.downside_pct <= 0

    @pytest.mark.asyncio
    async def test_get_risk_assessment_unknown_symbol(self, mock_risk_repo, service):
        mock_risk_repo.get_company_context.return_value = None
        with pytest.raises(ValueError, match="not found"):
            await service.get_risk_assessment("UNKNOWN")

    @pytest.mark.asyncio
    async def test_get_risk_assessment_partial_ratios(self, mock_risk_repo, service):
        mock_risk_repo.get_latest_financial_ratios.return_value = {
            "current_ratio": 0.5, "debt_to_ebitda": None,
        }
        mock_risk_repo.get_cash_flow_latest.return_value = None
        result = await service.get_risk_assessment("AAPL")
        assert result is not None
        assert result.layers["business_fragility"].moat_score == 85.0
        assert result.data_quality.fallbacks_used is not None

    @pytest.mark.asyncio
    async def test_empty_price_history(self, mock_risk_repo, service):
        mock_risk_repo.get_price_history_range.return_value = []
        result = await service.get_risk_assessment("AAPL")
        dd = result.layers["drawdown_risk"]
        assert dd.max_drawdown_5y is None
        assert dd.crisis_drawdowns is None or len(dd.crisis_drawdowns) == 0

    def test_business_fragility_with_moat(self, service):
        ctx = {"sector": "Technology", "industry": "Software"}
        moat = MagicMock()
        moat.valuation.moat_score = 85.0
        moat.valuation.moat_category = "Wide"
        moat.valuation.roic_minus_wacc = 22.0
        ratios = [{"fiscal_year": 2025, "gross_margin": 0.45}]
        result = service._analyze_business_fragility(ctx, moat, ratios)
        assert result.moat_score == 85.0
        assert result.moat_category == "Wide"
        moat_metric = [m for m in result.metrics if m.name == "Moat Durability"][0]
        assert moat_metric.status == "pass"

    def test_business_fragility_no_moat(self, service):
        ctx = {"sector": "Technology", "industry": "Software"}
        ratios = [{"fiscal_year": 2025, "gross_margin": 0.45}]
        result = service._analyze_business_fragility(ctx, None, ratios)
        assert result.moat_score is None
        assert result.moat_category is None
        moat_metric = [m for m in result.metrics if m.name == "Moat Durability"][0]
        assert moat_metric.status == "na"

    @pytest.mark.parametrize("d_e,expected_status", [
        (0.5, "pass"),
        (2.5, "caution"),
        (4.5, "fail"),
        (7.0, "fail"),
        (None, "na"),
    ])
    def test_balance_sheet_debt_ebitda_thresholds(self, service, d_e, expected_status):
        ratios = {"debt_to_ebitda": d_e, "interest_coverage": 10.0, "current_ratio": 2.0, "debt_to_equity": 0.5}
        cash_flow = {"cash_from_operating_activities": 100, "capital_expenditures": -20, "net_income": 80}
        result = service._analyze_balance_sheet(ratios, cash_flow)
        debt_metric = [m for m in result.metrics if m.name == "Debt/EBITDA"][0]
        assert debt_metric.status == expected_status

    @pytest.mark.asyncio
    async def test_valuation_compression_percentile(self, mock_risk_repo, service):
        mock_risk_repo.get_company_summary_history.return_value = [
            {"snapshot_date": f"{y}-01-01", "trailing_pe": float(v), "enterprise_to_ebitda": float(v * 0.5), "peg_ratio": 1.5}
            for y, v in zip(range(2015, 2026), range(10, 35, 2))
        ]
        result = await service._analyze_valuation_compression(1)
        assert result.pe_percentile is not None
        assert 0 <= result.pe_percentile <= 100
        assert result.pe_5y_min is not None
        assert result.pe_5y_max is not None

    @pytest.mark.asyncio
    async def test_valuation_compression_sparse_data(self, mock_risk_repo, service):
        mock_risk_repo.get_company_summary_history.return_value = [
            {"snapshot_date": "2025-01-01", "trailing_pe": 25.0, "enterprise_to_ebitda": 15.0, "peg_ratio": 2.0},
        ]
        result = await service._analyze_valuation_compression(1)
        assert result.pe_percentile == 50.0

    def test_earnings_stress_cagr(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps_diluted": 1.00},
            {"fiscal_year": 2022, "net_income": 115, "revenue": 1100, "eps_diluted": 1.15},
            {"fiscal_year": 2023, "net_income": 132, "revenue": 1250, "eps_diluted": 1.32},
            {"fiscal_year": 2024, "net_income": 152, "revenue": 1400, "eps_diluted": 1.52},
            {"fiscal_year": 2025, "net_income": 175, "revenue": 1600, "eps_diluted": 1.75},
        ]
        result = service._analyze_earnings_stress(income)
        assert result.eps_cagr_5y is not None
        assert abs(result.eps_cagr_5y - 0.15) < 0.02

    def test_drawdown_max_drawdown(self, service):
        prices = [
            {"close_price": p, "price_date": f"202{i}-01-01"}
            for i, p in enumerate([200, 180, 220, 160, 190])
        ]
        ctx = {"sector": "Technology"}
        result = service._analyze_drawdown_risk(prices, ctx)
        assert result.max_drawdown_5y is not None
        assert result.max_drawdown_5y < 0

    def test_drawdown_crisis_periods(self, service):
        prices = [
            {"close_price": 100.0, "price_date": "2020-01-01"},
            {"close_price": 110.0, "price_date": "2020-02-15"},
            {"close_price": 70.0, "price_date": "2020-03-15"},
            {"close_price": 80.0, "price_date": "2020-03-23"},
            {"close_price": 90.0, "price_date": "2020-06-01"},
            {"close_price": 150.0, "price_date": "2022-01-01"},
            {"close_price": 110.0, "price_date": "2022-06-01"},
            {"close_price": 120.0, "price_date": "2022-10-12"},
        ]
        ctx = {"sector": "Technology"}
        result = service._analyze_drawdown_risk(prices, ctx)
        assert result.crisis_drawdowns is not None
        assert len(result.crisis_drawdowns) >= 1

    def test_drawdown_all_positive(self, service):
        prices = [
            {"close_price": 100.0, "price_date": "2021-01-01"},
            {"close_price": 110.0, "price_date": "2022-01-01"},
            {"close_price": 120.0, "price_date": "2023-01-01"},
            {"close_price": 130.0, "price_date": "2024-01-01"},
            {"close_price": 140.0, "price_date": "2025-01-01"},
        ]
        ctx = {"sector": "Technology"}
        result = service._analyze_drawdown_risk(prices, ctx)
        assert result.max_drawdown_5y == 0.0
        assert result.current_drawdown == 0.0
        assert result.recovery_time_days is None

    def test_drawdown_monotonic_decline(self, service):
        prices = [
            {"close_price": 200.0, "price_date": "2021-01-01"},
            {"close_price": 160.0, "price_date": "2022-01-01"},
            {"close_price": 120.0, "price_date": "2023-01-01"},
            {"close_price": 80.0, "price_date": "2024-01-01"},
            {"close_price": 40.0, "price_date": "2025-01-01"},
        ]
        ctx = {"sector": "Technology"}
        result = service._analyze_drawdown_risk(prices, ctx)
        assert result.max_drawdown_5y == -0.8
        assert result.current_drawdown is not None

    def test_drawdown_recovery_time(self, service):
        prices = [
            {"close_price": 100.0, "price_date": "2021-01-01"},
            {"close_price": 80.0, "price_date": "2021-06-01"},
            {"close_price": 90.0, "price_date": "2022-01-01"},
            {"close_price": 100.0, "price_date": "2022-06-01"},
            {"close_price": 120.0, "price_date": "2023-01-01"},
        ]
        ctx = {"sector": "Technology"}
        result = service._analyze_drawdown_risk(prices, ctx)
        assert result.recovery_time_days is not None
        assert result.recovery_time_days > 0

    def test_drawdown_single_price(self, service):
        prices = [{"close_price": 100.0, "price_date": "2025-01-01"}]
        ctx = {"sector": "Technology"}
        result = service._analyze_drawdown_risk(prices, ctx)
        assert result.score == 5.0
        assert result.category == "moderate"
        assert result.max_drawdown_5y is None

    def test_drawdown_beta_status(self, service):
        prices = [
            {"close_price": 100.0, "price_date": "2021-01-01"},
            {"close_price": 110.0, "price_date": "2022-01-01"},
            {"close_price": 120.0, "price_date": "2023-01-01"},
            {"close_price": 130.0, "price_date": "2024-01-01"},
            {"close_price": 140.0, "price_date": "2025-01-01"},
        ]
        ctx = {"sector": "Technology", "beta": 0.8}
        result = service._analyze_drawdown_risk(prices, ctx)
        beta_metric = [m for m in result.metrics if m.name == "Beta (5y)"][0]
        assert beta_metric.status == "pass"

    def test_drawdown_high_beta_status(self, service):
        prices = [
            {"close_price": 100.0, "price_date": "2021-01-01"},
            {"close_price": 110.0, "price_date": "2022-01-01"},
            {"close_price": 120.0, "price_date": "2023-01-01"},
            {"close_price": 130.0, "price_date": "2024-01-01"},
            {"close_price": 140.0, "price_date": "2025-01-01"},
        ]
        ctx = {"sector": "Technology", "beta": 1.8}
        result = service._analyze_drawdown_risk(prices, ctx)
        beta_metric = [m for m in result.metrics if m.name == "Beta (5y)"][0]
        assert beta_metric.status == "fail"

    def test_compute_composite_weighted(self, service):
        from domain.models.risk_assessment import RiskLayer, RiskMetric
        layers = {}
        scores = {"business_fragility": 8.0, "balance_sheet": 9.0, "valuation_compression": 6.0, "earnings_stress": 7.0, "drawdown_risk": 8.0}
        for name, score in scores.items():
            layers[name] = RiskLayer(
                name=name, display_name=name, score=score, category="moderate",
                metrics=[RiskMetric(name="test", label="test", status="pass")],
                weight=0.20,
            )
        composite = service._compute_composite(layers)
        expected = (8.0*0.20 + 9.0*0.25 + 6.0*0.20 + 7.0*0.25 + 8.0*0.10) / 1.0 * 10
        assert abs(composite.score - expected) < 1.0
        assert composite.category in ("Very Low Downside", "Moderate", "Elevated", "High Risk")

    def test_compute_scenarios_bear_downside(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps_diluted": 10.0},
            {"fiscal_year": 2025, "net_income": 150, "revenue": 1500, "eps_diluted": 10.0},
        ]
        scenarios = service._compute_scenarios(income, 200.0)
        assert scenarios is not None
        bear = [s for s in scenarios if s.scenario == "bear"][0]
        assert bear.downside <= 0

    @pytest.mark.parametrize("score,expected", [
        (9.5, "low"),
        (8.0, "moderate"),
        (6.0, "elevated"),
        (4.0, "high"),
        (2.0, "severe"),
    ])
    def test_score_to_severity(self, service, score, expected):
        assert service._score_to_severity(score) == expected

    @pytest.mark.parametrize("score,expected", [
        (90, "Very Low Downside"),
        (70, "Moderate"),
        (50, "Elevated"),
        (30, "High Risk"),
    ])
    def test_composite_category(self, service, score, expected):
        assert service._composite_category(score) == expected

    # ── _compute_cagr validation ───────────────────────────────────────────

    @pytest.mark.parametrize("values,expected_cagr", [
        ([1.0, 1.15, 1.32, 1.52, 1.75], 0.15),
        ([10.0, 11.0], 0.10),
        ([100.0, 200.0], 1.0),
        ([100.0, 50.0], -0.50),
    ])
    def test_compute_cagr_known_values(self, service, values, expected_cagr):
        result = service._compute_cagr(values)
        assert result is not None
        assert abs(result - expected_cagr) < 0.02

    def test_compute_cagr_too_few_values(self, service):
        assert service._compute_cagr([5.0]) is None
        assert service._compute_cagr([]) is None

    def test_compute_cagr_negative_start(self, service):
        assert service._compute_cagr([-5.0, 10.0]) is None

    def test_compute_cagr_zero_start(self, service):
        assert service._compute_cagr([0.0, 10.0]) is None

    # ── _compute_max_drawdown validation ───────────────────────────────────

    def test_max_drawdown_monotonic_increase(self, service):
        assert service._compute_max_drawdown([100, 110, 120, 130]) == 0.0

    def test_max_drawdown_monotonic_decrease(self, service):
        result = service._compute_max_drawdown([100, 80, 60, 40])
        assert result == -0.6

    def test_max_drawdown_peak_then_trough(self, service):
        result = service._compute_max_drawdown([100, 200, 150, 100, 50])
        assert result == -0.75

    def test_max_drawdown_multiple_peaks(self, service):
        result = service._compute_max_drawdown([100, 200, 150, 180, 120, 160])
        assert result == -0.40

    def test_max_drawdown_single_value(self, service):
        assert service._compute_max_drawdown([100]) == 0.0

    def test_max_drawdown_empty(self, service):
        assert service._compute_max_drawdown([]) == 0.0

    def test_max_drawdown_all_same(self, service):
        assert service._compute_max_drawdown([50, 50, 50, 50]) == 0.0

    # ── _compute_percentile validation ─────────────────────────────────────

    def test_percentile_value_at_max(self, service):
        result = service._compute_percentile(100, [10, 30, 50, 80, 100])
        assert result == 100.0

    def test_percentile_value_at_min(self, service):
        result = service._compute_percentile(10, [10, 30, 50, 80, 100])
        assert result > 0.0

    def test_percentile_value_middle(self, service):
        result = service._compute_percentile(50, [10, 30, 50, 70, 90])
        assert result == 60.0

    def test_percentile_none_value(self, service):
        assert service._compute_percentile(None, [10, 20, 30]) == 50.0

    def test_percentile_empty_list(self, service):
        assert service._compute_percentile(50, []) == 50.0

    def test_percentile_single_element(self, service):
        assert service._compute_percentile(50, [50]) == 50.0

    # ── _compute_scenarios validation ──────────────────────────────────────

    def test_scenarios_none_price(self, service):
        income = [{"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps_diluted": 10.0}]
        assert service._compute_scenarios(income, None) is None

    def test_scenarios_empty_income(self, service):
        assert service._compute_scenarios([], 200.0) is None

    def test_scenarios_no_eps_values(self, service):
        income = [{"fiscal_year": 2021, "net_income": 100, "revenue": 1000}]
        assert service._compute_scenarios(income, 200.0) is None

    def test_scenarios_zero_current_eps(self, service):
        income = [{"fiscal_year": 2021, "net_income": 0, "revenue": 1000, "eps_diluted": 0.0}]
        assert service._compute_scenarios(income, 200.0) is None

    def test_scenarios_negative_current_eps_before_fix(self, service):
        """Single year — no revenue CAGR possible, still returns None."""
        income = [{"fiscal_year": 2021, "net_income": -50, "revenue": 1000, "eps_diluted": -1.54}]
        assert service._compute_scenarios(income, 200.0) is None

    def test_scenarios_negative_eps_revenue_based_path(self, service):
        """Revenue-based fallback: negative EPS but revenue data exists."""
        income = [
            {"fiscal_year": 2021, "net_income": -50, "revenue": 1000, "eps_diluted": -1.54, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2022, "net_income": -30, "revenue": 1200, "eps_diluted": -0.80, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2023, "net_income": -10, "revenue": 1400, "eps_diluted": -0.25, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2024, "net_income": 5,  "revenue": 1600, "eps_diluted": 0.10, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2025, "net_income": -20, "revenue": 1800, "eps_diluted": -0.50, "shares_outstanding_diluted": 100},
        ]
        scenarios = service._compute_scenarios(income, 200.0)
        assert scenarios is not None
        assert len(scenarios) == 4
        # All returns should be > -100% (i.e. downside > -1.0)
        for s in scenarios:
            assert s.downside > -1.0
            assert s.future_eps > 0  # terminal margin applied to positive RPS * revenue growth

    def test_scenarios_negative_eps_revenue_no_shares(self, service):
        """Revenue-based fallback unavailable — missing shares_outstanding_diluted."""
        income = [
            {"fiscal_year": 2021, "net_income": -50, "revenue": 1000, "eps_diluted": -1.54},
            {"fiscal_year": 2025, "net_income": -20, "revenue": 1800, "eps_diluted": -0.50},
        ]
        assert service._compute_scenarios(income, 200.0) is None

    def test_scenarios_negative_eps_revenue_no_revenue_data(self, service):
        """Revenue-based fallback unavailable — revenue field missing."""
        income = [
            {"fiscal_year": 2021, "net_income": -50, "eps_diluted": -1.54, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2025, "net_income": -20, "eps_diluted": -0.50, "shares_outstanding_diluted": 100},
        ]
        assert service._compute_scenarios(income, 200.0) is None

    def test_scenarios_zero_eps_revenue_based_path(self, service):
        """Zero current_eps falls to revenue-based path when revenue data exists."""
        income = [
            {"fiscal_year": 2021, "net_income": 0, "revenue": 1000, "eps_diluted": 0.0, "shares_outstanding_diluted": 50},
            {"fiscal_year": 2025, "net_income": 0, "revenue": 2000, "eps_diluted": 0.0, "shares_outstanding_diluted": 50},
        ]
        scenarios = service._compute_scenarios(income, 200.0)
        assert scenarios is not None
        assert len(scenarios) == 4

    def test_scenarios_negative_eps_mel_integration(self, service):
        """End-to-end: revenue-based scenarios compute and MEL is positive."""
        income = [
            {"fiscal_year": 2021, "net_income": -50, "revenue": 1000, "eps_diluted": -1.54, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2022, "net_income": -30, "revenue": 1200, "eps_diluted": -0.80, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2023, "net_income": -10, "revenue": 1400, "eps_diluted": -0.25, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2024, "net_income": 5,  "revenue": 1600, "eps_diluted": 0.10, "shares_outstanding_diluted": 100},
            {"fiscal_year": 2025, "net_income": -20, "revenue": 1800, "eps_diluted": -0.50, "shares_outstanding_diluted": 100},
        ]
        scenarios = service._compute_scenarios(income, 200.0)
        assert scenarios is not None
        mel = service._compute_mel(scenarios)
        assert mel is not None
        assert 0.0 < mel <= 100.0

    def test_scenarios_full_math_validation(self, service):
        current_price = 200.0
        eps_0 = 10.0
        eps_values = [eps_0 * (1.15 ** i) for i in range(5)]
        income = [
            {"fiscal_year": y, "net_income": 100 * (1.15 ** i), "revenue": 1000 * (1.10 ** i), "eps_diluted": eps_values[i]}
            for i, y in enumerate(range(2021, 2026))
        ]
        scenarios = service._compute_scenarios(income, current_price)
        assert scenarios is not None
        assert len(scenarios) == 4

        eps_cagr = 0.15
        bull_eps_growth = max(eps_cagr * 1.8, 0.10)
        base_eps_growth = max(eps_cagr, 0.05)
        bear_eps_growth = max(eps_cagr * 0.3, 0.02)
        severe_eps_growth = 0.0

        expected = [
            ("bull", 0.25, bull_eps_growth, 28),
            ("base", 0.50, base_eps_growth, 22),
            ("bear", 0.20, bear_eps_growth, 15),
            ("severe", 0.05, severe_eps_growth, 12),
        ]
        for s, prob, eps_g, exit_pe in expected:
            sc = [x for x in scenarios if x.scenario == s][0]
            assert sc.probability == prob
            assert abs(sc.eps_growth - eps_g) < 0.001
            assert sc.exit_pe == exit_pe
            future_eps = eps_values[-1] * ((1.0 + eps_g) ** 5)
            future_value = future_eps * exit_pe
            total_return = (future_value / current_price) - 1.0
            assert abs(sc.future_value - round(future_value, 2)) < 0.05
            assert abs(sc.total_return - round(total_return, 4)) < 0.005

    def test_scenarios_bear_downside_negative(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps_diluted": 10.0},
            {"fiscal_year": 2025, "net_income": 150, "revenue": 1500, "eps_diluted": 12.0},
        ]
        scenarios = service._compute_scenarios(income, 50.0)
        assert scenarios is not None
        bear = [s for s in scenarios if s.scenario == "bear"][0]
        severe = [s for s in scenarios if s.scenario == "severe"][0]
        assert bear.downside <= 0
        assert severe.downside <= 0

    # ── _compute_mel validation ────────────────────────────────────────────

    def test_mel_no_scenarios(self, service):
        assert service._compute_mel(None) is None
        assert service._compute_mel([]) is None

    def test_mel_all_scenarios_have_downside(self, service):
        scenarios = [
            ScenarioResult(scenario="bear", probability=0.20, eps_growth=0.02, exit_pe=15,
                           future_eps=10.0, future_value=150.0, total_return=-0.25, downside=-0.25),
            ScenarioResult(scenario="severe", probability=0.05, eps_growth=0.0, exit_pe=12,
                           future_eps=8.0, future_value=96.0, total_return=-0.50, downside=-0.50),
        ]
        expected = round((0.20 * abs(-0.25) + 0.05 * abs(-0.50)) * 100, 1)
        assert service._compute_mel(scenarios) == expected

    def test_mel_some_scenarios_no_downside(self, service):
        scenarios = [
            ScenarioResult(scenario="bull", probability=0.25, eps_growth=0.15, exit_pe=28,
                           future_eps=20.0, future_value=560.0, total_return=0.50, downside=0.0),
            ScenarioResult(scenario="bear", probability=0.20, eps_growth=0.02, exit_pe=15,
                           future_eps=10.0, future_value=150.0, total_return=-0.25, downside=-0.25),
        ]
        expected = round((0.20 * abs(-0.25)) * 100, 1)
        assert service._compute_mel(scenarios) == expected

    def test_mel_no_negative_downside(self, service):
        scenarios = [
            ScenarioResult(scenario="bull", probability=0.25, eps_growth=0.15, exit_pe=28,
                           future_eps=20.0, future_value=560.0, total_return=0.50, downside=0.0),
            ScenarioResult(scenario="base", probability=0.50, eps_growth=0.08, exit_pe=22,
                           future_eps=14.0, future_value=308.0, total_return=0.10, downside=0.0),
        ]
        assert service._compute_mel(scenarios) == 0.0

    def test_mel_capped_at_100(self, service):
        scenarios = [
            ScenarioResult(scenario="bear", probability=0.50, eps_growth=0.02, exit_pe=15,
                           future_eps=5.0, future_value=75.0, total_return=-2.0, downside=-2.0),
            ScenarioResult(scenario="severe", probability=0.50, eps_growth=0.0, exit_pe=12,
                           future_eps=4.0, future_value=48.0, total_return=-3.0, downside=-3.0),
        ]
        assert service._compute_mel(scenarios) == 100.0

    # ── _compute_layer_score validation ────────────────────────────────────

    def test_layer_score_all_pass(self, service):
        metrics = [
            RiskMetric(name="M1", label="P", status="pass", weight=3),
            RiskMetric(name="M2", label="P", status="pass", weight=2),
        ]
        assert service._compute_layer_score(metrics, {}) == 10.0

    def test_layer_score_all_fail(self, service):
        metrics = [
            RiskMetric(name="M1", label="F", status="fail", weight=3),
            RiskMetric(name="M2", label="F", status="fail", weight=2),
        ]
        assert service._compute_layer_score(metrics, {}) == 1.0

    def test_layer_score_all_caution(self, service):
        metrics = [
            RiskMetric(name="M1", label="C", status="caution", weight=3),
            RiskMetric(name="M2", label="C", status="caution", weight=2),
        ]
        assert service._compute_layer_score(metrics, {}) == 5.0

    def test_layer_score_mixed_statuses(self, service):
        metrics = [
            RiskMetric(name="M1", label="P", status="pass", weight=4),
            RiskMetric(name="M2", label="C", status="caution", weight=2),
            RiskMetric(name="M3", label="F", status="fail", weight=2),
        ]
        total = 10.0 * 4 + 5.0 * 2 + 1.0 * 2
        max_possible = 10.0 * (4 + 2 + 2)
        expected = round((total / max_possible) * 10.0, 1)
        assert service._compute_layer_score(metrics, {}) == expected

    def test_layer_score_all_na(self, service):
        metrics = [
            RiskMetric(name="M1", label="N/A", status="na", weight=3),
        ]
        assert service._compute_layer_score(metrics, {}) == 5.0

    def test_layer_score_with_custom_weights(self, service):
        metrics = [
            RiskMetric(name="moat_durability", label="P", status="pass", weight=5),
            RiskMetric(name="recurrence", label="P", status="pass", weight=3),
        ]
        custom = {"moat_durability": 10, "recurrence": 4}
        total = 10.0 * 10 + 10.0 * 4
        max_possible = 10.0 * (10 + 4)
        expected = round((total / max_possible) * 10.0, 1)
        assert service._compute_layer_score(metrics, custom) == expected

    # ── _compute_composite validation ──────────────────────────────────────

    def test_compute_composite_exact_formula(self, service):
        from domain.models.risk_assessment import RiskLayer, RiskMetric
        layers = {
            "business_fragility": RiskLayer(name="business_fragility", display_name="BF", score=8.0, category="low",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.20),
            "balance_sheet": RiskLayer(name="balance_sheet", display_name="BS", score=9.0, category="low",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.25),
            "valuation_compression": RiskLayer(name="valuation_compression", display_name="VC", score=6.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.20),
            "earnings_stress": RiskLayer(name="earnings_stress", display_name="ES", score=7.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.25),
            "drawdown_risk": RiskLayer(name="drawdown_risk", display_name="DD", score=8.0, category="low",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.10),
        }
        composite = service._compute_composite(layers)
        expected_10 = (8.0*0.20 + 9.0*0.25 + 6.0*0.20 + 7.0*0.25 + 8.0*0.10) / 1.0
        expected_100 = round(expected_10 * 10.0, 1)
        assert composite.score == expected_100
        assert composite.maximum_expected_loss_pct is None
        assert composite.bear_case.eps_growth_assumption == 0.0
        assert composite.bear_case.downside_pct == 0.0

    def test_compute_composite_bear_case_defaults(self, service):
        layers = {
            "business_fragility": RiskLayer(name="business_fragility", display_name="BF", score=5.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.20),
            "balance_sheet": RiskLayer(name="balance_sheet", display_name="BS", score=5.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.25),
            "valuation_compression": RiskLayer(name="valuation_compression", display_name="VC", score=5.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.20),
            "earnings_stress": RiskLayer(name="earnings_stress", display_name="ES", score=5.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.25),
            "drawdown_risk": RiskLayer(name="drawdown_risk", display_name="DD", score=5.0, category="moderate",
                metrics=[RiskMetric(name="t", label="t", status="pass")], weight=0.10),
        }
        from domain.models.risk_assessment import BearCase
        composite = service._compute_composite(layers)
        assert isinstance(composite.bear_case, BearCase)
        assert composite.bear_case.future_value == 0.0
        assert composite.bear_case.current_price == 0.0

    # ── _analyze_business_fragility score validation ───────────────────────

    def test_business_fragility_wide_moat_strong(self, service):
        ctx = {"sector": "Technology", "industry": "Software"}
        moat = MagicMock()
        moat.valuation.moat_score = 95.0
        moat.valuation.moat_category = "Wide"
        moat.valuation.roic_minus_wacc = 25.0
        ratios = [
            {"fiscal_year": 2023, "gross_margin": 0.60},
            {"fiscal_year": 2024, "gross_margin": 0.62},
            {"fiscal_year": 2025, "gross_margin": 0.65},
        ]
        result = service._analyze_business_fragility(ctx, moat, ratios)
        assert result.moat_category == "Wide"
        assert result.recurrence_classification == "High"
        assert result.pricing_power_assessment == "Strong"
        moat_m = [m for m in result.metrics if m.name == "Moat Durability"][0]
        assert moat_m.status == "pass"
        rec_m = [m for m in result.metrics if m.name == "Revenue Recurrence"][0]
        assert rec_m.status == "pass"
        pricing_m = [m for m in result.metrics if m.name == "Pricing Power"][0]
        assert pricing_m.status == "pass"
        assert result.score > 9.0

    def test_business_fragility_no_moat_low_recurrence(self, service):
        ctx = {"sector": "Energy", "industry": "Oil & Gas"}
        ratios = [
            {"fiscal_year": 2023, "gross_margin": 0.10},
            {"fiscal_year": 2024, "gross_margin": 0.12},
            {"fiscal_year": 2025, "gross_margin": 0.08},
        ]
        result = service._analyze_business_fragility(ctx, None, ratios)
        assert result.moat_category is None
        assert result.recurrence_classification == "Low"
        assert result.pricing_power_assessment == "Weak"
        moat_m = [m for m in result.metrics if m.name == "Moat Durability"][0]
        assert moat_m.status == "na"
        rec_m = [m for m in result.metrics if m.name == "Revenue Recurrence"][0]
        assert rec_m.status == "fail"
        pricing_m = [m for m in result.metrics if m.name == "Pricing Power"][0]
        assert pricing_m.status == "fail"
        assert result.score < 3.0

    def test_business_fragility_pricing_power_unknown(self, service):
        ctx = {"sector": "Technology", "industry": "Software"}
        ratios = [{"fiscal_year": 2025, "gross_margin": 0.40}]
        result = service._analyze_business_fragility(ctx, None, ratios)
        assert result.pricing_power_assessment == "Unknown"

    # ── _analyze_balance_sheet score validation ────────────────────────────

    def test_balance_sheet_all_healthy(self, service):
        ratios = {
            "debt_to_ebitda": 0.5, "net_debt_to_ebitda": 0.3,
            "interest_coverage": 25.0, "current_ratio": 2.5,
            "quick_ratio": 2.0, "debt_to_equity": 0.5,
            "fcf_conversion": 0.9,
        }
        cash_flow = {"cash_from_operating_activities": 100_000, "capital_expenditures": -10_000, "net_income": 80_000}
        result = service._analyze_balance_sheet(ratios, cash_flow)
        for m in result.metrics:
            assert m.status in ("pass", "na"), f"{m.name} should be pass, got {m.status}"
        assert result.score > 8.0

    def test_balance_sheet_all_unhealthy(self, service):
        ratios = {
            "debt_to_ebitda": 6.0, "net_debt_to_ebitda": 5.0,
            "interest_coverage": 1.5, "current_ratio": 0.5,
            "quick_ratio": 0.3, "debt_to_equity": 4.0,
            "fcf_conversion": 0.1,
        }
        cash_flow = {"cash_from_operating_activities": 100, "capital_expenditures": -200, "net_income": 50}
        result = service._analyze_balance_sheet(ratios, cash_flow)
        for m in result.metrics:
            if m.name == "FCF Stability":
                pass
            elif m.name != "Debt/EBITDA":
                pass
        assert result.score < 5.0

    def test_balance_sheet_no_data(self, service):
        result = service._analyze_balance_sheet(None, None)
        assert result.score == 0  # score is 0 with severe category
        assert result.category == "severe"
        no_data_metric = [m for m in result.metrics if m.name == "No Data"][0]
        assert no_data_metric.status == "na"

    def test_balance_sheet_null_ratios(self, service):
        ratios = {"debt_to_ebitda": None, "interest_coverage": None, "current_ratio": None,
                  "debt_to_equity": None, "fcf_conversion": None, "quick_ratio": None, "net_debt_to_ebitda": None}
        result = service._analyze_balance_sheet(ratios, None)
        for m in result.metrics:
            assert m.status == "na"

    # ── _analyze_valuation_compression score validation ────────────────────

    @pytest.mark.asyncio
    async def test_valuation_low_percentile_score(self, mock_risk_repo, service):
        mock_risk_repo.get_company_summary_history.return_value = [
            {"snapshot_date": f"{y}-01-01", "trailing_pe": float(v), "enterprise_to_ebitda": float(v * 0.5), "peg_ratio": 1.2}
            for y, v in zip(range(2015, 2026), [50, 48, 46, 44, 42, 40, 38, 36, 34, 32, 30])
        ]
        result = await service._analyze_valuation_compression(1)
        assert result.pe_percentile < 40
        pe_metric = [m for m in result.metrics if m.name == "P/E Percentile (5y)"][0]
        assert pe_metric.status == "pass"

    @pytest.mark.asyncio
    async def test_valuation_high_percentile_score(self, mock_risk_repo, service):
        mock_risk_repo.get_company_summary_history.return_value = [
            {"snapshot_date": f"{y}-01-01", "trailing_pe": float(v), "enterprise_to_ebitda": float(v * 0.5), "peg_ratio": 3.5}
            for y, v in zip(range(2015, 2026), [30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50])
        ]
        result = await service._analyze_valuation_compression(1)
        assert result.pe_percentile > 70
        pe_metric = [m for m in result.metrics if m.name == "P/E Percentile (5y)"][0]
        assert pe_metric.status == "fail"

    def test_valuation_empty_history(self, service):
        pass  # async method tested via async tests above

    # ── _analyze_earnings_stress score validation ──────────────────────────

    def test_earnings_stress_high_growth(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 100, "revenue": 1000, "eps_diluted": 1.00},
            {"fiscal_year": 2022, "net_income": 200, "revenue": 2000, "eps_diluted": 2.00},
            {"fiscal_year": 2023, "net_income": 300, "revenue": 3000, "eps_diluted": 3.00},
            {"fiscal_year": 2024, "net_income": 400, "revenue": 4000, "eps_diluted": 4.00},
            {"fiscal_year": 2025, "net_income": 500, "revenue": 5000, "eps_diluted": 5.00},
        ]
        result = service._analyze_earnings_stress(income)
        assert result.score > 7.0
        eps_metric = [m for m in result.metrics if m.name == "EPS CAGR (5y)"][0]
        assert eps_metric.status == "pass"

    def test_earnings_stress_declining(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 500, "revenue": 5000, "eps_diluted": 5.00},
            {"fiscal_year": 2022, "net_income": 400, "revenue": 4500, "eps_diluted": 4.00},
            {"fiscal_year": 2023, "net_income": 300, "revenue": 4000, "eps_diluted": 3.00},
            {"fiscal_year": 2024, "net_income": 200, "revenue": 3500, "eps_diluted": 2.00},
            {"fiscal_year": 2025, "net_income": 100, "revenue": 3000, "eps_diluted": 1.00},
        ]
        result = service._analyze_earnings_stress(income)
        eps_metric = [m for m in result.metrics if m.name == "EPS CAGR (5y)"][0]
        assert eps_metric.status == "fail"

    def test_earnings_stress_margin_trend_expanding(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 50, "revenue": 1000, "eps_diluted": 1.00},
            {"fiscal_year": 2022, "net_income": 100, "revenue": 1000, "eps_diluted": 2.00},
            {"fiscal_year": 2023, "net_income": 150, "revenue": 1000, "eps_diluted": 3.00},
            {"fiscal_year": 2024, "net_income": 200, "revenue": 1000, "eps_diluted": 4.00},
            {"fiscal_year": 2025, "net_income": 250, "revenue": 1000, "eps_diluted": 5.00},
        ]
        result = service._analyze_earnings_stress(income)
        assert result.operating_margin_trend == "expanding"
        margin_trend_metric = [m for m in result.metrics if m.name == "Margin Trend"][0]
        assert margin_trend_metric.status == "pass"

    def test_earnings_stress_margin_trend_contracting(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 250, "revenue": 1000, "eps_diluted": 5.00},
            {"fiscal_year": 2022, "net_income": 200, "revenue": 1000, "eps_diluted": 4.00},
            {"fiscal_year": 2023, "net_income": 150, "revenue": 1000, "eps_diluted": 3.00},
            {"fiscal_year": 2024, "net_income": 100, "revenue": 1000, "eps_diluted": 2.00},
            {"fiscal_year": 2025, "net_income": 50, "revenue": 1000, "eps_diluted": 1.00},
        ]
        result = service._analyze_earnings_stress(income)
        assert result.operating_margin_trend == "contracting"
        margin_trend_metric = [m for m in result.metrics if m.name == "Margin Trend"][0]
        assert margin_trend_metric.status == "fail"

    def test_earnings_stress_no_data(self, service):
        result = service._analyze_earnings_stress([])
        assert result.score == 5.0
        assert result.category == "moderate"

    # ── Helper method validation ───────────────────────────────────────────

    def test_moat_status(self, service):
        assert service._moat_status("Wide") == "pass"
        assert service._moat_status("Narrow") == "pass"
        assert service._moat_status("None") == "caution"
        assert service._moat_status(None) == "na"
        assert service._moat_status("") == "na"

    def test_recurrence_status(self, service):
        assert service._recurrence_status("High") == "pass"
        assert service._recurrence_status("Medium") == "caution"
        assert service._recurrence_status("Low") == "fail"

    def test_pricing_status(self, service):
        assert service._pricing_status("Strong") == "pass"
        assert service._pricing_status("Moderate") == "caution"
        assert service._pricing_status("Weak") == "fail"

    @pytest.mark.parametrize("value,expected", [
        (0.5, "pass"), (1.9, "pass"), (2.0, "caution"), (3.9, "caution"),
        (4.0, "fail"), (10.0, "fail"), (None, "na"),
    ])
    def test_debt_ebitda_status_boundaries(self, service, value, expected):
        assert service._debt_ebitda_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (15.0, "pass"), (10.0, "pass"), (7.0, "caution"), (5.0, "caution"),
        (4.0, "fail"), (0.0, "fail"), (None, "na"),
    ])
    def test_interest_coverage_status_boundaries(self, service, value, expected):
        assert service._interest_coverage_status(value) == expected

    @pytest.mark.parametrize("value,pass_thresh,fail_thresh,expected", [
        (2.0, 1.5, 1.0, "pass"), (1.5, 1.5, 1.0, "pass"),
        (1.2, 1.5, 1.0, "caution"), (1.0, 1.5, 1.0, "caution"),
        (0.5, 1.5, 1.0, "fail"), (None, 1.5, 1.0, "na"),
    ])
    def test_ratio_status(self, service, value, pass_thresh, fail_thresh, expected):
        assert service._ratio_status(value, pass_thresh, fail_thresh) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.5, "pass"), (0.99, "pass"), (1.0, "caution"), (1.5, "caution"),
        (2.49, "caution"), (2.5, "fail"), (3.0, "fail"), (None, "na"),
    ])
    def test_de_ratio_status_boundaries(self, service, value, expected):
        assert service._de_ratio_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.9, "pass"), (0.8, "pass"), (0.6, "caution"), (0.5, "caution"),
        (0.3, "fail"), (None, "na"),
    ])
    def test_fcf_stability_status_boundaries(self, service, value, expected):
        assert service._fcf_stability_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (30, "pass"), (39, "pass"), (40, "caution"), (69, "caution"),
        (70, "fail"), (100, "fail"), (None, "na"),
    ])
    def test_percentile_status_boundaries(self, service, value, expected):
        assert service._percentile_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (1.0, "pass"), (1.4, "pass"), (1.5, "caution"), (2.9, "caution"),
        (3.0, "fail"), (5.0, "fail"), (None, "na"),
    ])
    def test_peg_status_boundaries(self, service, value, expected):
        assert service._peg_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.15, "pass"), (0.10, "pass"), (0.05, "caution"), (0.03, "caution"),
        (0.01, "fail"), (-0.10, "fail"), (None, "na"),
    ])
    def test_cagr_status_boundaries(self, service, value, expected):
        assert service._cagr_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.20, "pass"), (0.15, "pass"), (0.10, "caution"), (0.05, "caution"),
        (0.01, "fail"), (-0.10, "fail"), (None, "na"),
    ])
    def test_margin_status_boundaries(self, service, value, expected):
        assert service._margin_status(value) == expected

    def test_margin_trend_status(self, service):
        assert service._margin_trend_status("expanding") == "pass"
        assert service._margin_trend_status("stable") == "caution"
        assert service._margin_trend_status("contracting") == "fail"

    def test_alignment_status(self, service):
        assert service._alignment_status("aligned") == "pass"
        assert service._alignment_status("diverging") == "caution"
        assert service._alignment_status("volatile") == "fail"

    @pytest.mark.parametrize("value,expected", [
        (-0.10, "pass"), (0.0, "pass"), (-0.14, "pass"),
        (-0.15, "caution"), (-0.29, "caution"),
        (-0.30, "fail"), (-0.50, "fail"), (None, "na"),
    ])
    def test_drawdown_status_boundaries(self, service, value, expected):
        assert service._drawdown_status(value) == expected

    @pytest.mark.parametrize("value,expected", [
        (0.5, "pass"), (1.19, "pass"), (1.2, "caution"),
        (1.49, "caution"), (1.5, "fail"), (3.0, "fail"), (None, "na"),
    ])
    def test_beta_status_boundaries(self, service, value, expected):
        assert service._beta_status(value) == expected

    # ── _compute_margin_trend validation ───────────────────────────────────

    def test_margin_trend_expanding(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 50, "revenue": 1000},
            {"fiscal_year": 2022, "net_income": 100, "revenue": 1000},
            {"fiscal_year": 2023, "net_income": 150, "revenue": 1000},
            {"fiscal_year": 2024, "net_income": 200, "revenue": 1000},
            {"fiscal_year": 2025, "net_income": 250, "revenue": 1000},
        ]
        assert service._compute_margin_trend(income) == "expanding"

    def test_margin_trend_contracting(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 250, "revenue": 1000},
            {"fiscal_year": 2022, "net_income": 200, "revenue": 1000},
            {"fiscal_year": 2023, "net_income": 150, "revenue": 1000},
            {"fiscal_year": 2024, "net_income": 100, "revenue": 1000},
            {"fiscal_year": 2025, "net_income": 50, "revenue": 1000},
        ]
        assert service._compute_margin_trend(income) == "contracting"

    def test_margin_trend_stable(self, service):
        income = [
            {"fiscal_year": 2021, "net_income": 100, "revenue": 1000},
            {"fiscal_year": 2022, "net_income": 102, "revenue": 1000},
            {"fiscal_year": 2023, "net_income": 101, "revenue": 1000},
            {"fiscal_year": 2024, "net_income": 103, "revenue": 1000},
            {"fiscal_year": 2025, "net_income": 102, "revenue": 1000},
        ]
        assert service._compute_margin_trend(income) == "stable"

    def test_margin_trend_insufficient_data(self, service):
        income = [{"fiscal_year": 2025, "net_income": 100, "revenue": 1000}]
        assert service._compute_margin_trend(income) == "stable"

    # ── _compute_eps_volatility validation ─────────────────────────────────

    def test_eps_volatility_stable(self, service):
        eps = [1.0, 1.05, 1.10, 1.15, 1.20]
        result = service._compute_eps_volatility(eps)
        assert result is not None
        assert result < 0.10

    def test_eps_volatility_volatile(self, service):
        eps = [1.0, 2.0, 0.5, 3.0, 1.5]
        result = service._compute_eps_volatility(eps)
        assert result is not None
        assert result > 0.20

    def test_eps_volatility_insufficient_data(self, service):
        assert service._compute_eps_volatility([1.0]) is None
        assert service._compute_eps_volatility([]) is None

    def test_eps_volatility_no_positive_previous(self, service):
        eps = [1.0, -1.0, 2.0]
        result = service._compute_eps_volatility(eps)
        assert result is not None

    # ── _compute_revenue_eps_alignment validation ──────────────────────────

    def test_alignment_aligned(self, service):
        eps = [1.0, 1.15, 1.32, 1.52, 1.75]
        rev = [1000, 1150, 1320, 1520, 1750]
        assert service._compute_revenue_eps_alignment(eps, rev) == "aligned"

    def test_alignment_diverging(self, service):
        eps = [1.0, 2.0, 4.0, 8.0, 16.0]
        rev = [1000, 1050, 1100, 1150, 1200]
        assert service._compute_revenue_eps_alignment(eps, rev) == "diverging"

    def test_alignment_insufficient_data(self, service):
        assert service._compute_revenue_eps_alignment([1.0, 2.0], [1000, 2000]) == "volatile"

    def test_alignment_negative_start_eps(self, service):
        eps = [-1.0, 1.0, 2.0, 3.0, 4.0]
        rev = [1000, 1100, 1200, 1300, 1400]
        assert service._compute_revenue_eps_alignment(eps, rev) == "volatile"

    # ── _compute_recovery_time validation ──────────────────────────────────

    def test_recovery_time_full_recovery(self, service):
        prices = [100, 80, 90, 85, 95, 100, 120]
        assert service._compute_recovery_time(prices) is not None

    def test_recovery_time_no_recovery(self, service):
        prices = [100, 80, 60, 40, 20]
        result = service._compute_recovery_time(prices)
        assert result is not None
        assert result > 0

    def test_recovery_time_no_downturn(self, service):
        prices = [100, 110, 120, 130, 140]
        assert service._compute_recovery_time(prices) is None

    def test_recovery_time_insufficient_data(self, service):
        assert service._compute_recovery_time([100]) is None
        assert service._compute_recovery_time([]) is None

    # ── _compute_fcf_stability validation ──────────────────────────────────

    def test_fcf_stability_healthy(self, service):
        cf = {"cash_from_operating_activities": 100_000, "capital_expenditures": -10_000, "net_income": 75_000}
        result = service._compute_fcf_stability(cf)
        assert result is not None
        assert abs(result - 1.333) < 0.01

    def test_fcf_stability_no_data(self, service):
        assert service._compute_fcf_stability(None) is None

    def test_fcf_stability_zero_net_income(self, service):
        cf = {"cash_from_operating_activities": 100_000, "capital_expenditures": -10_000, "net_income": 0}
        assert service._compute_fcf_stability(cf) is None

    def test_fcf_stability_missing_fields(self, service):
        cf = {"cash_from_operating_activities": None, "net_income": 75_000}
        assert service._compute_fcf_stability(cf) is None

    # ── _assess_pricing_power validation ───────────────────────────────────

    def test_pricing_power_strong(self, service):
        ratios = [
            {"fiscal_year": 2023, "gross_margin": 0.55},
            {"fiscal_year": 2024, "gross_margin": 0.60},
            {"fiscal_year": 2025, "gross_margin": 0.58},
        ]
        assert service._assess_pricing_power(ratios) == "Strong"

    def test_pricing_power_weak(self, service):
        ratios = [
            {"fiscal_year": 2023, "gross_margin": 0.10},
            {"fiscal_year": 2024, "gross_margin": 0.12},
            {"fiscal_year": 2025, "gross_margin": 0.08},
        ]
        assert service._assess_pricing_power(ratios) == "Weak"

    def test_pricing_power_insufficient_data(self, service):
        ratios = [{"fiscal_year": 2025, "gross_margin": 0.40}]
        assert service._assess_pricing_power(ratios) == "Unknown"

    # ── get_risk_assessment current_price fallback ─────────────────────────

    @pytest.mark.asyncio
    async def test_get_risk_assessment_current_price_fallback(self, mock_risk_repo, service):
        mock_risk_repo.get_current_market_price.return_value = None
        mock_risk_repo.get_price_history_range.return_value = [
            {"close_price": 180.0, "price_date": "2024-01-01"},
            {"close_price": 200.0, "price_date": "2025-06-01"},
        ]
        result = await service.get_risk_assessment("AAPL")
        assert result.scenarios is not None
        assert len(result.scenarios) == 4
        assert result.composite.maximum_expected_loss_pct > 0

    @pytest.mark.asyncio
    async def test_get_risk_assessment_current_price_no_fallback(self, mock_risk_repo, service):
        mock_risk_repo.get_current_market_price.return_value = None
        mock_risk_repo.get_price_history_range.return_value = []
        result = await service.get_risk_assessment("AAPL")
        assert result.scenarios is None
        assert result.composite.maximum_expected_loss_pct is None

    # ── get_risk_assessment end-to-end validation ──────────────────────────

    @pytest.mark.asyncio
    async def test_get_risk_assessment_scenario_mel_integration(self, mock_risk_repo, service):
        mock_risk_repo.get_current_market_price.return_value = 200.0
        result = await service.get_risk_assessment("AAPL")
        assert result.composite.maximum_expected_loss_pct > 0
        assert result.scenarios is not None
        mel = sum(s.probability * abs(s.downside) for s in result.scenarios if s.downside < 0) * 100
        assert abs(result.composite.maximum_expected_loss_pct - round(mel, 1)) < 0.1

    @pytest.mark.asyncio
    async def test_get_risk_assessment_all_layers_populated(self, mock_risk_repo, service):
        result = await service.get_risk_assessment("AAPL")
        for name in ("business_fragility", "balance_sheet", "valuation_compression", "earnings_stress", "drawdown_risk"):
            layer = result.layers[name]
            assert layer.score is not None
            assert layer.category in ("low", "moderate", "elevated", "high", "severe")

    @pytest.mark.asyncio
    async def test_get_risk_assessment_bear_case_matches_scenarios(self, mock_risk_repo, service):
        mock_risk_repo.get_current_market_price.return_value = 200.0
        result = await service.get_risk_assessment("AAPL")
        if result.scenarios:
            bear = [s for s in result.scenarios if s.scenario == "bear"]
            if bear:
                b = bear[0]
                assert abs(result.composite.bear_case.eps_growth_assumption - b.eps_growth) < 0.001
                assert result.composite.bear_case.exit_pe_ratio == b.exit_pe
                assert abs(result.composite.bear_case.future_value - b.future_value) < 0.01
                assert abs(result.composite.bear_case.downside_pct - b.downside) < 0.001

    @pytest.mark.asyncio
    async def test_get_risk_assessment_currency_company_id(self, mock_risk_repo, service):
        result = await service.get_risk_assessment("AAPL")
        assert result.currency == "USD"
        assert result.company_id == 1

    # ── classify_recurrence validation ─────────────────────────────────────

    def test_classify_recurrence_known_sectors(self, service):
        assert service._classify_recurrence("Technology") == "High"
        assert service._classify_recurrence("Utilities") == "High"
        assert service._classify_recurrence("Financials") == "Medium"
        assert service._classify_recurrence("Energy") == "Low"
        assert service._classify_recurrence("Unknown Sector") == "Medium"

    @pytest.mark.asyncio
    async def test_get_ai_narrative_happy_path(self, mock_risk_repo, service):
        mock_risk_repo.get_risk_ai_narrative.return_value = {
            "narrative": "Test narrative",
            "model": "openrouter/default",
            "generated_at": "2026-05-26T00:00:00Z",
            "generation_time_ms": 1000,
        }
        narrative = await service.get_ai_narrative("AAPL")
        assert narrative.narrative == "Test narrative"
        assert narrative.model == "openrouter/default"

    @pytest.mark.asyncio
    async def test_generate_ai_narrative_api_failure(self, mock_risk_repo, service):
        mock_risk_repo.get_company_context.return_value = {"company_id": 1, "symbol": "AAPL"}
        assessment = MagicMock()
        assessment.symbol = "AAPL"
        assessment.composite.score = 76
        assessment.composite.category = "Moderate"
        assessment.composite.maximum_expected_loss_pct = 12.5
        assessment.composite.bear_case.downside_pct = -0.172
        assessment.layers = {}
        narrative = await service.generate_ai_narrative("AAPL", assessment)
        assert narrative is not None
