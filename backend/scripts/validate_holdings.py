#!/usr/bin/env python3
"""
Validate ALL Super Investor Holdings Against SEC 13F Filings

This script:
1. Reads every entry from institutional_holdings
2. Fetches the original 13F filing from SEC EDGAR for that investor/quarter
3. Compares DB values against SEC values (shares, value in thousands, calculated weight)
4. Generates a detailed CSV report with discrepancies
5. Provides summary statistics for decision making

Output Files:
- validation_report.csv: Full report of ALL entries with validation status
- validation_summary.txt: Summary statistics

Usage:
    cd C:\\Project\\StockerPro\\StockerPro\backend
    $env:PYTHONIOENCODING="utf-8"
    python scripts/validate_holdings.py
"""
import csv
import logging
import os
import sys
from collections import defaultdict
from datetime import datetime
from typing import Any

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Suppress edgar debug logs
logging.getLogger("edgar").setLevel(logging.WARNING)

from database import supabase


def get_all_holdings() -> list[dict]:
    """Fetch all holdings with investor and company details."""
    logger.info("Fetching all holdings from database...")

    # Fetch holdings with related data using joins
    result = supabase.table("institutional_holdings").select(
        "holding_id, investor_id, company_id, quarter_end_date, filing_date, "
        "shares_held, position_value, portfolio_weight, data_source, created_at"
    ).order("investor_id").order("quarter_end_date").execute()

    logger.info(f"Fetched {len(result.data)} holdings")
    return result.data


def get_investors_map() -> dict[int, dict]:
    """Get mapping of investor_id -> investor info."""
    result = supabase.table("institutional_investors").select(
        "investor_id, investor_name, cik, investor_tag"
    ).execute()
    return {inv["investor_id"]: inv for inv in result.data}


def get_companies_map() -> dict[int, dict]:
    """Get mapping of company_id -> company info."""
    result = supabase.table("companies").select(
        "company_id, ticker_symbol, cusip, company_name"
    ).execute()
    return {comp["company_id"]: comp for comp in result.data}


def fetch_13f_filing(cik: str, quarter_end_date: str) -> tuple[Any, Any] | None:
    """
    Fetch 13F filing from SEC EDGAR for given CIK and quarter end date.
    Returns (filing, thirteenf) or None.
    """
    try:

        from edgar import get_filings

        # Parse quarter end date
        period_date = datetime.strptime(quarter_end_date, "%Y-%m-%d").date()

        # Get filings for this CIK around the period
        filings = get_filings(year=period_date.year, form="13F-HR").filter(cik=cik)

        if not filings:
            return None

        # Find the filing that matches this quarter end date
        for filing in filings:
            try:
                if hasattr(filing, 'report_date') and filing.report_date == period_date:
                    thirteenf = filing.obj()
                    return (filing, thirteenf)
            except:
                continue

        # If not found by exact match, try closest by report period
        for filing in filings:
            try:
                thirteenf = filing.obj()
                if str(thirteenf.report_period) == quarter_end_date:
                    return (filing, thirteenf)
            except:
                continue

        return None
    except Exception as e:
        logger.debug(f"Error fetching 13F for CIK {cik}, date {quarter_end_date}: {e}")
        return None


