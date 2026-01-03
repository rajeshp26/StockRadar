import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://viqdqgxcumcdhqxooplw.supabase.co")

# USE SECRET KEY: The backend must use the Service Role/Secret key to perform operations.
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_NxN3ywf1RrMektnf-rq9hg_FxKFOVoG")

if SUPABASE_KEY.startswith("sb_publishable"):
    print("[DEBUG] WARNING: Using PUBLISHABLE key. RLS will be enforced.")
elif SUPABASE_KEY.startswith("sb_secret"):
    print("[DEBUG] Using SECRET key. RLS will be bypassed.")
else:
    print(f"[DEBUG] Using key starting with: {SUPABASE_KEY[:10]}...")

# Singleton Supabase Client (Admin/Service Access)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_supabase_user_client(id_token: str = None) -> Client:
    """
    Returns the Supabase client. 
    """
    return supabase
