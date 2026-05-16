"""
Dependency Injection Configuration
Centralizes all service and repository instantiation.
Allows for easy testing and swapping implementations.

SECURITY PRINCIPLES (fail-closed):
- Authentication dependency must raise if not overridden.
- Rate limiting identifier should not trust proxy headers unless explicitly enabled.
"""

import logging
import os
from fastapi import Request, HTTPException, status
from slowapi import Limiter

# Repositories
from infrastructure.repositories.supabase_repository import (
    SupabaseWatchlistRepository,
    SupabaseUserRepository,
)
from infrastructure.repositories.financial_repository import SupabaseFinancialRepository
from infrastructure.repositories.valuation_repository import ValuationRepository

# Providers
from providers.yfinance_provider import YFinanceProvider
from providers.defeat_beta_provider import DefeatBetaProvider
from providers.edgar_provider import EdgarToolsProvider

# Services
from application.services.watchlist_service import WatchlistService
from application.services.recompute_guard import RecomputeGuard
from application.services.valuation_service import ValuationService

logger = logging.getLogger(__name__)


# ============================================================================
# AUTHENTICATION DEPENDENCY (FAIL-CLOSED PLACEHOLDER)
# ============================================================================

def get_current_user_dep():
    """
    Placeholder dependency for current user.

    This MUST be overridden in main.py with the actual auth implementation.
    SECURITY: Fail closed if not configured, so endpoints never run unauthenticated
    due to misconfiguration.
    """
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Authentication dependency not configured. Ensure main.py sets dependency_overrides.",
    )


# ============================================================================
# RATE LIMITING
# ============================================================================

def get_user_identifier(request: Request) -> str:
    """
    Get unique identifier for rate limiting.

    Default: client IP from the ASGI connection (request.client.host).
    Optional: use X-Forwarded-For ONLY if TRUST_PROXY_HEADERS=true
    to avoid spoofing in untrusted deployments.
    """
    ip = "unknown"
    try:
        if request.client and request.client.host:
            ip = request.client.host
    except Exception:
        ip = "unknown"

    trust_proxy = os.getenv("TRUST_PROXY_HEADERS", "false").strip().lower() in ("1", "true", "yes")
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            # XFF may contain a chain: "client, proxy1, proxy2"
            first = xff.split(",")[0].strip()
            if first:
                ip = first

    return ip


limiter = Limiter(key_func=get_user_identifier)


# ============================================================================
# PROVIDER SINGLETONS
# ============================================================================

_yfinance_provider: YFinanceProvider = None
_defeat_beta_provider: DefeatBetaProvider = None


def get_yfinance_provider() -> YFinanceProvider:
    """
    Get or create YFinanceProvider singleton.
    Used for: Real-time stock prices, company details.
    """
    global _yfinance_provider
    if _yfinance_provider is None:
        logger.debug("Initializing YFinanceProvider")
        _yfinance_provider = YFinanceProvider()
    return _yfinance_provider

_edgar_provider: EdgarToolsProvider = None
_stockdex_provider: "StockdexMacrotrendsProvider" = None

def get_edgar_provider() -> EdgarToolsProvider:
    """
    Get or create EdgarToolsProvider singleton.

    Covers: IS / BS / CF fetched directly from SEC EDGAR 10-K and 10-Q filings.
    Position in chain: DefeatBeta → EdgarTools → YFinance.

    Requires EDGAR_IDENTITY env var:
        EDGAR_IDENTITY="YourName yourname@example.com"
    """
    global _edgar_provider
    if _edgar_provider is None:
        logger.debug("Initializing EdgarToolsProvider")
        _edgar_provider = EdgarToolsProvider()
    return _edgar_provider

def get_stockdex_provider() -> "StockdexMacrotrendsProvider":
    """Get or create StockdexMacrotrendsProvider singleton."""
    global _stockdex_provider
    if _stockdex_provider is None:
        logger.debug("Initializing StockdexMacrotrendsProvider")
        from providers.stockdex_provider import StockdexMacrotrendsProvider
        _stockdex_provider = StockdexMacrotrendsProvider()
    return _stockdex_provider


def get_defeat_beta_provider() -> DefeatBetaProvider:
    """
    Get or create DefeatBetaProvider singleton.

    Provider chain:
        1. DefeatBeta  — primary (proprietary financial data API)
        2. Stockdex    — fallback 1 (Macrotrends scraper, 15+ years of IS/BS/CF)
        3. EdgarTools  — fallback 2 (SEC EDGAR XBRL filings, IS/BS/CF only)
        4. YFinance    — fallback 3 (scrape-based, covers everything prior sources cannot)
    """
    global _defeat_beta_provider
    if _defeat_beta_provider is None:
        logger.debug("Initializing DefeatBetaProvider")
        _defeat_beta_provider = DefeatBetaProvider(
            yfinance_provider=get_yfinance_provider(),
            edgar_provider=get_edgar_provider(),
            stockdex_provider=get_stockdex_provider(),
        )
    return _defeat_beta_provider


# ============================================================================
# REPOSITORY SINGLETONS
# ============================================================================

_watchlist_repo: SupabaseWatchlistRepository = None
_user_repo: SupabaseUserRepository = None
_financial_repo: SupabaseFinancialRepository = None
_valuation_repo: ValuationRepository = None


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


def get_valuation_repository() -> ValuationRepository:
    """Get or create ValuationRepository singleton."""
    global _valuation_repo
    if _valuation_repo is None:
        logger.debug("Initializing ValuationRepository")
        _valuation_repo = ValuationRepository()
    return _valuation_repo


# ============================================================================
# SERVICE DEPENDENCIES
# ============================================================================

def get_watchlist_service() -> WatchlistService:
    """
    Get WatchlistService with all dependencies injected.
    """
    return WatchlistService(
        stock_provider=get_yfinance_provider(),
        watchlist_repo=get_watchlist_repository(),
        user_repo=get_user_repository(),
        financial_repo=get_financial_repository(),
        defeat_beta_provider=get_defeat_beta_provider(),
    )


_recompute_guard: RecomputeGuard = None
_valuation_service: ValuationService = None


def get_recompute_guard() -> RecomputeGuard:
    """Get or create RecomputeGuard singleton (depends on ValuationRepository)."""
    global _recompute_guard
    if _recompute_guard is None:
        logger.debug("Initializing RecomputeGuard")
        _recompute_guard = RecomputeGuard(get_valuation_repository())
    return _recompute_guard


def get_valuation_service() -> ValuationService:
    """
    Get or create ValuationService singleton.
    Centralizes service construction instead of instantiating in route handlers.
    """
    global _valuation_service
    if _valuation_service is None:
        logger.debug("Initializing ValuationService")
        _valuation_service = ValuationService(get_valuation_repository(), get_recompute_guard())
    return _valuation_service


# ============================================================================
# DEPENDENCY OVERRIDE MAPPING
# ============================================================================
# Used in main.py:
# app.dependency_overrides[get_current_user_dep] = get_current_user_from_firebase
# app.dependency_overrides[...] = ...

__all__ = [
    # Authentication
    "get_current_user_dep",
    # Rate limiting
    "get_user_identifier",
    "limiter",
    # Providers
    "get_yfinance_provider",
    "get_edgar_provider",
    "get_defeat_beta_provider",
    # Repositories
    "get_watchlist_repository",
    "get_user_repository",
    "get_financial_repository",
    "get_valuation_repository",
    # Services
    "get_watchlist_service",
    "get_recompute_guard",
    "get_valuation_service",
]