def validate_holding(
    holding: dict,
    investor: dict,
    company: dict,
    filing_data_cache: dict[str, Any]
) -> dict[str, Any]:
    """
    Validate a single holding against SEC 13F data.
    
    Returns dict with validation results:
    - status: 'match', 'discrepancy', 'no_filing', 'no_match_in_filing', 'error'
    - db_shares, db_value, db_weight
    - sec_shares, sec_value_thousands, sec_value_dollars
    - expected_weight, calculated_weight
    - discrepancies: list of field names with mismatches
    """
    result = {
        "holding_id": holding["holding_id"],
        "investor_id": holding["investor_id"],
        "investor_name": investor.get("investor_name", "Unknown"),
        "investor_tag": investor.get("investor_tag", "Unknown"),
        "company_id": holding["company_id"],
        "ticker": company.get("ticker_symbol", "Unknown"),
        "cusip": company.get("cusip", ""),
        "quarter_end_date": holding["quarter_end_date"],
        "filing_date": holding["filing_date"],
        "data_source": holding.get("data_source", ""),
        "created_at": str(holding.get("created_at", "")),

        # DB values
        "db_shares": holding.get("shares_held", 0),
        "db_position_value": holding.get("position_value", 0),
        "db_portfolio_weight": holding.get("portfolio_weight", 0),

        # SEC values (to be filled)
        "sec_shares": None,
        "sec_value_thousands": None,
        "sec_value_dollars": None,
        "sec_total_portfolio_thousands": None,
        "sec_total_portfolio_dollars": None,
        "expected_weight": None,

        # Validation
        "status": "pending",
        "discrepancies": "",
        "shares_match": None,
        "value_match": None,
        "weight_match": None,
    }

    cik = investor.get("cik")
    if not cik:
        result["status"] = "no_cik"
        return result

    ticker = company.get("ticker_symbol")
    if not ticker:
        result["status"] = "no_ticker"
        return result

    # Check cache for filing data
    cache_key = f"{cik}_{holding['quarter_end_date']}"
    if cache_key in filing_data_cache:
        thirteenf = filing_data_cache[cache_key]
    else:
        # Fetch filing
        filing_result = fetch_13f_filing(cik, holding["quarter_end_date"])
        if not filing_result:
            result["status"] = "no_filing"
            return result
        _, thirteenf = filing_result
        filing_data_cache[cache_key] = thirteenf

    try:
        holdings_df = thirteenf.holdings
        if holdings_df is None or holdings_df.empty:
            result["status"] = "no_holdings_in_filing"
            return result

        # Calculate total portfolio value (SEC reports in thousands)
        total_value_thousands = holdings_df["Value"].sum()
        total_value_dollars = total_value_thousands * 1000

        result["sec_total_portfolio_thousands"] = float(total_value_thousands)
        result["sec_total_portfolio_dollars"] = float(total_value_dollars)

        # Find the specific holding by ticker or CUSIP
        ticker_upper = ticker.upper()
        cusip = company.get("cusip", "")

        match = holdings_df[
            (holdings_df["Ticker"].str.upper() == ticker_upper)
            | (holdings_df["Cusip"].str.upper() == cusip.upper() if cusip else False)
            | (holdings_df["Class"].str.contains(ticker_upper, case=False, na=False))
            | (holdings_df["Issuer"].str.contains(ticker_upper, case=False, na=False))
        ]

        if match.empty:
            result["status"] = "no_match_in_filing"
            return result

        row = match.iloc[0]

        sec_shares = int(row.get("SharesPrnAmount", 0) or 0)
        sec_value_thousands = float(row.get("Value", 0) or 0)
        sec_value_dollars = sec_value_thousands * 1000
        expected_weight = (sec_value_dollars / total_value_dollars) if total_value_dollars > 0 else 0

        result["sec_shares"] = sec_shares
        result["sec_value_thousands"] = sec_value_thousands
        result["sec_value_dollars"] = sec_value_dollars
        result["expected_weight"] = expected_weight

        # Compare values
        discrepancies = []

        # Check shares
        if result["db_shares"] != sec_shares:
            discrepancies.append(f"shares (DB:{result['db_shares']} vs SEC:{sec_shares})")
            result["shares_match"] = False
        else:
            result["shares_match"] = True

        # Check position value (DB should be in dollars, SEC in thousands)
        # DB value should equal sec_value_dollars
        if abs(result["db_position_value"] - sec_value_dollars) > 1:  # Allow $1 tolerance
            discrepancies.append(f"position_value (DB:${result['db_position_value']:.2f} vs SEC:${sec_value_dollars:.2f})")
            result["value_match"] = False
        else:
            result["value_match"] = True

        # Check portfolio weight
        if abs(result["db_portfolio_weight"] - expected_weight) > 0.0001:  # Small tolerance
            discrepancies.append(f"portfolio_weight (DB:{result['db_portfolio_weight']:.6f} vs Expected:{expected_weight:.6f})")
            result["weight_match"] = False
        else:
            result["weight_match"] = True

        if discrepancies:
            result["status"] = "discrepancy"
            result["discrepancies"] = "; ".join(discrepancies)
        else:
            result["status"] = "match"

    except Exception as e:
        logger.error(f"Error validating holding {holding['holding_id']}: {e}")
        result["status"] = "error"
        result["discrepancies"] = str(e)

    return result


