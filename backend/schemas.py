from pydantic import BaseModel, Field
from typing import Optional

class WatchlistCreate(BaseModel):
    watchlist_name: str
    description: Optional[str] = None
    is_default: bool = False

class WatchlistItemCreate(BaseModel):
    watchlist_id: int
    # The ticker symbol for the company, e.g., "AAPL"
    ticker_symbol: str = Field(..., description="The stock ticker symbol, e.g., AAPL") 
    target_buy: Optional[float] = None
    target_sell: Optional[float] = None
    position: Optional[int] = None
