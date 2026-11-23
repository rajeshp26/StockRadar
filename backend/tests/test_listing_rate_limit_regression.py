"""REG-006/REQ-005: listing-scoped provider fetch and rate-limit breaker.

Observed symptoms: `YFRateLimitError: Too Many Requests`, `[PriceMonitor] error`
from a 4-ticker `.TO/.V/.NE` fan-out, and `[PRICE] All providers failed`. A
listing refresh must issue exactly one request to its own provider symbol. A
rate limit on one security must not block another, and must reset after the
retry window.
"""
from __future__ import annotations

from domain.provider_resilience import (
    ListingRateLimitBreaker,
    RateLimitHit,
    refresh_listing,
)

META_NEO = {
    "security_id": 145,
    "symbol": "META",
    "exchange": "NEO",
    "kind": "CDR",
    "currency": "CAD",
    "provider_symbol": "META.NE",
    "cdr_ratio": 10.0,
}
META_NMS = {
    "security_id": 146,
    "symbol": "META",
    "exchange": "NMS",
    "kind": "COMMON",
    "currency": "USD",
    "provider_symbol": "META",
    "cdr_ratio": None,
}


class _FakeProvider:
    def __init__(self, price: float = 100.0, fail_for: str | None = None):
        self.calls: list[str] = []
        self.price = price
        self.fail_for = fail_for

    def get_quote(self, provider_symbol: str):
        self.calls.append(provider_symbol)
        if provider_symbol == self.fail_for:
            raise RateLimitHit(retry_after=30.0)
        return {"price": self.price}


def test_refresh_issues_exactly_one_request_to_the_listing_provider_symbol():
    provider = _FakeProvider()
    result = refresh_listing(provider, META_NEO, ListingRateLimitBreaker(), now=0.0)

    assert provider.calls == ["META.NE"]
    assert result.price == 100.0
    assert result.skipped is False


def test_rate_limit_breaker_is_scoped_to_security_id_and_resets():
    provider = _FakeProvider(fail_for="META.NE")
    breaker = ListingRateLimitBreaker()

    first = refresh_listing(provider, META_NEO, breaker, now=0.0)
    assert first.skipped is True
    assert first.reason == "rate_limited"

    # The throttled listing is closed, but its sibling listing is unaffected.
    assert breaker.allows(145, now=1.0) is False
    assert breaker.allows(146, now=1.0) is True
    sibling = refresh_listing(provider, META_NMS, breaker, now=1.0)
    assert sibling.skipped is False
    assert sibling.price == 100.0

    # After the retry window, the breaker half-opens and the provider is retried.
    assert breaker.allows(145, now=31.0) is True
    provider.fail_for = None
    recovered = refresh_listing(provider, META_NEO, breaker, now=31.0)
    assert recovered.skipped is False
    assert provider.calls.count("META.NE") == 2
