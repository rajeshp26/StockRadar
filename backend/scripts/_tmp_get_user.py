"""Get real user auth_id for mock."""
import sys
sys.path.insert(0, ".")
from database import supabase
r = supabase.table("users").select("user_id, auth_id").eq("email", "rajeshp01@gmail.com").execute()
for row in r.data or []:
    print(f"user_id={row['user_id']} auth_id={row['auth_id']}")
if not r.data:
    r = supabase.table("users").select("user_id, auth_id").limit(3).execute()
    print("Sample users:")
    for row in (r.data or [])[:3]:
        print(f"  user_id={row.get('user_id')} auth_id={row.get('auth_id')}")