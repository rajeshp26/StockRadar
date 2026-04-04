# backend/application/normalizers/statement_normalizer.py
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from domain.model_types import IncomeStatementRow, BalanceSheetRow, CashFlowRow


def _safe_decimal(x) -> Optional[Decimal]:
    if x is None:
        return None
    try:
        return x if isinstance(x, Decimal) else Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _safe_int(x) -> Optional[int]:
    if x is None:
        return None
    try:
        # Handles floats like 647482000.0 from DefeatBeta dumps
        return int(float(x))
    except Exception:
        return None


def normalize_period(fiscal_year: Optional[int], fiscal_quarter: Optional[int], period_end_date: Optional[date]) -> Tuple[Optional[int], Optional[int], Optional[date]]:
    """
    Canonical period rules:
      - Annual: fiscal_quarter must be None
      - Quarterly: fiscal_quarter 1..4
      - period_end_date must exist (if missing, caller must decide fallback behavior)
    """
    if fiscal_year is None:
        return None, None, period_end_date

    fq = fiscal_quarter
    if fq is not None and (fq < 1 or fq > 4):
        fq = None

    return int(fiscal_year), fq, period_end_date


def normalize_income_row(row: IncomeStatementRow) -> IncomeStatementRow:
    fy, fq, ped = normalize_period(row.fiscal_year, row.fiscal_quarter, row.period_end_date)

    return row.model_copy(update={
        "fiscal_year": fy or row.fiscal_year,
        "fiscal_quarter": fq,
        "period_end_date": ped or row.period_end_date,

        "revenue": _safe_decimal(row.revenue),
        "cost_of_goods_sold": _safe_decimal(row.cost_of_goods_sold),
        "gross_profit": _safe_decimal(row.gross_profit),
        "operating_expenses": _safe_decimal(row.operating_expenses),
        "rd_expenses": _safe_decimal(row.rd_expenses),
        "sga_expenses": _safe_decimal(row.sga_expenses),
        "operating_income": _safe_decimal(row.operating_income),
        "interest_expense": _safe_decimal(row.interest_expense),
        "tax_expense": _safe_decimal(row.tax_expense),
        "net_income": _safe_decimal(row.net_income),
        "ebitda": _safe_decimal(row.ebitda),

        "non_operating_income_expense": _safe_decimal(row.non_operating_income_expense),
        "pretax_income": _safe_decimal(row.pretax_income),
        "equity_in_earnings": _safe_decimal(row.equity_in_earnings),
        "minority_interest": _safe_decimal(row.minority_interest),
        "income_from_continuing_operations": _safe_decimal(row.income_from_continuing_operations),
        "discontinued_operations": _safe_decimal(row.discontinued_operations),
        "net_income_to_common": _safe_decimal(row.net_income_to_common),
        "preferred_dividends": _safe_decimal(row.preferred_dividends),
        "ebit": _safe_decimal(row.ebit),

        "eps_basic": _safe_decimal(row.eps_basic),
        "eps_diluted": _safe_decimal(row.eps_diluted),
        "shares_outstanding_basic": _safe_int(row.shares_outstanding_basic),
        "shares_outstanding_diluted": _safe_int(row.shares_outstanding_diluted),
        "interest_income": _safe_decimal(row.interest_income),
        "effective_tax_rate": _safe_decimal(row.effective_tax_rate),
        "total_unusual_items": _safe_decimal(row.total_unusual_items),
        "special_charges": _safe_decimal(row.special_charges),
        "currency": (row.currency or "USD"),
    })


