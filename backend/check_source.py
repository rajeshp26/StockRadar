import os
os.environ["ENVIRONMENT"] = "development"
from database import supabase as client

resp = client.table("price_history").select("company_id, data_source, price_date").in_("price_date", ["2026-05-29", "2026-06-18"]).limit(5).execute()
print(f"Remaining bad data: {len(resp.data)} rows")
for r in (resp.data or []):
    print(f"  company_id={r['company_id']}, date={r['price_date']}, source={r.get('data_source')}")
