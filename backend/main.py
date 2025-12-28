from fastapi import FastAPI
from api import watchlists, watchlist_items

app = FastAPI()

app.include_router(watchlists.router)
app.include_router(watchlist_items.router)
