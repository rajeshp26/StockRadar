
from pydantic import BaseModel


class Company(BaseModel):
    company_id: int
    ticker_symbol: str
    company_name: str
    sector:   str | None = None
    industry: str | None = None

class WatchlistItem(BaseModel):
    watchlist_item_id: int
    target_buy: float | None = None
    target_sell: float | None = None
    company: Company

class StockPriceInfo(BaseModel):
    id: int
    symbol: str
    name: str
    sector:   str | None = None
    industry: str | None = None
    price: float
    change: float
    changePercent: float
    targetBuy: float | None = None
    targetSell: float | None = None
    lastUpdated: str | None = None

class WatchlistWithStocks(BaseModel):
    watchlist_id: int
    name: str
    is_default: bool
    stocks: list[StockPriceInfo]
