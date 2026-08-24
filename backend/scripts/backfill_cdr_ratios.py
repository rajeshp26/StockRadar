"""
Backfill CDR ratios for all CDR holdings.

Computes cdr_ratio = TSX_share_price / CDR_average_cost and stores it in the companies table.

The TSX share price comes from current_market_data (yfinance_tor source).
The CDR average cost comes from portfolio_holdings (per-unit cost in CAD).

Usage:
    python scripts/backfill_cdr_ratios.py
"""
import sys
from decimal import Decimal
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from datetime import date

from database import supabase

CDR_DEFAULT_RATIO = Decimal("10")


def find_cdr_companies():
    """Find all companies with exchange_override='TOR' in portfolio_holdings."""
    result = (
        supabase.table("portfolio_holdings")
        .select("company_id")
        .eq("exchange_override", "TOR")
        .execute()
    )
    cids = list(set(row["company_id"] for row in (result.data or [])))
    if not cids:
        print("No CDR holdings found.")
        return []
    print(f"Found {len(cids)} CDR company IDs: {cids}")
    return cids


def get_company_info(company_ids):
    """Get company ticker symbols and names."""
    result = (
        supabase.table("companies")
        .select("company_id, ticker_symbol, company_name, currency")
        .in_("company_id", company_ids)
        .execute()
    )
    return {row["company_id"]: row for row in (result.data or [])}


def get_tsx_share_prices(company_ids):
    """Get TSX share prices from current_market_data."""
    result = (
        supabase.table("current_market_data")
        .select("company_id, current_price, last_updated")
        .in_("company_id", company_ids)
        .execute()
    )
    return {row["company_id"]: row for row in (result.data or [])}


def get_cdr_average_costs(company_ids):
    """Get average CDR cost per company from portfolio_holdings."""
    result = (
        supabase.table("portfolio_holdings")
        .select("company_id, average_cost, quantity")
        .in_("company_id", company_ids)
        .eq("exchange_override", "TOR")
        .execute()
    )
    # Compute weighted average cost per company
    costs = {}
    for row in (result.data or []):
        cid = row["company_id"]
        avg = float(row.get("average_cost") or 0)
        qty = float(row.get("quantity") or 0)
        if qty > 0 and avg > 0:
            if cid not in costs:
                costs[cid] = {"total_cost": 0, "total_qty": 0}
            costs[cid]["total_cost"] += avg * qty
            costs[cid]["total_qty"] += qty
    # Compute weighted average
    result_costs = {}
    for cid, data in costs.items():
        if data["total_qty"] > 0:
            result_costs[cid] = data["total_cost"] / data["total_qty"]
    return result_costs


def compute_and_store_ratios():
    """Compute CDR ratios and store in companies table."""
    cdr_cids = find_cdr_companies()
    if not cdr_cids:
        return

    company_info = get_company_info(cdr_cids)
    tsx_prices = get_tsx_share_prices(cdr_cids)
    cdr_costs = get_cdr_average_costs(cdr_cids)

    print(f"\n{'Symbol':<10} {'TSX Price':>12} {'CDR AvgCost':>12} {'Ratio':>10} {'Status'}")
    print("-" * 60)

    updated = 0
    for cid in cdr_cids:
        info = company_info.get(cid, {})
        symbol = info.get("ticker_symbol", "?")

        tsx_row = tsx_prices.get(cid)
        tsx_price = float(tsx_row["current_price"]) if tsx_row and tsx_row.get("current_price") else None

        cdr_avg_cost = cdr_costs.get(cid)

        if tsx_price is None:
            print(f"{symbol:<10} {'N/A':>12} {'N/A':>12} {'N/A':>10} SKIP (no TSX price)")
            continue

        if cdr_avg_cost is None or cdr_avg_cost <= 0:
            print(f"{symbol:<10} {tsx_price:>12.2f} {'N/A':>12} {'N/A':>10} SKIP (no CDR cost)")
            continue

        ratio = tsx_price / cdr_avg_cost

        # Sanity check: ratio should be between 1 and 100
        if ratio < 1 or ratio > 100:
            print(f"{symbol:<10} {tsx_price:>12.2f} {cdr_avg_cost:>12.2f} {ratio:>10.2f} SKIP (ratio out of range)")
            continue

        # Store in companies table
        try:
            supabase.table("companies").update({
                "cdr_ratio": round(ratio, 2),
                "cdr_ratio_date": date.today().isoformat(),
            }).eq("company_id", cid).execute()
            print(f"{symbol:<10} {tsx_price:>12.2f} {cdr_avg_cost:>12.2f} {ratio:>10.2f} OK")
            updated += 1
        except Exception as e:
            print(f"{symbol:<10} {tsx_price:>12.2f} {cdr_avg_cost:>12.2f} {ratio:>10.2f} ERROR: {e}")

    print(f"\nBackfill complete: {updated}/{len(cdr_cids)} companies updated.")


def verify():
    """Verify stored ratios."""
    result = (
        supabase.table("companies")
        .select("company_id, ticker_symbol, cdr_ratio, cdr_ratio_date")
        .not_.is_("cdr_ratio", "null")
        .execute()
    )
    print(f"\nVerification: {len(result.data or [])} companies have cdr_ratio set:")
    for row in (result.data or []):
        print(f"  {row['ticker_symbol']}: ratio={row['cdr_ratio']}, date={row['cdr_ratio_date']}")


if __name__ == "__main__":
    print("=" * 60)
    print("CDR RATIO BACKFILL")
    print("=" * 60)
    compute_and_store_ratios()
    verify()
