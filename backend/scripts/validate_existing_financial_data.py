#!/usr/bin/env python3
"""
Financial Data Validation & Gap Detection Script
Validates ALL existing data in Supabase + detects gaps.

Features:
- Validates existing income_statements, balance_sheets, cash_flows
- Detects missing periods (gap detection)
- Detects missing fields (field completeness)
- Tracks validation progress (resume support)
- Generates detailed quality report
- Suggests remediation actions

Run: cd backend && source venv/bin/activate && python scripts/validate_existing_financial_data.py
"""

import json
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from application.validators.financial_data_validator import (
    BALANCE_REQUIRED,
    CASHFLOW_REQUIRED,
    INCOME_REQUIRED,
    FinancialDataValidator,
    Severity,
    ValidationResult,
)
from database import supabase

CHECKPOINT_PATH = Path("logs") / "validation_checkpoint.json"


# ============================================================================
# CHECKPOINT MANAGER (Resume Support)
# ============================================================================

class CheckpointManager:
    """Tracks validation progress via local JSON file for resume support."""

    def __init__(self):
        self.checkpoint_path = CHECKPOINT_PATH
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> int | None:
        """Load last validated company_id from checkpoint."""
        try:
            if self.checkpoint_path.exists():
                data = json.loads(self.checkpoint_path.read_text())
                company_id = data.get("last_company_id")
                if company_id is not None:
                    return company_id
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
        return None

    def save(self, company_id: int, status: str = "validated"):
        """Save validation progress."""
        try:
            self.checkpoint_path.write_text(json.dumps({
                "last_company_id": company_id,
                "status": status,
                "updated_at": datetime.utcnow().isoformat()
            }))
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    def clear(self):
        """Remove checkpoint after successful completion."""
        try:
            if self.checkpoint_path.exists():
                self.checkpoint_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to clear checkpoint: {e}")


# ============================================================================
# GAP DETECTOR
# ============================================================================

class GapDetector:
    """
    Detects missing data:
    - Missing fiscal periods (Q1 2023 missing when Q2,Q3,Q4 exist)
    - Missing fields (required fields NULL)
    - Stale data (no update in 6+ months)
    """

    @staticmethod
    def detect_missing_periods(
        rows: list[dict[str, Any]],
        is_quarterly: bool
    ) -> list[tuple[int, int | None]]:
        """
        Detect missing fiscal periods.
        
        Returns list of (fiscal_year, fiscal_quarter) tuples for missing periods.
        """
        if not rows:
            return []

        # Build set of existing periods
        existing = set()
        for r in rows:
            fy = r.get("fiscal_year")
            fq = r.get("fiscal_quarter")
            if fy is not None:
                existing.add((fy, fq))

        # Determine range
        years = sorted(set(fy for fy, _ in existing))
        if not years:
            return []

        min_year, max_year = min(years), max(years)

        # Expected periods
        missing = []
        for year in range(min_year, max_year + 1):
            if is_quarterly:
                for quarter in [1, 2, 3, 4]:
                    if (year, quarter) not in existing:
                        missing.append((year, quarter))
            else:
                if (year, None) not in existing:
                    missing.append((year, None))

        return missing

    @staticmethod
    def detect_field_gaps(
        row: dict[str, Any],
        required_fields: set[str]
    ) -> list[str]:
        """Detect which required fields are missing."""
        missing = []
        for field in required_fields:
            if field == "fiscal_quarter" and row.get("fiscal_quarter") is None:
                continue  # OK for annual
            if row.get(field) is None:
                missing.append(field)
        return missing

    @staticmethod
    def detect_stale_data(updated_at: str | None, threshold_days: int = 180) -> bool:
        """Check if data hasn't been updated in threshold_days."""
        if not updated_at:
            return True

        try:
            updated = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
            age_days = (datetime.utcnow().replace(tzinfo=updated.tzinfo) - updated).days
            return age_days > threshold_days
        except Exception:
            return True


# ============================================================================
# QUALITY REPORT GENERATOR
# ============================================================================

