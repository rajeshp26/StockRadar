#!/usr/bin/env python3
"""
Backfill Super Investors Historical Data

Fetches up to 20 quarters of 13F filings for all super investors and saves to DB.
Includes resume logic to skip investors who already have complete data.
Run: cd backend && source venv/bin/activate && python scripts/backfill_super_investors.py
"""
import logging
import sys
import time
from typing import Any

sys.path.insert(0, ".")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

from application.services.super_investors_service import SUPER_INVESTORS
from application.services.watchlist_service import _map_quote_type
from providers.yfinance_provider import YFinanceProvider


def get_or_create_investor(supabase, cik: str, info: dict[str, str]) -> int:
    """Get or create investor record, return investor_id."""
    result = supabase.table("institutional_investors").select(
        "investor_id"
    ).eq("cik", cik).execute()

    if result.data and len(result.data) > 0:
        return result.data[0]["investor_id"]

    insert_data = {
        "cik": cik,
        "investor_name": info["name"],
        "firm_name": info["firm"],
        "investor_tag": info["tag"],
        "investment_style": info.get("style", ""),
        "is_super_investor": True,
        "is_active": True,
    }
    insert_result = supabase.table("institutional_investors").insert(insert_data).execute()
    if insert_result.data and len(insert_result.data) > 0:
        return insert_result.data[0]["investor_id"]

    raise ValueError(f"Failed to create investor: {info['name']}")


def get_or_create_company(supabase, ticker: str, stock_provider: YFinanceProvider = None) -> int:
    """Get existing company_id or create new one using Yahoo Finance."""
    if not ticker or not isinstance(ticker, str):
        return None

    ticker_upper = ticker.upper().strip()
    if not ticker_upper:
        return None

    result = supabase.table("companies").select("company_id").eq("ticker_symbol", ticker_upper).execute()

    if result.data and len(result.data) > 0:
        return result.data[0]["company_id"]

    if stock_provider is None:
        logger.warning(f"No stock provider for {ticker_upper}, skipping")
        return None

    try:
        sd = stock_provider.get_stock_details(ticker_upper)
    except Exception as e:
        if "404" in str(e):
            logger.warning(f"Skipping {ticker_upper}: YF not found (404)")
            return None
        logger.warning(f"YF API failed for {ticker_upper}: {e}")
        return None

    if not sd:
        logger.warning(f"Skipping {ticker_upper}: No YF data")
        return None

    payload = {
        "ticker_symbol": ticker_upper,
        "company_name": sd.long_name,
        "exchange": sd.exchange,
        "sector": sd.sector,
        "industry": sd.industry,
        "currency": sd.currency,
        "description": sd.description,
        "website": sd.website,
        # Prevents the DB default ('stock') stamping ETFs/funds from bulk
        # backfills — same mapping the watchlist add-flow uses (watchlist_service._map_quote_type).
        "security_type": _map_quote_type(sd.quote_type),
    }

    insert_result = supabase.table("companies").insert(payload).execute()
    if insert_result.data and len(insert_result.data) > 0:
        logger.info(f"Created company: {ticker_upper}")
        time.sleep(0.1)
        return insert_result.data[0]["company_id"]

    logger.error(f"Failed to create company for {ticker_upper}")
    return None


