"""
Delete bad price_history entries for 2026-05-29 and 2026-06-18.
These dates have inflated close prices due to yfinance auto_adjust=False issue.
"""
import os

os.environ["ENVIRONMENT"] = "development"
from database import supabase as client

bad_dates = ["2026-05-29", "2026-06-18"]

for d in bad_dates:
    # Count first
    count_resp = client.table("price_history").select("company_id", count="exact").eq("price_date", d).execute()
    count = count_resp.count if hasattr(count_resp, 'count') else len(count_resp.data)
    print(f"Deleting {count} price_history rows for {d}...")

    # Delete
    resp = client.table("price_history").delete().eq("price_date", d).execute()
    deleted = len(resp.data) if resp.data else 0
    print(f"  Deleted {deleted} rows for {d}")

print("Done. The scheduler will re-fetch correct prices on next run.")
