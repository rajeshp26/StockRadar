"""Security catalog and quote store repositories.

The security catalog is the authority for listing identity. Provider symbols and quotes are
always resolved through a security_id, never through a company_id or a bare ticker.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from database import supabase
from domain.listing_identity import listing_key

logger = logging.getLogger(__name__)

LISTING_CONFLICT = "symbol,exchange,kind,currency,provider_symbol"


class SecurityRepository:
    def __init__(self, client=None):
        self.client = client or supabase

    # ── Company/issuer lookup ────────────────────────────────────────────────
    def find_company_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        result = (
            self.client.table("companies")
            .select("company_id,ticker_symbol,exchange,currency,cdr_ratio,security_type")
            .eq("ticker_symbol", symbol)
            .order("company_id")
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def ensure_company(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Find the issuer row for a listing, creating a minimal one only when needed."""
        existing = self.find_company_for_symbol(candidate["symbol"])
        if existing:
            return existing
        payload = {
            "ticker_symbol": candidate["symbol"],
            "company_name": candidate.get("name") or candidate["symbol"],
            "exchange": candidate["exchange"],
            "currency": candidate["currency"],
            "security_type": "stock" if candidate["kind"] in ("COMMON", "CDR") else candidate["kind"].lower(),
        }
        result = self.client.table("companies").insert(payload).execute()
        if not result.data:
            raise RuntimeError(f"Failed to create issuer for {candidate['symbol']}")
        return result.data[0]

    # ── Security catalog ─────────────────────────────────────────────────────
    def get_by_id(self, security_id: int) -> dict[str, Any] | None:
        result = (
            self.client.table("securities")
            .select("*")
            .eq("security_id", security_id)
            .limit(1)
            .execute()
        )
        rows = result.data or []
        return rows[0] if rows else None

    def get_by_listing_key(self, candidate: dict[str, Any]) -> dict[str, Any] | None:
        query = self.client.table("securities").select("*")
        for field in ("symbol", "exchange", "kind", "currency", "provider_symbol"):
            query = query.eq(field, candidate[field])
        rows = (query.limit(1).execute()).data or []
        return rows[0] if rows else None

    def get_by_provider_symbol(self, provider_symbol: str) -> dict[str, Any] | None:
        rows = (
            self.client.table("securities")
            .select("*")
            .eq("provider_symbol", provider_symbol.upper())
            .limit(1)
            .execute()
        ).data or []
        return rows[0] if rows else None

    def list_securities_for_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """All listings that share a ticker (e.g. META/NMS and META/NEO CDR)."""
        rows = (
            self.client.table("securities")
            .select("*, companies(company_name)")
            .eq("symbol", symbol.upper())
            .order("security_id")
            .execute()
        ).data or []
        for row in rows:
            company = row.pop("companies", None)
            if isinstance(company, dict) and company.get("company_name"):
                row["company_name"] = company["company_name"]
        return rows

    def get_default_listing_for_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Resolve a bare ticker to its non-CDR listing (legacy fallback only).

        Prefer the direct/common listing so legacy callers keep the historical price
        semantics; a CDR must always be selected explicitly by security_id.
        """
        rows = (
            self.client.table("securities")
            .select("*")
            .eq("symbol", symbol.upper())
            .execute()
        ).data or []
        direct = [row for row in rows if row.get("kind") != "CDR"]
        pool = direct or rows
        return min(pool, key=lambda row: row["security_id"]) if pool else None

    def list_for_company(self, company_id: int) -> list[dict[str, Any]]:
        return (
            self.client.table("securities")
            .select("*")
            .eq("company_id", company_id)
            .order("security_id")
            .execute()
        ).data or []

    def get_or_create_listing(self, candidate: dict[str, Any]) -> dict[str, Any]:
        """Resolve a search candidate to exactly one security row, idempotently."""
        existing = self.get_by_listing_key(candidate)
        if existing:
            return existing

        company = self.ensure_company(candidate)
        payload: dict[str, Any] = {
            "company_id": company["company_id"],
            "symbol": candidate["symbol"],
            "exchange": candidate["exchange"],
            "kind": candidate["kind"],
            "currency": candidate["currency"],
            "provider_symbol": candidate["provider_symbol"],
            "provenance": "catalog_search",
        }
        if candidate["kind"] == "CDR":
            underlying = self.get_or_create_listing({
                "symbol": candidate["symbol"],
                "exchange": "NMS" if company.get("exchange", "").upper() in ("NMS", "NYQ", "") else company["exchange"],
                "kind": "COMMON",
                "currency": "USD",
                "provider_symbol": candidate["symbol"],
                "name": candidate.get("name", ""),
            })
            company = self.client.table("companies").select("*").eq(
                "company_id", company["company_id"]
            ).limit(1).execute().data[0]
            payload["company_id"] = company["company_id"]
            payload["underlying_security_id"] = underlying["security_id"]
            payload["cdr_ratio"] = company.get("cdr_ratio") or 10.0

        result = (
            self.client.table("securities")
            .upsert(payload, on_conflict=LISTING_CONFLICT)
            .execute()
        )
        if not result.data:
            raise RuntimeError(f"Failed to resolve listing {listing_key(candidate)}")
        return result.data[0]

    # ── Quotes ───────────────────────────────────────────────────────────────
    def get_quotes(self, security_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not security_ids:
            return {}
        rows = (
            self.client.table("quotes")
            .select("*")
            .in_("security_id", security_ids)
            .execute()
        ).data or []
        return {int(row["security_id"]): row for row in rows}

    def upsert_quote(self, security_id: int, quote: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "security_id": security_id,
            "current_price": quote.get("current_price"),
            "open_price": quote.get("open_price"),
            "high_price": quote.get("high_price"),
            "low_price": quote.get("low_price"),
            "close_price": quote.get("close_price"),
            "volume": quote.get("volume"),
            "market_state": quote.get("market_state"),
            "source": quote.get("source", "provider"),
            "is_stale": bool(quote.get("is_stale", False)),
            "last_updated": quote.get("last_updated") or datetime.now(timezone.utc).isoformat(),
        }
        result = self.client.table("quotes").upsert(payload, on_conflict="security_id").execute()
        if not result.data:
            raise RuntimeError(f"Failed to upsert quote for security {security_id}")
        return result.data[0]

    # ── Security-level holding lots ──────────────────────────────────────────
    def get_holding_lots(self, account_id: int) -> list[dict[str, Any]]:
        return (
            self.client.table("portfolio_holding_lots")
            .select("*,securities(*)")
            .eq("account_id", account_id)
            .execute()
        ).data or []
