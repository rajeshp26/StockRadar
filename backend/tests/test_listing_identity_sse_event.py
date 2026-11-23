"""SSE price_update events must carry full listing identity (AC-2/AC-5).

The original defect lost the selected listing once a quote entered the SSE cache:
two META listings shared a ticker, so their events were indistinguishable and one
overwrote the other. These tests pin the contract that every listing-aware event
carries all six identity fields and that sibling listings stay distinct end to end.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _identity(security_id, exchange, kind, provider_symbol, currency):
    return {
        "security_id": security_id,
        "symbol": "META",
        "exchange": exchange,
        "kind": kind,
        "currency": currency,
        "provider_symbol": provider_symbol,
    }


def test_quote_event_carries_all_six_identity_fields():
    from domain.listing_identity import build_quote_event, listing_payload

    identity = _identity(3128, "NEO", "CDR", "META.NE", "CAD")
    event = build_quote_event(
        identity=identity,
        price=50.0,
        last_updated="2026-11-22T00:00:00Z",
        change=1.5,
        change_percent=3.0,
        source="live",
    )

    assert event["type"] == "price_update"
    assert listing_payload(event) == identity
    assert event["price"] == 50.0
    assert event["lastUpdated"] == "2026-11-22T00:00:00Z"
    assert event["source"] == "live"
    assert event["change"] == 1.5
    assert event["changePercent"] == 3.0


def test_sibling_listings_produce_distinct_identity_bearing_events():
    """META/NMS and META/NEO share a ticker but must never collapse to one key."""
    from domain.listing_identity import build_quote_event

    direct = build_quote_event(
        identity=_identity(2833, "NMS", "COMMON", "META", "USD"),
        price=560.84, last_updated="2026-11-22T00:00:00Z",
    )
    cdr = build_quote_event(
        identity=_identity(3128, "NEO", "CDR", "META.NE", "CAD"),
        price=50.0, last_updated="2026-11-22T00:00:00Z",
    )

    # Same ticker, different price AND different security identity.
    assert direct["symbol"] == cdr["symbol"] == "META"
    assert direct["price"] != cdr["price"]
    assert direct["security_id"] == 2833 and cdr["security_id"] == 3128
    assert direct["provider_symbol"] == "META" and cdr["provider_symbol"] == "META.NE"
    assert direct["exchange"] == "NMS" and cdr["exchange"] == "NEO"
    assert direct["kind"] == "COMMON" and cdr["kind"] == "CDR"


def test_quote_event_rejects_incomplete_identity():
    """Identity is required, never inferred from the symbol alone."""
    from domain.listing_identity import ListingIdentityError, build_quote_event

    try:
        build_quote_event(
            identity={"symbol": "META"},  # missing the other five fields
            price=50.0,
            last_updated="2026-11-22T00:00:00Z",
        )
    except ListingIdentityError as exc:
        assert "security_id" in exc.fields
    else:
        raise AssertionError("incomplete identity must be rejected, not guessed")
