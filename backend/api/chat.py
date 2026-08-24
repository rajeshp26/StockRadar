from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from application.services.ai_service import _get_or_create_provider
from application.services.prompts.chat_prompt import (
    ChatRequest,
    build_chat_system_prompt,
    normalize_symbol,
)
from application.services.prompts.company_snapshot import CompanySnapshotBuilder
from dependencies import get_current_user_dep, get_valuation_repository, limiter
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/valuations", tags=["Digital Twin Chat"])


@router.post(
    "/{symbol}/chat",
    summary="Digital Twin — conversational AI about a stock (SSE streaming).",
)
@limiter.limit("20/minute")
async def chat_with_digital_twin(
    request: Request,
    symbol: str,
    body: ChatRequest,
    user=Depends(get_current_user_dep),
    repo: ValuationRepository = Depends(get_valuation_repository),
):
    sym = normalize_symbol(symbol)

    provider = _get_or_create_provider()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI provider not configured (OPEN_ROUTER_KEY missing).",
        )

    snapshot_builder = CompanySnapshotBuilder(repo)
    try:
        snapshot = await snapshot_builder.build(sym)
    except Exception as exc:
        logger.error("[Chat] Snapshot build failed for %s: %s", sym, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to load company financial data.",
        )

    context = CompanySnapshotBuilder.format_context(snapshot)
    system_prompt = build_chat_system_prompt(sym, context)

    chat_messages = [m.model_dump() for m in body.messages]

    async def event_stream():
        async for event in provider.generate_text_stream(
            messages=chat_messages,
            system_instruction=system_prompt,
            max_tokens=1024,
            temperature=0.1,
            timeout=15.0,
        ):
            if "error" in event:
                yield f"data: {json.dumps(event)}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"
                return
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
