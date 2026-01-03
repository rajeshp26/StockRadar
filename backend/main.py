from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
import asyncio
import yfinance as yf

from api import watchlists, watchlist_items, users
from database import supabase

# 1. Initialize Rate Limiter
limiter = Limiter(key_func=get_remote_address)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background price monitor
    monitor_task = asyncio.create_task(background_price_monitor())
    yield
    # Shutdown
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

async def background_price_monitor():
    """Background task for price updates."""
    print("[DEBUG] Background monitor started.")
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
                current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('postMarketPrice')
                prev_close = info.get('regularMarketPreviousClose') or info.get('previousClose')
                if current_price and prev_close:
                    change = float(current_price) - float(prev_close)
                    change_percent = (change / float(prev_close)) * 100
                    await broadcast_stock_update(symbol, current_price, change, change_percent)
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[ERROR] background_price_monitor: {e}")
            await asyncio.sleep(10)

app = FastAPI(lifespan=lifespan)

# 2. Add Rate Limiting State and Exception Handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 3. Security Middleware: Request Size Validation
@app.middleware("http")
async def validate_request_size(request: Request, call_next):
    # Reject payloads larger than 1MB to prevent resource exhaustion
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > 1_000_000:
        raise HTTPException(status_code=413, detail="Request payload too large")
    return await call_next(request)

# 4. Strict CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:9002",
        "http://127.0.0.1:9002",
        "https://9002-*.cloudworkstations.dev", # Handle IDX previews
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=3600,
)

# 5. Include Routers
app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)
