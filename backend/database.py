from supabase import create_client, Client
from config import settings

# Initialize Supabase client using settings
# If SUPABASE_SERVICE_ROLE_KEY is missing, initialization will still happen but queries will fail
# This is preferred for security over hardcoding local keys.
supabase: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

def get_supabase_user_client(id_token: str = None) -> Client:
    """
    Returns the Supabase client. 
    In the future, this can be extended to create a client with a user-specific JWT.
    """
    return supabase
