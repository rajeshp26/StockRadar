
from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    watchlist_name: str
    description: str | None = None
    is_default: bool = False

class WatchlistItemCreate(BaseModel):
    watchlist_id: int
    # The ticker symbol for the company, e.g., "AAPL"
    ticker_symbol: str = Field(..., description="The stock ticker symbol, e.g., AAPL")
    target_buy: float | None = None
    target_sell: float | None = None
    position: int | None = None
