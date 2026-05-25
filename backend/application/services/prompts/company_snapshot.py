from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from infrastructure.repositories.valuation_repository import ValuationRepository

logger = logging.getLogger(__name__)


class CompanySnapshotBuilder:

    _METHODS = ["rule1", "dcf", "ddm_gordon", "owner_earnings", "residual_income"]

    def __init__(self, repo: ValuationRepository) -> None:
        self._repo = repo

    async def build(self, symbol: str) -> Dict[str, Any]:
        import asyncio

        ctx = await self._repo.get_company_context(symbol)
        company_id = ctx.get("company_id") if ctx else None

        if not company_id:
            logger.warning("[Snapshot] No company found for symbol=%s", symbol)
            return {"symbol": symbol, "error": "Company not found"}

        tasks = {
            "company_context": self._safe_fetch(self._repo.get_company_context(symbol)),
            "income_statements": self._safe_fetch(self._repo.get_income_statements_annual(company_id, limit=99)),
            "balance_sheet": self._safe_fetch(self._repo.get_balance_sheet_latest(company_id)),
            "income_statement": self._safe_fetch(self._repo.get_income_statement_latest(company_id)),
            "cash_flow": self._safe_fetch(self._repo.get_cash_flow_latest(company_id)),
            "company_summary": self._safe_fetch(self._repo.get_company_summary_latest(company_id)),
            "shares_history": self._safe_fetch(self._repo.get_shares_history(company_id)),
            "current_price": self._safe_fetch(self._repo.get_current_market_price(company_id)),
        }

        for method in self._METHODS:
            tasks[f"cached_{method}"] = self._safe_fetch(
                self._repo.get_last_output_snapshot(company_id, method)
            )

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        snapshot = {"symbol": symbol.upper()}
        for key, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logger.warning("[Snapshot] %s failed: %s", key, result)
                snapshot[key] = None
            else:
                snapshot[key] = result

        return snapshot

    @staticmethod
    async def _safe_fetch(coro):
        try:
            return await coro
        except Exception as e:
            return e

    @staticmethod
    def format_context(snapshot: Dict[str, Any]) -> str:
        if snapshot.get("error"):
            return ""

        lines: List[str] = []
        ctx = snapshot.get("company_context")
        if ctx:
            lines.append(f"Company: {snapshot.get('symbol', '?')}")
            lines.append(f"Sector: {ctx.get('sector', 'N/A')} | Industry: {ctx.get('industry', 'N/A')}")
            lines.append(f"Currency: {ctx.get('currency', 'USD')}")

        price = snapshot.get("current_price")
        if price is not None:
            lines.append(f"Current Market Price: {price:.2f}")

        summary = snapshot.get("company_summary")
        if summary:
            shares = summary.get("shares_outstanding")
            if shares is not None:
                lines.append(f"Shares Outstanding: {shares}")
            eps = summary.get("trailing_eps")
            if eps is not None:
                lines.append(f"Trailing EPS: {eps}")

        is_ = snapshot.get("income_statement")
        if is_:
            parts = [f"Latest Income (FY{is_.get('fiscal_year','?')})"]
            rev = is_.get("revenue")
            if rev is not None: parts.append(f"Revenue={rev}")
            ni = is_.get("net_income_to_common")
            if ni is not None: parts.append(f"Net Income={ni}")
            eps = is_.get("eps_diluted")
            if eps is not None: parts.append(f"EPS(diluted)={eps}")
            if len(parts) > 1:
                lines.append(" | ".join(parts))

        bs = snapshot.get("balance_sheet")
        if bs:
            parts = [f"Latest Balance Sheet (FY{bs.get('fiscal_year','?')})"]
            ta = bs.get("total_assets")
            if ta is not None: parts.append(f"Assets={ta}")
            td = bs.get("total_debt")
            if td is not None: parts.append(f"Debt={td}")
            eq = bs.get("shareholders_equity")
            if eq is not None: parts.append(f"Equity={eq}")
            ch = bs.get("cash_and_cash_equivalents")
            if ch is not None: parts.append(f"Cash={ch}")
            if len(parts) > 1:
                lines.append(" | ".join(parts))

        cf = snapshot.get("cash_flow")
        if cf:
            parts = [f"Latest Cash Flow (FY{cf.get('fiscal_year','?')})"]
            ocf = cf.get("cash_from_operating_activities")
            if ocf is not None: parts.append(f"Ops Cash Flow={ocf}")
            capex = cf.get("capital_expenditures")
            if capex is not None: parts.append(f"Capex={capex}")
            if len(parts) > 1:
                lines.append(" | ".join(parts))

        is_hist = snapshot.get("income_statements")
        if is_hist:
            for r in is_hist[:5]:
                y = r.get("fiscal_year", "?")
                parts = [f"FY{y}"]
                rev = r.get("revenue")
                if rev is not None: parts.append(f"Rev={rev}")
                ebit = r.get("ebit")
                if ebit is not None: parts.append(f"EBIT={ebit}")
                ni = r.get("net_income_to_common")
                if ni is not None: parts.append(f"NetInc={ni}")
                shares = r.get("shares_outstanding_diluted")
                if shares is not None: parts.append(f"Shares={shares}")
                if len(parts) > 1:
                    lines.append(" | ".join(parts))

        for method in ["rule1", "dcf", "ddm_gordon", "owner_earnings", "residual_income"]:
            snap = snapshot.get(f"cached_{method}")
            if snap and isinstance(snap, dict):
                iv = snap.get("intrinsicValue") or snap.get("intrinsic_value") or snap.get("stickerPrice")
                if iv is not None:
                    lines.append(f"Cached {method.upper()} intrinsic: {iv}")

        if not lines:
            return ""

        lines.insert(0, "=== COMPANY CONTEXT ===")
        lines.append("")
        return "\n".join(lines)
