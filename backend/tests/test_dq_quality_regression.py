"""REG-006-DQ: a low-quality statement row must be quarantined per field, not dropped.

Observed symptom: `[DQ] ... Quality Score 0/100` rows were discarded wholesale,
their periods were recorded as gaps, and the gap-filler then substituted LOCF
synthetic values for data that was mostly correct. Only the fields that failed
validation should be nulled; every other real value must survive.
"""
from __future__ import annotations

from application.validators.financial_data_validator import (
    Severity,
    ValidationIssue,
    ValidationResult,
    quarantine_critical_fields,
)


def _result(*issues: ValidationIssue, score: int) -> ValidationResult:
    return ValidationResult(
        symbol="META",
        fiscal_year=2026,
        fiscal_quarter=1,
        statement_type="income",
        issues=list(issues),
        quality_score=score,
    )


def test_critical_field_is_quarantined_without_discarding_the_row():
    result = _result(
        ValidationIssue(
            severity=Severity.CRITICAL,
            field="revenue",
            message="Revenue must be positive (got $0)",
        ),
        score=75,
    )
    row = {"revenue": 0, "net_income": 5, "gross_profit": 3}

    cleaned = quarantine_critical_fields(row, result)

    assert cleaned["revenue"] is None
    assert cleaned["net_income"] == 5
    assert cleaned["gross_profit"] == 3
    assert row["revenue"] == 0, "the source row must not be mutated in place"


def test_zero_score_from_warnings_only_loses_no_fields():
    issues = [
        ValidationIssue(severity=Severity.WARNING, field=f"field_{i}", message="missing")
        for i in range(40)
    ]
    result = _result(*issues, score=0)
    row = {f"field_{i}": i for i in range(40)}
    row["revenue"] = 100

    cleaned = quarantine_critical_fields(row, result)

    assert cleaned == row, "warnings degrade quality but do not invalidate a field"


def test_identity_fields_are_never_quarantined():
    result = _result(
        ValidationIssue(severity=Severity.CRITICAL, field="company_id", message="bad"),
        score=75,
    )
    row = {"company_id": 145, "fiscal_year": 2026, "revenue": 100}

    cleaned = quarantine_critical_fields(row, result)

    assert cleaned["company_id"] == 145
    assert cleaned["fiscal_year"] == 2026
