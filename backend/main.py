
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import watchlists, watchlist_items, users
import asyncio
import yfinance as yf
from database import supabase
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Start background price monitor
    monitor_task = asyncio.create_task(background_price_monitor())
    yield
    # Shutdown: Stop monitor
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass

async def background_price_monitor():
    """
    Background task that fetches prices only for symbols with active subscribers.
    """
    print("[DEBUG] Background monitor started.")
    while True:
        try:
            from api.watchlists import symbol_subscribers, broadcast_stock_update
            
            # 1. Get only symbols that someone is actually watching RIGHT NOW
            active_symbols = list(symbol_subscribers.keys())
            
            if not active_symbols:
                await asyncio.sleep(5) 
                continue

            print(f"[DEBUG] Monitor: Updating {len(active_symbols)} active symbols.")

            # 2. Fetch latest prices in batch
            tickers = yf.Tickers(active_symbols)
            for symbol in active_symbols:
                ticker = tickers.tickers.get(symbol)
                if not ticker: continue
                
                info = ticker.info
                # Try multiple fields as yfinance can be inconsistent
                current_price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('postMarketPrice')
                prev_close = info.get('regularMarketPreviousClose') or info.get('previousClose')
                
                if current_price and prev_close:
                    change = float(current_price) - float(prev_close)
                    change_percent = (change / float(prev_close)) * 100
                    
                    # 3. Broadcast to interested subscribers
                    await broadcast_stock_update(symbol, current_price, change, change_percent)
            
            # Wait 10 seconds between background checks
            await asyncio.sleep(10)
            
        except Exception as e:
            print(f"[ERROR] background_price_monitor: {e}")
            await asyncio.sleep(10)

app = FastAPI(lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all the routers for the different API sections
app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)
