from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import asyncio
import yfinance as yf
import logging

from api import watchlists, watchlist_items, users
from config import settings
from database import supabase

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_user_identifier(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return f"auth:{auth_header[-20:]}" 
    return f"guest:{request.client.host}"

limiter = Limiter(key_func=get_user_identifier)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"StockerPro Backend starting in {settings.ENVIRONMENT} mode.")
    monitor_task = asyncio.create_task(background_price_monitor())
    yield
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

async def background_price_monitor():
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
                if not ticker: continue
                info = ticker.info
                current_price = info.get('currentPrice') or info.get('regularMarketPrice')
                prev_close = info.get('regularMarketPreviousClose')
                if current_price and prev_close:
                    change = float(current_price) - float(prev_close)
                    change_percent = (change / float(prev_close)) * 100
                    await broadcast_stock_update(symbol, current_price, change, change_percent)
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"monitor error: {e}")
            await asyncio.sleep(10)

app = FastAPI(
    title="StockerPro API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
)

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

app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)
