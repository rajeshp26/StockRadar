from __future__ import annotations

import hashlib
import json
import logging
from contextvars import ContextVar
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class CacheManager:
    """Three-layer cache: request-scoped dict + process TTL cache + AI response TTL cache."""

    def __init__(
        self,
        ai_ttl: int = 300,
        query_ttl: int = 30,
        context_ttl: int = 60,
        maxsize_ai: int = 256,
        maxsize_query: int = 512,
        maxsize_context: int = 64,
    ) -> None:
        self._request_cache: ContextVar[dict[str, Any]] = ContextVar("request_cache", default={})
        self._query_cache = TTLCache(maxsize=maxsize_query, ttl=query_ttl)
        self._ai_cache = TTLCache(maxsize=maxsize_ai, ttl=ai_ttl)
        self._context_cache = TTLCache(maxsize=maxsize_context, ttl=context_ttl)

    def cache_key(self, *parts: str) -> str:
        """Joins parts with ':' — e.g. 'query:get_company_context:RBLX'"""
        return ":".join(str(p) for p in parts)

    def get_query_result(self, key: str) -> Any | None:
        """Check request cache, then TTL cache."""
        req_cache = self._request_cache.get()
        if key in req_cache:
            logger.debug("[Cache] Request cache HIT for key: %s", key)
            return req_cache[key]

        if key in self._query_cache:
            logger.debug("[Cache] Query TTL cache HIT for key: %s", key)
            val = self._query_cache[key]
            # Promote to request cache to avoid further lookups in this request
            req_cache[key] = val
            self._request_cache.set(req_cache)
            return val

        logger.debug("[Cache] Query cache MISS for key: %s", key)
        return None

    def set_query_result(self, key: str, value: Any) -> None:
        """Store in request + TTL caches."""
        # Store in request cache
        req_cache = self._request_cache.get()
        req_cache[key] = value
        self._request_cache.set(req_cache)

        # Store in process-level TTL cache
        self._query_cache[key] = value
        logger.debug("[Cache] Query cache SET for key: %s", key)

    def get_ai_response(self, symbol: str, method: str, context_hash: str) -> Any | None:
        """Check AI response cache; hash captures financial data version."""
        key = self.cache_key("ai", symbol, method, context_hash)
        if key in self._ai_cache:
            logger.info("[Cache] AI response cache HIT for %s/%s | hash=%s", symbol, method, context_hash[:8])
            return self._ai_cache[key]
        logger.info("[Cache] AI response cache MISS for %s/%s | hash=%s", symbol, method, context_hash[:8])
        return None

    def set_ai_response(self, symbol: str, method: str, context_hash: str, value: Any) -> None:
        """Store AI response."""
        key = self.cache_key("ai", symbol, method, context_hash)
        self._ai_cache[key] = value
        logger.info("[Cache] AI response cache SET for %s/%s | hash=%s", symbol, method, context_hash[:8])

    def get_context(self, symbol: str) -> str | None:
        """Get formatted company context string."""
        key = self.cache_key("context", symbol)
        if key in self._context_cache:
            logger.info("[Cache] Context string cache HIT for %s", symbol)
            return self._context_cache[key]
        logger.info("[Cache] Context string cache MISS for %s", symbol)
        return None

    def set_context(self, symbol: str, value: str) -> None:
        """Store formatted company context string."""
        key = self.cache_key("context", symbol)
        self._context_cache[key] = value
        logger.info("[Cache] Context string cache SET for %s", symbol)

    def clear_request_cache(self) -> None:
        """Reset request-scoped ContextVar — call at end of each HTTP call via middleware."""
        self._request_cache.set({})
        logger.debug("[Cache] Request cache cleared")

    def clear_all(self) -> None:
        """Clear all three caches completely."""
        self._request_cache.set({})
        self._query_cache.clear()
        self._ai_cache.clear()
        self._context_cache.clear()
        logger.info("[Cache] All caches cleared")

    @staticmethod
    def compute_hash(data: Any) -> str:
        """Compute stable SHA256 hash of any JSON-serializable structure."""
        def serializer(obj: Any) -> Any:
            if isinstance(obj, (set, frozenset)):
                return sorted(list(obj))
            raise TypeError(f"Type {type(obj)} not serializable")

        serialized = json.dumps(data, sort_keys=True, default=serializer)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
