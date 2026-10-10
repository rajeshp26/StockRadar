import sys

import pytest

sys.path.insert(0, '.')

from application.validators.financial_data_validator import (
    FinancialDataValidator,
    Severity,
)


def _income_row(**overrides):
    row = {
        "fiscal_year": 2024,
        "fiscal_quarter": 1,
        "revenue": 1_000_000,
        "gross_profit": 400_000,
        "operating_income": 200_000,
        "net_income": 100_000,
    }
    row.update(overrides)
    return row


class TestRevenuePlausibility:
    def test_revenue_zero_is_critical(self):
        result = FinancialDataValidator.validate_income_statement(
            _income_row(revenue=0), "AHT"
        )
        assert result.has_critical_issues()
        revenue_issues = [i for i in result.issues if i.field == "revenue"]
        assert len(revenue_issues) == 1
        assert revenue_issues[0].severity == Severity.CRITICAL

    def test_revenue_negative_is_critical(self):
        result = FinancialDataValidator.validate_income_statement(
            _income_row(revenue=-5_000), "SPRU"
        )
        assert result.has_critical_issues()
        revenue_issues = [i for i in result.issues if i.field == "revenue"]
        assert revenue_issues[0].severity == Severity.CRITICAL

    def test_revenue_positive_in_range_passes(self):
        result = FinancialDataValidator.validate_income_statement(
            _income_row(), "SPRU"
        )
        assert not result.has_critical_issues()
        assert not result.has_errors()

    def test_revenue_positive_but_out_of_range_stays_error(self):
        result = FinancialDataValidator.validate_income_statement(
            _income_row(revenue=50_000), "SPRU"
        )
        assert not result.has_critical_issues()
        revenue_issues = [i for i in result.issues if i.field == "revenue"]
        assert len(revenue_issues) == 1
        assert revenue_issues[0].severity == Severity.ERROR