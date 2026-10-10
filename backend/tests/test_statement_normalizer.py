from __future__ import annotations

from datetime import date
from decimal import Decimal

from application.normalizers.statement_normalizer import (
    _sign_normalised_capex,
    normalize_cashflow_row,
)
from domain.model_types import CashFlowRow


def test_sign_normalised_capex_positive_to_negative():
    assert _sign_normalised_capex(100.0) == Decimal("-100.0")
    assert _sign_normalised_capex(Decimal("50.5")) == Decimal("-50.5")


def test_sign_normalised_capex_negative_unchanged():
    assert _sign_normalised_capex(-100.0) == Decimal("-100.0")
    assert _sign_normalised_capex(Decimal("-50.5")) == Decimal("-50.5")


def test_sign_normalised_capex_none():
    assert _sign_normalised_capex(None) is None


def test_normalize_cashflow_row_capex_signed():
    row = CashFlowRow(
        company_id=1,
        symbol="AAPL",
        fiscal_year=2024,
        fiscal_quarter=4,
        period_end_date=date(2024, 9, 28),
        capital_expenditures=Decimal("10000"),
    )
    normalized = normalize_cashflow_row(row)
    assert normalized.capital_expenditures == Decimal("-10000")


def test_normalize_cashflow_row_capex_already_negative_signed():
    row = CashFlowRow(
        company_id=1,
        symbol="AAPL",
        fiscal_year=2024,
        fiscal_quarter=4,
        period_end_date=date(2024, 9, 28),
        capital_expenditures=Decimal("-5000"),
    )
    normalized = normalize_cashflow_row(row)
    assert normalized.capital_expenditures == Decimal("-5000")


def test_normalize_cashflow_row_capex_none_unchanged():
    row = CashFlowRow(
        company_id=1,
        symbol="AAPL",
        fiscal_year=2024,
        fiscal_quarter=4,
        period_end_date=date(2024, 9, 28),
        capital_expenditures=None,
    )
    normalized = normalize_cashflow_row(row)
    assert normalized.capital_expenditures is None