def save_holdings_to_db(supabase, investor_id: int, holdings_df, period: str, filing_date: str, stock_provider: YFinanceProvider = None, total_value_dollars: float = None):
    """Save holdings to institutional_holdings table."""
    # edgar library returns Value in ACTUAL DOLLARS (not thousands)
    # Use total_value from thirteenf.total_value if provided, otherwise sum holdings
    if total_value_dollars is not None:
        total_value = total_value_dollars
    else:
        total_value = float(holdings_df["Value"].sum())

    saved_count = 0
    holdings_df = holdings_df[holdings_df["Ticker"].notna()]

    for _, row in holdings_df.iterrows():
        ticker = row.get("Ticker")
        if not ticker:
            continue

        company_id = get_or_create_company(supabase, ticker, stock_provider)
        if not company_id:
            logger.warning(f"Could not create company for {ticker}, skipping holding")
            continue

        shares = int(row.get("SharesPrnAmount", 0) or 0)
        value_dollars = float(row.get("Value", 0) or 0)  # edgar returns in actual dollars
        weight = (value_dollars / total_value) if total_value > 0 else 0

        # Validate before write
        if value_dollars < 1000000:  # < $1M is suspicious for super investors
            logger.warning(f"  Suspicious low value for {ticker}: ${value_dollars:,.0f}")
        if weight > 0.5:  # >50% for single position is suspicious
            logger.warning(f"  Suspicious high weight for {ticker}: {weight:.2%}")

        # Check if holding already exists
        existing = supabase.table("institutional_holdings").select(
            "holding_id"
        ).eq("investor_id", investor_id).eq(
            "company_id", company_id
        ).eq("quarter_end_date", period).execute()

        insert_data = {
            "investor_id": investor_id,
            "company_id": company_id,
            "quarter_end_date": period,
            "filing_date": filing_date,
            "shares_held": shares,
            "position_value": float(value_dollars),
            "portfolio_weight": float(weight),
            "data_source": "edgar",
        }

        if existing.data and len(existing.data) > 0:
            supabase.table("institutional_holdings").update(insert_data).eq(
                "holding_id", existing.data[0]["holding_id"]
            ).execute()
        else:
            supabase.table("institutional_holdings").insert(insert_data).execute()

        # Post-write validation: verify the entry was written correctly
        verify = supabase.table("institutional_holdings").select(
            "position_value, portfolio_weight"
        ).eq("investor_id", investor_id).eq(
            "company_id", company_id
        ).eq("quarter_end_date", period).execute()

        if verify.data and len(verify.data) > 0:
            written_val = float(verify.data[0]["position_value"])
            written_wgt = float(verify.data[0]["portfolio_weight"])
            if abs(written_val - value_dollars) > 1:
                logger.error(f"  VALIDATION FAIL: {ticker} value written={written_val}, expected={value_dollars}")
            if abs(written_wgt - weight) > 0.0001:
                logger.error(f"  VALIDATION FAIL: {ticker} weight written={written_wgt}, expected={weight}")
        else:
            logger.error(f"  VALIDATION FAIL: {ticker} entry not found after write")

        saved_count += 1

    return saved_count


def update_investor_tracking(supabase, cik: str, period: str, filing_date: str):
    """Update last_filed_period and last_filed_date."""
    update_data = {
        "last_filed_date": filing_date,
        "last_filed_period": period,
    }
    supabase.table("institutional_investors").update(update_data).eq("cik", cik).execute()


def get_investor_status(supabase, cik: str) -> dict[str, Any]:
    """
    Check investor's current state in DB.
    
    Returns:
        {
            "exists": bool,
            "investor_id": int or None,
            "last_filed_period": str or None,
            "last_filed_date": str or None,
            "existing_quarters": Set[str],
            "quarter_count": int
        }
    """
    result = supabase.table("institutional_investors").select(
        "investor_id, last_filed_period, last_filed_date"
    ).eq("cik", cik).execute()

    if not result.data or len(result.data) == 0:
        return {
            "exists": False,
            "investor_id": None,
            "last_filed_period": None,
            "last_filed_date": None,
            "existing_quarters": set(),
            "quarter_count": 0,
        }

    investor = result.data[0]
    investor_id = investor["investor_id"]

    holdings_result = supabase.table("institutional_holdings").select(
        "quarter_end_date"
    ).eq("investor_id", investor_id).execute()

    existing_quarters = set(h.get("quarter_end_date") for h in (holdings_result.data or []) if h.get("quarter_end_date"))

    return {
        "exists": True,
        "investor_id": investor_id,
        "last_filed_period": investor.get("last_filed_period"),
        "last_filed_date": investor.get("last_filed_date"),
        "existing_quarters": existing_quarters,
        "quarter_count": len(existing_quarters),
    }


def get_missing_filings(
    all_filings: list,
    existing_quarters: set[str],
    max_quarters: int
) -> list[tuple]:
    """
    Filter filings to only those for quarters not already in DB.
    
    Args:
        all_filings: List of SEC filings (sorted by date descending)
        existing_quarters: Set of quarter dates already in DB
        max_quarters: Maximum quarters to fetch for this investor
        
    Returns:
        List of (filing, thirteenf) tuples for missing quarters
    """
    missing_filings = []

    for filing in all_filings:
        try:
            thirteenf = filing.obj()
            if not thirteenf:
                continue

            period = str(thirteenf.report_period)

            if period in existing_quarters:
                continue

            missing_filings.append((filing, thirteenf))

            if len(missing_filings) >= max_quarters:
                break

        except Exception as e:
            logger.debug(f"Error parsing filing: {e}")
            continue

    return missing_filings


