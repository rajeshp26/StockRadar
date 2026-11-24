"""Pure listing-identity rules.

A ticker alone is not an instrument. This module owns the canonical shape shared by
search, add, quote persistence, REST quotes and SSE events, so those boundaries cannot
silently disagree about what was selected.

Pure by design: no database, provider, framework or I/O imports. Contract tests exercise
this module directly; application layers call it at their boundaries.
"""
from __future__ import annotations

import re
from typing import Any, Final

KINDS: Final = ("COMMON", "CDR", "ETF", "FUND", "INDEX")

_EXCHANGE_ALIASES: Final[dict[str, str]] = {
    "TOR": "TSX",
    "TSX": "TSX",
    "TO": "TSX",
    "XTSE": "TSX",
    "T": "TSX",
    "NEO": "NEO",
    "NE": "NEO",
    "NMS": "NMS",
    "NAS": "NMS",
    "NASDAQ": "NMS",  # yfinance exchDisp display name -> canonical catalog code
    "NCM": "NMS",
    "NGM": "NMS",
    "NYQ": "NYQ",
    "NYS": "NYQ",
    "NYSE": "NYQ",
    "ASE": "ASE",
    "PCX": "PCX",
}

_PROVIDER_SUFFIX: Final[dict[str, str]] = {
    "TSX": ".TO",
    "NEO": ".NE",
    "TSXV": ".V",
}

_CAD_EXCHANGES: Final = frozenset({"TSX", "NEO", "TSXV"})

_KIND_HINTS: Final[tuple[tuple[str, str], ...]] = (
    ("depositary", "CDR"),
    ("cdr", "CDR"),
    ("etf", "ETF"),
    ("fund", "FUND"),
    ("index", "INDEX"),
)

_SYMBOL_RE: Final = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,19}$")

# Migration 020 appended an exchange suffix unconditionally, so seven already
# suffixed tickers were stored as ENB.TO.TO / YTSL.NE.NE / ... and Yahoo answered
# every refresh with 404. Only an *identical repeated* trailing suffix is a defect;
# genuine dotted tickers (BRK.B, ABC.TO) must survive untouched.
_REPEATED_PROVIDER_SUFFIX_RE: Final = re.compile(r"(\.TO|\.NE|\.V)\1+$", re.IGNORECASE)

_ADD_REQUIRED: Final = (
    "watchlist_id",
    "security_id",
    "symbol",
    "exchange",
    "kind",
    "currency",
    "provider_symbol",
)

_LISTING_FIELDS: Final = (
    "security_id",
    "symbol",
    "exchange",
    "kind",
    "currency",
    "provider_symbol",
)

_ADD_ALLOWED: Final = frozenset(_ADD_REQUIRED + ("target_buy", "target_sell"))


class ListingIdentityError(ValueError):
    """Contract-shaped validation failure raised at a boundary."""

    def __init__(self, message: str, fields: list[str], status_code: int = 422):
        super().__init__(message)
        self.message = message
        self.fields = fields
        self.status_code = status_code
        self.code = "INVALID_LISTING_IDENTITY"

    def as_payload(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "fields": self.fields}


def normalize_exchange(value: Any) -> str:
    raw = str(value or "").strip().upper()
    if not raw:
        raise ListingIdentityError("Exchange is required", ["exchange"])
    return _EXCHANGE_ALIASES.get(raw, raw)


def normalize_kind(value: Any) -> str:
    raw = str(value or "").strip().upper()
    aliases = {
        "STOCK": "COMMON",
        "EQUITY": "COMMON",
        "COMMON STOCK": "COMMON",
        "DEPOSITARY_RECEIPT": "CDR",
        "DEPOSITARY RECEIPT": "CDR",
        "MUTUALFUND": "FUND",
        "MUTUAL_FUND": "FUND",
    }
    raw = aliases.get(raw, raw)
    if raw not in KINDS:
        raise ListingIdentityError(
            f"Unsupported security kind {value!r}",
            ["kind"],
        )
    return raw


def normalize_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    if not _SYMBOL_RE.match(symbol):
        raise ListingIdentityError(
            "Symbol must be 1-20 uppercase letters, digits, dots or hyphens",
            ["symbol"],
        )
    return symbol


def normalize_provider_symbol(value: Any) -> str:
    """Return a provider ticker with a doubled exchange suffix collapsed once.

    Repairing the stored catalog rows is necessary but not sufficient: a reader of
    a stale row must still never emit an invalid ticker to the provider. This rule
    is idempotent and intentionally narrow - it only collapses a repeated *same*
    suffix at the end, so a legitimate dotted base symbol is never truncated.
    """
    symbol = str(value or "").strip().upper()
    match = _REPEATED_PROVIDER_SUFFIX_RE.search(symbol)
    if match:
        symbol = symbol[: match.start()] + match.group(1).upper()
    if not _SYMBOL_RE.match(symbol):
        raise ListingIdentityError(
            "Provider symbol must be 1-20 uppercase letters, digits, dots or hyphens",
            ["provider_symbol"],
        )
    return symbol


