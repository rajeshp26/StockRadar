"""Resolve provider search hits and add requests to one canonical listing.

This service is the boundary owner for listing identity. Search results and add
payloads carry the exact selected listing (symbol + exchange + kind + currency +
provider_symbol); this module resolves them against the security catalog so the
selected exchange is never reconstructed from a bare ticker.

Pure orchestration over the injected repository: no provider or I/O imports here.
"""
from __future__ import annotations

from typing import Any, Iterable

from domain.listing_identity import (
    ListingIdentityError,
    normalize_search_candidate,
    normalize_search_result,
    validate_add_payload,
)
from infrastructure.repositories.security_repository import SecurityRepository

IDENTITY_FIELDS = ("symbol", "exchange", "kind", "currency", "provider_symbol")


class SecurityCatalogService:
    def __init__(self, repo: SecurityRepository | None = None):
        self.repo = repo or SecurityRepository()

    def search_listings(self, raw_results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """Resolve raw provider hits to catalog-backed SecurityListing payloads.

        A hit that cannot be resolved to exactly one listing is dropped rather than
        silently returning a symbol-only result, because that is the defect this
        architecture removes.
        """
        resolved: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for raw in raw_results:
            # A single malformed provider hit (e.g. a futures symbol 'SMETA=F'
            # that fails symbol validation) must not suppress the valid listings
            # in the same batch. Drop it and keep resolving the rest.
            try:
                candidate = normalize_search_candidate(raw)
            except ListingIdentityError:
                continue
            security = self.repo.get_or_create_listing(candidate)
            if not security:
                continue
            payload = normalize_search_result(
                {**candidate, "security_id": security["security_id"]}
            )
            key = tuple(payload[field] for field in IDENTITY_FIELDS)
            if key in seen:
                continue
            seen.add(key)
            resolved.append(payload)
        return resolved

    def catalog_listings_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """Return every catalog listing for an exact ticker in API-001 shape.

        Provider typeahead usually returns just one listing per ticker (the primary
        exchange). Alternate tradable rows such as META/NEO CDR live in the catalog
        but not in the provider's search feed; surfacing them here keeps them
        selectable so one user can watch both META/NMS and META/NEO.
        """
        lister = getattr(self.repo, "list_securities_for_symbol", None)
        if lister is None:
            return []
        results: list[dict[str, Any]] = []
        for row in lister(symbol):
            payload: dict[str, Any] = {
                "security_id": row["security_id"],
                "symbol": row["symbol"],
                "exchange": row["exchange"],
                "kind": row["kind"],
                "currency": row["currency"],
                "provider_symbol": row["provider_symbol"],
            }
            if row.get("company_name"):
                payload["name"] = row["company_name"]
            try:
                results.append(normalize_search_result(payload))
            except ListingIdentityError:
                continue
        return results

    def search_all(
        self, raw_results: Iterable[dict[str, Any]], symbol: str
    ) -> list[dict[str, Any]]:
        """Provider hits first, then exact-symbol catalog listings, deduplicated."""
        merged: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for payload in self.search_listings(raw_results) + self.catalog_listings_for_symbol(symbol):
            key = tuple(payload[field] for field in IDENTITY_FIELDS)
            if key in seen:
                continue
            seen.add(key)
            merged.append(payload)
        return merged

    def resolve_add(self, payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Validate an add request and return (canonical_payload, catalog_security).

        The submitted identity is cross-checked against the catalog row so a caller
        cannot pair a valid security_id with a different exchange/symbol.
        """
        validated = validate_add_payload(payload)
        security = self.repo.get_by_id(validated["security_id"])
        if not security:
            raise ListingIdentityError("Unknown security_id", ["security_id"])
        mismatches = [
            field for field in IDENTITY_FIELDS
            if str(security.get(field, "")).upper() != str(validated[field]).upper()
        ]
        if mismatches:
            raise ListingIdentityError(
                "Submitted listing identity does not match security_id",
                sorted(mismatches),
            )
        return validated, security