def backfill_all_investors():
    """Main function to backfill all super investors with resume logic."""
    from edgar import get_filings, set_identity

    from database import supabase

    set_identity("StockerPro backfill script rajeshp01@gmail.com")
    stock_provider = YFinanceProvider()
    YEARS_TO_FETCH = list(range(2021, 2027))  # Now includes 2026 for Q1 filings

    total_investors = len(SUPER_INVESTORS)
    logger.info(f"Starting backfill for {total_investors} investors")

    stats = {"complete": 0, "incomplete": 0, "new": 0, "error": 0}
    completed_ciks = []

    for idx, (cik, info) in enumerate(SUPER_INVESTORS.items(), 1):
        investor_name = info["name"]
        tag = info.get("tag", "UNKNOWN")
        target_quarters = info.get("quarters", 20)

        try:
            status = get_investor_status(supabase, cik)

            if status["exists"]:
                if status["quarter_count"] >= target_quarters:
                    logger.info(f"[{idx}/{total_investors}] {investor_name} ({tag}) - COMPLETE ({status['quarter_count']}/{target_quarters} quarters, skipping)")
                    stats["complete"] += 1
                    completed_ciks.append(cik)
                    continue
                else:
                    logger.info(f"[{idx}/{total_investors}] {investor_name} ({tag}) - INCOMPLETE ({status['quarter_count']}/{target_quarters} quarters, fetching {target_quarters - status['quarter_count']} more)")
                    stats["incomplete"] += 1
            else:
                logger.info(f"[{idx}/{total_investors}] {investor_name} ({tag}) - NEW investor, fetching {target_quarters} quarters")
                stats["new"] += 1

            investor_id = get_or_create_investor(supabase, cik, info)
            existing_quarters = status["existing_quarters"] if status["exists"] else set()

            all_filings = []
            for year in YEARS_TO_FETCH:
                try:
                    filings = get_filings(year=year, form="13F-HR").filter(cik=cik)
                    if filings:
                        all_filings.extend(list(filings))
                except Exception as e:
                    logger.debug(f"  No filings for {year}: {e}")
                    continue

            if not all_filings:
                logger.warning(f"  No filings found for {investor_name}")
                continue

            all_filings.sort(key=lambda x: x.filing_date, reverse=True)

            missing_filings = get_missing_filings(all_filings, existing_quarters, target_quarters)
            logger.info(f"  Found {len(all_filings)} total filings, {len(missing_filings)} missing quarters to fetch")

            if not missing_filings:
                logger.info(f"  {investor_name}: No missing quarters")
                continue

            total_holdings_saved = 0

            for filing_idx, (filing, thirteenf) in enumerate(missing_filings):
                try:
                    period = str(thirteenf.report_period)
                    filing_date = str(filing.filing_date)

                    holdings_df = thirteenf.holdings
                    if holdings_df is None or holdings_df.empty:
                        logger.debug(f"  Filing {filing_idx}: no holdings data")
                        continue

                    # thirteenf.total_value is in actual dollars (Decimal type)
                    total_val = float(thirteenf.total_value) if thirteenf.total_value else None

                    saved = save_holdings_to_db(
                        supabase, investor_id, holdings_df, period, filing_date, stock_provider, total_value_dollars=total_val
                    )
                    total_holdings_saved += saved
                    logger.info(f"  Filing {filing_idx+1}/{len(missing_filings)}: {period} - {saved} holdings saved")

                except Exception as e:
                    logger.error(f"  Error processing filing {filing_idx}: {e}")
                    continue

            if missing_filings:
                latest_filing, latest_thirteenf = missing_filings[0]
                latest_period = str(latest_thirteenf.report_period)
                latest_filing_date = str(latest_filing.filing_date)
                update_investor_tracking(supabase, cik, latest_period, latest_filing_date)

            logger.info(f"  {investor_name}: Total {total_holdings_saved} holdings saved")

        except Exception as e:
            logger.error(f"[{idx}/{total_investors}] Failed to process {investor_name}: {e}")
            stats["error"] += 1
            continue

    logger.info("=" * 60)
    logger.info("Backfill complete!")
    logger.info(f"  COMPLETE (skipped): {stats['complete']}")
    logger.info(f"  INCOMPLETE (fetched missing): {stats['incomplete']}")
    logger.info(f"  NEW (full backfill): {stats['new']}")
    if stats['error'] > 0:
        logger.info(f"  ERROR: {stats['error']}")
    logger.info("=" * 60)


if __name__ == "__main__":
    backfill_all_investors()
