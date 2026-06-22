# backend/application/services/dividend_dashboard_service.py
"""
Dividend Dashboard Service

Aggregates company-level dividend data at the portfolio level.
Reuses existing PortfolioRepository queries and DividendAnalysisService
outputs — never duplicates company-level dividend analysis logic.
"""

import logging
from shared.time_utils import now_utc, now_iso, parse_db_timestamp
from typing import Any, Dict, List, Optional
from collections import defaultdict

from infrastructure.repositories.portfolio_repository import PortfolioRepository

logger = logging.getLogger(__name__)


class DividendDashboardService:
    """Portfolio-level dividend dashboard aggregation.

    Every metric reuse strategy is documented in the design doc:
    ``docs/Dividends_Redesign_Feasibility.md`` §3.5 Reuse Traceability Matrix.
    """

    def __init__(
        self,
        portfolio_repo: Optional[PortfolioRepository] = None,
    ):
        self.repo = portfolio_repo or PortfolioRepository()

    # ── Public API ──────────────────────────────────────────────────────────

    def get_summary(self, account_ids: List[int]) -> Dict[str, Any]:
        """Compute portfolio-level dividend summary for the given accounts."""
        holdings = self.repo.get_holdings_with_companies(account_ids)
        if not holdings:
            return self._empty_summary()

        company_ids = [h["company_id"] for h in holdings if h.get("company_id")]

        # Fetch raw data in parallel-ish (sequential await-free calls)
        trailing_rows = self.repo.get_trailing_twelve_month_dividends(account_ids)
        dps_rows = self.repo.get_latest_regular_dps(company_ids) if company_ids else []
        metrics_rows = self.repo.get_dividend_metrics_for_companies(company_ids) if company_ids else []

        # ── Per-holding aggregations ────────────────────────────────────────
        trailing_by_symbol = defaultdict(float)
        currency_set = set()
        for r in trailing_rows:
            trailing_by_symbol[r["symbol"]] += float(r["amount"])
            if r.get("currency"):
                currency_set.add(r["currency"])

        dps_by_cid: Dict[int, float] = {
            r["company_id"]: float(r["dividend_amount"])
            for r in dps_rows if r.get("dividend_amount")
        }
        metrics_by_cid: Dict[int, Dict] = {
            r["company_id"]: r for r in metrics_rows
        }

        total_trailing = sum(trailing_by_symbol.values())
        total_forward = 0.0
        total_cost_dividend_payers = 0.0
        growth_values: List[tuple] = []  # (weight, value)
        safety_values: List[tuple] = []
        current_year = now_utc().year

        # Compute YTD from trailing rows filtered to current year
        ytd_by_symbol = defaultdict(float)
        for r in trailing_rows:
            pd = r.get("payment_date") or ""
            try:
                if isinstance(pd, str):
                    yr = int(pd[:4]) if len(pd) >= 4 else 0
                else:
                    yr = pd.year
                if yr == current_year:
                    ytd_by_symbol[r["symbol"]] += float(r["amount"])
            except (ValueError, AttributeError):
                pass
        total_ytd = sum(ytd_by_symbol.values())

        for h in holdings:
            symbol = h["symbol"]
            shares = float(h.get("quantity") or 0)
            cost = float(h.get("total_cost") or 0)
            cid = h.get("company_id")
            dps = dps_by_cid.get(cid, 0.0)
            fwd_income = shares * dps * 4  # quarterly × 4
            total_forward += fwd_income

            # Forward yield on cost — only for dividend payers
            if dps > 0 and cost > 0:
                total_cost_dividend_payers += cost

            # Weighted-average growth
            metrics = metrics_by_cid.get(cid) if cid else None
            if metrics and fwd_income > 0:
                gr = metrics.get("dividend_growth_rate_5yr")
                if gr is not None:
                    growth_values.append((fwd_income, float(gr)))

            # Weighted-average safety (read from composite_score in dividend_metrics,
            # which maps to DividendAnalysisService._compute_safety().composite_score)
            if cid and metrics:
                payout = metrics.get("cash_dividend_payout_ratio")
                if payout is not None and fwd_income > 0:
                    safety_values.append((fwd_income, max(0, 100 - float(payout))))

        # ── Compute summary aggregates ──────────────────────────────────────
        portfolio_growth_5yr = self._weighted_avg(growth_values)
        portfolio_safety = self._weighted_avg(safety_values)

        growth_coverage = (
            sum(w for w, _ in growth_values) / total_forward * 100
            if total_forward > 0 else 0.0
        )
        safety_coverage = (
            sum(w for w, _ in safety_values) / total_forward * 100
            if total_forward > 0 else 0.0
        )

        avg_monthly_trailing = round(total_trailing / 12, 2)
        avg_monthly_forward = round(total_forward / 12, 2)

        return {
            "trailing_12m_income": round(total_trailing, 2),
            "forward_annual_estimate": round(total_forward, 2),
            "ytd_dividends": round(total_ytd, 2),
            "forward_yield_on_cost": (
                round(total_forward / total_cost_dividend_payers * 100, 2)
                if total_cost_dividend_payers > 0 else None
            ),
            "avg_monthly_trailing": avg_monthly_trailing,
            "avg_monthly_forward": avg_monthly_forward,
            "portfolio_growth_5yr": {
                "value": round(portfolio_growth_5yr, 2) if portfolio_growth_5yr is not None else None,
                "coverage_pct": round(growth_coverage, 1),
            },
            "portfolio_safety": {
                "value": round(portfolio_safety, 2) if portfolio_safety is not None else None,
                "coverage_pct": round(safety_coverage, 1),
            },
            "goal_progress": {
                "monthly_income": avg_monthly_forward,
                "monthly_goal": None,
                "pct": 0.0,
            },
            "currency": "Mixed" if len(currency_set) > 1 else (next(iter(currency_set)) if currency_set else None),
            "currencies_mixed": len(currency_set) > 1,
            "last_updated": now_iso(),
        }

    def _trust_label(self, trust_score: float, status: str) -> str:
        """Map trust_score + status to a human-readable label."""
        if status == "provider_reported":
            if trust_score >= 0.90:
                return "Likely"
            elif trust_score >= 0.70:
                return "Estimate"
        return "Predicted"

    def _confidence_from_score(self, score: float) -> str:
        """Map any score (trust or confidence) to high/medium/low."""
        return "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"

    def get_upcoming(self, account_ids: List[int]) -> List[Dict[str, Any]]:
        """Get upcoming ex-dividend dates for held positions.
        
        Reads from upcoming_dividend_events (new table) — the dedicated
        forward-looking table.  Falls back to dividend_history for any
        company not yet populated in the new table (graceful migration).
        
        The upcoming_dividend_events table doesn't store dividend_amount
        (Phase 1 design decision).  DPS is backfilled from the latest
        regular payment in dividend_history so the card always shows
        an estimated income.
        """
        holdings = self.repo.get_holdings_with_companies(account_ids)
        if not holdings:
            return []

        cid_to_holding = {h["company_id"]: h for h in holdings if h.get("company_id")}
        company_ids = list(cid_to_holding.keys())

        # Fetch latest DPS for amount backfill
        dps_rows = self.repo.get_latest_regular_dps(company_ids) if company_ids else []
        dps_by_cid = {r["company_id"]: float(r["dividend_amount"]) for r in dps_rows if r.get("dividend_amount")}

        result = []

        # Primary source: upcoming_dividend_events table (batched)
        upcoming_events = self.repo.get_next_upcoming_events(company_ids) if company_ids else []
        seen_cids = {e["company_id"] for e in upcoming_events if e.get("company_id")}

        for event in upcoming_events:
            cid = event["company_id"]
            holding = cid_to_holding.get(cid)
            if not holding:
                continue
            shares = float(holding.get("quantity") or 0)
            ts = float(event.get("trust_score") or 0.50)
            ev_status = event.get("status", "predicted")
            dps = dps_by_cid.get(cid, 0.0)

            result.append({
                "symbol": holding["symbol"],
                "company_name": holding["company_name"],
                "ex_dividend_date": event["ex_dividend_date"],
                "amount_per_share": dps,
                "estimated_income": round(shares * dps, 2),
                "dividend_type": "regular",
                "confidence": self._confidence_from_score(ts),
                "trust_score": round(ts, 2),
                "trust_label": self._trust_label(ts, ev_status),
                "data_source": event.get("data_source", "predicted"),
                "event_type": "ex_date",
            })

        # Fallback: dividend_history for companies not yet in new table
        remaining_cids = [c for c in company_ids if c not in seen_cids]
        if remaining_cids:
            legacy = self.repo.get_upcoming_ex_dates(remaining_cids)
            for ex in legacy:
                cid = ex["company_id"]
                holding = cid_to_holding.get(cid)
                if not holding:
                    continue
                shares = float(holding.get("quantity") or 0)
                dps = float(ex.get("dividend_amount") or 0)
                cs = ex.get("confidence_score") or 0
                result.append({
                    "symbol": holding["symbol"],
                    "company_name": holding["company_name"],
                    "ex_dividend_date": ex["ex_dividend_date"],
                    "amount_per_share": dps,
                    "estimated_income": round(shares * dps, 2),
                    "dividend_type": ex.get("dividend_type", "regular"),
                    "confidence": self._confidence_from_score(cs),
                    "trust_score": round(float(cs), 2),
                    "trust_label": self._trust_label(float(cs), "provider_reported") if cs >= 0.7 else "Predicted",
                    "data_source": ex.get("data_source", "defeat_beta"),
                    "event_type": "ex_date",
                })

        return result

    def get_holdings(self, account_ids: List[int]) -> List[Dict[str, Any]]:
        """Get per-holding dividend data for the holdings table."""
        holdings = self.repo.get_holdings_with_companies(account_ids)
        if not holdings:
            return []

        company_ids = [h["company_id"] for h in holdings if h.get("company_id")]

        trailing_rows = self.repo.get_trailing_twelve_month_dividends(account_ids)
        dps_rows = self.repo.get_latest_regular_dps(company_ids) if company_ids else []
        metrics_rows = self.repo.get_dividend_metrics_for_companies(company_ids) if company_ids else []
        trailing_by_symbol = defaultdict(float)
        for r in trailing_rows:
            trailing_by_symbol[r["symbol"]] += float(r["amount"])

        dps_by_cid = {r["company_id"]: float(r["dividend_amount"]) for r in dps_rows if r.get("dividend_amount")}
        metrics_by_cid = {r["company_id"]: r for r in metrics_rows}

        # Upcoming events — batched single query to upcoming_dividend_events
        # with dividend_history as fallback for migration period
        upcoming_by_cid: Dict[int, Dict[str, Any]] = {}
        upcoming_events = self.repo.get_next_upcoming_events(company_ids) if company_ids else []
        seen_upcoming = {e["company_id"] for e in upcoming_events if e.get("company_id")}
        for event in upcoming_events:
            upcoming_by_cid[event["company_id"]] = event
        legacy_upcoming = self.repo.get_upcoming_ex_dates(
            [c for c in (company_ids or []) if c not in seen_upcoming]
        )
        for ex in legacy_upcoming:
            upcoming_by_cid[ex["company_id"]] = ex

        result = []
        for h in holdings:
            cid = h.get("company_id")
            symbol = h["symbol"]
            shares = float(h.get("quantity") or 0)
            cost = float(h.get("total_cost") or 0)
            dps = dps_by_cid.get(cid, 0.0)
            fwd_income = shares * dps * 4
            trailing = trailing_by_symbol.get(symbol, 0.0)
            metrics = metrics_by_cid.get(cid) if cid else None

            current_yield = None
            if dps and h.get("market_value") and float(h["market_value"]) > 0:
                current_yield = round(dps * 4 / float(h["market_value"]) * 100, 2)

            forward_yoc = round(fwd_income / cost * 100, 2) if dps > 0 and cost > 0 else None

            payout_ratio = None
            if metrics:
                pr = metrics.get("cash_dividend_payout_ratio")
                if pr is not None:
                    payout_ratio = round(float(pr), 2)

            increase_streak = None
            if metrics:
                streak = metrics.get("consecutive_years_paid")
                if streak is not None:
                    increase_streak = int(streak)

            safety_score = None
            if metrics:
                pr = metrics.get("cash_dividend_payout_ratio")
                if pr is not None:
                    safety_score = round(max(0, 100 - float(pr)), 1)

            next_event = None
            event = upcoming_by_cid.get(cid) if cid else None
            if event:
                ts = float(event.get("trust_score") or event.get("confidence_score") or 0)
                event_dps = float(event.get("dividend_amount") or 0)
                # New table has no dividend_amount — backfill from dps_by_cid
                if event_dps == 0:
                    event_dps = dps_by_cid.get(cid, 0.0)
                next_event = {
                    "symbol": symbol,
                    "company_name": h["company_name"],
                    "ex_dividend_date": event["ex_dividend_date"],
                    "amount_per_share": event_dps,
                    "estimated_income": round(shares * event_dps, 2),
                    "dividend_type": event.get("dividend_type", "regular"),
                    "confidence": self._confidence_from_score(ts),
                    "event_type": "ex_date",
                }

            result.append({
                "account_id": h.get("account_id"),
                "symbol": symbol,
                "company_name": h["company_name"],
                "sector": h.get("sector"),
                "quantity": shares,
                "market_value": float(h.get("market_value") or 0),
                "total_cost": cost,
                "forward_income": round(fwd_income, 2),
                "trailing_12m_income": round(trailing, 2),
                "current_yield": current_yield,
                "forward_yield_on_cost": forward_yoc,
                "payout_ratio": payout_ratio,
                "increase_streak": increase_streak,
                "safety_score": safety_score,
                "next_event": next_event,
            })

        return result

    def get_holding_detail(
        self, account_ids: List[int], symbol: str
    ) -> Dict[str, Any]:
        """Get detailed dividend data for a holding, merging across accounts."""
        holdings = self.repo.get_holdings_with_companies(account_ids)
        matching = [h for h in holdings if h["symbol"].upper() == symbol.upper()]

        if not matching:
            return {
                "symbol": symbol.upper(),
                "company_name": symbol.upper(),
                "sector": None,
                "income": {"trailing_12m": 0, "forward": 0, "ytd": 0, "yield_on_cost": None, "market_value": 0, "cost_basis": 0},
                "quality_metrics": None,
                "dividend_history": [],
                "annual_dividends_per_share": [],
                "cash_received_by_year": [],
                "recent_payments": [],
            }

        # Merge multi-account holdings for the same symbol
        total_shares = sum(float(h.get("quantity") or 0) for h in matching)
        total_cost = sum(float(h.get("total_cost") or 0) for h in matching)
        total_market_value = sum(float(h.get("current_value") or h.get("market_value") or 0) for h in matching)
        holding = matching[0]  # company info is the same

        company_ids = [holding["company_id"]] if holding.get("company_id") else []

        trailing_rows = self.repo.get_trailing_twelve_month_dividends(account_ids)
        dps_rows = self.repo.get_latest_regular_dps(company_ids) if company_ids else []
        metrics_rows = self.repo.get_dividend_metrics_for_companies(company_ids) if company_ids else []
        payments = self.repo.get_portfolio_dividends_for_symbol(account_ids, symbol)

        dps = dps_rows[0]["dividend_amount"] if dps_rows else 0.0
        fwd_income = total_shares * float(dps) * 4

        trailing = sum(
            float(r["amount"]) for r in trailing_rows if r["symbol"] == symbol.upper()
        )
        current_year = now_utc().year
        ytd = sum(
            float(r["amount"]) for r in trailing_rows
            if r["symbol"] == symbol.upper()
            and str(r.get("payment_date", "")).startswith(str(current_year))
        )

        yoc = round(fwd_income / total_cost * 100, 2) if dps > 0 and total_cost > 0 else None

        quality_metrics = None
        if metrics_rows and company_ids:
            m = metrics_rows[0]
            payout = m.get("cash_dividend_payout_ratio")
            growth = m.get("dividend_growth_rate_5yr")
            streak = m.get("consecutive_years_paid")
            current_yield_val = round(float(dps) * 4 / total_market_value * 100, 2) if dps > 0 and total_market_value > 0 else None
            quality_metrics = {
                "safety_score": round(max(0, 100 - float(payout)), 1) if payout is not None else None,
                "payout_ratio": round(float(payout), 2) if payout is not None else None,
                "growth_5yr": round(float(growth), 2) if growth is not None else None,
                "increase_streak": int(streak) if streak is not None else None,
                "current_yield": current_yield_val,
            }

        dividend_history = []
        annual_dividends_per_share = []
        if dps_rows:
            by_year: Dict[int, float] = {}
            for d in dps_rows:
                date_str = str(d.get("ex_dividend_date", ""))
                amount = float(d.get("dividend_amount") or 0)
                dividend_history.append({
                    "date": date_str,
                    "amount": amount,
                })
                year = int(date_str[:4]) if len(date_str) >= 4 else 0
                if year:
                    by_year[year] = by_year.get(year, 0) + amount
            annual_dividends_per_share = [
                {"year": y, "amount": round(a, 4)} for y, a in sorted(by_year.items())
            ]

        cash_received_by_year: Dict[int, float] = {}
        for p in payments:
            date_str = str(p.get("payment_date", ""))
            year = int(date_str[:4]) if len(date_str) >= 4 else 0
            if year:
                cash_received_by_year[year] = cash_received_by_year.get(year, 0) + float(p.get("amount") or 0)

        recent_payments = []
        for p in payments:
            recent_payments.append({
                "payment_date": str(p.get("payment_date", "")),
                "amount": float(p.get("amount") or 0),
                "shares_held": float(p.get("shares_held") or 0) if p.get("shares_held") else None,
            })

        return {
            "symbol": symbol.upper(),
            "company_name": holding["company_name"],
            "sector": holding.get("sector"),
            "income": {
                "trailing_12m": round(trailing, 2),
                "forward": round(fwd_income, 2),
                "ytd": round(ytd, 2),
                "yield_on_cost": yoc,
                "market_value": round(total_market_value, 2),
                "cost_basis": round(total_cost, 2),
            },
            "quality_metrics": quality_metrics,
            "dividend_history": dividend_history[:12],
            "annual_dividends_per_share": annual_dividends_per_share,
            "cash_received_by_year": [{"year": y, "amount": round(a, 2)} for y, a in sorted(cash_received_by_year.items())],
            "recent_payments": recent_payments,
        }

    # ── Private helpers ─────────────────────────────────────────────────────

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "trailing_12m_income": 0.0,
            "forward_annual_estimate": 0.0,
            "ytd_dividends": 0.0,
            "forward_yield_on_cost": None,
            "avg_monthly_trailing": 0.0,
            "avg_monthly_forward": 0.0,
            "portfolio_growth_5yr": {"value": None, "coverage_pct": 0.0},
            "portfolio_safety": {"value": None, "coverage_pct": 0.0},
            "goal_progress": {
                "monthly_income": 0.0,
                "monthly_goal": None,
                "pct": 0.0,
            },
            "currency": None,
            "currencies_mixed": False,
            "last_updated": now_iso(),
        }

    @staticmethod
    def _weighted_avg(values: List[tuple]) -> Optional[float]:
        """Compute weighted average from (weight, value) pairs."""
        if not values:
            return None
        total_weight = sum(w for w, _ in values)
        if total_weight == 0:
            return None
        return sum(w * v for w, v in values) / total_weight