def normalize_balance_row(row: BalanceSheetRow) -> BalanceSheetRow:
    fy, fq, ped = normalize_period(row.fiscal_year, row.fiscal_quarter, row.period_end_date)
    return row.model_copy(update={
        "fiscal_year": fy or row.fiscal_year,
        "fiscal_quarter": fq,
        "period_end_date": ped or row.period_end_date,
        "currency": (row.currency or "USD"),
        # BUG-05 FIX: sanitise all numeric fields, matching normalize_income_row()
        "total_assets":                 _safe_decimal(row.total_assets),
        "current_assets":               _safe_decimal(row.current_assets),
        "cash_and_cash_equivalents":    _safe_decimal(row.cash_and_cash_equivalents),
        "accounts_receivable":          _safe_decimal(row.accounts_receivable),
        "inventory":                    _safe_decimal(row.inventory),
        "property_plant_equipment_net": _safe_decimal(row.property_plant_equipment_net),
        "intangible_assets":            _safe_decimal(row.intangible_assets),
        "goodwill":                     _safe_decimal(row.goodwill),
        "total_liabilities":            _safe_decimal(row.total_liabilities),
        "current_liabilities":          _safe_decimal(row.current_liabilities),
        "accounts_payable":             _safe_decimal(row.accounts_payable),
        "short_term_debt":              _safe_decimal(row.short_term_debt),
        "long_term_debt":               _safe_decimal(row.long_term_debt),
        "total_debt":                   _safe_decimal(row.total_debt),
        "shareholders_equity":          _safe_decimal(row.shareholders_equity),
        "retained_earnings":            _safe_decimal(row.retained_earnings),
        "common_stock":                 _safe_decimal(row.common_stock),
        "long_term_investments":        _safe_decimal(row.long_term_investments),
        "other_non_current_assets":     _safe_decimal(row.other_non_current_assets),
        "other_current_liabilities":    _safe_decimal(row.other_current_liabilities),
        "minority_interest":            _safe_decimal(row.minority_interest),
        "total_liabilities_and_equity": _safe_decimal(row.total_liabilities_and_equity),
        "shares_outstanding":           _safe_int(row.shares_outstanding),
        "invested_capital":             _safe_decimal(row.invested_capital),
        # Phase 5 additions
        "capital_lease_obligations":    _safe_decimal(row.capital_lease_obligations),
        "total_non_current_liabilities": _safe_decimal(row.total_non_current_liabilities),
        "total_non_current_assets":     _safe_decimal(row.total_non_current_assets),
        "tangible_book_value":          _safe_decimal(row.tangible_book_value),
        "deferred_revenue_current":     _safe_decimal(row.deferred_revenue_current),
        "deferred_revenue_non_current": _safe_decimal(row.deferred_revenue_non_current),
        "other_current_assets":         _safe_decimal(row.other_current_assets),
    })


def normalize_cashflow_row(row: CashFlowRow) -> CashFlowRow:
    fy, fq, ped = normalize_period(row.fiscal_year, row.fiscal_quarter, row.period_end_date)
    return row.model_copy(update={
        "fiscal_year": fy or row.fiscal_year,
        "fiscal_quarter": fq,
        "period_end_date": ped or row.period_end_date,
        "currency": (row.currency or "USD"),
        "cash_from_operating_activities": _safe_decimal(row.cash_from_operating_activities),
        "net_income":                     _safe_decimal(row.net_income),
        "depreciation_amortization":      _safe_decimal(row.depreciation_amortization),
        "change_in_working_capital":      _safe_decimal(row.change_in_working_capital),
        "deferred_taxes":                 _safe_decimal(row.deferred_taxes),
        "stock_based_compensation":       _safe_decimal(row.stock_based_compensation),
        "capital_expenditures":           _safe_decimal(row.capital_expenditures),
        "acquisitions":                   _safe_decimal(row.acquisitions),
        "asset_sales":                    _safe_decimal(row.asset_sales),
        "investment_purchases":           _safe_decimal(row.investment_purchases),
        "cash_from_investing_activities": _safe_decimal(row.cash_from_investing_activities),
        "cash_from_financing_activities": _safe_decimal(row.cash_from_financing_activities),
        "debt_issued":                    _safe_decimal(row.debt_issued),
        "debt_repayment":                 _safe_decimal(row.debt_repayment),
        "dividends_paid":                 _safe_decimal(row.dividends_paid),
        "share_repurchases":              _safe_decimal(row.share_repurchases),
        "share_issuance":                 _safe_decimal(row.share_issuance),
        # Phase 5 additions
        "net_change_in_cash":         _safe_decimal(row.net_change_in_cash),
        "effect_of_fx_on_cash":       _safe_decimal(row.effect_of_fx_on_cash),
        "beginning_cash":             _safe_decimal(row.beginning_cash),
        "ending_cash":                _safe_decimal(row.ending_cash),
        "short_term_debt_net_change": _safe_decimal(row.short_term_debt_net_change),
        "asset_impairment_charge":    _safe_decimal(row.asset_impairment_charge),
        "free_cash_flow":             _safe_decimal(row.free_cash_flow),
    })