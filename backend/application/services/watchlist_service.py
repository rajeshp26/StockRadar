from typing import List, Dict, Any
from domain.interfaces.stock_provider import StockProvider
from domain.interfaces.repository import WatchlistRepository, UserRepository
from domain.entities.watchlist import WatchlistWithStocks, StockPriceInfo
from shared.exceptions.base import NotFoundError, ExternalServiceError
from database import supabase

class WatchlistService:
    def __init__(
        self, 
        stock_provider: StockProvider, 
        watchlist_repo: WatchlistRepository,
        user_repo: UserRepository
    ):
        self.stock_provider = stock_provider
        self.watchlist_repo = watchlist_repo
        self.user_repo = user_repo

    def get_db_user_id(self, firebase_uid: str) -> int:
        user = self.user_repo.find_by_firebase_uid(firebase_uid)
        if not user:
            raise NotFoundError("User not found.")
        return user['user_id']

    def get_default_watchlist_with_items(self, firebase_uid: str) -> WatchlistWithStocks:
        db_user_id = self.get_db_user_id(firebase_uid)

        # 1. Find or Create Default Watchlist
        watchlist = self.watchlist_repo.find_default_by_user_id(db_user_id)
        
        if watchlist:
            watchlist_id = watchlist['id']
            watchlist_name = watchlist['watchlist_name']
            is_default = watchlist['is_default']
        else:
            new_watchlist = self.watchlist_repo.create_default(db_user_id, "My Watchlist")
            watchlist_id = new_watchlist['id']
            watchlist_name = new_watchlist['watchlist_name']
            is_default = new_watchlist['is_default']

        # 2. Fetch Watchlist Items
        raw_watchlist_items = self.watchlist_repo.get_items_by_watchlist_id(watchlist_id)

        if not raw_watchlist_items:
            return WatchlistWithStocks(
                watchlist_id=watchlist_id, 
                name=watchlist_name, 
                is_default=is_default, 
                stocks=[]
            )
        
        symbols = [item['companies']['ticker_symbol'] for item in raw_watchlist_items if item.get('companies')]
        company_ids = [item['companies']['company_id'] for item in raw_watchlist_items if item.get('companies')]

        # 3. Fetch Market Data
        all_tickers_data = {} 
        if symbols:
            all_tickers_data = self.stock_provider.get_tickers_data(symbols)

        market_data_map = {}
        if company_ids:
            market_data_res = supabase.table('current_market_data').select('*').in_('company_id', company_ids).execute()
            if market_data_res.data:
                market_data_map = {item['company_id']: item for item in market_data_res.data}

        # 4. Combine data
        stocks_list = []
        for item in raw_watchlist_items:
            company = item.get('companies')
            if not company: continue
                
            ticker_symbol = company['ticker_symbol']
            ticker_data = all_tickers_data.get(ticker_symbol)
            
            current_price = None
            previous_close = None
            last_updated = None

            if ticker_data:
                current_price = ticker_data.info.get('currentPrice') or ticker_data.info.get('regularMarketPrice')
                previous_close = ticker_data.info.get('previousClose') or ticker_data.info.get('regularMarketPreviousClose')

            db_market_data = market_data_map.get(company['company_id'])
            if db_market_data:
                last_updated = db_market_data.get('last_updated')
                if current_price is None or previous_close is None:
                    current_price = float(db_market_data.get('current_price', 0))
                    previous_close = float(db_market_data.get('close_price')) if db_market_data.get('close_price') else current_price

            if current_price is None or previous_close is None:
                continue

            change = current_price - previous_close
            change_percent = (change / previous_close) * 100 if previous_close else 0
            
            stocks_list.append(StockPriceInfo(
                id=item['watchlist_item_id'],
                symbol=ticker_symbol,
                name=company['company_name'],
                price=current_price,
                change=change,
                changePercent=change_percent,
                targetBuy=item.get('target_buy'),
                targetSell=item.get('target_sell'),
                lastUpdated=last_updated
            ))

        return WatchlistWithStocks(
            watchlist_id=watchlist_id,
            name=watchlist_name,
            is_default=is_default,
            stocks=stocks_list
        )
