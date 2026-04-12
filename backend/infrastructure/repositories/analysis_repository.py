# backend/infrastructure/repositories/analysis_repository.py
"""
Read-only repository for Magic Formula, CANSlim, and Murphy Technical services.

Design:
  - Composes ValuationRepository (holds a reference, does not inherit).
  - Owns only queries not already exposed by ValuationRepository.
  - All methods are async, return None / [] on failure — callers never
    need to catch exceptions from these methods.
  - benchmark_config is the single source of truth for market proxies.
    Services never hardcode ticker symbols.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from database import supabase
from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class AnalysisRepository:
    def __init__(self, repo: ValuationRepository) -> None:
        self._repo = repo   # delegate — do not inherit

    # ── Benchmark resolution ──────────────────────────────────────────────────

    async def get_benchmark(self, role: str) -> Optional[Dict[str, Any]]:
        """
        Returns the active benchmark for a given role.
        Callers use role names ('us_market', 'us_tech') — never hardcode 'SPY'.

        Returns dict with keys: role, company_id, symbol, market, description.
        Returns None if the role is not configured or inactive.
        """
        try:
            resp = (
                supabase.table("benchmark_config")
                .select("role, company_id, symbol, market, description")
                .eq("role", role)
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error("get_benchmark failed for role=%s: %s", role, e)
            return None

    async def get_all_active_benchmarks(self, market: str = "US") -> List[Dict[str, Any]]:
        """Returns all active benchmarks for a market. Used for future multi-benchmark support."""
        try:
            resp = (
                supabase.table("benchmark_config")
                .select("role, company_id, symbol, market, description")
                .eq("market", market)
                .eq("is_active", True)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error("get_all_active_benchmarks failed for market=%s: %s", market, e)
            return []

    # ── Magic Formula ─────────────────────────────────────────────────────────

    async def get_ttm_ebit(self, company_id: int) -> Optional[float]:
        """
        Sums ebit from the 4 most recent quarterly income_statement rows.
        Falls back to the most recent annual row if fewer than 2 quarters available.
        Returns None only when no ebit data exists at all.
        """
        try:
            q_resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, ebit")
                .eq("company_id", company_id)
                .not_.is_("fiscal_quarter", "null")
                .not_.is_("ebit", "null")
                .order("fiscal_year", desc=True)
                .order("fiscal_quarter", desc=True)
                .limit(4)
                .execute()
            )
            rows = q_resp.data or []
            if len(rows) >= 2:
                total = sum(float(r["ebit"]) for r in rows)
                logger.debug(
                    "[MF] TTM EBIT from %d quarterly rows = %.2f, company_id=%d",
                    len(rows), total, company_id,
                )
                return total

            # Fallback to most recent annual row
            a_resp = (
                supabase.table("income_statements")
                .select("fiscal_year, ebit")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .not_.is_("ebit", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            a_rows = a_resp.data or []
            if a_rows:
                val = float(a_rows[0]["ebit"])
                logger.debug(
                    "[MF] TTM EBIT fallback to annual = %.2f, company_id=%d", val, company_id
                )
                return val

            return None
        except Exception as e:
            logger.error("get_ttm_ebit failed for company_id=%d: %s", company_id, e)
            return None

    async def get_enterprise_value_latest(self, company_id: int) -> Optional[float]:
        """Most recent enterprise_value from company_summary."""
        try:
            resp = (
                supabase.table("company_summary")
                .select("enterprise_value, snapshot_date")
                .eq("company_id", company_id)
                .not_.is_("enterprise_value", "null")
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            row = resp.data[0] if resp.data else None
            return float(row["enterprise_value"]) if row else None
        except Exception as e:
            logger.error("get_enterprise_value_latest failed for company_id=%d: %s", company_id, e)
            return None

    async def get_balance_sheet_mf_inputs(self, company_id: int) -> Optional[Dict[str, Any]]:
        """
        Fetches all fields needed for Greenblatt NWC and NFA computation.
        Uses most recent annual balance sheet row.

        NWC = (current_assets - cash_and_cash_equivalents) - (current_liabilities - short_term_debt)
        NFA = property_plant_equipment_net  [goodwill/intangibles excluded — already separate columns]
        """
        try:
            resp = (
                supabase.table("balance_sheets")
                .select(
                    "fiscal_year, "
                    "current_assets, cash_and_cash_equivalents, "
                    "current_liabilities, short_term_debt, "
                    "property_plant_equipment_net, "
                    "goodwill, intangible_assets, "
                    "total_assets"
                )
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .not_.is_("current_assets", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error("get_balance_sheet_mf_inputs failed for company_id=%d: %s", company_id, e)
            return None

    async def get_industry_multiples_full(
        self, sector: str, industry: str
    ) -> Optional[Dict[str, Any]]:
        """
        Wider select than ValuationRepository.get_industry_multiples().
        Includes ev/ebitda and revenue multiples needed for MF industry context panel.
        """
        if not sector or not industry:
            return None
        try:
            resp = (
                supabase.table("industry_multiples")
                .select(
                    "sector, industry, calculation_date, "
                    "avg_ev_ebitda, avg_ev_revenue, avg_ev_fcf, "
                    "median_pe, median_ev_ebitda, "
                    "avg_eps_growth, median_eps_growth, avg_revenue_growth, "
                    "sample_size"
                )
                .eq("sector", sector)
                .eq("industry", industry)
                .order("calculation_date", desc=True)
                .limit(1)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error(
                "get_industry_multiples_full failed sector=%s industry=%s: %s",
                sector, industry, e,
            )
            return None

    # ── CANSlim ───────────────────────────────────────────────────────────────

    async def get_quarterly_earnings_series(
        self, company_id: int, limit: int = 12
    ) -> List[Dict[str, Any]]:
        """
        Returns quarterly EPS data for CANSlim C criterion.
        Ordered newest-first so callers can index [0] = most recent quarter.

        YoY comparison: compare row where (fiscal_year, fiscal_quarter) == most recent
        against row where (fiscal_year - 1, same fiscal_quarter).
        """
        try:
            resp = (
                supabase.table("earnings")
                .select("fiscal_year, fiscal_quarter, eps_reported_diluted, period_end_date")
                .eq("company_id", company_id)
                .not_.is_("fiscal_quarter", "null")
                .not_.is_("eps_reported_diluted", "null")
                .order("fiscal_year", desc=True)
                .order("fiscal_quarter", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(
                "get_quarterly_earnings_series failed for company_id=%d: %s", company_id, e
            )
            return []

    async def get_quarterly_revenue_series(
        self, company_id: int, limit: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Revenue acceleration check for CANSlim C and N.
        Quarterly revenue, newest-first.
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, revenue, period_end_date")
                .eq("company_id", company_id)
                .not_.is_("fiscal_quarter", "null")
                .not_.is_("revenue", "null")
                .order("fiscal_year", desc=True)
                .order("fiscal_quarter", desc=True)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(
                "get_quarterly_revenue_series failed for company_id=%d: %s", company_id, e
            )
            return []

    async def get_price_history_monthly(
        self, company_id: int, months: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Monthly price history for CANSlim proxies.

        N — 52-week high: max(high_price or close_price) over last 12 months vs current.
        S — volume trend: recent 3-month avg volume vs prior 9-month avg.

        Uses the scheduler's stored monthly bars (intentional downsampling).
        Results are oldest-first for time-series calculations.
        """
        try:
            cutoff = (date.today() - timedelta(days=months * 31)).isoformat()
            resp = (
                supabase.table("price_history")
                .select("price_date, close_price, high_price, volume")
                .eq("company_id", company_id)
                .gte("price_date", cutoff)
                .order("price_date", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(
                "get_price_history_monthly failed for company_id=%d: %s", company_id, e
            )
            return []

    async def get_shares_outstanding_latest(self, company_id: int) -> Optional[float]:
        """
        Float size for CANSlim S — from most recent annual balance sheet.
        Falls back to company_summary if balance_sheets.shares_outstanding is NULL.
        """
        try:
            bs_resp = (
                supabase.table("balance_sheets")
                .select("shares_outstanding")
                .eq("company_id", company_id)
                .is_("fiscal_quarter", "null")
                .not_.is_("shares_outstanding", "null")
                .order("fiscal_year", desc=True)
                .limit(1)
                .execute()
            )
            if bs_resp.data:
                return float(bs_resp.data[0]["shares_outstanding"])

            cs_resp = (
                supabase.table("company_summary")
                .select("shares_outstanding")
                .eq("company_id", company_id)
                .not_.is_("shares_outstanding", "null")
                .order("snapshot_date", desc=True)
                .limit(1)
                .execute()
            )
            if cs_resp.data:
                return float(cs_resp.data[0]["shares_outstanding"])

            return None
        except Exception as e:
            logger.error(
                "get_shares_outstanding_latest failed for company_id=%d: %s", company_id, e
            )
            return None