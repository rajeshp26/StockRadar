"""Listing-scoped provider fetch with a provider-wide rate-limit gate.

A security is the unit of pricing: `META.NE` (CDR) and `META` (common) are two
listings with two provider symbols. The old price monitor fanned each ticker out
to `.TO/.V/.NE` and shared one global failure state, so a rate limit on one
listing silenced every other listing and `[PriceMonitor] error` spammed the log.

Two distinct failure scopes are modelled now:

  * `ProviderRateLimitHit` - Yahoo answered 429 for the shared egress/IP. This
    opens ONE `ProviderRateLimitBreaker` gate: every listing pauses together,
    one warning is emitted per episode, and a single probe detects recovery.
  * `RateLimitHit` - a genuinely symbol-local limit. This opens only that
    security's `ListingRateLimitBreaker`, so siblings keep refreshing.

`refresh_listing` calls the provider exactly once per non-skipped refresh, with
the listing's own `provider_symbol` (no speculative suffix fan-out). An optional
shared `ProviderPacer` spaces calls across every yfinance caller.

Pure and synchronous by design: no clock is read unless the caller omits `now`,
which makes the timing rules exactly testable.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class RateLimitScope(StrEnum):
    """Which breaker a rate-limit response belongs to."""

    PROVIDER = "provider"
    LISTING = "listing"


class ProviderErrorCode(StrEnum):
    """Stable, credential-free codes for provider failures in logs and APIs."""

    RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    NOT_FOUND = "PROVIDER_NOT_FOUND"
    UNAVAILABLE = "PROVIDER_UNAVAILABLE"


def provider_error_code(exc: Exception) -> ProviderErrorCode:
    """Classify a raw provider exception without exposing its payload.

    yfinance exceptions carry no status/headers and their text can include
    session detail. Callers log only this code; the raw exception stays as the
    chained cause for local debugging.
    """
    name = type(exc).__name__
    text = str(exc)
    if "RateLimit" in name or "429" in text or "Too Many Requests" in text:
        return ProviderErrorCode.RATE_LIMIT
    if "404" in text or "Not Found" in text or "Quote not found" in text:
        return ProviderErrorCode.NOT_FOUND
    return ProviderErrorCode.UNAVAILABLE


class RateLimitHit(Exception):
    """A provider signalled 429 / YFRateLimitError for one listing.

    Defaults to listing scope so existing callers keep their isolation
    semantics; Yahoo's IP-level 429s are raised as `ProviderRateLimitHit`.
    """

    def __init__(
        self,
        retry_after: float = 60.0,
        message: str = "rate limited",
        scope: RateLimitScope = RateLimitScope.LISTING,
    ):
        super().__init__(message)
        self.retry_after = float(retry_after)
        self.scope = scope


class ProviderRateLimitHit(RateLimitHit):
    """A provider-wide (shared egress / IP) rate limit, not a bad listing."""

    def __init__(
        self,
        retry_after: float = 60.0,
        message: str = "provider rate limited",
        provider: str = "yfinance",
    ):
        super().__init__(
            retry_after=retry_after,
            message=message,
            scope=RateLimitScope.PROVIDER,
        )
        self.provider = provider


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


@dataclass
class ProviderRateLimitBreaker:
    """One shared gate for provider-wide (IP-level) throttling.

    Yahoo rate-limits the egress, not individual tickers. Opening one gate per
    listing turns a single 429 into N warnings and N redundant HTTP calls each
    cycle. This gate is keyed by provider so it can be shared by every caller.
    """

    cooldown_seconds: float = 60.0
    _open_until: dict[str, float] = field(default_factory=dict)

    def allows(self, provider: str = "yfinance", now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        until = self._open_until.get(provider)
        if until is None or current >= until:
            self._open_until.pop(provider, None)
            return True
        return False

    def record(
        self,
        retry_after: float | None = None,
        now: float | None = None,
        provider: str = "yfinance",
    ) -> None:
        current = time.monotonic() if now is None else now
        window = self.cooldown_seconds if retry_after is None else float(retry_after)
        self._open_until[provider] = current + max(0.0, window)

    def reset(self, provider: str = "yfinance") -> None:
        self._open_until.pop(provider, None)


@dataclass
class ProviderPacer:
    """Minimum-interval gate shared by every caller of a provider.

    `acquire` returns the seconds the caller must wait before issuing its
    request and reserves the next slot. It never sleeps itself, so callers can
    choose blocking or async waits and tests stay deterministic.
    """

    min_interval_seconds: float = 0.1
    _last_call: float | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def acquire(self, now: float | None = None) -> float:
        current = time.monotonic() if now is None else now
        with self._lock:
            if self._last_call is None:
                self._last_call = current
                return 0.0
            ready_at = self._last_call + max(0.0, self.min_interval_seconds)
            if current >= ready_at:
                self._last_call = current
                return 0.0
            wait = ready_at - current
            self._last_call = ready_at
            return wait


_shared_pacer: ProviderPacer | None = None
_pacer_lock = threading.Lock()


def get_provider_pacer() -> ProviderPacer:
    """Return the process-wide provider throttle (one slot for all callers).

    shortcut: per-process pacing only, upgrade when a second backend process
    shares the same Yahoo egress and needs a cross-process rate limit.
    """
    global _shared_pacer
    if _shared_pacer is None:
        with _pacer_lock:
            if _shared_pacer is None:
                _shared_pacer = ProviderPacer()
    return _shared_pacer


@dataclass(frozen=True)
class ListingRefresh:
    """Outcome of one listing refresh attempt."""

    security_id: int
    provider_symbol: str
    price: float | None = None
    skipped: bool = False
    reason: str = "ok"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CycleSummary:
    """Aggregated outcome of one price-monitor cycle."""

    provider_limited: bool
    provider_limited_count: int
    per_listing_rate_limited_count: int


def summarize_cycle(results: list[ListingRefresh]) -> CycleSummary:
    """Collapse per-listing outcomes into one provider event plus listing counts."""
    provider_count = sum(
        1 for r in results if getattr(r, "reason", None) == "provider_rate_limited"
    )
    listing_count = sum(
        1 for r in results if getattr(r, "reason", None) == "rate_limited"
    )
    return CycleSummary(
        provider_limited=provider_count > 0,
        provider_limited_count=provider_count,
        per_listing_rate_limited_count=listing_count,
    )


def should_log_provider_limit(previously_logged: bool, provider_limited: bool) -> bool:
    """True only on the closed->open transition, so one episode logs once."""
    return provider_limited and not previously_logged


def refresh_listing(
    provider: QuoteProvider,
    security: dict[str, Any],
    breaker: ListingRateLimitBreaker,
    provider_breaker: ProviderRateLimitBreaker | None = None,
    pacer: ProviderPacer | None = None,
    now: float | None = None,
) -> ListingRefresh:
    """Fetch one listing by its exact provider symbol, guarded by both breakers.

    Exactly one provider call is made per non-skipped refresh. A provider-wide
    429 pauses every listing; a symbol-local 429 isolates only this
    `security_id`. Sibling listings remain fetchable in the latter case.
    """
    security_id = int(security["security_id"])
    provider_symbol = str(security["provider_symbol"])

    if provider_breaker is not None and not provider_breaker.allows(now=now):
        return ListingRefresh(
            security_id=security_id,
            provider_symbol=provider_symbol,
            skipped=True,
            reason="provider_rate_limited",
        )

    if not breaker.allows(security_id, now=now):
        return ListingRefresh(
            security_id=security_id,
            provider_symbol=provider_symbol,
            skipped=True,
            reason="rate_limited",
        )

    if pacer is not None:
        wait = pacer.acquire(now=now)
        if wait > 0:
            # The provider call is synchronous network I/O already; a short
            # spacing sleep on the same thread keeps all callers on one clock.
            time.sleep(wait)

    try:
        quote = provider.get_quote(provider_symbol) or {}
    except ProviderRateLimitHit as hit:
        if provider_breaker is not None:
            provider_breaker.record(hit.retry_after, now=now, provider=hit.provider)
        else:
            breaker.record(security_id, retry_after=hit.retry_after, now=now)
        return ListingRefresh(
            security_id=security_id,
            provider_symbol=provider_symbol,
            skipped=True,
            reason="provider_rate_limited",
        )
    except RateLimitHit as hit:
        breaker.record(security_id, retry_after=hit.retry_after, now=now)
        return ListingRefresh(
            security_id=security_id,
            provider_symbol=provider_symbol,
            skipped=True,
            reason="rate_limited",
        )

    if provider_breaker is not None:
        provider_breaker.reset()

    price = quote.get("price")
    return ListingRefresh(
        security_id=security_id,
        provider_symbol=provider_symbol,
        price=float(price) if price is not None else None,
        skipped=price is None,
        reason="ok" if price is not None else "no_price",
        raw=quote,
    )
