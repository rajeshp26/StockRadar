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
from typing import Any

from database import supabase
from infrastructure.repositories.valuation_repository import ValuationRepository
from shared.time_utils import now_utc

logger = logging.getLogger(__name__)


class AnalysisRepository:
    def __init__(self, repo: ValuationRepository) -> None:
        self._repo = repo   # delegate — do not inherit

    # ── Benchmark resolution ──────────────────────────────────────────────────

    async def get_benchmark(self, role: str) -> dict[str, Any] | None:
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

    async def get_all_active_benchmarks(self, market: str = "US") -> list[dict[str, Any]]:
        """Returns all active benchmarks for a market."""
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

    async def get_benchmark_by_symbol(self, symbol: str) -> dict[str, Any] | None:
        """Looks up a benchmark config by symbol (e.g. 'SPY'). Returns None if not found."""
        try:
            resp = (
                supabase.table("benchmark_config")
                .select("role, company_id, symbol, market, description")
                .eq("symbol", symbol.upper())
                .eq("is_active", True)
                .limit(1)
                .execute()
            )
            return resp.data[0] if resp.data else None
        except Exception as e:
            logger.error("get_benchmark_by_symbol failed for symbol=%s: %s", symbol, e)
            return None

    async def list_active_benchmarks(self) -> list[dict[str, Any]]:
        """
        Returns ALL active benchmarks across all markets.
        Single source of truth for benchmark listing.
        No `name` column exists in benchmark_config — the frontend
        falls back to the symbol for display.
        """
        try:
            resp = (
                supabase.table("benchmark_config")
                .select("role, symbol, market, description")
                .eq("is_active", True)
                .order("symbol")
                .execute()
            )
            return [
                {
                    "role": r.get("role"),
                    "symbol": r.get("symbol"),
                    "name": r.get("name", r.get("symbol")),
                    "market": r.get("market", "US"),
                    "description": r.get("description"),
                }
                for r in (resp.data or [])
            ]
        except Exception as e:
            logger.error("list_active_benchmarks failed: %s", e)
            return []

    # ── Magic Formula ─────────────────────────────────────────────────────────

    async def get_ttm_ebit(self, company_id: int) -> float | None:
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

    async def get_enterprise_value_latest(self, company_id: int) -> float | None:
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

    async def get_balance_sheet_mf_inputs(self, company_id: int) -> dict[str, Any] | None:
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
    ) -> dict[str, Any] | None:
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

    async def get_quarterly_eps_from_income_statements(
        self, company_id: int, limit: int = 12
    ) -> list[dict[str, Any]]:
        """
        Returns quarterly EPS data for CANSLIM C criterion from income_statements table.

        This replaces get_quarterly_earnings_series() which queried the now-empty earnings table.
        Uses accounting EPS (net_income / shares_outstanding_diluted) from income_statements.

        Ordered newest-first so callers can index [0] = most recent quarter.
        YoY comparison: compare row where (fiscal_year, fiscal_quarter) == most recent
        against row where (fiscal_year - 1, same fiscal_quarter).
        """
        try:
            resp = (
                supabase.table("income_statements")
                .select("fiscal_year, fiscal_quarter, net_income, net_income_to_common, shares_outstanding_diluted, period_end_date")
                .eq("company_id", company_id)
                .not_.is_("fiscal_quarter", "null")
                .not_.is_("net_income", "null")
                .order("fiscal_year", desc=True)
                .order("fiscal_quarter", desc=True)
                .limit(limit)
                .execute()
            )

            if not resp.data:
                return []

            result = []
            for row in resp.data:
                net_income = row.get('net_income') or row.get('net_income_to_common')
                shares = row.get('shares_outstanding_diluted')

                # Calculate EPS if we have both values
                eps = None
                if net_income and shares and shares != 0:
                    try:
                        eps = float(net_income) / float(shares)
                    except (TypeError, ZeroDivisionError):
                        eps = None

                result.append({
                    'fiscal_year': row.get('fiscal_year'),
                    'fiscal_quarter': row.get('fiscal_quarter'),
                    'eps_reported_diluted': eps,
                    'period_end_date': row.get('period_end_date'),
                })

            return result

        except Exception as e:
            logger.error(
                "get_quarterly_eps_from_income_statements failed for company_id=%d: %s", company_id, e
            )
            return []

    # Keep old function name for backward compatibility but mark as deprecated
    async def get_quarterly_earnings_series(
        self, company_id: int, limit: int = 12
    ) -> list[dict[str, Any]]:
        """
        DEPRECATED - Use get_quarterly_eps_from_income_statements() instead.
        This function now redirects to income_statements for EPS data.
        """
        return await self.get_quarterly_eps_from_income_statements(company_id, limit)

    async def get_quarterly_revenue_series(
        self, company_id: int, limit: int = 8
    ) -> list[dict[str, Any]]:
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
    ) -> list[dict[str, Any]]:
        """
        Monthly price history for CANSlim proxies.

        N — 52-week high: max(high_price or close_price) over last 12 months vs current.
        S — volume trend: recent 3-month avg volume vs prior 9-month avg.

        Uses the scheduler's stored monthly bars (intentional downsampling).
        Results are oldest-first for time-series calculations.
        """
        try:
            cutoff = (now_utc().date() - timedelta(days=months * 31)).isoformat()
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

    async def get_shares_outstanding_latest(self, company_id: int) -> float | None:
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

    # ── Stock vs Index Comparison ─────────────────────────────────────────────

    async def get_price_history_range(
        self, company_id: int, start_date: date, end_date: date
    ) -> list[dict[str, Any]]:
        """Get daily/monthly price history for a date range."""
        try:
            resp = (
                supabase.table("price_history")
                .select("price_date, close_price, high_price, low_price, volume")
                .eq("company_id", company_id)
                .gte("price_date", start_date.isoformat())
                .lte("price_date", end_date.isoformat())
                .order("price_date", desc=False)
                .execute()
            )
            return resp.data or []
        except Exception as e:
            logger.error(
                f"get_price_history_range failed for company_id={company_id}: {e}"
            )
            return []

    async def get_revenue_and_eps_growth(
        self, company_id: int, years: int = 3
    ) -> dict[str, float | None]:
        """Calculate 3-year CAGR for revenue and EPS."""
        try:
            income_data = await self._repo.get_income_statements_annual(
                company_id, limit=years + 1
            )
            if len(income_data) < 2:
                return {"revenue_cagr": None, "eps_cagr": None}

            income_data = sorted(income_data, key=lambda x: x.get("fiscal_year", 0))

            # Revenue CAGR
            rev_start = income_data[0].get("revenue")
            rev_end = income_data[-1].get("revenue")
            revenue_cagr = None
            if rev_start and rev_end and float(rev_start) > 0:
                n_years = income_data[-1]["fiscal_year"] - income_data[0]["fiscal_year"]
                if n_years > 0:
                    revenue_cagr = (float(rev_end) / float(rev_start)) ** (
                        1 / n_years
                    ) - 1

            # EPS CAGR
            eps_start_ni = income_data[0].get("net_income_to_common") or income_data[
                0
            ].get("net_income")
            eps_start_shares = income_data[0].get("shares_outstanding_diluted")
            eps_end_ni = income_data[-1].get("net_income_to_common") or income_data[
                -1
            ].get("net_income")
            eps_end_shares = income_data[-1].get("shares_outstanding_diluted")

            eps_cagr = None
            if all([eps_start_ni, eps_start_shares, eps_end_ni, eps_end_shares]):
                if float(eps_start_shares) > 0 and float(eps_end_shares) > 0:
                    eps_start = float(eps_start_ni) / float(eps_start_shares)
                    eps_end = float(eps_end_ni) / float(eps_end_shares)
                    if eps_start > 0:
                        n_years = income_data[-1]["fiscal_year"] - income_data[0]["fiscal_year"]
                        if n_years > 0:
                            eps_cagr = (eps_end / eps_start) ** (1 / n_years) - 1

            return {"revenue_cagr": revenue_cagr, "eps_cagr": eps_cagr}
        except Exception as e:
            logger.error(f"get_revenue_and_eps_growth failed: {e}")
            return {"revenue_cagr": None, "eps_cagr": None}
