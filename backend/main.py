# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import asyncio
import logging
import yfinance as yf
from typing import Optional, Dict, Any

from api import watchlists, watchlist_items, users, valuations
from api import analysis
from api import super_investors
from config import settings
from database import supabase
from auth import get_current_user, initialize_firebase_app
from dependencies import get_current_user_dep, limiter

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO))
logger = logging.getLogger("stockerpro.main")

# -----------------------------------------------------------------------------
# Background: real-time price monitor (existing)
# -----------------------------------------------------------------------------
async def background_price_monitor():
    """
    Background task to monitor and broadcast real-time stock prices.
    Uses yfinance every N seconds based on settings.SSE_UPDATE_INTERVAL_SECONDS.
    """
    interval = max(1, int(getattr(settings, "SSE_UPDATE_INTERVAL_SECONDS", 10)))
    while True:
        try:
            from api.watchlists import symbol_subscribers, broadcast_stock_update
            active_symbols = list(symbol_subscribers.keys())
            if not active_symbols:
                await asyncio.sleep(min(5, interval))
                continue
            
            tickers = yf.Tickers(active_symbols)
            for symbol in active_symbols:
                ticker = tickers.tickers.get(symbol)
                if not ticker:
                    continue
                
                info = getattr(ticker, "info", {}) or {}
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                prev_close = info.get("regularMarketPreviousClose")
                
                if current_price and prev_close:
                    change = float(current_price) - float(prev_close)
                    change_percent = (change / float(prev_close)) * 100
                    await broadcast_stock_update(symbol, current_price, change, change_percent)
            
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break  # graceful shutdown
        except Exception as e:
            logger.error(f"[PriceMonitor] error: {e}", exc_info=True)
            await asyncio.sleep(interval)

# -----------------------------------------------------------------------------
# Lifespan (startup/shutdown)
# -----------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"StockerPro Backend starting in {settings.ENVIRONMENT} mode.")
    
    # Centralize state
    app.state.tasks: Dict[str, asyncio.Task] = {}
    
    # STARTUP ---------------------------------------------------------------
    initialize_firebase_app()
    
    # SSE price monitor (stays in FastAPI - real-time user-facing)
    price_task = asyncio.create_task(background_price_monitor(), name="price_monitor")
    app.state.tasks["price_monitor"] = price_task
    logger.info("✅ Price monitor started")
    
    # ──────────────────────────────────────────────────────────────────────
    # SCHEDULERS MOVED TO SEPARATE WORKER PROCESS
    # ──────────────────────────────────────────────────────────────────────
    # All three schedulers (Super Investors, Market Data, Earnings) now run
    # in scheduler_worker.py to prevent blocking FastAPI HTTP requests.
    #
    # To start the worker:
    #   python scheduler_worker.py
    #
    # See deployment docs for systemd/docker setup.
    # ──────────────────────────────────────────────────────────────────────
    
    logger.info("ℹ️  Schedulers run in separate worker process (scheduler_worker.py)")
    
    try:
        yield
    finally:
        # SHUTDOWN ----------------------------------------------------------
        # Cancel background tasks
        for tname, task in list(app.state.tasks.items()):
            try:
                task.cancel()
            except Exception:
                pass
        
        for tname, task in list(app.state.tasks.items()):
            try:
                await task
                logger.info(f"⏹️  Task '{tname}' stopped")
            except asyncio.CancelledError:
                logger.info(f"⏹️  Task '{tname}' cancelled (normal)")
            except Exception as e:
                logger.error(f"Task '{tname}' error during cancel: {e}", exc_info=True)
        
        logger.info("🧹 Shutdown complete")

# -----------------------------------------------------------------------------
# FastAPI app
# -----------------------------------------------------------------------------
app = FastAPI(
    title="StockerPro API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
)

# DI & middleware
app.dependency_overrides[get_current_user_dep] = get_current_user
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    max_age=3600,
)

# -----------------------------------------------------------------------------
# System endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}

@app.get("/ready", tags=["System"])
async def readiness_check():
    try:
        supabase.table("users").select("user_id").limit(1).execute()
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready")

@app.get("/scheduler/status", tags=["System"])
async def schedulers_status():
    """
    Scheduler status endpoint - returns info about worker process.
    Note: Schedulers now run in scheduler_worker.py (separate process).
    This endpoint provides static config info only.
    """
    return {
        "environment": settings.ENVIRONMENT,
        "worker_process": {
            "note": "Schedulers run in separate worker process (scheduler_worker.py)",
            "super_investors": {
                "enabled": getattr(settings, "ENABLE_SUPER_INVESTORS_SCHEDULER", True),
                "interval_hours": getattr(settings, "SUPER_INVESTORS_REFRESH_INTERVAL_HOURS", 24),
            },
            "market_data": {
                "enabled": getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", True),
                "interval_hours": getattr(settings, "MARKET_DATA_REFRESH_INTERVAL_HOURS", 24),
            },
            "earnings": {
                "enabled": getattr(settings, "ENABLE_EARNINGS_SCHEDULER", False),
                "interval_hours": getattr(settings, "EARNINGS_REFRESH_CHECK_INTERVAL_HOURS", 2),
            },
        },
    }

# -----------------------------------------------------------------------------
# API routers
# -----------------------------------------------------------------------------
app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)
app.include_router(valuations.router)
app.include_router(analysis.router)
app.include_router(super_investors.router)