class QualityReport:
    """Generates detailed validation report."""

    def __init__(self):
        self.companies_validated = 0
        self.total_rows_validated = 0
        self.critical_issues = 0
        self.errors = 0
        self.warnings = 0
        self.companies_with_issues = []
        self.gap_summary = {
            "missing_periods": [],
            "missing_fields": defaultdict(int),
            "stale_data": []
        }

    def add_validation_result(
        self,
        symbol: str,
        company_id: int,
        result: ValidationResult
    ):
        """Record validation result."""
        self.total_rows_validated += 1

        for issue in result.issues:
            if issue.severity == Severity.CRITICAL:
                self.critical_issues += 1
            elif issue.severity == Severity.ERROR:
                self.errors += 1
            elif issue.severity == Severity.WARNING:
                self.warnings += 1

        if result.has_errors():
            self.companies_with_issues.append({
                "symbol": symbol,
                "company_id": company_id,
                "fiscal_year": result.fiscal_year,
                "fiscal_quarter": result.fiscal_quarter,
                "quality_score": result.quality_score,
                "issues": len(result.issues)
            })

    def add_gaps(
        self,
        symbol: str,
        missing_periods: list[tuple[int, int | None]],
        missing_fields: dict[str, list[str]],
        stale: bool
    ):
        """Record detected gaps."""
        if missing_periods:
            self.gap_summary["missing_periods"].append({
                "symbol": symbol,
                "periods": missing_periods
            })

        for field in missing_fields:
            self.gap_summary["missing_fields"][field] += 1

        if stale:
            self.gap_summary["stale_data"].append(symbol)

    def generate(self) -> str:
        """Generate human-readable report."""
        lines = []
        lines.append("=" * 80)
        lines.append("FINANCIAL DATA VALIDATION REPORT")
        lines.append("=" * 80)
        lines.append("")

        # Summary
        lines.append(f"Companies Validated: {self.companies_validated}")
        lines.append(f"Total Rows Validated: {self.total_rows_validated}")
        lines.append(f"Critical Issues: {self.critical_issues}")
        lines.append(f"Errors: {self.errors}")
        lines.append(f"Warnings: {self.warnings}")
        lines.append("")

        # Companies with issues
        if self.companies_with_issues:
            lines.append("Companies with Quality Issues (score < 100):")
            lines.append("-" * 80)
            for c in sorted(self.companies_with_issues, key=lambda x: x["quality_score"]):
                lines.append(
                    f"  {c['symbol']:<8} FY{c['fiscal_year']} Q{c['fiscal_quarter'] or 'Annual':<7} "
                    f"Score: {c['quality_score']}/100  Issues: {c['issues']}"
                )
            lines.append("")

        # Missing periods
        if self.gap_summary["missing_periods"]:
            lines.append("Missing Fiscal Periods:")
            lines.append("-" * 80)
            for item in self.gap_summary["missing_periods"][:10]:  # Top 10
                periods_str = ", ".join(
                    f"FY{y}Q{q or 'Annual'}" for y, q in item["periods"][:5]
                )
                lines.append(f"  {item['symbol']:<8} {periods_str}")
            if len(self.gap_summary["missing_periods"]) > 10:
                lines.append(f"  ... and {len(self.gap_summary['missing_periods']) - 10} more")
            lines.append("")

        # Missing fields
        if self.gap_summary["missing_fields"]:
            lines.append("Most Commonly Missing Fields:")
            lines.append("-" * 80)
            sorted_fields = sorted(
                self.gap_summary["missing_fields"].items(),
                key=lambda x: x[1],
                reverse=True
            )
            for field, count in sorted_fields[:10]:
                lines.append(f"  {field:<40} {count} companies")
            lines.append("")

        # Stale data
        if self.gap_summary["stale_data"]:
            lines.append(f"Companies with Stale Data (>180 days): {len(self.gap_summary['stale_data'])}")
            lines.append(f"  {', '.join(self.gap_summary['stale_data'][:20])}")
            if len(self.gap_summary["stale_data"]) > 20:
                lines.append(f"  ... and {len(self.gap_summary['stale_data']) - 20} more")
            lines.append("")

        lines.append("=" * 80)
        return "\n".join(lines)


