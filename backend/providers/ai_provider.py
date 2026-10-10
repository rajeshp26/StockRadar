from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from config import settings

logger = logging.getLogger(__name__)


class AIProvider(ABC):

    @abstractmethod
    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 800,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> str | None:
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> dict[str, Any] | None:
        ...

    @abstractmethod
    async def generate_text_stream(
        self,
        messages: list[dict[str, str]],
        system_instruction: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.1,
        timeout: float = 15.0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream tokens from the AI provider.

        Yields dicts with one of these shapes:
          {"token": "word"}    — a content token to stream to the client
          {"done": True}       — signals the response is complete
          {"error": "..."}     — something went wrong, stop streaming
        """
        ...
        if False:
            yield  # pragma: no cover — make the generator type-check


class OpenRouterProvider(AIProvider):

    _BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
    _credits_exhausted = False
    _credits_warned = False

    def __init__(self) -> None:
        self._api_key = settings.OPEN_ROUTER_KEY or ""
        self._model = settings.OPEN_ROUTER_MODEL

    async def generate_text(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 800,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> str | None:
        if OpenRouterProvider._credits_exhausted:
            logger.warning("[AI] OpenRouter credits exhausted — skipping text generation")
            return None
        if not self._api_key:
            logger.info("[AI] OPEN_ROUTER_KEY not set — text generation disabled")
            return None

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    self._BASE_URL,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                )
                if not resp.is_success:
                    if resp.status_code == 402 or "Insufficient credits" in resp.text:
                        OpenRouterProvider._credits_exhausted = True
                        OpenRouterProvider._credits_warned = True
                        logger.warning("[AI] OpenRouter credits exhausted (402) — opening breaker")
                    logger.warning(
                        "[AI] OpenRouter %s | body: %s",
                        resp.status_code, resp.text[:500],
                    )
                    return None

                data = resp.json()
                choice = data.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "").strip()

                if content:
                    logger.info(
                        "[AI] OpenRouter text: %d chars | finish=%s | prompt=%s out=%s",
                        len(content),
                        choice.get("finish_reason"),
                        data.get("usage", {}).get("prompt_tokens"),
                        data.get("usage", {}).get("completion_tokens"),
                    )
                else:
                    logger.warning(
                        "[AI] Empty response | finish=%s | raw=%s",
                        choice.get("finish_reason"), str(data)[:300],
                    )

                return content or None

        except httpx.TimeoutException:
            logger.warning("[AI] OpenRouter text generation timed out")
            return None
        except Exception as exc:
            logger.warning("[AI] OpenRouter text generation failed: %s", exc)
            return None

    async def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> dict[str, Any] | None:
        raw = await self.generate_text(
            prompt=prompt,
            system_instruction=system_instruction,
            max_tokens=max_tokens,
            temperature=temperature,
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
            return json.loads(clean)
        except json.JSONDecodeError as je:
            logger.warning("[AI] JSON parse failed: %s | raw=%s", je, raw[:300])
            return None

    async def generate_text_stream(
        self,
        messages: list[dict[str, str]],
        system_instruction: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.1,
        timeout: float = 15.0,
    ) -> AsyncGenerator[dict[str, Any], None]:
        if OpenRouterProvider._credits_exhausted:
            logger.warning("[AI] OpenRouter credits exhausted — skipping stream generation")
            return
        if not self._api_key:
            logger.info("[AI] OPEN_ROUTER_KEY not set — streaming disabled")
            return

        chat_messages: list[dict[str, str]] = []
        if system_instruction:
            chat_messages.append({"role": "system", "content": system_instruction})
        chat_messages.extend(messages)

        body = {
            "model": self._model,
            "messages": chat_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                async with client.stream(
                    "POST",
                    self._BASE_URL,
                    json=body,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                ) as resp:
                    if not resp.is_success:
                        if resp.status_code == 402 or "Insufficient credits" in resp.text:
                            OpenRouterProvider._credits_exhausted = True
                            OpenRouterProvider._credits_warned = True
                            logger.warning("[AI] OpenRouter credits exhausted (402) — opening breaker")
                        logger.warning(
                            "[AI] OpenRouter stream %s | body: %s",
                            resp.status_code, resp.text[:500],
                        )
                        yield {"error": f"HTTP {resp.status_code}"}
                        return

                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            yield {"done": True}
                            return
                        try:
                            chunk = json.loads(payload)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                yield {"token": content}
                            finish = chunk.get("choices", [{}])[0].get("finish_reason")
                            if finish == "stop":
                                yield {"done": True}
                                return
                        except json.JSONDecodeError:
                            continue

        except httpx.TimeoutException:
            logger.warning("[AI] OpenRouter stream timed out")
            yield {"error": "timeout"}
        except Exception as exc:
            logger.warning("[AI] OpenRouter stream failed: %s", exc)
            yield {"error": str(exc)}
