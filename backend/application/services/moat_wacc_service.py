from __future__ import annotations
import logging
from typing import Optional

from shared.finance_math import compute_cost_of_equity, compute_wacc, safe_float
from infrastructure.repositories.moat_repository import MoatRepository

logger = logging.getLogger(__name__)

_DEFAULT_RISK_FREE_RATE = 0.045
_DEFAULT_EQUITY_RISK_PREMIUM = 0.055
_DEFAULT_COST_OF_DEBT = 0.05
_DEFAULT_TAX_RATE = 0.21


class MoatWaccService:
    def __init__(self, repo: MoatRepository) -> None:
        self._repo = repo

    async def compute_wacc(self, company_id: int) -> Optional[float]:
        bs = await self._repo.get_balance_sheet_latest(company_id)
        cs = await self._repo.get_company_summary_latest(company_id)

        beta = safe_float(cs.get("beta")) if cs else None
        market_cap = safe_float(cs.get("market_cap")) if cs else None

        total_debt = safe_float(bs.get("total_debt")) if bs else None
        shareholders_equity = safe_float(bs.get("shareholders_equity")) if bs else None

        if beta is None:
            logger.info("Beta unavailable for company_id=%d, using default=1.0", company_id)
            beta = 1.0

        equity_value = market_cap
        if equity_value is None and shareholders_equity is not None:
            equity_value = shareholders_equity

        if equity_value is None or equity_value <= 0:
            logger.warning("Cannot determine equity value for company_id=%d", company_id)
            return None

        cost_of_equity = compute_cost_of_equity(
            risk_free_rate=_DEFAULT_RISK_FREE_RATE,
            beta=beta,
            equity_risk_premium=_DEFAULT_EQUITY_RISK_PREMIUM,
        )
        if cost_of_equity is None:
            return None

        wacc = compute_wacc(
            equity_value=equity_value,
            debt_value=total_debt,
            cost_of_equity=cost_of_equity,
            cost_of_debt=_DEFAULT_COST_OF_DEBT,
            tax_rate=_DEFAULT_TAX_RATE,
        )
        return wacc
