from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.ai_service import (
    configure_ai,
    generate_overview_summary,
    generate_suitability_summary,
)
from application.services.caching.cache_manager import CacheManager
from infrastructure.repositories.valuation_repository import ValuationRepository
from providers.ai_provider import AIProvider

# --- Unit Tests: CacheManager ---

class TestCacheManagerUnit:

    def test_cache_manager_init(self):
        """Verify caches exist, empty, with correct default TTLs."""
        cm = CacheManager(ai_ttl=300, query_ttl=30, context_ttl=60)
        assert cm._query_cache.ttl == 30
        assert cm._ai_cache.ttl == 300
        assert cm._context_cache.ttl == 60
        assert len(cm._query_cache) == 0
        assert len(cm._ai_cache) == 0
        assert len(cm._context_cache) == 0

    def test_query_cache_hit_and_miss(self):
        """Verify query cache set & get works for request and TTL cache."""
        cm = CacheManager()
        key = "query:test:arg"
        assert cm.get_query_result(key) is None

        cm.set_query_result(key, "canned_rows")
        assert cm.get_query_result(key) == "canned_rows"

    def test_query_cache_request_scope_clearing(self):
        """Verify request cache ContextVar is cleared independently of TTL cache."""
        cm = CacheManager()
        key = "query:test:arg"
        cm.set_query_result(key, "data")

        # In request scope
        assert key in cm._request_cache.get()

        cm.clear_request_cache()
        # request scope is empty, but TTL cache still has it
        assert key not in cm._request_cache.get()
        assert cm.get_query_result(key) == "data"  # Hits Layer B TTL cache!

    def test_ai_cache_hit_and_miss_with_hashing(self):
        """Verify AI cache set/get behavior with keys and hashes."""
        cm = CacheManager()
        symbol = "RBLX"
        method = "rule1"
        data = {"price": 35.0, "metrics": [1, 2, 3]}
        data_hash = cm.compute_hash(data)

        assert cm.get_ai_response(symbol, method, data_hash) is None

        cm.set_ai_response(symbol, method, data_hash, "AI Analysis Verdict")
        assert cm.get_ai_response(symbol, method, data_hash) == "AI Analysis Verdict"

        # Different hash -> Cache miss
        other_hash = cm.compute_hash({"price": 36.0, "metrics": [1, 2, 3]})
        assert cm.get_ai_response(symbol, method, other_hash) is None

    def test_hash_stability(self):
        """Verify JSON/hash generation is stable and deterministic."""
        cm = CacheManager()
        data1 = {"symbol": "AAPL", "evidence": {"growth": 0.12}, "flags": [{"code": "OK"}]}
        data2 = {"symbol": "AAPL", "evidence": {"growth": 0.12}, "flags": [{"code": "OK"}]}
        # Set with different order
        data3 = {"flags": [{"code": "OK"}], "symbol": "AAPL", "evidence": {"growth": 0.12}}

        h1 = cm.compute_hash(data1)
        h2 = cm.compute_hash(data2)
        h3 = cm.compute_hash(data3)

        assert h1 == h2
        assert h1 == h3


# --- Unit Tests: ai_service.py Cache Integration ---

class TestAiServiceCacheIntegration:

    @pytest.fixture(autouse=True)
    def setup_cleanup(self):
        # Reset AI configuration singletons before and after each test
        configure_ai(provider=None, snapshot_builder=None, cache_manager=None)
        yield
        configure_ai(provider=None, snapshot_builder=None, cache_manager=None)

    @pytest.mark.asyncio
    @patch("application.services.ai_service._get_or_create_provider")
    async def test_suitability_cache_hit_returns_cached(self, mock_get_provider):
        """Verify Cache HIT on suitability skips provider call entirely."""
        cm = CacheManager()
        mock_provider = AsyncMock(spec=AIProvider)
        mock_get_provider.return_value = mock_provider

        configure_ai(provider=mock_provider, cache_manager=cm)

        symbol = "AAPL"
        method = "rule1"
        inputs = {
            "symbol": symbol,
            "method": method,
            "score": 85,
            "category": "Good",
            "flags": [],
            "evidence": {},
            "valuation_inputs": {},
            "input_decisions": {},
        }
        h = cm.compute_hash(inputs)
        cm.set_ai_response(symbol, method, h, "Cached Text Verdict")

        result = await generate_suitability_summary(
            symbol=symbol, method=method, score=85, category="Good", flags=[],
            evidence={}, valuation_inputs={}, input_decisions={},
        )

        assert result == "Cached Text Verdict"
        mock_provider.generate_text.assert_not_called()

    @pytest.mark.asyncio
    @patch("application.services.ai_service._get_or_create_provider")
    async def test_suitability_cache_miss_calls_provider(self, mock_get_provider):
        """Verify Cache MISS on suitability calls provider and stores result."""
        cm = CacheManager()
        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.return_value = "Fresh AI Output Text"
        mock_get_provider.return_value = mock_provider

        configure_ai(provider=mock_provider, cache_manager=cm)

        symbol = "AAPL"
        method = "rule1"

        result = await generate_suitability_summary(
            symbol=symbol, method=method, score=85, category="Good", flags=[],
            evidence={"a": 1}, valuation_inputs={}, input_decisions={},
        )

        assert result == "Fresh AI Output Text"
        assert mock_provider.generate_text.call_count == 1

        # Check that it's now in the cache
        inputs = {
            "symbol": symbol,
            "method": method,
            "score": 85,
            "category": "Good",
            "flags": [],
            "evidence": {"a": 1},
            "valuation_inputs": {},
            "input_decisions": {},
        }
        h = cm.compute_hash(inputs)
        assert cm.get_ai_response(symbol, method, h) == "Fresh AI Output Text"

    @pytest.mark.asyncio
    @patch("application.services.ai_service._get_or_create_provider")
    async def test_suitability_no_company_context_built(self, mock_get_provider):
        """Verify suitability summary skips company context queries completely."""
        cm = CacheManager()
        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.return_value = "Factual suitability check"
        mock_get_provider.return_value = mock_provider

        # Setup snapshot builder spy
        mock_builder = MagicMock()
        configure_ai(provider=mock_provider, snapshot_builder=mock_builder, cache_manager=cm)

        await generate_suitability_summary(
            symbol="MSFT", method="dcf", score=60, category="Caution", flags=[],
            evidence={}, valuation_inputs={}, input_decisions={},
        )

        mock_builder.build.assert_not_called()

    @pytest.mark.asyncio
    @patch("application.services.ai_service._get_or_create_provider")
    @patch("application.services.ai_service._build_company_context")
    async def test_overview_cache_hit_returns_cached_dict(self, mock_build_context, mock_get_provider):
        """Verify Cache HIT on overview summary returns dictionary instantly."""
        cm = CacheManager()
        mock_provider = AsyncMock(spec=AIProvider)
        mock_get_provider.return_value = mock_provider
        mock_build_context.return_value = "AAPL Context Content"

        configure_ai(provider=mock_provider, cache_manager=cm)

        symbol = "AAPL"
        methods_data = {"rule1": {"status": "computed", "score": 80}}
        inputs = {
            "symbol": symbol,
            "sector": "Tech",
            "currency": "USD",
            "current_price": 170.0,
            "methods": methods_data,
            "context": "AAPL Context Content",
        }
        h = cm.compute_hash(inputs)
        cached_dict = {"bestMethod": "rule1", "bestMethodLabel": "Rule 1", "reasoning": "Decisive reasoning", "consensus": "Undervalued", "confidenceNote": "Note"}
        cm.set_ai_response(symbol, "overview", h, cached_dict)

        result = await generate_overview_summary(
            symbol=symbol, sector="Tech", currency="USD", current_price=170.0, methods=methods_data
        )

        assert result == cached_dict
        mock_provider.generate_text.assert_not_called()


