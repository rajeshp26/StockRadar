"""Provider-wide rate-limit breaker: warning-storm reproduction.

Observed incident: one Yahoo 429 is mapped to ``RateLimitHit`` for every active
listing, so each listing opens its own breaker and logs its own warning every
10-second cycle. The captured POC measured 21 warnings and 6 provider calls over
seven ticks for three listings.

Required behaviour:
  * a provider-wide 429 opens ONE shared gate; while it is open no listing
    issues a provider call and no per-listing warning is emitted;
  * the gate half-opens after its cooldown and a successful probe closes it;
  * a genuinely symbol-local limit still isolates only that listing.

Timing is injected as ``now`` so every rule is deterministic and testable.
"""
from __future__ import annotations

import pytest

from domain.provider_resilience import (
    ListingRateLimitBreaker,
    ProviderErrorCode,
    ProviderRateLimitBreaker,
    ProviderRateLimitHit,
    RateLimitHit,
    provider_error_code,
    refresh_listing,
    should_log_provider_limit,
    summarize_cycle,
)

ENB_TSX = {
    "security_id": 123,
    "symbol": "ENB",
    "exchange": "TSX",
    "kind": "COMMON",
    "currency": "CAD",
    "provider_symbol": "ENB.TO",
}
BCE_TSX = {
    "security_id": 3006,
    "symbol": "BCE",
    "exchange": "TSX",
    "kind": "COMMON",
    "currency": "CAD",
    "provider_symbol": "BCE.TO",
}
META_NMS = {
    "security_id": 146,
    "symbol": "META",
    "exchange": "NMS",
    "kind": "COMMON",
    "currency": "USD",
    "provider_symbol": "META",
}


class _Provider:
    """Deterministic provider: every call either raises the injected error or succeeds."""

    def __init__(self, error: Exception | None = None):
        self.calls: list[str] = []
        self.error = error

    def get_quote(self, provider_symbol: str):
        self.calls.append(provider_symbol)
        if self.error is not None:
            raise self.error
        return {"price": 100.0, "previous_close": 99.0}


# ---------------------------------------------------------------------------
# 1. Reproduction of the reported warning storm
# ---------------------------------------------------------------------------

def test_provider_wide_429_suppresses_every_listing_after_first_hit():
    """A single shared 429 must stop calls for all sibling listings in the cycle."""
    provider = _Provider(error=ProviderRateLimitHit(retry_after=30.0))
    listing_breaker = ListingRateLimitBreaker()
    provider_breaker = ProviderRateLimitBreaker(cooldown_seconds=60.0)

    results = [
        refresh_listing(
            provider, security, listing_breaker,
            provider_breaker=provider_breaker, now=0.0,
        )
        for security in (ENB_TSX, BCE_TSX, META_NMS)
    ]

    # Oracle: a provider-wide gate is shared, so exactly one HTTP call is allowed.
    assert provider.calls == ["ENB.TO"]
    assert [r.reason for r in results] == [
        "provider_rate_limited", "provider_rate_limited", "provider_rate_limited",
    ]
    assert all(r.skipped for r in results)


def test_provider_gate_reopens_after_cooldown_and_closes_on_success():
    """Seven 10-second ticks: one call during cooldown, then calls resume."""
    provider = _Provider(error=ProviderRateLimitHit(retry_after=30.0))
    listing_breaker = ListingRateLimitBreaker()
    provider_breaker = ProviderRateLimitBreaker(cooldown_seconds=30.0)

    for tick in range(7):
        now = tick * 10.0
        for security in (ENB_TSX, BCE_TSX, META_NMS):
            refresh_listing(
                provider, security, listing_breaker,
                provider_breaker=provider_breaker, now=now,
            )

    # Oracle: ticks 1 and 2 are inside the 30s cooldown -> only tick 0 calls.
    assert len(provider.calls) == 3, "one successful call per listing after recovery"

    # Ticks 0, 3 and 6 each opened a 30s gate (until 30, 60, 90).
    provider.error = None
    refresh_listing(
        provider, ENB_TSX, listing_breaker,
        provider_breaker=provider_breaker, now=95.0,
    )
    assert provider_breaker.allows(now=95.0) is True, "success closes the provider gate"


# ---------------------------------------------------------------------------
# 2. Regression guards for existing listing isolation
# ---------------------------------------------------------------------------

