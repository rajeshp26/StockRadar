import logging
from datetime import UTC, datetime
from typing import Any

from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)


class PriceRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

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
