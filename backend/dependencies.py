from fastapi import Depends
from domain.interfaces.stock_provider import StockProvider
from domain.interfaces.repository import WatchlistRepository, UserRepository
from application.services.watchlist_service import WatchlistService
from providers.yfinance_provider import YFinanceProvider
from infrastructure.repositories.supabase_repository import SupabaseWatchlistRepository, SupabaseUserRepository

def get_stock_provider() -> StockProvider:
    return YFinanceProvider()

def get_watchlist_repository() -> WatchlistRepository:
    return SupabaseWatchlistRepository()

def get_user_repository() -> UserRepository:
    return SupabaseUserRepository()

def get_watchlist_service(
    stock_provider: StockProvider = Depends(get_stock_provider),
    watchlist_repo: WatchlistRepository = Depends(get_watchlist_repository),
    user_repo: UserRepository = Depends(get_user_repository)
) -> WatchlistService:
    return WatchlistService(stock_provider, watchlist_repo, user_repo)
