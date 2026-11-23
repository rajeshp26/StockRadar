"""Black-box system tests for the security-master listing identity criteria.

These tests know nothing about the implementation. They log in through Supabase
Auth over HTTP and drive the running backend's public endpoints, using the two
real META listings profiled in data/MANIFEST.json. A ticker is not an instrument:
META/NMS/COMMON and META/NEO/CDR must stay separate in search, quotes, watchlist
prices and structure, including their effective CDR price.

Every mutation is reverted through the same public API in a finally block, so a
run leaves the real watchlist exactly as it found it.
"""
from __future__ import annotations

import requests

from test_support import _base, get, session

DATA = "data:listing-identity-2026-11-22"
NMS_ID = 2833
NEO_ID = 3128
NEO_ADD = {
    "watchlist_id": 6,
    "symbol": "META",
    "security_id": NEO_ID,
    "exchange": "NEO",
    "kind": "CDR",
    "currency": "CAD",
    "provider_symbol": "META.NE",
}
CSRF = {"X-Requested-With": "XMLHttpRequest"}
CENT = 0.01


def _stocks(watchlist_id=6):
    resp = session().post(_base() + "/watchlists/%d/structure" % watchlist_id,
                          headers=CSRF, timeout=60)
    assert resp.status_code == 200, "structure %d answered %d" % (watchlist_id, resp.status_code)
    return resp.json()["stocks"]


def _meta_rows(rows):
    return [r for r in rows if r.get("symbol") == "META"]


def _ensure_neo_item():
    """Add the CDR listing only when absent; return True if this call created it."""
    if any(r.get("securityId") == NEO_ID for r in _meta_rows(_stocks())):
        return False
    resp = session().post(_base() + "/watchlist-items", json=NEO_ADD,
                          headers=CSRF, timeout=120)
    if resp.status_code == 429 and any(
        r.get("securityId") == NEO_ID for r in _meta_rows(_stocks())
    ):
        # A sibling test already seeded the same listing and the endpoint's
        # per-minute limiter rejected the redundant second add. The real-stack
        # invariant under test (one CDR row) is already present.
        return False
    assert resp.status_code == 201, "add CDR answered %d: %s" % (
        resp.status_code, resp.text[:200])
    return True


def _delete_neo_item():
    for row in _meta_rows(_stocks()):
        if row.get("securityId") == NEO_ID and row.get("id"):
            session().post(_base() + "/watchlist-items/delete",
                           json={"item_id": row["id"]}, headers=CSRF, timeout=60)


def test_search_surfaces_both_meta_listings():
    """AC-2 AC-4 AC-6 kind:positive data:listing-identity-2026-11-22 shape:duplicate_ticker_two_listings shape:cdr_with_ratio shape:common_no_ratio search offers both META listings as distinct tradable identities"""
    resp = get("/stocks/search", q="META")
    assert resp.status_code == 200, "search answered %d" % resp.status_code
    results = resp.json()
    if isinstance(results, dict):
        results = results.get("quotes") or results.get("results") or []
    by_id = {r["security_id"]: r for r in results if r.get("symbol") == "META"}

    assert NMS_ID in by_id and NEO_ID in by_id, (
        "search returned META securities %s, expected both %d and %d"
        % (sorted(by_id), NMS_ID, NEO_ID))

    nms, neo = by_id[NMS_ID], by_id[NEO_ID]
    assert (nms["exchange"], nms["kind"], nms["provider_symbol"], nms["currency"]) == (
        "NMS", "COMMON", "META", "USD"), nms
    assert (neo["exchange"], neo["kind"], neo["provider_symbol"], neo["currency"]) == (
        "NEO", "CDR", "META.NE", "CAD"), neo
    assert nms["provider_symbol"] != neo["provider_symbol"], (
        "two listings must not collapse onto one provider symbol")


def test_structure_and_prices_keep_sibling_listings_independent():
    """AC-4 AC-5 AC-6 kind:positive data:listing-identity-2026-11-22 shape:duplicate_ticker_two_listings shape:cdr_with_ratio a watchlist holding both META listings returns two listing-keyed rows with independent prices"""
    created = _ensure_neo_item()
    try:
        stocks = _meta_rows(_stocks())
        by_sid = {r["securityId"]: r for r in stocks}
        assert {NMS_ID, NEO_ID}.issubset(by_sid), (
            "structure returned META securities %s" % sorted(by_sid))

        nms, neo = by_sid[NMS_ID], by_sid[NEO_ID]
        assert nms["exchange"] == "NMS" and nms["kind"] == "COMMON"
        assert neo["exchange"] == "NEO" and neo["kind"] == "CDR"
        assert neo["providerSymbol"] == "META.NE"
        assert nms["price"] is not None and neo["price"] is not None
        assert abs(nms["price"] - neo["price"]) > CENT, (
            "both META listings reported the same price %.2f" % nms["price"])

        resp = get("/watchlists/6/prices", page_size=50)
        assert resp.status_code == 200, "prices answered %d" % resp.status_code
        priced = {p["securityId"]: p for p in resp.json()["prices"]
                  if p.get("symbol") == "META"}
        assert {NMS_ID, NEO_ID}.issubset(priced), (
            "prices returned META securities %s" % sorted(priced))
        assert abs(priced[NMS_ID]["price"] - nms["price"]) <= CENT
        assert abs(priced[NEO_ID]["price"] - neo["price"]) <= CENT
    finally:
        if created:
            _delete_neo_item()