# --- Unit Tests: ValuationRepository Batch Query ---

class TestValuationRepositoryBatchQuery:

    @pytest.mark.asyncio
    @patch("infrastructure.repositories.valuation_repository.supabase")
    async def test_get_last_output_snapshots_returns_correct_mapping(self, mock_supabase):
        """Verify get_last_output_snapshots batch queries Supabase correctly using `.in_()`."""
        mock_execute = MagicMock()
        mock_execute.execute.return_value = MagicMock(data=[
            {"method": "rule1", "output_snapshot": {"val": 10}, "run_at": "2026-05-24T18:00:00"},
            {"method": "dcf", "output_snapshot": {"val": 20}, "run_at": "2026-05-24T19:00:00"},
            # Duplicate for rule1 (older)
            {"method": "rule1", "output_snapshot": {"val": 5}, "run_at": "2026-05-24T17:00:00"},
        ])

        mock_supabase.table.return_value.select.return_value.eq.return_value.in_.return_value.order.return_value = mock_execute

        repo = ValuationRepository()
        snapshots = await repo.get_last_output_snapshots(company_id=42, methods=["rule1", "dcf", "ddm_gordon"])

        assert len(snapshots) == 3
        # Must return the most recent output_snapshot (val: 10, not 5)
        assert snapshots["rule1"] == {"val": 10}
        assert snapshots["dcf"] == {"val": 20}
        # Not found method -> None
        assert snapshots["ddm_gordon"] is None


# --- Integration Tests: Request Flow & Tab Switching ---

class TestCachingIntegrationFlows:

    @pytest.mark.asyncio
    async def test_sequential_tab_switching_scenario(self):
        """Simulate realistic tab switching sequence: rule1 -> dcf -> rule1.
           Verifies the third call is a 0ms Cache HIT (0 provider calls)."""
        cm = CacheManager()
        mock_provider = AsyncMock(spec=AIProvider)
        mock_provider.generate_text.side_effect = ["Rule1 AI response text", "DCF AI response text"]

        with patch("application.services.ai_service._get_or_create_provider", return_value=mock_provider):
            configure_ai(provider=mock_provider, cache_manager=cm)

            # Step 1: Visit Rule 1
            res1 = await generate_suitability_summary(
                symbol="TSLA", method="rule1", score=70, category="Caution", flags=[],
                evidence={"data": 1}, valuation_inputs={}, input_decisions={},
            )
            assert res1 == "Rule1 AI response text"
            assert mock_provider.generate_text.call_count == 1

            # Step 2: Switch to DCF
            res2 = await generate_suitability_summary(
                symbol="TSLA", method="dcf", score=40, category="Poor", flags=[],
                evidence={"data": 2}, valuation_inputs={}, input_decisions={},
            )
            assert res2 == "DCF AI response text"
            assert mock_provider.generate_text.call_count == 2

            # Step 3: Switch BACK to Rule 1 (same input data!)
            res3 = await generate_suitability_summary(
                symbol="TSLA", method="rule1", score=70, category="Caution", flags=[],
                evidence={"data": 1}, valuation_inputs={}, input_decisions={},
            )
            # Must return cached result INSTANTLY without invoking OpenRouter!
            assert res3 == "Rule1 AI response text"
            assert mock_provider.generate_text.call_count == 2  # Call count remains 2!
