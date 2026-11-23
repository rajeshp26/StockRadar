"""
Financial Data Quality Validator
Matches super_investors validation pattern exactly.

Integration Points:
  1. DefeatBetaProvider._parse_*() methods - validate AFTER parsing, BEFORE returning
  2. FinancialRepository.upsert_*() methods - verify AFTER write (post-write verification)

Design:
  - Pre-write: field completeness, value ranges, logical consistency
  - Post-write: verify DB writes match expected values (like super_investors)
  - Severity levels: CRITICAL, ERROR, WARNING, INFO
  - Detailed logging with field-level issues
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Severity(Enum):
    """Validation issue severity levels"""
    CRITICAL = "CRITICAL"  # Missing required field - blocks save
    ERROR = "ERROR"        # Value out of range - degrades quality
    WARNING = "WARNING"    # Suspicious but valid - log only
    INFO = "INFO"          # Minor inconsistency


@dataclass
class ValidationIssue:
    """Single validation issue"""
    severity: Severity
    field: str
    message: str
    expected: Any | None = None
    actual: Any | None = None
    suggestion: str | None = None


@dataclass
class ValidationResult:
    """Validation result for a statement row"""
    symbol: str
    fiscal_year: int
    fiscal_quarter: int | None
    statement_type: str  # "income", "balance", "cashflow"
    issues: list[ValidationIssue]
    quality_score: int  # 0-100
    field_sources: dict[str, list[str]] | None = None

    def has_critical_issues(self) -> bool:
        return any(i.severity == Severity.CRITICAL for i in self.issues)

    def has_errors(self) -> bool:
        return any(i.severity in (Severity.CRITICAL, Severity.ERROR) for i in self.issues)

    def should_trigger_fallback(self) -> bool:
        """Should we try YFinance fallback?"""
        return self.has_critical_issues() or self.quality_score < 70


# ============================================================================
# FIELD REQUIREMENTS (extracted from your schema + DefeatBeta aliases)
# ============================================================================

# From your DB schema + DefeatBeta aliases, these are the ACTUAL required fields
INCOME_REQUIRED = {
    "revenue",
    "gross_profit",
    "operating_income",
    "net_income",
    "fiscal_year",
    "fiscal_quarter"  # Can be None for annual
}

BALANCE_REQUIRED = {
    "total_assets",
    "total_liabilities",
    "shareholders_equity",
    "fiscal_year",
    "fiscal_quarter"  # Can be None for annual
}

CASHFLOW_REQUIRED = {
    "cash_from_operating_activities",
    "cash_from_investing_activities",
    "cash_from_financing_activities",
    "fiscal_year",
    "fiscal_quarter"  # Can be None for annual
}

# Fields that are highly desirable but not strictly required
INCOME_IMPORTANT = {
    "cost_of_goods_sold",
    "operating_expenses",
    "ebitda",
    "eps_diluted",
    "shares_outstanding_diluted"
}

BALANCE_IMPORTANT = {
    "current_assets",
    "current_liabilities",
    "cash_and_cash_equivalents",
    "total_debt"
}

CASHFLOW_IMPORTANT = {
    "capital_expenditures",
    "depreciation_amortization"
}


# ============================================================================
# VALUE RANGES (based on your stock universe - large/mid cap)
# ============================================================================

# From your super_investors pattern: position_value < $1M is suspicious
# Scaling up for income statement (company-level vs position-level)
VALUE_RANGES = {
    # Income Statement
    "revenue": (100_000, 1_000_000_000_000),  # $100K to $1T (covers small caps to AAPL)
    "net_income": (-50_000_000_000, 500_000_000_000),  # -$50B to $500B (allows losses)
    "gross_profit": (0, 1_000_000_000_000),
    "operating_income": (-50_000_000_000, 500_000_000_000),
    "ebitda": (-50_000_000_000, 500_000_000_000),

    # Balance Sheet
    "total_assets": (100_000, 10_000_000_000_000),  # $100K to $10T
    "total_liabilities": (0, 10_000_000_000_000),
    "shareholders_equity": (-100_000_000_000, 5_000_000_000_000),  # Can be negative

    # Cash Flow
    "cash_from_operating_activities": (-50_000_000_000, 500_000_000_000),
    "capital_expenditures": (-500_000_000_000, 0),  # Always negative

    # Shares
    "shares_outstanding_diluted": (1_000_000, 100_000_000_000),  # 1M to 100B shares
}


# ============================================================================
# VALIDATOR
# ============================================================================

class FinancialDataValidator:
    """
    Validates financial data at provider layer.
    Matches super_investors validation pattern.
    """

    # ========================================================================
    # Income Statement Validation
    # ========================================================================

    @staticmethod
    def validate_income_statement(
        row: dict[str, Any],
        symbol: str,
    ) -> ValidationResult:
        """
        Validate income statement row BEFORE returning from provider.
        
        Args:
            row: Dict with income statement fields (from domain model or parsed dict)
            symbol: Ticker symbol for logging
            
        Returns:
            ValidationResult with issues and quality score
        """
        issues: list[ValidationIssue] = []
        fy = row.get("fiscal_year")
        fq = row.get("fiscal_quarter")

        # 1. REQUIRED FIELDS
        for field in INCOME_REQUIRED:
            if field == "fiscal_quarter" and fq is None:
                continue  # OK for annual
            if row.get(field) is None:
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    field=field,
                    message="Missing required field",
                    suggestion="Use YFinance fallback"
                ))

        # 2. IMPORTANT FIELDS (not critical but degrades quality)
        for field in INCOME_IMPORTANT:
            if row.get(field) is None:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    field=field,
                    message="Missing important field - quality degraded",
                ))

        # 3. VALUE RANGE VALIDATION
        revenue = _safe_float(row.get("revenue"))
        if revenue is not None:
            if revenue <= 0:
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    field="revenue",
                    message="Revenue must be positive (got $0) - treated as missing",
                    suggestion="Use YFinance fallback",
                    actual=f"${revenue:,.0f}"
                ))
            else:
                min_val, max_val = VALUE_RANGES["revenue"]
                if not (min_val <= revenue <= max_val):
                    issues.append(ValidationIssue(
                        severity=Severity.ERROR,
                        field="revenue",
                        message="Revenue out of expected range",
                        expected=f"${min_val:,} to ${max_val:,}",
                        actual=f"${revenue:,.0f}"
                    ))

        net_income = _safe_float(row.get("net_income"))
        if net_income is not None:
            min_val, max_val = VALUE_RANGES["net_income"]
            if not (min_val <= net_income <= max_val):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    field="net_income",
                    message="Net income out of expected range",
                    expected=f"${min_val:,} to ${max_val:,}",
                    actual=f"${net_income:,.0f}"
                ))

        # 4. LOGICAL CONSISTENCY (like super_investors checks)
        gross_profit = _safe_float(row.get("gross_profit"))
        if revenue and gross_profit:
            if gross_profit > revenue * 1.1:  # Allow 10% tolerance for rounding
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    field="gross_profit",
                    message="Gross profit exceeds revenue",
                    actual=f"GP: ${gross_profit:,.0f} > Rev: ${revenue:,.0f}"
                ))

        operating_income = _safe_float(row.get("operating_income"))
        if gross_profit and operating_income:
            if operating_income > gross_profit * 1.1:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    field="operating_income",
                    message="Operating income exceeds gross profit (unusual)",
                    actual=f"OI: ${operating_income:,.0f} > GP: ${gross_profit:,.0f}"
                ))

        # 5. SHARES REASONABLENESS
        shares = _safe_float(row.get("shares_outstanding_diluted"))
        if shares is not None:
            min_val, max_val = VALUE_RANGES["shares_outstanding_diluted"]
            if not (min_val <= shares <= max_val):
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    field="shares_outstanding_diluted",
                    message="Share count unusual",
                    actual=f"{shares:,.0f}",
                    suggestion="Verify not pre-split adjustment"
                ))

        quality_score = _calculate_quality_score(issues)
        field_sources = row.get("field_sources")

        return ValidationResult(
            symbol=symbol,
            fiscal_year=fy or 0,
            fiscal_quarter=fq,
            statement_type="income",
            issues=issues,
            quality_score=quality_score,
            field_sources=field_sources,
        )

    # ========================================================================
    # Balance Sheet Validation
    # ========================================================================

    @staticmethod
    def validate_balance_sheet(
        row: dict[str, Any],
        symbol: str,
    ) -> ValidationResult:
        """Validate balance sheet row BEFORE returning from provider."""
        issues: list[ValidationIssue] = []
        fy = row.get("fiscal_year")
        fq = row.get("fiscal_quarter")

        # 1. REQUIRED FIELDS
        for field in BALANCE_REQUIRED:
            if field == "fiscal_quarter" and fq is None:
                continue
            if row.get(field) is None:
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    field=field,
                    message="Missing required field",
                    suggestion="Use YFinance fallback"
                ))

        # 2. IMPORTANT FIELDS
        for field in BALANCE_IMPORTANT:
            if row.get(field) is None:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    field=field,
                    message="Missing important field",
                ))

        # 3. ACCOUNTING EQUATION: Assets = Liabilities + Equity (+ Minority Interest)
        #    US GAAP consolidations carry minority interest between liabilities and
        #    equity; omitting it flagged valid rows (e.g. DIS FY2022Q2 90/100).
        assets = _safe_float(row.get("total_assets"))
        liabilities = _safe_float(row.get("total_liabilities"))
        equity = _safe_float(row.get("shareholders_equity"))
        minority = _safe_float(row.get("minority_interest"))

        if all(v is not None for v in [assets, liabilities, equity]):
            expected_assets = liabilities + equity + (minority if minority is not None else 0)
            diff_pct = abs(assets - expected_assets) / assets if assets != 0 else 0

            if diff_pct > 0.02:  # >2% deviation is error
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    field="accounting_equation",
                    message="Balance sheet doesn't balance",
                    expected=f"Assets: ${expected_assets:,.0f}",
                    actual=f"Assets: ${assets:,.0f} (diff: {diff_pct:.2%})",
                    suggestion="Data quality issue - use YFinance fallback"
                ))

        # 4. VALUE RANGES
        if assets is not None:
            min_val, max_val = VALUE_RANGES["total_assets"]
            if not (min_val <= assets <= max_val):
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    field="total_assets",
                    message="Total assets out of expected range",
                    expected=f"${min_val:,} to ${max_val:,}",
                    actual=f"${assets:,.0f}"
                ))

        quality_score = _calculate_quality_score(issues)
        field_sources = row.get("field_sources")

        return ValidationResult(
            symbol=symbol,
            fiscal_year=fy or 0,
            fiscal_quarter=fq,
            statement_type="balance",
            issues=issues,
            quality_score=quality_score,
            field_sources=field_sources,
        )

    # ========================================================================
    # Cash Flow Validation
    # ========================================================================

    @staticmethod
    def validate_cash_flow(
        row: dict[str, Any],
        symbol: str,
    ) -> ValidationResult:
        """Validate cash flow row BEFORE returning from provider."""
        issues: list[ValidationIssue] = []
        fy = row.get("fiscal_year")
        fq = row.get("fiscal_quarter")

        # 1. REQUIRED FIELDS
        for field in CASHFLOW_REQUIRED:
            if field == "fiscal_quarter" and fq is None:
                continue
            if row.get(field) is None:
                issues.append(ValidationIssue(
                    severity=Severity.CRITICAL,
                    field=field,
                    message="Missing required field",
                    suggestion="Use YFinance fallback"
                ))

        # 2. IMPORTANT FIELDS
        for field in CASHFLOW_IMPORTANT:
            if row.get(field) is None:
                issues.append(ValidationIssue(
                    severity=Severity.WARNING,
                    field=field,
                    message="Missing important field",
                ))

        # 3. CAPEX SIGN CHECK (should be negative)
        capex = _safe_float(row.get("capital_expenditures"))
        if capex is not None and capex > 0:
            issues.append(ValidationIssue(
                severity=Severity.WARNING,
                field="capital_expenditures",
                message="CapEx is positive (expected negative)",
                actual=f"${capex:,.0f}",
                suggestion="Verify sign convention"
            ))

        quality_score = _calculate_quality_score(issues)
        field_sources = row.get("field_sources")

        return ValidationResult(
            symbol=symbol,
            fiscal_year=fy or 0,
            fiscal_quarter=fq,
            statement_type="cashflow",
            issues=issues,
            quality_score=quality_score,
            field_sources=field_sources,
        )


# ============================================================================
# POST-WRITE VERIFICATION (matches super_investors exactly)
# ============================================================================

def verify_database_write(
    supabase,
    table: str,
    company_id: int,
    fiscal_year: int,
    fiscal_quarter: int | None,
    expected_values: dict[str, Any],
    symbol: str,
) -> list[ValidationIssue]:
    """
    Post-write verification matching super_investors pattern EXACTLY.
    
    Query DB after write, compare written values to expected.
    
    Args:
        supabase: Supabase client
        table: "income_statements", "balance_sheets", or "cash_flow_statements"
        company_id: Company ID
        fiscal_year: Fiscal year
        fiscal_quarter: Fiscal quarter (None for annual)
        expected_values: Dict of field: expected_value
        symbol: Ticker symbol for logging
        
    Returns:
        List of validation issues
    """
    issues: list[ValidationIssue] = []

    try:
        # Build query
        query = (
            supabase.table(table)
            .select("*")
            .eq("company_id", company_id)
            .eq("fiscal_year", fiscal_year)
        )

        if fiscal_quarter is not None:
            query = query.eq("fiscal_quarter", fiscal_quarter)
        else:
            query = query.is_("fiscal_quarter", "null")

        result = query.execute()

        # Check entry exists
        if not result.data or len(result.data) == 0:
            issues.append(ValidationIssue(
                severity=Severity.CRITICAL,
                field=table,
                message="Entry not found after write",
                suggestion="Database write failed - retry"
            ))
            logger.error(
                "[DQ] %s: VALIDATION FAIL - %s entry not found after write (FY%s Q%s)",
                symbol, table, fiscal_year, fiscal_quarter or "Annual"
            )
            return issues

        written_row = result.data[0]

        # Verify each expected value (EXACT pattern from super_investors)
        for field, expected_val in expected_values.items():
            if expected_val is None:
                continue

            written_val = written_row.get(field)

            if written_val is None:
                issues.append(ValidationIssue(
                    severity=Severity.ERROR,
                    field=field,
                    message="Field NULL after write",
                    expected=expected_val,
                    actual=None
                ))
                logger.error(
                    "[DQ] %s: VALIDATION FAIL - %s.%s NULL after write (expected: %s)",
                    symbol, table, field, expected_val
                )
                continue

            # Numeric comparison with tolerance (0.1% like super_investors)
            if isinstance(expected_val, (int, float, Decimal)):
                try:
                    expected_float = float(expected_val)
                    written_float = float(written_val)
                    tolerance = abs(expected_float) * 0.001  # 0.1%

                    if abs(written_float - expected_float) > tolerance:
                        issues.append(ValidationIssue(
                            severity=Severity.ERROR,
                            field=field,
                            message="Value mismatch after write",
                            expected=expected_float,
                            actual=written_float
                        ))
                        logger.error(
                            "[DQ] %s: VALIDATION FAIL - %s.%s mismatch (written=%s, expected=%s)",
                            symbol, table, field, written_float, expected_float
                        )
                except (ValueError, TypeError):
                    pass

    except Exception as e:
        logger.error("[DQ] %s: Post-write verification failed: %s", symbol, e)
        issues.append(ValidationIssue(
            severity=Severity.ERROR,
            field="post_write_check",
            message=f"Verification failed: {e!s}",
        ))

    return issues


# ============================================================================
# LOGGING HELPERS
# ============================================================================

# Identity/structure fields must never be nulled by field-level quarantine.
_PROTECTED_FIELDS = frozenset(
    {"company_id", "fiscal_year", "fiscal_quarter", "period_end_date", "currency"}
)


def quarantine_critical_fields(
    row: dict[str, Any], result: ValidationResult
) -> dict[str, Any]:
    """Null only CRITICAL-flagged fields; preserve every other real value.

    Whole-row rejection caused `[DQ] Quality Score 0/100` rows to be discarded
    and their periods recorded as gaps; the gap-filler then replaced mostly-good
    source data with LOCF synthetic values. Only the specific fields that failed
    validation are invalid. The caller keeps the row (so it is not gap-filled).
    """
    cleaned = dict(row)
    for issue in result.issues:
        if issue.severity == Severity.CRITICAL and issue.field in _PROTECTED_FIELDS:
            # An invalid identity field cannot be repaired by nulling it; keep
            # the row intact and let the caller decide.
            continue
        if issue.severity == Severity.CRITICAL and issue.field in cleaned:
            cleaned[issue.field] = None
    return cleaned


def log_validation_result(result: ValidationResult) -> None:
    """Log validation result with severity-based formatting and provider attribution."""
    if not result.issues:
        logger.debug("[DQ] %s FY%s Q%s %s: ✅ PASS (score: %d/100)",
                    result.symbol, result.fiscal_year,
                    result.fiscal_quarter or "Annual",
                    result.statement_type.upper(),
                    result.quality_score)
        return

    logger.warning(
        "[DQ] %s FY%s Q%s %s: Quality Score %d/100",
        result.symbol, result.fiscal_year,
        result.fiscal_quarter or "Annual",
        result.statement_type.upper(),
        result.quality_score
    )

    for issue in result.issues:
        prefix = {
            Severity.CRITICAL: "🔴 CRITICAL",
            Severity.ERROR: "🟠 ERROR",
            Severity.WARNING: "🟡 WARNING",
            Severity.INFO: "ℹ️  INFO",
        }[issue.severity]

        msg = f"[DQ]   {prefix}: {issue.field} - {issue.message}"
        if issue.expected is not None:
            msg += f" (expected: {issue.expected}, got: {issue.actual})"

        if result.field_sources and issue.severity in (Severity.CRITICAL, Severity.WARNING):
            sources = result.field_sources.get(issue.field)
            if sources:
                msg += f" [provider: {', '.join(sources)}]"
            else:
                msg += " [provider: NONE]"

        if issue.suggestion:
            msg += f" → {issue.suggestion}"

        if issue.severity == Severity.CRITICAL or issue.severity == Severity.ERROR:
            logger.error(msg)
        elif issue.severity == Severity.WARNING:
            logger.warning(msg)
        else:
            logger.info(msg)


# ============================================================================
# HELPERS
# ============================================================================

def _safe_float(val: Any) -> float | None:
    """Safe float conversion (None on failure)."""
    if val is None:
        return None
    if isinstance(val, float) and val != val:  # NaN check
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _calculate_quality_score(issues: list[ValidationIssue]) -> int:
    """Calculate quality score (0-100) based on issues (like super_investors)."""
    if not issues:
        return 100

    penalty = 0
    for issue in issues:
        if issue.severity == Severity.CRITICAL:
            penalty += 25
        elif issue.severity == Severity.ERROR:
            penalty += 10
        elif issue.severity == Severity.WARNING:
            penalty += 3
        else:  # INFO
            penalty += 1

    score = max(0, 100 - penalty)
    return score
