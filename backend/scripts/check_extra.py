"""Check other users + import history columns."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import supabase
users = supabase.table("users").select("user_id, email").execute()
for u in users.data or []:
    accts = supabase.table("portfolio_accounts").select("account_id, account_type").eq("user_id", u["user_id"]).execute()
    aids = [a["account_id"] for a in accts.data or []]
    print(f"User {u['email']} (id={u['user_id']}): accounts={aids}")
r = supabase.table("portfolio_import_history").select("*").limit(1).execute()
print(f"Import history columns: {list((r.data or [{}])[0].keys())}")