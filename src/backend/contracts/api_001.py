# GENERATED from api-001.openapi.yaml — do not edit by hand. Regenerate: framework/contracts/gen_types.py
from typing import TypedDict, Literal, NotRequired

class SecurityListing(TypedDict):
    security_id: int
    symbol: str
    exchange: str
    kind: Literal['COMMON', 'CDR', 'ETF', 'FUND', 'INDEX']
    currency: str
    provider_symbol: str
    name: NotRequired[str]

class SearchListingsResponse(TypedDict):
    results: list

class AddWatchlistItemRequest(TypedDict):
    watchlist_id: int
    security_id: int
    symbol: str
    exchange: str
    kind: Literal['COMMON', 'CDR', 'ETF', 'FUND', 'INDEX']
    currency: str
    provider_symbol: str
    target_buy: NotRequired[float]
    target_sell: NotRequired[float]

class WatchlistItemAdded(TypedDict):
    watchlist_item_id: int
    watchlist_id: int
    security_id: int
    symbol: str
    exchange: str
    kind: Literal['COMMON', 'CDR', 'ETF', 'FUND', 'INDEX']
    currency: str
    provider_symbol: str
    target_buy: NotRequired[float]
    target_sell: NotRequired[float]
    price: NotRequired[float]
    lastUpdated: NotRequired[str]

class AddWatchlistItemResponse(TypedDict):
    watchlist_item: dict
    financials_loading: bool
    is_new_stock: bool

class QuoteSnapshot(TypedDict):
    security_id: int
    symbol: str
    exchange: str
    kind: Literal['COMMON', 'CDR', 'ETF', 'FUND', 'INDEX']
    currency: str
    provider_symbol: str
    price: float
    change: NotRequired[float]
    changePercent: NotRequired[float]
    lastUpdated: NotRequired[str]
    stale: bool

class QuoteEvent(TypedDict):
    type: Literal['price_update']
    security_id: int
    symbol: str
    exchange: str
    kind: Literal['COMMON', 'CDR', 'ETF', 'FUND', 'INDEX']
    currency: str
    provider_symbol: str
    price: float
    change: NotRequired[float]
    changePercent: NotRequired[float]
    lastUpdated: str
    isStale: bool
    source: NotRequired[str]

class ValidationError(TypedDict):
    code: str
    message: str
    fields: NotRequired[list]

