from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class Company(BaseModel):
    company_id: int
    ticker_symbol: str
    company_name: str

class WatchlistItem(BaseModel):
    watchlist_item_id: int
    target_buy: Optional[float] = None
    target_sell: Optional[float] = None
    company: Company

class StockPriceInfo(BaseModel):
    id: int
    symbol: str
    name: str
    price: float
    change: float
    changePercent: float
    targetBuy: Optional[float] = None
    targetSell: Optional[float] = None
    lastUpdated: Optional[str] = None

class WatchlistWithStocks(BaseModel):
    watchlist_id: int
    name: str
    is_default: bool
    stocks: List[StockPriceInfo]
