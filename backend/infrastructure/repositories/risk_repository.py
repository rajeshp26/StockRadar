from __future__ import annotations
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from database import supabase
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class RiskRepository:
    def __init__(self, repo: ValuationRepository) -> None:
        self._repo = repo

    async def get_company_context(self, symbol: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_company_context(symbol)

    async def get_latest_financial_ratios(self, company_id: int) -> Optional[Dict[str, Any]]:
        return await self._repo.get_derived_metrics_latest(company_id)

    async def get_financial_ratios_history(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        cutoff_year = date.today().year - years
        resp = (
            supabase.table("financial_ratios")
            .select("*")
            .eq("company_id", company_id)
            .gte("fiscal_year", cutoff_year)
            .order("fiscal_year", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_company_summary_history(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
        resp = (
            supabase.table("company_summary")
            .select("snapshot_date, trailing_pe, enterprise_to_ebitda, peg_ratio, beta, market_cap, enterprise_value")
            .eq("company_id", company_id)
            .not_.is_("trailing_pe", "null")
            .gte("snapshot_date", cutoff)
            .order("snapshot_date", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_income_statements_annual(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        return await self._repo.get_income_statements_annual(company_id, limit=years)

    async def get_cash_flow_latest(self, company_id: int) -> Optional[Dict[str, Any]]:
        return await self._repo.get_cash_flow_latest(company_id)

    async def get_price_history_range(
        self, company_id: int, years: int = 5
    ) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("price_history")
            .select("close_price, price_date")
            .eq("company_id", company_id)
            .order("price_date", desc=False)
            .execute()
        )
        rows = resp.data or []
        cutoff_date = (date.today() - timedelta(days=years * 365)).isoformat()
        return [r for r in rows if r.get("price_date", "") >= cutoff_date]

    async def get_current_market_price(self, company_id: int) -> Optional[float]:
        return await self._repo.get_current_market_price(company_id)

    async def upsert_risk_ai_narrative(self, company_id: int, payload: Dict[str, Any]) -> None:
        existing = (
            supabase.table("risk_ai_narratives")
            .select("id")
            .eq("company_id", company_id)
            .execute()
        )
        if existing.data:
            supabase.table("risk_ai_narratives").update(payload).eq("company_id", company_id).execute()
        else:
            supabase.table("risk_ai_narratives").insert(payload).execute()

    async def get_risk_ai_narrative(self, company_id: int) -> Optional[Dict[str, Any]]:
        resp = (
            supabase.table("risk_ai_narratives")
            .select("*")
            .eq("company_id", company_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None
