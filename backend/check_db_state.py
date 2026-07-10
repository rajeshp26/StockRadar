"""Check current state of price_history and identify remaining bad data."""
import os
os.environ["ENVIRONMENT"] = "development"
from database import supabase as client
from datetime import date

# Check what data_source entries exist
resp = client.table("price_history").select("data_source", count="exact").execute()
print(f"Total price_history rows: {resp.count if hasattr(resp, 'count') else len(resp.data)}")

# Group by data_source
sources = {}
for r in (resp.data or []):
    s = r.get("data_source") or "unknown"
    sources[s] = sources.get(s, 0) + 1
print(f"By data_source: {sources}")

# Check RY specifically
for cid, sym in [(2808, "RY"), (2225, "TD"), (1341, "ENB"), (1117, "SHOP"), (69, "AAPL")]:
    resp2 = client.table("price_history").select("price_date, close_price, data_source").eq("company_id", cid).order("price_date", desc=True).limit(20).execute()
    print(f"\n{sym} (cid={cid}) last 20 entries:")
    for r in (resp2.data or []):
        print(f"  {r['price_date']}: ${r['close_price']} [{r.get('data_source')}]")

# Check for weekend data
print("\n=== Weekend data check ===")
resp3 = client.table("price_history").select("price_date, close_price, data_source, company_id", count="exact").execute()
weekend_count = 0
for r in (resp3.data or []):
    try:
        dt = date.fromisoformat(str(r["price_date"]))
        if dt.weekday() >= 5:  # Saturday=5, Sunday=6
            weekend_count += 1
            if weekend_count <= 10:
                print(f"  {r['price_date']} (weekend) cid={r['company_id']} ${r['close_price']} [{r.get('data_source')}]")
    except:
        pass
print(f"Total weekend entries: {weekend_count}")
