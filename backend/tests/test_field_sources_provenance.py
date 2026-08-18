"""
Unit tests for per-field provenance tracking (field_sources).

Covers:
  - _build_field_sources helper on DefeatBetaProvider
  - Domain models accepting field_sources parameter
  - Validator carrying field_sources through ValidationResult
  - Backward compatibility when field_sources is None
"""
import sys
sys.path.insert(0, '.')

from decimal import Decimal
from domain.model_types import (
    IncomeStatementRow, BalanceSheetRow, CashFlowRow,
)
from application.validators.financial_data_validator import (
    FinancialDataValidator, ValidationResult, Severity,
)


# ============================================================================
# _build_field_sources tests
# ============================================================================

class TestBuildFieldSources:
    """Tests for DefeatBetaProvider._build_field_sources static method."""

    def setup_method(self):
        from providers.defeat_beta_provider import DefeatBetaProvider
        self.build = DefeatBetaProvider._build_field_sources

    def test_non_null_fields_tagged(self):
        result = self.build(
            {"revenue": Decimal("1000"), "gross_profit": Decimal("500"), "net_income": None},
            "defeat_beta",
        )
        assert result == {"revenue": ["defeat_beta"], "gross_profit": ["defeat_beta"]}

    def test_all_none_returns_empty(self):
        result = self.build({"revenue": None, "net_income": None}, "yfinance")
        assert result == {}

    def test_stockdex_source(self):
        result = self.build({"revenue": Decimal("2000")}, "stockdex")
        assert result == {"revenue": ["stockdex"]}

    def test_edgar_source(self):
        result = self.build({"total_assets": Decimal("999")}, "edgar")
        assert result == {"total_assets": ["edgar"]}

    def test_empty_dict(self):
        result = self.build({}, "defeat_beta")
        assert result == {}

    def test_numeric_zero_is_non_null(self):
        result = self.build({"revenue": 0}, "defeat_beta")
        assert result == {"revenue": ["defeat_beta"]}

    def test_float_zero_is_non_null(self):
        result = self.build({"revenue": 0.0}, "defeat_beta")
        assert result == {"revenue": ["defeat_beta"]}


# ============================================================================
# Domain model field_sources tests
# ============================================================================

class TestDomainModelFieldSources:
    """Tests that domain models accept field_sources correctly."""

    def _make_kwargs(self):
        return {"company_id": 1, "fiscal_year": 2025, "fiscal_quarter": 1, "period_end_date": "2025-03-31"}

    def test_income_statement_with_field_sources(self):
        fs = {"revenue": ["defeat_beta"], "gross_profit": ["stockdex"]}
        row = IncomeStatementRow(**self._make_kwargs(), revenue=1000, field_sources=fs)
        assert row.field_sources == fs

    def test_income_statement_without_field_sources(self):
        row = IncomeStatementRow(**self._make_kwargs(), revenue=1000)
        assert row.field_sources is None

    def test_balance_sheet_with_field_sources(self):
        fs = {"total_assets": ["stockdex"], "current_assets": []}
        row = BalanceSheetRow(**self._make_kwargs(), total_assets=5000, field_sources=fs)
        assert row.field_sources == fs

    def test_balance_sheet_without_field_sources(self):
        row = BalanceSheetRow(**self._make_kwargs(), total_assets=5000)
        assert row.field_sources is None

    def test_cash_flow_with_field_sources(self):
        fs = {"cash_from_operating_activities": ["yfinance"]}
        row = CashFlowRow(**self._make_kwargs(), field_sources=fs)
        assert row.field_sources == fs

    def test_cash_flow_without_field_sources(self):
        row = CashFlowRow(**self._make_kwargs())
        assert row.field_sources is None

    def test_model_dump_includes_field_sources(self):
        fs = {"revenue": ["defeat_beta"]}
        row = IncomeStatementRow(**self._make_kwargs(), revenue=1000, field_sources=fs)
        d = row.model_dump()
        assert "field_sources" in d
        assert d["field_sources"] == fs

    def test_model_dump_none_field_sources(self):
        row = IncomeStatementRow(**self._make_kwargs(), revenue=1000)
        d = row.model_dump()
        assert d["field_sources"] is None


# ============================================================================
# Validator field_sources tests
# ============================================================================

class TestValidatorFieldSources:
    """Tests that validator carries field_sources through ValidationResult."""

    def _base_row(self, **overrides):
        base = {
            "fiscal_year": 2025, "fiscal_quarter": 1,
            "revenue": 10000, "gross_profit": 5000,
            "operating_income": 2000, "net_income": 1000,
        }
        base.update(overrides)
        return base

    def test_income_validator_carries_field_sources(self):
        fs = {"revenue": ["defeat_beta"], "gross_profit": ["stockdex"]}
        row = self._base_row(field_sources=fs)
        result = FinancialDataValidator.validate_income_statement(row, "TD.TO")
        assert result.field_sources == fs

    def test_income_validator_without_field_sources(self):
        row = self._base_row()
        result = FinancialDataValidator.validate_income_statement(row, "TD.TO")
        assert result.field_sources is None

    def test_balance_validator_carries_field_sources(self):
        fs = {"total_assets": ["yfinance"], "total_liabilities": ["yfinance"]}
        row = {
            "fiscal_year": 2025, "fiscal_quarter": 1,
            "total_assets": 50000, "total_liabilities": 30000,
            "shareholders_equity": 20000, "field_sources": fs,
        }
        result = FinancialDataValidator.validate_balance_sheet(row, "RY.TO")
        assert result.field_sources == fs

    def test_cashflow_validator_carries_field_sources(self):
        fs = {"cash_from_operating_activities": ["stockdex"]}
        row = {
            "fiscal_year": 2025, "fiscal_quarter": 1,
            "cash_from_operating_activities": 5000,
            "cash_from_investing_activities": -1000,
            "cash_from_financing_activities": -2000,
            "field_sources": fs,
        }
        result = FinancialDataValidator.validate_cash_flow(row, "CM.TO")
        assert result.field_sources == fs

    def test_validation_result_backward_compat(self):
        result = ValidationResult(
            symbol="TD.TO", fiscal_year=2025, fiscal_quarter=1,
            statement_type="income", issues=[], quality_score=100,
        )
        assert result.field_sources is None
