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

# Canadian exchange suffixes for yfinance (matches yfinance_provider.EXCHANGE_SUFFIX_MAP)
_YF_SUFFIXES = [".TO", ".V"]

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
            # Resolve Canadian suffixes: try raw symbol first, fall back to .TO / .V
            resolved_symbols = []
            symbol_suffix_map: Dict[str, str] = {}
            for sym in active_symbols:
                resolved_symbols.append(sym)
                symbol_suffix_map[sym] = ""
                for sfx in _YF_SUFFIXES:
                    resolved_symbols.append(sym + sfx)
                    symbol_suffix_map[sym + sfx] = sfx

            all_tickers = yf.Tickers(resolved_symbols)
            updated_count = 0
            skipped_count = 0
            for symbol in active_symbols:
                ticker = all_tickers.tickers.get(symbol)
                info = {}
                if ticker:
                    info = getattr(ticker, "info", {}) or {}
                if not info:
                    # Try suffixed version
                    for sfx in _YF_SUFFIXES:
                        alt = all_tickers.tickers.get(symbol + sfx)
                        if alt:
                            alt_info = getattr(alt, "info", {}) or {}
                            if alt_info:
                                info = alt_info
                                break
                if not info:
                    logger.debug(f"[PRICE-MONITOR-DIAG] {symbol}: no data (tried raw and {_YF_SUFFIXES})")
                    skipped_count += 1
                    continue
                
                current_price = info.get("currentPrice") or info.get("regularMarketPrice")
                prev_close = info.get("regularMarketPreviousClose")
                
                # Apply CDR adjustment if this symbol is a CDR
                try:
                    from database import supabase as _sb
                    comp_res = _sb.table("companies").select("company_id, cdr_ratio").eq("ticker_symbol", symbol).limit(1).execute()
                    comp_row = comp_res.data[0] if comp_res.data else None
                    if comp_row:
                        cid = comp_row["company_id"]
                        hold_check = _sb.table("portfolio_holdings").select("exchange_override").eq("company_id", cid).eq("exchange_override", "TOR").limit(1).execute()
                        if hold_check.data:
                            from shared.snapshot_builder import CDR_RATIO as _CDR_RATIO
                            ratio = float(comp_row["cdr_ratio"]) if comp_row.get("cdr_ratio") is not None else float(_CDR_RATIO)
                            if current_price:
                                current_price = float(current_price) / ratio
                            if prev_close:
                                prev_close = float(prev_close) / ratio
                except Exception:
                    pass

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
    Scheduler status endpoint — reads runtime state from DB.
    Returns scheduler state, worker heartbeats, and job queue stats.
    """
    from infrastructure.repositories.scheduler_repository import SchedulerRepository
    repo = SchedulerRepository()

    from datetime import datetime, timezone

    try:
        # Scheduler state from DB
        scheduler_names = ["super_investors", "market_data", "earnings", "aggregation"]
        states = {}
        for name in scheduler_names:
            state = repo.get_scheduler_state(name)
            if state:
                states[name] = {
                    "enabled": state.get("enabled", False),
                    "last_planned_at": state.get("last_planned_at"),
                    "last_status": state.get("last_status"),
                    "last_error": state.get("last_error"),
                    "next_due_at": state.get("next_due_at"),
                    "interval_hours": state.get("interval_hours"),
                }

        # Worker heartbeats
        now = datetime.now(timezone.utc)
        heartbeats = repo.get_worker_heartbeats(minutes=5)
        alive = any(
            h.get("last_hb_at") and (now - datetime.fromisoformat(h["last_hb_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)).total_seconds() < 120
            for h in (heartbeats or [])
        )

        # Stale heartbeats count (workers not seen in 2+ minutes)
        stale_heartbeats = sum(
            1 for h in (heartbeats or [])
            if h.get("last_hb_at")
            and (now - datetime.fromisoformat(h["last_hb_at"].replace("Z", "+00:00")).replace(tzinfo=timezone.utc)).total_seconds() >= 120
        )

        # Job queue counts
        job_counts = repo.get_queue_depth()

        # Stale leases
        stale_leases = repo.get_stale_lock_count()

        # Oldest pending
        oldest_pending = repo.get_oldest_pending_age_seconds()

    except Exception as e:
        logger.error("Failed to read scheduler state from DB: %s", e)
        states = {}
        heartbeats = []
        job_counts = {}
        stale_leases = 0
        stale_heartbeats = 0
        oldest_pending = None
        alive = False

    return {
        "environment": settings.ENVIRONMENT,
        "schedulers": states,
        "worker": {
            "alive": alive,
            "last_heartbeat": heartbeats[0]["last_hb_at"] if heartbeats else None,
            "active_jobs": heartbeats[0].get("active_jobs") if heartbeats else None,
        },
        "queue": {
            **job_counts,
            "oldest_pending_age_seconds": oldest_pending,
        },
        "stale_leases": stale_leases,
        "stale_heartbeats": stale_heartbeats,
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