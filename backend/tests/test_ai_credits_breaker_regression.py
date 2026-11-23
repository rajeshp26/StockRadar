"""REG-006-AI: the OpenRouter credits breaker must reset after its cooldown.

Observed symptom: `[AI] OpenRouter credits exhausted — skipping text generation`
appeared forever after a single 402, because `_credits_exhausted` was a process
global that was set True and never cleared. A top-up could never be picked up.
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from providers.ai_provider import OpenRouterProvider


def _success_response(text: str = "Hello world"):
    resp = MagicMock()
    resp.is_success = True
    resp.json.return_value = {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}]
    }
    return resp


def _credits_response():
    resp = MagicMock()
    resp.is_success = False
    resp.status_code = 402
    resp.text = "Insufficient credits"
    return resp


def _client(resp):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = resp
    return client


@pytest.fixture(autouse=True)
def _clean_breaker():
    OpenRouterProvider._credits_exhausted = False
    OpenRouterProvider._credits_exhausted_at = None
    yield
    OpenRouterProvider._credits_exhausted = False
    OpenRouterProvider._credits_exhausted_at = None


@pytest.mark.asyncio
async def test_402_opens_breaker_and_blocks_within_cooldown():
    with patch("providers.ai_provider.settings") as s, patch(
        "providers.ai_provider.httpx.AsyncClient"
    ) as client_cls:
        s.OPEN_ROUTER_KEY = "k"
        s.OPEN_ROUTER_MODEL = "m"
        client_cls.return_value = _client(_credits_response())
        provider = OpenRouterProvider()
        assert await provider.generate_text("x") is None
        assert OpenRouterProvider._credits_breaker_open() is True

        # A top-up happened, but we are still inside the cooldown: no probe yet.
        client_cls.return_value = _client(_success_response())
        assert await provider.generate_text("x") is None


@pytest.mark.asyncio
async def test_breaker_resets_after_cooldown_and_retries():
    with patch("providers.ai_provider.settings") as s, patch(
        "providers.ai_provider.httpx.AsyncClient"
    ) as client_cls:
        s.OPEN_ROUTER_KEY = "k"
        s.OPEN_ROUTER_MODEL = "m"
        client_cls.return_value = _client(_credits_response())
        provider = OpenRouterProvider()
        await provider.generate_text("x")  # open the breaker

        # Fast-forward past the retry window.
        OpenRouterProvider._credits_exhausted_at = (
            time.monotonic() - OpenRouterProvider._CREDITS_COOLDOWN_SECONDS - 1
        )
        recovered = _client(_success_response("Recovered"))
        client_cls.return_value = recovered
        assert await provider.generate_text("x") == "Recovered"
        recovered.post.assert_awaited_once()
