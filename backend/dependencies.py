from fastapi import Depends, Header, HTTPException, Request
from firebase_admin import auth, credentials
import firebase_admin
from slowapi import Limiter
from slowapi.util import get_remote_address
import logging
import os

from config import settings
from domain.interfaces.stock_provider import StockProvider
from domain.interfaces.repository import WatchlistRepository, UserRepository
from application.services.watchlist_service import WatchlistService
from providers.yfinance_provider import YFinanceProvider
from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository, SupabaseUserRepository
from database import get_supabase_user_client

logger = logging.getLogger(__name__)

# ============================================
# 1. Global Limiter Instance
# ============================================
limiter = Limiter(key_func=get_remote_address)

# ============================================
# 2. Robust Firebase Admin Initialization
# ============================================
if not firebase_admin._apps:
    try:
        # Check if service account file exists
        sa_path = os.path.join(os.path.dirname(__file__), "service-account.json")
        
        if os.path.exists(sa_path):
            logger.info("🔑 Initializing Firebase Admin with Service Account file.")
            cred = credentials.Certificate(sa_path)
            firebase_admin.initialize_app(cred)
            logger.info("✅ Firebase Admin initialized successfully with service account")
        else:
            logger.info(f"🌐 Initializing Firebase Admin for project: {settings.FIREBASE_PROJECT_ID} (Public/Workstation Mode)")
            logger.info("   (No service-account.json found; using project ID only to prevent metadata server loops)")
            
            # Force the SDK to skip metadata server auto-discovery
            # This is critical for Cloud Workstations where the metadata server doesn't have proper service account info
            firebase_admin.initialize_app(
                options={'projectId': settings.FIREBASE_PROJECT_ID}
            )
            logger.info("✅ Firebase Admin initialized successfully (public mode)")
            
    except Exception as e:
        logger.error(f"❌ Firebase Admin initialization failed: {e}")
        logger.error("   This may indicate a misconfigured FIREBASE_PROJECT_ID in backend/.env")
        raise

# ============================================
# 3. Dependency Functions
# ============================================

def get_stock_provider() -> StockProvider:
    """Provides stock data service."""
    return YFinanceProvider()

async def verify_firebase_token(authorization: str = Header(None)) -> dict:
    """
    SECURITY LAYER: Verifies the Firebase ID token from the client.
    
    Expects: Authorization: Bearer <firebase_id_token>
    
    Returns: Decoded token with user info (uid, email, etc.)
    
    Raises: HTTPException 401 if token is invalid or missing
    """
    if not authorization or not authorization.startswith("Bearer "):
        logger.warning("❌ Auth attempt without Bearer token")
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Use 'Authorization: Bearer <token>'"
        )

    token = authorization.split("Bearer ")[1]
    try:
        # IMPORTANT: check_revoked=False prevents additional IAM/metadata server calls
        # that often fail in restricted environments like Cloud Workstations.
        # In production, consider using check_revoked=True for security.
        decoded_token = auth.verify_id_token(token, check_revoked=False)
        logger.info(f"✅ Token verified for user: {decoded_token.get('uid')}")
        return decoded_token
        
    except auth.ExpiredIdTokenError:
        logger.warning(f"❌ Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except auth.RevokedIdTokenError:
        logger.warning(f"❌ Token revoked")
        raise HTTPException(status_code=401, detail="Token revoked")
    except Exception as e:
        logger.error(f"❌ Token verification failed: {type(e).__name__}: {e}")
        # Don't expose detailed error in production
        if settings.is_production:
            raise HTTPException(status_code=401, detail="Invalid token")
        else:
            raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")

def get_watchlist_repository(user_token: dict = Depends(verify_firebase_token)) -> WatchlistRepository:
    """Provides watchlist repository (Supabase-backed)."""
    return SupabaseWatchlistRepository(client=get_supabase_user_client())

def get_user_repository(user_token: dict = Depends(verify_firebase_token)) -> UserRepository:
    """Provides user repository (Supabase-backed)."""
    return SupabaseUserRepository(client=get_supabase_user_client())

def get_watchlist_service(
    stock_provider: StockProvider = Depends(get_stock_provider),
    watchlist_repo: WatchlistRepository = Depends(get_watchlist_repository),
    user_repo: UserRepository = Depends(get_user_repository)
) -> WatchlistService:
    """Provides business logic service for watchlist operations."""
    return WatchlistService(stock_provider, watchlist_repo, user_repo)
