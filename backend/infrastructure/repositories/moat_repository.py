from __future__ import annotations

import logging
from typing import Any

from database import supabase
from shared.finance_math import safe_float

logger = logging.getLogger(__name__)


def _first(data: Any) -> dict[str, Any] | None:
    if not data:
        return None
    if isinstance(data, list) and len(data) > 0:
        return data[0]
    return None


class MoatRepository:
    def get_company_context(self, symbol: str) -> dict[str, Any] | None:
        try:
            resp = (
                supabase.table("companies")
                .select("company_id, currency, sector, industry, ticker_symbol")
                .eq("ticker_symbol", symbol.upper())
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_company_context failed for %s: %s", symbol, e)
            return None

    async def get_financial_ratios_history(
        self, company_id: int, years: int = 6
    ) -> list[dict[str, Any]]:
        try:
            resp = (
                supabase.table("financial_ratios")
                .select(
                    "fiscal_year, roic, roe, gross_margin, operating_margin, "
                    "net_margin, free_cash_flow, fcf_conversion, "
                    "debt_to_equity, interest_coverage, asset_turnover"
                )
                .eq("company_id", company_id)
                .order("fiscal_year", desc=True)
                .limit(years)
                .execute()
            )
            return sorted(resp.data or [], key=lambda x: x.get("fiscal_year") or 0)
        except Exception as e:
            logger.error("get_financial_ratios_history failed: %s", e)
            return []

    async def get_income_statements_annual(
        self, company_id: int, years: int = 6
    ) -> list[dict[str, Any]]:
        try:
            resp = (
                supabase.table("income_statements")
                .select(
                    "fiscal_year, revenue, cost_of_goods_sold, operating_income, "
                    "net_income, ebit, interest_expense, tax_expense, "
                    "shares_outstanding_diluted"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .order("fiscal_year", desc=True)
                .limit(years)
                .execute()
            )
            return sorted(resp.data or [], key=lambda x: x.get("fiscal_year") or 0)
        except Exception as e:
            logger.error("get_income_statements_annual failed: %s", e)
            return []

    async def get_balance_sheet_latest(self, company_id: int) -> dict[str, Any] | None:
        try:
            resp = (
                supabase.table("balance_sheets")
                .select(
                    "fiscal_year, total_assets, shareholders_equity, "
                    "total_debt, cash_and_cash_equivalents, "
                    "property_plant_equipment_net, goodwill, intangible_assets, "
                    "long_term_debt, short_term_debt, current_assets, current_liabilities"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_balance_sheet_latest failed: %s", e)
            return None

    async def get_cash_flow_latest(self, company_id: int) -> dict[str, Any] | None:
        try:
            resp = (
                supabase.table("cash_flow_statements")
                .select(
                    "fiscal_year, cash_from_operating_activities, "
                    "capital_expenditures, depreciation_amortization"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_cash_flow_latest failed: %s", e)
            return None

    async def get_company_summary_latest(self, company_id: int) -> dict[str, Any] | None:
        try:
            resp = (
                supabase.table("company_summary")
                .select(
                    "market_cap, enterprise_value, beta, shares_outstanding, "
                    "trailing_pe, forward_pe, trailing_eps, forward_eps, "
                    "enterprise_to_ebitda, enterprise_to_revenue, "
                    "peg_ratio, snapshot_date"
                )
                .eq("company_id", company_id)
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_company_summary_latest failed: %s", e)
            return None

    async def get_industry_multiples(
        self, sector: str, industry: str
    ) -> dict[str, Any] | None:
        if not sector or not industry:
            return None
        try:
            resp = (
                supabase.table("industry_multiples")
                .select(
                    "sector, industry, calculation_date, "
                    "avg_ev_ebitda, median_pe, avg_eps_growth, "
                    "avg_revenue_growth, avg_roic, avg_gross_margin, "
                    "sample_size"
                )
                .eq("sector", sector)
                .eq("industry", industry)
                .order("calculation_date", desc=True)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_industry_multiples failed: %s", e)
            return None

    async def upsert_moat_analysis(self, company_id: int, data: dict[str, Any]) -> bool:
        try:
            record = {**data, "company_id": company_id, "computed_at": "now()"}
            # Remove id if present to avoid conflict — company_id has a unique constraint
            record.pop("id", None)
            supabase.table("moat_analysis").upsert(
                record, on_conflict="company_id"
            ).execute()
            return True
        except Exception as e:
            logger.error("upsert_moat_analysis failed: %s", e)
            return False

    async def get_moat_analysis(self, company_id: int) -> dict[str, Any] | None:
        try:
            resp = (
                supabase.table("moat_analysis")
                .select("*")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_moat_analysis failed: %s", e)
            return None

    async def delete_moat_keyword_evidence(self, company_id: int) -> bool:
        try:
            supabase.table("moat_keyword_evidence").delete().eq(
                "company_id", company_id
            ).execute()
            return True
        except Exception as e:
            logger.error("delete_moat_keyword_evidence failed: %s", e)
            return False

    async def insert_moat_keyword_evidence(
        self, rows: list[dict[str, Any]]
    ) -> bool:
        if not rows:
            return True
        try:
            supabase.table("moat_keyword_evidence").insert(rows).execute()
            return True
        except Exception as e:
            logger.error("insert_moat_keyword_evidence failed: %s", e)
            return False

    async def get_moat_keyword_evidence(
        self, company_id: int
    ) -> list[dict[str, Any]]:
        try:
            resp = (
                supabase.table("moat_keyword_evidence")
                .select("*")
                .eq("company_id", company_id)
                .order("keyword_group", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error("get_moat_keyword_evidence failed: %s", e)
            return []

    async def upsert_moat_ai_narrative(
        self, company_id: int, data: dict[str, Any]
    ) -> bool:
        try:
            existing = (
                supabase.table("moat_ai_narratives")
                .select("id")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            record = {**data, "generated_at": "now()"}
            if existing.data:
                supabase.table("moat_ai_narratives").update(record).eq(
                    "company_id", company_id
                ).execute()
            else:
                supabase.table("moat_ai_narratives").insert(record).execute()
            return True
        except Exception as e:
            logger.error("upsert_moat_ai_narrative failed: %s", e)
            return False

    async def get_moat_ai_narrative(
        self, company_id: int
    ) -> dict[str, Any] | None:
        try:
            resp = (
                supabase.table("moat_ai_narratives")
                .select("*")
                .eq("company_id", company_id)
                .limit(1)
                .execute()
            )
            return _first(resp.data)
        except Exception as e:
            logger.error("get_moat_ai_narrative failed: %s", e)
            return None

    async def get_current_market_price(self, company_id: int) -> float | None:
        try:
            resp = (
                supabase.table("current_market_data")
                .select("current_price")
                .eq("company_id", company_id)
                .order("last_updated", desc=True)
                .limit(1)
                .execute()
            )
            row = _first(resp.data)
            if row:
                return safe_float(row.get("current_price"))
            return None
        except Exception as e:
            logger.error("get_current_market_price failed: %s", e)
            return None
