from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import asyncio
import yfinance as yf
import logging
from api import watchlists, watchlist_items, users
from config import settings
from database import supabase
from auth import get_current_user, initialize_firebase_app
from dependencies import get_current_user_dep, limiter  # Updated import
from application.schedulers.earnings_scheduler import EarningsRefreshScheduler  # NEW

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Handles startup and shutdown of background tasks.
    """
    logger.info(f"StockerPro Backend starting in {settings.ENVIRONMENT} mode.")
    
    # ====================================================================
    # STARTUP
    # ====================================================================
    
    # Initialize Firebase
    initialize_firebase_app()
    
    # Start price monitor task (existing)
    monitor_task = asyncio.create_task(background_price_monitor())
    logger.info("✅ Price monitor started")
    
    # Start earnings scheduler (NEW)
    if settings.ENABLE_EARNINGS_SCHEDULER:
        scheduler = EarningsRefreshScheduler()
        await scheduler.start()
        app.state.scheduler = scheduler  # Store for shutdown
        logger.info("✅ Earnings scheduler started")
    else:
        logger.info("⏭️  Earnings scheduler disabled (set ENABLE_EARNINGS_SCHEDULER=true to enable)")
        app.state.scheduler = None
    
    yield
    
    # ====================================================================
    # SHUTDOWN
    # ====================================================================
    
    # Stop price monitor
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    logger.info("⏹️  Price monitor stopped")
    
    # Stop earnings scheduler (NEW)
    if hasattr(app.state, 'scheduler') and app.state.scheduler:
        await app.state.scheduler.stop()
        logger.info("⏹️  Earnings scheduler stopped")


async def background_price_monitor():
    """
    Background task to monitor and broadcast real-time stock prices.
    Runs continuously, fetching prices every 10 seconds.
    """
    while True:
        try:
            from api.watchlists import symbol_subscribers, broadcast_stock_update
            
            active_symbols = list(symbol_subscribers.keys())
            
            if not active_symbols:
                await asyncio.sleep(5)
                continue
            
            tickers = yf.Tickers(active_symbols)
            
            for symbol in active_symbols:
                ticker = tickers.tickers.get(symbol)
                if not ticker:
                    continue
                
                info = ticker.info
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                prev_close = info.get('regularMarketPreviousClose')
                
                if current_price and prev_close:
                    change = float(current_price) - float(prev_close)
                    change_percent = (change / float(prev_close)) * 100
                    await broadcast_stock_update(symbol, current_price, change, change_percent)
            
            await asyncio.sleep(10)
        
        except Exception as e:
            logger.error(f"Price monitor error: {e}")
            await asyncio.sleep(10)


# ============================================================================
# FASTAPI APP INITIALIZATION
# ============================================================================

app = FastAPI(
    title="StockerPro API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
)

# Centralized Dependency Injection
app.dependency_overrides[get_current_user_dep] = get_current_user
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS: Use the unified allowed_origins from config.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

# ============================================================================
# SYSTEM ENDPOINTS
# ============================================================================


@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for load balancers."""
    return {"status": "healthy", "environment": settings.ENVIRONMENT}


@app.get("/ready", tags=["System"])
async def readiness_check():
    """Readiness check endpoint for deployments."""
    try:
        supabase.table("users").select("user_id").limit(1).execute()
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")


@app.get("/scheduler/status", tags=["System"])
async def scheduler_status():
    """
    Get current scheduler status.
    
    Returns:
    - is_running: Whether scheduler is active
    - enabled: Whether scheduler is configured to run
    - interval_hours: How often scheduler runs
    - buffer_days: Earnings window (±N days)
    """
    scheduler = app.state.scheduler if hasattr(app.state, 'scheduler') else None
    
    return {
        "is_running": scheduler.is_running if scheduler else False,
        "enabled": settings.ENABLE_EARNINGS_SCHEDULER,
        "interval_hours": settings.EARNINGS_REFRESH_CHECK_INTERVAL_HOURS,
        "buffer_days": settings.EARNINGS_REFRESH_BUFFER_DAYS,
    }


@app.post("/scheduler/trigger", tags=["System"])
async def trigger_scheduler_now():
    """
    Manually trigger an immediate earnings check.
    
    Useful for: testing, admin operations, force-refresh
    
    Note: Can only be called in development environment
    """
    if settings.is_production:
        raise HTTPException(
            status_code=403,
            detail="Scheduler manual trigger disabled in production"
        )
    
    scheduler = app.state.scheduler if hasattr(app.state, 'scheduler') else None
    
    if not scheduler:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialized"
        )
    
    logger.info("🔄 Manual scheduler trigger requested")
    result = await scheduler.trigger_immediate_check()
    
    return {
        "status": "triggered",
        "result": result,
    }


# ============================================================================
# API ROUTERS
# ============================================================================

app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)