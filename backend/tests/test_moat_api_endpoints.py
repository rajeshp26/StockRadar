import sys
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock defeatbeta_api before any api.analysis imports trigger it
_fake_defeat = MagicMock()
_fake_ticker = MagicMock()
sys.modules["defeatbeta_api"] = _fake_defeat
sys.modules["defeatbeta_api.data"] = _fake_defeat
sys.modules["defeatbeta_api.data.ticker"] = _fake_ticker

# Pre-import the router module so patches below can find it
from api import analysis as _analysis_mod


def _mock_user():
    return {"user_id": "test-user-123", "email": "test@example.com"}


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    """Disable slowapi rate limiter for all tests."""
    mock_limiter = MagicMock()
    mock_limiter.limit.return_value = lambda f: f
    with patch.object(_analysis_mod, "limiter", mock_limiter):
        yield


@pytest.fixture
def test_app():
    """Build a minimal FastAPI app with the moat router and auth override."""
    from fastapi import FastAPI

    from api.analysis import router as moat_router
    from dependencies import get_current_user_dep

    app = FastAPI()
    app.include_router(moat_router)
    app.dependency_overrides[get_current_user_dep] = _mock_user
    return app


@pytest.fixture
def client(test_app):
    from starlette.testclient import TestClient
    with TestClient(test_app) as c:
        yield c


@pytest.fixture
def mock_moat_response():
    """Standard successful MoatResponse dict."""
    from domain.models.analysis_moat import (
        MoatApplicability,
        MoatDataQuality,
        MoatIndustryContext,
        MoatInputs,
        MoatResponse,
        MoatValuation,
    )
    resp = MoatResponse(
        symbol="AAPL",
        company_id=1,
        currency="USD",
        inputs=MoatInputs(fiscal_years_used=5),
        valuation=MoatValuation(moat_score=85.0, moat_category="Wide",
                                roic=0.32, wacc=0.10, roic_minus_wacc=22.0,
                                gross_margin_pct=43.0, operating_margin_pct=30.0,
                                net_margin_pct=25.0, roic_5y_avg=0.30, roic_5y_std=0.02,
                                roic_stability_score=90.0, asset_turnover=0.88,
                                capital_efficiency_score=85.0),
        industry_context=MoatIndustryContext(),
        applicability=MoatApplicability(score=85, category="Applicable"),
        data_quality=MoatDataQuality(last_computed_at="2025-01-01T00:00:00Z"),
    )
    return resp


@pytest.fixture
def mock_evidence_response():
    """Standard successful MoatEvidenceResponse dict."""
    from domain.models.analysis_moat import MoatEvidenceResponse, MoatKeywordEvidence
    resp = MoatEvidenceResponse(
        symbol="AAPL",
        company_id=1,
        text_analysis_available=True,
        total_keyword_matches=5,
        evidence_by_group={
            "intangible_assets": [
                MoatKeywordEvidence(keyword="patent", keyword_group="intangible_assets",
                                    section="item_1_business", context="The company holds patents")
            ]
        },
        groups_found=["intangible_assets"],
    )
    return resp


@pytest.fixture
def mock_ai_response():
    """Standard successful MoatAiResponse dict."""
    from domain.models.analysis_moat import MoatAiNarrative, MoatAiResponse
    resp = MoatAiResponse(
        symbol="AAPL",
        company_id=1,
        narrative=MoatAiNarrative(
            narrative="Strong economic moat based on brand power and ecosystem lock-in.",
            model="openrouter/default",
            generated_at=datetime.now(UTC).isoformat(),
        ),
        available=True,
    )
    return resp


class TestMoatAPIEndpoints:
    """API-01 through API-09: Endpoint integration tests."""

    # ── API-01: GET /analysis/{symbol}/moat (success) ─────────────

    def test_get_moat_analysis_success(self, client, mock_moat_response):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_analysis = AsyncMock(return_value=mock_moat_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/moat")
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "AAPL"
            assert data["valuation"]["moat_score"] == 85.0
            assert data["valuation"]["moat_category"] == "Wide"

    # ── API-02: GET /analysis/{symbol}/moat (unknown symbol) ───────

    def test_get_moat_analysis_unknown_symbol(self, client):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_analysis = AsyncMock(
                side_effect=ValueError("Unknown symbol: UNKNOWN")
            )
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/UNKNOWN/moat")
            assert resp.status_code == 404
            assert "Unknown symbol" in resp.json()["detail"]

    # ── API-03: GET /analysis/{symbol}/moat?force=true ────────────

    def test_get_moat_analysis_force(self, client, mock_moat_response):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_analysis = AsyncMock(return_value=mock_moat_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/moat", params={"force": True})
            assert resp.status_code == 200
            mock_svc.get_moat_analysis.assert_called_with("AAPL", force=True)

    # ── API-04: GET /analysis/{symbol}/moat/evidence (success) ─────

    def test_get_moat_evidence_success(self, client, mock_evidence_response):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_evidence = AsyncMock(return_value=mock_evidence_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/moat/evidence")
            assert resp.status_code == 200
            data = resp.json()
            assert data["symbol"] == "AAPL"
            assert data["total_keyword_matches"] == 5

    # ── API-05: GET /analysis/{symbol}/moat/evidence (not found) ───

    def test_get_moat_evidence_not_found(self, client):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_evidence = AsyncMock(
                side_effect=ValueError("No EDGAR evidence found for symbol")
            )
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/UNKNOWN/moat/evidence")
            assert resp.status_code == 404

    # ── API-06: POST /analysis/{symbol}/moat/ai (generate) ─────────

    def test_generate_moat_ai_narrative(self, client, mock_ai_response):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.generate_moat_ai_narrative = AsyncMock(return_value=mock_ai_response)
            mock_factory.return_value = mock_svc

            resp = client.post("/analysis/AAPL/moat/ai")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True
            assert "moat" in data["narrative"]["narrative"].lower()

    # ── API-07: GET /analysis/{symbol}/moat/ai (get cached) ────────

    def test_get_moat_ai_narrative(self, client, mock_ai_response):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_ai_narrative = AsyncMock(return_value=mock_ai_response)
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/moat/ai")
            assert resp.status_code == 200
            data = resp.json()
            assert data["available"] is True

    # ── API-08: GET /analysis/{symbol}/moat (invalid symbol) ───────

    def test_get_moat_analysis_invalid_symbol(self, client):
        resp = client.get("/analysis/INVALID@@@/moat")
        assert resp.status_code == 422

    # ── API-09: GET /analysis/{symbol}/moat (service error) ───────

    def test_get_moat_analysis_service_error(self, client):
        with patch("api.analysis._get_moat_service") as mock_factory:
            mock_svc = MagicMock()
            mock_svc.get_moat_analysis = AsyncMock(
                side_effect=Exception("Internal database error")
            )
            mock_factory.return_value = mock_svc

            resp = client.get("/analysis/AAPL/moat")
            assert resp.status_code == 500
            assert "Moat analysis failed" in resp.json()["detail"]
