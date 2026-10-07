import logging
from datetime import UTC, datetime
from typing import Any

from config import settings
from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)


class PriceRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def _last_verified_close(self, company_id: int) -> float | None:
        """Latest close already in price_history; upstream rows pass the plausibility gate."""
        try:
            result = (
                self.client.table("price_history")
                .select("close_price")
                .eq("company_id", company_id)
                .order("price_date", desc=True)
                .limit(1)
                .execute()
            )
            rows = result.data or []
            if rows and rows[0].get("close_price") is not None:
                return float(rows[0]["close_price"])
        except Exception as e:
            logger.error(
                "Failed to fetch last verified close (company=%s): %s",
                company_id, e,
            )
        return None

    def get_company_exchanges(self, company_ids: list[int]) -> dict[int, str]:
        if not company_ids:
            return {}
        try:
            result = (
                self.client.table("companies")
                .select("company_id, exchange")
                .in_("company_id", company_ids)
                .execute()
            )
            return {
                row["company_id"]: (row.get("exchange") or "UNKNOWN")
                for row in (result.data or [])
            }
        except Exception as e:
            logger.error("Failed to fetch company exchanges: %s", e)
            return {}

    def get_price_source_preferences(
        self, company_ids: list[int]
    ) -> dict[tuple, str]:
        if not company_ids:
            return {}
        try:
            result = (
                self.client.table("price_source_preferences")
                .select("company_id, exchange, preferred_source")
                .in_("company_id", company_ids)
                .execute()
            )
            prefs: dict[tuple, str] = {}
            for row in result.data or []:
                prefs[(row["company_id"], row["exchange"])] = row["preferred_source"]
            return prefs
        except Exception as e:
            logger.error("Failed to fetch price source preferences: %s", e)
            return {}

    def upsert_price_source(
        self,
        company_id: int,
        exchange: str,
        price: float,
        source: str,
        currency: str = "USD",
        ttl_seconds: int = 300,
    ) -> None:
        # Root-cause guard: provider scale errors must never reach current_market_data.
        if getattr(settings, "ENABLE_PRICE_PLAUSIBILITY_GATE", True):
            max_ratio = float(getattr(settings, "MAX_PRICE_UP_RATIO", 100.0))
            anchor = self._last_verified_close(company_id)
            if anchor is not None and price > anchor * max_ratio:
                logger.warning(
                    "[PRICE-GATE] Rejecting current price %s for company_id=%s: exceeds last verified close %s x %s",
                    price, company_id, anchor, max_ratio,
                )
                try:
                    self.client.table("data_quality_events").insert({
                        "company_id": company_id,
                        "scope": "current_market_data",
                        "metric": "PRICE_PLAUSIBILITY_VIOLATION",
                        "severity": "high",
                        "message": (
                            f"Rejected current price {price} above last verified close "
                            f"{anchor} x {max_ratio:g} (provider scale error suspected)"
                        ),
                        "details": {
                            "anchor_price": anchor,
                            "max_ratio": max_ratio,
                            "rejected_price": price,
                        },
                    }).execute()
                except Exception as e:
                    logger.error(f"[PRICE-GATE] event ledger write failed for {company_id}: {e!s}")
                return

        try:
            self.client.table("current_market_data").upsert(
                {
                    "company_id": company_id,
                    "current_price": price,
                    "source": source,
                    "last_updated": datetime.now(UTC).isoformat(),
                },
                on_conflict="company_id",
            ).execute()
        except Exception as e:
            logger.error(
                "Failed to upsert current_market_data (company=%s): %s",
                company_id, e,
            )

    def get_all_active_holdings(self) -> list[dict[str, Any]]:
        try:
            result = (
                self.client.table("portfolio_holdings")
                .select(
                    "holding_id, account_id, company_id, symbol, quantity, "
                    "average_cost, total_cost, exchange_override"
                )
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error("Failed to fetch active holdings: %s", e)
            return []

    def get_all_active_symbols(self) -> list[dict[str, Any]]:
        """Returns ALL unique (company_id, symbol, exchange) that any user
        cares about — portfolio holdings AND watchlist items combined.

        Deduplicates by company_id so a stock in both is only returned once.
        """
        seen: dict[int, dict[str, Any]] = {}

        # 1) Portfolio holdings (existing path)
        holdings = self.get_all_active_holdings()
        for h in holdings:
            cid = h.get("company_id")
            if cid and cid not in seen:
                seen[cid] = {
                    "company_id": cid,
                    "symbol": h["symbol"],
                    "exchange_override": h.get("exchange_override") or "UNKNOWN",
                }


        # When exchange_override is NULL (defaulted to UNKNOWN above), fall back
        # to the company's canonical exchange from the companies table.
        missing_cids = [
            seen[cid]["company_id"]
            for cid in seen
            if seen[cid]["exchange_override"] == "UNKNOWN"
        ]
        if missing_cids:
            company_exchanges = self.get_company_exchanges(missing_cids)
            for cid in seen:
                if seen[cid]["exchange_override"] == "UNKNOWN" and cid in company_exchanges:
                    seen[cid]["exchange_override"] = company_exchanges[cid]

        # 2) Watchlist items (new path)
        try:
            wl_result = (
                self.client.table("watchlist_items")
                .select("company_id, companies(ticker_symbol, exchange)")
                .execute()
            )
            for row in (wl_result.data or []):
                cid = row.get("company_id")
                co = row.get("companies")
                if cid and co and cid not in seen:
                    seen[cid] = {
                        "company_id": cid,
                        "symbol": co["ticker_symbol"],
                        "exchange_override": co.get("exchange") or "UNKNOWN",
                    }
        except Exception as e:
            logger.error("Failed to fetch watchlist items for price refresh: %s", e)

        return list(seen.values())

    def get_holdings_for_accounts(self, account_ids: list[int]) -> list[dict[str, Any]]:
        if not account_ids:
            return []
        try:
            result = (
                self.client.table("portfolio_holdings")
                .select(
                    "holding_id, account_id, company_id, symbol, quantity, "
                    "average_cost, total_cost, exchange_override"
                )
                .in_("account_id", account_ids)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error("Failed to fetch holdings for accounts: %s", e)
            return []
