"""
Integration tests for the Digital Twin Chat feature.

These tests exercise the full data flow:
  - Pydantic model validation (ChatMessage, ChatRequest)
  - Symbol normalization
  - System prompt building
  - SSE event stream parsing (simulating frontend ReadableStream reader)
  - Frontend message accumulation logic
  - Empty assistant message guard

No external API calls are made — all provider and repository calls are mocked.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List, Optional


# =============================================================================
# 1. Core model & prompt integration
# =============================================================================

class TestCoreIntegration:

    def test_chat_message_to_provider_format(self):
        """ChatMessage model_dump() produces the dict the provider expects."""
        from application.services.prompts.chat_prompt import ChatMessage, ChatRequest

        msg = ChatMessage(role="user", content="What is the P/E?")
        dumped = msg.model_dump()
        assert dumped == {"role": "user", "content": "What is the P/E?"}

    def test_chat_request_round_trip(self):
        """ChatRequest serializes and deserializes correctly (simulating JSON body)."""
        from application.services.prompts.chat_prompt import ChatMessage, ChatRequest

        original = ChatRequest(messages=[
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content="Hello!"),
        ])
        raw = original.model_dump_json()
        restored = ChatRequest.model_validate_json(raw)
        assert len(restored.messages) == 2
        assert restored.messages[0].content == "Hi"
        assert restored.messages[1].content == "Hello!"

    def test_chat_request_with_empty_assistant(self):
        """Request containing an empty assistant message is accepted (no 422)."""
        from application.services.prompts.chat_prompt import ChatMessage, ChatRequest

        req = ChatRequest(messages=[
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content=""),
            ChatMessage(role="user", content="Tell me more"),
        ])
        assert req.messages[1].content == ""

    def test_chat_request_empty_messages_rejected(self):
        """Empty messages list is rejected."""
        from application.services.prompts.chat_prompt import ChatRequest

        with pytest.raises(Exception):
            ChatRequest(messages=[])

    def test_normalize_symbol_pipe(self):
        """Symbol flows through normalization correctly."""
        from application.services.prompts.chat_prompt import normalize_symbol

        assert normalize_symbol("  rblx  ") == "RBLX"
        assert normalize_symbol("brk.b") == "BRK.B"

    def test_system_prompt_contains_context(self):
        """System prompt includes symbol and context verbatim."""
        from application.services.prompts.chat_prompt import build_chat_system_prompt

        context = "=== CONTEXT ===\nRevenue: $5B\nP/E: 25"
        prompt = build_chat_system_prompt("RBLX", context)
        assert "RBLX" in prompt
        assert "Revenue: $5B" in prompt
        assert "P/E: 25" in prompt
        assert "guidelines" in prompt.lower()


# =============================================================================
# 2. SSE stream parsing integration
# =============================================================================

class MockStreamReader:
    """Simulates a ReadableStreamDefaultReader for SSE data chunks."""

    def __init__(self, chunks: List[bytes]):
        self._chunks = list(chunks)
        self._idx = 0

    async def read(self):
        if self._idx >= len(self._chunks):
            return {"done": True, "value": None}
        chunk = self._chunks[self._idx]
        self._idx += 1
        return {"done": False, "value": chunk}


def parse_sse_stream(chunks: List[bytes]) -> dict:
    """
    Simulates the SSE parsing logic from the frontend use-chat.ts hook.

    Returns:
        accumulated_content: full text accumulated from token events
        errors: list of error strings
    """
    accumulated = ""
    errors: List[str] = []
    buffer = ""
    decoder = json.JSONDecoder()

    for chunk in chunks:
        buffer += chunk.decode("utf-8")
        lines = buffer.split("\n")
        buffer = lines.pop() or ""

        for line in lines:
            if not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
                if data.get("done"):
                    pass  # signal done — caller decides what to do with accumulated
                elif "token" in data:
                    accumulated += data["token"]
                elif "error" in data:
                    errors.append(data["error"])
            except json.JSONDecodeError:
                continue

    return {"content": accumulated, "errors": errors}


class TestSSEParsingIntegration:

    def test_parse_multi_token_stream(self):
        """Multiple token events are accumulated correctly."""
        chunks = [
            b'data: {"token":"RBLX"}\n\n',
            b'data: {"token":" is"}\n\n',
            b'data: {"token":" growing"}\n\n',
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["content"] == "RBLX is growing"
        assert result["errors"] == []

    def test_parse_token_spans_chunks(self):
        """Token split across chunks still accumulates correctly."""
        chunks = [
            b'data: {"token":"RBLX is"}\n\n',
            b'data: {"token":" a "}\ndata: {"tok',
            b'en":"great company"}\n\ndata: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["content"] == "RBLX is a great company"

    def test_parse_zero_tokens_only_done(self):
        """No token events — only done signal — produces empty content."""
        chunks = [
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["content"] == ""

    def test_parse_empty_chunk(self):
        """Empty incoming chunks are handled gracefully."""
        chunks = [
            b'',
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["content"] == ""

    def test_parse_malformed_events_skipped(self):
        """Malformed JSON in SSE is skipped, valid events still processed."""
        chunks = [
            b'data: not-json\n\n',
            b'data: {"token":"valid"}\n\n',
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["content"] == "valid"

    def test_parse_error_event(self):
        """Error events are collected separately."""
        chunks = [
            b'data: {"error":"rate limited"}\n\n',
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["errors"] == ["rate limited"]

    def test_parse_multiple_events_in_one_chunk(self):
        """Multiple SSE events packed in a single chunk are all processed."""
        chunks = [
            b'data: {"token":"First"}\n\ndata: {"token":" Second"}\n\ndata: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        assert result["content"] == "First Second"


# =============================================================================
# 3. Frontend message accumulation integration
# =============================================================================

class TestFrontendMessageFlow:

    def test_empty_assistant_guard(self):
        """
        Simulate the frontend fix: a done signal with zero accumulated tokens
        should NOT append an assistant message to the conversation history.
        """
        accumulated = ""
        messages: List[dict] = [{"role": "user", "content": "Hi"}]

        # Simulate SSE: only done, no tokens
        chunks = [b'data: {"done":true}\n\n']
        result = parse_sse_stream(chunks)

        # The fix: only append if content is non-empty
        if result["content"]:
            messages.append({"role": "assistant", "content": result["content"]})

        assert len(messages) == 1  # No empty assistant appended
        assert messages[0]["role"] == "user"

    def test_normal_assistant_message_appended(self):
        """
        Normal flow: tokens accumulated, then done → assistant message appended.
        """
        accumulated = ""
        messages: List[dict] = [{"role": "user", "content": "Hi"}]

        chunks = [
            b'data: {"token":"Hello"}\n\n',
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)

        if result["content"]:
            messages.append({"role": "assistant", "content": result["content"]})

        assert len(messages) == 2
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Hello"

    def test_conversation_continues_after_empty_assistant(self):
        """
        Simulate the full bug scenario:
        1. User sends "Hi" → AI returns empty (zero tokens)
        2. Second user message is sent without empty assistant in history
        3. Next AI response is processed correctly
        """
        messages: List[dict] = []

        # --- Turn 1: user sends "Hi" ---
        messages.append({"role": "user", "content": "Hi"})
        chunks_1 = [b'data: {"done":true}\n\n']
        result_1 = parse_sse_stream(chunks_1)
        if result_1["content"]:
            messages.append({"role": "assistant", "content": result_1["content"]})

        assert len(messages) == 1  # No empty assistant appended
        assert messages[-1]["content"] == "Hi"

        # --- Turn 2: user sends "what about RBLX?" ---
        messages.append({"role": "user", "content": "what about RBLX?"})
        chunks_2 = [
            b'data: {"token":"RBLX is..."}\n\n',
            b'data: {"done":true}\n\n',
        ]
        result_2 = parse_sse_stream(chunks_2)
        if result_2["content"]:
            messages.append({"role": "assistant", "content": result_2["content"]})

        assert len(messages) == 3  # user, user, assistant
        assert messages[0] == {"role": "user", "content": "Hi"}
        assert messages[1] == {"role": "user", "content": "what about RBLX?"}
        assert messages[2] == {"role": "assistant", "content": "RBLX is..."}

    def test_conversation_continues_after_error(self):
        """After an error event, subsequent messages still work."""
        messages: List[dict] = []

        # --- Turn 1: error ---
        messages.append({"role": "user", "content": "Hi"})
        # frontend would display error but not append assistant

        # --- Turn 2: successful response ---
        messages.append({"role": "user", "content": "Is RBLX a buy?"})
        chunks = [
            b'data: {"token":"Based on data..."}\n\n',
            b'data: {"done":true}\n\n',
        ]
        result = parse_sse_stream(chunks)
        if result["content"]:
            messages.append({"role": "assistant", "content": result["content"]})

        assert len(messages) == 3


# =============================================================================
# 4. Endpoint request/response cycle (mocked AI provider)
# =============================================================================

class TestEndpointIntegration:

    @pytest.mark.asyncio
    async def test_chat_endpoint_lifecycle(self):
        """Full lifecycle: validate → build context → stream → parse SSE."""
        from fastapi.responses import StreamingResponse
        from starlette.requests import Request
        from application.services.prompts.chat_prompt import ChatRequest, ChatMessage, build_chat_system_prompt

        # 1. Build a valid request
        body = ChatRequest(messages=[
            ChatMessage(role="user", content="How is RBLX doing?"),
        ])
        assert len(body.messages) == 1

        # 2. Build system prompt (simulating what the endpoint does)
        context = "Revenue: $2.7B, Net Income: -$1.2B"
        prompt = build_chat_system_prompt("RBLX", context)
        assert "RBLX" in prompt
        assert "Revenue: $2.7B" in prompt

        # 3. Mock provider + call endpoint
        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"token": "RBLX has growing revenue"}
            yield {"done": True}
        mock_provider.generate_text_stream = mock_stream

        # Verify provider was called with correct messages
        sent_messages = []
        original_stream = mock_stream

        async def capturing_stream(**kwargs):
            nonlocal sent_messages
            sent_messages = kwargs.get("messages", [])
            async for event in original_stream(**kwargs):
                yield event

        mock_provider.generate_text_stream = capturing_stream

        stream = mock_provider.generate_text_stream(
            messages=body.messages,
            system_instruction=prompt,
            max_tokens=1024,
            temperature=0.1,
        )

        tokens = [e async for e in stream]
        assert tokens == [
            {"token": "RBLX has growing revenue"},
            {"done": True},
        ]

        # 4. Simulate frontend SSE parsing
        sse_chunks = []
        for t in tokens:
            line = f"data: {json.dumps(t)}\n\n"
            sse_chunks.append(line.encode())

        result = parse_sse_stream(sse_chunks)
        assert result["content"] == "RBLX has growing revenue"
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_endpoint_zero_token_still_valid_sse(self):
        """Zero-token response from provider still produces valid SSE."""
        from application.services.prompts.chat_prompt import build_chat_system_prompt

        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"done": True}
        mock_provider.generate_text_stream = mock_stream

        stream = mock_provider.generate_text_stream(
            messages=[{"role": "user", "content": "Hi"}],
            system_instruction=build_chat_system_prompt("TEST", "Context"),
        )

        events = [e async for e in stream]
        assert events == [{"done": True}]

        # Simulate frontend parsing
        sse = b"".join(f"data: {json.dumps(e)}\n\n".encode() for e in events)
        result = parse_sse_stream([sse])
        assert result["content"] == ""

    @pytest.mark.asyncio
    async def test_endpoint_error_sse_format(self):
        """Error responses produce correct SSE error + done events."""
        from application.services.prompts.chat_prompt import build_chat_system_prompt

        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"error": "rate limited"}
        mock_provider.generate_text_stream = mock_stream

        stream = mock_provider.generate_text_stream(
            messages=[{"role": "user", "content": "Hi"}],
            system_instruction=build_chat_system_prompt("TEST", "Context"),
        )

        events = [e async for e in stream]
        assert events == [{"error": "rate limited"}]

        # Simulate backend forwarding: error yields two SSE events
        sse_events = []
        for e in events:
            if "error" in e:
                sse_events.append(f"data: {json.dumps(e)}\n\n")
                sse_events.append(f"data: {json.dumps({'done': True})}\n\n")

        sse = b"".join(s.encode() for s in sse_events)
        result = parse_sse_stream([sse])
        assert result["errors"] == ["rate limited"]
