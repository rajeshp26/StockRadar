"""
One-time migration: multiply contaminated financial rows by 1,000,000.

Macrotrends (via Stockdex) reports values in millions. The gap-fill pipeline
stored them as full dollars, causing all large-cap companies' fallback-filled
quarters to be off by 1,000,000x.

Strategy:
  1. Identify companies with max_revenue > $10B  ("large caps")
  2. For each, find quarterly rows where sentinel column (revenue / total_assets / cfo)
     is between $0 and $1M (the contaminated range)
  3. Multiply all numeric columns in those rows by 1,000,000
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import logging
import ssl

ssl._create_default_https_context = ssl._create_unverified_context
import urllib3

urllib3.disable_warnings()
import httpx

_orig_init = httpx.Client.__init__
def _patched_init(self, *args, **kwargs):
    kwargs["verify"] = False
    return _orig_init(self, *args, **kwargs)
httpx.Client.__init__ = _patched_init

logging.disable(logging.CRITICAL)
from database import supabase

TABLE_CONFIG = [
    {
        "table": "income_statements",
        "pk": "is_id",
        "sentinel": "revenue",
        "numeric_cols": [
            "revenue", "cost_of_goods_sold", "gross_profit",
            "operating_expenses", "rd_expenses", "sga_expenses",
            "operating_income", "interest_expense", "tax_expense",
            "net_income", "ebitda", "ebit",
            "non_operating_income_expense", "pretax_income",
            "equity_in_earnings", "minority_interest",
            "income_from_continuing_operations", "discontinued_operations",
            "net_income_to_common", "preferred_dividends",
            "interest_income", "effective_tax_rate",
            "total_unusual_items", "special_charges",
        ],
        "per_share_cols": ["eps_basic", "eps_diluted"],
        "int_cols": ["shares_outstanding_basic", "shares_outstanding_diluted"],
    },
    {
        "table": "cash_flow_statements",
        "pk": "cf_id",
        "sentinel": "cash_from_operating_activities",
        "numeric_cols": [
            "cash_from_operating_activities", "net_income",
            "depreciation_amortization", "capital_expenditures",
            "cash_from_investing_activities", "cash_from_financing_activities",
            "dividends_paid", "change_in_working_capital",
            "deferred_taxes", "stock_based_compensation",
            "acquisitions", "asset_sales", "investment_purchases",
            "debt_issued", "debt_repayment", "share_repurchases",
            "share_issuance",
        ],
        "per_share_cols": [],
        "int_cols": [],
    },
    {
        "table": "balance_sheets",
        "pk": "bs_id",
        "sentinel": "total_assets",
        "numeric_cols": [
            "total_assets", "current_assets",
            "cash_and_cash_equivalents", "accounts_receivable", "inventory",
            "property_plant_equipment_net", "intangible_assets", "goodwill",
            "total_liabilities", "current_liabilities", "accounts_payable",
            "short_term_debt", "long_term_debt", "total_debt",
            "shareholders_equity", "retained_earnings", "common_stock",
            "long_term_investments", "other_non_current_assets",
            "other_current_liabilities", "minority_interest",
            "total_liabilities_and_equity",
        ],
        "per_share_cols": [],
        "int_cols": [],
    },
]

def get_large_cap_ids() -> list[int]:
    resp = supabase.table("income_statements") \
        .select("company_id") \
        .gt("revenue", 10_000_000_000) \
        .not_.is_("revenue", "null") \
        .execute()
    return list(set(r["company_id"] for r in resp.data))


def multiply_col(col_name: str, val) -> float:
    if val is None:
        return None
    return float(val) * 1_000_000


def multiply_int(col_name: str, val) -> int:
    if val is None:
        return None
    return int(float(val) * 1_000_000)


def fix_table(cfg: dict, company_ids: list[int], dry_run: bool = True):
    table = cfg["table"]
    pk = cfg["pk"]
    sentinel = cfg["sentinel"]
    numeric_cols = cfg["numeric_cols"]
    int_cols = cfg["int_cols"]

    print(f"\n{'='*60}")
    print(f"Table: {table}")
    print(f"{'='*60}")

    total_updated = 0
    total_skipped = 0

    for cid in company_ids:
        resp = supabase.table(table) \
            .select("*") \
            .eq("company_id", cid) \
            .gt(sentinel, 0) \
            .lt(sentinel, 1_000_000) \
            .not_.is_(sentinel, "null") \
            .execute()

        rows = resp.data
        if not rows:
            continue

        for row in rows:
            rid = row.get(pk)
            if not rid:
                print(f"  [WARN] No {pk} for {table} row company={cid}")
                continue

            fy = row.get("fiscal_year")
            fq = row.get("fiscal_quarter")
            rev = row.get(sentinel)
            location = f"company={cid} Q{fq} {fy} (id={rid}, {sentinel}={rev})"

            if abs(float(rev)) >= 1_000_000:
                print(f"  [SKIP] {location} — already fixed")
                total_skipped += 1
                continue

            update = {}

            for col in numeric_cols:
                val = row.get(col)
                if val is not None:
                    update[col] = multiply_col(col, val)

            for col in int_cols:
                val = row.get(col)
                if val is not None:
                    update[col] = multiply_int(col, val)

            if not update:
                print(f"  [SKIP] {location} — no columns to update")
                total_skipped += 1
                continue

            if dry_run:
                print(f"  [DRY]  {location}")
                for k, v in update.items():
                    old = row.get(k)
                    print(f"         {k}: {old} -> {v}")
            else:
                supabase.table(table) \
                    .update(update) \
                    .eq(pk, rid) \
                    .execute()
                print(f"  [OK]   {location} — {len(update)} cols updated")

            total_updated += 1

    print(f"\nResults for {table}: {total_updated} updated, {total_skipped} skipped")
    return total_updated


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("[DRY RUN] No changes will be made. Pass --apply to execute.")
    else:
        print("[LIVE] Updating database.")

    print("Finding large-cap companies (revenue > $10B in any quarter)...")
    large_ids = get_large_cap_ids()
    print(f"Found {len(large_ids)} large-cap companies.")

    total = 0
    for cfg in TABLE_CONFIG:
        total += fix_table(cfg, large_ids, dry_run=dry_run)

    print(f"\n{'='*60}")
    print(f"TOTAL: {total} rows affected")
    if dry_run:
        print("Run with --apply to commit changes.")
