from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class WatchlistRepository(ABC):
    @abstractmethod
    def find_by_user_id(self, user_id: int) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    def find_default_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def create_default(self, user_id: int, name: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def get_items_by_watchlist_id(self, watchlist_id: int) -> List[Dict[str, Any]]:
        pass

class UserRepository(ABC):
    @abstractmethod
    def find_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        pass
