from __future__ import annotations

import json as _json
import logging
from typing import Any

from application.services.caching.cache_manager import CacheManager
from application.services.prompts.company_snapshot import CompanySnapshotBuilder
from application.services.prompts.overview import (
    _METHOD_LABELS,
    OVERVIEW_FALLBACK,
    build_overview_prompt,
)
from application.services.prompts.suitability import build_suitability_prompt
from config import settings
from providers.ai_provider import AIProvider, OpenRouterProvider

logger = logging.getLogger(__name__)

_provider: AIProvider | None = None
_snapshot_builder: CompanySnapshotBuilder | None = None
_cache_manager: CacheManager | None = None

_SUITABILITY_SYSTEM_INSTRUCTION = (
    "You are a financial analysis assistant writing plain-English summaries "
    "for retail investors. You always complete every sentence fully. "
    "You never use bullet points, headers, or labels. "
    "You only reference metric values that are explicitly provided — never invent numbers."
)

_OVERVIEW_SYSTEM_INSTRUCTION = (
    "You are a financial analysis assistant writing cross-method valuation recommendations "
    "for retail investors. You always respond with valid JSON only — no markdown, no preamble. "
    "You only reference metric values that are explicitly provided — never invent numbers. "
    "You complete every sentence in the reasoning field."
)


def configure_ai(
    provider: AIProvider | None = None,
    snapshot_builder: CompanySnapshotBuilder | None = None,
    cache_manager: CacheManager | None = None,
) -> None:
    global _provider, _snapshot_builder, _cache_manager
    if provider is not None:
        _provider = provider
    if snapshot_builder is not None:
        _snapshot_builder = snapshot_builder
    if cache_manager is not None:
        _cache_manager = cache_manager


def _get_or_create_provider() -> AIProvider | None:
    global _provider
    if _provider is None:
        key = settings.OPEN_ROUTER_KEY or ""
        if not key:
            logger.info("[AI] OPEN_ROUTER_KEY not set — AI disabled")
            return None
        _provider = OpenRouterProvider()
    return _provider


async def _build_company_context(symbol: str) -> str:
    builder = _snapshot_builder
    if builder is None:
        return ""
    try:
        snapshot = await builder.build(symbol)
        return CompanySnapshotBuilder.format_context(snapshot)
    except Exception as exc:
        logger.warning("[AI] Company context build failed for %s: %s", symbol, exc)
        return ""


async def generate_suitability_summary(
    symbol:           str,
    method:           str,
    score:            int,
    category:         str,
    flags:            list[dict],
    evidence:         dict[str, Any] | None = None,
    valuation_inputs: dict[str, Any] | None = None,
    input_decisions:  dict[str, Any] | None = None,
    timeout:          float = 8.0,
) -> str | None:
    provider = _get_or_create_provider()
    if provider is None:
        return None

    inputs_to_hash = {
        "symbol": symbol,
        "method": method,
        "score": score,
        "category": category,
        "flags": flags,
        "evidence": evidence or {},
        "valuation_inputs": valuation_inputs or {},
        "input_decisions": input_decisions or {},
    }

    context_hash = ""
    if _cache_manager is not None:
        context_hash = _cache_manager.compute_hash(inputs_to_hash)
        cached = _cache_manager.get_ai_response(symbol, method, context_hash)
        if cached is not None:
            return cached

    task_prompt = build_suitability_prompt(
        symbol, method, score, category, flags,
        evidence or {}, valuation_inputs or {}, input_decisions or {},
    )

    # Suitability checks use TASK prompt only (no company financial context needed)
    logger.info("[AI] No company context for %s/%s — using task-only prompt", symbol, method)
    full_prompt = task_prompt

    logger.info(
        "[AI] Sending prompt for %s/%s (%d chars):\n--- PROMPT START ---\n%s\n--- PROMPT END ---",
        symbol, method, len(full_prompt), full_prompt,
    )

    result = await provider.generate_text(
        prompt=full_prompt,
        system_instruction=_SUITABILITY_SYSTEM_INSTRUCTION,
        max_tokens=800,
        temperature=0.1,
        timeout=timeout,
    )

    if result and _cache_manager is not None and context_hash:
        _cache_manager.set_ai_response(symbol, method, context_hash, result)

    return result


async def generate_overview_summary(
    symbol:        str,
    sector:        str | None,
    currency:      str,
    current_price: float | None,
    methods:       dict[str, Any],
    timeout:       float = 10.0,
) -> dict[str, Any] | None:
    provider = _get_or_create_provider()
    if provider is None:
        logger.info("[AI] OPEN_ROUTER_KEY not set — overview summaries disabled")
        return None

    if not methods:
        return None

    context = ""
    if _cache_manager is not None:
        context = _cache_manager.get_context(symbol) or ""
        if not context:
            context = await _build_company_context(symbol)
            if context:
                _cache_manager.set_context(symbol, context)
    else:
        context = await _build_company_context(symbol)

    inputs_to_hash = {
        "symbol": symbol,
        "sector": sector,
        "currency": currency,
        "current_price": current_price,
        "methods": methods,
        "context": context,
    }

    context_hash = ""
    if _cache_manager is not None:
        context_hash = _cache_manager.compute_hash(inputs_to_hash)
        cached = _cache_manager.get_ai_response(symbol, "overview", context_hash)
        if cached is not None:
            return cached

    task_prompt = build_overview_prompt(
        symbol=symbol,
        sector=sector,
        currency=currency,
        current_price=current_price,
        methods=methods,
    )

    if context:
        full_prompt = f"{context}=== TASK ===\n\n{task_prompt}"
    else:
        logger.info("[AI] No company context for overview/%s — using task-only prompt", symbol)
        full_prompt = task_prompt

    logger.info(
        "[AI] Sending overview prompt for %s (%d chars):\n--- PROMPT START ---\n%s\n--- PROMPT END ---",
        symbol, len(full_prompt), full_prompt,
    )

    raw = await provider.generate_text(
        prompt=full_prompt,
        system_instruction=_OVERVIEW_SYSTEM_INSTRUCTION,
        max_tokens=1000,
        temperature=0.1,
        timeout=timeout,
    )

    if not raw:
        return None

    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[-1]
        if "```" in clean:
            clean = clean.rsplit("```", 1)[0]
    clean = clean.strip()

    try:
        result = _json.loads(clean)
    except _json.JSONDecodeError as je:
        logger.warning("[AI] overview/%s: JSON parse failed (%s) | raw=%s", symbol, je, raw[:300])
        return None

    required = {"bestMethod", "bestMethodLabel", "reasoning", "consensus", "confidenceNote"}
    if not required.issubset(result.keys()):
        missing = required - result.keys()
        logger.warning("[AI] overview/%s: missing keys %s in response", symbol, missing)
        for k in missing:
            result[k] = OVERVIEW_FALLBACK.get(k, "")

    if result.get("bestMethod") not in _METHOD_LABELS:
        logger.warning("[AI] overview/%s: unknown bestMethod=%s, falling back", symbol, result.get("bestMethod"))
        best = max(methods.items(), key=lambda kv: kv[1].get("score") or 0)
        result["bestMethod"] = best[0]
        result["bestMethodLabel"] = _METHOD_LABELS.get(best[0], best[0])

    if _cache_manager is not None and context_hash:
        _cache_manager.set_ai_response(symbol, "overview", context_hash, result)

    return result

