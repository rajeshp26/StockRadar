# backend/infrastructure/repositories/fundamentals_repository.py
"""
Read-only repository for Fundamentals Tab data.

Provides 8 query methods that source from:
  - financial_ratios (pre-computed ratios, health scores)
  - income_statements / balance_sheets / cash_flow_statements (raw CAGR inputs)
  - companies (company metadata)
  - positions (buy anchor)

All methods are async, return plain dicts/lists, and raise on DB error.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database import supabase

logger = logging.getLogger(__name__)


class FundamentalsRepository:
    """Read-only data access for the Fundamentals tab."""

    async def get_company_by_symbol(self, symbol: str) -> Optional[Dict[str, Any]]:
        resp = (
            supabase.table("companies")
            .select("company_id, company_name, sector, industry, exchange, ticker_symbol")
            .ilike("ticker_symbol", symbol)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    async def get_annual_financial_ratios(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        """Return all annual ratios (fiscal_quarter IS NULL).

        Ordered by fiscal_year ascending so the frontend can render trends
        left-to-right (oldest → newest).
        """
        resp = (
            supabase.table("financial_ratios")
            .select("*")
            .eq("company_id", company_id)
            .is_("fiscal_quarter", None)
            .order("fiscal_year", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_quarterly_financial_ratios(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        """Return all quarterly ratios (fiscal_quarter IS NOT NULL).

        Ordered by fiscal_year + fiscal_quarter ascending.
        Used for health scores and trend charts.
        """
        resp = (
            supabase.table("financial_ratios")
            .select("*")
            .eq("company_id", company_id)
            .not_.is_("fiscal_quarter", "null")
            .order("fiscal_year", desc=False)
            .order("fiscal_quarter", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_annual_income_statements(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("income_statements")
            .select("fiscal_year, revenue, net_income, net_income_to_common, ebitda, period_end_date")
            .eq("company_id", company_id)
            .is_("fiscal_quarter", None)
            .order("fiscal_year", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_quarterly_income_statements(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("income_statements")
            .select("fiscal_year, fiscal_quarter, revenue, net_income, net_income_to_common, shares_outstanding_diluted, period_end_date")
            .eq("company_id", company_id)
            .not_.is_("fiscal_quarter", "null")
            .order("fiscal_year", desc=True)
            .order("fiscal_quarter", desc=True)
            .execute()
        )
        return resp.data or []

    async def get_annual_cash_flows(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("cash_flow_statements")
            .select("fiscal_year, cash_from_operating_activities, capital_expenditures, period_end_date")
            .eq("company_id", company_id)
            .is_("fiscal_quarter", None)
            .order("fiscal_year", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_quarterly_cash_flows(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("cash_flow_statements")
            .select("fiscal_year, fiscal_quarter, cash_from_operating_activities, capital_expenditures, period_end_date")
            .eq("company_id", company_id)
            .not_.is_("fiscal_quarter", "null")
            .order("fiscal_year", desc=True)
            .order("fiscal_quarter", desc=True)
            .execute()
        )
        return resp.data or []

    async def get_quarterly_balance_sheets(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        resp = (
            supabase.table("balance_sheets")
            .select("fiscal_year, fiscal_quarter, total_equity, total_debt, total_assets, retained_earnings, current_assets, current_liabilities")
            .eq("company_id", company_id)
            .not_.is_("fiscal_quarter", "null")
            .order("fiscal_year", desc=True)
            .order("fiscal_quarter", desc=True)
            .execute()
        )
        return resp.data or []

    async def get_company_name(self, company_id: int) -> Optional[str]:
        resp = (
            supabase.table("companies")
            .select("company_name")
            .eq("company_id", company_id)
            .execute()
        )
        rows = resp.data or []
        return rows[0]["company_name"] if rows else None

    async def is_held_in_portfolio(self, company_id: int, user_id: str) -> bool:
        """Check whether the user holds this company in any portfolio account.

        Uses `portfolio_holdings` (the derived holdings table) as the single
        source of truth, matching the tab bar's ``check_holding_exists``.
        """
        account_ids = await self._get_user_account_ids(user_id)
        if not account_ids:
            return False
        resp = (
            supabase.table("portfolio_holdings")
            .select("holding_id")
            .eq("company_id", company_id)
            .in_("account_id", account_ids)
            .limit(1)
            .execute()
        )
        return len(resp.data or []) > 0

    async def get_buy_anchor(self, company_id: int, user_id: str) -> Optional[Dict[str, Any]]:
        """Return the earliest purchase date + average cost for a held position.

        Sources from ``portfolio_holdings.first_purchase_date`` (the earliest
        BUY transaction across all of the user's accounts) and
        ``average_cost`` (FIFO-weighted cost per share).
        """
        account_ids = await self._get_user_account_ids(user_id)
        if not account_ids:
            return None
        resp = (
            supabase.table("portfolio_holdings")
            .select("first_purchase_date, average_cost")
            .eq("company_id", company_id)
            .in_("account_id", account_ids)
            .order("first_purchase_date", desc=False)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            return None
        row = rows[0]
        return {
            "transaction_date": row.get("first_purchase_date"),
            "unit_price": row.get("average_cost"),
        }

    async def _get_user_account_ids(self, user_id: str) -> List[int]:
        """Return all active account IDs for the given user."""
        resp = (
            supabase.table("portfolio_accounts")
            .select("account_id")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .execute()
        )
        return [a["account_id"] for a in (resp.data or [])]

    async def get_company_summary_history(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        """Get company_summary snapshots for valuation multiples (P/E, EV/EBITDA).

        Ordered by snapshot_date descending (most recent first).
        """
        resp = (
            supabase.table("company_summary")
            .select("snapshot_date, trailing_pe, forward_pe, enterprise_to_ebitda, enterprise_value, market_cap")
            .eq("company_id", company_id)
            .not_.is_("snapshot_date", None)
            .order("snapshot_date", desc=True)
            .execute()
        )
        return resp.data or []

    async def get_latest_valuation_overview(
        self, company_id: int
    ) -> Optional[Dict[str, Any]]:
        """Get the latest valuation_runs output_snapshot for a company.

        Returns the most recent run's overview data for Price vs Intrinsic comparison.
        """
        resp = (
            supabase.table("valuation_runs")
            .select("output_snapshot, run_at")
            .eq("company_id", company_id)
            .order("run_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0] if rows else None

    async def get_earnings_history(
        self, company_id: int
    ) -> List[Dict[str, Any]]:
        """Get all quarterly earnings data for surprise and beat-rate computation.

        Uses earnings table with eps_surprise_percent and revenue_surprise_percent columns.
        Ordered chronologically ascending for direct use by the service layer.
        """
        resp = (
            supabase.table("earnings")
            .select("fiscal_year, fiscal_quarter, eps_surprise_percent, revenue_surprise_percent, period_end_date")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=False)
            .order("fiscal_quarter", desc=False)
            .execute()
        )
        return resp.data or []

    async def get_current_market_price(self, company_id: int) -> Optional[float]:
        """Get the latest current_price from current_market_data."""
        resp = (
            supabase.table("current_market_data")
            .select("current_price")
            .eq("company_id", company_id)
            .order("last_updated", desc=True)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0]["current_price"] if rows else None

    async def get_retained_earnings(self, company_id: int, fiscal_year: int) -> Optional[float]:
        """Get retained_earnings for a specific fiscal year from balance_sheets."""
        resp = (
            supabase.table("balance_sheets")
            .select("retained_earnings")
            .eq("company_id", company_id)
            .eq("fiscal_year", fiscal_year)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        return rows[0].get("retained_earnings") if rows else None
