import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from database import supabase
from supabase import Client

logger = logging.getLogger(__name__)


class PriceRepository:
    def __init__(self, client: Client = supabase):
        self.client = client

    def get_company_exchanges(self, company_ids: List[int]) -> Dict[int, str]:
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
        self, company_ids: List[int]
    ) -> Dict[tuple, str]:
        if not company_ids:
            return {}
        try:
            result = (
                self.client.table("price_source_preferences")
                .select("company_id, exchange, preferred_source")
                .in_("company_id", company_ids)
                .execute()
            )
            prefs: Dict[tuple, str] = {}
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
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="company_id",
            ).execute()
        except Exception as e:
            logger.error(
                "Failed to upsert current_market_data (company=%s): %s",
                company_id, e,
            )

    def get_all_active_holdings(self) -> List[Dict[str, Any]]:
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

    def get_holdings_for_accounts(self, account_ids: List[int]) -> List[Dict[str, Any]]:
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
