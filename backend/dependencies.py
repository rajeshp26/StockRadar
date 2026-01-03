from fastapi import Depends, Header, HTTPException, Request
from firebase_admin import auth, credentials, initialize_app
import firebase_admin
import os
from slowapi import Limiter
from slowapi.util import get_remote_address

from domain.interfaces.stock_provider import StockProvider
from domain.interfaces.repository import WatchlistRepository, UserRepository
from application.services.watchlist_service import WatchlistService
from providers.yfinance_provider import YFinanceProvider
from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository, SupabaseUserRepository
from database import get_supabase_user_client

# 1. Global Limiter Instance
limiter = Limiter(key_func=get_remote_address)

# 2. Initialize Firebase Admin
if not firebase_admin._apps:
    try:
        # EXPLICIT: Use the project ID from the frontend to avoid audience mismatch
        PROJECT_ID = "studio-5026044967-252d9"
        print(f"[DEBUG] Initializing Firebase Admin for project: {PROJECT_ID}")
        firebase_admin.initialize_app(options={'projectId': PROJECT_ID})
        print("[DEBUG] Firebase Admin initialized successfully.")
    except Exception as e:
        print(f"[DEBUG] Firebase Admin initialization failed: {e}")
        # Fallback to default
        firebase_admin.initialize_app()

def get_stock_provider() -> StockProvider:
    return YFinanceProvider()

async def get_id_token(authorization: str = Header(None)) -> str:
    """Helper to extract raw ID token from header."""
    if not authorization:
        print("[DEBUG] get_id_token: No authorization header found.")
        raise HTTPException(status_code=401, detail="Authentication required")
    
    if not authorization.startswith("Bearer "):
        print(f"[DEBUG] get_id_token: Authorization header does not start with Bearer. Header: {authorization[:20]}...")
        raise HTTPException(status_code=401, detail="Authentication required")
        
    token = authorization.split("Bearer ")[1]
    return token

def get_watchlist_repository(token: str = Depends(get_id_token)) -> WatchlistRepository:
    # Return a repository instance bound to the specific user's token for RLS
    client = get_supabase_user_client(token)
    return SupabaseWatchlistRepository(client=client)

def get_user_repository(token: str = Depends(get_id_token)) -> UserRepository:
    # Return a repository instance bound to the specific user's token for RLS
    client = get_supabase_user_client(token)
    return SupabaseUserRepository(client=client)

def get_watchlist_service(
    stock_provider: StockProvider = Depends(get_stock_provider),
    watchlist_repo: WatchlistRepository = Depends(get_watchlist_repository),
    user_repo: UserRepository = Depends(get_user_repository)
) -> WatchlistService:
    return WatchlistService(stock_provider, watchlist_repo, user_repo)

async def verify_firebase_token(authorization: str = Header(None)) -> dict:
    """Verify Firebase ID token and return decoded user info."""
    if not authorization:
        print("[DEBUG] verify_firebase_token: No authorization header found.")
        raise HTTPException(status_code=401, detail="Missing or invalid authentication credentials")

    if not authorization.startswith("Bearer "):
        print(f"[DEBUG] verify_firebase_token: Authorization header does not start with Bearer. Header: {authorization[:20]}...")
        raise HTTPException(status_code=401, detail="Missing or invalid authentication credentials")
    
    token = authorization.split("Bearer ")[1]
    print(f"[DEBUG] verify_firebase_token: Attempting to verify token (len: {len(token)})...")
    try:
        # ENV FIX: Disable check_revoked=True in Cloud Workstations as it requires a properly configured 
        # service account that isn't always present in dev environments.
        decoded_token = auth.verify_id_token(token, check_revoked=False)
        print(f"[DEBUG] verify_firebase_token: Successfully verified token for UID: {decoded_token.get('uid')}")
        return decoded_token
    except auth.ExpiredIdTokenError:
        print("[DEBUG] verify_firebase_token: Token has expired")
        raise HTTPException(status_code=401, detail="Token has expired")
    except auth.InvalidIdTokenError as e:
        print(f"[DEBUG] verify_firebase_token: Invalid token: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")
    except Exception as e:
        print(f"[SECURITY ERROR] Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")
