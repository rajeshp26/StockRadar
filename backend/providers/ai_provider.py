from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

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
    ) -> Optional[str]:
        ...

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system_instruction: str = "",
        max_tokens: int = 1000,
        temperature: float = 0.1,
        timeout: float = 10.0,
    ) -> Optional[Dict[str, Any]]:
        ...


class OpenRouterProvider(AIProvider):

    _BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

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
    ) -> Optional[str]:
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
    ) -> Optional[Dict[str, Any]]:
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
