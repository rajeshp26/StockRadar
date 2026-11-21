"""I27 -- full AI prompt bodies must not be dumped at INFO on every call.

Two sites in ``application/services/ai_service.py`` logged the entire prompt
(context + task instructions) at INFO, once per suitability/overview call.
That is high-volume and puts financial context into shared worker logs.

Contract: INFO records only compact metadata (symbol/method, char count and a
short sha256 handle for correlation); the full body is emitted only at DEBUG,
i.e. when an operator deliberately enables debug logging. RED today.
"""
from __future__ import annotations

import json
import logging
from unittest.mock import AsyncMock, patch

import pytest

from application.services import ai_service
from application.services.ai_service import (
    generate_overview_summary,
    generate_suitability_summary,
)

LOGGER = "application.services.ai_service"
SUIT_BODY = "SUITABILITY_SECRET_PROMPT_BODY_XYZ"
TASK_BODY = "OVERVIEW_TASK_SECRET_PROMPT_BODY_XYZ"
CONTEXT_BODY = "OVERVIEW_COMPANY_CONTEXT_SECRET_XYZ"

OVERVIEW_JSON = json.dumps({
    "bestMethod": "rule1",
    "bestMethodLabel": "Rule #1",
    "reasoning": "ok",
    "consensus": "ok",
    "confidenceNote": "ok",
})


@pytest.fixture(autouse=True)
def _isolated_ai(monkeypatch):
    provider = AsyncMock()
    provider.generate_text.return_value = OVERVIEW_JSON
    monkeypatch.setattr(ai_service, "_get_or_create_provider", lambda: provider)
    monkeypatch.setattr(ai_service, "_cache_manager", None)
    return provider


async def test_suitability_prompt_body_not_logged_at_info(caplog):
    with (
        patch(
            "application.services.ai_service.build_suitability_prompt",
            return_value=SUIT_BODY,
        ),
        caplog.at_level(logging.INFO, logger=LOGGER),
    ):
        await generate_suitability_summary("AAPL", "rule1", 85, "Good", [])

    assert SUIT_BODY not in caplog.text
    assert "PROMPT START" not in caplog.text
    assert "Sending prompt for AAPL/rule1" in caplog.text
    assert "sha256=" in caplog.text
    assert f"({len(SUIT_BODY)} chars" in caplog.text


async def test_suitability_prompt_body_available_at_debug(caplog):
    with (
        patch(
            "application.services.ai_service.build_suitability_prompt",
            return_value=SUIT_BODY,
        ),
        caplog.at_level(logging.DEBUG, logger=LOGGER),
    ):
        await generate_suitability_summary("AAPL", "rule1", 85, "Good", [])

    assert SUIT_BODY in caplog.text


async def test_overview_context_and_task_bodies_not_logged_at_info(caplog):
    with (
        patch("application.services.ai_service.build_overview_prompt", return_value=TASK_BODY),
        patch(
            "application.services.ai_service._build_company_context",
            return_value=CONTEXT_BODY,
        ),
        caplog.at_level(logging.INFO, logger=LOGGER),
    ):
        await generate_overview_summary(
            "AAPL", "Tech", "USD", 100.0, {"rule1": {"score": 85}}
        )

    assert TASK_BODY not in caplog.text
    assert CONTEXT_BODY not in caplog.text
    assert "PROMPT START" not in caplog.text
    assert "Sending overview prompt for AAPL" in caplog.text
    assert "sha256=" in caplog.text


async def test_overview_bodies_available_at_debug(caplog):
    with (
        patch("application.services.ai_service.build_overview_prompt", return_value=TASK_BODY),
        patch(
            "application.services.ai_service._build_company_context",
            return_value=CONTEXT_BODY,
        ),
        caplog.at_level(logging.DEBUG, logger=LOGGER),
    ):
        await generate_overview_summary(
            "AAPL", "Tech", "USD", 100.0, {"rule1": {"score": 85}}
        )

    assert TASK_BODY in caplog.text
    assert CONTEXT_BODY in caplog.text
