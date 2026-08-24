import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# Mock defeatbeta_api before any api.analysis imports trigger it
_fake_defeat = MagicMock()
_fake_ticker = MagicMock()
sys.modules["defeatbeta_api"] = _fake_defeat
sys.modules["defeatbeta_api.data"] = _fake_defeat
sys.modules["defeatbeta_api.data.ticker"] = _fake_ticker


class TestMoatAPI:
    @pytest.mark.asyncio
    async def test_normalize_valid(self):
        from api.analysis import _normalize
        assert _normalize("aapl") == "AAPL"
        assert _normalize("BRK.B") == "BRK.B"
        assert _normalize("  msft  ") == "MSFT"

    @pytest.mark.asyncio
    async def test_normalize_invalid(self):
        from api.analysis import _normalize
        with pytest.raises(HTTPException) as exc:
            _normalize("INVALID@@@")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_normalize_empty(self):
        from api.analysis import _normalize
        with pytest.raises(HTTPException) as exc:
            _normalize("")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_get_moat_service_creates(self):
        from api.analysis import _get_moat_service
        service = _get_moat_service()
        assert service is not None

    @pytest.mark.asyncio
    async def test_moat_analysis_endpoint_pattern(self):
        from domain.models.analysis_moat import (
            MoatApplicability,
            MoatDataQuality,
            MoatIndustryContext,
            MoatInputs,
            MoatResponse,
            MoatValuation,
        )
        response = MoatResponse(
            symbol="AAPL",
            company_id=1,
            currency="USD",
            inputs=MoatInputs(fiscal_years_used=5),
            valuation=MoatValuation(moat_score=85.0, moat_category="Wide"),
            industry_context=MoatIndustryContext(),
            applicability=MoatApplicability(score=85, category="Applicable"),
            data_quality=MoatDataQuality(last_computed_at="2025-01-01T00:00:00Z"),
        )
        d = response.dict()
        assert d["symbol"] == "AAPL"
        assert d["valuation"]["moat_score"] == 85.0
        assert d["valuation"]["moat_category"] == "Wide"

    @pytest.mark.asyncio
    async def test_moat_evidence_response_pattern(self):
        from domain.models.analysis_moat import MoatEvidenceResponse, MoatKeywordEvidence
        response = MoatEvidenceResponse(
            symbol="AAPL",
            company_id=1,
            text_analysis_available=True,
            total_keyword_matches=5,
            evidence_by_group={
                "intangible_assets": [
                    MoatKeywordEvidence(keyword="patent", keyword_group="intangible_assets", section="item_1_business")
                ]
            },
            groups_found=["intangible_assets"],
        )
        d = response.dict()
        assert d["text_analysis_available"] is True
        assert d["total_keyword_matches"] == 5
        assert "intangible_assets" in d["evidence_by_group"]

    @pytest.mark.asyncio
    async def test_moat_ai_response_pattern(self):
        from domain.models.analysis_moat import MoatAiNarrative, MoatAiResponse
        response = MoatAiResponse(
            symbol="AAPL",
            company_id=1,
            narrative=MoatAiNarrative(narrative="Strong moat", model="openrouter/default", generated_at="2025-01-01T00:00:00Z"),
            available=True,
        )
        d = response.dict()
        assert d["available"] is True
        assert "Strong moat" in d["narrative"]["narrative"]

    @pytest.mark.asyncio
    async def test_moat_valuation_round_trip(self):
        from domain.models.analysis_moat import MoatValuation
        v = MoatValuation(
            roic=0.32,
            wacc=0.10,
            roic_minus_wacc=22.0,
            gross_margin_pct=43.0,
            operating_margin_pct=30.0,
            net_margin_pct=25.0,
            roic_5y_avg=0.30,
            roic_5y_std=0.02,
            roic_stability_score=90.0,
            asset_turnover=0.88,
            capital_efficiency_score=85.0,
            moat_score=85.0,
            moat_category="Wide",
        )
        d = v.dict()
        assert d["roic"] == 0.32
        assert d["moat_category"] == "Wide"

    @pytest.mark.asyncio
    async def test_moat_response_serialization(self):
        import json

        from domain.models.analysis_moat import (
            MoatApplicability,
            MoatDataQuality,
            MoatIndustryContext,
            MoatInputs,
            MoatResponse,
            MoatValuation,
        )
        response = MoatResponse(
            symbol="AAPL",
            company_id=1,
            currency="USD",
            inputs=MoatInputs(fiscal_years_used=5),
            valuation=MoatValuation(moat_score=85.0, moat_category="Wide"),
            industry_context=MoatIndustryContext(),
            applicability=MoatApplicability(score=85, category="Applicable"),
            data_quality=MoatDataQuality(last_computed_at="2025-01-01T00:00:00Z"),
        )
        json_str = response.json()
        parsed = json.loads(json_str)
        assert parsed["symbol"] == "AAPL"
        assert parsed["valuation"]["moat_score"] == 85.0
