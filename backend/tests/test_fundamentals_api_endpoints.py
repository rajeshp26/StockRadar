"""
Integration tests for GET /analysis/{symbol}/fundamentals.
Verifies user_id is properly resolved from JWT dict → DB user_id.
"""
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
    """Return shape matching real JWT from Firebase/Supabase (a dict with 'sub')."""
    return {"sub": "firebase-uid-abc123", "email": "test@example.com"}


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


class TestFundamentalsAPIEndpoint:
    """Integration tests for the fundamentals API endpoint."""

    def test_fundamentals_passes_resolved_user_id(self, client):
        """
        With the fix, user['sub'] is extracted from the JWT dict and resolved
        to a DB user_id via _resolve_db_user_id. The service receives the
        resolved user_id as a string.
        """
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value={"success": True, "symbol": "AAPL",
                                                "sections": []})
        ))

        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42) as mock_resolve,
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        assert resp.status_code == 200
        mock_resolve.assert_called_once_with("firebase-uid-abc123")
        mock_svc.get_fundamentals.assert_called_once_with(
            "AAPL", user_id="42", frequency="quarterly"
        )

    def test_fundamentals_no_user_when_sub_missing(self, client):
        """If user dict has no 'sub', user_id should be None."""
        def _mock_user_no_sub():
            return {"email": "test@example.com"}

        test_app = client._transport.app
        from dependencies import get_current_user_dep
        test_app.dependency_overrides[get_current_user_dep] = _mock_user_no_sub

        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value={"success": True, "symbol": "AAPL",
                                                "has_portfolio_position": False,
                                                "sections": []})
        ))

        with patch("api.analysis._get_fundamentals_service", return_value=mock_svc):
            resp = client.get("/analysis/AAPL/fundamentals")

        assert resp.status_code == 200
        mock_svc.get_fundamentals.assert_called_once_with(
            "AAPL", user_id=None, frequency="quarterly"
        )

    def test_fundamentals_returns_200(self, client):
        """Endpoint returns 200 with valid data."""
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value={"success": True, "symbol": "AAPL",
                                                "has_portfolio_position": False,
                                                "sections": []})
        ))

        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"

    def test_fundamentals_passes_frequency_param(self, client):
        """The frequency query parameter must be forwarded."""
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value={"success": True, "symbol": "AAPL",
                                                "sections": []})
        ))

        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals", params={"frequency": "annual"})

        assert resp.status_code == 200
        mock_svc.get_fundamentals.assert_called_once_with(
            "AAPL", user_id="42", frequency="annual"
        )

    def test_fundamentals_422_on_invalid_symbol(self, client):
        """Invalid symbol format must return 422."""
        resp = client.get("/analysis/INVALID@@@/fundamentals")
        assert resp.status_code == 422

    def test_fundamentals_500_on_service_error(self, client):
        """Service exception must return 500."""
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(side_effect=Exception("DB error"))

        with patch("api.analysis._get_fundamentals_service", return_value=mock_svc):
            resp = client.get("/analysis/AAPL/fundamentals")

        assert resp.status_code == 500
        assert "Fundamentals analysis failed" in resp.json()["detail"]

    def test_fundamentals_403_when_user_not_in_db(self, client):
        """If _resolve_db_user_id raises 403, the endpoint must propagate it."""
        from fastapi import HTTPException
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value={"success": True, "symbol": "AAPL",
                                                "sections": []})
        ))

        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id",
                  side_effect=HTTPException(status_code=403, detail="User not found.")),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        assert resp.status_code == 403
