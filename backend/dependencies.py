"""
Dependency Injection Configuration
Centralizes all service and repository instantiation.
Allows for easy testing and swapping implementations.
"""

import logging
from fastapi import Request
from slowapi import Limiter

# Repositories
from infrastructure.repositories.supabase_repository import (
    SupabaseWatchlistRepository,
    SupabaseUserRepository,
)
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository

# Providers
from providers.yfinance_provider import YFinanceProvider
from providers.defeat_beta_provider import DefeatBetaProvider

# Services
from application.services.watchlist_service import WatchlistService

logger = logging.getLogger(__name__)


# ============================================================================
# AUTHENTICATION DEPENDENCY
# ============================================================================

def get_current_user_dep():
    """
    Placeholder dependency for current user.
    This will be overridden in main.py with the actual Firebase auth implementation.
    
    Ensures that our API endpoints are decoupled from the concrete auth implementation.
    """
    pass


# ============================================================================
# RATE LIMITING
# ============================================================================

def get_user_identifier(request: Request) -> str:
    """Get unique identifier for rate limiting (by client IP)."""
    return request.client.host


limiter = Limiter(key_func=get_user_identifier)


# ============================================================================
# PROVIDER SINGLETONS
# ============================================================================
# These are initialized once and reused across requests

_yfinance_provider: YFinanceProvider = None
_defeat_beta_provider: DefeatBetaProvider = None


def get_yfinance_provider() -> YFinanceProvider:
    """
    Get or create YFinanceProvider singleton.
    
    Used for: Real-time stock prices, company details
    """
    global _yfinance_provider
    if _yfinance_provider is None:
        logger.debug("Initializing YFinanceProvider")
        _yfinance_provider = YFinanceProvider()
    return _yfinance_provider


def get_defeat_beta_provider() -> DefeatBetaProvider:
    """
    Get or create DefeatBetaProvider singleton.
    
    Used for: Financial statements, earnings data, dividends
    Falls back to yfinance if defeat-beta fails
    """
    global _defeat_beta_provider
    if _defeat_beta_provider is None:
        logger.debug("Initializing DefeatBetaProvider")
        yfinance = get_yfinance_provider()
        _defeat_beta_provider = DefeatBetaProvider(yfinance_provider=yfinance)
    return _defeat_beta_provider


# ============================================================================
# REPOSITORY SINGLETONS
# ============================================================================

_watchlist_repo: SupabaseWatchlistRepository = None
_user_repo: SupabaseUserRepository = None
_financial_repo: SupabaseFinancialRepository = None


def get_watchlist_repository() -> SupabaseWatchlistRepository:
    """Get or create WatchlistRepository singleton."""
    global _watchlist_repo
    if _watchlist_repo is None:
        logger.debug("Initializing SupabaseWatchlistRepository")
        _watchlist_repo = SupabaseWatchlistRepository()
    return _watchlist_repo


def get_user_repository() -> SupabaseUserRepository:
    """Get or create UserRepository singleton."""
    global _user_repo
    if _user_repo is None:
        logger.debug("Initializing SupabaseUserRepository")
        _user_repo = SupabaseUserRepository()
    return _user_repo


def get_financial_repository() -> SupabaseFinancialRepository:
    """Get or create FinancialRepository singleton."""
    global _financial_repo
    if _financial_repo is None:
        logger.debug("Initializing SupabaseFinancialRepository")
        _financial_repo = SupabaseFinancialRepository()
    return _financial_repo


# ============================================================================
# SERVICE DEPENDENCIES
# ============================================================================

def get_watchlist_service() -> WatchlistService:
    """
    Get WatchlistService with all dependencies injected.
    
    WatchlistService handles:
    - Watchlist CRUD operations
    - Adding stocks with financial data loading
    - On-demand financial data refresh
    
    Dependencies:
    - YFinanceProvider: Real-time prices
    - DefeatBetaProvider: Financial statements
    - SupabaseWatchlistRepository: Watchlist DB ops
    - SupabaseUserRepository: User DB ops
    - SupabaseFinancialRepository: Financial data DB ops
    """
    return WatchlistService(
        stock_provider=get_yfinance_provider(),
        watchlist_repo=get_watchlist_repository(),
        user_repo=get_user_repository(),
        financial_repo=get_financial_repository(),
        defeat_beta_provider=get_defeat_beta_provider(),
    )


# ============================================================================
# DEPENDENCY OVERRIDE MAPPING
# ============================================================================
# Used in main.py:
# app.dependency_overrides[get_current_user_dep] = get_current_user_from_firebase
# app.dependency_overrides[get_watchlist_service] = get_watchlist_service

__all__ = [
    # Authentication
    "get_current_user_dep",
    # Rate limiting
    "get_user_identifier",
    "limiter",
    # Providers
    "get_yfinance_provider",
    "get_defeat_beta_provider",
    # Repositories
    "get_watchlist_repository",
    "get_user_repository",
    "get_financial_repository",
    # Services
    "get_watchlist_service",
]