from supabase import create_client, Client

# Supabase setup - credentials should ideally be in environment variables
url: str = "https://viqdqgxcumcdhqxooplw.supabase.co"
key: str = "sb_publishable_u27S_tnQtxoeqDwTqc39RQ_e9igg_LM"
supabase: Client = create_client(url, key)
