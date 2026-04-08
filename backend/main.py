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
from config import settings
from database import supabase
from auth import get_current_user, initialize_firebase_app
from dependencies import get_current_user_dep, limiter
from application.schedulers.earnings_scheduler import EarningsRefreshScheduler
from application.schedulers.market_data_scheduler import MarketDataRefreshScheduler

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
    app.state.schedulers: Dict[str, Any] = {"earnings": None, "market_data": None}

    # STARTUP ---------------------------------------------------------------
    initialize_firebase_app()

    # SSE price monitor
    price_task = asyncio.create_task(background_price_monitor(), name="price_monitor")
    app.state.tasks["price_monitor"] = price_task
    logger.info("✅ Price monitor started")

    # Earnings scheduler
    if getattr(settings, "ENABLE_EARNINGS_SCHEDULER", False):
        try:
            earnings_sched = EarningsRefreshScheduler()
            await earnings_sched.start()
            app.state.schedulers["earnings"] = earnings_sched
            logger.info("✅ Earnings scheduler started")
        except Exception as e:
            logger.error(f"❌ Failed to start Earnings scheduler: {e}", exc_info=True)
    else:
        logger.info("⏭️  Earnings scheduler disabled (ENABLE_EARNINGS_SCHEDULER=false)")

    # Market Data scheduler (flag may not exist; default True to match design intent)
    if getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", True):
        try:
            market_sched = MarketDataRefreshScheduler()
            await market_sched.start()
            app.state.schedulers["market_data"] = market_sched
            logger.info("✅ Market Data scheduler started")
        except Exception as e:
            logger.error(f"❌ Failed to start Market Data scheduler: {e}", exc_info=True)
    else:
        logger.info("⏭️  Market Data scheduler disabled (ENABLE_MARKET_DATA_SCHEDULER=false)")

    # Back-compat handle
    app.state.scheduler = app.state.schedulers["earnings"]

    try:
        yield
    finally:
        # SHUTDOWN ----------------------------------------------------------
        # Stop schedulers
        for name, sched in list(app.state.schedulers.items()):
            if sched:
                try:
                    await sched.stop()
                    logger.info(f"⏹️  {name.capitalize()} scheduler stopped")
                except Exception as e:
                    logger.error(f"Error stopping {name} scheduler: {e}", exc_info=True)

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
# Helpers for status payloads
# -----------------------------------------------------------------------------
def _get_bool_attr(obj: Any, primary: str, fallback: str, default: bool = False) -> bool:
    if not obj:
        return default
    if hasattr(obj, primary):
        return bool(getattr(obj, primary))
    if hasattr(obj, fallback):
        return bool(getattr(obj, fallback))
    return default


def _sched_to_status_payload(
    enabled: bool,
    scheduler: Optional[Any],
    extra: Dict[str, Any],
) -> Dict[str, Any]:
    # Earnings exposes is_running; Market Data currently uses _is_running
    is_running = _get_bool_attr(scheduler, "is_running", "_is_running", False)
    next_run_at = getattr(scheduler, "next_run_at", None) if scheduler else None
    last_run_at = getattr(scheduler, "last_run_at", None) if scheduler else None
    last_result = getattr(scheduler, "last_result", None) if scheduler else None

    payload = {
        "enabled": bool(enabled),
        "is_running": is_running,
        "next_run_at": str(next_run_at) if next_run_at else None,
        "last_run_at": str(last_run_at) if last_run_at else None,
        "last_result": last_result,
    }
    payload.update(extra or {})
    return payload


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
    earnings_sched = app.state.schedulers.get("earnings")
    market_sched = app.state.schedulers.get("market_data")

    earnings_payload = _sched_to_status_payload(
        enabled=getattr(settings, "ENABLE_EARNINGS_SCHEDULER", False),
        scheduler=earnings_sched,
        extra={
            "type": "earnings",
            "interval_hours": getattr(settings, "EARNINGS_REFRESH_CHECK_INTERVAL_HOURS", None),
            "buffer_days": getattr(settings, "EARNINGS_REFRESH_BUFFER_DAYS", None),
        },
    )
    market_payload = _sched_to_status_payload(
        enabled=getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", False),
        scheduler=market_sched,
        extra={
            "type": "market_data",
            "interval_hours": getattr(settings, "MARKET_DATA_REFRESH_INTERVAL_HOURS", 24),
            "price_lookback_days": getattr(settings, "MARKET_DATA_PRICE_LOOKBACK_DAYS", 45),
            "max_concurrency": getattr(settings, "MARKET_DATA_MAX_CONCURRENCY", 5),
        },
    )
    return {
        "environment": settings.ENVIRONMENT,
        "earnings": earnings_payload,
        "market_data": market_payload,
    }


