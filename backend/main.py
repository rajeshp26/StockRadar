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
from api.chat import router as chat_router
from config import settings
from database import supabase
from auth import get_current_user
from dependencies import get_current_user_dep, limiter
from api.portfolio import router as portfolio_router
from api.stocks import router as stocks_router

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
                logger.debug("[PRICE-MONITOR-DIAG] No active symbol subscribers — sleeping 5s")
                await asyncio.sleep(min(5, interval))
                continue
            
            logger.debug(f"[PRICE-MONITOR-DIAG] Fetching prices for {len(active_symbols)} symbols: {active_symbols}")
            tickers = yf.Tickers(active_symbols)
            updated_count = 0
            skipped_count = 0
            for symbol in active_symbols:
                ticker = tickers.tickers.get(symbol)
                if not ticker:
                    logger.debug(f"[PRICE-MONITOR-DIAG] {symbol}: ticker object is None")
                    skipped_count += 1
                    continue
                
                info = getattr(ticker, "info", {}) or {}
                if not info:
                    logger.debug(f"[PRICE-MONITOR-DIAG] {symbol}: info dict is empty")
                    skipped_count += 1
                    continue
                
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                prev_close = info.get("regularMarketPreviousClose")
                
                # Log ALL available close-related keys for diagnostics
                close_keys = [k for k in info.keys() if 'close' in k.lower()]
                current_keys = [k for k in info.keys() if 'price' in k.lower() or 'current' in k.lower()]
                logger.debug(f"[PRICE-MONITOR-DIAG] {symbol}: currentPrice={current_price}, prev_close={prev_close}, close_keys={close_keys}, current_keys={current_keys}")
                
                if current_price and prev_close:
                    change = float(current_price) - float(prev_close)
                    change_percent = (change / float(prev_close)) * 100
                    await broadcast_stock_update(symbol, current_price, change, change_percent)
                    updated_count += 1
                else:
                    skipped_count += 1
                    logger.debug(f"[PRICE-MONITOR-DIAG] {symbol}: SKIPPED broadcast — current_price={current_price}, prev_close={prev_close}")
            
            logger.debug(f"[PRICE-MONITOR-DIAG] Cycle complete: {updated_count} updated, {skipped_count} skipped")
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
    # No Firebase initialization — Supabase JWT verification uses lazy JWKS fetch
    
    # SSE price monitor (stays in FastAPI - real-time user-facing)
    price_task = asyncio.create_task(background_price_monitor(), name="price_monitor")
    app.state.tasks["price_monitor"] = price_task
    logger.info("✅ Price monitor started")

    # DuckDB cache pre-warm (non-blocking)
    from dependencies import get_defeat_beta_provider
    provider = get_defeat_beta_provider()
    warm_task = asyncio.create_task(provider.warm_cache(), name="duckdb_warm")
    app.state.tasks["duckdb_warm"] = warm_task
    
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


@app.middleware("http")
async def clear_request_cache_middleware(request, call_next):
    try:
        response = await call_next(request)
        return response
    finally:
        try:
            from dependencies import get_cache_manager
            get_cache_manager().clear_request_cache()
        except Exception as e:
            logger.error("Failed to clear request cache: %s", e)

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
app.include_router(chat_router)
app.include_router(analysis.router)
app.include_router(super_investors.router)
app.include_router(portfolio_router)
app.include_router(stocks_router)