def test_quote_endpoint_is_listing_scoped():
    """AC-5 AC-8 kind:positive data:listing-identity-2026-11-22 shape:cdr_with_ratio shape:common_no_ratio shape:duplicate_ticker_two_listings quote lookups keep provider identity and the CDR ratio adjustment separate"""
    quotes = {}
    for sid in (NMS_ID, NEO_ID):
        resp = get("/stocks/META/quote", security_id=sid)
        assert resp.status_code == 200, "quote %d answered %d" % (sid, resp.status_code)
        quotes[sid] = resp.json()
        assert quotes[sid]["security_id"] == sid, (
            "quote for %d returned security_id %r" % (sid, quotes[sid]["security_id"]))

    nms, neo = quotes[NMS_ID], quotes[NEO_ID]
    assert (nms["exchange"], nms["kind"], nms["provider_symbol"]) == (
        "NMS", "COMMON", "META")
    assert (neo["exchange"], neo["kind"], neo["provider_symbol"]) == (
        "NEO", "CDR", "META.NE")
    assert abs(nms["price"] - neo["price"]) > CENT, (
        "listing-scoped quotes collapsed to one price")
    # The CDR ratio is 10, so an effective per-CDR price must be roughly an order
    # of magnitude below the US listing. A factor of 20 is deliberately loose
    # enough to survive real price drift while still failing on the original
    # defect, where the raw 29.64 native quote was served as the CDR price.
    assert neo["price"] < nms["price"] / 20.0, (
        "CDR price %.2f is not ratio-adjusted against the US listing %.2f"
        % (neo["price"], nms["price"]))


def test_missing_or_unknown_listing_identity_is_rejected():
    """AC-2 AC-4 kind:negative kind:boundary missing symbol, unknown security id and incomplete listing identity never create a watchlist row"""
    for label, payload in (
        ("missing symbol", {"watchlist_id": 6}),
        ("unknown security id", dict(NEO_ADD, security_id=999999)),
    ):
        before = {r.get("securityId") for r in _meta_rows(_stocks())}
        resp = session().post(_base() + "/watchlist-items", json=payload,
                              headers=CSRF, timeout=120)
        assert resp.status_code != 201, (
            "%s was accepted with HTTP 201: %s" % (label, resp.text[:200]))
        after = {r.get("securityId") for r in _meta_rows(_stocks())}
        assert before == after, "%s mutated the real watchlist" % label


def test_unauthenticated_requests_never_return_listing_data():
    """AC-5 AC-8 kind:abuse anonymous and forged callers cannot read listing-keyed prices or quotes"""
    for label, headers in (("anonymous", {}),
                           ("forged", {"Authorization": "Bearer not-a-jwt"})):
        for path, params in (("/watchlists/6/prices", {"page_size": 50}),
                             ("/stocks/META/quote", {"security_id": NEO_ID})):
            resp = requests.get(_base() + path, params=params, headers=headers, timeout=60)
            assert resp.status_code in (401, 403), (
                "%s %s answered %d instead of 401/403"
                % (label, path, resp.status_code))
            assert "securityId" not in resp.text and "provider_symbol" not in resp.text, (
                "%s %s leaked listing identity" % (label, path))


def test_duplicate_add_does_not_create_two_rows():
    """AC-6 AC-8 kind:idempotency adding the same CDR listing twice leaves exactly one listing-specific row"""
    created = _ensure_neo_item()
    try:
        resp = session().post(_base() + "/watchlist-items", json=NEO_ADD,
                              headers=CSRF, timeout=120)
        assert resp.status_code != 201, (
            "duplicate add was accepted with HTTP 201: %s" % resp.text[:200])
        rows = [r for r in _meta_rows(_stocks()) if r.get("securityId") == NEO_ID]
        assert len(rows) == 1, (
            "duplicate add left %d rows for security %d" % (len(rows), NEO_ID))
        assert rows[0]["exchange"] == "NEO" and rows[0]["kind"] == "CDR"
    finally:
        if created:
            _delete_neo_item()


def test_unselected_watchlist_is_unchanged_when_listing_added():
    """AC-6 AC-8 kind:regression adding a listing to one watchlist never changes another watchlist's listed identities"""
    before = sorted((r.get("securityId"), r.get("symbol"))
                    for r in _stocks(5))
    created = _ensure_neo_item()
    try:
        after = sorted((r.get("securityId"), r.get("symbol"))
                       for r in _stocks(5))
        assert after == before, (
            "adding to watchlist 6 changed the identities in watchlist 5")
    finally:
        if created:
            _delete_neo_item()


def test_search_handles_malformed_and_unicode_queries():
    """AC-6 kind:boundary malformed and non-Latin search text returns a clean result instead of crashing the catalog"""
    for query in ("SMETA=F", "MÉTA", "META" * 40, "  "):
        resp = get("/stocks/search", q=query)
        assert resp.status_code == 200, (
            "search %r answered %d: %s" % (query[:20], resp.status_code, resp.text[:200]))
        body = resp.json()
        assert isinstance(body, (list, dict)), "search %r returned a non-JSON body" % query[:20]
