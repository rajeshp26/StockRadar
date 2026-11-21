from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# I1d: removed module-level sys.modules injection of fake `defeatbeta_api` and
# `database`. Those hacks leaked into every later-collected test (notably
# test_database.py, where `import database` returned a MagicMock) and are no
# longer needed — the real imports work. Dependencies are patched per-test.
from api import portfolio as _portfolio_mod


def _mock_user():
    return {"sub": "test-user-123", "email": "test@example.com"}


@pytest.fixture(autouse=True)
def _disable_rate_limiter():
    mock_limiter = MagicMock()
    mock_limiter.limit.return_value = lambda f: f
    with patch.object(_portfolio_mod, "limiter", mock_limiter):
        yield


@pytest.fixture(autouse=True)
def _mock_supabase_deps():
    with (
        patch("api.portfolio.supabase") as mock_supabase,
        patch("api.portfolio.SupabaseUserRepository") as mock_repo_cls,
    ):
        mock_repo = MagicMock()
        mock_repo.find_by_firebase_uid.return_value = {"user_id": 42}
        mock_repo_cls.return_value = mock_repo
        yield


@pytest.fixture
def test_app():
    from fastapi import FastAPI

    from api.portfolio import router as portfolio_router
    from dependencies import get_current_user_dep

    app = FastAPI()
    app.include_router(portfolio_router)
    app.dependency_overrides[get_current_user_dep] = _mock_user
    return app


@pytest.fixture
def client(test_app):
    from starlette.testclient import TestClient
    with TestClient(test_app) as c:
        yield c


def _make_schema_response(schema_cls, **kwargs):
    return schema_cls(**kwargs)


def _make_mock_risk_service(**overrides):
    from schemas_portfolio import (
        CovarianceResponse,
        DrawdownResponse,
        EfficientFrontierResponse,
        FactorExposureResponse,
        RiskContributionItem,
        RiskContributionResponse,
        RiskMetricsResponse,
        RollingSharpeResponse,
    )

    svc = MagicMock()
    svc.compute_risk_metrics = AsyncMock(return_value=_make_schema_response(
        RiskMetricsResponse,
        success=True, period="1Y",
        sharpe_ratio=1.25, sortino_ratio=1.80,
        variance=0.0324, std_deviation=0.18,
        downside_deviation=0.12,
        max_drawdown=-0.15, max_drawdown_pct=-0.15,
        value_at_risk_95=-0.025, value_at_risk_99=-0.035,
        conditional_var_95=-0.04, beta=1.10, alpha=0.02,
        tracking_error=0.08, information_ratio=0.25,
        **{k: v for k, v in overrides.items() if k != "series"},
    ))
    svc.compute_drawdown = AsyncMock(return_value=_make_schema_response(
        DrawdownResponse,
        success=True, period="1Y",
        drawdowns=[{"date": "2026-01-15", "value": 100.0, "drawdown_pct": 0.0}],
        max_drawdown=0.0, max_drawdown_pct=0.0,
    ))
    svc.compute_covariance_matrix = AsyncMock(return_value=_make_schema_response(
        CovarianceResponse,
        success=True, period="1Y",
        holdings=["AAPL", "MSFT"],
        covariance_matrix=[[0.04, 0.02], [0.02, 0.03]],
        correlation_matrix=[[1.0, 0.58], [0.58, 1.0]],
    ))
    svc.compute_efficient_frontier = AsyncMock(return_value=_make_schema_response(
        EfficientFrontierResponse,
        success=True,
        frontier=[
            {"volatility": 0.15, "expected_return": 0.10, "sharpe_ratio": 0.67,
             "weights": {"AAPL": 0.6, "MSFT": 0.4}},
        ],
    ))
    svc.compute_rolling_sharpe = AsyncMock(return_value=_make_schema_response(
        RollingSharpeResponse,
        success=True, period="1Y", window=252,
        series=[{"date": "2026-05-01", "sharpe_ratio": 1.25}],
    ))
    svc.compute_risk_contribution = AsyncMock(return_value=_make_schema_response(
        RiskContributionResponse,
        success=True,
        contributions=[
            RiskContributionItem(symbol="AAPL", weight=0.6, marginal_risk=0.30,
                                 component_risk=0.18, risk_pct=0.55),
        ],
        total_risk=0.18,
    ))
    svc.compute_market_exposure = AsyncMock(return_value=_make_schema_response(
        FactorExposureResponse,
        success=True,
        exposures={"market": 1.05, "alpha": 0.02},
        r_squared=0.65,
    ))
    return svc


