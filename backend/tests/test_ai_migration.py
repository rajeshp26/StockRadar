from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.prompts.company_snapshot import CompanySnapshotBuilder
from application.services.prompts.overview import build_overview_prompt
from application.services.prompts.suitability import (
    _critical_flags,
    _fmt,
    build_suitability_prompt,
)
from providers.ai_provider import AIProvider, OpenRouterProvider


class TestPromptBuilders:

    def test_rule1_prompt_contains_expected_sections(self):
        prompt = build_suitability_prompt(
            symbol="AAPL",
            method="rule1",
            score=75,
            category="Good",
            flags=[],
            evidence={
                "final_scoring": {"points": 6, "totalPossible": 10, "hardFail": False},
                "growth_eps_cagr": {"cagr": 0.12},
                "eps_quality_positive_net_income_years": {"positive": 5, "total": 5},
            },
            valuation_inputs={"currency": "USD", "eps0": 5.0, "growth": 0.10},
            input_decisions={},
        )
        assert "SCORECARD" in prompt
        assert "AAPL" in prompt
        assert "AVAILABLE METRIC EVIDENCE" in prompt
        assert prompt.count("===") >= 4

    def test_dcf_prompt_broken_formula(self):
        prompt = build_suitability_prompt(
            symbol="XYZ",
            method="dcf",
            score=29,
            category="Poor",
            flags=[{"code": "DCF-NO-FORECAST", "severity": "critical", "message": "No forecast"}],
            evidence={"final_scoring": {"passes": 0, "totalPossible": 7}},
            valuation_inputs={"currency": "USD", "baseFcf": -100},
            input_decisions={},
        )
        assert "cannot produce a valid intrinsic value" in prompt
        assert "FORMULA BREAKDOWN" in prompt

    def test_generic_fallback(self):
        prompt = build_suitability_prompt(
            symbol="TEST", method="unknown_method", score=50, category="Caution",
            flags=[{"code": "WARN", "severity": "medium", "message": "Test"}],
            evidence={}, valuation_inputs={}, input_decisions={},
        )
        assert "TEST" in prompt
        assert "unknown_method" in prompt
        assert "Caution" in prompt

    def test_magic_formula_excluded_sector(self):
        prompt = build_suitability_prompt(
            symbol="GS", method="magic_formula", score=0, category="Not Applicable",
            flags=[{"code": "MF-SECTOR-EXCLUDED", "severity": "high", "message": "Financials excluded"}],
            evidence={"sector": "Financial Services", "industry": "Banks"},
            valuation_inputs={}, input_decisions={},
        )
        assert "excluded" in prompt.lower()
        assert "Greenblatt" in prompt

    def test_canslim_prompt(self):
        prompt = build_suitability_prompt(
            symbol="NVDA", method="canslim", score=78, category="Strong",
            flags=[],
            evidence={
                "C": {"available": True, "score": 85, "signal": "Bullish", "headline": "Strong EPS growth"},
                "A": {"available": True, "score": 80, "signal": "Bullish", "headline": "Strong earnings"},
            },
            valuation_inputs={}, input_decisions={},
        )
        assert "CANSlim" in prompt
        assert "NVDA" in prompt
        assert "LETTER DETAIL" in prompt

    def test_overview_prompt_basic(self):
        prompt = build_overview_prompt(
            symbol="MSFT",
            sector="Technology",
            currency="USD",
            current_price=350.0,
            methods={
                "dcf": {"status": "computed", "intrinsicValue": 412.0, "score": 86, "category": "Good"},
                "rule1": {"status": "computed", "intrinsicValue": 390.0, "score": 72, "category": "Good"},
            },
        )
        assert "MSFT" in prompt
        assert "Technology" in prompt
        assert "Discounted Cash Flow" in prompt
        assert "Rule #1" in prompt
        assert "strong convergence" in prompt.lower()


