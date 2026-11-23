"""Unit tests for listing identity resolution at the search/add boundary (AC-1, AC-4)."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from application.services.security_catalog_service import SecurityCatalogService
from domain.listing_identity import ListingIdentityError


class FakeRepo:
    """Catalog stub keyed by provider_symbol. No provider or database I/O."""

    def __init__(self, listings):
        self.listings = {row["provider_symbol"]: row for row in listings}

    def get_or_create_listing(self, candidate):
        return self.listings.get(candidate["provider_symbol"])

    def get_by_id(self, security_id):
        return next(
            (row for row in self.listings.values() if row["security_id"] == security_id),
            None,
        )

    def list_securities_for_symbol(self, symbol):
        return [r for r in self.listings.values() if r["symbol"] == symbol.upper()]


META_US = {
    "security_id": 1, "symbol": "META", "exchange": "NMS", "kind": "COMMON",
    "currency": "USD", "provider_symbol": "META",
}
META_CDR = {
    "security_id": 2, "symbol": "META", "exchange": "NEO", "kind": "CDR",
    "currency": "CAD", "provider_symbol": "META.NE",
}

SERVICE = SecurityCatalogService(FakeRepo([META_US, META_CDR]))


def test_two_listings_for_same_symbol_are_distinct():
    results = SERVICE.search_listings([
        {"symbol": "META", "exchange": "NMS", "type": "equity", "name": "Meta Platforms"},
        {"symbol": "META", "exchange": "NEO", "type": "equity", "name": "Meta Platforms CDR"},
    ])
    assert len(results) == 2
    assert {(r["security_id"], r["exchange"], r["provider_symbol"]) for r in results} == {
        (1, "NMS", "META"), (2, "NEO", "META.NE"),
    }


def test_selected_exchange_is_preserved_from_search_to_add():
    results = SERVICE.search_listings([
        {"symbol": "META", "exchange": "NEO", "type": "equity", "name": "Meta Platforms CDR"},
    ])
    selected = results[0]
    payload, security = SERVICE.resolve_add({
        "watchlist_id": 3,
        **{k: selected[k] for k in ("security_id", "symbol", "exchange", "kind", "currency", "provider_symbol")},
    })
    assert payload["exchange"] == "NEO"
    assert security["provider_symbol"] == "META.NE"


def test_spoofed_exchange_for_a_security_id_is_rejected():
    try:
        SERVICE.resolve_add({
            "watchlist_id": 3, "security_id": 2, "symbol": "META", "exchange": "NMS",
            "kind": "CDR", "currency": "CAD", "provider_symbol": "META.NE",
        })
    except ListingIdentityError as exc:
        assert "exchange" in exc.fields
    else:
        raise AssertionError("mismatched exchange was accepted")


def test_unresolvable_search_hit_is_dropped_not_guessed():
    assert SERVICE.search_listings([
        {"symbol": "ZZZZ", "exchange": "NMS", "type": "equity", "name": "Unknown"},
    ]) == []


def test_malformed_hit_does_not_abort_whole_search():
    """One bad provider hit (e.g. a futures symbol 'SMETA=F') must not suppress
    valid listings in the same batch — otherwise searching META yields nothing."""
    results = SERVICE.search_listings([
        {"symbol": "SMETA=F", "exchange": "CME", "type": "futures", "name": "Meta Futures"},
        {"symbol": "META", "exchange": "NEO", "type": "equity", "name": "Meta Platforms CDR"},
    ])
    assert len(results) == 1
    assert results[0]["provider_symbol"] == "META.NE"


def test_provider_display_exchange_names_are_canonicalized():
    """yfinance sends display names ('NASDAQ'), the catalog uses canonical codes
    ('NMS'). Without this alias, search creates a duplicate META/NASDAQ security
    instead of resolving to the existing META/NMS listing."""
    from domain.listing_identity import normalize_exchange

    assert normalize_exchange("NASDAQ") == "NMS"
    assert normalize_exchange("NYSE") == "NYQ"
    results = SERVICE.search_listings([
        {"symbol": "META", "exchange": "NASDAQ", "type": "equity", "name": "Meta Platforms"},
    ])
    assert len(results) == 1
    assert results[0]["security_id"] == 1
    assert results[0]["exchange"] == "NMS"


def test_catalog_surfaces_alternate_listing_not_returned_by_provider():
    """Provider typeahead returns only META/NMS, but the META/NEO CDR listing is
    in the catalog and must remain selectable in the UI. Otherwise the user cannot
    watch both listings of the same ticker — the core requirement."""
    results = SERVICE.search_all(
        [{"symbol": "META", "exchange": "NMS", "type": "equity", "name": "Meta Platforms"}],
        "META",
    )
    assert {(r["security_id"], r["exchange"], r["provider_symbol"]) for r in results} == {
        (1, "NMS", "META"), (2, "NEO", "META.NE"),
    }


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc!r}")
    raise SystemExit(1 if failed else 0)