def generate_reports(validation_results: list[dict], output_dir: str = "."):
    """Generate CSV and summary reports."""

    # Count statistics
    stats = defaultdict(int)
    for r in validation_results:
        stats[r["status"]] += 1

    total = len(validation_results)

    # Write detailed CSV report
    csv_path = os.path.join(output_dir, "validation_report.csv")
    logger.info(f"Writing detailed report to {csv_path}")

    fieldnames = [
        "holding_id", "investor_name", "investor_tag", "ticker", "quarter_end_date",
        "status", "discrepancies",
        "db_shares", "sec_shares", "shares_match",
        "db_position_value", "sec_value_dollars", "value_match",
        "db_portfolio_weight", "expected_weight", "weight_match",
        "sec_total_portfolio_dollars", "data_source", "created_at"
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for r in validation_results:
            writer.writerow(r)

    # Write summary report
    summary_path = os.path.join(output_dir, "validation_summary.txt")
    logger.info(f"Writing summary to {summary_path}")

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("SUPER INVESTOR HOLDINGS VALIDATION SUMMARY\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write("=" * 80 + "\n\n")

        f.write(f"TOTAL ENTRIES ANALYZED: {total}\n\n")

        f.write("STATUS BREAKDOWN:\n")
        f.write("-" * 40 + "\n")
        for status, count in sorted(stats.items(), key=lambda x: -x[1]):
            pct = (count / total * 100) if total > 0 else 0
            f.write(f"  {status:30s}: {count:5d} ({pct:5.1f}%)\n")

        f.write("\n" + "=" * 80 + "\n")
        f.write("RECOMMENDATION:\n")
        f.write("=" * 80 + "\n\n")

        match_pct = (stats.get('match', 0) / total * 100) if total > 0 else 0
        discrepancy_pct = (stats.get('discrepancy', 0) / total * 100) if total > 0 else 0
        error_pct = ((total - stats.get('match', 0) - stats.get('discrepancy', 0)) / total * 100) if total > 0 else 0

        f.write(f"  Entries with exact match: {stats.get('match', 0)} ({match_pct:.1f}%)\n")
        f.write(f"  Entries with discrepancies: {stats.get('discrepancy', 0)} ({discrepancy_pct:.1f}%)\n")
        f.write(f"  Entries with errors/no data: {total - stats.get('match', 0) - stats.get('discrepancy', 0)} ({error_pct:.1f}%)\n\n")

        if discrepancy_pct < 1.0:
            f.write("  RECOMMENDATION: Targeted fixes for discrepancies only.\n")
            f.write("  ACTION: Run SQL updates to fix the discrepant entries.\n")
        elif discrepancy_pct < 5.0:
            f.write("  RECOMMENDATION: Fix discrepancies + re-validate.\n")
            f.write("  ACTION: Run SQL updates for discrepancies, then re-run validation.\n")
        else:
            f.write("  RECOMMENDATION: DELETE ALL and RE-BACKFILL.\n")
            f.write("  ACTION: This guarantees 100% accurate data with no wrong information.\n")
            f.write("  RATIONALE: >5% error rate means data integrity is compromised.\n")

        f.write("\n" + "=" * 80 + "\n")

        # Detailed discrepancy breakdown
        discrepancies = [r for r in validation_results if r["status"] == "discrepancy"]
        if discrepancies:
            f.write("\nDISCREPANCY BREAKDOWN (First 20):\n")
            f.write("-" * 80 + "\n")
            for r in discrepancies[:20]:
                f.write(f"  [{r['investor_tag']}] {r['ticker']} ({r['quarter_end_date']}): {r['discrepancies']}\n")
            if len(discrepancies) > 20:
                f.write(f"  ... and {len(discrepancies) - 20} more (see CSV report)\n")

    logger.info("Reports generated successfully")

    return stats


def main():
    """Main validation function."""
    logger.info("Starting Super Investor Holdings Validation")
    logger.info("=" * 60)

    # Initialize edgar identity
    try:
        from edgar import set_identity
        set_identity("StockerPro validation script rajeshp01@gmail.com")
    except ImportError:
        logger.error("edgartools not installed. Run: pip install edgartools")
        return

    # Fetch all data
    holdings = get_all_holdings()
    investors = get_investors_map()
    companies = get_companies_map()

    logger.info(f"Validating {len(holdings)} holdings for {len(investors)} investors and {len(companies)} companies")

    # Validate each holding
    validation_results = []
    filing_data_cache = {}

    for idx, holding in enumerate(holdings, 1):
        investor_id = holding["investor_id"]
        company_id = holding["company_id"]

        investor = investors.get(investor_id, {})
        company = companies.get(company_id, {})

        if idx % 10 == 0:
            logger.info(f"Progress: {idx}/{len(holdings)} ({idx/len(holdings)*100:.1f}%)")

        result = validate_holding(holding, investor, company, filing_data_cache)
        validation_results.append(result)

    logger.info("Validation complete. Processing reports...")

    # Generate reports
    stats = generate_reports(validation_results)

    logger.info("=" * 60)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total entries: {len(validation_results)}")
    for status, count in sorted(stats.items(), key=lambda x: -x[1]):
        logger.info(f"  {status}: {count}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