class TestPortfolioRiskAPI:
    """Integration tests for portfolio risk endpoints."""

    def test_risk_metrics_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/risk-metrics?period=1Y")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["sharpe_ratio"] == 1.25
            assert data["sortino_ratio"] == 1.80
            assert data["std_deviation"] == 0.18
            assert data["max_drawdown_pct"] == -0.15
            assert data["value_at_risk_95"] == -0.025
            assert data["conditional_var_95"] == -0.04
            assert data["period"] == "1Y"

    def test_risk_metrics_with_account_ids(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/risk-metrics?period=6M&account_ids=1,2")
            assert resp.status_code == 200
            mock_svc.compute_risk_metrics.assert_called_once()
            call_kwargs = mock_svc.compute_risk_metrics.call_args[1]
            assert call_kwargs["period"] == "6M"
            assert call_kwargs["account_ids"] == [1, 2]

    def test_risk_metrics_service_error(self, client):
        mock_svc = MagicMock()
        mock_svc.compute_risk_metrics = AsyncMock(side_effect=Exception("boom"))
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/risk-metrics")
            assert resp.status_code == 500

    def test_risk_metrics_returns_correct_schema(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/risk-metrics")
            data = resp.json()
            assert "sharpe_ratio" in data
            assert "sortino_ratio" in data
            assert "std_deviation" in data
            assert "variance" in data
            assert "max_drawdown_pct" in data
            assert "value_at_risk_95" in data
            assert "value_at_risk_99" in data
            assert "conditional_var_95" in data
            assert "beta" in data
            assert "alpha" in data
            assert "period" in data

    def test_drawdown_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/drawdown?period=1Y")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["period"] == "1Y"
            assert isinstance(data["drawdowns"], list)
            assert data["max_drawdown_pct"] == 0.0
            assert "date" in data["drawdowns"][0]
            assert "value" in data["drawdowns"][0]
            assert "drawdown_pct" in data["drawdowns"][0]

    def test_drawdown_service_error(self, client):
        mock_svc = MagicMock()
        mock_svc.compute_drawdown = AsyncMock(side_effect=Exception("boom"))
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/drawdown")
            assert resp.status_code == 500

    def test_covariance_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/covariance?period=1Y")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert len(data["covariance_matrix"]) == 2
            assert len(data["correlation_matrix"]) == 2
            assert data["holdings"] == ["AAPL", "MSFT"]

    def test_covariance_service_error(self, client):
        mock_svc = MagicMock()
        mock_svc.compute_covariance_matrix = AsyncMock(side_effect=Exception("boom"))
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/covariance")
            assert resp.status_code == 500

    def test_efficient_frontier_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/efficient-frontier?points=50")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert len(data["frontier"]) == 1
            pt = data["frontier"][0]
            assert "expected_return" in pt
            assert "volatility" in pt
            assert "sharpe_ratio" in pt
            assert "weights" in pt

    def test_efficient_frontier_points_param(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/efficient-frontier?points=100")
            assert resp.status_code == 200
            mock_svc.compute_efficient_frontier.assert_called_once()
            assert mock_svc.compute_efficient_frontier.call_args[1]["points"] == 100

    def test_efficient_frontier_invalid_points(self, client):
        resp = client.get("/portfolio/efficient-frontier?points=5")
        assert resp.status_code == 422

    def test_rolling_sharpe_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/rolling-sharpe?window=252")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["window"] == 252
            assert data["period"] == "1Y"
            assert isinstance(data["series"], list)
            assert "date" in data["series"][0]
            assert "sharpe_ratio" in data["series"][0]

    def test_rolling_sharpe_window_param(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/rolling-sharpe?window=60")
            assert resp.status_code == 200
            assert mock_svc.compute_rolling_sharpe.call_args[1]["window"] == 60

    def test_rolling_sharpe_invalid_window(self, client):
        resp = client.get("/portfolio/rolling-sharpe?window=10")
        assert resp.status_code == 422

    def test_risk_contribution_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/risk-contribution")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert len(data["contributions"]) == 1
            contrib = data["contributions"][0]
            assert "symbol" in contrib
            assert "weight" in contrib
            assert "marginal_risk" in contrib
            assert "component_risk" in contrib
            assert "risk_pct" in contrib
            assert data["total_risk"] == 0.18

    def test_market_exposure_success(self, client):
        mock_svc = _make_mock_risk_service()
        with patch("api.portfolio._get_portfolio_risk_service") as mock_factory:
            mock_factory.return_value = mock_svc
            resp = client.get("/portfolio/market-exposure")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert "market" in data["exposures"]
            assert "alpha" in data["exposures"]
            assert "r_squared" in data

    def test_all_endpoints_require_auth(self):
        from fastapi import FastAPI

        from api.portfolio import router as portfolio_router
        app = FastAPI()
        app.include_router(portfolio_router)
        from starlette.testclient import TestClient
        with TestClient(app) as c:
            endpoints = [
                "/portfolio/risk-metrics",
                "/portfolio/drawdown",
                "/portfolio/covariance",
                "/portfolio/efficient-frontier",
                "/portfolio/rolling-sharpe",
                "/portfolio/risk-contribution",
                "/portfolio/market-exposure",
            ]
            for ep in endpoints:
                resp = c.get(ep)
                assert resp.status_code in (401, 403, 500), f"{ep} should reject unauthenticated requests, got {resp.status_code}"