class TestSnapshotBuilder:

    def test_format_context_empty(self):
        result = CompanySnapshotBuilder.format_context({"error": "No company"})
        assert result == ""

    def test_format_context_with_data(self):
        snapshot = {
            "symbol": "AAPL",
            "company_context": {
                "currency": "USD",
                "sector": "Technology",
                "industry": "Consumer Electronics",
            },
            "current_price": 175.50,
            "company_summary": {
                "shares_outstanding": 15000000000,
                "trailing_eps": 6.50,
            },
            "income_statement": {
                "fiscal_year": 2025,
                "revenue": 391000000000,
                "net_income_to_common": 97000000000,
                "eps_diluted": 6.50,
            },
            "balance_sheet": {
                "fiscal_year": 2025,
                "total_assets": 352000000000,
                "total_debt": 105000000000,
                "shareholders_equity": 62000000000,
                "cash_and_cash_equivalents": 55000000000,
            },
            "cash_flow": {
                "fiscal_year": 2025,
                "cash_from_operating_activities": 110000000000,
                "capital_expenditures": 11000000000,
            },
            "income_statements": [
                {"fiscal_year": 2025, "revenue": 391000000000, "net_income_to_common": 97000000000},
                {"fiscal_year": 2024, "revenue": 383000000000, "net_income_to_common": 94000000000},
            ],
        }
        for method in ["rule1", "dcf", "ddm_gordon", "owner_earnings", "residual_income"]:
            snapshot[f"cached_{method}"] = None

        result = CompanySnapshotBuilder.format_context(snapshot)
        assert "=== COMPANY CONTEXT ===" in result
        assert "AAPL" in result
        assert "Technology" in result
        assert "Current Market Price: 175.50" in result
        assert "Shares Outstanding: 15000000000" in result
        assert "Trailing EPS: 6.5" in result
        assert "Revenue=391000000000" in result
        assert "Debt=105000000000" in result
        assert "Cash=55000000000" in result
        assert "Ops Cash Flow=110000000000" in result
        assert "Capex=11000000000" in result


class TestFormatHelpers:

    def test_fmt_basic(self):
        assert _fmt(42.0) == "42.0"
        assert _fmt(0.055, as_pct=True) == "5.5%"
        assert _fmt(None) == "N/A"

    def test_critical_flags_filters(self):
        flags = [
            {"code": "HIGH-RISK", "severity": "critical", "message": "Critical"},
            {"code": "LOW-INFO", "severity": "low", "message": "Low"},
            {"code": "TEST-SCORECARD", "severity": "critical", "message": "Scorecard"},
        ]
        result = _critical_flags(flags)
        assert len(result) == 1
        assert result[0]["code"] == "HIGH-RISK"


