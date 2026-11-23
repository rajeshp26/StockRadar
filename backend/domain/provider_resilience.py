"""Listing-scoped provider fetch and rate-limit breaker.

A security is the unit of pricing: `META.NE` (CDR) and `META` (common) are two
listings with two provider symbols. The old price monitor fanned each ticker out
to `.TO/.V/.NE` and shared one global failure state, so a rate limit on one
listing silenced every other listing and `[PriceMonitor] error` spammed the log.

This module makes the retry unit a `security_id`:
  * `refresh_listing` calls the provider exactly once, with the listing's own
    `provider_symbol` (no speculative suffix fan-out);
  * `ListingRateLimitBreaker` opens only for the throttled `security_id`;
  * the breaker half-opens after its retry window, so a recovered provider is
    retried without a process restart.

Pure and synchronous by design: no clock is read unless the caller omits `now`,
which makes the timing rules exactly testable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class RateLimitHit(Exception):
    """A provider signalled 429 / YFRateLimitError for one listing."""

    def __init__(self, retry_after: float = 60.0, message: str = "rate limited"):
        super().__init__(message)
        self.retry_after = float(retry_after)


class QuoteProvider(Protocol):
    """Minimal provider surface used by a listing refresh."""

    def get_quote(self, provider_symbol: str) -> dict[str, Any]: ...


@dataclass
class ListingRateLimitBreaker:
    """Per-security rate-limit breaker with a bounded retry window."""

    cooldown_seconds: float = 60.0
    _open_until: dict[int, float] = field(default_factory=dict)

    def allows(self, security_id: int, now: float | None = None) -> bool:
        """True when this listing may be fetched; expires its own window lazily."""
        until = self._open_until.get(security_id)
        current = time.monotonic() if now is None else now
        if until is None or current >= until:
            self._open_until.pop(security_id, None)
            return True
        return False

    def record(
        self,
        security_id: int,
        retry_after: float | None = None,
        now: float | None = None,
    ) -> None:
        """Open this listing's breaker until `retry_after` seconds from now."""
        current = time.monotonic() if now is None else now
        window = self.cooldown_seconds if retry_after is None else float(retry_after)
        self._open_until[security_id] = current + max(0.0, window)

    def reset(self, security_id: int) -> None:
        """Explicitly close one listing's breaker (e.g. after a successful probe)."""
        self._open_until.pop(security_id, None)


@dataclass(frozen=True)
class ListingRefresh:
    """Outcome of one listing refresh attempt."""

    security_id: int
    provider_symbol: str
    price: float | None = None
    skipped: bool = False
    reason: str = "ok"
    raw: dict[str, Any] = field(default_factory=dict)


def refresh_listing(
    provider: QuoteProvider,
    security: dict[str, Any],
    breaker: ListingRateLimitBreaker,
    now: float | None = None,
) -> ListingRefresh:
    """Fetch one listing by its exact provider symbol, guarded by its breaker.

    Exactly one provider call is made per non-skipped refresh. A rate limit is
    recorded against this `security_id` only; sibling listings remain fetchable.
    """
    security_id = int(security["security_id"])
    provider_symbol = str(security["provider_symbol"])

    if not breaker.allows(security_id, now=now):
        return ListingRefresh(
            security_id=security_id,
            provider_symbol=provider_symbol,
            skipped=True,
            reason="rate_limited",
        )

    try:
        quote = provider.get_quote(provider_symbol) or {}
    except RateLimitHit as hit:
        breaker.record(security_id, retry_after=hit.retry_after, now=now)
        return ListingRefresh(
            security_id=security_id,
            provider_symbol=provider_symbol,
            skipped=True,
            reason="rate_limited",
        )

    price = quote.get("price")
    return ListingRefresh(
        security_id=security_id,
        provider_symbol=provider_symbol,
        price=float(price) if price is not None else None,
        skipped=price is None,
        reason="ok" if price is not None else "no_price",
        raw=quote,
    )
