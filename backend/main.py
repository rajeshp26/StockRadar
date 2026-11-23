# main.py
import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime

import yfinance as yf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api import analysis, super_investors, users, valuations, watchlist_items, watchlists
from api.chat import router as chat_router
from api.portfolio import router as portfolio_router
from api.stocks import router as stocks_router
from auth import get_current_user
from config import settings
from database import supabase
from dependencies import get_current_user_dep, limiter
from shared.api_tracing import RequestTracingMiddleware
from shared.logging_setup import (
    CONSOLE_FORMAT,
    install_correlation_stamping,
    setup_debug_logging,
)

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
# Stamp the correlation id onto every record before any handler formats it, so
# CONSOLE_FORMAT's %(correlation_id)s is always populated. This runs before
# basicConfig so the root handler is already using CONSOLE_FORMAT by the time
# the first record is created. See logging_setup.install_correlation_stamping
# for why this is a record factory rather than a Filter.
install_correlation_stamping()
logging.basicConfig(
    level=getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO),
    format=CONSOLE_FORMAT,
)
logger = logging.getLogger("stockerpro.main")

# §4.8: correlation IDs — one ID per request, echoed on the response and
# attached to every log record via a contextvar + record factory so a request's
# logs can be traced end-to-end.
#
# The contextvar lives in shared.debug_trace rather than here. It used to be
# module-local, so no repository or service could read the active id without
# importing main (circular) — and the nightly snapshot job, which runs in a
# separate worker process with no request, therefore had no id at all. Jobs mint
# one with debug_trace.trace_scope().
setup_debug_logging()

# -----------------------------------------------------------------------------
# Background: real-time price monitor (existing)
# -----------------------------------------------------------------------------
class _YFinanceQuoteAdapter:
    """Adapts yfinance to the one-listing-at-a-time QuoteProvider protocol.

    No `.TO/.V/.NE` fan-out: the security already carries its exact provider
    symbol. A rate-limit response is translated into RateLimitHit so the
    per-security breaker can back off only that listing.
    """

    def get_quote(self, provider_symbol: str) -> dict:
        try:
            info = yf.Ticker(provider_symbol).info or {}
        except Exception as exc:
            text = str(exc)
            if (
                "RateLimit" in type(exc).__name__
                or "429" in text
                or "Too Many Requests" in text
            ):
                from domain.provider_resilience import RateLimitHit
                raise RateLimitHit(retry_after=60.0, message=text) from exc
            raise
        return {
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "previous_close": info.get("regularMarketPreviousClose"),
        }


# One breaker for the whole monitor, keyed by security_id so a throttled CDR
# never silences its sibling listing or any other symbol.
_price_monitor_breaker = None  # initialised on first cycle (imports stay local)