def _infer_kind(
    exchange: str,
    symbol: str,
    name: str,
    type_hint: str,
) -> str:
    haystack = f"{name} {type_hint}".lower()
    for needle, kind in _KIND_HINTS:
        if needle in haystack:
            return kind
    # A NEO-listed equity in this catalogue is a depositary receipt unless the source
    # explicitly named another kind. The exchange suffix alone preserves listing identity
    # even when the provider's display name omits "CDR".
    if exchange == "NEO" and symbol.upper().endswith(".NE"):
        return "CDR"
    return "COMMON"


def provider_symbol_for(symbol: str, exchange: str) -> str:
    if "." in symbol:
        return symbol
    return f"{symbol}{_PROVIDER_SUFFIX.get(exchange, '')}"


def currency_for(exchange: str) -> str:
    return "CAD" if exchange in _CAD_EXCHANGES else "USD"


def listing_key(identity: dict[str, Any]) -> str:
    """Stable natural key used by the migration and uniqueness invariant."""
    return "|".join(
        str(identity[field]).strip().upper()
        for field in ("symbol", "exchange", "kind", "currency", "provider_symbol")
    )


def normalize_search_candidate(result: dict[str, Any]) -> dict[str, Any]:
    """Turn one provider search hit into a catalog lookup key, before it has an id."""
    unknown = set(result) - {
        "security_id", "symbol", "name", "exchange", "type", "kind",
        "currency", "provider_symbol",
    }
    if unknown:
        raise ListingIdentityError("Unexpected search result fields", sorted(unknown))

    symbol = normalize_symbol(result.get("symbol"))
    exchange = normalize_exchange(result.get("exchange"))
    name = str(result.get("name") or "")
    type_hint = str(result.get("type") or "")
    kind = normalize_kind(result.get("kind") or _infer_kind(exchange, symbol, name, type_hint))
    provider_symbol = str(result.get("provider_symbol") or provider_symbol_for(symbol, exchange)).upper()
    currency = str(result.get("currency") or currency_for(exchange)).upper()

    payload: dict[str, Any] = {
        "symbol": symbol,
        "exchange": exchange,
        "kind": kind,
        "currency": currency,
        "provider_symbol": provider_symbol,
    }
    if name:
        payload["name"] = name
    return payload


def normalize_search_result(result: dict[str, Any]) -> dict[str, Any]:
    """Turn a catalog-resolved search hit into the API-001 SecurityListing shape."""
    candidate = normalize_search_candidate(result)
    if "security_id" not in result:
        raise ListingIdentityError(
            "Search result must carry the catalog security_id",
            ["security_id"],
        )
    security_id = result["security_id"]
    if not isinstance(security_id, int) or security_id <= 0:
        raise ListingIdentityError("Invalid security_id", ["security_id"])
    return {"security_id": security_id, **candidate}


def listing_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract only the six identity fields from a validated or stored payload."""
    missing = [field for field in _LISTING_FIELDS if field not in payload]
    if missing:
        raise ListingIdentityError("Listing identity is incomplete", missing)
    return {field: payload[field] for field in _LISTING_FIELDS}


def validate_add_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an API-001 add request and return its canonical form."""
    if not isinstance(payload, dict):
        raise ListingIdentityError("Request body must be an object", ["body"])

    errors: list[str] = []
    for field in _ADD_REQUIRED:
        if field not in payload or payload[field] in (None, ""):
            errors.append(field)
    unknown = sorted(set(payload) - _ADD_ALLOWED)
    errors.extend(unknown)
    if errors:
        raise ListingIdentityError("Listing identity is incomplete or undeclared", errors)

    normalized: dict[str, Any] = {}
    for field in ("watchlist_id", "security_id"):
        value = payload[field]
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            errors.append(field)
        else:
            normalized[field] = value

    try:
        normalized["symbol"] = normalize_symbol(payload["symbol"])
    except ListingIdentityError as exc:
        errors.extend(exc.fields)

    try:
        normalized["exchange"] = normalize_exchange(payload["exchange"])
    except ListingIdentityError as exc:
        errors.extend(exc.fields)

    try:
        normalized["kind"] = normalize_kind(payload["kind"])
    except ListingIdentityError as exc:
        errors.extend(exc.fields)

    currency = str(payload["currency"]).strip().upper()
    if len(currency) != 3:
        errors.append("currency")
    else:
        normalized["currency"] = currency

    provider_symbol = str(payload["provider_symbol"]).strip().upper()
    if not _SYMBOL_RE.match(provider_symbol):
        errors.append("provider_symbol")
    else:
        normalized["provider_symbol"] = provider_symbol

    for field in ("target_buy", "target_sell"):
        if field not in payload:
            continue
        value = payload[field]
        if value is None:
            normalized[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            errors.append(field)
        else:
            normalized[field] = float(value)

    if errors:
        raise ListingIdentityError("Invalid listing identity", sorted(set(errors)))
    return normalized


def build_quote_event(
    *,
    identity: dict[str, Any],
    price: float,
    last_updated: str,
    change: float | None = None,
    change_percent: float | None = None,
    source: str = "live",
    is_stale: bool = False,
) -> dict[str, Any]:
    """Build the SSE payload. Identity is required, never inferred from symbol alone."""
    base = listing_payload(identity)
    event: dict[str, Any] = {
        "type": "price_update",
        **base,
        "price": float(price),
        "lastUpdated": last_updated,
        "isStale": bool(is_stale),
        "source": source,
    }
    if change is not None:
        event["change"] = float(change)
    if change_percent is not None:
        event["changePercent"] = float(change_percent)
    return event