# ============================================================================
# HELPERS
# ============================================================================

def _detect_table_gaps(
    rows: list[dict[str, Any]],
    collector: list[tuple[int, int | None]],
):
    """Detect missing quarterly and annual periods, appending to collector."""
    quarterly = [r for r in rows if r.get("fiscal_quarter") is not None]
    annual = [r for r in rows if r.get("fiscal_quarter") is None]
    collector.extend(
        GapDetector.detect_missing_periods(quarterly, is_quarterly=True)
        + GapDetector.detect_missing_periods(annual, is_quarterly=False)
    )


# ============================================================================
# MAIN VALIDATOR
# ============================================================================

def validate_company_financial_data(
    company_id: int,
    symbol: str,
    report: QualityReport,
    last_financial_refresh_at: str | None = None,
) -> dict[str, Any]:
    """
    Validate all financial data for a single company.
    Returns summary with issues and gaps.
    """
    logger.info(f"[VALIDATE] {symbol} (company_id={company_id})")

    results = {
        "symbol": symbol,
        "company_id": company_id,
        "income_statements": {"validated": 0, "issues": 0},
        "balance_sheets": {"validated": 0, "issues": 0},
        "cash_flows": {"validated": 0, "issues": 0},
        "gaps": {
            "missing_periods": [],
            "missing_fields": {},
            "stale": False,
        }
    }

    company_missing_fields: set[str] = set()
    is_rows: list[dict[str, Any]] = []
    bs_rows: list[dict[str, Any]] = []
    cf_rows: list[dict[str, Any]] = []

    # ========================================================================
    # VALIDATE INCOME STATEMENTS
    # ========================================================================
    try:
        is_rows = (
            supabase.table("income_statements")
            .select("*")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=False)
            .execute()
        ).data or []

        if not is_rows:
            logger.warning(f"{symbol}: No income_statements rows found")

        for row in is_rows:
            validation_result = FinancialDataValidator.validate_income_statement(
                row=row,
                symbol=symbol
            )
            report.add_validation_result(symbol, company_id, validation_result)
            results["income_statements"]["validated"] += 1
            if validation_result.has_errors():
                results["income_statements"]["issues"] += 1

            company_missing_fields.update(
                GapDetector.detect_field_gaps(row, INCOME_REQUIRED)
            )

        # Detect missing periods
        _detect_table_gaps(is_rows, results["gaps"]["missing_periods"])

    except Exception as e:
        logger.error(f"[VALIDATE] {symbol} income statements failed: {e}")

    # ========================================================================
    # VALIDATE BALANCE SHEETS
    # ========================================================================
    try:
        bs_rows = (
            supabase.table("balance_sheets")
            .select("*")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=False)
            .execute()
        ).data or []

        if not bs_rows:
            logger.warning(f"{symbol}: No balance_sheets rows found")

        for row in bs_rows:
            validation_result = FinancialDataValidator.validate_balance_sheet(
                row=row,
                symbol=symbol
            )
            report.add_validation_result(symbol, company_id, validation_result)
            results["balance_sheets"]["validated"] += 1
            if validation_result.has_errors():
                results["balance_sheets"]["issues"] += 1

            company_missing_fields.update(
                GapDetector.detect_field_gaps(row, BALANCE_REQUIRED)
            )

        # Detect missing periods
        _detect_table_gaps(bs_rows, results["gaps"]["missing_periods"])

    except Exception as e:
        logger.error(f"[VALIDATE] {symbol} balance sheets failed: {e}")

    # ========================================================================
    # VALIDATE CASH FLOWS
    # ========================================================================
    try:
        cf_rows = (
            supabase.table("cash_flow_statements")
            .select("*")
            .eq("company_id", company_id)
            .order("fiscal_year", desc=False)
            .execute()
        ).data or []

        if not cf_rows:
            logger.warning(f"{symbol}: No cash_flow_statements rows found")

        for row in cf_rows:
            validation_result = FinancialDataValidator.validate_cash_flow(
                row=row,
                symbol=symbol
            )
            report.add_validation_result(symbol, company_id, validation_result)
            results["cash_flows"]["validated"] += 1
            if validation_result.has_errors():
                results["cash_flows"]["issues"] += 1

            company_missing_fields.update(
                GapDetector.detect_field_gaps(row, CASHFLOW_REQUIRED)
            )

        # Detect missing periods
        _detect_table_gaps(cf_rows, results["gaps"]["missing_periods"])

    except Exception as e:
        logger.error(f"[VALIDATE] {symbol} cash flows failed: {e}")

    # Check staleness — prefer company-level, fall back to row-level
    if last_financial_refresh_at:
        results["gaps"]["stale"] = GapDetector.detect_stale_data(
            last_financial_refresh_at
        )
    else:
        all_rows = is_rows + bs_rows + cf_rows
        if all_rows:
            latest = max(all_rows, key=lambda r: r.get("updated_at") or "")
            results["gaps"]["stale"] = GapDetector.detect_stale_data(
                latest.get("updated_at")
            )
        else:
            results["gaps"]["stale"] = True

    # Build missing_fields dict for report
    results["gaps"]["missing_fields"] = dict.fromkeys(company_missing_fields, [])

    # Add gaps to report
    report.add_gaps(
        symbol=symbol,
        missing_periods=results["gaps"]["missing_periods"],
        missing_fields=results["gaps"]["missing_fields"],
        stale=results["gaps"]["stale"]
    )

    return results


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def validate_all_companies(
    resume_from: int | None = None,
    limit: int | None = None,
):
    """
    Validate all companies with resume support.
    
    Args:
        resume_from: company_id to resume from (None = start from beginning)
        limit: maximum number of companies to validate (None = all)
    """
    logger.info("=" * 80)
    logger.info("Starting Financial Data Validation")
    logger.info("=" * 80)

    # Get all companies
    try:
        query = (
            supabase.table("companies")
            .select("company_id, ticker_symbol, last_financial_refresh_at")
            .in_("data_completeness_status", ["COMPLETE", "CURRENT", "PARTIAL"])
            .order("company_id", desc=False)
        )

        if resume_from is not None:
            query = query.gte("company_id", resume_from)

        companies = query.execute().data or []

    except Exception as e:
        logger.error(f"Failed to fetch companies: {e}")
        return

    total = len(companies)
    logger.info(f"Found {total} companies to validate")
    if resume_from:
        logger.info(f"Resuming from company_id={resume_from}")

    if limit is not None:
        companies = companies[:limit]
        logger.info(f"Limited to {limit} companies")

    # Initialize report and checkpoint
    report = QualityReport()
    checkpoint = CheckpointManager()

    # Validate each company
    for idx, company in enumerate(companies, 1):
        company_id = company["company_id"]
        symbol = company["ticker_symbol"]
        last_refresh = company.get("last_financial_refresh_at")

        try:
            logger.info(f"[{idx}/{total}] Validating {symbol} (company_id={company_id})")

            validate_company_financial_data(
                company_id, symbol, report,
                last_financial_refresh_at=last_refresh,
            )
            report.companies_validated += 1

            # Save checkpoint
            checkpoint.save(company_id)

        except Exception as e:
            logger.error(f"[{idx}/{total}] Failed to validate {symbol}: {e}")
            checkpoint.save(company_id, "failed")
            continue

    # Clear checkpoint on successful completion
    checkpoint.clear()

    # Generate and display report
    logger.info("")
    logger.info(report.generate())

    # Write report to file
    report_path = f"validation_report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(report_path, "w") as f:
        f.write(report.generate())
    logger.info(f"Report saved to: {report_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate existing financial data")
    parser.add_argument(
        "--resume-from",
        type=int,
        help="Resume from company_id (manual override)"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from last checkpoint file"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of companies to validate (for testing)"
    )

    args = parser.parse_args()

    resume_from = args.resume_from

    if args.resume and resume_from is None:
        checkpoint = CheckpointManager()
        resume_from = checkpoint.load()
        if resume_from is None:
            logger.info("No checkpoint found, starting from beginning")

    validate_all_companies(resume_from=resume_from, limit=args.limit)
