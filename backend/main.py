
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import watchlists, watchlist_items, users
import firebase_admin
from firebase_admin import credentials

app = FastAPI()

# Configure CORS
# This allows the frontend (running on a different port) to communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include all the routers for the different API sections
app.include_router(users.router)
app.include_router(watchlists.router)
app.include_router(watchlist_items.router)

