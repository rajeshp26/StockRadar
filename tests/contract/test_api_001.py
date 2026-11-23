"""Contract tests for API-001 (listing-specific watchlist identity).

Runs under pytest and standalone. These tests assert that the IMPLEMENTATION produces
instances accepted by the schema. They are the gate, not documentation.
"""
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()


def _find(relative: str) -> Path | None:
    for parent in _HERE.parents:
        candidate = parent / relative
        if candidate.exists():
            return parent
    return None


ROOT = _find("framework/contracts/validator.py")
if ROOT is None:
    raise SystemExit("cannot locate repository root from " + str(_HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from framework.contracts.validator import load_contract, validate_instance  # noqa: E402

try:
    from domain.listing_identity import (  # noqa: E402
        ListingIdentityError,
        build_quote_event,
        listing_payload,
        normalize_search_result,
        validate_add_payload,
    )
except ImportError as exc:  # RED phase: module is intentionally absent before implementation
    build_quote_event = None  # type: ignore[assignment]
    listing_payload = None  # type: ignore[assignment]
    normalize_search_result = None  # type: ignore[assignment]
    validate_add_payload = None  # type: ignore[assignment]
    ListingIdentityError = Exception  # type: ignore[assignment,misc]
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

SCHEMA = ROOT / ".planning/contracts/api-001.openapi.yaml"
CONTRACT = load_contract(SCHEMA)

VALID_ADD = {
    "watchlist_id": 11,
    "security_id": 145,
    "symbol": "META",
    "exchange": "NEO",
    "kind": "CDR",
    "currency": "CAD",
    "provider_symbol": "META.NE",
    "target_buy": 55.0,
    "target_sell": 75.0,
}


def _assert_schema(schema_name: str, payload: dict) -> None:
    schema = CONTRACT.doc["components"]["schemas"][schema_name]
    errors = validate_instance(payload, schema, CONTRACT.doc)
    assert not errors, f"{schema_name} violation: {errors}"


def test_implementation_module_is_importable():
    assert _IMPORT_ERROR is None, f"domain.listing_identity is missing: {_IMPORT_ERROR}"


def test_search_result_is_normalized_to_schema_shape():
    result = normalize_search_result({
        "security_id": 145,
        "symbol": "META",
        "name": "Meta Platforms CDR",
        "exchange": "NEO",
        "type": "equity",
    })
    _assert_schema("SecurityListing", result)
    assert result["kind"] == "CDR"
    assert result["provider_symbol"] == "META.NE"


def test_complete_add_payload_is_schema_valid():
    payload = validate_add_payload(dict(VALID_ADD))
    _assert_schema("AddWatchlistItemRequest", payload)


def test_missing_exchange_for_duplicate_ticker_is_rejected():
    bad = dict(VALID_ADD)
    bad.pop("exchange")
    try:
        validate_add_payload(bad)
    except ListingIdentityError as exc:
        assert "exchange" in exc.fields
        assert exc.status_code == 422
    else:
        raise AssertionError("symbol-only add payload was accepted")


def test_unknown_extra_field_is_rejected():
    bad = dict(VALID_ADD)
    bad["ticker"] = "META"
    try:
        validate_add_payload(bad)
    except ListingIdentityError as exc:
        assert "ticker" in exc.fields
    else:
        raise AssertionError("undeclared field was accepted")


def test_quote_event_carries_selected_listing_identity():
    identity = listing_payload(VALID_ADD)
    event = build_quote_event(
        identity=identity,
        price=60.7,
        change=0.35,
        change_percent=0.58,
        last_updated="2026-11-22T12:00:00Z",
        source="cached",
        is_stale=False,
    )
    _assert_schema("QuoteEvent", event)
    assert event["security_id"] == 145
    assert event["exchange"] == "NEO"
    assert event["provider_symbol"] == "META.NE"


TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failed = []
    for test in TESTS:
        try:
            test()
            print(f"  PASS  {test.__name__}")
        except Exception as exc:
            failed.append((test.__name__, repr(exc)))
            print(f"  FAIL  {test.__name__}: {exc!r}")
    print(f"\n{len(TESTS) - len(failed)}/{len(TESTS)} contract tests passed")
    sys.exit(1 if failed else 0)
