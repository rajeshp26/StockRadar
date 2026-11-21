import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from application.services.prompts.chat_prompt import (
    ChatMessage,
    ChatRequest,
    build_chat_system_prompt,
    normalize_symbol,
)
from providers.ai_provider import OpenRouterProvider

# =============================================================================
# Unit Tests: build_chat_system_prompt (pure function, no mocking needed)
# =============================================================================

class TestChatSystemPrompt:

    def test_build_chat_system_prompt_includes_symbol(self):
        prompt = build_chat_system_prompt("AAPL", "=== COMPANY CONTEXT ===\nRevenue: 391B")
        assert "AAPL" in prompt
        assert "=== COMPANY CONTEXT ===" in prompt
        assert "Revenue: 391B" in prompt
        assert "digital financial analyst" in prompt.lower()

    def test_build_chat_system_prompt_guidelines(self):
        prompt = build_chat_system_prompt("MSFT", "Some context")
        assert "concise and factual" in prompt
        assert "retail investor" in prompt
        assert "do not invent metrics" in prompt.lower()


# =============================================================================
# Unit Tests: normalize_symbol
# =============================================================================

class TestNormalizeSymbol:

    def test_normalize_symbol_valid(self):
        assert normalize_symbol("aapl") == "AAPL"
        assert normalize_symbol("BRK.B") == "BRK.B"
        assert normalize_symbol("  msft  ") == "MSFT"

    def test_normalize_symbol_invalid_empty(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            normalize_symbol("")
        assert exc.value.status_code == 422

    def test_normalize_symbol_invalid_too_long(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            normalize_symbol("TOO_LONG_SYMBOL")
        assert exc.value.status_code == 422


# =============================================================================
# Unit Tests: ChatMessage / ChatRequest models
# =============================================================================

class TestChatModels:

    def test_chat_message_valid(self):
        msg = ChatMessage(role="user", content="What is the P/E ratio?")
        assert msg.role == "user"
        assert msg.content == "What is the P/E ratio?"

    def test_chat_message_invalid_role(self):
        with pytest.raises(Exception):
            ChatMessage(role="admin", content="test")

    def test_chat_message_empty_content_allowed(self):
        msg = ChatMessage(role="assistant", content="")
        assert msg.content == ""

    def test_chat_request_accepts_empty_assistant_message(self):
        req = ChatRequest(messages=[
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content=""),
        ])
        assert len(req.messages) == 2
        assert req.messages[1].content == ""

    def test_chat_request_empty_messages(self):
        with pytest.raises(Exception):
            ChatRequest(messages=[])


# =============================================================================
# Unit Tests: OpenRouterProvider.generate_text_stream
# =============================================================================

class TestOpenRouterProviderStream:

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_yields_tokens(self, mock_settings, mock_httpx):
        """Verify SSE chunks are parsed into correct token events."""
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = MagicMock()
        mock_resp.is_success = True
        lines = [
            'data: {"choices":[{"delta":{"content":"The"}}]}',
            'data: {"choices":[{"delta":{"content":" intrinsic"}}]}',
            'data: {"choices":[{"delta":{"content":" value"}}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ]
        async def mock_aiter_lines():
            for line in lines:
                yield line
        mock_resp.aiter_lines = mock_aiter_lines

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        tokens = []
        async for event in provider.generate_text_stream(
            messages=[{"role": "user", "content": "hi"}]
        ):
            tokens.append(event)

        assert tokens == [
            {"token": "The"},
            {"token": " intrinsic"},
            {"token": " value"},
            {"done": True},
        ]

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_done_signal(self, mock_settings, mock_httpx):
        """Verify [DONE] line yields done signal and stops."""
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = MagicMock()
        mock_resp.is_success = True
        lines = [
            'data: {"choices":[{"delta":{"content":"Only"}}]}',
            "data: [DONE]",
        ]
        async def mock_aiter_lines():
            for line in lines:
                yield line
        mock_resp.aiter_lines = mock_aiter_lines

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        tokens = []
        async for event in provider.generate_text_stream(messages=[]):
            tokens.append(event)

        assert tokens == [
            {"token": "Only"},
            {"done": True},
        ]

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_http_error(self, mock_settings, mock_httpx):
        """Verify non-2xx response yields error event."""
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = AsyncMock()
        mock_resp.is_success = False
        mock_resp.status_code = 429
        mock_resp.text = "Rate limited"
        mock_resp.aiter_lines.return_value = []

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        events = []
        async for event in provider.generate_text_stream(messages=[]):
            events.append(event)

        assert events[0]["error"] == "HTTP 429"
        assert len(events) == 1

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_timeout(self, mock_settings, mock_httpx):
        """Verify TimeoutException yields error event."""
        import httpx
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.side_effect = httpx.TimeoutException("timed out")
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        events = []
        async for event in provider.generate_text_stream(messages=[]):
            events.append(event)

        assert events[0]["error"] == "timeout"

    @patch("providers.ai_provider.settings")
    async def test_stream_no_api_key(self, mock_settings):
        """Verify no API key skips generation entirely."""
        mock_settings.OPEN_ROUTER_KEY = ""
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        provider = OpenRouterProvider()
        events = []
        async for event in provider.generate_text_stream(
            messages=[{"role": "user", "content": "hi"}]
        ):
            events.append(event)

        assert events == []

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_malformed_chunk(self, mock_settings, mock_httpx):
        """Verify malformed JSON chunks are skipped, valid ones still processed."""
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = MagicMock()
        mock_resp.is_success = True
        lines = [
            "data: not valid json",
            'data: {"choices":[{"delta":{"content":" valid"}}]}',
            "not a data line",
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ]
        async def mock_aiter_lines():
            for line in lines:
                yield line
        mock_resp.aiter_lines = mock_aiter_lines

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        tokens = []
        async for event in provider.generate_text_stream(messages=[]):
            tokens.append(event)

        assert tokens == [
            {"token": " valid"},
            {"done": True},
        ]

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_system_instruction_included(self, mock_settings, mock_httpx):
        """Verify system instruction is passed as first message."""
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = MagicMock()
        mock_resp.is_success = True
        lines = [
            'data: {"choices":[{"delta":{"content":"ok"}}]}',
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ]
        async def mock_aiter_lines():
            for line in lines:
                yield line
        mock_resp.aiter_lines = mock_aiter_lines

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        async for _ in provider.generate_text_stream(
            messages=[{"role": "user", "content": "hi"}],
            system_instruction="You are an expert.",
        ):
            pass

        call_kwargs = mock_client.stream.call_args[1]
        body = call_kwargs["json"]
        assert body["messages"][0] == {"role": "system", "content": "You are an expert."}
        assert body["messages"][1] == {"role": "user", "content": "hi"}
        assert body["stream"] is True
        assert body["model"] == "test-model"

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_empty_response(self, mock_settings, mock_httpx):
        """Verify SSE with no content tokens yields only done."""
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = MagicMock()
        mock_resp.is_success = True
        lines = [
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ]
        async def mock_aiter_lines():
            for line in lines:
                yield line
        mock_resp.aiter_lines = mock_aiter_lines

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        events = []
        async for event in provider.generate_text_stream(messages=[]):
            events.append(event)

        assert events == [{"done": True}]

    @patch("providers.ai_provider.httpx.AsyncClient")
    @patch("providers.ai_provider.settings")
    async def test_stream_respects_timeout_param(self, mock_settings, mock_httpx):
        """Verify the timeout parameter is passed to httpx.AsyncClient."""
        import httpx
        mock_settings.OPEN_ROUTER_KEY = "test-key"
        mock_settings.OPEN_ROUTER_MODEL = "test-model"

        mock_resp = MagicMock()
        mock_resp.is_success = True
        lines = [
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        ]
        async def mock_aiter_lines():
            for line in lines:
                yield line
        mock_resp.aiter_lines = mock_aiter_lines

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        stream_ctx = MagicMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_resp)
        stream_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_client.stream.return_value = stream_ctx
        mock_httpx.return_value = mock_client

        provider = OpenRouterProvider()
        async for _ in provider.generate_text_stream(messages=[], timeout=5.0):
            pass

        call_args = mock_httpx.call_args
        timeout_arg = call_args[1]["timeout"]
        assert isinstance(timeout_arg, httpx.Timeout)


# =============================================================================
# Unit Tests: Chat Endpoint Logic (mocked dependencies)
# =============================================================================

class TestChatEndpointUnit:

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    @patch("api.chat.CompanySnapshotBuilder")
    @patch("api.chat.get_valuation_repository")
    async def test_endpoint_returns_streaming_response(
        self, mock_get_repo, mock_snapshot_builder_cls, mock_get_provider
    ):
        """Verify the core logic produces a StreamingResponse with SSE tokens."""
        from fastapi.responses import StreamingResponse

        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"token": "Hello"}
            yield {"done": True}
        mock_provider.generate_text_stream = mock_stream
        mock_get_provider.return_value = mock_provider

        mock_builder = AsyncMock()
        mock_builder.build.return_value = {"key": "data"}
        mock_snapshot_builder_cls.return_value = mock_builder

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

        with patch.object(mock_snapshot_builder_cls, "format_context", return_value="Company data"):
            result = await chat_with_digital_twin(
                request=mock_request,
                symbol="AAPL",
                body=body,
                user={"uid": "test-user"},
                repo=mock_repo,
            )

        assert isinstance(result, StreamingResponse)
        assert result.media_type == "text/event-stream"
        assert result.headers.get("Cache-Control") == "no-cache"

        body_chunks = [chunk async for chunk in result.body_iterator]
        assert any("Hello" in c for c in body_chunks)

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    async def test_endpoint_503_when_no_provider(self, mock_get_provider):
        """Verify 503 when AI provider key is missing."""
        mock_get_provider.return_value = None

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

        with pytest.raises(Exception) as exc_info:
            await chat_with_digital_twin(
                request=mock_request,
                symbol="AAPL",
                body=body,
                user={"uid": "test-user"},
                repo=MagicMock(),
            )
        assert "503" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    @patch("api.chat.CompanySnapshotBuilder")
    @patch("api.chat.get_valuation_repository")
    async def test_endpoint_503_when_snapshot_fails(
        self, mock_get_repo, mock_snapshot_builder_cls, mock_get_provider
    ):
        """Verify 503 when company snapshot build fails."""
        mock_provider = AsyncMock()
        mock_get_provider.return_value = mock_provider

        mock_builder = AsyncMock()
        mock_builder.build.side_effect = ValueError("DB connection failed")
        mock_snapshot_builder_cls.return_value = mock_builder

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

        with pytest.raises(Exception) as exc_info:
            await chat_with_digital_twin(
                request=mock_request,
                symbol="AAPL",
                body=body,
                user={"uid": "test-user"},
                repo=mock_repo,
            )
        assert "503" in str(exc_info.value)

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    @patch("api.chat.CompanySnapshotBuilder")
    @patch("api.chat.get_valuation_repository")
    async def test_endpoint_streams_correct_sse_format(
        self, mock_get_repo, mock_snapshot_builder_cls, mock_get_provider
    ):
        """Verify SSE events are correctly formatted data: lines."""
        import json

        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"token": "Test"}
            yield {"done": True}
        mock_provider.generate_text_stream = mock_stream
        mock_get_provider.return_value = mock_provider

        mock_builder = AsyncMock()
        mock_builder.build.return_value = {"key": "data"}
        mock_snapshot_builder_cls.return_value = mock_builder

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

        with patch.object(mock_snapshot_builder_cls, "format_context", return_value="Company data"):
            result = await chat_with_digital_twin(
                request=mock_request,
                symbol="AAPL",
                body=body,
                user={"uid": "test-user"},
                repo=mock_repo,
            )

        chunks = [c async for c in result.body_iterator]
        lines = [l for l in "".join(chunks).strip().split("\n") if l]

        # First line should be "data: {"token":"Test"}"
        assert lines[0].startswith("data: ")
        parsed = json.loads(lines[0][6:])
        assert parsed["token"] == "Test"

        # Last line should be "data: {"done":true}"
        assert lines[-1].startswith("data: ")
        parsed_done = json.loads(lines[-1][6:])
        assert parsed_done["done"] is True

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    @patch("api.chat.CompanySnapshotBuilder")
    @patch("api.chat.get_valuation_repository")
    async def test_endpoint_forwards_error_event(
        self, mock_get_repo, mock_snapshot_builder_cls, mock_get_provider
    ):
        """Verify provider errors are forwarded as SSE error + done events."""
        import json

        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"error": "rate limited"}
        mock_provider.generate_text_stream = mock_stream
        mock_get_provider.return_value = mock_provider

        mock_builder = AsyncMock()
        mock_builder.build.return_value = {"key": "data"}
        mock_snapshot_builder_cls.return_value = mock_builder

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

        with patch.object(mock_snapshot_builder_cls, "format_context", return_value="Company data"):
            result = await chat_with_digital_twin(
                request=mock_request,
                symbol="AAPL",
                body=body,
                user={"uid": "test-user"},
                repo=mock_repo,
            )

        chunks = [c async for c in result.body_iterator]
        lines = [l for l in "".join(chunks).strip().split("\n") if l]

        assert lines[0].startswith("data: ")
        parsed = json.loads(lines[0][6:])
        assert parsed["error"] == "rate limited"

        assert lines[1].startswith("data: ")
        parsed_done = json.loads(lines[1][6:])
        assert parsed_done["done"] is True

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    @patch("api.chat.CompanySnapshotBuilder")
    @patch("api.chat.get_valuation_repository")
    async def test_endpoint_handles_zero_token_response(
        self, mock_get_repo, mock_snapshot_builder_cls, mock_get_provider
    ):
        """Verify zero-token AI response (immediate done) produces valid SSE."""
        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"done": True}
        mock_provider.generate_text_stream = mock_stream
        mock_get_provider.return_value = mock_provider

        mock_builder = AsyncMock()
        mock_builder.build.return_value = {"key": "data"}
        mock_snapshot_builder_cls.return_value = mock_builder

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

        with patch.object(mock_snapshot_builder_cls, "format_context", return_value="Company data"):
            result = await chat_with_digital_twin(
                request=mock_request,
                symbol="AAPL",
                body=body,
                user={"uid": "test-user"},
                repo=mock_repo,
            )

        chunks = [c async for c in result.body_iterator]
        lines = [l for l in "".join(chunks).strip().split("\n") if l]
        # Should produce exactly one event: the done signal
        assert len(lines) == 1
        parsed = json.loads(lines[0][6:])
        assert parsed["done"] is True

    @pytest.mark.asyncio
    @patch("api.chat._get_or_create_provider")
    @patch("api.chat.CompanySnapshotBuilder")
    @patch("api.chat.get_valuation_repository")
    async def test_endpoint_accepts_empty_assistant_in_history(
        self, mock_get_repo, mock_snapshot_builder_cls, mock_get_provider
    ):
        """Verify request body with empty assistant message is accepted (no 422)."""
        from fastapi.responses import StreamingResponse

        mock_provider = AsyncMock()
        async def mock_stream(**kwargs):
            yield {"token": "Continuing after empty..."}
            yield {"done": True}
        mock_provider.generate_text_stream = mock_stream
        mock_get_provider.return_value = mock_provider

        mock_builder = AsyncMock()
        mock_builder.build.return_value = {"key": "data"}
        mock_snapshot_builder_cls.return_value = mock_builder

        mock_repo = MagicMock()
        mock_get_repo.return_value = mock_repo

        from starlette.requests import Request

        from api.chat import ChatRequest, chat_with_digital_twin
        from application.services.prompts.chat_prompt import ChatMessage
        mock_request = Request(scope={
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 8080),
            "server": ("testserver", 80),
            "scheme": "http",
        })
        body = ChatRequest(messages=[
            ChatMessage(role="user", content="Hi"),
            ChatMessage(role="assistant", content=""),
            ChatMessage(role="user", content="what about RBLX?"),
        ])

        with patch.object(mock_snapshot_builder_cls, "format_context", return_value="Company data"):
            result = await chat_with_digital_twin(
                request=mock_request,
                symbol="RBLX",
                body=body,
                user={"uid": "test-user"},
                repo=mock_repo,
            )

        assert isinstance(result, StreamingResponse)
        body_chunks = [chunk async for chunk in result.body_iterator]
        assert any("Continuing" in c for c in body_chunks)