def test_symbol_local_limit_still_isolates_siblings():
    """A plain (listing-scoped) RateLimitHit must not open the provider gate."""
    provider = _Provider(error=RateLimitHit(retry_after=30.0))
    listing_breaker = ListingRateLimitBreaker()
    provider_breaker = ProviderRateLimitBreaker(cooldown_seconds=60.0)

    first = refresh_listing(
        provider, ENB_TSX, listing_breaker,
        provider_breaker=provider_breaker, now=0.0,
    )
    # The fake raised on the first symbol only; the sibling must still succeed.
    provider.error = None
    sibling = refresh_listing(
        provider, BCE_TSX, listing_breaker,
        provider_breaker=provider_breaker, now=1.0,
    )

    assert first.reason == "rate_limited"
    assert sibling.skipped is False
    assert provider_breaker.allows(now=1.0) is True
    assert listing_breaker.allows(123, now=1.0) is False
    assert listing_breaker.allows(3006, now=1.0) is True


def test_provider_rate_limit_hit_is_a_rate_limit_hit():
    """Provider-scoped hit remains catchable by existing RateLimitHit handlers."""
    assert isinstance(ProviderRateLimitHit(retry_after=5.0), RateLimitHit)


# ---------------------------------------------------------------------------
# 3. Cycle-level warning aggregation
# ---------------------------------------------------------------------------

def test_cycle_summary_flags_provider_limit_without_counting_per_listing_warnings():
    """21 provider-limited listings collapse to one provider event, not 21 warnings."""
    results = [
        type("R", (), {"reason": "provider_rate_limited", "skipped": True})()
        for _ in range(21)
    ]
    summary = summarize_cycle(results)

    assert summary.provider_limited is True
    assert summary.provider_limited_count == 21
    assert summary.per_listing_rate_limited_count == 0


def test_provider_limit_is_logged_once_per_episode():
    """Log on the closed->open transition; stay silent for every later tick."""
    assert should_log_provider_limit(previously_logged=False, provider_limited=True) is True
    assert should_log_provider_limit(previously_logged=True, provider_limited=True) is False
    # A recovery tick resets the latch, so the next episode logs once again.
    assert should_log_provider_limit(previously_logged=True, provider_limited=False) is False
    assert should_log_provider_limit(previously_logged=False, provider_limited=True) is True


# ---------------------------------------------------------------------------
# 4. Shared pacing
# ---------------------------------------------------------------------------

def test_provider_pacer_spaces_calls_by_configured_min_interval():
    """Oracle (hand computation for a 0.2s interval and blocking callers):

    acquire(0.00) -> wait 0.00, scheduled call at 0.00
    acquire(0.30) -> wait 0.00, scheduled call at 0.30
    acquire(0.35) -> wait 0.15, scheduled call at 0.50
    acquire(0.55) -> wait 0.15, scheduled call at 0.70
    """
    from domain.provider_resilience import ProviderPacer

    pacer = ProviderPacer(min_interval_seconds=0.2)
    assert pacer.acquire(now=0.0) == pytest.approx(0.0)
    assert pacer.acquire(now=0.3) == pytest.approx(0.0)
    assert pacer.acquire(now=0.35) == pytest.approx(0.15)
    assert pacer.acquire(now=0.55) == pytest.approx(0.15)


def test_shared_pacer_is_a_single_instance():
    """All yfinance callers must consult the same throttle."""
    from domain.provider_resilience import get_provider_pacer

    assert get_provider_pacer() is get_provider_pacer()


# ---------------------------------------------------------------------------
# 5. Stable, redacted error codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "exception,expected",
    [
        (
            Exception("YFRateLimitError: Too Many Requests. Rate limited."),
            ProviderErrorCode.RATE_LIMIT,
        ),
        (Exception("HTTP Error 429"), ProviderErrorCode.RATE_LIMIT),
        (
            Exception(
                '{"quoteSummary":{"error":{"code":"Not Found",'
                '"description":"Quote not found for symbol: ENB.TO.TO"}}}'
            ),
            ProviderErrorCode.NOT_FOUND,
        ),
        (Exception("connection reset by peer"), ProviderErrorCode.UNAVAILABLE),
        (ValueError("bad payload"), ProviderErrorCode.UNAVAILABLE),
    ],
)
def test_provider_errors_map_to_stable_codes(exception, expected):
    """Oracle: documented yfinance/Yahoo failure shapes, hand-classified."""
    assert provider_error_code(exception) is expected