class TestOpenRouterProvider:

    @pytest.fixture(autouse=True)
    def _reset_credits_breaker(self):
        OpenRouterProvider._credits_exhausted = False
        yield
        OpenRouterProvider._credits_exhausted = False

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_generate_text_success(self, mock_settings, mock_httpx):
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello world"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        result = await provider.generate_text("Test prompt", system_instruction="Be helpful")
        assert result == "Hello world"

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_generate_text_no_key(self, mock_settings, mock_httpx):
        mock_settings.OPEN_ROUTER_KEY = ""
        provider = OpenRouterProvider()
        result = await provider.generate_text("Test")
        assert result is None

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_generate_text_api_error(self, mock_settings, mock_httpx):
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_response = MagicMock()
        mock_response.is_success = False
        mock_response.status_code = 429
        mock_response.text = "Rate limited"

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        result = await provider.generate_text("Test")
        assert result is None

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_generate_json_success(self, mock_settings, mock_httpx):
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": '{"bestMethod": "dcf", "consensus": "Undervalued"}'},
                "finish_reason": "stop",
            }],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        result = await provider.generate_json("Test JSON prompt")
        assert result == {"bestMethod": "dcf", "consensus": "Undervalued"}

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_generate_json_markdown_fences(self, mock_settings, mock_httpx):
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_response = MagicMock()
        mock_response.is_success = True
        mock_response.json.return_value = {
            "choices": [{
                "message": {"content": "```json\n{\"key\": \"value\"}\n```"},
                "finish_reason": "stop",
            }],
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        result = await provider.generate_json("Test")
        assert result == {"key": "value"}

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_generate_text_skips_when_credits_exhausted(self, mock_settings, mock_httpx):
        OpenRouterProvider._credits_exhausted = True
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_client = AsyncMock()
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        result = await provider.generate_text("Test")
        assert result is None
        mock_client.post.assert_not_called()


class TestAIProviderABC:

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            AIProvider()


class TestAiServiceIntegration:

    @pytest.fixture(autouse=True)
    def setup_cleanup(self):
        # I1d: ai_service caches AI responses by input hash in a module-level
        # _cache_manager. In the full suite an earlier test configured it, so
        # two tests with identical inputs returned the first test's mocked
        # answer ("This is a suitability summary."). Disable that cache for
        # these provider-call unit tests; they assert on the generated result,
        # not on cache behaviour.
        from contextlib import suppress

        with patch("application.services.ai_service._cache_manager", None):
            from dependencies import get_cache_manager
            with suppress(Exception):
                get_cache_manager().clear_all()
            yield
            with suppress(Exception):
                get_cache_manager().clear_all()

    @patch("application.services.ai_service._get_or_create_provider")
    @patch("application.services.ai_service._build_company_context")
    async def test_generate_suitability_with_context(
        self, mock_build_context, mock_get_provider
    ):
        mock_build_context.return_value = "=== COMPANY CONTEXT ===\nSome context\n\n"

        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.return_value = "This is a suitability summary."
        mock_get_provider.return_value = mock_provider

        from application.services.ai_service import generate_suitability_summary

        result = await generate_suitability_summary(
            symbol="AAPL", method="rule1", score=75, category="Good",
            flags=[], evidence={}, valuation_inputs={}, input_decisions={},
        )
        assert result == "This is a suitability summary."
        call_args = mock_provider.generate_text.call_args[1]
        assert "=== COMPANY CONTEXT ===" not in call_args["prompt"]
        mock_build_context.assert_not_called()

    @patch("application.services.ai_service._get_or_create_provider")
    @patch("application.services.ai_service._build_company_context")
    async def test_generate_suitability_fallback_no_context(
        self, mock_build_context, mock_get_provider
    ):
        mock_build_context.return_value = ""

        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.return_value = "Fallback summary."
        mock_get_provider.return_value = mock_provider

        from application.services.ai_service import generate_suitability_summary

        result = await generate_suitability_summary(
            symbol="AAPL", method="rule1", score=75, category="Good",
            flags=[], evidence={}, valuation_inputs={}, input_decisions={},
        )
        assert result == "Fallback summary."
        call_args = mock_provider.generate_text.call_args[1]
        assert "=== COMPANY CONTEXT ===" not in call_args["prompt"]

    @patch("application.services.ai_service._get_or_create_provider")
    @patch("application.services.ai_service._build_company_context")
    async def test_generate_overview_with_context(
        self, mock_build_context, mock_get_provider
    ):
        mock_build_context.return_value = "=== COMPANY CONTEXT ===\nSome context\n\n"

        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.return_value = '{"bestMethod": "dcf", "bestMethodLabel": "DCF", "reasoning": "Test", "consensus": "Undervalued", "confidenceNote": "Note"}'
        mock_get_provider.return_value = mock_provider

        from application.services.ai_service import generate_overview_summary

        result = await generate_overview_summary(
            symbol="MSFT", sector="Technology", currency="USD",
            current_price=350.0,
            methods={"dcf": {"status": "computed", "intrinsicValue": 412.0, "score": 86, "category": "Good"}},
        )
        assert result is not None
        assert result["bestMethod"] == "dcf"
        assert result["consensus"] == "Undervalued"

    @patch("application.services.ai_service._get_or_create_provider")
    @patch("application.services.ai_service._build_company_context")
    async def test_generate_overview_fallback_missing_keys(
        self, mock_build_context, mock_get_provider
    ):
        mock_build_context.return_value = ""

        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.return_value = '{"bestMethod": "dcf"}'
        mock_get_provider.return_value = mock_provider

        from application.services.ai_service import generate_overview_summary

        result = await generate_overview_summary(
            symbol="MSFT", sector="Tech", currency="USD",
            current_price=350.0,
            methods={"dcf": {"status": "computed", "intrinsicValue": 412.0, "score": 86, "category": "Good"}},
        )
        assert result is not None
        assert result.get("bestMethod") == "dcf"
        assert "reasoning" in result
        assert "consensus" in result