async def background_price_monitor():
    """Monitor and broadcast quotes keyed by *listing* identity.

    Exactly one provider request is issued per active listing, using its own
    provider_symbol. There is no N×3 suffix fan-out and no company-wide CDR
    adjustment: each security carries its own kind/ratio, and the SSE event carries
    the full identity so META/NMS and META/NEO stay distinguishable. A rate limit
    backs off only the throttled security_id, and resets after its retry window.
    """
    global _price_monitor_breaker
    from api.watchlists import broadcast_stock_update, symbol_subscribers
    from domain.provider_resilience import (
        ListingRateLimitBreaker,
        refresh_listing,
    )
    from domain.valuation import ValuationError, price_for_listing
    from infrastructure.repositories.security_repository import SecurityRepository

    if _price_monitor_breaker is None:
        _price_monitor_breaker = ListingRateLimitBreaker(cooldown_seconds=60.0)
    breaker = _price_monitor_breaker
    adapter = _YFinanceQuoteAdapter()
    interval = max(1, int(getattr(settings, "SSE_UPDATE_INTERVAL_SECONDS", 10)))
    catalog = SecurityRepository()
    while True:
        try:
            active_symbols = list(symbol_subscribers.keys())
            if not active_symbols:
                await asyncio.sleep(min(5, interval))
                continue

            # A ticker can have several listings. Resolve all of them; never guess a
            # single listing from the company row.
            securities: list[dict] = []
            for sym in set(active_symbols):
                securities.extend(catalog.list_securities_for_symbol(sym))
            if not securities:
                await asyncio.sleep(interval)
                continue

            updated = skipped = 0
            for security in securities:
                sid = int(security["security_id"])
                psym = security["provider_symbol"]
                # One provider request for this listing, guarded by its own breaker.
                result = refresh_listing(adapter, security, breaker)
                if result.skipped:
                    skipped += 1
                    if result.reason == "rate_limited":
                        logger.warning(
                            "[PriceMonitor] %s (security %s): rate limited, "
                            "backing off this listing only", psym, sid,
                        )
                    continue
                breaker.reset(sid)  # successful probe closes this listing's breaker
                current = result.price
                prev = result.raw.get("previous_close")
                if current is None or prev is None:
                    skipped += 1
                    continue
                try:
                    effective, _ = price_for_listing(security, current)
                    effective_prev, _ = price_for_listing(security, prev)
                except ValuationError as exc:
                    logger.warning("[PriceMonitor] %s: %s", psym, exc.message)
                    skipped += 1
                    continue

                last_updated = datetime.now(UTC).isoformat()
                try:
                    catalog.upsert_quote(security["security_id"], {
                        "current_price": float(current),
                        "close_price": float(prev),
                        "last_updated": last_updated,
                        "source": "yfinance",
                        "is_stale": False,
                    })
                except Exception as exc:
                    logger.debug("[PriceMonitor] %s quote write failed: %s", psym, exc)

                change = float(effective - effective_prev)
                change_percent = (change / float(effective_prev)) * 100 if effective_prev else 0.0
                await broadcast_stock_update(
                    security["symbol"], float(effective), change, change_percent,
                    identity=security,
                )
                updated += 1

            logger.debug("[PRICE-MONITOR] cycle: %s updated, %s skipped", updated, skipped)
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
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
    app.state.tasks: dict[str, asyncio.Task] = {}

    # STARTUP ---------------------------------------------------------------
    # No Firebase initialization — Supabase JWT verification uses lazy JWKS fetch

    # Dependency preflight: surface drift from requirements.txt at boot rather
    # than silently serving unreliable price data (see
    # scripts/preflight_dependencies.py for the outage this prevents).
    from scripts.preflight_dependencies import startup_check
    startup_check(logger=logger)

    # SSE price monitor (stays in FastAPI - real-time user-facing)
    price_task = asyncio.create_task(background_price_monitor(), name="price_monitor")
    app.state.tasks["price_monitor"] = price_task
    logger.info("✅ Price monitor started")

    # §4.1 tracer: event-loop lag sampler (times every sync .execute() via
    # database.TimedClient; summary at GET /internal/trace)
    from tracing import start_loop_lag_sampler
    lag_task = asyncio.create_task(start_loop_lag_sampler(), name="loop_lag_sampler")
    app.state.tasks["loop_lag_sampler"] = lag_task
    logger.info("📈 Loop-lag sampler started")

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

    logger.info("Schedulers run in separate worker process (scheduler_worker.py)")

    try:
        yield
    finally:
        # SHUTDOWN ----------------------------------------------------------
        # Cancel background tasks
        for task in list(app.state.tasks.values()):
            with suppress(Exception):
                task.cancel()

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
async def trace_request_middleware(request, call_next):
    """Feeds the in-memory latency summary served by /internal/trace.

    Separate from RequestTracingMiddleware on purpose: this one is a rolling
    in-process aggregate, that one writes a durable per-request record. Dropping
    this would leave /internal/trace reporting zero spans with no error.
    """
    import time as _time

    from tracing import tracer
    tracer.active_requests += 1
    t0 = _time.perf_counter()
    try:
        return await call_next(request)
    finally:
        tracer.active_requests -= 1
        tracer.record_request((_time.perf_counter() - t0) * 1000.0)


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

# Registered last so it is the OUTERMOST middleware: Starlette inserts each
# add_middleware at index 0 and wraps user_middleware[0] last, so the final
# registration runs first. The trace id must already be set when the cache,
# timing, CORS and route layers run, or their records get stamped with None.
app.add_middleware(RequestTracingMiddleware)

# -----------------------------------------------------------------------------
# System endpoints
# -----------------------------------------------------------------------------
@app.get("/health", tags=["System"])
async def health_check():
    return {"status": "healthy", "environment": settings.ENVIRONMENT}

@app.get("/internal/trace", tags=["System"])
async def internal_trace():
    """§4.1 evidence: event-loop lag, sync .execute() timings, request spans."""
    from tracing import tracer
    return tracer.summary()

@app.get("/ready", tags=["System"])
async def readiness_check():
    try:
        supabase.table("users").select("user_id").limit(1).execute()
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        logger.error(f"Readiness failed: {e}")
        raise HTTPException(status_code=503, detail="Service not ready") from e

@app.get("/scheduler/status", tags=["System"])
async def schedulers_status():
    """
    Scheduler status endpoint — reads runtime state from DB.
    Returns scheduler state, worker heartbeats, and job queue stats.
    """
    from infrastructure.repositories.scheduler_repository import SchedulerRepository
    repo = SchedulerRepository()

    from datetime import datetime

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
        now = datetime.now(UTC)
        heartbeats = repo.get_worker_heartbeats(minutes=5)
        alive = any(
            h.get("last_hb_at") and (now - datetime.fromisoformat(h["last_hb_at"].replace("Z", "+00:00")).replace(tzinfo=UTC)).total_seconds() < 120
            for h in (heartbeats or [])
        )

        # Stale heartbeats count (workers not seen in 2+ minutes)
        stale_heartbeats = sum(
            1 for h in (heartbeats or [])
            if h.get("last_hb_at")
            and (now - datetime.fromisoformat(h["last_hb_at"].replace("Z", "+00:00")).replace(tzinfo=UTC)).total_seconds() >= 120
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
