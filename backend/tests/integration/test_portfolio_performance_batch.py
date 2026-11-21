"""
Integration tests for POST /portfolio/performance/batch endpoint.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# I1d: removed module-level sys.modules["database"] = MagicMock(). It leaked
# into every later-collected test (notably test_database.py) at collection
# time even when this integration module was deselected. Real imports work.
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


def _make_perf_result(success: bool = True, period: str = "1Y", snapshots=None):
    if snapshots is None:
        snapshots = []
    return {
        "success": success,
        "period": period,
        "snapshots": snapshots,
        "total_return": 1500.0 if success else 0,
        "total_return_pct": 15.0 if success else 0,
        "data_source": "snapshots" if success else "",
        "data_quality_flag": "OK" if success else "",
        "return_methodology": "simple" if success else "",
    }


class TestPerformanceBatchEndpoint:

    def test_batch_single_period_success(self, client):
        mock_svc = MagicMock()
        mock_svc.get_portfolio_performance = AsyncMock(
            return_value=_make_perf_result(success=True, period="1Y")
        )
        with patch.object(_portfolio_mod, "_get_portfolio_service", return_value=mock_svc):
            resp = client.post("/portfolio/performance/batch", json={
                "account_ids": [1, 2],
                "periods": ["1Y"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "1Y" in data["results"]
        assert data["results"]["1Y"]["total_return"] == 1500.0
        assert data["results"]["1Y"]["total_return_pct"] == 15.0
        mock_svc.get_portfolio_performance.assert_called_once_with(42, "1Y", [1, 2])

    def test_batch_multiple_periods(self, client):
        mock_svc = MagicMock()
        def perf_side_effect(user_id, period, account_ids=None):
            return _make_perf_result(success=True, period=period)
        mock_svc.get_portfolio_performance = AsyncMock(side_effect=perf_side_effect)

        with patch.object(_portfolio_mod, "_get_portfolio_service", return_value=mock_svc):
            resp = client.post("/portfolio/performance/batch", json={
                "periods": ["1M", "3M", "1Y", "5Y", "ALL"],
            })

        assert resp.status_code == 200
        data = resp.json()
        for p in ["1M", "3M", "1Y", "5Y", "ALL"]:
            assert p in data["results"]
            assert data["results"][p]["period"] == p

    def test_batch_partial_failure(self, client):
        mock_svc = MagicMock()
        def perf_side_effect(user_id, period, account_ids=None):
            if period == "1Y":
                return _make_perf_result(success=True, period="1Y")
            return {"success": False, "period": period}
        mock_svc.get_portfolio_performance = AsyncMock(side_effect=perf_side_effect)

        with patch.object(_portfolio_mod, "_get_portfolio_service", return_value=mock_svc):
            resp = client.post("/portfolio/performance/batch", json={
                "periods": ["1M", "1Y"],
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["results"]["1Y"] is not None
        assert data["results"]["1M"] is None

    def test_batch_default_period_is_1Y(self, client):
        mock_svc = MagicMock()
        mock_svc.get_portfolio_performance = AsyncMock(
            return_value=_make_perf_result(success=True, period="1Y")
        )
        with patch.object(_portfolio_mod, "_get_portfolio_service", return_value=mock_svc):
            resp = client.post("/portfolio/performance/batch", json={})

        assert resp.status_code == 200
        data = resp.json()
        assert "1Y" in data["results"]
        mock_svc.get_portfolio_performance.assert_called_once_with(42, "1Y", None)

    def test_batch_account_ids_not_list_returns_422(self, client):
        resp = client.post("/portfolio/performance/batch", json={
            "account_ids": "not-a-list",
        })
        assert resp.status_code == 422
        assert "account_ids must be a list of integers" in resp.json()["detail"]

    def test_batch_service_error_returns_500(self, client):
        mock_svc = MagicMock()
        mock_svc.get_portfolio_performance = AsyncMock(side_effect=ValueError("DB error"))
        with patch.object(_portfolio_mod, "_get_portfolio_service", return_value=mock_svc):
            resp = client.post("/portfolio/performance/batch", json={
                "periods": ["1Y"],
            })

        assert resp.status_code == 500
        assert "Failed to fetch batch performance" in resp.json()["detail"]

    def test_batch_requires_auth(self):
        from fastapi import FastAPI

        from api.portfolio import router as portfolio_router
        app = FastAPI()
        app.include_router(portfolio_router)
        from starlette.testclient import TestClient
        with TestClient(app) as c:
            resp = c.post("/portfolio/performance/batch", json={"periods": ["1Y"]})
        assert resp.status_code in (401, 403, 500)