@app.get("/scheduler/earnings/status", tags=["System"])
async def earnings_scheduler_status():
    earnings_sched = app.state.schedulers.get("earnings")
    return _sched_to_status_payload(
        enabled=getattr(settings, "ENABLE_EARNINGS_SCHEDULER", False),
        scheduler=earnings_sched,
        extra={
            "type": "earnings",
            "interval_hours": getattr(settings, "EARNINGS_REFRESH_CHECK_INTERVAL_HOURS", None),
            "buffer_days": getattr(settings, "EARNINGS_REFRESH_BUFFER_DAYS", None),
        },
    )


@app.get("/scheduler/market-data/status", tags=["System"])
async def market_data_scheduler_status():
    market_sched = app.state.schedulers.get("market_data")
    return _sched_to_status_payload(
        enabled=getattr(settings, "ENABLE_MARKET_DATA_SCHEDULER", False),
        scheduler=market_sched,
        extra={
            "type": "market_data",
            "interval_hours": getattr(settings, "MARKET_DATA_REFRESH_INTERVAL_HOURS", 24),
            "price_lookback_days": getattr(settings, "MARKET_DATA_PRICE_LOOKBACK_DAYS", 45),
            "max_concurrency": getattr(settings, "MARKET_DATA_MAX_CONCURRENCY", 5),
        },
    )


# --- Manual triggers (DEV only)
@app.post("/scheduler/earnings/trigger", tags=["System"])
async def trigger_earnings_now():
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Manual trigger disabled in production")
    sched = app.state.schedulers.get("earnings")
    if not sched:
        raise HTTPException(status_code=503, detail="Earnings scheduler not initialized")
    trigger_fn = getattr(sched, "trigger_immediate_check", None) or getattr(sched, "trigger_immediate_run", None)
    if not trigger_fn:
        raise HTTPException(status_code=500, detail="Earnings scheduler does not expose a manual trigger")
    logger.info("🔄 Manual trigger: Earnings scheduler")
    result = await trigger_fn()
    return {"status": "triggered", "result": result}


@app.post("/scheduler/market-data/trigger", tags=["System"])
async def trigger_market_data_now():
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Manual trigger disabled in production")
    sched = app.state.schedulers.get("market_data")
    if not sched:
        raise HTTPException(status_code=503, detail="Market Data scheduler not initialized")
    # MarketDataRefreshScheduler has no public trigger; fallback to private cycle if needed
    trigger_fn = (
        getattr(sched, "trigger_immediate_run", None)
        or getattr(sched, "trigger_immediate_check", None)
        or getattr(sched, "_refresh_cycle", None)
    )
    if not trigger_fn:
        raise HTTPException(status_code=500, detail="Market Data scheduler does not expose a manual trigger")
    logger.info("🔄 Manual trigger: Market Data scheduler")
    result = await trigger_fn()
    return {"status": "triggered", "result": result}


# Legacy trigger (back-compat → earnings)
@app.post("/scheduler/trigger", tags=["System"])
async def trigger_scheduler_now_legacy():
    if settings.is_production:
        raise HTTPException(status_code=403, detail="Manual trigger disabled in production")
    sched = app.state.schedulers.get("earnings")
    if not sched:
        raise HTTPException(status_code=503, detail="Earnings scheduler not initialized")
    trigger_fn = getattr(sched, "trigger_immediate_check", None) or getattr(sched, "trigger_immediate_run", None)
    if not trigger_fn:
        raise HTTPException(status_code=500, detail="Earnings scheduler does not expose a manual trigger")
    logger.info("🔄 Manual scheduler trigger requested (legacy earnings endpoint)")
    result = await trigger_fn()
    return {"status": "triggered", "result": result}


# -----------------------------------------------------------------------------
# API routers
# -----------------------------------------------------------------------------
app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)
app.include_router(valuations.router) 
app.include_router(analysis.router)