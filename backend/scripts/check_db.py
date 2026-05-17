#!/usr/bin/env python3
import sys
sys.path.insert(0, ".")

from database import supabase

result = supabase.table("institutional_investors").select("investor_id, investor_name, cik, last_filed_period").order("investor_id").execute()
print("Investors:")
for r in (result.data or []):
    print(f"  {r['investor_id']}: {r['investor_name']} ({r['cik']}) - Last: {r.get('last_filed_period')}")

result2 = supabase.table("institutional_holdings").select("investor_id").execute()
print(f"\nTotal holdings: {len(result2.data or [])}")