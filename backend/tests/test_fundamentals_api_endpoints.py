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


class TestFundamentalsAPIContract:
    """Verifies the API response body matches the designed contract."""

    def _mock_valuation_section(self):
        """Build a realistic valuation section with all required fields."""
        return {
            "section_id": "valuation",
            "title": "Valuation",
            "status": {"label": "Watch"},
            "score": 55.0,
            "metrics": [
                {
                    "metric_id": "pe_ratio", "label": "P/E", "unit": "x",
                    "buy_quarter_index": None,
                    "trend_direction": "down",
                    "change_pct": -0.4,
                    "change_label": "-40.0%",
                    "quarters": [
                        {"fiscal_year": 2024, "fiscal_quarter": 1,
                         "label": "Q1 2024", "value": 20.0, "status": "normal",
                         "ttm_eps": 1.50, "quarter_end_price": 100.0,
                         "components": [
                             {"label": "Q1 2024", "value": 0.50},
                             {"label": "Q4 2023", "value": 0.40},
                             {"label": "Q3 2023", "value": 0.30},
                             {"label": "Q2 2023", "value": 0.30},
                         ]},
                        {"fiscal_year": 2024, "fiscal_quarter": 4,
                         "label": "Q4 2024", "value": 12.0, "status": "normal",
                         "ttm_eps": 1.80, "quarter_end_price": 105.0,
                         "components": [
                             {"label": "Q4 2024", "value": 0.60},
                             {"label": "Q3 2024", "value": 0.50},
                             {"label": "Q2 2024", "value": 0.40},
                             {"label": "Q1 2024", "value": 0.30},
                         ]},
                    ],
                },
                {
                    "metric_id": "ev_ebitda", "label": "EV/EBITDA", "unit": "x",
                    "buy_quarter_index": None,
                    "trend_direction": "up",
                    "change_pct": 0.1875,
                    "change_label": "+18.8%",
                    "quarters": [
                        {"fiscal_year": 2024, "fiscal_quarter": 1,
                         "label": "Q1 2024", "value": 8.0, "status": "normal"},
                        {"fiscal_year": 2024, "fiscal_quarter": 4,
                         "label": "Q4 2024", "value": 9.5, "status": "normal"},
                    ],
                },
                {
                    "metric_id": "price_to_fcf", "label": "P/FCF", "unit": "x",
                    "buy_quarter_index": None,
                    "trend_direction": "stable",
                    "change_pct": None, "change_label": "stable",
                    "quarters": [
                        {"fiscal_year": 2024, "fiscal_quarter": 1,
                         "label": "Q1 2024", "value": 15.0, "status": "normal"},
                    ],
                },
                {
                    "metric_id": "price_vs_intrinsic", "label": "Price vs intrinsic", "unit": "%",
                    "buy_quarter_index": None,
                    "trend_direction": "stable", "change_pct": None,
                    "change_label": "current snapshot",
                    "quarters": [
                        {"fiscal_year": 0, "fiscal_quarter": 0,
                         "label": "Current", "value": -10.5, "status": "normal"},
                    ],
                },
            ],
        }

    def _build_full_response(self):
        return {
            "success": True,
            "symbol": "AAPL",
            "company_name": "Apple Inc.",
            "has_portfolio_position": True,
            "purchase_date": "2020-06-15",
            "purchase_period": "2020-06",
            "quarters": ["Q1 2024", "Q2 2024", "Q3 2024", "Q4 2024"],
            "buy_quarter_index": 1,
            "composite_score": 62,
            "sections": [
                {"section_id": "quality", "title": "Quality metrics",
                 "status": {"label": "Intact"}, "score": 80.0, "metrics": []},
                {"section_id": "growth", "title": "Growth metrics",
                 "status": {"label": "Watch"}, "score": 55.0, "metrics": []},
                {"section_id": "financial_health", "title": "Financial Health",
                 "status": {"label": "Intact"}, "score": 75.0, "metrics": []},
                self._mock_valuation_section(),
                {"section_id": "narrative", "title": "Narrative",
                 "status": {"label": "Intact"}, "score": 72.0, "metrics": []},
            ],
            "data_quality": {
                "sources": ["financial_ratios", "income_statements"],
                "staleness_days": None,
                "earliest_data_year": 2018,
                "quarterly_data_count": 4,
            },
            "error": None,
        }

    def test_response_contains_all_sections(self, client):
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=self._build_full_response())
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        section_ids = {s["section_id"] for s in data["sections"]}
        assert section_ids == {"quality", "growth", "financial_health", "valuation", "narrative"}

    def test_pe_metric_has_trend_direction(self, client):
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=self._build_full_response())
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        val = next(s for s in data["sections"] if s["section_id"] == "valuation")
        pe = next(m for m in val["metrics"] if m["metric_id"] == "pe_ratio")
        assert pe["trend_direction"] in ("up", "down", "stable")
        assert pe["trend_direction"] == "down"
        assert pe["change_label"] != "per quarter"
        assert pe["change_label"] == "-40.0%"

    def test_ev_ebitda_has_trend_direction(self, client):
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=self._build_full_response())
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        val = next(s for s in data["sections"] if s["section_id"] == "valuation")
        ev = next(m for m in val["metrics"] if m["metric_id"] == "ev_ebitda")
        assert ev["trend_direction"] in ("up", "down", "stable")
        assert ev["change_label"] != "per quarter"

    def test_pe_quarter_has_all_fields(self, client):
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=self._build_full_response())
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        val = next(s for s in data["sections"] if s["section_id"] == "valuation")
        pe = next(m for m in val["metrics"] if m["metric_id"] == "pe_ratio")
        q = pe["quarters"][0]

        assert "value" in q
        assert "status" in q
        assert q["status"] in ("normal", "not_applicable", "insufficient_data")
        assert "ttm_eps" in q
        assert "quarter_end_price" in q
        assert "components" in q
        assert len(q["components"]) == 4
        assert all("label" in c and "value" in c for c in q["components"])

    def test_buy_quarter_index_none_when_no_position(self, client):
        resp_data = self._build_full_response()
        resp_data["has_portfolio_position"] = False
        resp_data["purchase_date"] = None
        resp_data["purchase_period"] = None
        resp_data["buy_quarter_index"] = None

        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=resp_data)
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        assert data["buy_quarter_index"] is None
        assert data["has_portfolio_position"] is False

    def test_composite_score_present(self, client):
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=self._build_full_response())
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        assert data["composite_score"] is not None
        assert isinstance(data["composite_score"], (int, float))

    def test_valuation_section_has_4_metrics(self, client):
        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=self._build_full_response())
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        val = next(s for s in data["sections"] if s["section_id"] == "valuation")
        metric_ids = {m["metric_id"] for m in val["metrics"]}
        assert metric_ids == {"pe_ratio", "ev_ebitda", "price_to_fcf", "price_vs_intrinsic"}

    def test_insufficient_data_quarter_has_components(self, client):
        resp_data = self._build_full_response()
        val_section = next(s for s in resp_data["sections"] if s["section_id"] == "valuation")
        pe = next(m for m in val_section["metrics"] if m["metric_id"] == "pe_ratio")
        pe["quarters"] = [
            {"fiscal_year": 2022, "fiscal_quarter": 2, "label": "Q2 2022",
             "value": None, "status": "insufficient_data",
             "ttm_eps": None, "quarter_end_price": None,
             "components": [
                 {"label": "Q2 2022", "value": 0.16, "highlight": None},
                 {"label": "Q1 2022", "value": None, "highlight": None},
                 {"label": "Q4 2021", "value": None, "highlight": None},
                 {"label": "Q3 2021", "value": None, "highlight": None},
             ]},
        ]

        mock_svc = MagicMock()
        mock_svc.get_fundamentals = AsyncMock(return_value=MagicMock(
            model_dump=MagicMock(return_value=resp_data)
        ))
        with (
            patch("api.analysis._get_fundamentals_service", return_value=mock_svc),
            patch("api.analysis._resolve_db_user_id", return_value=42),
        ):
            resp = client.get("/analysis/AAPL/fundamentals")

        data = resp.json()
        val = next(s for s in data["sections"] if s["section_id"] == "valuation")
        pe = next(m for m in val["metrics"] if m["metric_id"] == "pe_ratio")
        q = pe["quarters"][0]
        assert q["status"] == "insufficient_data"
        assert q["value"] is None
        assert len(q["components"]) == 4
        null_components = [c for c in q["components"] if c["value"] is None]
        assert len(null_components) == 3
        assert null_components[0]["label"] == "Q1 2022"
