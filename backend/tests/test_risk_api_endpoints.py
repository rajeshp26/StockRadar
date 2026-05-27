import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


_fake_defeat = MagicMock()
_fake_ticker = MagicMock()
sys.modules["defeatbeta_api"] = _fake_defeat
sys.modules["defeatbeta_api.data"] = _fake_defeat
sys.modules["defeatbeta_api.data.ticker"] = _fake_ticker

from api import analysis as _analysis_mod


def _mock_user():
    return {"user_id": "test-user-123", "email": "test@example.com"}


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    mock_limiter = MagicMock()
    mock_limiter.limit.return_value = lambda f: f
    with patch.object(_analysis_mod, "limiter", mock_limiter):
        yield


@pytest.fixture
def test_app():
    from fastapi import FastAPI
    from dependencies import get_current_user_dep
    from api.analysis import router as analysis_router

    app = FastAPI()
    app.include_router(analysis_router)
    app.dependency_overrides[get_current_user_dep] = _mock_user
    return app


@pytest.fixture
def client(test_app):
    from starlette.testclient import TestClient
    with TestClient(test_app) as c:
        yield c


@pytest.fixture
def mock_risk_response():
    from domain.models.risk_assessment import (
        RiskAssessmentResponse, CompositeScore, BearCase, RiskDataQuality,
        BusinessFragility, BalanceSheetRisk, ValuationCompressionRisk,
        EarningsStressRisk, DrawdownRisk, RiskMetric,
    )
    return RiskAssessmentResponse(
        symbol="AAPL",
        company_id=1,
        currency="USD",
        composite=CompositeScore(
            score=76.0,
            category="Moderate",
            maximum_expected_loss_pct=12.5,
            bear_case=BearCase(
                eps_growth_assumption=0.02, exit_pe_ratio=15,
                future_value=165.62, current_price=200.0, downside_pct=-0.172,
            ),
        ),
        layers={
            "business_fragility": BusinessFragility(
                name="business_fragility", display_name="Business Fragility",
                score=8.2, category="low",
                metrics=[RiskMetric(name="Moat", label="Wide", status="pass")],
                weight=0.20, moat_score=85.0, moat_category="Wide",
            ),
            "balance_sheet": BalanceSheetRisk(
                name="balance_sheet", display_name="Balance Sheet",
                score=9.1, category="low",
                metrics=[RiskMetric(name="D/E", label="0.2x", status="pass")],
                weight=0.25, debt_to_ebitda=0.2,
            ),
            "valuation_compression": ValuationCompressionRisk(
                name="valuation_compression", display_name="Valuation Compression",
                score=6.5, category="moderate",
                metrics=[RiskMetric(name="P/E", label="75th", status="caution")],
                weight=0.20, pe_percentile=75.0,
            ),
            "earnings_stress": EarningsStressRisk(
                name="earnings_stress", display_name="Earnings Stress",
                score=7.8, category="low",
                metrics=[RiskMetric(name="EPS CAGR", label="15%", status="pass")],
                weight=0.25, eps_cagr_5y=0.15,
            ),
            "drawdown_risk": DrawdownRisk(
                name="drawdown_risk", display_name="Drawdown Risk",
                score=7.0, category="moderate",
                metrics=[RiskMetric(name="Max DD", label="-38%", status="caution")],
                weight=0.10, max_drawdown_5y=-0.38,
            ),
        },
        data_quality=RiskDataQuality(
            data_sources="database", last_computed_at="2026-05-26T00:00:00Z",
        ),
    )


class TestRiskAPISnakeCaseFields:
    """IT-B7: Verify all response fields use snake_case."""

    def test_risk_assessment_response_shape(self, client, mock_risk_response):
        with patch("api.analysis._get_risk_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_risk_assessment = AsyncMock(return_value=mock_risk_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/risk-assessment")
            assert resp.status_code == 200
            data = resp.json()

            assert "company_id" in data, "Missing snake_case: company_id"
            assert "companyId" not in data, "camelCase companyId leaked"
            assert "data_quality" in data, "Missing snake_case: data_quality"
            assert "dataQuality" not in data, "camelCase dataQuality leaked"
            assert "ai_narrative" not in data or "aiNarrative" not in data
            assert "maximum_expected_loss_pct" in data["composite"]
            assert "maximumExpectedLossPct" not in data["composite"]
            assert "bear_case" in data["composite"]
            assert "bearCase" not in data["composite"]

            bc = data["composite"]["bear_case"]
            assert "eps_growth_assumption" in bc
            assert "exit_pe_ratio" in bc
            assert "future_value" in bc
            assert "current_price" in bc
            assert "downside_pct" in bc

            for layer_name, layer in data["layers"].items():
                assert "display_name" in layer, f"{layer_name} missing display_name"
                assert "displayName" not in layer, f"{layer_name} has camelCase displayName"

            dq = data["data_quality"]
            assert "data_sources" in dq
            assert "fallbacks_used" in dq
            assert "last_computed_at" in dq


class TestRiskAPIEndpoints:
    """IT-B1 through IT-B6: Integration tests."""

    def test_get_risk_assessment_success(self, client, mock_risk_response):
        with patch("api.analysis._get_risk_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_risk_assessment = AsyncMock(return_value=mock_risk_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/risk-assessment")
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "AAPL"
            assert data["composite"]["score"] == 76.0
            assert len(data["layers"]) == 5

    def test_get_risk_assessment_unknown_symbol(self, client):
        with patch("api.analysis._get_risk_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_risk_assessment = AsyncMock(
                side_effect=ValueError("Symbol 'ZZZZZ' not found.")
            )
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/ZZZZZ/risk-assessment")
            assert resp.status_code == 404
            assert "not found" in resp.json()["detail"]

    def test_get_risk_assessment_force_recompute(self, client, mock_risk_response):
        with patch("api.analysis._get_risk_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_risk_assessment = AsyncMock(return_value=mock_risk_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/risk-assessment", params={"force": True})
            assert resp.status_code == 200
            mock_svc.get_risk_assessment.assert_called_with("AAPL", force=True)

    def test_post_risk_ai_narrative(self, client, mock_risk_response):
        with patch("api.analysis._get_risk_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_risk_assessment = AsyncMock(return_value=mock_risk_response)
            from domain.models.risk_assessment import RiskAiNarrative
            mock_svc.generate_ai_narrative = AsyncMock(
                return_value=RiskAiNarrative(
                    narrative="Test risk narrative",
                    model="openrouter/default",
                )
            )
            mock_factory.return_value = mock_svc

            resp = client.post("/analysis/AAPL/risk-assessment/ai")
            assert resp.status_code == 200
            data = resp.json()
            assert "narrative" in data
            assert "model" in data

    def test_get_risk_assessment_invalid_symbol(self, client):
        resp = client.get("/analysis/INVALID@@@/risk-assessment")
        assert resp.status_code == 422

    def test_get_risk_assessment_service_error(self, client):
        with patch("api.analysis._get_risk_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_risk_assessment = AsyncMock(
                side_effect=Exception("Internal error")
            )
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/risk-assessment")
            assert resp.status_code == 500
            assert "Risk assessment failed" in resp.json()["detail"]
